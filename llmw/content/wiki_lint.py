#!/usr/bin/env python3
"""wiki_lint — deterministic 健康检查（`llmw wiki lint`）。

finding 含义 / severity / 修法走 `--explain`（注册表 = llmw.content.findings）；
半定性检查由 agent 现场做。退出码：0 = 无 finding / 报告完成；1 = 有 finding；2 = 运行错误。
"""

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from llmw.content._check_common import (
    SEMVER_RE,
)
from llmw.content._check_common import (
    compare_semver as _compare_semver,
)
from llmw.content.findings import severity_of as _severity_of
from llmw.content.ingest_diff import parse_frontmatter_simple
from llmw.content.log_format import (
    LOG_LINE_RE,
    LOG_RETENTION_LIMIT,
    parse_date_or_datetime,
)
from llmw.content.page_types import (
    REQUIRED_FRONTMATTER_FIELDS,
    TYPE_TO_SECTION,
    TYPES_DISPLAY,
    VALID_TYPES,
    WIKI_SUBDIRS,
)

MEMORY_SUBDIR = "MEMORY"
# kebab-case 正则与 external 子目录 / anchor 文件名常量 SSOT 在 external_anchor（lint 仅消费）
from llmw.content.external_anchor import (  # noqa: E402
    ANCHOR_FILENAME,
    EXTERNAL_SUBDIR,
    SOURCE_NAME_RE,
)
from llmw.content.external_anchor import load as load_anchor  # noqa: E402

DISCUSSIONS_SUBDIR = "discussions"  # raw/ 下用户 + LLM 协作草稿层；与 external/ 并列的 raw/ 写权限例外
MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"\[\[[^\]\n]+\]\]")
EXTERNAL_URL_RE = re.compile(r"^(https?:|mailto:|//)")

# 剔 code 区再扫链接（渲染器不 linkify code 区，裸扫会误报）；等长空白替换保偏移稳定
_CODE_FENCE_RE = re.compile(r"^(?P<fence>```|~~~)[^\n]*\n.*?^(?P=fence)[^\n]*$", re.M | re.S)
_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")


def strip_code_regions(text: str) -> str:
    """剔 fenced code block 与行内 code span（等长空白替换），返回处理后的文本。"""
    text = _CODE_FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return _CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_absolute_path(p: str) -> bool:
    """平台无关的绝对路径判定（Unix / Windows 盘符 / UNC 三种形式）。

    不走 pathlib.PurePath.is_absolute()——它按调用平台分叉，POSIX 主机判不了 Windows 路径。
    先剥成对引号：frontmatter list 元素保留引号（`'/etc/passwd'`），不剥会漏判。
    """
    if not p:
        return False
    stripped = p.strip()
    if len(stripped) >= 2 and stripped[0] in ("'", '"') and stripped[-1] == stripped[0]:
        stripped = stripped[1:-1]
    if not stripped:
        return False
    if stripped.startswith("/"):
        return True
    if stripped.startswith("\\\\"):
        return True
    if _WIN_DRIVE_RE.match(stripped):
        return True
    return False


# SSOT = llmw/__init__ 常量；SKILL.md frontmatter 由 CI gate 比对
from llmw import WIKI_FORMAT_VERSION  # noqa: E402

CURRENT_WIKI_FORMAT = WIKI_FORMAT_VERSION

# pattern key → 迁移依据（rule_ref）；修复语义自含于 plan actions 的 to_action
LEGACY_PATTERN_KEYS = {
    # 拦内容页误用 reserved `type: memory`（MEMORY 桶合法，仅内容页误用触发）
    "type-memory-value": "page-templates.md#共有-frontmatter-段",
}

SEV_RANK = {"error": 0, "warn": 1, "info": 2}


def is_external_url(url: str) -> bool:
    return bool(EXTERNAL_URL_RE.match(url.strip()))


def find_md_files(wiki_root: Path) -> Dict[str, List[Path]]:
    """收集 wiki/**/*.md 与 MEMORY/*.md，按子目录分桶（memory 桶不强制 index 覆盖）。

    桶键推导自 page_types.WIKI_SUBDIRS（新增内容类型不 KeyError）。
    """
    out = {sub: [] for sub in WIKI_SUBDIRS + ("index", "log", "memory")}  # type: Dict[str, List[Path]]
    wiki_dir = wiki_root / "wiki"
    if not wiki_dir.is_dir():
        return out
    for sub in WIKI_SUBDIRS:
        d = wiki_dir / sub
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                out[sub].append(p)
    mem_dir = wiki_root / MEMORY_SUBDIR
    if mem_dir.is_dir():
        for p in sorted(mem_dir.glob("*.md")):
            out["memory"].append(p)
    out["index"].append(wiki_dir / "index.md")
    out["log"].append(wiki_dir / "log.md")
    return out


def is_git_repo(path: Path) -> bool:
    """path 是否在 git 仓内（`.git/` 存在即可，不依赖 git CLI）。

    裸目录树 wiki 默认支持——无 git 时没有"未提交改动"概念，不可变性检查据此跳过。
    """
    if not path.is_dir():
        return False
    cur = path.resolve()
    while True:
        if (cur / ".git").exists():
            return True
        parent = cur.parent
        if parent == cur:
            return False
        cur = parent


def _git_porcelain_paths(line: str) -> List[str]:
    """porcelain v1 一行 → path 列表（rename/copy 行返 [old, new]）。

    前 2 字符 = XY 状态、第 3 字符 = 空格；含特殊字符的 path 被双引号包裹。
    """
    if len(line) < 4:
        return []
    rest = line[3:]
    if " -> " in rest:
        paths = rest.split(" -> ", 1)
    else:
        paths = [rest]
    return [p.strip().strip('"') for p in paths]


