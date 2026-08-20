"""全局配置 + workspace 路径解析 + 包内资源定位"""

import os
from pathlib import Path

from llmw.errors import WorkspaceNotFound

DEFAULT_WORKSPACE = Path.home() / "yzr-llm-workspace"

CONTENT_DIR = Path(__file__).resolve().parent / "content"


def resolve_workspace_root(
    explicit: str = None,
) -> Path:
    """解析 workspace 根路径

    优先级:
      1. explicit (--workspace flag)
      2. $LLMW_WORKSPACE env var
      3. ~/yzr-llm-wiki-workspace (默认)

    解析后校验: 必须存在、是目录、含 workspace.toml。
    不存在 → WorkspaceNotFound
    """
    if explicit:
        root = Path(explicit).resolve()
    elif os.environ.get("LLMW_WORKSPACE"):
        root = Path(os.environ["LLMW_WORKSPACE"]).resolve()
    else:
        root = DEFAULT_WORKSPACE.resolve()

    if not root.is_dir():
        raise WorkspaceNotFound(
            hint=f"路径不存在: {root}。可指定 --workspace 或 $LLMW_WORKSPACE",
        )
    if not (root / "workspace.toml").is_file():
        raise WorkspaceNotFound(
            hint=f"目录 {root} 不是 llmw workspace（缺少 workspace.toml）。"
            f"可运行 `llmw init --path={root}`",
        )
    return root


def wiki_templates_dir() -> Path:
    """包内 llmw/content/templates/wiki/ 路径 (AGENTS.md SSOT 模板 / CLAUDE.md 薄壳模板 / fixtures 字节金标准)"""
    return CONTENT_DIR / "templates" / "wiki"


def workspace_templates_dir() -> Path:
    """包内 llmw/content/templates/workspace/ 路径 (workspace AGENTS.md / CLAUDE.md 模板 / fixtures 字节金标准)"""
    return CONTENT_DIR / "templates" / "workspace"


def metadata_templates_dir() -> Path:
    """包内 llmw/content/templates/metadata/ 路径 (wiki_metadata.toml 渲染模板)"""
    return CONTENT_DIR / "templates" / "metadata"
