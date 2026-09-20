#!/usr/bin/env python3
"""ingest_diff — 找出 raw/ 里需要 LLM 关注的文件（`llmw wiki ingest-diff`）。

"已摄取"判定 = source 页 frontmatter.sources ∪ log.md ingest 记录（新条目 raw 路径
精确命中 / 老条目标题 slug 归一化兜底）。三类输出：
untracked（未摄取）/ stale-raw（--check-stale：raw mtime 晚于 source updated）/
log-only-no-source-page（log 有记录但 source 页缺失）。

stdout 保持纯路径（--json / --relative 可换格式）；计数总结走 stderr。退出码 0/1/2。
"""

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Set, Tuple

# log 行格式正则 + created/updated 时间解析 SSOT 来自 log_format 模块
from llmw.content.log_format import LOG_INGEST_RE, parse_date_or_datetime

# 简易 YAML frontmatter 解析（不依赖 pyyaml，避免 setup 阶段的依赖膨胀）
# 支持最常见的 key: value 形式（含数组、字符串）
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter_simple(text: str) -> Dict:
    """轻量 YAML frontmatter 解析；只处理 skill 实际写出的格式

    空值语义：`key:`（无值）先挂起——下一行若是 "  - item" 列表项则按 list 解析，
    否则落定为空字符串；`key: []` 是立即的空 list（后续跟随的列表项不再吸收）。
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    result = {}  # type: Dict[str, object]
    pending_key = None  # type: Optional[str]  # `key:` 空值——等下一行确认 list 还是空标量
    current_list_key = None  # type: Optional[str]
    current_list_items = []  # type: List[str]

    def _flush_list():
        nonlocal current_list_key, current_list_items
        if current_list_key is not None:
            result[current_list_key] = current_list_items
            current_list_key = None
            current_list_items = []

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        # 列表项（仅当上一行是 `key:` 空值 或已在列表内）
        list_match = re.match(r"^\s+-\s+(.+?)\s*$", line)
        if list_match and (pending_key is not None or current_list_key is not None):
            if pending_key is not None:
                current_list_key = pending_key
                pending_key = None
            current_list_items.append(list_match.group(1).strip())
            continue
        # 新 key 前收尾：挂起的空值按空字符串落定；上个 list 提交
        if pending_key is not None:
            result[pending_key] = ""
            pending_key = None
        _flush_list()
        # 新 key: value
        kv_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not kv_match:
            continue
        key = kv_match.group(1)
        val = kv_match.group(2).strip()
        if val == "":
            pending_key = key
        elif val == "[]":
            result[key] = []
        elif val.startswith("[") and val.endswith("]"):
            # inline 数组
            inner = val[1:-1].strip()
            if not inner:
                result[key] = []
            else:
                items = [x.strip().strip("\"'") for x in inner.split(",")]
                result[key] = items
        else:
            # 普通字符串（去引号）
            result[key] = val.strip("\"'")
    # 收尾
    if pending_key is not None:
        result[pending_key] = ""
    _flush_list()
    return result


INGEST_GLOBS = ("*.md", "*.markdown", "*.txt")


def collect_raw_files(raw_root: Path) -> List[Path]:
    """递归收集 raw/ 下可摄取的文本素材（排除 assets/ 与 discussions/ 子树、隐藏 / 系统文件）。

    assets/ 是图片 / 附件终态（不该被当 untracked 信号）；discussions/ 是协作草稿层，
    列出来会诱导 LLM 把自己写的草稿当 raw 真相 ingest（provenance 后门）——转正先 mv 到
    raw/articles 等子树。
    """
    if not raw_root.is_dir():
        return []
    files = []  # type: List[Path]
    seen = set()  # type: Set[str]
    # assets/ + discussions/ 子树整体跳过（rglob 会先遍历到，命中后按祖先过滤）
    skip_dirs = {raw_root / "assets", raw_root / "discussions"}
    for pattern in INGEST_GLOBS:
        for p in raw_root.rglob(pattern):
            if not p.is_file():
                continue
            if any(parent in skip_dirs for parent in p.parents):
                continue
            name = p.name
            if name.startswith("."):
                continue
            if name == "Thumbs.db":
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            files.append(p)
    return files


def normalize_rel(path: Path, base: Path) -> str:
    """把绝对路径转成相对 base 的 POSIX 风格字符串"""
    rel = path.relative_to(base)
    return rel.as_posix()


def _slugify(s: str) -> str:
    """标题 / 文件名 → kebab-case slug（对齐 `write new --slug` 约定）；无可归一字符 → ""。

    log 标题是 source 页 title、raw 比对对象是文件名 stem，两者只在命名对齐时同源——
    slug 归一化把 "Attention Is All You Need" 与 stem `attention-is-all-you-need` 对上。
    """
    return re.sub(r"[^a-z0-9]+", "-", s.strip().lower()).strip("-")


def collect_ingested_from_log(log_path: Path) -> Tuple[Set[str], Set[str]]:
    """从 log.md 提取 ingest 记录 → (标题集合, raw 相对路径集合)。

    新条目（write log --raw）带 raw 路径 → 精确命中；老条目只有 title → 调用方
    slug 归一化兜底（提示性；"已摄取"判定主要靠 source 页 frontmatter）。
    """
    titles = set()  # type: Set[str]
    raw_paths = set()  # type: Set[str]
    if not log_path.is_file():
        return titles, raw_paths
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = LOG_INGEST_RE.match(line)
        if m:
            titles.add(m.group("title").strip())
            if m.group("raw"):
                raw_paths.add(m.group("raw").strip())
    return titles, raw_paths


def collect_ingested_sources_map(wiki_root: Path) -> Dict[str, List[Path]]:
    """frontmatter.sources → raw 相对路径（POSIX）到引用页列表的映射。"""
    mapping = {}  # type: Dict[str, List[Path]]
    sources_dir = wiki_root / "wiki" / "sources"
    if not sources_dir.is_dir():
        return mapping
    for p in sources_dir.glob("*.md"):
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        srcs = fm.get("sources", [])
        if isinstance(srcs, list):
            for s in srcs:
                if isinstance(s, str):
                    mapping.setdefault(s.strip(), []).append(p)
    return mapping


def raw_newer_than_source(raw_path: Path, source_page: Path) -> bool:
    """raw mtime 日期是否晚于 source 页 updated；无法判定（缺 / 格式错）返 False（不误报）。"""
    text = source_page.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter_simple(text)
    updated = fm.get("updated")
    upd_date = parse_date_or_datetime(updated)
    if upd_date is None:
        return False
    try:
        raw_date = date.fromtimestamp(raw_path.stat().st_mtime)
    except OSError:
        return False
    return raw_date > upd_date


def run(wiki_root: Path, *, as_json: bool = False, relative: bool = False, check_stale: bool = False) -> int:
    """ingest-diff 业务入口（cli.py dispatch 直调；flag SSOT 在 llmw.cli argparse 树）。"""
    raw_root = wiki_root / "raw"
    if not raw_root.is_dir():
        print(f"ERROR: {raw_root} 不存在（wiki 还没 setup？）", file=sys.stderr)
        return 2

    raw_files = collect_raw_files(raw_root)
    src_map = collect_ingested_sources_map(wiki_root)
    ingested_paths = set(src_map.keys())
    log_titles, log_raw_paths = collect_ingested_from_log(wiki_root / "wiki" / "log.md")
    log_title_slugs = {_slugify(t) for t in log_titles} - {""}

    pending = []  # list of (Path, reason) tuples
    for p in raw_files:
        rel_to_root = normalize_rel(p, wiki_root)
        if rel_to_root in ingested_paths:
            if check_stale:
                for sp in src_map[rel_to_root]:
                    if raw_newer_than_source(p, sp):
                        pending.append((p, "stale-raw"))
                        break
            continue
        stem = p.stem
        # 新条目 raw 路径精确命中；老条目（无路径）走标题 slug 归一化兜底（启发式）
        if rel_to_root in log_raw_paths or _slugify(stem) in log_title_slugs:
            pending.append((p, "log-only-no-source-page"))
            continue
        pending.append((p, "untracked"))

    if as_json:
        out = []
        for p, reason in pending:
            rel = normalize_rel(p, wiki_root) if relative else normalize_rel(p, raw_root)
            stat = p.stat()
            out.append(
                {
                    "path": rel,
                    "abs_path": str(p),
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                    "reason": reason,
                }
            )
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not pending:
            print("All raw files are ingested. ✓")
        else:
            for p, _ in pending:
                if relative:
                    print(normalize_rel(p, wiki_root))
                else:
                    print(normalize_rel(p, raw_root))

    if pending:
        counts = {}  # type: Dict[str, int]
        for _, reason in pending:
            counts[reason] = counts.get(reason, 0) + 1
        parts = [f"{c} {r}" for r, c in counts.items()]
        print("Summary: {}".format(", ".join(parts)), file=sys.stderr)
        if counts.get("stale-raw"):
            print(
                "（stale-raw = raw 被用户更新过、需重新摄取；对应 source 页已存在，ingest 时走 Edit 而非 Write）",
                file=sys.stderr,
            )

    log_only = [pr for pr in pending if pr[1] == "log-only-no-source-page"]
    if log_only and not as_json:
        print(file=sys.stderr)
        print(
            f"WARN: {len(log_only)} 个文件在 log.md 中有 ingest 记录但对应的 source 页缺失，建议重建：", file=sys.stderr
        )
        for p, _ in log_only:
            print(f"  {p}", file=sys.stderr)

    return 1 if pending else 0