def check_raw_immutable(wiki_root: Path, use_git: bool) -> List[str]:
    """raw/ 是否有未提交改动（非 git 仓 / raw 未跟踪 → 跳过）。

    返回 (findings, skipped_reason)；skipped_reason 非空 = 跳过原因，由调用方展示。
    """
    if not use_git:
        return ([], "")
    raw_dir = wiki_root / "raw"
    if not raw_dir.is_dir():
        return ([], "")
    if not is_git_repo(wiki_root):
        return ([], "raw-immutable-skipped: 未启用 git（无 .git/），跳过 raw/ 不可变性检查")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "raw/"],
            cwd=str(wiki_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except FileNotFoundError:
        return ([], "raw-immutable-skipped: 未找到 git CLI，跳过 raw/ 不可变性检查")
    if result.returncode != 0:
        return ([], "raw-immutable-skipped: raw/ 未纳入 git 跟踪，跳过 raw/ 不可变性检查")
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    # discussions/ 是协作草稿层、双方可写，未提交改动不算 raw 违规；external/ 的
    # symlink 被 .gitignore 排除不进 status。rename 行任一侧命中 discussions 也排除
    # （归档 mv 跨边界：discussions/ → articles/ 属合法）
    discussions_prefix = "raw/" + DISCUSSIONS_SUBDIR + "/"
    lines = [ln for ln in lines if not any(p.startswith(discussions_prefix) for p in _git_porcelain_paths(ln))]
    if not lines:
        return ([], "")
    findings = [f"raw-modified: raw/ 有 {len(lines)} 处未提交改动：{lines[0]}{' ...' if len(lines) > 1 else ''}"]
    return (findings, "")


def check_external_symlinks(wiki_root: Path) -> List[str]:
    """raw/external/ 与 anchor 的双向健康检查（扁平布局 + TOML anchor）。

    finding 名与 severity 见 llmw.content.findings；目录不存在时返回空。
    """
    findings = []  # type: List[str]
    external_dir = wiki_root / "raw" / EXTERNAL_SUBDIR
    if not external_dir.is_dir():
        return findings

    try:
        top_entries = list(external_dir.iterdir())
    except OSError:
        return findings

    symlink_names = set()  # type: Set[str]
    for entry in top_entries:
        if entry.name.startswith("."):
            continue
        if entry.name in symlink_names:
            continue
        # 先判 is_symlink：symlink-to-dir 的 is_dir() 也为 True，但 target 是目录合法
        if entry.is_symlink():
            if not SOURCE_NAME_RE.match(entry.name):
                rel = entry.relative_to(wiki_root).as_posix()
                findings.append(
                    f"external-source-name-invalid: {rel} symlink 名 '{entry.name}' 不符合 "
                    f"^[a-z0-9][a-z0-9-]*$（kebab-case 短名）"
                )
            symlink_names.add(entry.name)
            continue
        if entry.is_dir():
            rel = entry.relative_to(wiki_root).as_posix()
            findings.append(
                f"external-source-name-invalid: {rel}/ 是子目录，但 raw/external/ 为扁平布局——"
                f"symlink + anchor 应直接 in external/，不要开 <source-name>/ 子目录"
            )
            continue
        rel = entry.relative_to(wiki_root).as_posix()
        findings.append(
            f"external-source-name-invalid: {rel} 是普通文件，但 raw/external/ 顶层只允许 "
            f"symlink + '{ANCHOR_FILENAME}'（扁平布局）"
        )

    anchor_path = external_dir / ANCHOR_FILENAME
    entries = None  # type: Optional[List[Dict[str, str]]]
    if not anchor_path.is_file():
        if symlink_names:
            findings.append(
                f"external-anchor-missing: raw/external/ 下有 symlink "
                f"{sorted(symlink_names)} 但缺 '{ANCHOR_FILENAME}'（必填）"
            )
        return findings
    entries = load_anchor(anchor_path)
    if entries is None:
        findings.append(f"external-anchor-corrupt: raw/external/{ANCHOR_FILENAME} 解析失败或 0 个有效 entry")
        return findings

    entry_by_symlink = {e["symlink"]: e for e in entries if "symlink" in e}

    # 双向校验 (1)：每个 symlink 必须有 entry
    for sl_name in sorted(symlink_names):
        if sl_name not in entry_by_symlink:
            rel = (external_dir / sl_name).relative_to(wiki_root).as_posix()
            findings.append(f"external-anchor-orphan: {rel} 是 symlink 但 anchor 无对应 [[entry]]（必填关联）")
            continue
        anchor = entry_by_symlink[sl_name]
        rel = (external_dir / sl_name).relative_to(wiki_root).as_posix()
        target_path = Path(anchor["target"]).expanduser()
        if not target_path.exists():
            findings.append(
                f"external-target-dead: {rel} 的 anchor target='{anchor['target']}' "
                f"已不存在（captured_at={anchor.get('captured_at', '?')}）；"
                f"用户需重新锚定或删除 symlink"
            )
            continue
        # target 与 symlink 解析不一致 = drift。比较前双方都要 resolve()：仅
        # expanduser 不够——home 目录本身可能是 symlink（/home/x → 挂载点），
        # 会与 sl_path.resolve() 不等而误报
        sl_path = external_dir / sl_name
        try:
            current_target = str(sl_path.resolve())
        except OSError:
            current_target = ""
        try:
            expanded_anchor_target = str(Path(anchor["target"]).expanduser().resolve())
        except OSError:
            expanded_anchor_target = ""
        if current_target and expanded_anchor_target != current_target:
            findings.append(
                f"external-target-drift: {rel} 当前 symlink 解析为 "
                f"'{current_target}'，但 anchor 记录 '{anchor['target']}'"
                f"（展开后 '{expanded_anchor_target}'）；"
                f"anchor 需更新"
            )

    # 双向校验 (2)：每个 entry 必须有 symlink
    for entry in entries:
        sl_name = entry.get("symlink", "")
        if sl_name not in symlink_names:
            target = entry.get("target", "?")
            findings.append(
                f"external-symlink-missing: anchor [[entry]] symlink='{sl_name}' target='{target}' "
                f"但 raw/external/{sl_name} symlink 不存在（必填关联）"
            )

    return findings


def _check_source_element(wiki_root: Path, rel: str, s) -> Optional[str]:
    """source 页单个 sources 元素 → finding 或 None（每元素至多一条，不重复报）。"""
    if not isinstance(s, str):
        return None
    # 必须相对路径——绝对路径（Unix / Windows 盘符 / UNC）破坏跨机器可移植性
    if _is_absolute_path(s):
        return (
            f"sources-absolute-path: {rel} sources 含绝对路径 '{s}'；"
            f"必须用相对 wiki 根的路径（如 raw/articles/... 或 "
            f"raw/external/<source-name>/...）（解释见 "
            f"llmw wiki lint --explain=sources-absolute-path）"
        )
    # raw/discussions/ 禁止作 source——协作草稿层不是"用户掌控的真相源"，
    # 放开口子 = provenance 后门（LLM 自产内容被当 raw 真相 ingest 回 wiki）；
    # 先 mv 到 raw/articles 等正式子树再走标准 ingest
    if s.startswith("raw/" + DISCUSSIONS_SUBDIR + "/"):
        return (
            f"source-in-discussions: {rel} sources='{s}' 指向 "
            f"raw/{DISCUSSIONS_SUBDIR}/——discussions/ 是协作草稿层"
            f"，不可作 source 真相源；先 mv 到 raw/articles "
            f"等正式子树再 ingest"
        )
    # raw/external/<symlink>/...：.resolve() 会落到 wiki 根外，不该判 sources-out-of-root
    if s.startswith("raw/external/"):
        parts = Path(s).parts
        # 路径段应为 [raw, external, <symlink>, ...]；< 3 视为语法错
        if len(parts) < 3:
            return f"sources-malformed: {rel} sources='{s}' raw/external/ 路径需 <symlink>/<path-under-target>"
        sl_name = parts[2]
        anchor = wiki_root / "raw" / EXTERNAL_SUBDIR / ANCHOR_FILENAME
        if not anchor.is_file():
            return (
                f"sources-external-anchor-missing: {rel} sources='{s}' "
                f"但 {anchor.relative_to(wiki_root).as_posix()} 不存在"
            )
        sl_path = wiki_root / "raw" / EXTERNAL_SUBDIR / sl_name
        if not sl_path.is_symlink() and not sl_path.exists():
            return f"sources-external-symlink-missing: {rel} sources='{s}' symlink {sl_name} 不存在"
        # 跟随 symlink 后可访问——不 .resolve() 避免相对 wiki 根判定；文件或目录皆可
        # （external repo 本身是 git 仓即目录，sources 可指向整个仓作语料）
        if not (wiki_root / s).exists():
            return f"sources-missing: {rel} sources='{s}' 路径不可访问"
        return None
    sp = (wiki_root / s).resolve()
    try:
        sp.relative_to(wiki_root.resolve())
    except ValueError:
        return f"sources-out-of-root: {rel} sources='{s}'不在 wiki 根下"
    if not sp.is_file():
        return f"sources-missing: {rel} sources='{s}'但文件不存在"
    return None


def _check_sources_field(wiki_root: Path, rel: str, t: str, srcs) -> List[str]:
    """source / synthesis 页的 sources 字段校验（必填非空；source 页逐元素查现存）。"""
    if not isinstance(srcs, list) or not srcs:
        return [f"missing-sources: {rel} type={t} 缺 'sources' 字段或为空"]
    if t != "source":
        return []
    findings = []  # type: List[str]
    for s in srcs:
        finding = _check_source_element(wiki_root, rel, s)
        if finding:
            findings.append(finding)
    return findings


def check_frontmatter(wiki_root: Path) -> List[str]:
    """frontmatter 完整性 + source/synthesis 的 sources 字段

    校验口径分两类（口径 canonical = finding 注册表 llmw.content.findings）：
    - wiki 内容页：
      必填 frontmatter 字段 + 推荐 description
    - MEMORY/*.md：仅 `title` 必填，其余 5 字段全 optional（frontmatter 是
      可选 decoration；MEMORY 不在 wiki/index.md 列出、无 reviewed 概念、
      tag 不共享 wiki taxonomy——必填字段的 rationale 对 MEMORY 多半不成立）
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    # wiki 内容页：完整必填校验
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter_simple(text)
            rel = p.relative_to(wiki_root).as_posix()
            for field in REQUIRED_FRONTMATTER_FIELDS:
                if field not in fm:
                    findings.append(f"missing-frontmatter: {rel} 缺 '{field}' 字段")
            t = fm.get("type")
            if t is not None and t not in VALID_TYPES:
                findings.append(f"invalid-type: {rel} type='{t}' 非法；应为 {sorted(VALID_TYPES)} 之一")
            # tags 若取则必须是 list（否则 tag taxonomy 静默跳过该页解析）
            if "tags" in fm and not isinstance(fm["tags"], list):
                findings.append(f"invalid-tags: {rel} tags 应为 list，当前类型不符")
            if t in ("source", "synthesis"):
                findings.extend(_check_sources_field(wiki_root, rel, t, fm.get("sources", [])))
    # MEMORY/*.md（除索引）：仅 title 必填；frontmatter 整体可选，有则按弱规则校验
    for p in pages["memory"]:
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        rel = p.relative_to(wiki_root).as_posix()
        if "title" not in fm:
            findings.append(f"missing-frontmatter: {rel} 缺 'title' 字段")
        t = fm.get("type")
        if t is not None and t not in VALID_TYPES:
            findings.append(f"invalid-type: {rel} type='{t}' 非法；应为 {sorted(VALID_TYPES)} 之一")
        if "tags" in fm and not isinstance(fm["tags"], list):
            findings.append(f"invalid-tags: {rel} tags 应为 list，当前类型不符")
    return findings


def check_frontmatter_structure(wiki_root: Path) -> List[str]:
    """frontmatter 定界符结构：闭合 `---` 须独占一行（粘连 → error），与正文间须空行（缺 → warn）。

    宽松 frontmatter 正则对粘连形态照样"剥得掉"，别的检查全绿但页面不渲染——本检查兜底。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    candidates = []  # type: List[Path]
    for sub in WIKI_SUBDIRS + ("index", "log", "memory"):
        candidates.extend(pages[sub])
    for p in candidates:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        rel = p.relative_to(wiki_root).as_posix()
        strict = re.match(r"^---\n.*?\n---[ \t]*(?=\n|$)", text, re.DOTALL)
        if strict is None:
            findings.append(
                f"frontmatter-delimiter-glued: {rel} frontmatter 闭合 `---` 与正文粘连"
                "（如 `---# 标题`）——前置块定界符失效，整页不渲染；手动 Edit 补换行修复"
            )
            continue
        rest = text[strict.end() :]
        if len(rest) > 1 and not rest[1:].startswith("\n"):
            findings.append(
                f"frontmatter-no-blank-line: {rel} 闭合 `---` 与正文之间缺空行"
                "（frontmatter 后应空一行再接正文，见 page-templates.md）"
            )
    return findings


def resolve_link(base: Path, link: str) -> Optional[Path]:
    """Markdown 链接 → 绝对路径；外部 URL / 锚点 / query 返回 None。"""
    link = link.strip()
    link = link.split("#", 1)[0]
    link = link.split("?", 1)[0]
    if not link:
        return None
    if is_external_url(link):
        return None
    target = (base.parent / link).resolve()
    return target


def check_link_integrity(wiki_root: Path) -> List[str]:
    """正文 Markdown 链接完整性（仅 wiki/ 范围；raw/ 下的图不查）。"""
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    all_pages = []
    for sub in WIKI_SUBDIRS + ("index", "log", "memory"):
        all_pages.extend(pages[sub])
    for p in all_pages:
        if not p.is_file():
            continue
        rel = p.relative_to(wiki_root).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        body = strip_code_regions(text)
        for wm in WIKILINK_RE.finditer(body):
            findings.append(
                f"wikilink-used: {rel} 正文用了 wikilink `{wm.group(0)}`——改为相对路径链接 `[X](../<dir>/x.md)`"
            )
        for m in MD_LINK_RE.finditer(body):
            url = m.group(2)
            target = resolve_link(p, url)
            if target is None:
                continue
            try:
                target.relative_to(wiki_root.resolve() / "wiki")
            except ValueError:
                continue
            if not target.is_file():
                findings.append(
                    f"broken-link: {rel} 引用 '{url}' 解析为 {target.relative_to(wiki_root).as_posix()}，但文件不存在"
                )
    return findings


def check_index_coverage(wiki_root: Path) -> List[str]:
    """index.md 覆盖：内容页必须被列出。"""
    findings = []  # type: List[str]
    index_path = wiki_root / "wiki" / "index.md"
    if not index_path.is_file():
        return ["index-missing: wiki/index.md 不存在"]
    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    indexed = set()  # type: Set[str]
    for m in MD_LINK_RE.finditer(strip_code_regions(index_text)):
        url = m.group(2)
        target = resolve_link(index_path, url)
        if target is None:
            continue
        try:
            rel = target.relative_to(wiki_root).as_posix()
        except ValueError:
            continue
        indexed.add(rel)
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            rel = p.relative_to(wiki_root).as_posix()
            if rel not in indexed:
                findings.append(f"orphan-page: {rel} 未在 wiki/index.md 中列出")
    return findings


def check_index_section_placement(wiki_root: Path) -> List[str]:
    """index.md 条目须落在页 type 对应的 `##` 类别段内（覆盖检查看不到位置错乱）。

    目标页缺失 / type 非法 → 跳过（由 broken-link / invalid-type 报，不重复）。
    """
    findings = []  # type: List[str]
    index_path = wiki_root / "wiki" / "index.md"
    if not index_path.is_file():
        return []  # index-missing 由 check_index_coverage 报
    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    current_section = None  # type: Optional[str]  # None = 尚未进入任何 `##` 段
    for ln in index_text.splitlines():
        hm = re.match(r"^##\s+(.+?)\s*$", ln.strip())
        if hm:
            current_section = hm.group(1)
            continue
        em = _INDEX_ENTRY_RE.match(ln.strip())
        if not em:
            continue
        link = em.group(1).strip()
        target = resolve_link(index_path, link)
        if target is None:
            continue
        try:
            target.relative_to(wiki_root)
        except ValueError:
            continue
        if not target.is_file():
            continue
        fm = parse_frontmatter_simple(target.read_text(encoding="utf-8", errors="replace"))
        t = str(fm.get("type", "")).strip()
        expected = TYPE_TO_SECTION.get(t)
        if expected is None:
            continue
        if current_section != expected:
            rel = target.relative_to(wiki_root).as_posix()
            findings.append(
                f"index-entry-wrong-section: {rel} 条目落在 `## {current_section or '(无段)'}`"
                f"，应按 type={t} 归入 `## {expected}`（index 纪律：按类别分组 + 字母序）"
            )
    return findings


def check_log_format(wiki_root: Path) -> List[str]:
    """log.md 格式"""
    findings = []  # type: List[str]
    log_path = wiki_root / "wiki" / "log.md"
    if not log_path.is_file():
        return ["log-missing: wiki/log.md 不存在"]
    text = log_path.read_text(encoding="utf-8", errors="replace")
    body = _strip_frontmatter_body(text)
    for i, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        if line.startswith("## "):
            if not LOG_LINE_RE.match(line):
                findings.append(
                    f"log-format: wiki/log.md 第 {i} 行格式不合规：'{line[:60]}{'...' if len(line) > 60 else ''}'"
                )
    return findings


STALE_SUMMARY_DAYS = 90


def check_log_truncation(wiki_root: Path) -> List[str]:
    """log.md 条目数超滚动窗口上限即建议截断（完整历史靠 git）；只报告，截断由 agent 做。

    log-missing 由 check_log_format 报，这里跳过。
    """
    findings = []  # type: List[str]
    log_path = wiki_root / "wiki" / "log.md"
    if not log_path.is_file():
        return findings
    text = log_path.read_text(encoding="utf-8", errors="replace")
    body = _strip_frontmatter_body(text)
    entry_count = sum(1 for line in body.splitlines() if LOG_LINE_RE.match(line))
    if entry_count > LOG_RETENTION_LIMIT:
        findings.append(
            f"log-truncation-recommended: wiki/log.md 含 {entry_count} 条目，超过 {LOG_RETENTION_LIMIT} "
            f"滚动窗口上限；建议截断保最近 {LOG_RETENTION_LIMIT} 条"
            f"（完整历史查 git log -p -- wiki/log.md）"
        )
    return findings


def check_stale_summaries(wiki_root: Path, threshold_days: int = STALE_SUMMARY_DAYS) -> List[str]:
    """source 页 `updated` 距今超阈值。"""
    findings = []  # type: List[str]
    sources_dir = wiki_root / "wiki" / "sources"
    if not sources_dir.is_dir():
        return findings
    today = date.today()
    for p in sources_dir.glob("*.md"):
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        updated = fm.get("updated")
        upd_date = parse_date_or_datetime(updated)
        if upd_date is None:
            continue
        age = (today - upd_date).days
        if age > threshold_days:
            rel = p.relative_to(wiki_root).as_posix()
            findings.append(
                f"stale-summary: {rel} type=source updated={updated} ({age} 天前，超过 {threshold_days} 天阈值)"
            )
    return findings


TAXONOMY_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
TAG_KV_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

TAG_FILE_PRIMARY = "wiki/tags.md"


def _parse_tag_bullets(text: str) -> Set[str]:
    """裸 bullet 文本 → kebab-case tag 集合。

    支持 `- category：tag1 / tag2`（中英文分隔符）与 `- tag`；跳过注释 / fence / 空行。
    """
    tags = set()  # type: Set[str]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.startswith("```"):
            continue
        m = TAXONOMY_BULLET_RE.match(stripped)
        if not m:
            continue
        content = m.group(1).strip()
        sep_match = re.match(r"^([^：:]+)[：:]\s*(.+)$", content)
        if sep_match:
            tag_part = sep_match.group(2)
        else:
            tag_part = content
        for t in re.split(r"[/，,]", tag_part):
            t = t.strip().strip("`").strip("*").strip()
            if t and TAG_KV_RE.match(t):
                tags.add(t)
    return tags


def parse_tag_taxonomy(wiki_root: Path) -> Set[str]:
    """读 wiki/tags.md 白名单；文件不存在 / 解析出 0 个 → 空集合（调用方静默跳过）。"""
    primary = wiki_root / TAG_FILE_PRIMARY
    if primary.is_file():
        text = primary.read_text(encoding="utf-8", errors="replace")
        return _parse_tag_bullets(text)
    return set()


def check_tag_taxonomy(wiki_root: Path) -> List[str]:
    """内容页 frontmatter.tags 是否都在白名单内；空白名单跳过。"""
    findings = []  # type: List[str]
    allowed = parse_tag_taxonomy(wiki_root)
    if not allowed:
        return findings
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    # MEMORY/*.md 不进白名单校验：agent 私有记忆，tag 不共享用户面 taxonomy
    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        tags = fm.get("tags", [])
        if not isinstance(tags, list):
            continue
        rel = p.relative_to(wiki_root).as_posix()
        for t in tags:
            if not isinstance(t, str):
                continue
            t = t.strip().strip("\"'")
            if not t:
                continue
            if t not in allowed:
                findings.append(f"tag-not-in-taxonomy: {rel} tags 含 '{t}' 不在 wiki/tags.md 白名单")
    return findings


def check_filename_kebab(wiki_root: Path) -> List[str]:
    """文件名 kebab-case（MEMORY.md 索引除外）。"""
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS + ("index", "log"):
        for p in pages[sub]:
            stem = p.stem
            if not SOURCE_NAME_RE.match(stem):
                rel = p.relative_to(wiki_root).as_posix()
                findings.append(
                    f"filename-not-kebab: {rel} 文件名 '{p.name}' 应使用 kebab-case（小写字母 + 数字 + 短横线）"
                )
    for p in pages["memory"]:
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        stem = p.stem
        if not SOURCE_NAME_RE.match(stem):
            rel = p.relative_to(wiki_root).as_posix()
            findings.append(
                f"filename-not-kebab: {rel} 文件名 '{p.name}' 应使用 kebab-case（小写字母 + 数字 + 短横线）"
            )
    return findings


def check_duplicate_titles(wiki_root: Path) -> List[str]:
    """同一 title 出现在多页。"""
    findings = []  # type: List[str]
    title_to_files = {}  # type: Dict[str, List[str]]
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter_simple(text)
            title = fm.get("title")
            if not isinstance(title, str):
                continue
            rel = p.relative_to(wiki_root).as_posix()
            title_to_files.setdefault(title, []).append(rel)
    for title, files in title_to_files.items():
        if len(files) > 1:
            findings.append(f"duplicate-title: '{title}' 出现在 {len(files)} 个页面：{', '.join(files)}")
    return findings


# 正文非空行阈值（其他 prose 引此常量）
PAGE_SIZE_THRESHOLD = 300


def _strip_frontmatter_body(text):
    """去 frontmatter，返回正文（体量统计不计 frontmatter）。"""
    body_start = 0
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
        if m:
            body_start = m.end()
    return text[body_start:]


def check_page_size(wiki_root, threshold=PAGE_SIZE_THRESHOLD):
    """正文非空行数超阈值的内容页（MEMORY 无上限）。"""
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            body = _strip_frontmatter_body(text)
            n = sum(1 for ln in body.splitlines() if ln.strip())
            if n > threshold:
                rel = p.relative_to(wiki_root).as_posix()
                findings.append(
                    f"oversized-page: {rel} 正文 {n} 行（非空），超过 {threshold} 阈值——"
                    f"建议拆成子主题页 + cross-link（page-templates.md#建页--追加--归档阈值page-thresholds）"
                )
    return findings


def check_quality_signals(wiki_root):
    """可信度 / 认知质量信号：reviewed / contested / contradictions + index ✓✗ 标识漂移。

    字段全部可选（省略 = 不评）；只拎作者已写 / 已渲染的信号，finding 含义见 --explain。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    # MEMORY 是 agent 私有记忆，不进 reviewed 校验（字段仍可写，只是不兜底报告）
    # contradictions 对端映射：page_rel -> 已解析对端集合（对称性检查用）
    contra_out = {}  # type: Dict[str, Set[str]]
    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        rel = p.relative_to(wiki_root).as_posix()

        reviewed_raw = _raw_field_value(text, "reviewed")
        reviewed_at_raw = fm.get("reviewed_at")
        is_reviewed = reviewed_raw == "true"
        has_reviewed_at = reviewed_at_raw is not None and str(reviewed_at_raw).strip() != ""

        if reviewed_raw is not None and not is_reviewed:
            findings.append(f"invalid-reviewed-value: {rel} reviewed='{reviewed_raw}' 非法；应为严格 true 或省略")

        if is_reviewed and not has_reviewed_at:
            findings.append(f"reviewed-at-missing: {rel} reviewed=true 但缺 reviewed_at")
        if has_reviewed_at and not is_reviewed:
            findings.append(f"reviewed-at-orphan: {rel} reviewed_at='{reviewed_at_raw}' 但缺 reviewed=true")

        if is_reviewed and has_reviewed_at:
            updated = fm.get("updated")
            if updated and str(updated).strip() > str(reviewed_at_raw).strip():
                findings.append(
                    f"reviewed-stale: {rel} reviewed=true reviewed_at={reviewed_at_raw} "
                    f"但 updated={updated} — LLM 修改后未清 reviewed，建议重新审核"
                )

        if not is_reviewed:
            findings.append(f"pending-review: {rel} 未审核 — 待人工复审后置 reviewed: true")

        if str(fm.get("contested", "")).strip().strip("\"'").lower() == "true":
            findings.append(f"contested-page: {rel} contested=true — 含未解决矛盾主张，需裁定后移除该标记")

        contras = fm.get("contradictions", [])
        if isinstance(contras, list) and contras:
            resolved = set()  # type: Set[str]
            for c in contras:
                if not isinstance(c, str):
                    continue
                target = resolve_link(p, c)
                if target is None:
                    continue
                try:
                    target_rel = target.relative_to(wiki_root.resolve()).as_posix()
                except ValueError:
                    continue
                if target.is_file():
                    resolved.add(target_rel)
                else:
                    findings.append(
                        f"contradiction-target-missing: {rel} contradictions 含 '{c}'，但该页不存在（{target_rel}）"
                    )
            if resolved:
                contra_out[rel] = resolved

    for src, targets in contra_out.items():
        for tgt in targets:
            back = contra_out.get(tgt)
            if back is None or src not in back:
                findings.append(
                    f"contradiction-asymmetric: {src} 把 {tgt} 标为矛盾对端，"
                    f"但 {tgt} 的 contradictions 未反向标注 {src}（要求双向标注）"
                )

    findings.extend(_check_index_review_badges(wiki_root))

    return findings


# index.md 条目：`- [title](path)` + 可选 description / ✓✗ 标识
_INDEX_ENTRY_RE = re.compile(
    r"^\s*-\s*\[[^\]]+\]\(([^)]+)\)(.*)$",
    re.MULTILINE,
)
# `✓ reviewed YYYY-MM-DD` 或 `✗ pending review`
_REVIEWED_BADGE_RE = re.compile(r"✓\s+reviewed\s+(\d{4}-\d{2}-\d{2})\b|✗\s+pending\s+review\b")


def _raw_field_value(text: str, key: str):
    """取 frontmatter key 的原始字面值（不剥引号）；None = key 不存在，"" = 存在但空。

    不能用 parse_frontmatter_simple——它剥引号，而 reviewed 语义要求严格 `true` 字面量
    （`"true"` / `'true'` / yes 都要能被区分出来）。
    """
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return None
    for line in fm_match.group(1).splitlines():
        m = re.match(r"^" + re.escape(key) + r":\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


def _check_index_review_badges(wiki_root):
    """index.md ✓/✗ 标识与被链页 reviewed 状态一致性（缺 / 日期错 / 多余均报）。"""
    findings = []  # type: List[str]
    index_path = wiki_root / "wiki" / "index.md"
    if not index_path.is_file():
        return findings
    text = index_path.read_text(encoding="utf-8", errors="replace")
    wiki_root_resolved = wiki_root.resolve()
    for m in _INDEX_ENTRY_RE.finditer(text):
        path = m.group(1).strip()
        rest = m.group(2)
        if is_external_url(path) or path.startswith("#"):
            continue
        target = (index_path.parent / path).resolve()
        try:
            target.relative_to(wiki_root_resolved)
        except ValueError:
            continue
        if not target.is_file():
            continue
        target_text = target.read_text(encoding="utf-8", errors="replace")
        reviewed = _raw_field_value(target_text, "reviewed")
        target_fm = parse_frontmatter_simple(target_text)
        reviewed_at = target_fm.get("reviewed_at")
        is_reviewed = reviewed == "true"
        reviewed_at_s = str(reviewed_at).strip() if reviewed_at is not None else ""
        badge_match = _REVIEWED_BADGE_RE.search(rest)
        title_match = re.match(r"\s*-\s*\[([^\]]+)\]", m.group(0))
        title = title_match.group(1) if title_match else path

        if is_reviewed and reviewed_at_s:
            if badge_match is None:
                findings.append(
                    f"index-review-badge-drift: wiki/index.md 条目 '{title}' 缺标识 — "
                    f"被链页 reviewed=true reviewed_at={reviewed_at_s}"
                )
            else:
                if "✓" in badge_match.group(0):
                    actual_date_match = re.search(r"(\d{4}-\d{2}-\d{2})", badge_match.group(0))
                    actual_date = actual_date_match.group(1) if actual_date_match else None
                    if actual_date != reviewed_at_s:
                        findings.append(
                            f"index-review-badge-drift: wiki/index.md 条目 '{title}' "
                            f"标识为 '{badge_match.group(0)}' 但被链页 reviewed=true reviewed_at={reviewed_at_s} — 日期错"
                        )
                else:
                    findings.append(
                        f"index-review-badge-drift: wiki/index.md 条目 '{title}' 标识为 '{badge_match.group(0)}' "
                        f"但被链页 reviewed=true reviewed_at={reviewed_at_s} — 标识类型错"
                    )
        else:
            if badge_match and "✓" in badge_match.group(0):
                findings.append(
                    f"index-review-badge-drift: wiki/index.md 条目 '{title}' "
                    f"标识为 '{badge_match.group(0)}' 但被链页未 reviewed — 多余标识"
                )
    return findings


def check_memory_index(wiki_root: Path) -> List[str]:
    """MEMORY.md 索引 ↔ MEMORY/*.md 双向一致性。

    经验条目须在 MEMORY.md 索引列一行（AGENTS.md `@import` 加载依赖）；反向 dangling 也查。
    短条目（`- 一句话事实`）无链接文件，不算 dangling；MEMORY.md 缺失时静默跳过。
    """
    findings = []  # type: List[str]
    mem_dir = wiki_root / MEMORY_SUBDIR
    memory_index = mem_dir / "MEMORY.md"
    if not memory_index.is_file():
        return findings
    indexed = set()  # type: Set[str]
    mem_dir_resolved = mem_dir.resolve()
    try:
        text = memory_index.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for m in MD_LINK_RE.finditer(strip_code_regions(text)):
        target = resolve_link(memory_index, m.group(2))
        if target is None:
            continue
        try:
            target.relative_to(mem_dir_resolved)
        except ValueError:
            continue
        if target.is_file():
            indexed.add(target.name)
        else:
            findings.append(
                f"memory-index-dangling: MEMORY/MEMORY.md 索引指向 "
                f"{target.relative_to(wiki_root).as_posix()}，但该文件不存在"
            )
    for p in sorted(mem_dir.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        if p.name not in indexed:
            rel = p.relative_to(wiki_root).as_posix()
            findings.append(
                f"memory-not-indexed: {rel} 未在 MEMORY/MEMORY.md 索引中列出；"
                f"该条目下次会话读不到 "
                f"（追加一行：- <slug> — <一句话> → [正文](<slug>.md)）"
            )
    return findings


def check_related_links(wiki_root: Path) -> List[str]:
    """frontmatter `related` / `compared` 路径引用（文件不存在 → warn）。

    基准陷阱：字段相对内容根 `wiki/`（解析须补 `wiki/` 段），与 `sources` 的外层 `raw/` 基准不同。
    为什么是 warn：机器消费字段，不让元数据小毛病阻断批量 ingest（正文 broken-link 才是 error）。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        rel = p.relative_to(wiki_root).as_posix()
        # related / compared 同语义合扫；contradictions 走文件相对，不在本检查
        for field_name in ("related", "compared"):
            items = fm.get(field_name, [])
            if not isinstance(items, list) or not items:
                continue
            for idx, item in enumerate(items):
                if not isinstance(item, str):
                    continue
                if is_external_url(item):
                    continue
                # 补 wiki/ 段（内容根相对，非最外层根相对）；不 .resolve()——
                # is_file() 判定已够，跟随不存在路径反而吞错
                target = wiki_root / "wiki" / item
                if not target.is_file():
                    findings.append(
                        f"related-broken-link: {rel} {field_name}[{idx}]='{item}' "
                        f"按内容根 wiki/ 相对解析为 wiki/{item}，但文件不存在"
                    )
    return findings


def severity_of(finding: str) -> str:
    """从 finding 文本取严重性——注册表 SSOT 见 llmw.content.findings。"""
    return _severity_of(finding)


# ===== --check-version：纯探测（不写盘）；plan 的消费方 = upgrade-workflow.md =====

# 「当前配置」表格式版本行（容忍用户编辑变体，如多余空格 / 备注尾部；semver 单独抓取）
CLAUDE_FORMAT_ROW_RE = re.compile(r"^\s*\|\s*Wiki Format 版本\s*\|\s*([^|]+?)\s*\|")


def parse_format_version(wiki_root: Path) -> Optional[str]:
    """抽 AGENTS.md「当前配置」表的 `Wiki Format 版本`；解析失败 / 缺文件 → None。

    只认表行不扫全文（防误抓正文版本号）；表被编辑坏 → None，让上游提示人工填回而不是猜。
    """
    md_file = wiki_root / "AGENTS.md"
    if not md_file.is_file():
        return None
    try:
        text = md_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = CLAUDE_FORMAT_ROW_RE.match(line)
        if not m:
            continue
        cell = m.group(1).strip()
        semver = SEMVER_RE.search(cell)
        if semver:
            return semver.group(0)
        return None
    return None


def check_format_version(wiki_root: Path) -> List[str]:
    """常规 lint 里报 wiki 版本新旧（只产 warn；升级 plan 由 --check-version --apply 落）。"""
    findings = []  # type: List[str]
    current = parse_format_version(wiki_root)
    if current is None:
        findings.append(
            "wiki-format-version-unparsed: AGENTS.md 末尾「当前配置」表 `Wiki Format 版本` 行无法解析"
            "（缺 AGENTS.md 或表格格式破坏）——"
            "跑 `llmw wiki lint --check-version` 诊断"
        )
        return findings
    cmp = _compare_semver(current, CURRENT_WIKI_FORMAT)
    if cmp == "older":
        findings.append(
            f"wiki-format-version-stale: AGENTS.md 末尾「当前配置」表 format {current} 落后 llmw 支持版本 {CURRENT_WIKI_FORMAT}——"
            "跑 `llmw wiki lint --check-version --apply` 走升级流程"
        )
    elif cmp == "newer":
        findings.append(
            f"wiki-format-version-ahead: AGENTS.md 末尾「当前配置」表 format {current} 领先 llmw 支持版本 {CURRENT_WIKI_FORMAT}——"
            "更新 llmw 安装对齐"
        )
    # equal / unknown → 无 finding
    return findings


def _run_fixtures_check(wiki_root: Path) -> Dict[str, object]:
    """直调 wiki_fixtures.run_checks；异常兜底返 skipped（不阻 lint 主流程）。"""
    try:
        from llmw.content.wiki_fixtures import run_checks

        return run_checks(wiki_root, CURRENT_WIKI_FORMAT)
    except Exception as e:  # noqa: BLE001
        return {"skipped": True, "reason": f"fixtures check exec failed: {e}"}


def _has_type_memory(page_rel: str, text: str) -> bool:
    """内容页是否误用 `type: memory`（该值仅 MEMORY 桶合法；本函数只扫内容页）。"""
    if page_rel.startswith("MEMORY/"):
        return False

    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return False
    for line in m.group(1).splitlines():
        if re.match(r"^\s*type:\s*memory\s*$", line):
            return True
    return False


def detect_legacy_patterns(wiki_root: Path) -> Dict[str, object]:
    """扫 legacy 现场：{"patterns": {key: [...]}, "conflicts": [...]}（供 plan / --json 复用）。"""
    pages = find_md_files(wiki_root)
    out = {
        "patterns": {k: [] for k in LEGACY_PATTERN_KEYS},  # type: Dict[str, List[Dict[str, object]]]
        "conflicts": [],  # type: List[Dict[str, str]]
    }  # type: Dict[str, object]

    candidates = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        candidates.extend(pages[sub])
    for p in pages["memory"]:
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        candidates.append(p)

    for p in candidates:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(wiki_root).as_posix()

        if _has_type_memory(rel, text):
            out["patterns"]["type-memory-value"].append({"file": rel, "conflict": False})  # type: ignore

    return out


# fixtures-check 失败项 → (type, to_action) 表；新增 check 加一行即可，骨架类后缀自动命中
_FIXTURES_ACTION_TABLE: Dict[str, Tuple[str, Callable[[Dict[str, object]], str]]] = {
    "gitignore-external-track-toml": (
        "fixtures-fix-gitignore",
        lambda b: (
            "Edit .gitignore：把旧 `!raw/external/**/.symlink-anchor.json` 行替换为"
            " `!raw/external/.symlink-anchor.toml`；保留 `raw/external/*` 排除行不动；"
            "保留其它规则不动"
        ),
    ),
    "agents-version-is-current": (
        "fixtures-fix-agents-version",
        lambda b: (
            f"跑 `llmw wiki upgrade --apply`：CLI 全量重渲染 AGENTS.md，版本行随渲染落地"
            f"（`{b['actual']}` → `{b['expected']}`）。**不要**手改 AGENTS.md——byte-owned 禁改，"
            "手改过不了 agents-md-template-sync 的整文件字节比对；若因版本行 diff 进"
            " blocked_drift，确认无本地定制后加 `--yes` 重跑"
        ),
    ),
    "agents-md-template-sync": (
        "fixtures-fix-agents-md-resync",
        lambda b: (
            "跑 `llmw wiki upgrade --apply`：CLI 全量重渲染 AGENTS.md（byte-owned，"
            "「当前配置」表四变量保留 wiki 现值）。若本地定制 diff 进 blocked_drift："
            "逐条列给用户裁定——搬 MEMORY/（一行事实写 MEMORY/MEMORY.md 索引短条目；"
            "含 why 的建 `MEMORY/<slug>.md` 完整条目）或丢弃，裁定完加 `--yes` 重跑"
        ),
    ),
    "symlink-anchor-toml-schema": (
        "fixtures-fix-anchor-schema",
        lambda b: (
            "raw/external/.symlink-anchor.toml 损坏：CLI add 拒绝覆盖损坏文件"
            "（保护手工修复现场）——备份后删除，或手工改对 TOML，再用"
            " `llmw wiki external add <target> --name=<n>` 重建 entries。"
            "字段语义见 external-repo.md#首次接入；schema 归 CLI 持有"
            "（`llmw wiki external` 子命令）"
        ),
    ),
    "symlink-anchor-toml-symlink-matches": (
        "fixtures-fix-anchor-symlink-matches",
        lambda b: (
            "双向校验：anchor 有 entry 但 symlink 缺 → `mkdir -p raw/external && ln -s <target> raw/external/<symlink>`；"
            "symlink 有但 anchor 无 entry → 补一条 `[[entry]]` 块（含 symlink/target/captured_at/kind + 可选 git 身份字段）"
        ),
    ),
    "memory-index-no-frontmatter": (
        "fixtures-fix-strip-frontmatter",
        lambda b: f"Edit {b['file']}：删除首部 `---...---` YAML frontmatter 块，保留正文",
    ),
    "scripts-md-no-frontmatter": (
        "fixtures-fix-strip-frontmatter",
        lambda b: f"Edit {b['file']}：删除首部 `---...---` YAML frontmatter 块，保留正文",
    ),
    "tags-md-no-frontmatter": (
        "fixtures-fix-strip-frontmatter",
        lambda b: f"Edit {b['file']}：删除首部 `---...---` YAML frontmatter 块，保留正文",
    ),
    "memory-entries-indexed": (
        "fixtures-fix-memory-index",
        lambda b: (
            "在 MEMORY/MEMORY.md 索引追加缺失条目（fixture 头部说明块规则）："
            "`- [<slug>](<slug>.md) — 一句话 → [正文](<slug>.md)`"
        ),
    ),
    "log-md-format-strict": (
        "fixtures-fix-log-format",
        lambda b: (
            f"Edit {b['file']} 不合规行：每行匹配 `^## [YYYY-MM-DD HH:MM] (ingest|query|lint|setup) | .+$`（HH:MM 可选；老 wikis date-only 仍合法，宽容解析）；"
            "迁移期不变更 history（仅当行确属违规，才 Edit 修复格式；保留日期 + 类型 + 简介）"
        ),
    ),
    "index-md-categories-stable": (
        "fixtures-fix-index-categories",
        lambda b: (
            f"补齐 {b['file']} 缺类别：{len(TYPE_TO_SECTION)} 标题齐全（见 fixture 头部模板）"
            f"（{' / '.join(TYPE_TO_SECTION.values())}），顺序可调"
        ),
    ),
}

_FIXTURES_SKELETON_SUFFIXES = ("-skeleton", "-frontmatter-complete", "-init-rules-complete")

_FIXTURES_SKELETON_SPEC: Tuple[str, Callable[[Dict[str, object]], str]] = (
    "fixtures-fix-skeleton",
    lambda b: (
        f"Edit {b['file']}：按本条 `expected`（缺失骨架信号清单）单 Edit 补齐——"
        "frontmatter 键 / H1 / 说明块 / 段标题 / .gitignore 段"
        "（.gitignore 段可跑 `llmw wiki upgrade --apply` 由 CLI 重渲染）；"
        "成长型内容（index 类别下条目 / log 历史 / MEMORY 经验 / tag bullet）"
        "**不动**——只补结构骨架"
    ),
)

_FIXTURES_UNKNOWN_SPEC: Tuple[str, Callable[[Dict[str, object]], str]] = (
    "fixtures-fix-unknown",
    lambda b: f"按 rule_ref ({b['rule_ref']}) 与 {b['check_id']} 描述自行处理",
)


def _build_fixtures_action(fc: Dict[str, object]) -> Dict[str, object]:
    """单条失败 fixtures-check → fixtures_actions[] 条目（base 字段 + 表驱动 to_action）。"""
    cid = str(fc["id"])
    base: Dict[str, object] = {
        "check_id": cid,
        "file": fc["file"],
        "severity": fc.get("severity", "error"),
        "rule_ref": fc.get("rule_ref", ""),
        "expected": fc.get("expected", ""),
        "actual": fc.get("actual", ""),
    }
    spec = _FIXTURES_ACTION_TABLE.get(cid)
    if spec is None:
        spec = _FIXTURES_SKELETON_SPEC if cid.endswith(_FIXTURES_SKELETON_SUFFIXES) else _FIXTURES_UNKNOWN_SPEC
    action_type, to_action_fn = spec
    return {**base, "type": action_type, "to_action": to_action_fn(base)}


def build_upgrade_plan(
    current_format: Optional[str],
    legacy: Dict[str, object],
    fixtures_check: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """legacy + fixtures 发现 → agent 可执行 plan（fixtures_actions 优先于 actions，两套都跑）。

    每个 action 含 file / type / rule_ref / to_action；消费流程见 ref/upgrade-workflow.md。
    """
    today = date.today().isoformat()
    actions = []  # type: List[Dict[str, object]]
    fixtures_actions = []  # type: List[Dict[str, object]]

    for entry in legacy["patterns"]["type-memory-value"]:  # type: ignore
        fpath = entry["file"]  # type: ignore
        actions.append(
            {
                "file": fpath,
                "type": "frontmatter-retype",
                "rule_ref": LEGACY_PATTERN_KEYS["type-memory-value"],
                "to_action": (
                    f"Edit {fpath}：把 frontmatter 的 `type: memory` 按页面真实语义改为内容页类型之一"
                    f"（{TYPES_DISPLAY}）。**不要**改成"
                    " `memory-entry`——那是 MEMORY 桶扩展值，写进内容页语义错且不再触发本检查"
                ),
            }
        )

    # base 字段含 expected/actual，让 agent 一眼看清"该改成什么"
    if fixtures_check and not fixtures_check.get("skipped"):
        for fc in fixtures_check.get("checks", []) or []:  # type: ignore
            if fc.get("passed") is not False:  # type: ignore
                continue
            fixtures_actions.append(_build_fixtures_action(fc))  # type: ignore

    plan = {
        "generated_at": today,
        "from_version": current_format,
        "to_version": CURRENT_WIKI_FORMAT,
        "skill_doc": "SKILL.md（yzr-llm-wiki-management skill 根）",
        "format_doc": "ref/lint-workflow.md（yzr-llm-wiki-management skill，lint 流程与 --explain 入口）",
        "rule_doc": "ref/upgrade-workflow.md（yzr-llm-wiki-management skill）",
        "actions": actions,
        "fixtures_actions": fixtures_actions,
        "skipped_conflicts": legacy.get("conflicts", []),  # type: ignore
        "agent_rules": [
            "按 actions[] 顺序逐项修；每个 action 前打印依据 rule_ref",
            "frontmatter-retype：按 action.to_action 落（内容页 `type: memory` 改内容页类型之一，不要改 `memory-entry`）",
            "skipped_conflicts[] 永远不自动覆盖——转人工",
            "AGENTS.md / CLAUDE.md 是 byte-owned 禁手改：版本行与骨架均由 `llmw wiki upgrade --apply` 重渲染落地",
            "不写 log 条目（迁移是脚本运行，不是 wiki 操作事件）",
            "不调 ingest / query——保持职责单一（lint --check-version 是本迁移的正路）",
            "fixtures_actions[] 与 actions[] 平行处理——先走 fixtures_actions 修约定文件（如 .gitignore / anchor TOML）",
            "再走 actions[] 修内容页 frontmatter / log；fixtures 修复是后续内容页编辑的前置",
            "fixtures-fix-anchor-schema / -anchor-symlink-matches 各 to_action 自含修 schema / ln / 补 entry 的具体指令",
            "fixtures-fix-strip-frontmatter 仅删首部 frontmatter 块，保留全文正文一字不动",
            "fixtures-fix-skeleton：按 expected（缺失骨架信号清单）补 frontmatter 键 / H1 / 说明块 / 段标题 / .gitignore 段，单 Edit 可落；成长型内容（index 类别 / log 历史 / MEMORY 经验 / tag bullet）不动",
            "fixtures-fix-agents-md-resync / -agents-version：跑 `llmw wiki upgrade --apply`（CLI 重渲染 byte-owned）；本地定制先按 blocked_drift 与用户裁定搬 MEMORY/ 或丢弃",
            "fixtures 改造配合 upgrade-workflow.md#语义合并规则——结构性合规由 fixtures-fix-* 完成，跨条目语义合并由 LLM 按该节判断",
        ],
    }  # type: Dict[str, object]
    return plan


def cmd_check_version(wiki_root: Path, apply: bool, json_mode: bool) -> int:
    """--check-version 主入口：版本 + legacy 探测 + fixtures check。

    默认只打印报告；--apply 把 upgrade plan 输出到 stdout（不落盘）。
    """
    current_format = parse_format_version(wiki_root)
    comparison = _compare_semver(current_format, CURRENT_WIKI_FORMAT)
    legacy = detect_legacy_patterns(wiki_root)

    total_patterns = 0
    for entries in legacy["patterns"].values():  # type: ignore
        total_patterns += len(entries)  # type: ignore
    needs_upgrade = (comparison == "older") or (total_patterns > 0)

    fixtures_check = _run_fixtures_check(wiki_root)
    if not fixtures_check.get("skipped"):
        # fixtures 不合规（error/warn）也算"待迁移"
        f_sum = fixtures_check.get("summary", {})  # type: ignore
        if f_sum.get("error", 0) > 0 or f_sum.get("warn", 0) > 0:  # type: ignore
            needs_upgrade = True

    report = {
        "current_format": current_format,
        "skill_format": CURRENT_WIKI_FORMAT,
        "comparison": comparison,
        "needs_upgrade": needs_upgrade,
        "legacy_patterns": legacy["patterns"],  # type: ignore
        "conflicts": legacy["conflicts"],  # type: ignore
        "fixtures_check": fixtures_check,
    }

    if json_mode:
        if apply:
            plan = build_upgrade_plan(current_format, legacy, fixtures_check)
            report["upgrade_plan"] = plan
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print("=== Wiki Format 版本检查 ===")
    print(f"  current_format : {current_format or '(解析失败)'}")
    print(f"  skill_format   : {CURRENT_WIKI_FORMAT}")
    print(f"  comparison   : {comparison}")
    print(f"  needs_upgrade: {needs_upgrade}")
    print()

    if comparison == "newer":
        print(f"[WARN] wiki 用比 llmw 支持版本更新的 format（{current_format} > {CURRENT_WIKI_FORMAT}）")
        print("       请更新 llmw 安装；本子命令不会修改 wiki")
        print()
        _print_fixtures_check(fixtures_check, indent="")
        return 0

    if current_format is None:
        print("[WARN] 无法解析 <wiki-root>/AGENTS.md 末尾「当前配置」表 `Wiki Format 版本`")
        print("       请确认该行存在且格式为: | Wiki Format 版本 | 0.x.y |")
        print("       解析失败不影响 legacy pattern 探测（下方继续输出）")
        print()

    legacy_empty = total_patterns == 0 and not legacy["conflicts"]  # type: ignore
    fixtures_skipped = bool(fixtures_check.get("skipped"))
    fixtures_empty = fixtures_skipped or not any(
        c.get("passed") is False
        for c in fixtures_check.get("checks", [])  # type: ignore
    )
    if legacy_empty and fixtures_empty:
        print("No legacy patterns / fixtures issues found. ✓")
        return 0

    if not legacy_empty:
        print(f"[LEGACY] 共 {total_patterns} 处老格式现场")
        for pattern_key, entries in legacy["patterns"].items():  # type: ignore
            if not entries:  # type: ignore
                continue
            rule_ref = LEGACY_PATTERN_KEYS.get(pattern_key, "?")
            print(f"  - {pattern_key} ({len(entries)}) → {rule_ref}")
            for entry in entries:  # type: ignore
                flag = " [CONFLICT]" if entry.get("conflict") else ""  # type: ignore
                print(f"      {entry['file']}{flag}")  # type: ignore

        if legacy["conflicts"]:  # type: ignore
            print()
            print(f"[CONFLICTS] {len(legacy['conflicts'])} 处冲突页——agent 不自动覆盖")  # type: ignore
            for c in legacy["conflicts"]:  # type: ignore
                print(f"  - {c['file']}: {c['reason']}")  # type: ignore

    _print_fixtures_check(fixtures_check, indent="")

    if apply:
        plan = build_upgrade_plan(current_format, legacy, fixtures_check)
        print("\n[PLAN] upgrade plan 已生成（stdout JSON 输出，agent 直接消费，不落盘）")
        print(
            f"       actions: {len(plan['actions'])}, skipped_conflicts: {len(plan['skipped_conflicts'])}, "  # type: ignore
            f"fixtures_actions: {len(plan.get('fixtures_actions', []))}"  # type: ignore
        )
        print("       agent 按 plan.actions[] + plan.fixtures_actions[] 走 Edit/Write 修复（规则见 plan.rule_doc）")
        print("--- upgrade-plan JSON begin ---")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        print("--- upgrade-plan JSON end ---")
    else:
        print()
        print("[HINT] 加 --apply 输出 upgrade plan（stdout JSON）供 agent 走 Edit/Write 修复（默认 dry-run）")
        print("       加 --json  输出机器可读 JSON")

    return 0


def _print_fixtures_check(fixtures_check: Dict[str, object], indent: str = "") -> None:
    """人读打印 fixtures-check 段（跑挂时一行 skip）。"""
    if fixtures_check.get("skipped"):
        print(f"{indent}[FIXTURES] skipped: {fixtures_check.get('reason', '(unknown)')}")
        return
    checks = fixtures_check.get("checks", [])  # type: ignore
    summary = fixtures_check.get("summary", {})  # type: ignore
    print(
        f"{indent}[FIXTURES] error={summary.get('error', 0)} "  # type: ignore
        f"warn={summary.get('warn', 0)} "  # type: ignore
        f"pass={summary.get('pass', 0)} "  # type: ignore
        f"skip={summary.get('skip', 0)}"  # type: ignore
    )
    failed = [c for c in checks if c.get("passed") is False]  # type: ignore
    if not failed:
        return
    print(f"{indent}  - failed:")
    for c in failed:
        sev = str(c.get("severity", "")).upper()  # type: ignore
        cid = c.get("id", "")  # type: ignore
        fpath = c.get("file", "")  # type: ignore
        rr = c.get("rule_ref", "")  # type: ignore
        print(f"{indent}      [{sev}] {cid} ({fpath})")
        if c.get("expected"):  # type: ignore
            print(f"{indent}          期望: {c['expected']}")  # type: ignore
        if c.get("actual"):  # type: ignore
            print(f"{indent}          实际: {c['actual']}")  # type: ignore
        if rr:
            print(f"{indent}          rule: {rr}")


def run(
    wiki_root: Path,
    *,
    severity: str = "all",
    no_git: bool = False,
    check_version: bool = False,
    apply: bool = False,
    json_mode: bool = False,
) -> int:
    """lint 业务入口（flag SSOT 在 llmw.cli argparse 树）。

    no_git=True 完全不检测 git；否则按 `.git/` 自动决定（裸目录树 wiki 默认支持）。
    """
    if not (wiki_root / "wiki").is_dir():
        print(f"ERROR: {wiki_root}/wiki 不存在（wiki 还没 setup？）", file=sys.stderr)
        return 2

    effective_use_git = not no_git

    # --check-version 是互斥模式：只跑版本扫描
    if check_version:
        return cmd_check_version(wiki_root, apply=apply, json_mode=json_mode)

    all_findings = []  # type: List[str]
    info_notes = []  # type: List[str]  # 说明性输出，不受 --severity 过滤
    all_findings.extend(check_format_version(wiki_root))
    raw_findings, raw_skip = check_raw_immutable(wiki_root, effective_use_git)
    all_findings.extend(raw_findings)
    if raw_skip:
        info_notes.append(raw_skip)
    all_findings.extend(check_frontmatter(wiki_root))
    all_findings.extend(check_frontmatter_structure(wiki_root))
    all_findings.extend(check_link_integrity(wiki_root))
    all_findings.extend(check_index_coverage(wiki_root))
    all_findings.extend(check_index_section_placement(wiki_root))
    all_findings.extend(check_log_format(wiki_root))
    all_findings.extend(check_log_truncation(wiki_root))
    all_findings.extend(check_stale_summaries(wiki_root))
    all_findings.extend(check_filename_kebab(wiki_root))
    all_findings.extend(check_duplicate_titles(wiki_root))
    all_findings.extend(check_tag_taxonomy(wiki_root))
    all_findings.extend(check_external_symlinks(wiki_root))
    all_findings.extend(check_page_size(wiki_root))
    all_findings.extend(check_quality_signals(wiki_root))
    all_findings.extend(check_memory_index(wiki_root))
    all_findings.extend(check_related_links(wiki_root))

    if severity != "all":
        threshold = SEV_RANK[severity]
        all_findings = [f for f in all_findings if SEV_RANK[severity_of(f)] <= threshold]

    if info_notes:
        print("\n[NOTES]")
        for n in info_notes:
            print(f"  {n}")

    if not all_findings:
        print("No issues found. ✓")
        return 0

    by_sev = {"error": [], "warn": [], "info": []}  # type: Dict[str, List[str]]
    for f in all_findings:
        by_sev[severity_of(f)].append(f)

    for sev in ("error", "warn", "info"):
        if by_sev[sev]:
            print(f"\n[{sev.upper()}] ({len(by_sev[sev])})")
            for f in by_sev[sev]:
                print(f"  {f}")

    print()
    print(f"Total: {len(all_findings)} finding(s)")
    return 1
