#!/usr/bin/env python3
"""wiki_fixtures — wiki 约定文件的结构性字节合规检查（`llmw wiki check-fixtures`）。

只查结构；语义合并（字段升级 / 条目归并等）由 agent 走 upgrade plan 处理。
不写文件、不产 plan（plan 由 `lint --check-version --apply` 生成）。退出码 0/1/2 = pass / error fail / 运行错误。
新增 check：registry 加条目（骨架类并加 SKELETON_REGISTRY 描述符）。
"""

import difflib
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

# 常量 SSOT 在 _check_common / wiki_lint / log_format / external_anchor，import 不复制。
from llmw import WIKI_FORMAT_VERSION
from llmw import __version__ as CLI_VERSION
from llmw.config import wiki_templates_dir
from llmw.content._check_common import (
    SEMVER_RE,
)
from llmw.content._check_common import (
    compare_semver as _compare_semver,
)
from llmw.content._check_common import (
    print_rules as _print_rules,
)
from llmw.content._check_common import (
    read_text as _read_text,
)
from llmw.content._check_common import (
    scan_template_outbound_refs as _scan_template_outbound_refs,
)
from llmw.content.external_anchor import SOURCE_NAME_RE
from llmw.content.log_format import LOG_LINE_RE
from llmw.content.page_types import TYPE_TO_SECTION
from llmw.content.render import render_wiki_agents_md
from llmw.content.wiki_lint import (
    ANCHOR_FILENAME,
    EXTERNAL_SUBDIR,
    MEMORY_SUBDIR,
)
from llmw.errors import WikiMetadataCorrupt
from llmw.wiki import store as wiki_store

# -- 公开 check 注册表（顺序 = 输出顺序）--
# 每条: severity (error/warn)、rule_ref（指向 skill 文档段）、desc（人读摘要）
CHECK_REGISTRY = [
    {
        "id": "agents-version-is-current",
        "severity": "error",
        "file": "AGENTS.md",
        "rule_ref": "lint-workflow.md「调用方式」（--check-version wiki-format-version）",
        "desc": "AGENTS.md 末尾「当前配置」表 Wiki Format 版本行需与 --target-format 一致",
    },
    {
        "id": "agents-md-template-sync",
        "severity": "error",
        "file": "AGENTS.md",
        "rule_ref": "upgrade-workflow.md「职责切分」（agents-md-template-sync 修复走 upgrade --apply）",
        "desc": "AGENTS.md 与包内 agents-md-template.md 渲染稿字节一致（「当前配置」四变量替换后）；定制纪律应沉淀到 MEMORY/",
    },
    {
        "id": "template-no-outbound-refs",
        "severity": "error",
        "file": "AGENTS.md",
        "rule_ref": "<wiki-root>/AGENTS.md「本文件本身的纪律」节（含骨架所有权四分表）",
        "desc": "模板零出边引用——不得含 page-templates/lint-workflow/SKILL.md/references/yzr-llm-wiki-management/OKF/阿拉伯数字 §节号（wiki 侧读不到 skill 目录，指针全是死引用）",
    },
    {
        "id": "gitignore-external-track-toml",
        "severity": "error",
        "file": ".gitignore",
        "rule_ref": "external-repo.md「跨主机重建」",
        "desc": ".gitignore 含 `raw/external/*` 排除 + `!raw/external/.symlink-anchor.toml` 跟踪",
    },
    {
        "id": "symlink-anchor-toml-schema",
        "severity": "error",
        "file": "raw/external/.symlink-anchor.toml",
        "rule_ref": "external-repo.md「首次接入」",
        "desc": "raw/external/.symlink-anchor.toml（若存在）：合法 TOML + [[entry]] 数组 + 必填字段齐 + git 身份字段可选（schema 归 CLI 持有，`llmw wiki external` 子命令维护）",
    },
    {
        "id": "symlink-anchor-toml-symlink-matches",
        "severity": "error",
        "file": "raw/external/",
        "rule_ref": "external-repo.md「跨主机重建」（anchor 进 git 的 rationale + 扁平布局不变量）",
        "desc": "anchor 每个 [[entry]].symlink 对应 external/ 顶层同名 symlink；anchor 无对应 symlink / orphan symlink 一并检查",
    },
    {
        "id": "index-md-categories-stable",
        "severity": "warn",
        "file": "wiki/index.md",
        "rule_ref": "wiki/index.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/index.md 含 {} 类别标题 ({})".format(len(TYPE_TO_SECTION), " / ".join(TYPE_TO_SECTION.values())),
    },
    {
        "id": "memory-index-no-frontmatter",
        "severity": "error",
        "file": "MEMORY/MEMORY.md",
        "rule_ref": "MEMORY/MEMORY.md fixture header (wiki 实例内直接可读)",
        "desc": "MEMORY/MEMORY.md（索引）不带 YAML frontmatter（其 ## 索引 段条目随 AGENTS.md 顶部引用自动加载）",
    },
    {
        "id": "memory-entries-indexed",
        "severity": "error",
        "file": "MEMORY/",
        "rule_ref": "MEMORY/MEMORY.md fixture header (wiki 实例内直接可读)",
        "desc": "MEMORY/*.md（除 MEMORY.md）每条都在 MEMORY/MEMORY.md 索引中列出",
    },
    {
        "id": "log-md-format-strict",
        "severity": "error",
        "file": "wiki/log.md",
        "rule_ref": "wiki/log.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/log.md 每行匹配 `^## [YYYY-MM-DD HH:MM] (ingest|query|lint|setup) | .+$`（HH:MM 可选；老 wikis date-only 仍合法，宽容解析）",
    },
    {
        "id": "scripts-md-no-frontmatter",
        "severity": "error",
        "file": "scripts/SCRIPTS.md",
        "rule_ref": "scripts/SCRIPTS.md fixture header (wiki 实例内直接可读)",
        "desc": "scripts/SCRIPTS.md 不带 YAML frontmatter",
    },
    {
        "id": "tags-md-no-frontmatter",
        "severity": "error",
        "file": "wiki/tags.md",
        "rule_ref": "wiki/tags.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/tags.md 不带 YAML frontmatter",
    },
    {
        "id": "wiki-metadata-reads-satisfied",
        "severity": "error",
        "file": "wiki_metadata.toml",
        "rule_ref": "lint-workflow.md「lint 的边界」（fixtures 边界，check 清单由 CLI 注册表承载）",
        "desc": "wiki_metadata.toml 含 SKILL scan 读取的 6 字段：name / topic / display_name / description / tags / created_at",
    },
    {
        "id": "opencode-instructions-sync",
        "severity": "error",
        "file": "agents-md-template.md",
        "rule_ref": "AGENTS.md 顶层 @import 链与 opencode Instructions 配置一一对应（CLI 包自检；不一致 = 升级 / 重装 llmw）",
        "desc": "AGENTS.md 模板顶层 @import 引用与 opencode 路径写入的 instructions 列表一一对应（opencode 不解析 @import，用 instructions 字段替代）",
    },
]

# -- 解析用正则 --
AGENTS_FORMAT_ROW_RE = re.compile(r"^\s*\|\s*Wiki Format 版本\s*\|\s*([^|]+?)\s*\|")
INDEX_CATEGORY_RE = re.compile(r"^## (.+)$")
GITIGNORE_TRACK_TOML_RE = re.compile(r"^!\s*raw/external/\.symlink-anchor\.toml\s*(#.*)?$")
GITIGNORE_EXCLUDE_EXTERNAL_RE = re.compile(r"^\s*raw/external/?\*?\s*(#.*)?$")
YAML_FRONT_MATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _skill_format_version() -> Optional[str]:
    """wiki format 版本（SSOT = llmw.WIKI_FORMAT_VERSION 包内常量）。"""
    return WIKI_FORMAT_VERSION


