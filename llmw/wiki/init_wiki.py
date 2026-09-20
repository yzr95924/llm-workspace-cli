"""wiki 仓初始化：把"出生形态"落盘（8 件产物 + 目录树 + .gitkeep）。

只做编排；模板渲染统一走 llmw.content.render（变量 SSOT = metadata + 版本常量）。
字节金标准 gate 在 scripts/test/smoke_fixtures.py。git 红线：CLI 绝不碰 git，
只落盘 + 打印手动 hint。
"""

from pathlib import Path

from llmw.config import wiki_templates_dir
from llmw.content.page_types import WIKI_SUBDIRS
from llmw.content.render import (
    render_wiki_agents_md,
    render_wiki_claude_md,
    render_wiki_index_md,
    render_wiki_log_md,
)
from llmw.errors import SetupFailed, SkillMissing, WikiAlreadyInitialized
from llmw.fsutil import atomic_write


# 内容页子目录按字母序创建（SSOT：page_types.WIKI_SUBDIRS）
_CONTENT_SUBDIRS = sorted(WIKI_SUBDIRS)
# raw/ 默认子目录；external/ 不预建——.gitignore 的 `raw/external/*` 会吃掉 .gitkeep，
# 预建对 git 不可见（接入外部仓时按需建）
_RAW_SUBDIRS = ["articles", "assets", "discussions"]

# 需 .gitkeep 占位的空目录（MEMORY/ 与 scripts/ 各有真实索引文件，不需要占位）
_GITKEEP_DIRS = [Path("wiki") / d for d in _CONTENT_SUBDIRS] + [
    Path("raw") / d for d in _RAW_SUBDIRS
]


def check_not_initialized(wiki_dir: Path) -> None:
    """6 份产物任一已存在 → 拒绝覆盖（须在 mkdir 前调用，避免半成品目录）。"""
    files = [
        wiki_dir / "AGENTS.md",
        wiki_dir / "CLAUDE.md",
        wiki_dir / "wiki" / "index.md",
        wiki_dir / "MEMORY" / "MEMORY.md",
        wiki_dir / "wiki" / "tags.md",
        wiki_dir / "scripts" / "SCRIPTS.md",
    ]
    for f in files:
        if f.exists():
            raise WikiAlreadyInitialized(
                f"{f} 已存在,拒绝覆盖",
                hint="若要重新初始化,请先备份 + 删除该文件",
            )


def render_and_write(
    wiki_dir: Path,
    topic: str,
    today: str,
    cli_version: str,
    format_version: str,
) -> None:
    """按包内 templates/ + fixtures/ 落盘 wiki 骨架（调用方已 mkdir wiki_dir；本函数不碰 git）。

    Raises: SkillMissing（templates 缺失）/ SetupFailed（渲染 / 写入失败）。
    """
    refs = wiki_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(
            f"找不到包内 templates/wiki/ 目录: {refs}",
            hint="llmw/content/templates/wiki/ 目录缺失（CLI 包完整性受损）",
        )
    fixtures = refs / "fixtures"
    if not fixtures.is_dir():
        raise SetupFailed(
            f"fixtures 目录缺失: {fixtures}",
            hint="检查 llmw/content/templates/wiki/fixtures/ 是否完整",
        )

    # 渲染 4 份有占位符的文件（走 llmw.content.render 单一入口）
    agents_md = render_wiki_agents_md(
        topic=topic,
        setup_date=today,
        cli_version=cli_version,
        format_version=format_version,
    )
    claude_md = render_wiki_claude_md(topic=topic)
    index_md = render_wiki_index_md(topic=topic, setup_date=today)
    log_md = render_wiki_log_md(topic=topic, setup_date=today)

    # 读 4 份无占位符的字面量源(memory-index.txt / tags.md.txt / scripts.md.txt / gitignore.txt)
    try:
        memory_md = (fixtures / "memory-index.txt").read_text(encoding="utf-8")
        tags_md = (fixtures / "tags.md.txt").read_text(encoding="utf-8")
        scripts_md = (fixtures / "scripts.md.txt").read_text(encoding="utf-8")
        gitignore = (fixtures / "gitignore.txt").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取 fixture 失败: {e.filename}",
            hint="检查 llmw/content/templates/wiki/fixtures/ 是否完整",
        )

    # 先建所有子目录，再 .gitkeep 占位，再落盘 8 份产物
    for d in (
        [wiki_dir / "raw" / x for x in _RAW_SUBDIRS]
        + [wiki_dir / "wiki" / x for x in _CONTENT_SUBDIRS]
        + [wiki_dir / "MEMORY"]
        + [wiki_dir / "scripts"]
    ):
        d.mkdir(parents=True, exist_ok=True)

    # .gitkeep 无条件落盘（best-effort：失败不阻断）
    for rel in _GITKEEP_DIRS:
        try:
            (wiki_dir / rel / ".gitkeep").touch()
        except OSError:
            pass

    try:
        atomic_write(wiki_dir / "AGENTS.md", agents_md)
        atomic_write(wiki_dir / "CLAUDE.md", claude_md)
        atomic_write(wiki_dir / ".gitignore", gitignore)
        atomic_write(wiki_dir / "wiki" / "index.md", index_md)
        atomic_write(wiki_dir / "wiki" / "log.md", log_md)
        atomic_write(wiki_dir / "MEMORY" / "MEMORY.md", memory_md)
        atomic_write(wiki_dir / "wiki" / "tags.md", tags_md)
        atomic_write(wiki_dir / "scripts" / "SCRIPTS.md", scripts_md)
    except OSError as e:
        raise SetupFailed(
            f"写入文件失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )
