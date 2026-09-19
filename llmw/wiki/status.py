"""llmw status — 一屏回答"哪些 wiki 的 agent 在跑、跑了多久、是否已退出"。

tmux 窗口表即注册表（实时枚举带标窗口，无轮询无账本）。主路径只读；唯一例外是
workspace 缺失时的孤儿清理（显式确认后收残留窗口——该场景 stop 已被 cli 的
workspace 解析阻断）。被 llmw/cli.py 接线。
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

# 孤儿清理模式的指引（非 TTY / --json / --tmux 只指不动手）
_ORPHAN_CLEAN_HINT = (
    "[llmw] hint: TTY 下运行 `llmw status` 可交互清理以上残留窗口，"
    "或手动 `byobu-tmux kill-window -t @N`"
)

# ===== STATE 判定 =====
# 内部值 ASCII 稳定（--json 契约）；显示值只入表格层。判定短路：dead → 假活 shell
# → capture-pane 模式匹配（注册表见 backends.py）→ unknown。
_STATE_DISPLAY = {
    "dead": "✗",
    "shell": "⚠ shell",
    "working": "⚙ working",
    "waiting": "⏳ waiting",
    "unknown": "?",
}

# 假活：带标窗口但前台进程是 shell = agent 已退出/崩溃但窗口残留
_SHELL_CMDS = frozenset({"fish", "bash", "zsh", "sh", "dash", "ash"})

_STATE_ORDER = {"shell": 0, "waiting": 0, "working": 1, "unknown": 1, "dead": 2}


def _classify_state(d: Dict) -> str:
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
    return f"✗ exited {_fmt_dur(seconds)} ago"


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s) if s else None
    except ValueError:
        return None


def _pcmd_basename(s: str) -> str:
    s = s.strip()
    return os.path.basename(s) if s else ""


def _row_to_dict(row: byobu.WindowRow, now: float) -> Optional[Dict]:
    """行 → 展示 dict；@llmw_wiki 为空（非 llmw 窗口）→ None。"""
    wiki = row.wiki
    if not wiki:
        return None
    dead = row.dead == byobu.DEAD_FLAG
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
        # 停表源 pane_dead_time；老 tmux 缺失 → 回退 activity（死后无输出即冻结 ≈ 死亡时刻）
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
    """枚举带标窗口 → 展示 dict 列表（wiki/窗口名稳定序；state 逐个填充）。"""
    rows = [r for r in byobu.list_windows() if r.wiki]
    rows.sort(key=lambda r: (r.wiki, r.window_name))
    dicts = [d for d in (_row_to_dict(r, now) for r in rows) if d is not None]
    for d in dicts:
        d["state"] = _classify_state(d)
    return dicts


def _state_sorted(dicts: List[Dict]) -> List[Dict]:
    return sorted(
        dicts,
        key=lambda d: (_STATE_ORDER.get(d.get("state"), 1), d["wiki"], d["window"]),
    )


def _render_tmux_line(dicts: List[Dict]) -> None:
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
    """孤儿清理：workspace 缺失时的 status 降级路径（仅 cli.py 隐式默认路径解析
    失败时调用；显式路径失败保持硬报错）。非 TTY / --json / --tmux 只打 hint；
    TTY 纯文本表下确认后逐窗 kill。
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
