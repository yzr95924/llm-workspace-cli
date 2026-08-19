"""全局配置 + workspace 路径解析 + 包内路径定位"""

import os
import re
from functools import lru_cache
from pathlib import Path

from llmw.errors import WorkspaceNotFound

DEFAULT_WORKSPACE = Path.home() / "yzr-llm-wiki-workspace"


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


def package_root() -> Path:
    """返回 llmw 包根 (含 __init__.py 的目录的父)"""
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    """返回仓库根 (package_root 的父目录)"""
    return package_root().parent


def wiki_spec_templates_dir() -> Path:
    """同仓 yzr-llm-wiki-management/references/ 目录路径(CLI 字节金标准的来源)

    包含:
      - agents-md-template.md / claude-md-template.md (AGENTS.md SSOT / CLAUDE.md 薄壳模板)
      - fixtures/{index.md,log.md,memory-index,tags.md,scripts.md,gitignore}.txt

    不存在 → 由调用方 raise SkillMissing
    """
    return repo_root() / "yzr-llm-wiki-management" / "references"


def workspace_spec_templates_dir() -> Path:
    """同仓 yzr-llm-workspace-management/references/ 目录路径(workspace CLAUDE.md 模板来源)

    包含:
      - workspace-claude-md-template.md (workspace CLAUDE.md 拷贝模板, spec §4)
      - workspace-spec.md

    不存在 → 由调用方 raise SkillMissing
    """
    return repo_root() / "yzr-llm-workspace-management" / "references"


def templates_dir() -> Path:
    return repo_root() / "templates"


@lru_cache(maxsize=None)
def skill_spec_version(skill_dir: str, key: str) -> str:
    """读同仓 SKILL.md frontmatter 的 *_spec_version——单一真源，bump 只改 frontmatter 一处。

    skill_dir: 'yzr-llm-wiki-management' / 'yzr-llm-workspace-management'
    key: 'wiki_spec_version' / 'workspace_spec_version'
    同仓 + editable-only 定位下 SKILL.md 恒存在；读不到直接失败（不静默降级）。
    """
    skill_md = repo_root() / skill_dir / "SKILL.md"
    m = re.search(
        rf"^[ \t]*{key}:[ \t]*(\S+)[ \t]*$",
        skill_md.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if m is None:
        raise RuntimeError(f"SKILL.md 缺 {key} 字段: {skill_md}")
    return m.group(1).strip()
