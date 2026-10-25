#!/usr/bin/env python3
"""eval 夹具生成器：骨架现生成，仓内只存语义覆盖。

用法：``python3 scripts/test/build_wiki_eval.py CASE_ID DEST_DIR``

CASE_ID = ``eval/fixtures/`` 下的用例目录。其中每个含 ``build.conf`` 的子目录生成
一个 wiki 根（目录名 = llmw 的 wiki 名）。``build.conf`` 为 ``KEY = VALUE`` 行：

- ``topic`` / ``display_name`` / ``tag`` / ``description``：llmw wiki add 参数
- ``base``：语义基底名（``eval/fixtures/_bases/<base>/``），先拷基底再拷本目录覆盖
- ``orphans``：逗号分隔的 wiki/ 相对路径，跳过 index add（造 orphan-page）

生成完自动重建：index add（全部内容页 − orphans）、log ingest（按 source 页
frontmatter 的 created 排序）、tags 生长段（基底/用例目录的 ``tags.growth.md``
追加到白名单锚点之后）。每个根落为 ``DEST_DIR/<根名>/``。

退出码：0 成功；2 用法 / 夹具错误 / llmw 失败。
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "yzr-llm-wiki-management" / "eval" / "fixtures"
PAGE_DIRS = ("comparisons", "concepts", "entities", "sources", "syntheses")
TAG_ANCHOR = "<!-- tag 白名单起点（upgrade 嫁接锚点，勿删） -->"
DEFAULTS = {
    "topic": "机器学习笔记",
    "display_name": "Eval Fixture",
    "tag": "model",
    "description": "eval 夹具 wiki",
    "base": "",
    "orphans": "",
}


def _fail(msg):
    sys.stderr.write("[build-wiki-eval] error: %s\n" % msg)
    raise SystemExit(2)


def _llmw(*args):
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [sys.executable, "-m", "llmw", *[str(a) for a in args]],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        _fail("llmw %s exit=%d" % (" ".join(str(a) for a in args), proc.returncode))
    return proc


def _load_conf(path):
    conf = dict(DEFAULTS)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        conf[key.strip()] = value.strip()
    return conf


def _merge_copy(src, dst):
    for root, dirs, files in os.walk(str(src)):
        rel = Path(root).relative_to(src)
        target = dst / rel
        target.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name == "build.conf":
                continue
            shutil.copy2(os.path.join(root, name), str(target / name))


def _frontmatter(path):
    """取 title / created / sources / reviewed_at（fixture frontmatter 形状固定，够用）。"""
    title = created = reviewed_at = ""
    reviewed = False
    sources = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return title, created, sources, reviewed_at
    in_sources = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if in_sources:
            if stripped.startswith("- "):
                sources.append(stripped[2:].strip())
                continue
            in_sources = False
        if stripped.startswith("sources:"):
            in_sources = True
        elif stripped.startswith("title:"):
            title = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("created:"):
            created = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("reviewed:"):
            reviewed = stripped.split(":", 1)[1].strip() == "true"
        elif stripped.startswith("reviewed_at:"):
            reviewed_at = stripped.split(":", 1)[1].strip()
    if not reviewed:
        reviewed_at = ""
    return title, created, sources, reviewed_at


def _badge_index_entry(wiki, rel, reviewed_at):
    """write index add 不生成 ✓ 标识而 lint 要求（index-review-badge-drift），
    夹具构建侧按 lint 基准补挂；CLI 面只报告不修。"""
    index = wiki / "wiki" / "index.md"
    lines = index.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        if "](%s)" % rel in line and "✓" not in line and line.rstrip("\n").strip():
            line = line.rstrip("\n") + " ✓ reviewed %s\n" % reviewed_at
        out.append(line)
    index.write_text("".join(out), encoding="utf-8")


def _append_tags_growth(wiki, growth_file):
    if not growth_file.is_file():
        return
    extra = growth_file.read_text(encoding="utf-8").rstrip("\n")
    tags = wiki / "wiki" / "tags.md"
    text = tags.read_text(encoding="utf-8")
    if TAG_ANCHOR in text:
        tags.write_text(
            text.replace(TAG_ANCHOR, TAG_ANCHOR + "\n\n" + extra, 1), encoding="utf-8"
        )
    else:
        tags.write_text(text + "\n" + extra + "\n", encoding="utf-8")


def _content_pages(wiki):
    pages = []
    for d in PAGE_DIRS:
        wdir = wiki / "wiki" / d
        if not wdir.is_dir():
            continue
        for p in sorted(wdir.glob("*.md")):
            pages.append(wdir.name + "/" + p.name)
    return pages


def _build_root(name, conf, case_dir, tmp_ws):
    _llmw(
        "wiki",
        "--workspace=" + str(tmp_ws),
        "--name=" + name,
        "add",
        "--topic=" + conf["topic"],
        "--display-name=" + conf["display_name"],
        "--description=" + conf["description"],
        "--tag=" + conf["tag"],
        "-q",
    )
    wiki = tmp_ws / name
    if conf["base"]:
        base = FIXTURES / "_bases" / conf["base"]
        if not base.is_dir():
            _fail("base not found: %s" % base)
        _merge_copy(base, wiki)
    _merge_copy(case_dir / name, wiki)

    for growth in (
        FIXTURES / "_bases" / conf["base"] / "tags.growth.md" if conf["base"] else None,
        (case_dir / name / "tags.growth.md"),
    ):
        if growth is not None:
            _append_tags_growth(wiki, growth)

    orphans = set()
    for o in conf["orphans"].split(","):
        o = o.strip().lstrip("/")
        if o.startswith("wiki/"):
            o = o[len("wiki/") :]
        if o:
            orphans.add(o)
    for rel in _content_pages(wiki):
        if rel in orphans:
            continue
        _llmw("wiki", "--path=" + str(wiki), "write", "index", "add", "wiki/" + rel)
        _created, _date, _srcs, reviewed_at = _frontmatter(wiki / "wiki" / rel)
        if reviewed_at:
            _badge_index_entry(wiki, rel, reviewed_at)

    sources = []
    src_dir = wiki / "wiki" / "sources"
    if src_dir.is_dir():
        for p in src_dir.glob("*.md"):
            sources.append(p)
    sources.sort(key=lambda p: _frontmatter(p)[1])
    for p in sources:
        title, _created, srcs, _reviewed_at = _frontmatter(p)
        if not (srcs and title):
            _fail("source page without title/raw: %s" % p)
        _llmw(
            "wiki",
            "--path=" + str(wiki),
            "write",
            "log",
            "--op=ingest",
            "--title=" + title,
            "--raw=" + srcs[0],
        )
    return wiki


def main(argv):
    if len(argv) != 3:
        _fail("用法：build_wiki_eval.py CASE_ID DEST_DIR")
    case_id, dest_arg = argv[1], argv[2]
    case_dir = FIXTURES / case_id
    if not case_dir.is_dir():
        _fail("case not found: %s" % case_dir)
    roots = sorted(
        d.name
        for d in case_dir.iterdir()
        if d.is_dir() and (d / "build.conf").is_file()
    )
    if not roots:
        _fail("no root dirs with build.conf under %s" % case_dir)

    dest = Path(dest_arg)
    dest.mkdir(parents=True, exist_ok=True)
    tmp_ws = Path(tempfile.mkdtemp(prefix="wiki-eval-ws-"))
    try:
        _llmw("init", "--path=" + str(tmp_ws), "-q")
        for name in roots:
            conf = _load_conf(case_dir / name / "build.conf")
            wiki = _build_root(name, conf, case_dir, tmp_ws)
            target = dest / name
            if target.exists():
                shutil.rmtree(str(target))
            shutil.move(str(wiki), str(target))
            print("[build-wiki-eval] %s -> %s" % (case_id, target))
    finally:
        shutil.rmtree(str(tmp_ws), ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
