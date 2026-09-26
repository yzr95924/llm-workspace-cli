"""骨架文件渲染单一入口：模板 + 变量 → 骨架字节。

变量 SSOT = metadata toml + 版本 / 行为常量，不从旧文件反提取（派生化 checker 的基础）。
"""

import re
from pathlib import Path
from typing import Dict

from llmw.config import wiki_templates_dir
from llmw.content.log_format import LOG_OPS, LOG_RETENTION_LIMIT
from llmw.content.page_types import TYPE_TO_SECTION, WIKI_SUBDIRS
from llmw.errors import SetupFailed


def wiki_constant_mapping() -> Dict[str, str]:
    return {
        "LOG_RETENTION_LIMIT": str(LOG_RETENTION_LIMIT),
        "LOG_OPS": " / ".join(f"`{op}`" for op in LOG_OPS),
        "WIKI_SUBDIRS_GLOB": "{" + ",".join(WIKI_SUBDIRS) + "}",
        "INDEX_SECTIONS": " / ".join(sorted(TYPE_TO_SECTION.values())),
    }


def _substitute(text: str, mapping: Dict[str, str]) -> str:
    """替换 {{KEY}}；残留占位符 = 模板漂移，快速失败。"""
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
    """读模板；失败抛 SetupFailed（包内资源缺失）。"""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取模板失败: {e.filename}",
            hint="检查 llmw/content/templates/ 包内资源是否完整（editable 安装或 wheel 打包缺失）",
        ) from e


# ===== wiki side =====


def render_wiki_agents_md(*, topic: str, setup_date: str, cli_version: str, format_version: str) -> str:
    """渲染 <wiki-root>/AGENTS.md。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "agents-md-template.md")
    return _substitute(
        tmpl,
        {
            "TOPIC_NAME": topic,
            "SETUP_DATE": setup_date,
            "CLI_VERSION": cli_version,
            "WIKI_FORMAT_VERSION": format_version,
            **wiki_constant_mapping(),
        },
    )


def render_wiki_claude_md(*, topic: str) -> str:
    """渲染 <wiki-root>/CLAUDE.md 薄壳。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "claude-md-template.md")
    return _substitute(tmpl, {"TOPIC_NAME": topic})


def render_wiki_index_md(*, topic: str, setup_date: str) -> str:
    """渲染 wiki/index.md 初始骨架。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "fixtures" / "index.md.txt")
    return _substitute(tmpl, {"TOPIC_NAME": topic, "SETUP_DATE": setup_date, **wiki_constant_mapping()})


def render_wiki_log_md(*, topic: str, setup_date: str) -> str:
    """渲染 wiki/log.md 初始骨架。"""
    refs = wiki_templates_dir()
    tmpl = _read_template(refs / "fixtures" / "log.md.txt")
    return _substitute(tmpl, {"TOPIC_NAME": topic, "SETUP_DATE": setup_date, **wiki_constant_mapping()})


# ===== workspace side =====
