"""wiki 仓初始化: 读同仓 yzr-llm-wiki-management/references/ 下的模板与 fixtures,
把 wiki 仓"出生形态"落盘（按包内 templates/ + fixtures/ 字节金标准；`llmw wiki check-fixtures` 探测）.

CLI 内联实现(wiki 创建归 CLI 负责,skill 只供 references 素材).
fixtures 是 CLI 字节金标准;完整 gate 走 scripts/test/smoke_fixtures.py
(CI 跑 real llmw init + wiki add 后用 llmw.content checkers 探测器断言)。

本模块只做**编排**(mkdir 目录树 + .gitkeep 占位 + atomic_write 8 份字面量产物);
**模板渲染**统一走 llmw.content.render(单一入口,变量 SSOT,详见设计文档 §7.2)。

落盘 8 件产物(AGENTS.md SSOT 拆出):
  AGENTS.md, CLAUDE.md(薄壳), .gitignore, wiki/index.md, wiki/log.md,
  MEMORY/MEMORY.md, wiki/tags.md, scripts/SCRIPTS.md
子目录: raw/{articles,assets,discussions}, wiki/{5 类内容页}, MEMORY/, scripts/

git 红线: CLI 绝不碰 git——init 仅落盘目录树 + .gitkeep 占位
+ 打印手动 hint;所有 git 操作由用户自行触发。.gitkeep 无条件落盘(8 个空目录:
5 内容页 + raw/articles + raw/assets + raw/discussions),便于用户后续 `git add .`
跟踪空目录。
"""

from pathlib import Path

from llmw.config import wiki_templates_dir
from llmw.content.render import (
    render_wiki_agents_md,
    render_wiki_claude_md,
    render_wiki_index_md,
    render_wiki_log_md,
)
from llmw.errors import SetupFailed, SkillMissing, WikiAlreadyInitialized
from llmw.fsutil import atomic_write


# 内容页子目录 + MEMORY/, 字母序创建
_CONTENT_SUBDIRS = [
    "comparisons",
    "concepts",
    "entities",
    "sources",
    "syntheses",
]
# raw/ 默认子目录(字母序):
#   articles / assets —— 始终预建(默认占位)
#   discussions       —— 预建(协作草稿层):用户高频用,预建免去手动 mkdir;
#                        .gitkeep 不被 .gitignore 排除,git 正常跟踪。
# raw/external/ **不**在此列:按需建(接入外部仓 + anchor.toml 时才存在),
# 且 .gitignore 的 `raw/external/*` 规则会吃掉 .gitkeep——预建对 git 不可见(实测)。
_RAW_SUBDIRS = ["articles", "assets", "discussions"]

# step 3: 需要 .gitkeep 占位的空目录——5 内容页子目录 + raw 三个默认
# 子目录(articles/assets/discussions)。MEMORY/ 与 scripts/ 不需要(各有真实索引文件
# MEMORY.md / SCRIPTS.md 让目录被 git 跟踪)。.gitkeep 无条件落盘(不 gated on --git),
# 纯目录树下无害。
_GITKEEP_DIRS = [Path("wiki") / d for d in _CONTENT_SUBDIRS] + [
    Path("raw") / d for d in _RAW_SUBDIRS
]


def check_not_initialized(wiki_dir: Path) -> None:
    """6 份 CLI 落盘产物任一已存在 → 拒绝覆盖

    表格字面列 3 份(AGENTS.md / CLAUDE.md / wiki/index.md);§8 总段"绝不允许
    覆盖已有 wiki"的精神把范围扩到 MEMORY.md / tags.md / SCRIPTS.md。
    必须在 mkdir 前调用,避免留下半成品目录.
    """
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
    """按包内 templates/ + fixtures/ 落盘 wiki 仓骨架.

    Args:
        wiki_dir: wiki 仓根目录 (含路径名);调用方应已 mkdir 此目录.
        topic: 主题名 (人类可读, e.g. "LLM Systems"),用于 AGENTS.md / CLAUDE.md / index.md / log.md 占位符.
        today: YYYY-MM-DD HH:MM,setup 日期(字节金标准粒度,floor 兼容老格式解析).
        cli_version: llmw.__version__,用于 AGENTS.md 占位符.
        format_version: llmw.WIKI_FORMAT_VERSION,用于 AGENTS.md 占位符.

    Raises:
        SkillMissing: SKILL 的 references/ 目录不存在.
        SetupFailed: 模板读取失败 / 占位符残留 / atomic_write 失败.

    Note:
        本函数不碰 git——仅落盘目录树 + .gitkeep 占位 + 8 份字面量
        产物;所有 git 操作由用户自行触发(调用方负责打印手动 hint)。
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

    # 读 4 份无占位符的字面量源(/ §9.1 / §14 / §6 gitignore)
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

    # 字节金标准自检不放在此处:fixtures 是带占位符模板,用户态 mapping 不匹配固定测试值,
    # byte-cmp 会误伤。完整 gate 走 scripts/test/smoke_fixtures.py
    # (llmw.content checkers + workspace 探测器)——CI 跑 real llmw init + llmw wiki add
    # 后用探测器断言 0 error,等价于"产物满足 templates/fixtures 字节契约"。

    # 落盘顺序: 先建所有子目录, 再 .gitkeep 占位, 再 atomic_write 8 份字面量产物
    # MEMORY/在 wiki 根,与 wiki/ 平级;scripts/ 必须始终创建
    for d in (
        [wiki_dir / "raw" / x for x in _RAW_SUBDIRS]
        + [wiki_dir / "wiki" / x for x in _CONTENT_SUBDIRS]
        + [wiki_dir / "MEMORY"]
        + [wiki_dir / "scripts"]
    ):
        d.mkdir(parents=True, exist_ok=True)

    # step 3: .gitkeep 无条件落盘——8 个空目录占位,便于用户后续
    # `git add .` 跟踪。touch 是幂等 best-effort:目录已建,空文件无害;失败不阻断落盘。
    for rel in _GITKEEP_DIRS:
        try:
            (wiki_dir / rel / ".gitkeep").touch()
        except OSError:
            pass

    try:
        # 先写 AGENTS.md (SSOT), 再写 CLAUDE.md (薄壳)
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
