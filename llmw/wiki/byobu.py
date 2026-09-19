"""byobu/tmux 薄封装 + 开窗编排原语（spawn / 复用 / 打标 / 枚举 + session 可见性查询）。

模型：agent 开成 tmux 窗口，归属 / 起算 / backend 打在窗口用户选项上（无自建账本；
tmux 窗口表即注册表）。只被 enter / status / manager 调用。
兼容 tmux ≥ 2.7（无版本分叉）；各原语的替代方案与坑见对应函数注释。
"""

import os
import re
import shlex
import shutil
import subprocess
import time
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from llmw.errors import (
    ByobuCommandFailed,
    InvalidWindowSuffix,
    WindowBackendMismatch,
)

_BYOBU_BIN = "byobu-tmux"
# 兜底 session 名（代码常量，不可配）：tmux 外且可见 session 数 ≠1 时的落点。
# 命名约束：禁含 `-`、禁 `_` 开头——byobu-select-session 菜单按此隐藏 session，
# 违规名会被裸 byobu 永远挡在直达门外（与 visible_sessions 口径同源）。
BYOBU_SESSION = "llm_workspace"

# pane_dead 格式变量的字面量（_LIST_FORMAT 的 #{pane_dead}）：消费端统一引此，不裸比较 "1"
DEAD_FLAG = "1"

# 最近一次失败命令的 stderr（单线程 CLI 无并发问题）——供异常消息带真实报错，
# 不能只靠 returncode 猜。
_LAST_STDERR = ""

# suffix 校验（wiki 名由 NAME_RE 保证；suffix 是 --window-suffix 的实际输入）
_SUFFIX_RE = re.compile(r"^[a-z0-9_-]{1,16}$")
_WINDOW_NAME_MAX = 40

# byobu wrapper 的 stdout 污染（见 _run docstring）：只剥 OSC 标题序列，
# 不动其它 ANSI（TUI 内容的颜色等）。
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

# 枚举 10 字段：@llmw_* 为打标；pane_current_command 供 BACKEND fallback 与假活检测。
# 解析产物 = WindowRow（消费端属性访问；列序只在本类与 _LIST_FORMAT 维护）。
_LIST_FORMAT = (
    "#{session_name}\t#{window_id}\t#{window_name}\t#{window_activity}\t"
    "#{pane_dead}\t#{pane_dead_time}\t#{@llmw_wiki}\t#{@llmw_started}\t"
    "#{@llmw_backend}\t#{pane_current_command}"
)


class WindowRow(NamedTuple):
    """解析行；字段序 = _LIST_FORMAT 列序。"""

    session: str
    window_id: str
    window_name: str
    activity: str
    dead: str
    dead_time: str
    wiki: str
    started: str
    backend: str
    pcmd: str


class SpawnSpec(NamedTuple):
    session: str
    window_name: str
    wiki: str
    cwd: str
    cmd_argv: List[str]
    env: Dict[str, str]
    backend: str
    ensure: bool = False


def byobu_available() -> bool:
    return shutil.which(_BYOBU_BIN) is not None


def window_name_for(wiki: str, suffix: str) -> str:
    if not _SUFFIX_RE.match(suffix):
        raise InvalidWindowSuffix(
            f"window suffix '{suffix}' 非法",
            hint="suffix 须匹配 ^[a-z0-9_-]{1,16}$（如 main / ingest / index）",
        )
    name = f"{wiki}-{suffix}"
    if len(name) > _WINDOW_NAME_MAX:
        raise InvalidWindowSuffix(
            f"窗口名 '{name}' 过长 ({len(name)} > {_WINDOW_NAME_MAX})",
            hint="缩短 wiki 名或 suffix",
        )
    return name


def _run(args: List[str]) -> "subprocess.CompletedProcess[str]":
    """调 byobu-tmux；只信 returncode，stderr 杂讯仅供错误提示。

    stdout 统一剥离 OSC 序列：byobu wrapper 每次调用都前置终端标题
    ``\\x1b]0;user@host (ip) - byobu\\x07``，不清洗会污染所有 -p / -F / list-* 解析。
    """
    global _LAST_STDERR
    p = subprocess.run(
        [_BYOBU_BIN] + args,
        capture_output=True,
        text=True,
        check=False,
    )
    p.stdout = _OSC_RE.sub("", p.stdout)
    if p.returncode != 0:
        _LAST_STDERR = _OSC_RE.sub("", p.stderr).strip()
    return p


