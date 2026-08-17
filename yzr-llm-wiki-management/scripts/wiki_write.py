#!/usr/bin/env python3
"""wiki_write.py — 机械字节写操作（scripts 持有形式，agent 持有判断）

准入规则（yzr-skill-creator 审计标准「机械操作脚本化」）：一个写操作进脚本，当且仅当
(1) 输出字节是输入的纯函数——不读正文内容、无权衡、无用户偏好；(2) lint 已有对应检查
能验证产物。五个子命令都满足两条。手写永远是 schema 合法的、lint 兜底——本脚本是
**默认路径不是闸门**（agent 遇到脚本不支持的形态，退到 Edit/Write 不算违规）。

子命令：
  log     追加 wiki/log.md 条目（严格格式；写完自动截断保最近 LOG_RETENTION_LIMIT 条）
          `python3 wiki_write.py <WIKI_ROOT> log --op ingest --title "..." [--title "..." ...]`
          `python3 wiki_write.py <WIKI_ROOT> log --op ingest --bulk --topic "..." --count N`
  index   增删 wiki/index.md 条目（从页 frontmatter 派生 title/description，类别段内字母序）
          `python3 wiki_write.py <WIKI_ROOT> index add <wiki/sources/foo.md>`
          `python3 wiki_write.py <WIKI_ROOT> index remove <wiki/sources/foo.md>`
  touch   编辑后更新：`updated`=现在 + 删 `reviewed` / `reviewed_at`（清审核戳）
          `python3 wiki_write.py <WIKI_ROOT> touch <wiki/concepts/foo.md>`
  new     新建内容页脚手架（frontmatter + H1；**不生成正文**——正文模板 SSOT 在
          references/page-templates.md，避免双源）
          `python3 wiki_write.py <WIKI_ROOT> new --type source --slug foo --title "Foo" --sources raw/articles/foo.md [--description ...] [--tags a,b]`
  memory  新建 MEMORY 条目（仅 title 必填 frontmatter）+ 原子追加 MEMORY.md 索引行
          `python3 wiki_write.py <WIKI_ROOT> memory add --slug foo --title "Foo" [--index-line "一句话"]`

版本错位警告：wiki §八 钉定版本与 SKILL 的 CURRENT_WIKI_SPEC 不一致时警告"先 migrate 再写"
——防新格式写进老 wiki。只警告不阻断（逃生舱：用户对老 wiki 有意写入时仍可用）。

退出码：0 = 成功（含 no-op）；2 = 运行错误 / 参数错误。
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_diff import parse_frontmatter_simple  # noqa: E402
from lint_wiki import (  # noqa: E402
    CURRENT_WIKI_SPEC,
    LOG_RETENTION_LIMIT,
    SOURCE_NAME_RE,
    parse_spec_version,
)
from log_format import LOG_LINE_RE  # noqa: E402

# wiki 5 类内容页（非 MEMORY 扩展类型）→ 子目录 + index.md 类别段
_TYPE_TO_DIR = {
    "entity": "entities",
    "concept": "concepts",
    "source": "sources",
    "comparison": "comparisons",
    "synthesis": "syntheses",
}
_CONTENT_TYPES = set(_TYPE_TO_DIR.keys())
_TYPE_TO_SECTION = {
    "entity": "Entities",
    "concept": "Concepts",
    "source": "Sources",
    "comparison": "Comparisons",
    "synthesis": "Syntheses",
}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_INDEX_ENTRY_RE = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)(.*)$")
_SECTION_RE = re.compile(r"^##\s+(.+)$")
_PLACEHOLDER_RE = re.compile(r"^_\s*（暂无内容）\s*_$")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _warn_version(wiki_root):
    """wiki §八 钉定版本与 SKILL 不一致时打警告（stderr，不阻断）"""
    pinned = parse_spec_version(Path(wiki_root))
    if pinned and pinned != CURRENT_WIKI_SPEC:
        print(
            f"[WARN] wiki 钉定 spec {pinned}，与 SKILL {CURRENT_WIKI_SPEC} 不一致——"
            f"建议先跑 `lint_wiki.py --check-version --apply` 完成迁移再写入",
            file=sys.stderr,
        )


def _log_body_start(text):
    """跳过 frontmatter，返回正文起始偏移（与 lint check_log_format 同口径）"""
    if text.startswith("---"):
        m = _FRONTMATTER_RE.match(text)
        if m:
            return m.end()
    return 0


# ---------- log ----------


def cmd_log(wiki_root, args):
    log_path = Path(wiki_root) / "wiki" / "log.md"
    if not log_path.is_file():
        return "log-missing: wiki/log.md 不存在", 2
    if args.bulk:
        if not args.topic or args.count is None:
            return "log --bulk 需 --topic 与 --count", 2
        lines = [f"## [{_now()}] {args.op} | Bulk: {args.topic} ({args.count} sources)"]
    else:
        if not args.title:
            return "log 需至少一个 --title（或 --bulk）", 2
        bad = [t for t in args.title if not t.strip() or "\n" in t]
        if bad:
            return "log 标题必须非空且单行", 2
        lines = [f"## [{_now()}] {args.op} | {t.strip()}" for t in args.title]
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if not text.endswith("\n"):
        text += "\n"
    for line in lines:
        if not LOG_LINE_RE.match(line):
            return f"生成的 log 行格式非法（不该发生）：{line}", 2
        text += line + "\n"
    body_start = _log_body_start(text)
    body = text[body_start:]
    entry_idx = [i for i, ln in enumerate(body.splitlines()) if LOG_LINE_RE.match(ln)]
    if len(entry_idx) > LOG_RETENTION_LIMIT:
        cut = entry_idx[-LOG_RETENTION_LIMIT]
        body = "\n".join(body.splitlines()[cut:]) + "\n"
        text = text[:body_start] + body
        print(
            f"log 条目数超过 {LOG_RETENTION_LIMIT}，已截断保最近 {LOG_RETENTION_LIMIT} 条"
            "（完整历史见 git log -p -- wiki/log.md）",
            file=sys.stderr,
        )
    log_path.write_text(text, encoding="utf-8")
    print(f"已追加 {len(lines)} 条 log 条目到 wiki/log.md", file=sys.stderr)
    return None, 0


# ---------- index ----------


def _index_page_paths(wiki_root, page_arg):
    """把 index add/remove 的 <wiki/...> 参数规范化为 wiki 根相对 posix 路径

    参数基准：相对 wiki 根（`wiki/sources/foo.md`）；绝对路径也接受。
    目标页必须已存在（index add 需要读 frontmatter；remove 需要定位条目）。
    """
    p = Path(page_arg)
    if not p.is_absolute():
        p = Path(wiki_root) / p
    try:
        rel = p.resolve().relative_to(Path(wiki_root).resolve()).as_posix()
    except ValueError:
        return None
    if not rel.endswith(".md") or "/" not in rel:
        return None
    return rel


def _index_link_for(rel):
    """index.md（在 wiki/ 内）视角的链接：`wiki/sources/foo.md` → `sources/foo.md`"""
    parts = rel.split("/")
    return "/".join(parts[1:])


def cmd_index(wiki_root, args):
    index_path = Path(wiki_root) / "wiki" / "index.md"
    if not index_path.is_file():
        return "index-missing: wiki/index.md 不存在", 2
    rel = _index_page_paths(wiki_root, args.page)
    if rel is None:
        return f"index 参数必须是 wiki/ 内的 .md 页：{args.page}", 2
    link = _index_link_for(rel)
    text = index_path.read_text(encoding="utf-8", errors="replace")

    page_path = Path(wiki_root) / rel
    if args.action == "remove":
        lines = text.splitlines(keepends=True)
        out = []
        removed = False
        for line in lines:
            m = _INDEX_ENTRY_RE.match(line)
            if m and m.group(2).strip() == link:
                removed = True
                continue
            out.append(line)
        if not removed:
            return f"index 中未找到指向 {link} 的条目", 2
        index_path.write_text("".join(out), encoding="utf-8")
        print(f"已从 wiki/index.md 移除 {link} 条目", file=sys.stderr)
        return None, 0

    if not page_path.is_file():
        return f"index add 目标页不存在：{rel}", 2
    fm = parse_frontmatter_simple(page_path.read_text(encoding="utf-8", errors="replace"))
    title = str(fm.get("title", "")).strip()
    if not title:
        return "index add 需要目标页 frontmatter 含非空 title", 2
    section = _TYPE_TO_SECTION.get(str(fm.get("type", "")).strip())
    if section is None:
        return "index add 需要目标页 type 为 5 类内容页之一（当前: {}）".format(fm.get("type")), 2
    desc = str(fm.get("description", "")).strip()
    entry = "- [{}]({}){}".format(title, link, (" — " + desc) if desc else "")

    lines = text.splitlines(keepends=True)
    existing_links = {m.group(2).strip() for m in (_INDEX_ENTRY_RE.match(ln) for ln in lines) if m}
    if link in existing_links:
        return f"index 已存在指向 {link} 的条目，跳过", 0

    in_section = False
    seen_target = False
    section_lines = []
    out = []
    for line in lines:
        m = _SECTION_RE.match(line.strip())
        if m:
            if in_section:
                in_section = False
            out.append(line)
            in_section = m.group(1).strip() == section
            if in_section:
                seen_target = True
            continue
        if in_section:
            section_lines.append(line)
        else:
            out.append(line)
    if not seen_target:
        return f"wiki/index.md 缺 `## {section}` 类别段（按 page-templates §6 骨架补）", 2

    entries = [_INDEX_ENTRY_RE.match(ln) for ln in section_lines if _INDEX_ENTRY_RE.match(ln)]
    if entries:
        insert_at = len(section_lines)
        for i, m in enumerate(entries):
            if m.group(1).strip().lower() > title.lower():
                insert_at = section_lines.index(entries[i].string)
                break
        section_lines.insert(insert_at, entry + "\n")
    else:
        kept = [ln for ln in section_lines if not _PLACEHOLDER_RE.match(ln.strip())]
        section_lines = kept
        if section_lines and not section_lines[-1].endswith("\n"):
            section_lines[-1] += "\n"
        section_lines.append(entry + "\n")
    index_path.write_text("".join(out + section_lines), encoding="utf-8")
    print(f"已在 wiki/index.md `## {section}` 段添加 {link} 条目", file=sys.stderr)
    return None, 0


# ---------- touch ----------


def cmd_touch(wiki_root, args):
    page_path = Path(wiki_root) / args.page
    if not page_path.is_file():
        return f"touch 目标页不存在：{args.page}", 2
    text = page_path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return f"touch 目标页无 frontmatter：{args.page}", 2
    now = _now()
    block_lines = m.group(1).splitlines()
    changed = []
    new_lines = []
    for line in block_lines:
        if re.match(r"^updated:\s*", line):
            new_lines.append(f"updated: {now}")
            changed.append(f"updated→{now}")
        elif re.match(r"^(reviewed|reviewed_at):\s*", line):
            changed.append("删 {}".format(line.split(":", 1)[0]))
            continue
        else:
            new_lines.append(line)
    if f"updated: {now}" not in new_lines:
        new_lines.append(f"updated: {now}")
        changed.append(f"补 updated={now}")
    new_block = "---\n" + "\n".join(new_lines) + "\n---"
    page_path.write_text(new_block + text[m.end() :], encoding="utf-8")
    print("touch {}：{}".format(args.page, "；".join(changed) if changed else "无改动"), file=sys.stderr)
    return None, 0


# ---------- new ----------


def cmd_new(wiki_root, args):
    if args.type not in _CONTENT_TYPES:
        return "new --type 必须是 5 类内容页之一（{}）".format(", ".join(sorted(_CONTENT_TYPES))), 2
    if not SOURCE_NAME_RE.match(args.slug):
        return f"new --slug 必须是小写 kebab-case（^[a-z0-9][a-z0-9-]*$）：{args.slug}", 2
    if not args.title.strip():
        return "new --title 必须非空", 2
    page_path = Path(wiki_root) / "wiki" / _TYPE_TO_DIR[args.type] / (args.slug + ".md")
    if page_path.is_file():
        return f"new 目标页已存在（如需更新用 Edit）：{page_path}", 2
    if args.type == "source" and not args.sources:
        return "new --type source 必须提供 --sources（lint §二.3 sources 非空是 error）", 2

    now = _now()
    fm_lines = ["---", f'title: "{args.title}"']
    if args.description:
        fm_lines.append(f'description: "{args.description}"')
    fm_lines.append(f"type: {args.type}")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    fm_lines.append("tags: [{}]".format(", ".join(tags)))
    fm_lines.append(f"created: {now}")
    fm_lines.append(f"updated: {now}")
    if args.sources:
        fm_lines.append("sources:")
        fm_lines.extend(f"  - {s}" for s in args.sources)
    fm_lines.append("---")
    body = f"\n\n# {args.title}\n"
    page_path.write_text("\n".join(fm_lines) + body, encoding="utf-8")
    print(f"已创建 {page_path}（正文待 agent 按 page-templates.md 填充）", file=sys.stderr)
    return None, 0


# ---------- memory ----------


def cmd_memory(wiki_root, args):
    if not SOURCE_NAME_RE.match(args.slug):
        return f"memory add --slug 必须是小写 kebab-case：{args.slug}", 2
    if not args.title.strip():
        return "memory add --title 必须非空", 2
    mem_dir = Path(wiki_root) / "MEMORY"
    entry_path = mem_dir / (args.slug + ".md")
    if entry_path.is_file():
        return f"memory 条目已存在：{entry_path}", 2
    index_path = mem_dir / "MEMORY.md"
    if not index_path.is_file():
        return "memory add 需要 MEMORY/MEMORY.md 索引存在（缺失走 migrate 补，不自动创建）", 2
    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    if "## 索引" not in index_text:
        return "MEMORY/MEMORY.md 缺 `## 索引` 段", 2

    entry_path.write_text(f'---\ntitle: "{args.title}"\n---\n\n', encoding="utf-8")
    if not index_text.endswith("\n"):
        index_text += "\n"
    index_line = "- [{}]({}.md){}".format(
        args.title,
        args.slug,
        (" — " + args.index_line) if args.index_line else "",
    )
    index_path.write_text(index_text + index_line + "\n", encoding="utf-8")
    print(f"已创建 MEMORY/{args.slug}.md + 追加 MEMORY.md 索引行（正文待 agent 写）", file=sys.stderr)
    return None, 0


# ---------- main ----------


def main(argv=None):
    parser = argparse.ArgumentParser(description="wiki 机械字节写操作（见 docstring 准入规则）")
    parser.add_argument("wiki_root", help="wiki 根目录（含 AGENTS.md / wiki/ / MEMORY/）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_log = sub.add_parser("log", help=f"追加 log.md 条目（自动截断保最近 {LOG_RETENTION_LIMIT} 条）")
    p_log.add_argument("--op", required=True, choices=["ingest", "query", "lint", "setup"])
    p_log.add_argument("--title", action="append", help="条目标题（可重复）")
    p_log.add_argument("--bulk", action="store_true", help="批量摄取模式（Bulk: <topic> (<N> sources)）")
    p_log.add_argument("--topic", help="--bulk 用的主题概览")
    p_log.add_argument("--count", type=int, help="--bulk 用的 source 数")
    p_log.set_defaults(func=cmd_log)

    p_index = sub.add_parser("index", help="增删 index.md 条目（派生自页 frontmatter）")
    p_index.add_argument("action", choices=["add", "remove"])
    p_index.add_argument("page", help="wiki/ 内页面路径，如 wiki/sources/foo.md")
    p_index.set_defaults(func=cmd_index)

    p_touch = sub.add_parser("touch", help="编辑后更新 updated + 清 reviewed 戳")
    p_touch.add_argument("page", help="wiki/ 内页面路径，如 wiki/concepts/foo.md")
    p_touch.set_defaults(func=cmd_touch)

    p_new = sub.add_parser("new", help="新建内容页脚手架（frontmatter + H1）")
    p_new.add_argument("--type", required=True, help="5 类内容页之一")
    p_new.add_argument("--slug", required=True, help="kebab-case 文件名")
    p_new.add_argument("--title", required=True)
    p_new.add_argument("--description", default="")
    p_new.add_argument("--tags", default="", help="逗号分隔 tag 列表")
    p_new.add_argument("--sources", action="append", help="raw/ 相对路径（type=source 必填，可重复）")
    p_new.set_defaults(func=cmd_new)

    p_mem = sub.add_parser("memory", help="新建 MEMORY 条目 + 原子索引行")
    p_mem.add_argument("action", choices=["add"])
    p_mem.add_argument("--slug", required=True)
    p_mem.add_argument("--title", required=True)
    p_mem.add_argument("--index-line", default="", help="索引行一句话摘要")
    p_mem.set_defaults(func=cmd_memory)

    args = parser.parse_args(argv)
    _warn_version(args.wiki_root)
    err, code = args.func(args.wiki_root, args)
    if err:
        print(err, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
