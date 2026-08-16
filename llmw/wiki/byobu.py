"""wiki enter 的 tmux 窗口模式 — 当前 session 开 agent 窗口 + 兜底 session llm_workspace

设计 (doc/session-visibility-design.md §2)：enter 把 agent 开成"当前 tmux session 的一个
窗口"（W' 模型）；不在 tmux 内时用兜底 session llm_workspace。**不维护任何自建 session
账本**——spawn 时在窗口上打两个 tmux 用户选项（@llmw_wiki 归属 / @llmw_started 起算
时间戳）；agent 是窗口主命令，进程退出 → pane 销毁 → 窗口消亡 → 标记随之消亡。
tmux 窗口表即注册表，枚举即现实——无心跳、无轮询、无僵尸记录。

本模块是 byobu/tmux 的薄封装 + 开窗编排（spawn / 复用 / 打标 / 枚举四原语），
只被 llmw/wiki/enter.py / llmw/wiki/status.py / llmw/wiki/manager.py 调用；
不写元数据、不读配置。

设计要点：

- **版本口径**：目标 tmux ≥ 2.7（软性下限，设计 §1.4 A3，2026-08-15 修订）——只使用
  2.7 时代已稳定存在的原语，**无版本分叉、无运行时版本检测**；本机实测 3.4。三处
  曾经的版本钉子已拔掉：``-e`` 注入（3.2+）→ 命令前缀；``list-windows -a``（2.9+）→
  逐 session 枚举；``#{pane_dead_time}``（疑 2.9+）缺失 → R5 activity 回退。
- **一律调 ``byobu-tmux``**（/usr/bin/byobu 的 symlink）：byobu 启动脚本经 argv[0]
  强制 BYOBU_BACKEND=tmux（盖过 ~/.byobu/backend 配置）；带参数调用时
  ``exec tmux -u -f <byobu tmuxrc> "$@"`` 全透传（/usr/bin/byobu:258-267）。
- **窗口 target 一律用 ``#{window_id}``（@N），不用名字**——wiki NAME_RE 允许纯数字
  名（如 123），``select-window -t session:123`` 有 name/index 解析歧义。
- **session target 一律用 ``<name>:``（显式冒号段）**——target-window 类命令
  （``new-window -t``）无冒号时整串先按**窗口 index/name** 解析：数字 session 名
  （tmux / byobu 默认命名 "0" / "1"…）必被窗口 index 匹配抢先，``new-window -t 1``
  实际是"在 index 1 处创建"→ 已占用时报 ``create window failed: index 1 in use``
  （2026-08-15 实机复现，用户 byobu 恰为数字名 session）。``<name>:`` 强制走
  session 段解析（man：session 名逐条精确/前缀匹配），数字名无歧义。target-session
  类命令（``has-session`` / ``list-windows -t`` / ``attach-session -t``）不受影响——
  其解析规则含精确名匹配，数字名正常（实测 ``has-session -t 1`` 通过）。
- **agent argv[0] 先经 shutil.which 解析为绝对路径**：tmux server 的环境来自启动
  server 的进程（可能是很久前的登录 shell），其 PATH 不一定含 agent 所在目录
  （如 ~/.local/bin）；llmw 里 which 通过 ≠ 窗口里 sh -c 找得到。
- **agent 命令拼 shell 字符串**：tmux 对 shell-command 走 ``sh -c``，拼串形态全版本
  兼容（多 argv 直 exec 是 3.4 行为，不依赖）；py3.7 无 shlex.join，手写
  ``" ".join(shlex.quote(a) for a in argv)``。
- **env 注入走命令前缀**（2026-08-15 起取代 tmux 3.2+ 的 ``-e``）：``K=V cmd`` 前缀
  拼进 shell_cmd——赋值前缀是 ``sh -c`` 原生语义，全版本通用；值过 shlex.quote。
  **只允许非敏感变量**（LLM_WIKI_ROOT 是路径）——api_key 恒走 overlay 文件交付
  （[[model-ops-no-env-vars]]）。语义差异：``-e`` 写 window 环境（respawn 后仍带），
  前缀只作用初始进程（respawn 后丢失）——用户手动 respawn 边缘场景，可接受。
- **status 枚举走逐 session**（2026-08-15 起取代 2.9+ 的 ``list-windows -a``）：
  ``list-sessions`` + 每 session ``list-windows -t <name>``——远古原语，行为全版本
  一致；session 在两次调用间消失 → 跳过不报错（快照语义）。调用方自行稳定排序。
- **窗口名经 ``new-window -n`` 锁定**：tmux 对显式命名的窗口自动关闭该窗口的
  automatic-rename，agent 进程改名（OSC escape 只改 pane title）不影响窗口名。
- **R1 窗口名**：一律 ``<wiki>-<suffix>`` 形态，suffix 默认 ``main``；suffix 校验
  ``^[a-z0-9_-]{1,16}$``，拼接后总长 ≤40 字符（防误开 + 名字即用途 + 形状恒定消歧）。
- **R2 复用**：作用域 session 内，窗口名精确匹配 **AND** ``@llmw_wiki`` == 当前 wiki
  **AND** ``@llmw_backend`` == 当前 backend **AND** pane 非 dead 四条件命中 →
  select-window；命中但 **backend 不符** → 拒绝（调用方 exit 1 + hint"先 stop 或
  --window-suffix"，防"切换 agent"意图被静默吞掉）；命中但已 dead → kill-window
  收尸后按无窗口新开（尸体无活进程，非 R6 高危动作；防复用尸体落在死 pane 上
  误报"agent 已在运行"，并保持"1 个 <wiki>-<suffix> 至多 1 个窗口"不变量——
  同名一死一活共存会使 stop 的 --window-suffix 消歧失效）；否则新开
  （防劫持用户自开的同名非 llmw 窗口）。
- **R3 打标**：仅新开窗口时打 ``@llmw_wiki`` + ``@llmw_started``；复用**不刷新**
  ``@llmw_started``（"session 起来多久"从最初 spawn 起算）。
- **竞争只做线性降级（≤3 步），不上锁**：双 enter 首建竞争的产物是同名窗口共存
  （tmux 允许），后续 find 取带标精确匹配，行为确定（README 已知限制）。
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
# 兜底 session 名（代码常量，不可配）：enter 不在 tmux 内时的落点，status/enter 共享
BYOBU_SESSION = "llm_workspace"

# pane_dead 格式变量的字面量（_LIST_FORMAT 的 #{pane_dead}）：消费端统一引此，不裸比较 "1"
DEAD_FLAG = "1"

# 最近一次失败命令的 stderr（单线程 CLI 无并发问题；供异常消息诊断——
# 关键失败的真实报错要能上抛，不能只靠 returncode 猜）
_LAST_STDERR = ""

# R1: suffix 校验（wiki 名由 NAME_RE 保证；suffix 是 enter 新入口的输入）
_SUFFIX_RE = re.compile(r"^[a-z0-9_-]{1,16}$")
_WINDOW_NAME_MAX = 40

# 枚举格式（R5，2026-08-15 扩展为 10 字段）：status 实时枚举的字段集合；
# @llmw_wiki / @llmw_started / @llmw_backend 为打标；pane_current_command 供
# BACKEND 列 fallback 与假活（shell 残留）检测。解析产物是 WindowRow NamedTuple
# （本模块唯一出口——消费端用属性访问，不再有索引手抄）。
_LIST_FORMAT = (
    "#{session_name}\t#{window_id}\t#{window_name}\t#{window_activity}\t"
    "#{pane_dead}\t#{pane_dead_time}\t#{@llmw_wiki}\t#{@llmw_started}\t"
    "#{@llmw_backend}\t#{pane_current_command}"
)


class WindowRow(NamedTuple):
    """list_windows() 的解析行（10 字段，与 _LIST_FORMAT 一一对应）。

    消费端（status.py / manager.py）一律属性访问——列序改动只动本类与 _LIST_FORMAT。
    """

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
    """spawn_window 的参数簇（T12 收参数对象，巡检 #6）。

    调用方只有 enter.py:_spawn——拆对象是为读法清晰（8 个平铺参数容易错位），
    不是为多态。
    """

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
    """R1 窗口名：``<wiki>-<suffix>`` 拼接 + 校验。suffix 缺省 'main'。

    非法（suffix 不符 ``^[a-z0-9_-]{1,16}$`` 或拼接后 >40 字符）→ InvalidWindowSuffix。
    """
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
    """调 byobu-tmux；只信 returncode。

    byobu 包装器每次调用都会先跑 byobu-janitor 等副作用（/usr/bin/byobu:108），
    stderr 可能有杂讯——不作为失败判据，仅供上层拼错误提示。
    失败时把 stderr 摘要记入 _LAST_STDERR，供异常消息带上真实报错（如
    ``create window failed: index 1 in use``——数字 session 名的经典歧义）。
    """
    global _LAST_STDERR
    p = subprocess.run(
        [_BYOBU_BIN] + args,
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        _LAST_STDERR = p.stderr.strip()
    return p


def current_session() -> Optional[str]:
    """llmw 进程所在的 tmux session 名；不在 tmux 内或 server 已死 → None。"""
    if not os.environ.get("TMUX"):
        return None
    p = _run(["display-message", "-p", "#S"])
    return p.stdout.strip() if p.returncode == 0 else None


def has_session(name: str) -> bool:
    """session 是否存在（无 server / 无 session 统一 False）。"""
    return _run(["has-session", "-t", name]).returncode == 0


def _window_id(p: "subprocess.CompletedProcess[str]") -> Optional[str]:
    """从 ``-P -F '#{window_id}'`` 输出提 window_id（@N）；失败 → None。"""
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def new_session(
    session: str, window_name: str, cwd: str, shell_cmd: str
) -> Optional[str]:
    """session 与首窗口一步建成（避免先建 session 留下裸 shell 窗口）。

    返回 window_id；失败 → None（如并发竞争 duplicate session）。
    env 已由调用方拼进 shell_cmd 前缀（命令前缀注入，兼容 tmux ≥2.7）。
    """
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
    """在指定 session 开窗口，返回 window_id；失败 → None。

    ``-t <session>:`` 显式冒号段（模块 docstring「session target 一律 <name>:」）——
    target-window 无冒号时整串按窗口 index/name 解析，数字 session 名（tmux/byobu
    默认 "0"/"1"…）会被窗口 index 匹配抢先，``-t 1`` 实际落在 "index 1 in use"。
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
    """R2 复用判定：作用域 session 内「窗口名精确匹配 AND @llmw_wiki == wiki
    AND @llmw_backend == backend」。

    三条件防劫持——用户自开的同名非 llmw 窗口（@llmw_wiki 空）不被误选，而是正常新开
    一个带标窗口；老窗口无 @llmw_backend 标（T9 前的遗留窗口）→ 视为 backend 不符
    （状态不明不猜，拒绝并提示，用户可 stop 或 --window-suffix 绕开）。
    返回 (window_id, pane_dead, backend_matches)；无命中 → None。

    pane_dead=True（remain-on-exit=on 残留尸体）由调用方收尸后按无窗口处理——
    复用尸体会把用户落在无 agent 的死 pane 上（设计 §2.4 R2，2026-08-15 修订）。
    backend_matches=False（带标活窗但 backend 不符）由调用方拒绝 enter——
    复用它会吞掉用户"切换 agent"的意图（设计 §2.4 R2，2026-08-15 修订）。
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
            return wid, dead == "1", tagged_backend == backend
    return None


def select_window(window_id: str) -> bool:
    return _run(["select-window", "-t", window_id]).returncode == 0


def tag_window(window_id: str, wiki: str, backend: str) -> None:
    """R3 打标：仅新开窗口时调用（复用不刷新任何标）。

    @llmw_started = spawn 时刻 unix 时间戳——"session 起来多久"从最初 spawn 起算；
    @llmw_backend = agent CLI 名（claude/qodercli/opencode），供 status 的 BACKEND
    列与 STATE 模式路由；窗口消亡标记随亡（tmux 窗口选项），账本零漂移。
    """
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
    """全 server 窗口枚举（R7 感知模型：无轮询无账本，实时枚举）。

    返回 WindowRow 列表（窗口值空串与 None 同态由调用方决定——字符串空即可判）。
    无 server / 无窗口 → []（tmux daemon 收尸，僵尸条目不存在）。

    逐 session 枚举（`list-sessions` + 每 session `list-windows -t`）——
    2026-08-15 起取代 2.9+ 的 `list-windows -a`，行为全版本一致（设计 §2.4 R5）。
    session 在两次调用间消失 → 该次调用失败 → 跳过不报错（快照语义）。
    **按 window_id 去重**（linked/grouped session，`new-session -t <base>` 无 -s 时
    tmux 自动建 `<base>-<n>` 共享窗口）：窗口是 tmux 唯一实体（window_id 全局唯一），
    linked session 只是同一窗口在多 session 可见——逐 session 枚举会重复返回同一
    窗口，导致 status 重复行 / stop 误报 MultipleRunningSessions。保留首个枚举到的
    session（list-sessions 按创建序），后续同 id 行丢弃。
    10 字段（含 @llmw_backend / pane_current_command，见 _LIST_FORMAT）。
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
    """捕获窗口当前 pane 的屏幕尾部文本（R5 STATE 数据源）。

    只读（capture-pane 不改状态）；失败 → 空串（调用方降级 unknown）。
    target 用 window_id（@N）——target-pane 语法接受窗口引用（取当前 pane）。
    """
    p = _run(["capture-pane", "-p", "-t", window_id, "-S", f"-{lines}"])
    if p.returncode != 0:
        return ""
    return p.stdout