def current_session() -> Optional[str]:
    if not os.environ.get("TMUX"):
        return None
    p = _run(["display-message", "-p", "#S"])
    return p.stdout.strip() if p.returncode == 0 else None


def has_session(name: str) -> bool:
    return _run(["has-session", "-t", name]).returncode == 0


def visible_sessions() -> List[str]:
    """裸 byobu 菜单可见的 session 名（tmux 外 enter 选路用）。

    隐藏 `_` 开头与含 `-` 的名字——与 byobu-select-session 菜单口径对齐：
    enter 选中的 session 必须与用户敲裸 byobu 会进的一致，否则分组残影会把
    "唯一真实 session" 场景顶成 ≥2。
    """
    p = _run(["list-sessions", "-F", "#{session_name}"])
    if p.returncode != 0:
        return []
    return [
        s for s in p.stdout.splitlines() if s and not s.startswith("_") and "-" not in s
    ]


def _window_id(p: "subprocess.CompletedProcess[str]") -> Optional[str]:
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def new_session(
    session: str, window_name: str, cwd: str, shell_cmd: str
) -> Optional[str]:
    """一步建成 session + 首窗口（避免留裸 shell 窗口）；失败 → None。"""
    return _window_id(
        _run(
            [
                "new-session",
                "-d",
                "-s",
                session,
                "-P",
                "-F",
                "#{window_id}",
                "-n",
                window_name,
                "-c",
                cwd,
            ]
            + [shell_cmd]
        )
    )


def new_window(
    session: str, window_name: str, cwd: str, shell_cmd: str
) -> Optional[str]:
    """在指定 session 开窗口；失败 → None。

    ``-t <session>:`` 显式冒号段：target-window 无冒号时整串按窗口 index/name 解析，
    数字 session 名（tmux/byobu 默认 "0"/"1"…）会被窗口 index 匹配抢先报 in use。
    """
    return _window_id(
        _run(
            [
                "new-window",
                "-t",
                f"{session}:",
                "-P",
                "-F",
                "#{window_id}",
                "-n",
                window_name,
                "-c",
                cwd,
            ]
            + [shell_cmd]
        )
    )


def find_tagged_window(
    session: str, window_name: str, wiki: str, backend: str
) -> Optional[Tuple[str, bool, bool]]:
    """按窗口名 + @llmw_wiki + @llmw_backend 判复用；无命中 → None。

    返回 (window_id, pane_dead, backend_matches)。老窗口无 backend 标 = 不符
    （状态不明不猜）。pane_dead / backend 不符的处置由调用方做。
    """
    p = _run(
        [
            "list-windows",
            "-t",
            session,
            "-F",
            "#{window_id}\t#{window_name}\t#{@llmw_wiki}\t#{pane_dead}\t#{@llmw_backend}",
        ]
    )
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        wid, wname, tag, dead, tagged_backend = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        if wname == window_name and tag == wiki:
            return wid, dead == DEAD_FLAG, tagged_backend == backend
    return None


def select_window(window_id: str) -> bool:
    return _run(["select-window", "-t", window_id]).returncode == 0


def tag_window(window_id: str, wiki: str, backend: str) -> None:
    """新开窗口打标；@llmw_started = 起算时刻（复用不刷新）。"""
    p1 = _run(["set-option", "-w", "-t", window_id, "@llmw_wiki", wiki])
    p2 = _run(
        ["set-option", "-w", "-t", window_id, "@llmw_started", str(int(time.time()))]
    )
    p3 = _run(["set-option", "-w", "-t", window_id, "@llmw_backend", backend])
    if p1.returncode != 0 or p2.returncode != 0 or p3.returncode != 0:
        raise ByobuCommandFailed(
            f"窗口打标失败 (window={window_id}, wiki={wiki})",
            hint="打标失败 = 窗口对 status 不可见；可手动 kill-window 清理后重试"
            + (f"（tmux: {_LAST_STDERR}）" if _LAST_STDERR else ""),
        )


def list_windows() -> List[WindowRow]:
    """全 server 窗口枚举；无 server / 无窗口 → []。

    逐 session 枚举（兼容 tmux ≥2.7）；session 两次调用间消失 → 跳过（快照语义）。
    按 window_id 去重：linked/grouped session 下同一窗口在多 session 可见，
    不去重会出重复行 / 让 stop 误报多候选。
    """
    p = _run(["list-sessions", "-F", "#{session_name}"])
    if p.returncode != 0:
        return []
    rows: List[WindowRow] = []
    seen: Set[str] = set()
    for sname in p.stdout.splitlines():
        q = _run(["list-windows", "-t", sname, "-F", _LIST_FORMAT])
        if q.returncode != 0:
            continue  # session 恰在两次调用间消失 → 跳过（快照边界，可接受）
        for line in q.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < len(WindowRow._fields):
                continue
            row = WindowRow(*parts[: len(WindowRow._fields)])
            if row.window_id in seen:
                continue  # linked/grouped session 重复 → 只保留首个
            seen.add(row.window_id)
            rows.append(row)
    return rows


