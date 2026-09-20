"""resolved ModelEntry + habit template → <wiki>/.claude/settings.local.json（claude 路径 overlay）。

只接收已解析的 ModelEntry；走 Claude Code Local 层（优先级 > User 配置，取代早期
subprocess env 注入）。ANTHROPIC_MODEL 由本模块按 context_window 加 `[1m]` 视图——
客户端约定不进 registry 数据（opencode / qodercli 路径不读本模块）。
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from llmw.errors import OverlayFileUnparseable
from llmw.fsutil import atomic_write, chmod_600, load_json_optional
from llmw.models.store import ModelEntry

# 习惯级 env key（非用户可配；增删改一律改本常量，见 MEMORY/overlay-habit-template.md）
_HABIT_TEMPLATE: Dict[str, str] = {
    # 隐私: 关闭非必要流量（无遥测）
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    # 关闭 attribution header（值 0 = 不标记）
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
}

# Claude Code 1M context 启用约定 = 模型名带 `[1m]` 后缀；按 context_window 自动加
_CLAUDE_1M_CONTEXT_THRESHOLD = 1_000_000
_CLAUDE_1M_SUFFIX = "[1m]"


def _claude_anthropic_model(name: str, context_window: int) -> str:
    """裸 wire 名 + context_window → ANTHROPIC_MODEL（>=1M 且未带后缀则自动加 `[1m]`）。"""
    if context_window >= _CLAUDE_1M_CONTEXT_THRESHOLD and not name.endswith(
        _CLAUDE_1M_SUFFIX
    ):
        return name + _CLAUDE_1M_SUFFIX
    return name


def _model_env(model: ModelEntry) -> dict:
    """ModelEntry → env 块（CLI-controllable，来源 registry）。"""
    return {
        "ANTHROPIC_MODEL": _claude_anthropic_model(model.name, model.context_window),
        "ANTHROPIC_BASE_URL": model.base_url,
        "ANTHROPIC_AUTH_TOKEN": model.api_key,
    }


def render(model: ModelEntry) -> dict:
    """ModelEntry + habit template → overlay env 块（habit 值为常量，下次 enter 会 reset）。"""
    return {**_model_env(model), **_HABIT_TEMPLATE}


def _load_existing(path: Path) -> Optional[dict]:
    """不存在 → None；JSON 非法 → OverlayFileUnparseable（绝不 clobber 损坏文件）。"""
    try:
        return load_json_optional(path)
    except ValueError as e:
        raise OverlayFileUnparseable(
            f"{path} 不是合法 JSON: {e}",
            hint="手动修复或删除该文件后重试；CLI 不会覆盖损坏文件",
        )


def _is_up_to_date(data: Optional[dict], expected: dict) -> bool:
    """所有 owned key（ANTHROPIC_* + habit template）是否已全部 == expected。"""
    if not data:
        return False
    env = data.get("env") or {}
    return all(env.get(k) == v for k, v in expected.items())


def inspect(wiki_dir: Path, model: ModelEntry) -> Tuple[Path, bool]:
    """dry-run：返回 (path, would_write)，不写盘（损坏文件同样抛，与 apply 一致）。"""
    path = wiki_dir / ".claude" / "settings.local.json"
    expected = render(model)
    data = _load_existing(path)
    return path, not _is_up_to_date(data, expected)


def apply(wiki_dir: Path, model: ModelEntry) -> Path:
    """幂等合并写 + chmod 600：只覆盖 owned key，保留其余顶层 key；已一致则短路不写。"""
    path = wiki_dir / ".claude" / "settings.local.json"
    expected = render(model)

    data = _load_existing(path) or {}
    if _is_up_to_date(data, expected):
        return path  # 幂等短路

    env = dict(data.get("env") or {})
    env.update(expected)
    data["env"] = env

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    # 安全：overlay 含明文 api_key，强制 600（NFS best-effort）
    chmod_600(path)
    return path
