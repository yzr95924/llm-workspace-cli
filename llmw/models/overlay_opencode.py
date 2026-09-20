"""wiki 骨架 @import 引用 → <wiki>/opencode.json 整文件（opencode 不解析 @path，
用 instructions 字段替代，与 AGENTS.md 叠加加载）。

整文件 CLI 拥有（byte-owned）；用户自定义配置放全局 ~/.config/opencode/opencode.json。
机器本地生成、不入 git；旧版遗留的 provider.llmw 明文 apiKey 由整文件覆盖自动剥除。
非 CLI 管理 key 覆盖前逐名警告；JSON 损坏则阻断不 clobber。
INSTRUCTION_FILES 与模板顶层 @import 的同步由 opencode-instructions-sync 强制。
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from llmw.errors import OverlayFileUnparseable
from llmw.fsutil import atomic_write, load_json_optional

# opencode 路径的 @import 等价物；与模板顶层 @import 一一对应（gate 强制）
INSTRUCTION_FILES: Tuple[str, ...] = (
    "MEMORY/MEMORY.md",
    "scripts/SCRIPTS.md",
)

_SCHEMA_URL = "https://opencode.ai/config.json"

# CLI 拥有的顶层 key；之外的 key 覆盖前逐名警告
_OWNED_KEYS = frozenset({"$schema", "instructions"})


def effective_instructions(wiki_dir: Path) -> List[str]:
    """INSTRUCTION_FILES ∩ wiki 内实际存在的文件（缺文件自动剔除，恢复后自动补回）。"""
    return [f for f in INSTRUCTION_FILES if (wiki_dir / f).is_file()]


def _load_existing(path: Path) -> Optional[dict]:
    """不存在 → None；JSON 非法 → OverlayFileUnparseable（绝不 clobber 损坏文件）。"""
    try:
        return load_json_optional(path)
    except ValueError as e:
        raise OverlayFileUnparseable(
            f"{path} 不是合法 JSON: {e}",
            hint="手动修复或删除该文件后重试；CLI 不会覆盖损坏文件",
        )


def render(wiki_dir: Path) -> dict:
    """整文件渲染（instructions 经 effective 过滤）；与模型无关。"""
    return {
        "$schema": _SCHEMA_URL,
        "instructions": effective_instructions(wiki_dir),
    }


def _extra_keys(data: Optional[dict]) -> List[str]:
    """现有文件中 CLI 不拥有的顶层 key 列表（被 apply 覆盖前会被 warning）。"""
    if not data:
        return []
    return sorted(k for k in data if k not in _OWNED_KEYS)


def inspect(wiki_dir: Path) -> Tuple[Path, bool]:
    """dry-run：(path, would_write)，不写盘（含遗留 key 待剥除时也算要写）。"""
    path = wiki_dir / "opencode.json"
    data = _load_existing(path)
    if data is None:
        return path, True
    return path, data != render(wiki_dir)


def apply(wiki_dir: Path) -> Path:
    """幂等整文件覆盖写：一致则短路；非 CLI key 逐名警告后覆盖（遗留 secret 由此剥除）。

    JSON 损坏抛 OverlayFileUnparseable（不 clobber）；无 secret 不 chmod、不入 git。
    """
    path = wiki_dir / "opencode.json"
    data = _load_existing(path)
    expected = render(wiki_dir)

    if data is not None and data == expected:
        return path  # 幂等短路

    extras = _extra_keys(data)
    if extras:
        print(
            f"[llmw] warning: {path} 含非 CLI 管理 key，将被覆盖: {', '.join(extras)}"
            "（opencode 自定义配置应放全局 ~/.config/opencode/opencode.json）",
            file=sys.stderr,
        )

    atomic_write(path, json.dumps(expected, ensure_ascii=False, indent=2))
    return path
