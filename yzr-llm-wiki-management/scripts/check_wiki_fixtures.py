#!/usr/bin/env python3
"""check_wiki_fixtures.py — fixtures 一致性检查（升级时专用）

按 wiki-spec（§3/§4/§5/§6/§9.1/§10/§13/§14 各节）的 fixture 视角，校验一个已存在 wiki 的
"约定文件"（AGENTS.md §八 / .gitignore / wiki/index.md / wiki/log.md / wiki/tags.md /
MEMORY/MEMORY.md / MEMORY/*.md 条目 / scripts/SCRIPTS.md / raw/external/.symlink-anchor.toml /
wiki_metadata.toml）是否满足当前 wiki spec 的结构要求。本脚本只校验**结构性字节合规**；
语义合并（frontmatter 字段升级 / index 重复条目 / 多 MEMORY 条目归并等）由
migrate-workflow.md §六 + LLM agent 走 migration plan 时处理——本脚本不替代。

用法:
  python3 check_wiki_fixtures.py [<WIKI_ROOT>] [--json] [--target-spec <semver>]

缺省 --target-spec 时读 SKILL.md metadata.wiki_spec_version 作为"目标 spec"。
standalone（不依赖 lint_wiki.py）；自身合法 TOML 解析，不依赖 tomli/tomllib。

退出码:
  0 = 全部 check pass (或仅 skip)
  1 = 至少一条 check fail
  2 = 运行错误（路径 / 参数 / 文件 IO）

设计权衡:
- 该脚本不写文件，也不产出 migration plan（那是 lint_wiki.py --check-version
  `--apply` 以 stdout JSON 输出并 call 它的活）；standalone 调用方只能看到 stdout/JSON 报告。
- 21 条 check（13 条结构探测 + 7 条骨架字段比对 + 1 条模板自检 `template-no-outbound-refs`）；
  下一个 wiki spec 升级只需新增 register 条目 / SKELETON_SPECS 描述符。骨架信号硬编码在
  SKELETON_SPECS（与 references/canonical/ 一致，改 canonical 时手工同步描述符）；
  唯独 .gitignore 走 references/fixtures/gitignore.txt 自动跟随。
- `template-no-outbound-refs`（0.33.0+）：模板零出边引用是架构不变量（纪律正文唯一维护点 =
  模板；spec / SKILL.md / page-templates.md 单向指入模板），由该 check 机械强制。
- AGENTS.md 走**模板渲染比对**（0.26.0+ `agents-md-template-sync`）：从 wiki §八 提取
  主题/创建日期/CLI 版本三变量 + wiki 自钉 spec 版本，渲染 references/agents-md-template.md
  后字节比对——一次性覆盖"旧版本残留 + 本地改动"全部漂移，取代 0.25.0- 的两条存在性检查
  （has-at-imports / top-read-directive）。定制纪律应沉淀到 MEMORY/，不进 AGENTS.md。
- 复用 lint_wiki 的 WIKI_SUBDIRS / MEMORY_SUBDIR / EXTERNAL_SUBDIR 常量名（SSOT
  在 lint_wiki.py；本脚本硬编码确保 vendored 副本仍能跑）。
"""

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# -- 复用 lint_wiki.py 常量名（保持 SSOT 一致；standalone 不依赖 lint_wiki.py import）--
WIKI_SUBDIRS = ("entities", "concepts", "sources", "comparisons", "syntheses")
MEMORY_SUBDIR = "MEMORY"
EXTERNAL_SUBDIR = "external"
ANCHOR_FILENAME = ".symlink-anchor.toml"  # 0.17.0+ TOML

# -- 公开 check 注册表（顺序 = 输出顺序）--
# 每条: severity (error/warn)、rule_ref（指向 spec/lint-checklist 段）、desc（人读摘要）
CHECK_REGISTRY = [
    {
        "id": "agents-version-is-current",
        "severity": "error",
        "rule_ref": "wiki-spec.md §10",
        "desc": "AGENTS.md §八 Wiki Spec 版本行需与 --target-spec 一致",
    },
    {
        "id": "agents-md-template-sync",
        "severity": "error",
        "rule_ref": "wiki-spec.md §10.1",
        "desc": "AGENTS.md 与 references/agents-md-template.md 渲染稿字节一致（§八 四变量替换后）；定制纪律应沉淀到 MEMORY/",
    },
    {
        "id": "template-no-outbound-refs",
        "severity": "error",
        "rule_ref": "wiki-spec.md §2（纪律正文唯一副本 canonical）",
        "desc": "模板零出边引用——不得含 wiki-spec/page-templates/lint-checklist/SKILL.md/references/yzr-llm-wiki-management/阿拉伯数字 §节号（wiki 侧跨仓读不到 skill，指针全是死引用）",
    },
    {
        "id": "gitignore-external-track-toml",
        "severity": "error",
        "rule_ref": "wiki-spec.md §13.4",
        "desc": ".gitignore 含 `raw/external/*` 排除 + `!raw/external/.symlink-anchor.toml` 跟踪；老 `**/.symlink-anchor.json` 残留即报错",
    },
    {
        "id": "symlink-anchor-toml-schema",
        "severity": "error",
        "rule_ref": "wiki-spec.md §13.2",
        "desc": "raw/external/.symlink-anchor.toml（若存在）：合法 TOML + [[entry]] 数组 + 每 entry 必填 4 字段 + git 身份字段可选",
    },
    {
        "id": "symlink-anchor-toml-symlink-matches",
        "severity": "error",
        "rule_ref": "wiki-spec.md §13.1",
        "desc": "anchor 每个 [[entry]].symlink 对应 external/ 顶层同名 symlink；anchor 无对应 symlink / orphan symlink 一并检查",
    },
    {
        "id": "symlink-anchor-flat-not-legacy",
        "severity": "error",
        "rule_ref": "wiki-spec.md §13.6",
        "desc": "raw/external/ 不存在 <source-name>/ 子目录（0.17.0+ 扁平布局）",
    },
    {
        "id": "index-md-categories-stable",
        "severity": "warn",
        "rule_ref": "wiki-spec.md §3",
        "desc": "wiki/index.md 含 5 类别标题 (Entities / Concepts / Sources / Comparisons / Syntheses)",
    },
    {
        "id": "memory-index-no-frontmatter",
        "severity": "error",
        "rule_ref": "wiki-spec.md §5",
        "desc": "MEMORY/MEMORY.md（索引）不带 YAML frontmatter（其 ## 索引 段条目由 AGENTS.md 顶部 @MEMORY/MEMORY.md @import 加载）",
    },
    {
        "id": "memory-entries-indexed",
        "severity": "error",
        "rule_ref": "wiki-spec.md §5.1",
        "desc": "MEMORY/*.md（除 MEMORY.md）每条都在 MEMORY/MEMORY.md 索引中列出",
    },
    {
        "id": "log-md-format-strict",
        "severity": "error",
        "rule_ref": "wiki-spec.md §4",
        "desc": "wiki/log.md 每行匹配 `^## [YYYY-MM-DD HH:MM] (ingest|query|lint|setup) | .+$`（HH:MM 可选；老 wikis date-only 仍合法，宽容解析）",
    },
    {
        "id": "scripts-md-no-frontmatter",
        "severity": "error",
        "rule_ref": "wiki-spec.md §14",
        "desc": "scripts/SCRIPTS.md 不带 YAML frontmatter",
    },
    {
        "id": "tags-md-no-frontmatter",
        "severity": "error",
        "rule_ref": "wiki-spec.md §9.1",
        "desc": "wiki/tags.md 不带 YAML frontmatter",
    },
    {
        "id": "wiki-metadata-reads-satisfied",
        "severity": "error",
        "rule_ref": "wiki-spec.md §1.1 wiki_metadata.toml（SKILL 读取契约）",
        "desc": "wiki_metadata.toml 含 SKILL scan 读取的 6 字段：name / topic / display_name / description / tags / created_at",
    },
]

