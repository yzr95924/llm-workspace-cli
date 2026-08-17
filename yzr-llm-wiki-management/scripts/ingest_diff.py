#!/usr/bin/env python3
"""
ingest_diff.py — 找出 raw/ 里需要 LLM 关注的文件

用法：
  python3 ingest_diff.py [<WIKI_ROOT>] [--json] [--relative] [--check-stale]

判定"已摄取"的依据：
- 扫 <WIKI_ROOT>/raw/ 递归收集可摄取的文本素材（扩展名白名单：*.md / *.markdown / *.txt；
  见 INGEST_GLOBS）
- 读所有 wiki/sources/*.md 的 frontmatter.sources 字段，建立 raw 路径 → source 页映射
- 同时读 wiki/log.md 提取 ingest 条目标题（排查"log 写了但 source 页丢了"）

三类需要关注的文件：
1. **未摄取**（reason=untracked）——raw 路径不在任何 source 页的 sources 字段里
2. **待重新摄取**（reason=stale-raw，仅 --check-stale）——raw 路径已有 source 页，
   但 raw 文件 mtime 晚于 source 页 frontmatter.updated，说明 raw 被用户更新过
3. **log-only**（reason=log-only-no-source-page）——log 有 ingest 记录但 source 页缺失

输出：
- 默认 plain text：每行一个路径（stdout 保持纯路径，便于 grep / 循环）
- --json：JSON 数组 [{path, abs_path, size_bytes, mtime, reason}]
- --relative：输出相对 WIKI_ROOT 而非相对 raw/
- 人类可读的按类别计数总结打到 stderr

退出码：
- 0 = 全部已摄取（且 --check-stale 下无 stale 项）
- 1 = 有需要关注的项
- 2 = 运行错误
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Set

# log 行格式正则 + created/updated 时间解析 SSOT 来自 log_format 模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
from log_format import LOG_INGEST_RE, parse_date_or_datetime  # noqa: E402

# 简易 YAML frontmatter 解析（不依赖 pyyaml，避免 setup 阶段的依赖膨胀）
# 支持最常见的 key: value 形式（含数组、字符串）
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter_simple(text: str) -> Dict:
    """轻量 YAML frontmatter 解析；只处理 skill 实际写出的格式"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    result = {}  # type: Dict[str, object]
    current_list_key = None
    current_list_items = []  # type: List[str]
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        # 列表项
        list_match = re.match(r"^\s+-\s+(.+?)\s*$", line)
        if list_match and current_list_key is not None:
            current_list_items.append(list_match.group(1).strip())
            continue
        # 若是新 key：先把上一个 list 提交
        if current_list_key is not None:
            result[current_list_key] = current_list_items
            current_list_key = None
            current_list_items = []
        # 新 key: value
        kv_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not kv_match:
            continue
        key = kv_match.group(1)
        val = kv_match.group(2).strip()
        if val == "" or val == "[]":
            # 可能是 inline 列表或空数组——下一行若是 "  - item" 才算列表
            result[key] = []
            current_list_key = key
            current_list_items = []
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
    if current_list_key is not None:
        result[current_list_key] = current_list_items
    return result


# ingest 单元：raw/ 下被视为"可摄取素材"的扩展名白名单。
# 文本素材（md / txt / markdown）走 raw/{articles,clippings,papers,...}/
# 等任意子目录，rglob 递归扫；raw/assets/ 整棵子树跳过（用户放图片 / 二进制附件的地方，
# LLM 不该管它们是否"已摄取"——它们本身就是 raw 终态，不应被 source 页引用）；
# raw/discussions/ 整棵子树跳过（用户 + LLM 协作草稿层，spec §15——不是待摄取的
# 用户真相源，LLM 可写，不应被 ingest_diff 当 untracked 素材列出）。
INGEST_GLOBS = ("*.md", "*.markdown", "*.txt")


def collect_raw_files(raw_root: Path) -> List[Path]:
    """递归收集 raw/ 下可摄取的文本素材（排除 assets/ + discussions/ 子树与隐藏 / 系统文件）。

    为什么不收 raw/assets/：assets/ 是用户放图片 / 附件 / 二进制 PDF 的地方，
    引用关系走 raw/{articles,...} 下的 .md（md 内用相对路径链图）。把 png
    报为 untracked 会污染 ingest_diff 的信号。
    为什么不收 raw/discussions/：discussions/ 是用户 + LLM 双方可写的
    协作草稿层（spec §15），不是"用户掌控的真相源"——把它当 untracked 素材列出会
    诱导 LLM 把自己写的草稿当 raw 真相 ingest 回 wiki（provenance 后门）。草稿要转
    正式先由用户确认 mv 到 raw/articles 等子树（spec §15.3），mv 后才会被本函数扫到。
    """
    if not raw_root.is_dir():
        return []
    files = []  # type: List[Path]
    seen = set()  # type: Set[str]
    # assets/ + discussions/ 子树直接跳过（不去 glob 它们）
    skip_dirs = {raw_root / "assets", raw_root / "discussions"}
    for pattern in INGEST_GLOBS:
        for p in raw_root.rglob(pattern):
            if not p.is_file():
                continue
            # 任一祖先在 skip_dirs 集合里就跳过
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


