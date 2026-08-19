"""backend 单一真源：agent CLI 名集合 + status STATE 模式注册表。

项目内所有"backend 知识"收敛于此：
enter_cli 白名单（enter.py / workspace.manager._check_enter_cli）、spawn 打标
（byobu.tag_window）、status 的 BACKEND 列与 STATE 模式路由（status.py）——
新增 agent 只改本文件一处。

STATE_PATTERNS：backend → 屏幕尾部文本的判据。模式随 CLI 版本漂移 → 匹配不上
优雅降级 unknown，status 表不坏（设计 §2.4 R5）。claude / qodercli 暂缺
（扩展点，占位未配置）；opencode 模式基于 1.18.18 屏幕实测：
工作态——底部状态行含 "esc interrupt" + braille spinner 段；空闲态——底部输入
行含 "ctrl+p commands" 且无工作标志。
"""

from typing import Dict, NamedTuple, Optional, Tuple


class StatePatterns(NamedTuple):
    """一个 backend 的 STATE 判据：working 标志 / waiting 标志 / spinner 字符集。"""

    working: Tuple[str, ...] = ()
    waiting: Tuple[str, ...] = ()
    spinner: str = ""


KNOWN_BACKENDS = frozenset({"claude", "qodercli", "opencode"})

# 默认 backend（workspace_local.toml#enter_cli 未设时的缺省）：唯一真源——
# local_store 落盘判定 / config dump 文案 / enter 回退 全部引此，不散落 "claude" 字面量。
DEFAULT_BACKEND = "claude"

_OPENCODE_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

STATE_PATTERNS: Dict[str, StatePatterns] = {
    "opencode": StatePatterns(
        working=("esc interrupt",),
        waiting=("ctrl+p commands",),
        spinner=_OPENCODE_SPINNER,
    ),
}


def match_working(tail: str, backend: Optional[str]) -> bool:
    """tail（capture-pane 尾部文本）是否命中 backend 的 working 判据。

    未注册 backend → False（对应方降级 unknown）。
    """
    pats = STATE_PATTERNS.get(backend)
    if pats is None:
        return False
    if any(m in tail for m in pats.working):
        return True
    return bool(pats.spinner) and any(c in tail for c in pats.spinner)


def match_waiting(tail: str, backend: Optional[str]) -> bool:
    """tail 是否命中 backend 的 waiting 判据（与 working 互斥，调用方保证先查 working）。"""
    pats = STATE_PATTERNS.get(backend)
    if pats is None:
        return False
    return any(m in tail for m in pats.waiting) and not match_working(tail, backend)