# -- 解析用正则 --
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")
LOG_LINE_RE = re.compile(
    r"^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] "
    r"(ingest|query|lint|setup) \| .+$"
)
AGENTS_VERSION_ROW_RE = re.compile(r"^\s*\|\s*Wiki Spec 版本\s*\|\s*([^|]+?)\s*\|")
AGENTS_TOPIC_ROW_RE = re.compile(r"^\s*\|\s*主题\s*\|\s*([^|]+?)\s*\|")
AGENTS_SETUP_DATE_ROW_RE = re.compile(r"^\s*\|\s*创建日期\s*\|\s*([^|]+?)\s*\|")
AGENTS_CLI_VERSION_ROW_RE = re.compile(r"^\s*\|\s*CLI 版本\s*\|\s*([^|]+?)\s*\|")
AGENTS_H1_TOPIC_RE = re.compile(r"^#\s+(.+?)\s+Wiki\s+—\s+LLM 维护守则\s*$")
INDEX_CATEGORY_RE = re.compile(r"^## (.+)$")
SOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GITIGNORE_TRACK_TOML_RE = re.compile(r"^!\s*raw/external/\.symlink-anchor\.toml\s*(#.*)?$")
GITIGNORE_TRACK_LEGACY_RE = re.compile(r"^!\s*raw/external/\*?/?\.symlink-anchor\.json\s*(#.*)?$")
GITIGNORE_EXCLUDE_EXTERNAL_RE = re.compile(r"^\s*raw/external/?\*?\s*(#.*)?$")
YAML_FRONT_MATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
CL_LLM_WIKI_ROOT = "LLM_WIKI_ROOT"


