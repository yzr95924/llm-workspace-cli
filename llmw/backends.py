"""backend 单一真源：agent CLI 名集合 + status STATE 模式注册表（新增 agent 只改本文件）。

STATE_PATTERNS：backend → 屏幕尾部文本判据（opencode 实测；claude / qodercli 暂无，
降级 unknown）。模式随 CLI 版本漂移，匹配不上即降级。
"""

from typing import Dict, NamedTuple, Optional, Tuple


class StatePatterns(NamedTuple):
    """一个 backend 的 STATE 判据：working 标志 / waiting 标志 / spinner 字符集。"""

    working: Tuple[str, ...] = ()
    waiting: Tuple[str, ...] = ()
    spinner: str = ""


KNOWN_BACKENDS = frozenset({"claude", "qodercli", "opencode"})

# 默认 backend 唯一真源（落盘判定 / config 文案 / enter 回退均引此）
DEFAULT_BACKEND = "opencode"

_OPENCODE_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

STATE_PATTERNS: Dict[str, StatePatterns] = {
    "opencode": StatePatterns(
        working=("esc interrupt",),
        waiting=("ctrl+p",),
        spinner=_OPENCODE_SPINNER,
    ),
}


def match_working(tail: str, backend: Optional[str]) -> bool:
    """tail 是否命中 backend 的 working 判据；未注册 backend → False（降级 unknown）。"""
    pats = STATE_PATTERNS.get(backend)
    if pats is None:
        return False
    if any(m in tail for m in pats.working):
        return True
    return bool(pats.spinner) and any(c in tail for c in pats.spinner)


def match_waiting(tail: str, backend: Optional[str]) -> bool:
    """tail 是否命中 waiting 判据（互斥项，调用方先查 working）。"""
    pats = STATE_PATTERNS.get(backend)
    if pats is None:
        return False
    return any(m in tail for m in pats.waiting) and not match_working(tail, backend)