def kill_window(window_id: str) -> bool:
    return _run(["kill-window", "-t", window_id]).returncode == 0


def capture_pane_tail(window_id: str, lines: int = 15) -> str:
    """捕获当前 pane 尾部文本（STATE 判定用）；失败 → 空串。

    -J 合并折行：窄 pane 下 TUI hint 会被硬折行拆开，子串匹配失效。
    """
    p = _run(["capture-pane", "-p", "-J", "-t", window_id, "-S", f"-{lines}"])
    if p.returncode != 0:
        return ""
    return p.stdout


def attach_session(session: str) -> bool:
    """TTY 下 attach（阻塞至 detach）；不走 _run 捕获（交互客户端，捕获会与 TUI 冲突）。"""
    return subprocess.run([_BYOBU_BIN, "attach-session", "-t", session]).returncode == 0


def spawn_window(spec: SpawnSpec) -> Tuple[bool, str, bool]:
    """开 agent 窗口或复用带标同名窗口（env 前缀拼 shell_cmd；argv[0] 先解析绝对路径）。

    Returns:
        (created, window_id, collected)：created True=新建 / False=复用；
        collected=True 表示新建前收掉了同名 dead 残留（供调用方打印）。
    """
    session = spec.session
    window_name = spec.window_name
    wiki = spec.wiki
    cwd = spec.cwd
    backend = spec.backend
    resolved = shutil.which(spec.cmd_argv[0]) or spec.cmd_argv[0]
    # env 走命令前缀注入：`K=V cmd` 赋值前缀是 sh -c 原生语义（取代 tmux 3.2+ 的 -e），
    # 全版本兼容；值过 shlex.quote。调用方只传非敏感变量（LLM_WIKI_ROOT 路径）。
    env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in spec.env.items())
    shell_cmd = " ".join(shlex.quote(a) for a in [resolved] + list(spec.cmd_argv[1:]))
    if env_prefix:
        shell_cmd = f"{env_prefix} {shell_cmd}"

    if spec.ensure and not has_session(session):
        wid = new_session(session, window_name, cwd, shell_cmd)
        if wid is not None:
            tag_window(wid, wiki, backend)
            return True, wid, False
        # 并发下另一个 enter 抢先建了 session → 落入窗口级路径

    collected = False
    found = find_tagged_window(session, window_name, wiki, backend)
    if found is not None:
        wid, dead, backend_ok = found
        if dead:
            # 收尸：dead pane 无活进程，无需确认；收尸后新开，保持
            # "1 个 <wiki>-<suffix> 至多 1 个窗口"不变量
            kill_window(wid)
            collected = True
        elif backend_ok:
            if select_window(wid):
                return False, wid, False
            # select 失败（窗口刚好死掉）→ 降级 new-window
        else:
            # 拒绝：带标活窗但 backend 不符（或老窗口无 @llmw_backend 标）——
            # 复用会吞掉"切换 agent"的意图；不自动开同名第二窗口（唯一性不变量）
            raise WindowBackendMismatch(
                f"窗口 '{window_name}' 正在运行其他 backend 的 agent",
                hint="先 `llmw wiki --name=<wiki> stop` 收掉旧窗口，"
                "或用 `--window-suffix` 开第二窗口并行",
            )

    wid = new_window(session, window_name, cwd, shell_cmd)
    if wid is None:
        # new-window 失败：session 在 has_session 之后被 kill → 最后重试一次一步建
        wid = new_session(session, window_name, cwd, shell_cmd)
    if wid is None:
        raise ByobuCommandFailed(
            f"byobu 开窗失败 (session={session}, window={window_name})",
            hint="new-window 与 new-session 均失败——检查 tmux server 状态；"
            "可手动 `byobu-tmux has-session -t "
            f"{session}` 诊断" + (f"（tmux: {_LAST_STDERR}）" if _LAST_STDERR else ""),
        )
    tag_window(wid, wiki, backend)
    return True, wid, collected