def _read_text(path: Path) -> Optional[str]:
    """读文件文本；失败返 None（不抛异常；fixture-check 静默容错）。"""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _skill_spec_version() -> Optional[str]:
    """读 SKILL.md metadata.wiki_spec_version（脚本相对路径）。

    找不到 / 解析失败返 None——Standalone 调用方用 --target-spec 显式传；该函数
    只在缺省 --target-spec 时作为 fallback。
    """
    # __file__ -> scripts/check_wiki_fixtures.py → ../SKILL.md
    skill_md = Path(__file__).resolve().parent.parent / "SKILL.md"
    if not skill_md.is_file():
        return None
    text = _read_text(skill_md)
    if text is None:
        return None
    m = re.search(r"^[ \t]*wiki_spec_version:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def _compare_semver(a: Optional[str], b: Optional[str]) -> str:
    """返 'equal' / 'older' / 'newer' / 'unknown'。"""
    if not a or not b:
        return "unknown"

    def parse(v: str) -> Optional[Tuple[int, int, int]]:
        m = SEMVER_RE.search(v)
        if not m:
            return None
        try:
            return tuple(int(x) for x in m.group(0).split("."))  # type: ignore
        except ValueError:
            return None

    av, bv = parse(a), parse(b)
    if not av or not bv:
        return "unknown"
    if av < bv:
        return "older"
    if av > bv:
        return "newer"
    return "equal"


def _parse_anchor_minimal(anchor_path: Path) -> Optional[List[Dict[str, str]]]:
    """最小 TOML 解析——支持 [[entry]] 表 + key = "value" 双引号。

    与 lint_wiki.py _parse_anchor 同语义，独立以避免脚本间 import。返回 List[Dict]
    或 None（文件缺失 / 解析失败 / 无有效 entry）。
    """
    text = _read_text(anchor_path)
    if text is None:
        return None
    entries = []  # type: List[Dict[str, str]]
    current = None  # type: Optional[Dict[str, str]]
    for raw_line in text.splitlines():
        if "#" in raw_line:
            in_str = False
            cut = -1
            for i, ch in enumerate(raw_line):
                if ch == '"':
                    in_str = not in_str
                elif ch == "#" and not in_str:
                    cut = i
                    break
            if cut >= 0:
                raw_line = raw_line[:cut]
        stripped = raw_line.rstrip().strip()
        if not stripped:
            continue
        m = re.match(r"^\[\[(\w+)\]\]\s*$", stripped)
        if m:
            if current is not None:
                entries.append(current)
            current = {}
            continue
        m = re.match(r'^([a-z_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', stripped)
        if m:
            key, raw_val = m.group(1), m.group(2)
            val = re.sub(
                r"\\(.)",
                lambda mo: {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    '"': '"',
                    "\\": "\\",
                }.get(mo.group(1), mo.group(1)),
                raw_val,
            )
            if current is not None:
                current[key] = val
            continue
        # 顶层标量（schema_version = 1 等）跳过
        m = re.match(r"^([a-z_]+)\s*=\s*([0-9]+|true|false)\s*$", stripped)
        if m:
            continue
        # 未知行 silent 跳过——返回上层按"无有效 entry"判定

    if current is not None:
        entries.append(current)

    valid = [
        e
        for e in entries
        if all(e.get(k) for k in ("symlink", "target", "captured_at")) and e.get("kind") == "external-repo"
    ]
    return valid if valid else None


# ============================================================================
# 各 check 函数定义——每个返 Dict { passed, severity, expected, actual, file, evidence }
# 约定：returned dict 至少有 "passed" (bool)；passed=False 时尽量附 "expected"/"actual"
# ============================================================================


def check_agents_version(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """AGENTS.md §八 spec 行与 --target-spec 一致"""
    target_spec = info.get("target_spec") or None
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": "AGENTS.md",
    }
    if target_spec is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "--target-spec 未提供；跳过版本对齐检查"
        return out

    # 从 AGENTS.md 抓行；若 AGENTS.md 不存在，fallback CLAUDE.md（pre-0.11.0 老 wiki 兼容）
    found_version = None
    source_file = None
    for candidate in ("AGENTS.md", "CLAUDE.md"):
        fpath = wiki_root / candidate
        text = _read_text(fpath)
        if text is None:
            continue
        for line in text.splitlines():
            m = AGENTS_VERSION_ROW_RE.match(line)
            if not m:
                continue
            cell = m.group(1).strip()
            semver = SEMVER_RE.search(cell)
            if semver:
                found_version = semver.group(0)
                source_file = candidate
            break
        if found_version is not None:
            break
    if found_version is None:
        out["passed"] = False  # type: ignore
        out["actual"] = "(无法解析 §八 Wiki Spec 版本行)"
        out["expected"] = target_spec
        return out
    out["file"] = source_file  # type: ignore
    cmp = _compare_semver(found_version, target_spec)
    if cmp != "equal":
        out["passed"] = False  # type: ignore
        out["actual"] = found_version
        out["expected"] = target_spec
        out["comparison"] = cmp  # type: ignore
    return out


def _extract_agents_row(text: str, row_re: "re.Pattern[str]") -> Optional[str]:
    """从 AGENTS.md §八 表格提取某字段行单元格；未命中返 None。"""
    for line in text.splitlines():
        m = row_re.match(line)
        if m:
            return m.group(1).strip()
    return None


def check_agents_md_template_sync(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """AGENTS.md 与 references/agents-md-template.md 渲染稿字节一致（0.26.0+）。

    per-wiki 变量只有 4 个（主题 / 创建日期 / CLI 版本 / Wiki Spec 版本，全在 H1 + §八），
    正文 §一~§七 + §九 跨 wiki 逐字相同——故用"提取变量 → 渲染模板 → 字节比对"一次覆盖
    旧版本残留 + 本地改动全部漂移，取代 0.25.0- 的两条存在性检查（has-at-imports /
    top-read-directive）。{{WIKI_SPEC_VERSION}} 用 wiki 自钉版本替换，与
    `agents-version-is-current`（版本行对齐 target）保持正交——本 check 只管"正文与模板同步"，
    不管版本新旧。
    修复路径：plan 的 fixtures-fix-agents-md-resync（全量重渲染；本地定制逐条与用户
    裁定搬 MEMORY/ 或丢弃）。
    """
    out = {"passed": True, "severity": "error", "file": "AGENTS.md"}  # type: Dict[str, object]
    wiki_text = _read_text(wiki_root / "AGENTS.md")
    if wiki_text is None:
        out["passed"] = None
        out["skipped"] = "AGENTS.md 不存在"
        return out
    template = _read_text(Path(__file__).resolve().parent.parent / "references" / "agents-md-template.md")
    if template is None:
        out["passed"] = None
        out["skipped"] = "references/agents-md-template.md 未找到（无法模板比对）"
        return out

    topic = _extract_agents_row(wiki_text, AGENTS_TOPIC_ROW_RE)
    if topic is None:  # fallback H1 `# <主题> Wiki — LLM 维护守则`
        h1 = next((ln for ln in wiki_text.splitlines() if ln.startswith("# ")), "")
        h1m = AGENTS_H1_TOPIC_RE.match(h1)
        if h1m:
            topic = h1m.group(1).strip()
    setup_date = _extract_agents_row(wiki_text, AGENTS_SETUP_DATE_ROW_RE)
    cli_version = _extract_agents_row(wiki_text, AGENTS_CLI_VERSION_ROW_RE)
    spec_cell = _extract_agents_row(wiki_text, AGENTS_VERSION_ROW_RE) or ""
    spec_semver = SEMVER_RE.search(spec_cell)

    if not topic or not setup_date or not cli_version or spec_semver is None:
        out["passed"] = False  # type: ignore
        out["expected"] = "§八 含可解析的 主题 / 创建日期 / CLI 版本 / Wiki Spec 版本 四行（模板比对前置）"
        out["actual"] = "§八 字段解析失败——走 fixtures-fix-agents-md-resync 全量重渲染（agent 人工提取变量）"
        return out

    rendered = (
        template.replace("{{TOPIC_NAME}}", topic)
        .replace("{{SETUP_DATE}}", setup_date)
        .replace("{{CLI_VERSION}}", cli_version)
        .replace("{{WIKI_SPEC_VERSION}}", spec_semver.group(0))
    )
    if rendered != wiki_text:
        diff = list(difflib.unified_diff(wiki_text.splitlines(), rendered.splitlines(), lineterm="", n=0))
        changed = [ln for ln in diff if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
        preview = "; ".join(ln[:60] for ln in changed[:4])
        out["passed"] = False  # type: ignore
        out["expected"] = "AGENTS.md 与渲染模板字节一致（定制纪律沉淀到 MEMORY/，不进本文件）"
        out["actual"] = f"{len(changed)} 行与模板渲染稿不一致（首处: {preview}）" if preview else "与模板渲染稿不一致"
    return out


# 模板零出边引用（0.33.0+ 架构不变量：纪律正文唯一维护点 = 模板，模板是引用图汇点）。
# 任何指向 skill 仓文件 / 阿拉伯数字 §节号的引用都会被本 check 报 error——wiki 侧 agent
# 跨仓解析不了这些指针（模板自己都写着"模板与配套工具随 skill 分发，不在本 wiki 内"），
# 对运行时读者是死指针；改纪律只改模板对应段，spec / SKILL.md / page-templates.md 单向指入模板。
TEMPLATE_OUTBOUND_PATTERNS = (
    "wiki-spec.md",
    "page-templates.md",
    "lint-checklist.md",
    "SKILL.md",
    "references/",
    "yzr-llm-wiki-management",
    "OKF",
)
TEMPLATE_OUTBOUND_SECTION_RE = re.compile(r"§[0-9]")


def _scan_template_outbound_refs(text):
    """扫模板文本中的出边引用，返回 ["<行号>:<模式>", ...]（空 = 干净）。

    独立成函数便于测试——检测逻辑直接喂合成文本；check 函数做文件 IO + 报告。
    """
    hits = []  # type: List[str]
    for ln_no, ln in enumerate(text.splitlines(), 1):
        for pat in TEMPLATE_OUTBOUND_PATTERNS:
            if pat in ln:
                hits.append(f"{ln_no}:{pat}")
        if TEMPLATE_OUTBOUND_SECTION_RE.search(ln):
            hits.append(f"{ln_no}:§节号引用")
    return hits


def check_template_no_outbound_refs(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """references/agents-md-template.md 不含任何指向 skill 仓的出边引用（0.33.0+）。

    模板随 init 拷贝进每个 wiki 成为 AGENTS.md——wiki 侧 agent 读不到 skill 仓，模板内
    一切 `wiki-spec.md` / `page-templates.md` / `lint-checklist.md` / `SKILL.md` /
    `references/` / 阿拉伯数字 §节号 引用都是死指针（零白名单，含 provenance 声明也不得
    携带——0.33.0 起全部改写为自包含措辞）。skill 仓内文件 → 模板 单向引用由本 check
    机械强制；对每个 wiki 报告同一结果（模板是全局文件），违反时 error 逼 skill 侧修复。
    """
    out = {"passed": True, "severity": "error", "file": "references/agents-md-template.md"}  # type: Dict[str, object]
    template = _read_text(Path(__file__).resolve().parent.parent / "references" / "agents-md-template.md")
    if template is None:
        out["passed"] = None
        out["skipped"] = "references/agents-md-template.md 未找到（无法模板自检）"
        return out
    hits = _scan_template_outbound_refs(template)
    if hits:
        out["passed"] = False
        out["expected"] = "模板不含任何指向 skill 仓的引用（自包含措辞；spec / SKILL.md 单向指入模板）"
        out["actual"] = "出边引用: " + "; ".join(hits[:8])
    return out


def check_gitignore_external_track(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """.gitignore 含 raw/external/* 排除 + !raw/external/.symlink-anchor.toml 跟踪"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": ".gitignore",
    }
    text = _read_text(wiki_root / ".gitignore")
    if text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = ".gitignore 不存在"
        return out

    has_exclude = False
    has_track_toml = False
    has_legacy_json = False
    for line in text.splitlines():
        if GITIGNORE_EXCLUDE_EXTERNAL_RE.match(line):
            has_exclude = True
        if GITIGNORE_TRACK_TOML_RE.match(line):
            has_track_toml = True
        if GITIGNORE_TRACK_LEGACY_RE.match(line):
            has_legacy_json = True

    if has_legacy_json:
        out["passed"] = False  # type: ignore
        out["actual"] = "残留旧 `!raw/external/**/.symlink-anchor.json` 跟踪规则（0.17.0+ 退役）"
        out["expected"] = "!raw/external/.symlink-anchor.toml"
        out["rule_ref"] = "wiki-spec.md §13.6 迁移"
        return out
    if not has_exclude:
        out["passed"] = False  # type: ignore
        out["actual"] = "缺 `raw/external/*` 排除规则"
        out["expected"] = "raw/external/*\\n!raw/external/.symlink-anchor.toml"
        return out
    if not has_track_toml:
        out["passed"] = False  # type: ignore
        out["actual"] = "缺 `!raw/external/.symlink-anchor.toml` 跟踪规则"
        out["expected"] = "!raw/external/.symlink-anchor.toml"
        return out
    return out


def check_symlink_anchor_toml_schema(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """.symlink-anchor.toml（若存在）合法 + 必填字段齐 + git 身份字段可选"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": f"raw/{EXTERNAL_SUBDIR}/{ANCHOR_FILENAME}",
    }
    anchor_path = wiki_root / "raw" / EXTERNAL_SUBDIR / ANCHOR_FILENAME
    if not anchor_path.exists():
        out["passed"] = None  # type: ignore
        out["skipped"] = "anchor 文件不存在（external/ 无 symlink 时可不建）"
        return out

    entries = _parse_anchor_minimal(anchor_path)
    if entries is None:
        out["passed"] = False  # type: ignore
        out["actual"] = "TOML 解析失败 / 无有效 [[entry]] / 必填字段缺失"
        out["expected"] = (
            "schema_version = 1（顶层）+ 至少 1 个 [[entry]]（每 entry 含 symlink/target/captured_at/kind='external-repo'）"
        )
        return out

    bad_entries = []  # type: List[str]
    for entry in entries:
        sym = entry.get("symlink", "<no-symlink>")
        target = entry.get("target", "")
        # 必填字段：parse 函数已保证 symlink/target/captured_at 非空 + kind='external-repo'
        # 此处额外核对 symlink 命名规则 + target 非空
        if not SOURCE_NAME_RE.match(sym):
            bad_entries.append(f"{sym}: 不合 kebab-case")
        if not target:
            bad_entries.append(f"{sym}: target 字段空")
    if bad_entries:
        out["passed"] = False  # type: ignore
        out["actual"] = "; ".join(bad_entries)
        out["expected"] = "每 entry symlink 合 `^[a-z0-9][a-z0-9-]*$` + target 非空"
        return out
    return out


def check_symlink_anchor_toml_symlink_matches(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """anchor entry ↔ external/ 顶层 symlink 双向匹配"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": f"raw/{EXTERNAL_SUBDIR}/",
    }
    anchor_path = wiki_root / "raw" / EXTERNAL_SUBDIR / ANCHOR_FILENAME
    if not anchor_path.exists():
        out["passed"] = None  # type: ignore
        out["skipped"] = "anchor 文件不存在"
        return out

    external_dir = wiki_root / "raw" / EXTERNAL_SUBDIR
    if not external_dir.is_dir():
        out["passed"] = None  # type: ignore
        out["skipped"] = "raw/external/ 目录不存在"
        return out

    entries = _parse_anchor_minimal(anchor_path)
    if entries is None:
        # schema check 已报，此处跳过避免重复（passed=None）
        out["passed"] = None  # type: ignore
        out["skipped"] = "anchor 解析失败（已被 #3 报）"
        return out

    entry_symlinks = {e["symlink"] for e in entries if e.get("symlink")}
    real_symlinks = {p.name for p in external_dir.iterdir() if p.is_symlink()} if external_dir.is_dir() else set()

    orphan_entry = sorted(entry_symlinks - real_symlinks)  # anchor 有 entry 但 symlink 缺
    orphan_symlink = sorted(real_symlinks - entry_symlinks)  # symlink 有但 anchor 无 entry

    if orphan_entry or orphan_symlink:
        out["passed"] = False  # type: ignore
        out["actual"] = (f"anchor 缺 symlink: {orphan_entry}; " if orphan_entry else "") + (
            f"symlink 缺 entry: {orphan_symlink}" if orphan_symlink else ""
        )
        out["expected"] = "anchor [[entry]].symlink 与 external/ 顶层 symlink 一一对应"
        return out
    return out


def check_symlink_anchor_flat(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """external/ 不存在 <source-name>/ 子目录（0.17.0+ 扁平）"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": f"raw/{EXTERNAL_SUBDIR}/",
    }
    external_dir = wiki_root / "raw" / EXTERNAL_SUBDIR
    if not external_dir.is_dir():
        out["passed"] = None  # type: ignore
        out["skipped"] = "raw/external/ 目录不存在"
        return out

    legacy_subdirs = []  # type: List[str]
    legacy_anchor_json = []  # type: List[str]
    for p in sorted(external_dir.iterdir()):
        # 实际子目录（非 symlink 跟随）= legacy 0.16.0- 形态
        if p.is_dir() and not p.is_symlink():
            legacy_subdirs.append(p.name + "/")
            # 子目录内若还有 .symlink-anchor.json，则更明确的标志
            if (p / ".symlink-anchor.json").exists():
                legacy_anchor_json.append(str(p.name) + "/.symlink-anchor.json")
        elif p.name == ".symlink-anchor.json" and not p.is_symlink():
            # 旧 anchor 文件直接放 external/ 顶层（变体，不规范）
            legacy_anchor_json.append(p.name)

    if legacy_subdirs or legacy_anchor_json:
        out["passed"] = False  # type: ignore
        msg_parts = []  # type: List[str]
        if legacy_subdirs:
            msg_parts.append(f"legacy 子目录: {legacy_subdirs}")
        if legacy_anchor_json:
            msg_parts.append(f"legacy anchor 文件: {legacy_anchor_json}")
        out["actual"] = "; ".join(msg_parts)
        out["expected"] = "扁平布局: symlink + .symlink-anchor.toml 直接在 external/ 顶层"
        return out
    return out


def check_index_md_categories(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """wiki/index.md 含 5 类别标题（顺序可调）"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "warn",
        "file": "wiki/index.md",
    }
    text = _read_text(wiki_root / "wiki" / "index.md")
    if text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "wiki/index.md 不存在"
        return out
    found = set()
    for line in text.splitlines():
        m = INDEX_CATEGORY_RE.match(line)
        if m:
            name = m.group(1).strip()
            if name in ("Entities", "Concepts", "Sources", "Comparisons", "Syntheses"):
                found.add(name)
    expected = {"Entities", "Concepts", "Sources", "Comparisons", "Syntheses"}
    missing = sorted(expected - found)
    if missing:
        out["passed"] = False  # type: ignore
        out["actual"] = f"缺类别: {missing}"
        out["expected"] = "5 类别齐全 (Entities / Concepts / Sources / Comparisons / Syntheses)"
        return out
    return out


def check_memory_index_no_frontmatter(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """MEMORY/MEMORY.md 不带 YAML frontmatter"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": f"{MEMORY_SUBDIR}/MEMORY.md",
    }
    text = _read_text(wiki_root / MEMORY_SUBDIR / "MEMORY.md")
    if text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "MEMORY/MEMORY.md 不存在"
        return out
    # YAML frontmatter = 文件首行 `---` 紧跟块再以 `---` 闭合
    if YAML_FRONT_MATTER_RE.match(text):
        out["passed"] = False  # type: ignore
        out["actual"] = "文件以 `---` 起始（YAML frontmatter）"
        out["expected"] = "无 frontmatter（索引文件）"
        return out
    return out


def check_memory_entries_indexed(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """MEMORY/*.md 每条在 MEMORY.md 索引列出"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": f"{MEMORY_SUBDIR}/",
    }
    mem_dir = wiki_root / MEMORY_SUBDIR
    if not mem_dir.is_dir():
        out["passed"] = None  # type: ignore
        out["skipped"] = "MEMORY/ 目录不存在"
        return out
    memory_md_text = _read_text(mem_dir / "MEMORY.md")
    if memory_md_text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "MEMORY/MEMORY.md 不存在"
        return out

    # 收集 MEMORY/ 下除 MEMORY.md 外所有 .md
    memory_entries = [p.name for p in sorted(mem_dir.glob("*.md")) if p.name != "MEMORY.md"]
    if not memory_entries:
        # 无经验条目 → 跳过；纯索引文件不算违规
        out["passed"] = None  # type: ignore
        out["skipped"] = "MEMORY/ 无经验条目"
        return out

    missing = []  # type: List[str]
    for entry in memory_entries:
        # 索引行匹配：以 stem 形式出现即可（链接 / slug / 路径均可）
        stem = entry[: -len(".md")] if entry.endswith(".md") else entry
        if (stem) not in memory_md_text:
            missing.append(entry)
    if missing:
        out["passed"] = False  # type: ignore
        out["actual"] = f"未索引: {missing}"
        out["expected"] = "MEMORY/MEMORY.md 含 `- [slug](slug.md)` 或 slug 字面量"
        return out
    return out


def check_log_md_format(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """wiki/log.md 每行匹配严格格式（仅 ## 一级 heading 行）"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": "wiki/log.md",
    }
    text = _read_text(wiki_root / "wiki" / "log.md")
    if text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "wiki/log.md 不存在"
        return out
    bad_lines = []  # type: List[int]
    for i, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        # 仅检查 ## 一级 heading 行（与 lint_wiki.py check_log_format 同口径；
        # spec §4 条目正则即以 ## 起头）；其它行（续段落 / 描述）允许
        if line.lstrip().startswith("## "):
            if not LOG_LINE_RE.match(line):
                bad_lines.append(i)
    if bad_lines:
        out["passed"] = False  # type: ignore
        out["actual"] = f"不合规行: {bad_lines[:5]}{'... (前 5 行)' if len(bad_lines) > 5 else ''}"
        out["expected"] = "每行匹配 `^## [YYYY-MM-DD HH:MM] (ingest|query|lint|setup) | .+$`"
        return out
    return out


def _check_no_frontmatter(file_path: Path) -> Dict[str, object]:
    """共用：检测文件首部是否存在 YAML frontmatter"""
    rel = file_path.name
    out = {  # type: Dict[str, object]
        "passed": True,
        "severity": "error",
        "file": rel,
    }
    text = _read_text(file_path)
    if text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = f"{rel} 不存在"
        return out
    if YAML_FRONT_MATTER_RE.match(text):
        out["passed"] = False  # type: ignore
        out["actual"] = "文件以 `---` 起始（YAML frontmatter）"
        out["expected"] = "无 frontmatter"
        return out
    return out


def check_scripts_md_no_frontmatter(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """scripts/SCRIPTS.md 不带 YAML frontmatter"""
    result = _check_no_frontmatter(wiki_root / "scripts" / "SCRIPTS.md")
    result["file"] = "scripts/SCRIPTS.md"
    return result


def check_tags_md_no_frontmatter(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """wiki/tags.md 不带 YAML frontmatter"""
    result = _check_no_frontmatter(wiki_root / "wiki" / "tags.md")
    result["file"] = "wiki/tags.md"
    return result


# 读取契约 co-location：这 6 字段 = workspace skill scan 读 wiki_metadata.toml 的字段子集。
# SKILL 将来新读某字段，必须同步加到这里 + wiki-spec §1.1「skill 读取的字段」——两处一致，
# wiki-metadata-reads-satisfied gate 才有效（清单漂移 = check 不报警 = gate 失效）。
WIKI_METADATA_REQUIRED_FIELDS = ("name", "topic", "display_name", "description", "tags", "created_at")
WIKI_METADATA_KEY_RE = re.compile(r"^[ \t]*([a-z_]+)[ \t]*=", re.MULTILINE)


def check_wiki_metadata_reads_satisfied(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """wiki_metadata.toml 含 SKILL scan 读取的 6 字段（读取契约自洽）。

    CLI `wiki add` 必落盘 wiki_metadata.toml；缺失即产物不完整 → fail（不 skip）。
    复用 minimal TOML key=value 风格解析，不引入 tomli。
    """
    out = {"passed": True, "severity": "error", "file": "wiki_metadata.toml"}  # type: Dict[str, object]
    text = _read_text(wiki_root / "wiki_metadata.toml")
    if text is None:
        out["passed"] = False  # type: ignore
        out["expected"] = "wiki_metadata.toml 存在（CLI wiki add 必落盘）含 6 读取字段"
        out["actual"] = "wiki_metadata.toml 不存在"
        return out
    found = {m.group(1) for m in WIKI_METADATA_KEY_RE.finditer(text)}
    missing = [f for f in WIKI_METADATA_REQUIRED_FIELDS if f not in found]
    if missing:
        out["passed"] = False  # type: ignore
        out["expected"] = "wiki_metadata.toml 含 6 读取字段：" + " / ".join(WIKI_METADATA_REQUIRED_FIELDS)
        out["actual"] = "缺：" + " / ".join(missing)
    return out


# ============================================================================
# 骨架字段级比对——gitignore 读 references/fixtures/（canonical 无 .gitignore）；
# 其余骨架信号（frontmatter 键 / H1 / 说明块 / ## 标题）硬编码在 SKELETON_SPECS
# 描述符里（与 canonical/*.md 一致），改 canonical 时手工同步描述符。
# 纯骨架件（.gitignore/tags.md/SCRIPTS.md/MEMORY.md）全字段骨架比对；成长件
# （index.md/log.md）只比结构必填（frontmatter 键 + H1 + 说明块），不动成长内容。
# 只有 index.md.txt/log.md.txt 带占位符，故其余文件 canonical==fixtures 字节相同。
# ============================================================================


def _fixtures_dir() -> Path:
    """references/fixtures/（带占位符模板；canonical 无 .gitignore，gitignore 走此）。"""
    return Path(__file__).resolve().parent.parent / "references" / "fixtures"


def _load_fixture_text(name: str) -> Optional[str]:
    """读 references/fixtures/<name>；失败返 None。"""
    return _read_text(_fixtures_dir() / name)


def _parse_frontmatter_keys(text: str) -> List[str]:
    """提取首部 YAML frontmatter 的字段名（顺序保留）；无 frontmatter 返 []。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not m:
        return []  # type: ignore
    keys = []  # type: List[str]
    for line in m.group(1).splitlines():
        km = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:", line)
        if km:
            keys.append(km.group(1))
    return keys


def _parse_gitignore_sections(text: str) -> Dict[str, List[str]]:
    """解析 .gitignore 段：返 {段注释文本: [规则行]}。

    段注释 = ``#`` 开头行；其后非注释非空行归属该段，直到下一个 ``#``。
    """
    sections = {}  # type: Dict[str, List[str]]
    current = None  # type: Optional[str]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            current = stripped
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(stripped)
    return sections


def _check_skeleton_signals(wiki_text: str, signals: Dict[str, object]) -> List[str]:
    """对照 signals 检查 wiki_text；返缺失项列表（空 = 全 pass）。

    signals 支持的 key（任选组合）：
      - ``frontmatter_keys``: List[str] — wiki frontmatter 键集必须 ⊇
      - ``h1``: str — wiki 必须含该字面 H1 行（固定标题，如 ``# Tags``）
      - ``h1_pattern``: str(regex) — wiki 首个 H1 必须匹配（变体标题，如 index.md ``# <topic> Wiki``）
      - ``blockquote``: bool — wiki 必须含至少一行 ``>`` 引用（说明块）
      - ``section_headings``: List[str] — wiki 必须含这些 ``##`` 标题
      - ``gitignore_section_structure``: bool — 对照 fixtures/gitignore.txt，
        非 external 段齐全 + 每段 ≥1 规则（容忍用户删某条编辑器规则，不绑死具体行）
    """
    missing = []  # type: List[str]
    lines = wiki_text.splitlines()

    if "frontmatter_keys" in signals:
        actual = set(_parse_frontmatter_keys(wiki_text))
        for k in signals["frontmatter_keys"]:  # type: ignore
            if k not in actual:
                missing.append(f"frontmatter 缺字段 `{k}`")

    if "h1" in signals:
        target = signals["h1"]  # type: ignore
        if not any(ln.strip() == target for ln in lines):
            missing.append(f"缺 H1 `{target}`")

    if "h1_pattern" in signals:
        pat = re.compile(signals["h1_pattern"])  # type: ignore
        h1_lines = [ln for ln in lines if ln.lstrip().startswith("# ")]
        if not any(pat.match(ln.strip()) for ln in h1_lines):
            missing.append("H1 不匹配 `{}`".format(signals["h1_pattern"]))  # type: ignore

    if signals.get("blockquote"):
        if not any(ln.lstrip().startswith(">") for ln in lines):
            missing.append("缺说明块（`>` 引用行）")

    if "section_headings" in signals:
        # 任意 H2-H6 heading（`## ` / `### ` / `#### ` / ...）——段标题可能在 §一 的子节里
        actual_secs = {ln.strip() for ln in lines if re.match(r"^#{2,6} ", ln)}
        for s in signals["section_headings"]:  # type: ignore
            if s not in actual_secs:
                missing.append(f"缺段标题 `{s}`")

    if signals.get("gitignore_section_structure"):
        fixture_text = _load_fixture_text("gitignore.txt")
        if fixture_text is None:
            missing.append("fixtures/gitignore.txt 未找到（无法比对段结构）")
        else:
            expected_secs = _parse_gitignore_sections(fixture_text)
            actual_secs = _parse_gitignore_sections(wiki_text)
            # external 段由 gitignore-external-track-toml(error) 单独管，此处跳过
            for sec, _rules in expected_secs.items():
                if "raw/external" in sec or ".symlink-anchor" in sec:
                    continue
                if sec not in actual_secs:
                    missing.append(f".gitignore 缺段注释 `{sec}`")
                elif not actual_secs[sec]:
                    missing.append(f".gitignore 段 `{sec}` 下无规则行")
    return missing


# -- 骨架 check 描述符（id/severity/wiki_path/rule_ref/desc/signals）--
# wiki_path 相对 wiki 根；signals 见 _check_skeleton_signals 支持的 key。
SKELETON_SPECS = [
    {
        "id": "gitignore-init-rules-complete",
        "severity": "warn",
        "wiki_path": ".gitignore",
        "rule_ref": "wiki-spec.md §6",
        "desc": ".gitignore 含 OS/编辑器 + Obsidian + 临时文件 段（各 ≥1 规则；external 段由 gitignore-external-track-toml 单独查）",
        "signals": {"gitignore_section_structure": True},
    },
    {
        "id": "index-md-frontmatter-complete",
        "severity": "error",
        "wiki_path": "wiki/index.md",
        "rule_ref": "wiki-spec.md §3",
        "desc": "wiki/index.md frontmatter 含 6 必填键（title/type/okf_version/tags/created/updated）",
        "signals": {"frontmatter_keys": ["title", "type", "okf_version", "tags", "created", "updated"]},
    },
    {
        "id": "index-md-skeleton",
        "severity": "warn",
        "wiki_path": "wiki/index.md",
        "rule_ref": "wiki-spec.md §3",
        "desc": "wiki/index.md 含 H1（# <topic> Wiki）+ 说明块（> 引用）",
        "signals": {"h1_pattern": r"^# .+ Wiki$", "blockquote": True},
    },
    {
        "id": "log-md-frontmatter-complete",
        "severity": "error",
        "wiki_path": "wiki/log.md",
        "rule_ref": "wiki-spec.md §4",
        "desc": "wiki/log.md frontmatter 含 5 必填键（title/type/tags/created/updated）",
        "signals": {"frontmatter_keys": ["title", "type", "tags", "created", "updated"]},
    },
    {
        "id": "memory-index-skeleton",
        "severity": "warn",
        "wiki_path": "MEMORY/MEMORY.md",
        "rule_ref": "wiki-spec.md §5.1",
        "desc": "MEMORY/MEMORY.md 含 H1（# MEMORY）+ 说明块 + ## 索引",
        "signals": {"h1": "# MEMORY", "blockquote": True, "section_headings": ["## 索引"]},
    },
    {
        "id": "scripts-md-skeleton",
        "severity": "warn",
        "wiki_path": "scripts/SCRIPTS.md",
        "rule_ref": "wiki-spec.md §14",
        "desc": "scripts/SCRIPTS.md 含 H1（# Scripts）+ 说明块 + ## 索引",
        "signals": {"h1": "# Scripts", "blockquote": True, "section_headings": ["## 索引"]},
    },
    {
        "id": "tags-md-skeleton",
        "severity": "warn",
        "wiki_path": "wiki/tags.md",
        "rule_ref": "wiki-spec.md §9.1",
        "desc": "wiki/tags.md 含 H1（# Tags）+ 说明块（无 ## 索引——tags 直接 bullet 列表）",
        "signals": {"h1": "# Tags", "blockquote": True},
    },
]


def _make_skeleton_check(spec: Dict[str, object]) -> Callable[[Path, Dict[str, str]], Dict[str, object]]:
    """按 SKELETON_SPECS 描述符生成一条骨架 check 函数（照搬 _check_no_frontmatter 共享模式）。"""
    wiki_path = spec["wiki_path"]  # type: ignore
    severity = spec["severity"]  # type: ignore
    rule_ref = spec["rule_ref"]  # type: ignore
    sigs = spec["signals"]  # type: ignore

    def _check(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
        out = {"passed": True, "severity": severity, "file": wiki_path}  # type: Dict[str, object]
        wiki_text = _read_text(wiki_root / wiki_path)
        if wiki_text is None:
            out["passed"] = None
            out["skipped"] = f"{wiki_path} 不存在"
            return out
        missing = _check_skeleton_signals(wiki_text, sigs)
        if missing:
            out["passed"] = False
            out["expected"] = f"骨架信号对齐 references/canonical（或 fixtures/gitignore.txt）；详见 {rule_ref}"
            out["actual"] = "; ".join(missing)
        return out

    _check.__name__ = "check_" + str(spec["id"]).replace("-", "_")  # type: ignore
    return _check


# 骨架 check 并入 CHECK_REGISTRY（runtime 顺序 = 输出顺序，排在原 13 条之后）
CHECK_REGISTRY.extend(
    {
        "id": s["id"],
        "severity": s["severity"],
        "rule_ref": s["rule_ref"],
        "desc": s["desc"],
    }
    for s in SKELETON_SPECS
)


# ============================================================================
# 调度
# ============================================================================

CHECK_FUNCTIONS = [
    ("agents-version-is-current", check_agents_version),
    ("agents-md-template-sync", check_agents_md_template_sync),
    ("template-no-outbound-refs", check_template_no_outbound_refs),
    ("gitignore-external-track-toml", check_gitignore_external_track),
    ("symlink-anchor-toml-schema", check_symlink_anchor_toml_schema),
    ("symlink-anchor-toml-symlink-matches", check_symlink_anchor_toml_symlink_matches),
    ("symlink-anchor-flat-not-legacy", check_symlink_anchor_flat),
    ("index-md-categories-stable", check_index_md_categories),
    ("memory-index-no-frontmatter", check_memory_index_no_frontmatter),
    ("memory-entries-indexed", check_memory_entries_indexed),
    ("log-md-format-strict", check_log_md_format),
    ("scripts-md-no-frontmatter", check_scripts_md_no_frontmatter),
    ("tags-md-no-frontmatter", check_tags_md_no_frontmatter),
    ("wiki-metadata-reads-satisfied", check_wiki_metadata_reads_satisfied),
] + [(s["id"], _make_skeleton_check(s)) for s in SKELETON_SPECS]


def run_checks(wiki_root: Path, target_spec: Optional[str]) -> Dict[str, object]:
    """跑全部 check；返 { wiki_root, target_spec, checks: [...], summary: {...} }"""
    info = {"wiki_root": str(wiki_root), "target_spec": target_spec or ""}
    checks_out = []  # type: List[Dict[str, object]]
    summary = {"error": 0, "warn": 0, "info": 0, "pass": 0, "skip": 0}  # type: Dict[str, int]
    for check_id, fn in CHECK_FUNCTIONS:
        reg = next(c for c in CHECK_REGISTRY if c["id"] == check_id)
        result = fn(wiki_root, info)
        # 统一字段 schema
        passed = result.get("passed")  # type: Optional[bool]
        severity = reg["severity"]
        if passed is True:
            summary["pass"] += 1
        elif passed is False:
            if severity == "error":
                summary["error"] += 1
            elif severity == "warn":
                summary["warn"] += 1
            else:
                summary["info"] += 1
        else:
            # passed is None → skipped
            summary["skip"] += 1
        entry = {
            "id": check_id,
            "file": result.get("file", ""),
            "passed": passed,
            "severity": severity,
            "rule_ref": reg["rule_ref"],
            "desc": reg["desc"],
            "expected": result.get("expected", ""),
            "actual": result.get("actual", ""),
            "skipped": result.get("skipped", ""),
            "comparison": result.get("comparison", ""),
        }
        checks_out.append(entry)
    return {
        "wiki_root": str(wiki_root),
        "target_spec": target_spec,
        "checks": checks_out,
        "summary": summary,
    }


def _format_human(report: Dict[str, object]) -> str:
    """人读报告（默认输出）。"""
    lines = []  # type: List[str]
    lines.append("=== Wiki fixtures 一致性检查 ===")
    lines.append(f"  wiki_root     : {report['wiki_root']}")
    lines.append(f"  target_spec   : {report['target_spec'] or '(未指定)'}")
    s = report["summary"]  # type: ignore
    lines.append(
        f"  error={s['error']} warn={s['warn']} info={s['info']} pass={s['pass']} skip={s['skip']}"  # type: ignore
    )
    lines.append("")
    for c in report["checks"]:  # type: ignore
        passed = c.get("passed")  # type: ignore
        cid = c["id"]  # type: ignore
        sev = c["severity"].upper()  # type: ignore
        fpath = c["file"]  # type: ignore
        if passed is True:
            tag = "✓"
        elif passed is False:
            tag = "✗"
        else:
            tag = "·"
        lines.append(f"[{tag}] [{sev}] {cid} ({fpath})")
        if c.get("rule_ref"):  # type: ignore
            lines.append(f"        规则: {c['rule_ref']}")  # type: ignore
        if passed is False:
            if c.get("expected"):  # type: ignore
                lines.append(f"        期望: {c['expected']}")  # type: ignore
            if c.get("actual"):  # type: ignore
                lines.append(f"        实际: {c['actual']}")  # type: ignore
        elif passed is None and c.get("skipped"):  # type: ignore
            lines.append(f"        skip: {c['skipped']}")  # type: ignore
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check_wiki_fixtures",
        description="检查已存在 wiki 的 fixtures 一致性（升级检查专用）",
    )
    parser.add_argument("wiki_root", nargs="?", help="wiki 根目录；默认从 $LLM_WIKI_ROOT 读")
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读 JSON 而不是人读报告",
    )
    parser.add_argument(
        "--target-spec",
        default=None,
        help="目标 wiki spec 版本（缺省读 SKILL.md metadata.wiki_spec_version）",
    )
    args = parser.parse_args()

    if args.wiki_root:
        wiki_root = Path(args.wiki_root).expanduser().resolve()
    elif os.environ.get(CL_LLM_WIKI_ROOT):
        wiki_root = Path(os.environ[CL_LLM_WIKI_ROOT]).expanduser().resolve()
    else:
        print("ERROR: 需提供 wiki_root 参数或设置 $LLM_WIKI_ROOT", file=sys.stderr)
        return 2

    if not wiki_root.is_dir():
        print(f"ERROR: {wiki_root} 不是目录", file=sys.stderr)
        return 2

    target_spec = args.target_spec or _skill_spec_version()

    report = run_checks(wiki_root, target_spec)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_human(report))

    # 退出码：error > warn > pass/skip
    s = report["summary"]  # type: ignore
    if s["error"] > 0:  # type: ignore
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