def attach_session(session: str) -> bool:
    """TTY 下 attach 到 session（阻塞至 detach；stdout 非 TTY 的调用方不得调用）。

    不经 _run 的 capture——attach 是交互客户端，捕获输出会与 TUI 冲突。
    """
    return subprocess.run([_BYOBU_BIN, "attach-session", "-t", session]).returncode == 0


def spawn_window(spec: SpawnSpec) -> Tuple[bool, str, bool]:
    """在作用域 session 内为 wiki 开 agent 窗口（或复用带标同名窗口）。

    Args:
        spec: 开窗参数簇（session / window_name / wiki / cwd / cmd_argv / env /
            backend / ensure，见 SpawnSpec）：
            backend: agent CLI 名（claude/qodercli/opencode），随 R3 打标供 status 使用。
            ensure: True → session 不存在时一步建成（session + 首窗口，防裸 shell 窗口）；
                False → 假定 session 已存在（tmux 内的当前 session）。
            cmd_argv: agent 命令 argv（首元素为二进制名，spawn 前解析为绝对路径）。

    Returns:
        (created, window_id, collected)：created True=新建（已按 R3 打标）/
        False=复用（已 select-window）；collected=True 表示新建前收掉了同名 dead
        残留窗口（R2 收尸，供调用方打印透明文案）。

    线性降级（≤3 步，不循环，不上锁）：

    1. ensure 且无 session → new-session 一步带首窗口 + 打标；失败（并发竞争
       duplicate session）→ 落入窗口级路径
    2. 复用判定（R2）命中：非 dead 且 backend 匹配 → select-window；已 dead →
       kill-window 收尸后按无窗口处理；非 dead 但 backend 不符 →
       WindowBackendMismatch 拒绝（不自动开同名第二窗口）；窗口刚好死掉
       （select 失败）→ 降级 new-window
    3. 无命中 → new-window；session 刚好被 kill（失败）→ 重试一次一步建 new-session

    再失败抛 ByobuCommandFailed（命令行无 secret）。
    """
    session = spec.session
    window_name = spec.window_name
    wiki = spec.wiki
    cwd = spec.cwd
    backend = spec.backend
    resolved = shutil.which(spec.cmd_argv[0]) or spec.cmd_argv[0]
    # env 走命令前缀注入（设计 §2.2 步 8 / docstring「env 注入走命令前缀」）：
    # `K=V cmd` 赋值前缀是 sh -c 原生语义，全版本兼容；值过 shlex.quote。
    # 只允许非敏感变量（调用方只传 LLM_WIKI_ROOT 路径）。
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
            # R2 收尸：dead pane 无活进程，不属 R6 高危动作，无需确认；
            # 收尸后新开，保持 "1 个 <wiki>-<suffix> 至多 1 个窗口" 不变量
            kill_window(wid)
            collected = True
        elif backend_ok:
            if select_window(wid):
                return False, wid, False
            # select 失败（窗口刚好死掉）→ 降级 new-window
        else:
            # R2 拒绝：带标活窗但 backend 不符（或老窗口无 @llmw_backend 标）——
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
