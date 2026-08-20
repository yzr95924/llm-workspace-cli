"""llmw.content.render — 骨架文件渲染单一入口

所有"模板 + 变量 → 骨架字节"的事实都在此模块。消费方:

- llmw.wiki.init_wiki.render_and_write（wiki add 落盘骨架，保留编排逻辑）
- llmw.workspace.manager 的 init 流程（workspace init 落盘 AGENTS.md / CLAUDE.md）
- llmw.content.upgrade 引擎（resync 重渲染，Task 4）
- llmw.content.wiki_fixtures 的 agents-md-template-sync（render-compare）
- llmw.content.workspace_fixtures 的 template-sync（render-compare）
- tests/test_content_*（替代迷你渲染器 `_render_agents_md` 等）

变量 SSOT:
- metadata toml: wiki_metadata.toml (name/topic/created_at) / workspace.toml (display_name)
- 版本常量: llmw/__init__.py (WIKI_SPEC_VERSION / WORKSPACE_SPEC_VERSION / __version__)

不从旧文件反提取变量（这是派生化 checker 的基础，详见设计文档 §7.2）。
"""

import re
from pathlib import Path
from typing import Dict

from llmw.config import wiki_templates_dir, workspace_templates_dir
from llmw.errors import SetupFailed


def _substitute(text: str, mapping: Dict[str, str]) -> str:
    """替换 {{KEY}} 占位符；末尾 assert 无残留。

    残留占位符 = 模板漂移（模板加了变量但 mapping 没覆盖），快速失败。
    """
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{[^}]+\}\}", text)
    if leftover:
        raise SetupFailed(
            f"模板占位符未替换干净: {leftover}",
            hint="检查 mapping 是否覆盖所有占位符（render.py 单一入口）",
        )
    return text


def _read_template(path: Path) -> str:
    """读模板文本；失败抛 SetupFailed 统一兜底。"""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取模板失败: {e.filename}",
            hint="检查 references/ 是否完整（SKILL 随 CLI 同仓，仓库完整克隆即含）",
        ) from e


# ===== wiki side =====


def render_wiki_agents_md(*, topic: str, setup_date: str, cli_version: str, spec_version: str) -> str:
    """渲染 wiki <wiki-root>/AGENTS.md（模板 4 占位符）。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "agents-md-template.md")
    return _substitute(
        tmpl,
        {
            "TOPIC_NAME": topic,
            "SETUP_DATE": setup_date,
            "CLI_VERSION": cli_version,
            "WIKI_SPEC_VERSION": spec_version,
        },
    )


def render_wiki_claude_md(*, topic: str) -> str:
    """渲染 wiki <wiki-root>/CLAUDE.md 薄壳（模板仅 {{TOPIC_NAME}}）。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "claude-md-template.md")
    return _substitute(tmpl, {"TOPIC_NAME": topic})


def render_wiki_index_md(*, topic: str, setup_date: str) -> str:
    """渲染 wiki/index.md 初始骨架（来自 fixtures/index.md.txt，2 占位符）。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "fixtures" / "index.md.txt")
    return _substitute(tmpl, {"TOPIC_NAME": topic, "SETUP_DATE": setup_date})


def render_wiki_log_md(*, topic: str, setup_date: str) -> str:
    """渲染 wiki/log.md 初始骨架（来自 fixtures/log.md.txt，2 占位符）。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "fixtures" / "log.md.txt")
    return _substitute(tmpl, {"TOPIC_NAME": topic, "SETUP_DATE": setup_date})


# ===== workspace side =====


def render_workspace_agents_md(*, display_name: str, setup_date: str, cli_version: str, spec_version: str) -> str:
    """渲染 workspace <workspace>/AGENTS.md（模板 4 占位符）。"""
    refs = workspace_templates_dir()
    tmpl = _read_template(refs / "workspace-agents-md-template.md")
    return _substitute(
        tmpl,
        {
            "WORKSPACE_DISPLAY_NAME": display_name,
            "SETUP_DATE": setup_date,
            "CLI_VERSION": cli_version,
            "WORKSPACE_SPEC_VERSION": spec_version,
        },
    )


def render_workspace_claude_md(*, display_name: str) -> str:
    """渲染 workspace <workspace>/CLAUDE.md 薄壳（模板仅 {{WORKSPACE_DISPLAY_NAME}}）。"""
    refs = workspace_templates_dir()
    tmpl = _read_template(refs / "workspace-claude-md-template.md")
    return _substitute(tmpl, {"WORKSPACE_DISPLAY_NAME": display_name})
