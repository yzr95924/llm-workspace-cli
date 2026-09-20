"""全局配置 + workspace 路径解析 + 包内资源定位"""

import os
from pathlib import Path

from llmw.errors import WorkspaceNotFound

DEFAULT_WORKSPACE = Path.home() / "yzr-llm-wiki-workspace"

CONTENT_DIR = Path(__file__).resolve().parent / "content"


def resolve_workspace_root(
    explicit: str = None,
) -> Path:
    """解析 workspace 根：explicit > $LLMW_WORKSPACE > 默认路径。

    校验存在 / 是目录 / 含 workspace.toml，失败 WorkspaceNotFound。
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
    return CONTENT_DIR / "templates" / "wiki"


def workspace_templates_dir() -> Path:
    return CONTENT_DIR / "templates" / "workspace"


def metadata_templates_dir() -> Path:
    return CONTENT_DIR / "templates" / "metadata"
