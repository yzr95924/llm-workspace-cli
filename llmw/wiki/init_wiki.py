"""wiki 仓初始化: 读同仓 yzr-llm-wiki-management/references/ 下的模板与 fixtures,
按 wiki-spec.md §1-§7 + §9.1 + §14 把 wiki 仓"出生形态"落盘.

CLI 内联实现(wiki 创建归 CLI 负责,skill 只供 references 素材).
fixtures 是 CLI 字节金标准;完整 gate 走 scripts/test/smoke_fixtures.py
(CI 跑 real llmw init + wiki add 后用 check_wiki_fixtures.py 探测器断言)。

落盘 8 件产物(AGENTS.md SSOT 拆出):
  AGENTS.md, CLAUDE.md(薄壳), .gitignore, wiki/index.md, wiki/log.md,
  MEMORY/MEMORY.md, wiki/tags.md, scripts/SCRIPTS.md
子目录: raw/{articles,assets,discussions}, wiki/{5 类内容页}, MEMORY/, scripts/

git 红线(spec §7): CLI 绝不碰 git——init 仅落盘目录树 + .gitkeep 占位
+ 打印手动 hint;所有 git 操作由用户自行触发。.gitkeep 无条件落盘(8 个空目录:
5 内容页 + raw/articles + raw/assets + raw/discussions),便于用户后续 `git add .`
跟踪空目录。
"""

import re
from pathlib import Path
from typing import Dict

from llmw.config import wiki_spec_templates_dir
from llmw.errors import SetupFailed, SkillMissing, WikiAlreadyInitialized
from llmw.fsutil import atomic_write


# spec §1: 内容页子目录 + MEMORY/, 字母序创建
_CONTENT_SUBDIRS = [
    "comparisons",
    "concepts",
    "entities",
    "sources",
    "syntheses",
]
# raw/ 默认子目录(字母序):
#   articles / assets —— 始终预建(spec §1 默认占位)
#   discussions       —— 预建(spec §15 协作草稿层):用户高频用,预建免去手动 mkdir;
#                        .gitkeep 不被 .gitignore 排除,git 正常跟踪。
# raw/external/ **不**在此列:spec §13 按需建(接入外部仓 + anchor.toml 时才存在),
# 且 .gitignore 的 `raw/external/*` 规则会吃掉 .gitkeep——预建对 git 不可见(实测)。
_RAW_SUBDIRS = ["articles", "assets", "discussions"]

# spec §7 step 3: 需要 .gitkeep 占位的空目录——5 内容页子目录 + raw 三个默认
# 子目录(articles/assets/discussions)。MEMORY/ 与 scripts/ 不需要(各有真实索引文件
# MEMORY.md / SCRIPTS.md 让目录被 git 跟踪)。.gitkeep 无条件落盘(不 gated on --git),
# 纯目录树下无害。
_GITKEEP_DIRS = [Path("wiki") / d for d in _CONTENT_SUBDIRS] + [
    Path("raw") / d for d in _RAW_SUBDIRS
]


def check_not_initialized(wiki_dir: Path) -> None:
    """spec §8: 6 份 CLI 落盘产物任一已存在 → 拒绝覆盖

    spec §8 表格字面列 3 份(AGENTS.md / CLAUDE.md / wiki/index.md);§8 总段"绝不允许
    覆盖已有 wiki"的精神把范围扩到 MEMORY.md / tags.md / SCRIPTS.md。
    必须在 mkdir 前调用,避免留下半成品目录.
    """
    files = [
        wiki_dir / "AGENTS.md",  # spec §2 (用户宪法/SSOT)
        wiki_dir / "CLAUDE.md",  # spec §2 (薄壳, Claude Code 自动加载)
        wiki_dir / "wiki" / "index.md",  # spec §3 (agent 单一入口)
        wiki_dir / "MEMORY" / "MEMORY.md",  # spec §5.1
        wiki_dir / "wiki" / "tags.md",  # spec §9.1
        wiki_dir / "scripts" / "SCRIPTS.md",  # spec §14
    ]
    for f in files:
        if f.exists():
            raise WikiAlreadyInitialized(
                f"{f} 已存在,拒绝覆盖",
                hint="若要重新初始化,请先备份 + 删除该文件",
            )


def _substitute(text: str, mapping: Dict[str, str]) -> str:
    """替换 {{KEY}} 占位符; 末尾 assert 无残留"""
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{[^}]+\}\}", text)
    if leftover:
        raise SetupFailed(
            f"模板占位符未替换干净: {leftover}",
            hint="检查 mapping 是否覆盖所有占位符",
        )
    return text