def _parse_anchor_minimal(anchor_path: Path) -> Optional[List[Dict[str, str]]]:
    """最小 TOML 解析（[[entry]] + 双引号标量）；captured_at 空串过滤（比 external_anchor.load 严）。

    返回 List[Dict] 或 None（缺失 / 解析失败 / 无有效 entry）。
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


# 各 check 函数：返 dict 至少含 "passed"；False 时尽量附 "expected"/"actual"


def check_agents_version(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """AGENTS.md 末尾「当前配置」表 `Wiki Format 版本` 字段与 --target-format 一致"""
    target_format = info.get("target_format") or None
    out = {  # type: Dict[str, object]
        "passed": True,
        "file": "AGENTS.md",
    }
    if target_format is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "--target-format 未提供；跳过版本对齐检查"
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
            m = AGENTS_FORMAT_ROW_RE.match(line)
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
        out["actual"] = "(无法解析末尾「当前配置」表 `Wiki Format 版本` 字段)"
        out["expected"] = target_format
        return out
    out["file"] = source_file  # type: ignore
    cmp = _compare_semver(found_version, target_format)
    if cmp != "equal":
        out["passed"] = False  # type: ignore
        out["actual"] = found_version
        out["expected"] = target_format
        out["comparison"] = cmp  # type: ignore
    return out


def check_agents_md_template_sync(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """AGENTS.md 与 render.py 渲染稿字节一致（变量 SSOT = metadata + 版本常量）。

    渲染输入不从旧文件反提取；定制纪律沉淀 MEMORY/（否则字节不比）。与
    agents-version-is-current 的冗余是 benign——两者都推荐 upgrade，一次修复。
    """
    out = {"passed": True, "file": "AGENTS.md"}  # type: Dict[str, object]
    wiki_text = _read_text(wiki_root / "AGENTS.md")
    if wiki_text is None:
        out["passed"] = None
        out["skipped"] = "AGENTS.md 不存在"
        return out

    # 变量 SSOT: 从 wiki_metadata.toml 读 topic/created_at（不从 AGENTS.md「当前配置」表反提取）
    try:
        meta = wiki_store.load(wiki_root)
    except WikiMetadataCorrupt as e:
        out["passed"] = None  # type: ignore
        out["skipped"] = f"wiki_metadata.toml 解析失败, 无法派生渲染变量: {e}"
        return out
    except OSError as e:
        out["passed"] = None  # type: ignore
        out["skipped"] = f"wiki_metadata.toml 不可读: {e}"
        return out

    if not meta.topic or not meta.created_at:
        out["passed"] = False  # type: ignore
        out["expected"] = "wiki_metadata.toml 含 topic 与 created_at（渲染变量 SSOT）"
        out["actual"] = f"topic={meta.topic!r}, created_at={meta.created_at!r}"
        return out

    # created_at 形如 "2026-08-19T15:23:45Z" — ISO 8601; 模板 SETUP_DATE 占位符粒度
    # 为 YYYY-MM-DD HH:MM（与 init_wiki.today 一致）
    ca = meta.created_at.replace("T", " ")
    setup_date = ca[:16] if len(ca) >= 16 else ca

    rendered = render_wiki_agents_md(
        topic=meta.topic,
        setup_date=setup_date,
        cli_version=CLI_VERSION,
        format_version=WIKI_FORMAT_VERSION,
    )

    if rendered != wiki_text:
        diff = list(difflib.unified_diff(wiki_text.splitlines(), rendered.splitlines(), lineterm="", n=0))
        changed = [ln for ln in diff if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
        preview = "; ".join(ln[:60] for ln in changed[:4])
        out["passed"] = False  # type: ignore
        out["expected"] = "AGENTS.md 与 CLI 渲染稿字节一致（定制纪律沉淀到 MEMORY/，不进本文件）"
        out["actual"] = f"{len(changed)} 行与渲染稿不一致（首处: {preview}）" if preview else "与渲染稿不一致"
    return out


# 模板零出边引用（模板 = 引用图汇点）：指向 skill 目录的指针对 wiki 侧 agent 是死指针
TEMPLATE_OUTBOUND_PATTERNS = (
    "page-templates.md",
    "lint-workflow.md",
    "SKILL.md",
    "references/",
    "yzr-llm-wiki-management",
    "OKF",
)


def check_template_no_outbound_refs(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """包内 agents-md-template.md 零出边引用（零白名单；违反 → skill 侧修复）。"""
    out = {"passed": True, "file": "agents-md-template.md"}  # type: Dict[str, object]
    template = _read_text(wiki_templates_dir() / "agents-md-template.md")
    if template is None:
        out["passed"] = None
        out["skipped"] = "agents-md-template.md 未找到（无法模板自检）"
        return out
    hits = _scan_template_outbound_refs(template, TEMPLATE_OUTBOUND_PATTERNS)
    if hits:
        out["passed"] = False
        out["expected"] = "模板不含任何指向 skill 目录的引用（自包含措辞；SKILL.md 单向指入模板）"
        out["actual"] = "出边引用: " + "; ".join(hits[:8])
    return out


def check_gitignore_external_track(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """.gitignore 含 raw/external/* 排除 + !raw/external/.symlink-anchor.toml 跟踪"""
    out = {  # type: Dict[str, object]
        "passed": True,
        "file": ".gitignore",
    }
    text = _read_text(wiki_root / ".gitignore")
    if text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = ".gitignore 不存在"
        return out

    has_exclude = False
    has_track_toml = False
    for line in text.splitlines():
        if GITIGNORE_EXCLUDE_EXTERNAL_RE.match(line):
            has_exclude = True
        if GITIGNORE_TRACK_TOML_RE.match(line):
            has_track_toml = True

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
    real_symlinks = {p.name for p in external_dir.iterdir() if p.is_symlink()}

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


def check_index_md_categories(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """wiki/index.md 含全部类别标题（顺序可调）"""
    out = {  # type: Dict[str, object]
        "passed": True,
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
            if name in set(TYPE_TO_SECTION.values()):
                found.add(name)
    expected = set(TYPE_TO_SECTION.values())
    missing = sorted(expected - found)
    if missing:
        out["passed"] = False  # type: ignore
        out["actual"] = f"缺类别: {missing}"
        out["expected"] = "{} 类别齐全 ({})".format(len(TYPE_TO_SECTION), " / ".join(TYPE_TO_SECTION.values()))
        return out
    return out


def check_memory_index_no_frontmatter(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """MEMORY/MEMORY.md 不带 YAML frontmatter"""
    out = {  # type: Dict[str, object]
        "passed": True,
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
        # 仅检查 ## 一级 heading 行（与 wiki_lint.check_log_format 同口径；
        # 条目正则即以 ## 起头）；其它行（续段落 / 描述）允许
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
# SKILL 将来新读某字段，必须同步加到这里——清单完整（wiki-metadata-reads-satisfied
# 检查）才有效（清单漂移 = check 不报警 = gate 失效）。
WIKI_METADATA_REQUIRED_FIELDS = ("name", "topic", "display_name", "description", "tags", "created_at")
WIKI_METADATA_KEY_RE = re.compile(r"^[ \t]*([a-z_]+)[ \t]*=", re.MULTILINE)


def check_wiki_metadata_reads_satisfied(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """wiki_metadata.toml 含 SKILL scan 读取的 6 字段（读取契约自洽）。

    CLI `wiki add` 必落盘 wiki_metadata.toml；缺失即产物不完整 → fail（不 skip）。
    复用 minimal TOML key=value 风格解析，不引入 tomli。
    """
    out = {"passed": True, "file": "wiki_metadata.toml"}  # type: Dict[str, object]
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


# opencode instructions 同步：AGENTS.md 模板的顶层 @import 引用必须与
# overlay_opencode.INSTRUCTION_FILES 一一对应——opencode 不解析 @import，
# 用 opencode.json 的 instructions 字段替代（官方推荐），两份数据必须同步。
_TEMPLATE_AT_IMPORT_RE = re.compile(r"^@(\S+)\s*$", re.MULTILINE)


def _scan_template_at_imports(template: str) -> List[str]:
    """扫模板文本中的顶层 @path 引用（整行 `@path`，排除行内 @提及）。"""
    return _TEMPLATE_AT_IMPORT_RE.findall(template)


def check_opencode_instructions_sync(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """包内 agents-md-template.md 的顶层 @import 与 overlay_opencode.INSTRUCTION_FILES 同步。

    opencode 不解析 AGENTS.md 的 @path 引用，用 opencode.json 的 instructions 字段替代
    （官方 config.mdx "Instructions" 小节）。overlay_opencode.INSTRUCTION_FILES 是 opencode
    路径写入的 instructions 列表，必须与模板顶层 @import 一一对应——否则 opencode 路径
    上下文缺失或冗余。两份数据各自是各自模块的 SSOT，由本 check 机械强制。
    """
    from llmw.models.overlay_opencode import INSTRUCTION_FILES

    out = {"passed": True, "file": "agents-md-template.md"}  # type: Dict[str, object]
    template = _read_text(wiki_templates_dir() / "agents-md-template.md")
    if template is None:
        out["passed"] = None
        out["skipped"] = "agents-md-template.md 未找到（无法自检）"
        return out
    template_refs = _scan_template_at_imports(template)
    expected = list(INSTRUCTION_FILES)
    if template_refs == expected:
        return out
    out["passed"] = False  # type: ignore
    out["expected"] = "模板顶层 @import 应为 " + repr(expected)
    out["actual"] = "模板顶层 @import = " + repr(template_refs)
    return out


# 骨架字段级比对：信号硬编码在 SKELETON_REGISTRY（与包内 fixtures/*.txt 一致，
# 改 fixtures 时手工同步）；只有 index.md.txt / log.md.txt 带占位符。


def _fixtures_dir() -> Path:
    """包内 fixtures/（带占位符模板；gitignore 走此）。"""
    return wiki_templates_dir() / "fixtures"


def _load_fixture_text(name: str) -> Optional[str]:
    """读包内 fixtures/<name>；失败返 None。"""
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

    signals key（任选组合）：frontmatter_keys / h1 / h1_pattern / blockquote /
    section_headings / gitignore_section_structure。
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
        # 任意 H2-H6 heading（`## ` / `### ` / `#### ` / ...）——段标题可能在节内子节里
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
SKELETON_REGISTRY = [
    {
        "id": "gitignore-init-rules-complete",
        "severity": "warn",
        "wiki_path": ".gitignore",
        "rule_ref": ".gitignore fixture (wiki 实例内直接可读)",
        "desc": ".gitignore 含 OS/编辑器 + Obsidian + 临时文件 段（各 ≥1 规则；external 段由 gitignore-external-track-toml 单独查）",
        "signals": {"gitignore_section_structure": True},
    },
    {
        "id": "index-md-frontmatter-complete",
        "severity": "error",
        "wiki_path": "wiki/index.md",
        "rule_ref": "wiki/index.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/index.md frontmatter 含 6 必填键（title/type/okf_version/tags/created/updated）",
        "signals": {"frontmatter_keys": ["title", "type", "okf_version", "tags", "created", "updated"]},
    },
    {
        "id": "index-md-skeleton",
        "severity": "warn",
        "wiki_path": "wiki/index.md",
        "rule_ref": "wiki/index.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/index.md 含 H1（# <topic> Wiki）+ 说明块（> 引用）",
        "signals": {"h1_pattern": r"^# .+ Wiki$", "blockquote": True},
    },
    {
        "id": "log-md-frontmatter-complete",
        "severity": "error",
        "wiki_path": "wiki/log.md",
        "rule_ref": "wiki/log.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/log.md frontmatter 必填键齐全",
        "signals": {"frontmatter_keys": ["title", "type", "tags", "created", "updated"]},
    },
    {
        "id": "log-md-skeleton",
        "severity": "warn",
        "wiki_path": "wiki/log.md",
        "rule_ref": "wiki/log.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/log.md 含说明块（> 引用）——write log 滚动截断历史 bug 曾把 frontmatter 后 preamble 整段吞掉",
        "signals": {"blockquote": True},
    },
    {
        "id": "memory-index-skeleton",
        "severity": "warn",
        "wiki_path": "MEMORY/MEMORY.md",
        "rule_ref": "MEMORY/MEMORY.md fixture header (wiki 实例内直接可读)",
        "desc": "MEMORY/MEMORY.md 含 H1（# MEMORY）+ 说明块 + ## 索引",
        "signals": {"h1": "# MEMORY", "blockquote": True, "section_headings": ["## 索引"]},
    },
    {
        "id": "scripts-md-skeleton",
        "severity": "warn",
        "wiki_path": "scripts/SCRIPTS.md",
        "rule_ref": "scripts/SCRIPTS.md fixture header (wiki 实例内直接可读)",
        "desc": "scripts/SCRIPTS.md 含 H1（# Scripts）+ 说明块 + ## 索引",
        "signals": {"h1": "# Scripts", "blockquote": True, "section_headings": ["## 索引"]},
    },
    {
        "id": "tags-md-skeleton",
        "severity": "warn",
        "wiki_path": "wiki/tags.md",
        "rule_ref": "wiki/tags.md fixture header (wiki 实例内直接可读)",
        "desc": "wiki/tags.md 含 H1（# Tags）+ 说明块（无 ## 索引——tags 直接 bullet 列表）",
        "signals": {"h1": "# Tags", "blockquote": True},
    },
]


def _make_skeleton_check(entry: Dict[str, object]) -> Callable[[Path, Dict[str, str]], Dict[str, object]]:
    """按 SKELETON_REGISTRY 描述符生成一条骨架 check 函数（照搬 _check_no_frontmatter 共享模式）。"""
    wiki_path = entry["wiki_path"]  # type: ignore
    sigs = entry["signals"]  # type: ignore

    def _check(wiki_root: Path, info: Dict[str, str]) -> Dict[str, object]:
        out = {"passed": True, "file": wiki_path}  # type: Dict[str, object]
        wiki_text = _read_text(wiki_root / wiki_path)
        if wiki_text is None:
            out["passed"] = None
            out["skipped"] = f"{wiki_path} 不存在"
            return out
        missing = _check_skeleton_signals(wiki_text, sigs)
        if missing:
            out["passed"] = False
            out["expected"] = "; ".join(missing)
            out["actual"] = f"缺失 {len(missing)} 项骨架信号"
        return out

    _check.__name__ = "check_" + str(entry["id"]).replace("-", "_")  # type: ignore
    return _check


# 骨架 check 并入 CHECK_REGISTRY（runtime 顺序 = 输出顺序）
CHECK_REGISTRY.extend(
    {
        "id": s["id"],
        "severity": s["severity"],
        "file": s["wiki_path"],
        "rule_ref": s["rule_ref"],
        "desc": s["desc"],
    }
    for s in SKELETON_REGISTRY
)


# ===== 调度 =====

CHECK_FUNCTIONS = [
    ("agents-version-is-current", check_agents_version),
    ("agents-md-template-sync", check_agents_md_template_sync),
    ("template-no-outbound-refs", check_template_no_outbound_refs),
    ("gitignore-external-track-toml", check_gitignore_external_track),
    ("symlink-anchor-toml-schema", check_symlink_anchor_toml_schema),
    ("symlink-anchor-toml-symlink-matches", check_symlink_anchor_toml_symlink_matches),
    ("index-md-categories-stable", check_index_md_categories),
    ("memory-index-no-frontmatter", check_memory_index_no_frontmatter),
    ("memory-entries-indexed", check_memory_entries_indexed),
    ("log-md-format-strict", check_log_md_format),
    ("scripts-md-no-frontmatter", check_scripts_md_no_frontmatter),
    ("tags-md-no-frontmatter", check_tags_md_no_frontmatter),
    ("wiki-metadata-reads-satisfied", check_wiki_metadata_reads_satisfied),
    ("opencode-instructions-sync", check_opencode_instructions_sync),
] + [(s["id"], _make_skeleton_check(s)) for s in SKELETON_REGISTRY]


def run_checks(wiki_root: Path, target_format: Optional[str]) -> Dict[str, object]:
    """跑全部 check；返 { wiki_root, target_format, checks: [...], summary: {...} }"""
    info = {"wiki_root": str(wiki_root), "target_format": target_format or ""}
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
        "target_format": target_format,
        "checks": checks_out,
        "summary": summary,
    }


def _format_human(report: Dict[str, object]) -> str:
    """人读报告（默认输出）。"""
    lines = []  # type: List[str]
    lines.append("=== Wiki fixtures 一致性检查 ===")
    lines.append(f"  wiki_root     : {report['wiki_root']}")
    lines.append(f"  target_format   : {report['target_format'] or '(未指定)'}")
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


def list_rules(as_json: bool = False) -> int:
    """--list-rules 业务入口（自包含，无需 wiki_root）。"""
    return _print_rules("Wiki fixtures 规则清单", CHECK_REGISTRY, as_json)


def run(wiki_root: Path, *, as_json: bool = False, target_format: Optional[str] = None) -> int:
    """check-fixtures 业务入口（cli.py dispatch 直调；flag SSOT 在 llmw.cli argparse 树）。"""
    if not wiki_root.is_dir():
        print(f"ERROR: {wiki_root} 不是目录", file=sys.stderr)
        return 2

    target = target_format or _skill_format_version()

    report = run_checks(wiki_root, target)

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_human(report))

    # 退出码：error > warn > pass/skip
    s = report["summary"]  # type: ignore
    if s["error"] > 0:  # type: ignore
        return 1
    return 0
