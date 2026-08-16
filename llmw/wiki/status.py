"""llmw status — 一屏回答"哪些 wiki 的 agent 在跑、跑了多久、是否已退出"

设计 (doc/session-visibility-design.md §2.4 R5 / R7)：tmux 窗口表即注册表——实时枚举
（逐 session：``list-sessions`` + 每 session ``list-windows -t``，兼容 tmux ≥2.7），
过滤 ``@llmw_wiki`` 非空行，无轮询、无账本、无 hook。
agent 进程退出 → pane 销毁 → 窗口消亡 → 标记随之消亡，拉取精确对"看一眼哪些在跑"
是满分答案；remain-on-exit=on 时窗口残留为 dead pane，status 显式 ``✗ exited``
（尸体可见才会被 stop 收掉，隐藏会让用户积累不可见僵尸；dead 行停表数据源
``pane_dead_time``，缺失时回退 ``window_activity``——见 ``_row_to_dict``）。

本模块主路径只做"看"（枚举 + 展示），窗口开关归 enter / stop。唯一例外是 R8
孤儿清理模式（设计 §2.4 R8）：workspace 缺失时 status 经显式确认收尸体/残留窗口——
stop 此时被 cli 入口的 workspace 解析阻断，孤儿清理是该场景唯一的 llmw 内收尸通道。
被 llmw/cli.py 接线。
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from llmw.backends import match_waiting, match_working
from llmw.errors import ByobuNotFound, LlmwError
from llmw.wiki import byobu

# R8 孤儿模式的清理指引（非 TTY / --json / --tmux 只指不动手）
_ORPHAN_CLEAN_HINT = (
    "[llmw] hint: TTY 下运行 `llmw status` 可交互清理以上残留窗口，"
    "或手动 `byobu-tmux kill-window -t @N`"
)

# ===== STATE 判定（R5，2026-08-15 新增；2026-08-15 重构） =====
# 内部值是 ASCII 稳定值（--json 输出此值，脚本可判等）：dead / shell / working /
# waiting / unknown。显示值（✗ / ⚠ shell / ⚙ working / ⏳ waiting / ?）只存在于
# 表格层——显示值与机器契约分离（巡检 #3）。
# 判定短路优先级：dead → 假活 shell → capture-pane 尾部按 backend 模式匹配 → unknown。
# 模式注册表在 llmw/backends.py（单一真源）；模式随 CLI 版本漂移 → 优雅降级 unknown。
_STATE_DISPLAY = {
    "dead": "✗",
    "shell": "⚠ shell",
    "working": "⚙ working",
    "waiting": "⏳ waiting",
    "unknown": "?",
}

# 假活判定集合（唯一消费方是本模块 STATE 判定——故归此处，不占 byobu 的 tmux IO 边界）：
# 带标窗口但前台进程是 shell = agent 已退出/崩溃但窗口残留（R5 STATE ②）
_SHELL_CMDS = frozenset({"fish", "bash", "zsh", "sh", "dash", "ash"})

# 表格排序：actionable first（waiting/假活最前 → working/unknown → dead 最后）
_STATE_ORDER = {"shell": 0, "waiting": 0, "working": 1, "unknown": 1, "dead": 2}


def _classify_state(d: Dict) -> str:
    """STATE 判定（R5 优先级短路）：只对非 dead 非 shell 的窗口做 capture。"""
    if d["dead"]:
        return "dead"
    pcmd = (d.get("pcmd") or "").lower()
    if pcmd in _SHELL_CMDS:
        return "shell"
    tail = byobu.capture_pane_tail(d["window_id"])
    if match_working(tail, d.get("backend")):
        return "working"
    if match_waiting(tail, d.get("backend")):
        return "waiting"
    return "unknown"


def _fmt_dur(seconds: float) -> str:
    """R5 时间格式：<60s → 'now'；<60min → 'Nm'；<24h → 'Nh'；否则 'Nd'。"""
    if seconds < 60:
        return "now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours}h"
    return f"{int(hours // 24)}d"


def _fmt_dur_ago(seconds: float) -> str:
    """dead 行 IDLE 用：``✗ exited <Nd> ago``。"""
    return f"✗ exited {_fmt_dur(seconds)} ago"


def _to_int(s: str) -> Optional[int]:
    """空串 / 非数字 → None（未打标或手改窗口）。"""
    try:
        return int(s) if s else None
    except ValueError:
        return None


def _pcmd_basename(s: str) -> str:
    """pane_current_command 可能是完整路径（如 /usr/bin/opencode）→ 取 basename。"""
    s = s.strip()
    return os.path.basename(s) if s else ""


def _row_to_dict(row: byobu.WindowRow, now: float) -> Optional[Dict]:
    """原始枚举行 → 展示 dict；@llmw_wiki 为空的行（非 llmw 窗口）→ None。

    纯函数（不做 tmux IO）；STATE 判定在 _enumerate 中填充（需 capture）。
    """
    wiki = row.wiki
    if not wiki:
        return None
    dead = row.dead == "1"
    started = _to_int(row.started)
    dead_time = _to_int(row.dead_time)
    activity = _to_int(row.activity)

    pcmd = _pcmd_basename(row.pcmd)
    out = {
        "wiki": wiki,
        "window": row.window_name,
        "window_id": row.window_id,
        "session": row.session,
        "dead": dead,
        "started_at": started,
        "activity_at": activity,
        "dead_at": dead_time,
        "backend": row.backend.strip() or pcmd,
        "pcmd": pcmd,
    }
    if dead:
        # 停表数据源：pane_dead_time；缺失（tmux <2.9 疑无此格式变量）时回退
        # window_activity——agent 死后无输出 → activity 冻结 ≈ 死亡时刻（设计 §2.4 R5）
        died_at = dead_time if dead_time is not None else activity
        if died_at is not None:
            out["dead_at"] = died_at  # 回退时为近似值（无 pane_dead_time 的版本）
            out["dead_seconds_ago"] = max(0, now - died_at)
            if started is not None:
                out["uptime_seconds"] = max(0, died_at - started)  # UPTIME 停表于死时
    else:
        if started is not None:
            out["uptime_seconds"] = max(0, now - started)
        if activity is not None:
            out["idle_seconds"] = max(0, now - activity)
    return out


def _render_table(rows: List[Dict]) -> None:
    """R5 文本表：WIKI / WINDOW / SESSION / BACKEND / STATE / UPTIME / IDLE。

    入参已按 state 优先级排好（actionable first，见 _enumerate）。
    """
    if not rows:
        print("# (no running sessions)", file=sys.stdout)
        return
    cells = []
    for r in rows:
        uptime = _fmt_dur(r["uptime_seconds"]) if "uptime_seconds" in r else "-"
        if r["dead"]:
            idle = (
                _fmt_dur_ago(r["dead_seconds_ago"])
                if "dead_seconds_ago" in r
                else "✗ exited"
            )
        else:
            idle = _fmt_dur(r["idle_seconds"]) if "idle_seconds" in r else "-"
        cells.append(
            {
                "wiki": r["wiki"],
                "window": r["window"],
                "session": r["session"],
                "backend": r.get("backend") or "-",
                "state": _STATE_DISPLAY.get(r.get("state"), "?"),
                "uptime": uptime,
                "idle": idle,
            }
        )
    header = {
        "wiki": "WIKI",
        "window": "WINDOW",
        "session": "SESSION",
        "backend": "BACKEND",
        "state": "STATE",
        "uptime": "UPTIME",
        "idle": "IDLE",
    }
    width = {k: max(len(c[k]) for c in cells + [header]) for k in header}
    print(
        f"{header['wiki'].ljust(width['wiki'])}  "
        f"{header['window'].ljust(width['window'])}  "
        f"{header['session'].ljust(width['session'])}  "
        f"{header['backend'].ljust(width['backend'])}  "
        f"{header['state'].ljust(width['state'])}  "
        f"{header['uptime'].ljust(width['uptime'])}  "
        f"{header['idle'].ljust(width['idle'])}"
    )
    for c in cells:
        print(
            f"{c['wiki'].ljust(width['wiki'])}  {c['window'].ljust(width['window'])}  "
            f"{c['session'].ljust(width['session'])}  "
            f"{c['backend'].ljust(width['backend'])}  "
            f"{c['state'].ljust(width['state'])}  "
            f"{c['uptime'].ljust(width['uptime'])}  {c['idle'].ljust(width['idle'])}"
        )


def _enumerate(now: float) -> List[Dict]:
    """实时枚举全部 llmw 带标窗口 → 展示 dict 列表。

    按 wiki → 窗口名稳定排序（--json 用此序）；state 判定在排序后逐个填充
    （capture-pane 短路：dead / 假活 shell 不捕获）。表格用另行按 state 排序的副本。
    """
    rows = [r for r in (byobu.list_windows() or []) if r.wiki]
    rows.sort(key=lambda r: (r.wiki, r.window_name))
    dicts = [d for d in (_row_to_dict(r, now) for r in rows) if d is not None]
    for d in dicts:
        d["state"] = _classify_state(d)
    return dicts


def _state_sorted(dicts: List[Dict]) -> List[Dict]:
    """表格排序：actionable first（waiting/⚠ shell 最前 → working/unknown → dead 最后）。"""
    return sorted(
        dicts,
        key=lambda d: (_STATE_ORDER.get(d.get("state"), 1), d["wiki"], d["window"]),
    )


def _render_tmux_line(dicts: List[Dict]) -> None:
    """``●N``（仅计运行中窗口）；存在 dead 窗口时后缀 `` ✗M``。"""
    running = sum(1 for d in dicts if not d["dead"])
    dead = sum(1 for d in dicts if d["dead"])
    line = f"●{running}"
    if dead:
        line += f" ✗{dead}"
    print(line, file=sys.stdout)


def status(
    as_json: bool = False,
    tmux_line: bool = False,
) -> int:
    """R5 status：实时枚举全部 llmw 带标窗口并展示。返回 0。

    --json: 结构化列表（含原始时间戳秒数）；--tmux: 单行 ``●N [✗M]``
    （仅计运行中窗口；供 byobu 状态条集成）。
    """
    if not byobu.byobu_available():
        raise ByobuNotFound(
            "byobu-tmux 不在 PATH",
            hint="安装 byobu（如 apt install byobu / brew install byobu）",
        )
    dicts = _enumerate(time.time())

    if tmux_line:
        _render_tmux_line(dicts)
        return 0

    if as_json:
        print(json.dumps(dicts, ensure_ascii=False, indent=2))
        return 0

    _render_table(_state_sorted(dicts))
    return 0


def status_orphan(
    ws_path: Path,
    err: LlmwError,
    as_json: bool = False,
    tmux_line: bool = False,
) -> int:
    """R8 孤儿清理模式（设计 §2.4 R8）：workspace 缺失时的 status 降级路径。

    仅 cli.py 在**隐式默认路径**解析失败时调用（显式 --workspace / $LLMW_WORKSPACE
    失败保持硬报错——typo 路径 + 习惯性回 y = 误杀活窗口，护栏见 R8）。

    - byobu 不可用 / 无带标窗口 → 抛回原 WorkspaceNotFound（新机器 / 路径写错，
      没有什么可清）
    - 有带标窗口 → stderr warning + 照常渲染（表 / JSON / tmux 行）；仅纯文本表 +
      TTY 时追加交互确认（先列表、区分运行中/已退出，与 R6 同级显式），确认后逐窗
      kill-window。非 TTY / --json / --tmux 只打 hint 不交互（脚本场景零副作用）。
    """
    if not byobu.byobu_available():
        raise err
    dicts = _enumerate(time.time())
    if not dicts:
        raise err

    running = sum(1 for d in dicts if not d["dead"])
    dead = len(dicts) - running
    print(
        f"[llmw] warning: workspace 未找到: {ws_path}；"
        f"tmux 中发现 {len(dicts)} 个残留 session（{running} 运行中 / {dead} 已退出）",
        file=sys.stderr,
    )

    if tmux_line:
        _render_tmux_line(dicts)
        print(_ORPHAN_CLEAN_HINT, file=sys.stderr)
        return 0
    if as_json:
        print(json.dumps(dicts, ensure_ascii=False, indent=2))
        print(_ORPHAN_CLEAN_HINT, file=sys.stderr)
        return 0

    _render_table(_state_sorted(dicts))
    if not sys.stdin.isatty():
        print(_ORPHAN_CLEAN_HINT, file=sys.stderr)
        return 0

    try:
        ans = (
            input(
                f"将清理全部 {len(dicts)} 个窗口"
                f"（{running} 个运行中 agent 将被终止 / {dead} 个已退出残留），"
                "确认？[y/N]: "
            )
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        print()
        ans = "n"
    if ans not in ("y", "yes"):
        print("[llmw] 取消")
        return 0

    killed = 0
    for d in dicts:
        if byobu.kill_window(d["window_id"]):
            killed += 1
        else:
            print(
                f"[llmw] warning: kill-window 失败 ({d['window_id']} {d['window']})",
                file=sys.stderr,
            )
    print(f"[llmw] ✓ 已清理 {killed}/{len(dicts)} 个残留窗口", file=sys.stdout)
    return 0