def render_and_write(
    wiki_dir: Path,
    topic: str,
    today: str,
    cli_version: str,
    spec_version: str,
) -> None:
    """按 wiki-spec.md 落盘 wiki 仓骨架.

    Args:
        wiki_dir: wiki 仓根目录 (含路径名);调用方应已 mkdir 此目录.
        topic: 主题名 (人类可读, e.g. "LLM Systems"),用于 AGENTS.md / CLAUDE.md / index.md / log.md 占位符.
        today: YYYY-MM-DD HH:MM,setup 日期(字节金标准粒度,floor 兼容老格式解析).
        cli_version: llmw.__version__,用于 AGENTS.md 占位符.
        spec_version: llmw.WIKI_SPEC_VERSION,用于 AGENTS.md 占位符.

    Raises:
        SkillMissing: SKILL 的 references/ 目录不存在.
        SetupFailed: 模板读取失败 / 占位符残留 / atomic_write 失败.

    Note:
        spec §7: 本函数不碰 git——仅落盘目录树 + .gitkeep 占位 + 8 份字面量
        产物;所有 git 操作由用户自行触发(调用方负责打印手动 hint)。
    """
    refs = wiki_spec_templates_dir()
    if not refs.is_dir():
        raise SkillMissing(
            f"找不到 SKILL references/ 目录: {refs}",
            hint="检查 yzr-llm-wiki-management/references/ 是否完整（SKILL 随 CLI 同仓）",
        )
    fixtures = refs / "fixtures"
    if not fixtures.is_dir():
        raise SetupFailed(
            f"fixtures 目录缺失: {fixtures}",
            hint="检查 references/fixtures/ 是否完整",
        )

    # 读 8 份字面量源(spec §2 / §3 / §4 / §5.1 / §6 / §9.1 / §14)
    # spec §2: AGENTS.md (SSOT, 工具无关) + CLAUDE.md (薄壳, Claude Code 自动加载)
    # 占位符子集不同 — AGENTS.md 4 占位符, CLAUDE.md 仅 {{TOPIC_NAME}};
    # 共享 mapping, str.replace 对不存在的 key 是 no-op, 不影响
    try:
        agents_md_tmpl = (refs / "agents-md-template.md").read_text(encoding="utf-8")
        claude_md_tmpl = (refs / "claude-md-template.md").read_text(encoding="utf-8")
        index_md_tmpl = (fixtures / "index.md.txt").read_text(encoding="utf-8")
        log_md_tmpl = (fixtures / "log.md.txt").read_text(encoding="utf-8")
        memory_md_tmpl = (fixtures / "memory-index.txt").read_text(encoding="utf-8")
        tags_md_tmpl = (fixtures / "tags.md.txt").read_text(encoding="utf-8")
        scripts_md_tmpl = (fixtures / "scripts.md.txt").read_text(encoding="utf-8")
        gitignore_tmpl = (fixtures / "gitignore.txt").read_text(encoding="utf-8")
    except OSError as e:
        raise SetupFailed(
            f"读取模板失败: {e.filename}",
            hint="检查 yzr-llm-wiki-management/references/ 是否完整（SKILL 随 CLI 同仓）",
        )

    mapping = {
        "TOPIC_NAME": topic,
        "SETUP_DATE": today,
        "WIKI_SPEC_VERSION": spec_version,
        "CLI_VERSION": cli_version,
    }

    # 渲染(占位符替换 + assert 无残留)
    # 4 份有占位符: AGENTS.md (4) / CLAUDE.md 薄壳 (1) / index.md (2) / log.md (2)
    # 4 份无占位符少数派: memory-index / tags / scripts / gitignore
    # (fixture 已经不含占位符,无需 _substitute)
    try:
        agents_md = _substitute(agents_md_tmpl, mapping)
        claude_md = _substitute(claude_md_tmpl, mapping)
        index_md = _substitute(index_md_tmpl, mapping)
        log_md = _substitute(log_md_tmpl, mapping)
    except SetupFailed:
        raise

    # 字节金标准自检不放在此处:fixtures 是带占位符模板,用户态 mapping 不匹配固定测试值,
    # byte-cmp 会误伤。完整 gate 走 scripts/test/smoke_fixtures.py
    # (check_wiki_fixtures.py + workspace 探测器)——CI 跑 real llmw init + llmw wiki add
    # 后用探测器断言 0 error,等价于"产物满足 spec/fixtures 字节契约"。

    # 落盘顺序: 先建所有子目录, 再 .gitkeep 占位, 再 atomic_write 8 份字面量产物
    # MEMORY/在 wiki 根,与 wiki/ 平级;scripts/ 必须始终创建
    for d in (
        [wiki_dir / "raw" / x for x in _RAW_SUBDIRS]
        + [wiki_dir / "wiki" / x for x in _CONTENT_SUBDIRS]
        + [wiki_dir / "MEMORY"]
        + [wiki_dir / "scripts"]
    ):
        d.mkdir(parents=True, exist_ok=True)

    # spec §7 step 3: .gitkeep 无条件落盘——8 个空目录占位,便于用户后续
    # `git add .` 跟踪。touch 是幂等 best-effort:目录已建,空文件无害;失败不阻断落盘。
    for rel in _GITKEEP_DIRS:
        try:
            (wiki_dir / rel / ".gitkeep").touch()
        except OSError:
            pass

    try:
        # spec §2: 先写 AGENTS.md (SSOT), 再写 CLAUDE.md (薄壳)
        atomic_write(wiki_dir / "AGENTS.md", agents_md)
        atomic_write(wiki_dir / "CLAUDE.md", claude_md)
        atomic_write(wiki_dir / ".gitignore", gitignore_tmpl)
        atomic_write(wiki_dir / "wiki" / "index.md", index_md)
        atomic_write(wiki_dir / "wiki" / "log.md", log_md)
        atomic_write(wiki_dir / "MEMORY" / "MEMORY.md", memory_md_tmpl)
        atomic_write(wiki_dir / "wiki" / "tags.md", tags_md_tmpl)
        atomic_write(wiki_dir / "scripts" / "SCRIPTS.md", scripts_md_tmpl)
    except OSError as e:
        raise SetupFailed(
            f"写入文件失败: {e.filename or e.strerror}",
            hint="检查磁盘空间 + 目录权限",
        )