def collect_ingested_from_log(log_path: Path) -> Set[str]:
    """从 wiki/log.md 提取 ingest 条目的标题集合。
    注意：log 只记标题，不直接给出 raw 路径；这里仅做提示性收集。
    实际"已摄取"判定主要靠 source 页 frontmatter。"""
    ingested = set()  # type: Set[str]
    if not log_path.is_file():
        return ingested
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = LOG_INGEST_RE.match(line)
        if m:
            ingested.add(m.group(1).strip())
    return ingested


def collect_ingested_sources_map(wiki_root: Path) -> Dict[str, List[Path]]:
    """读所有 wiki/sources/*.md 的 frontmatter.sources，返回
    raw 相对路径（POSIX）→ 引用它的 source 页列表。"""
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
    """raw 文件的 mtime 日期是否晚于 source 页 frontmatter.updated。
    若 updated 缺失 / 格式错 / mtime 不可读，视为"无法判定"，返回 False
    （保守起见不报 stale，避免误报）。updated 接受 `YYYY-MM-DD` 与 `YYYY-MM-DD HH:MM`
    两种格式（见 log_format.parse_date_or_datetime）。"""
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find files in raw/ that need LLM attention (untracked or, with --check-stale, updated)."
    )
    parser.add_argument("wiki_root", nargs="?", help="wiki 根目录；默认从 $LLM_WIKI_ROOT 读")
    parser.add_argument("--json", action="store_true", help="以 JSON 数组形式输出")
    parser.add_argument("--relative", action="store_true", help="输出相对 wiki_root 而非 raw/")
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="额外检查已摄取文件：raw mtime 晚于 source 页 updated → 标记 stale-raw（待重新摄取）",
    )
    args = parser.parse_args()

    # 决定 wiki_root
    if args.wiki_root:
        wiki_root = Path(args.wiki_root).expanduser().resolve()
    elif os.environ.get("LLM_WIKI_ROOT"):
        wiki_root = Path(os.environ["LLM_WIKI_ROOT"]).expanduser().resolve()
    else:
        print("ERROR: 需提供 wiki_root 参数或设置 $LLM_WIKI_ROOT", file=sys.stderr)
        return 2

    raw_root = wiki_root / "raw"
    if not raw_root.is_dir():
        print(f"ERROR: {raw_root} 不存在（wiki 还没 setup？）", file=sys.stderr)
        return 2

    raw_files = collect_raw_files(raw_root)
    src_map = collect_ingested_sources_map(wiki_root)
    ingested_paths = set(src_map.keys())
    log_titles = collect_ingested_from_log(wiki_root / "wiki" / "log.md")

    pending = []  # list of (Path, reason) tuples
    for p in raw_files:
        rel_to_root = normalize_rel(p, wiki_root)
        if rel_to_root in ingested_paths:
            # 已摄取——仅 --check-stale 时看 raw 是否被更新过
            if args.check_stale:
                for sp in src_map[rel_to_root]:
                    if raw_newer_than_source(p, sp):
                        pending.append((p, "stale-raw"))
                        break
            continue
        # 未摄取
        stem = p.stem
        if stem in log_titles:
            # log 有但 source 页丢了——标记为待重建
            pending.append((p, "log-only-no-source-page"))
            continue
        pending.append((p, "untracked"))

    # 输出
    if args.json:
        out = []
        for p, reason in pending:
            rel = normalize_rel(p, wiki_root) if args.relative else normalize_rel(p, raw_root)
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
                if args.relative:
                    print(normalize_rel(p, wiki_root))
                else:
                    print(normalize_rel(p, raw_root))

    # 人类可读总结 → stderr（保持 stdout 为纯路径列表）
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

    # log-only 异常提示
    log_only = [pr for pr in pending if pr[1] == "log-only-no-source-page"]
    if log_only and not args.json:
        print(file=sys.stderr)
        print(
            f"WARN: {len(log_only)} 个文件在 log.md 中有 ingest 记录但对应的 source 页缺失，建议重建：", file=sys.stderr
        )
        for p, _ in log_only:
            print(f"  {p}", file=sys.stderr)

    return 1 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
