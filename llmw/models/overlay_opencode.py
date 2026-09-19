"""wiki 骨架 @import 引用 → <wiki>/opencode.json 整文件（opencode 指令文件交付）

opencode 不解析 AGENTS.md 中的 ``@path`` 引用（官方文档明确：
"While opencode doesn't automatically parse file references in AGENTS.md"），
推荐用 ``opencode.json`` 的 ``instructions`` 字段（config.mdx "Instructions" 小节 +
rules.mdx "Custom Instructions"）显式声明额外指令文件列表——与 AGENTS.md **叠加**加载。

**整文件 CLI 拥有（byte-owned 配置）**——与 ``AGENTS.md`` 的 byte-owned 模板同模型。
CLI 拥有 ``opencode.json`` 的全部内容；用户自定义 opencode 配置（permission / mcp /
custom provider 等）应放在全局 ``~/.config/opencode/opencode.json``，opencode 官方
config 合并机制保证项目级 > 全局，非冲突 key 合并。

**gitignore 保留 ``**/opencode.json`` 行**——与 ``**/.claude/settings*.json`` 同模型：
机器本地生成配置，每次 ``llmw wiki enter`` 幂等渲染重建，不入 git。fresh clone 后
只要走过一次 ``llmw wiki enter`` 即生成（裸跑 opencode 绕开 llmw 属反工作流，缝隙可忽略）。

**遗留 secret 自动剥除**：旧版 overlay_opencode 曾写含明文 apiKey 的 ``provider.llmw``
块与顶层 ``model: "llmw/..."`` 键（CLI owned）。本次语义改为整文件覆盖，下次 enter
这些遗留键即消失（CLI 清理自有内容，非 clobber 用户配置——其他 provider id 不存在于
CLI 旧写入，故"用户自定义 provider"与"CLI 遗留"可由键名/前缀识别）。磁盘 secret 由此
渐进消失。

**P1 防御过滤**：``effective_instructions(wiki_dir)`` 把 ``INSTRUCTION_FILES`` 与
wiki 内实际存在的文件取交集——缺文件（破坏的 wiki）自动剔除，文件恢复后下次 enter
自动补回。``INSTRUCTION_FILES`` 仍是 SSOT，过滤是防御性兜底（opencode 对缺失
instruction 文件的容忍行为未验证）。

**额外 key 警告（不静默）**：现有文件含 ``{$schema, instructions}`` 之外的 key 时，
apply 会 stderr 逐名点名"将被覆盖"——本工具卖点即可见性，自己不该静默吞用户内容。
覆盖仍然执行（CLI 整文件拥有），只是不静默。

**JSON 损坏绝不 clobber**：现有文件非法 JSON → ``OverlayFileUnparseable``，调用方
阻断 enter，由用户手动修复。

**与 wiki 模板同步**：``INSTRUCTION_FILES`` 与 ``agents-md-template.md`` 的顶层
``@path`` 行必须一一匹配——由 ``wiki_fixtures.py`` 的
``opencode-instructions-sync`` 规则保证。
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from llmw.errors import OverlayFileUnparseable
from llmw.fsutil import atomic_write, load_json_optional

# 必须同步加载的指令文件列表——与 agents-md-template.md 的顶层 @import 一一对应。
# 架构含义：opencode 无 @import 展开，此常量（经 effective_instructions 过滤后）
# 是 opencode 路径的等价物。
# wiki_fixtures.py:opencode-instructions-sync 保证本常量与模板 @import 同步。
INSTRUCTION_FILES: Tuple[str, ...] = (
    "MEMORY/MEMORY.md",
    "scripts/SCRIPTS.md",
)

_SCHEMA_URL = "https://opencode.ai/config.json"

# CLI 整文件拥有的顶层 key 集合；apply 时若现有文件含此集合之外的 key，会逐名警告。
_OWNED_KEYS = frozenset({"$schema", "instructions"})


def effective_instructions(wiki_dir: Path) -> List[str]:
    """INSTRUCTION_FILES 与 wiki 内实际存在文件的交集（P1 防御过滤）。

    缺文件（破坏的 wiki）自动剔除；文件恢复后下次 enter 自动补回。
    """
    return [f for f in INSTRUCTION_FILES if (wiki_dir / f).is_file()]


def _load_existing(path: Path) -> Optional[dict]:
    """读现有 opencode.json。不存在 → None；JSON 非法 → OverlayFileUnparseable。

    绝不 clobber 损坏文件：解析失败直接抛，调用方阻断，由用户手动修复。
    IO 骨架共享 fsutil.load_json_optional（文件级语义），业务异常在此包装。
    """
    try:
        return load_json_optional(path)
    except ValueError as e:
        raise OverlayFileUnparseable(
            f"{path} 不是合法 JSON: {e}",
            hint="手动修复或删除该文件后重试；CLI 不会覆盖损坏文件",
        )


def render(wiki_dir: Path) -> dict:
    """渲染整文件：``{"$schema": ..., "instructions": [...]}``。

    instructions 经 effective_instructions 过滤（P1）。无 ModelEntry 参数——
    与模型无关，纯骨架常量。
    """
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
    """dry-run 用：返回 (path, would_write)。不写盘。

    would_write=True 当且仅当文件不存在或与 render 期望不一致（含遗留 key 待剥除）。
    损坏文件（JSON 非法）→ OverlayFileUnparseable（与 apply 一致，绝不 clobber）。
    """
    path = wiki_dir / "opencode.json"
    data = _load_existing(path)
    if data is None:
        return path, True
    return path, data != render(wiki_dir)


def apply(wiki_dir: Path) -> Path:
    """real enter 用：幂等整文件覆盖写。返回写入 path。

    - 现有文件 == render 期望 → 不写、不动 mtime（幂等短路）
    - 现有文件含 ``{$schema, instructions}`` 之外的 key → stderr 逐名警告将被覆盖
      （CLI 整文件拥有；遗留 ``provider.llmw`` 明文 apiKey / 悬空 ``model`` 键
      由此自动剥除，磁盘 secret 渐进消失）
    - 新建文件即 ``{"$schema": ..., "instructions": [...]}``
    - JSON 非法 → OverlayFileUnparseable，绝不 clobber
    - 无 secret，不 chmod 600
    - 整文件不入 git（gitignore 保留；机器本地生成，每次 enter 重建）
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
