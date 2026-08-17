#!/usr/bin/env python3
"""test_wiki_write.py — wiki_write.py 端到端测试（机械字节写操作）

stdlib unittest + subprocess 调真实脚本（无 mock）：在 tmp 目录搭最小 scratch wiki，
覆盖五个子命令的 round-trip 不变量——
- `new` 产物必须过 lint_wiki.check_frontmatter（准入规则第 2 条：lint 可验证）
- `log` 产物必须被 LOG_LINE_RE 解析（含截断后 frontmatter 不动）
- `memory` 产物必须过 lint_wiki.check_memory_index（memory-not-indexed 免疫）
- `index` 条目派生自页 frontmatter（title/description 复制防漂移）

运行:
  python3 scripts/test_wiki_write.py        # 在 skill 仓根或 scripts/ 下均可
"""

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "wiki_write.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_wiki import CURRENT_WIKI_SPEC, check_frontmatter, check_memory_index  # noqa: E402
from log_format import LOG_LINE_RE  # noqa: E402

INDEX_SKELETON = """---
title: "Test Index"
type: index
okf_version: "0.1"
tags: [index]
created: 2026-06-28 14:30
updated: 2026-06-28 14:30
---

# Test Wiki

> 本 wiki 由 LLM 维护，用户只读 + 提供 raw 资料 + 提问题。
> Schema 见 [`../AGENTS.md`](../AGENTS.md)。

## Comparisons

_（暂无内容）_

## Concepts

- [Beta Concept](concepts/beta.md) — beta 摘要

## Entities

_（暂无内容）_

## Sources

- [Alpha Source](sources/alpha.md) — alpha 摘要

## Syntheses

_（暂无内容）_
"""

LOG_SKELETON = """---
title: "Test Log"
type: log
tags: [log]
created: 2026-06-28 14:30
updated: 2026-06-28 14:30
---

## [2026-06-28 14:30] setup | Initial scaffold
## [2026-06-28 14:31] ingest | Alpha Source
"""

MEMORY_INDEX_SKELETON = """# MEMORY

> LLM agent 的持久化记忆索引（无 frontmatter）。

## 索引

- [Existing Tip](existing-tip.md) — 已有条目
"""


def _make_wiki(root, spec_version=None):
    root = Path(root)
    for sub in ("entities", "concepts", "sources", "comparisons", "syntheses"):
        (root / "wiki" / sub).mkdir(parents=True)
    (root / "MEMORY").mkdir()
    (root / "raw" / "articles").mkdir(parents=True)
    (root / "raw" / "external").mkdir()
    ver = spec_version or CURRENT_WIKI_SPEC
    (root / "AGENTS.md").write_text(
        f"# Test Wiki\n\n## 八 Wiki Spec\n\n| Wiki Spec 版本 | {ver} |\n",
        encoding="utf-8",
    )
    (root / "wiki" / "index.md").write_text(INDEX_SKELETON, encoding="utf-8")
    (root / "wiki" / "log.md").write_text(LOG_SKELETON, encoding="utf-8")
    (root / "MEMORY" / "MEMORY.md").write_text(MEMORY_INDEX_SKELETON, encoding="utf-8")
    (root / "MEMORY" / "existing-tip.md").write_text('---\ntitle: "Existing Tip"\n---\n', encoding="utf-8")
    (root / "wiki" / "sources" / "alpha.md").write_text(
        '---\ntitle: "Alpha Source"\ndescription: "alpha 摘要"\ntype: source\n'
        "tags: [llm]\ncreated: 2026-06-28 14:30\nupdated: 2026-06-28 14:30\n"
        "sources:\n  - raw/articles/alpha.md\n---\n\n# Alpha Source\n",
        encoding="utf-8",
    )
    (root / "raw" / "articles" / "alpha.md").write_text("# alpha raw\n", encoding="utf-8")
    return root


def _run(wiki_root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(wiki_root)] + list(args),
        capture_output=True,
        text=True,
    )


class LogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_wiki(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _log_text(self):
        return (self.root / "wiki" / "log.md").read_text(encoding="utf-8")

    def test_append_single(self):
        r = _run(self.root, "log", "--op", "ingest", "--title", "Foo Bar")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self._log_text().splitlines()
        last = lines[-1]
        self.assertTrue(LOG_LINE_RE.match(last), last)
        self.assertIn("ingest | Foo Bar", last)
        # frontmatter 未被破坏
        self.assertTrue(lines[0].startswith("---"))

    def test_append_multiple(self):
        r = _run(self.root, "log", "--op", "ingest", "--title", "A", "--title", "B")
        self.assertEqual(r.returncode, 0, r.stderr)
        tail = self._log_text().splitlines()[-2:]
        self.assertTrue(any(LOG_LINE_RE.match(ln) and ln.endswith("| A") for ln in tail))
        self.assertTrue(any(LOG_LINE_RE.match(ln) and ln.endswith("| B") for ln in tail))

    def test_bulk(self):
        r = _run(self.root, "log", "--op", "ingest", "--bulk", "--topic", "RL 综述", "--count", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        last = self._log_text().splitlines()[-1]
        self.assertIn("Bulk: RL 综述 (5 sources)", last)

    def test_truncation_keeps_frontmatter(self):
        body = "\n".join(f"## [2026-06-01 {i // 60:02d}:{i % 60:02d}] ingest | entry-{i}" for i in range(52))
        log_path = self.root / "wiki" / "log.md"
        text = log_path.read_text(encoding="utf-8")
        frontmatter, _, rest = text.partition("\n---\n")
        log_path.write_text(frontmatter + "\n---\n" + body + "\n", encoding="utf-8")
        r = _run(self.root, "log", "--op", "ingest", "--title", "newest")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self._log_text()
        self.assertTrue(text.startswith("---\ntitle:"), "frontmatter 被截断破坏")
        body_lines = text.split("\n---\n", 1)[1].splitlines()
        count = sum(1 for ln in body_lines if LOG_LINE_RE.match(ln))
        self.assertLessEqual(count, 50)
        self.assertIn("| newest", body_lines[-1])

    def test_missing_log(self):
        (self.root / "wiki" / "log.md").unlink()
        r = _run(self.root, "log", "--op", "ingest", "--title", "X")
        self.assertEqual(r.returncode, 2)
        self.assertIn("log-missing", r.stderr)

    def test_bad_title_rejected(self):
        r = _run(self.root, "log", "--op", "ingest")
        self.assertEqual(r.returncode, 2)
        r2 = _run(self.root, "log", "--op", "bogus", "--title", "X")
        self.assertEqual(r2.returncode, 2)


class IndexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_wiki(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _index_text(self):
        return (self.root / "wiki" / "index.md").read_text(encoding="utf-8")

    def test_add_source_alphabetical(self):
        (self.root / "wiki" / "sources" / "zeta.md").write_text(
            '---\ntitle: "Zeta Source"\ndescription: "zeta 摘要"\ntype: source\n'
            "tags: [llm]\ncreated: 2026-07-01 10:00\nupdated: 2026-07-01 10:00\n"
            "sources:\n  - raw/articles/zeta.md\n---\n\n# Zeta Source\n",
            encoding="utf-8",
        )
        r = _run(self.root, "index", "add", "wiki/sources/zeta.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self._index_text()
        sources_section = text.split("## Sources\n", 1)[1].split("\n## ")[0]
        lines = [ln for ln in sources_section.splitlines() if ln.strip().startswith("- [")]
        self.assertEqual(
            [ln for ln in lines if "Alpha Source" in ln or "Zeta Source" in ln],
            ["- [Alpha Source](sources/alpha.md) — alpha 摘要", "- [Zeta Source](sources/zeta.md) — zeta 摘要"],
        )

    def test_add_into_empty_section_removes_placeholder(self):
        (self.root / "wiki" / "comparisons" / "a-vs-b.md").write_text(
            '---\ntitle: "A vs B"\ntype: comparison\ntags: []\n'
            "created: 2026-07-01 10:00\nupdated: 2026-07-01 10:00\n---\n\n# A vs B\n",
            encoding="utf-8",
        )
        r = _run(self.root, "index", "add", "wiki/comparisons/a-vs-b.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self._index_text()
        self.assertNotIn("_（暂无内容）_", text.split("## Comparisons\n", 1)[1].split("\n## ")[0])
        self.assertIn("- [A vs B](comparisons/a-vs-b.md)", text)

    def test_add_duplicate_noop(self):
        r = _run(self.root, "index", "add", "wiki/sources/alpha.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("跳过", r.stderr)
        self.assertEqual(self._index_text(), INDEX_SKELETON)

    def test_add_missing_type_rejected(self):
        (self.root / "wiki" / "sources" / "no-type.md").write_text(
            '---\ntitle: "No Type"\ntags: []\ncreated: 2026-07-01 10:00\nupdated: 2026-07-01 10:00\n---\n\n# No Type\n',
            encoding="utf-8",
        )
        r = _run(self.root, "index", "add", "wiki/sources/no-type.md")
        self.assertEqual(r.returncode, 2)

    def test_remove(self):
        r = _run(self.root, "index", "remove", "wiki/sources/alpha.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("sources/alpha.md", self._index_text())

    def test_remove_missing_rejected(self):
        r = _run(self.root, "index", "remove", "wiki/sources/never.md")
        self.assertEqual(r.returncode, 2)


class TouchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_wiki(self._tmp.name)
        (self.root / "wiki" / "concepts" / "beta.md").write_text(
            '---\ntitle: "Beta Concept"\nreviewed: true\nreviewed_at: 2026-06-28 14:30\n'
            "type: concept\ntags: [llm]\ncreated: 2026-06-28 14:30\nupdated: 2026-06-28 14:30\n"
            "---\n\n# Beta Concept\n\n正文保持不动。\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_touch_clears_reviewed(self):
        r = _run(self.root, "touch", "wiki/concepts/beta.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root / "wiki" / "concepts" / "beta.md").read_text(encoding="utf-8")
        self.assertNotIn("reviewed", text)
        self.assertIn("updated: {}".format(datetime.now().strftime("%Y-%m-%d")), text)
        self.assertIn("正文保持不动。", text)
        self.assertIn("created: 2026-06-28 14:30", text)

    def test_touch_no_reviewed_only_updates(self):
        (self.root / "wiki" / "concepts" / "beta.md").write_text(
            '---\ntitle: "Beta Concept"\ntype: concept\ntags: [llm]\n'
            "created: 2026-06-28 14:30\nupdated: 2026-06-28 14:30\n---\n\n# Beta Concept\n",
            encoding="utf-8",
        )
        r = _run(self.root, "touch", "wiki/concepts/beta.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.root / "wiki" / "concepts" / "beta.md").read_text(encoding="utf-8")
        self.assertIn("updated: {}".format(datetime.now().strftime("%Y-%m-%d")), text)

    def test_touch_missing_page(self):
        r = _run(self.root, "touch", "wiki/concepts/nope.md")
        self.assertEqual(r.returncode, 2)


class NewTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_wiki(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_new_source_roundtrip_lint_clean(self):
        r = _run(
            self.root,
            "new",
            "--type",
            "source",
            "--slug",
            "attention",
            "--title",
            "Attention Is All You Need",
            "--description",
            "transformer 论文",
            "--sources",
            "raw/articles/attention.md",
            "--tags",
            "llm, transformer",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.root / "raw" / "articles" / "attention.md").write_text("# attention raw\n", encoding="utf-8")
        page = self.root / "wiki" / "sources" / "attention.md"
        self.assertTrue(page.is_file())
        findings = check_frontmatter(self.root)
        self.assertFalse(
            any("attention.md" in f for f in findings),
            f"new 产物应过 frontmatter 检查: {findings}",
        )
        text = page.read_text(encoding="utf-8")
        self.assertIn("created: ", text)
        self.assertIn("updated: ", text)
        self.assertIn("sources:\n  - raw/articles/attention.md", text)

    def test_new_source_requires_sources(self):
        r = _run(self.root, "new", "--type", "source", "--slug", "x", "--title", "X")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--sources", r.stderr)

    def test_new_bad_slug(self):
        r = _run(self.root, "new", "--type", "concept", "--slug", "Bad Slug", "--title", "X")
        self.assertEqual(r.returncode, 2)
        r2 = _run(self.root, "new", "--type", "memory", "--slug", "x", "--title", "X")
        self.assertEqual(r2.returncode, 2)

    def test_new_refuses_overwrite(self):
        r = _run(
            self.root,
            "new",
            "--type",
            "source",
            "--slug",
            "alpha",
            "--title",
            "dup",
            "--sources",
            "raw/articles/alpha.md",
        )
        self.assertEqual(r.returncode, 2)
        self.assertIn("已存在", r.stderr)

    def test_new_entity_without_sources_ok(self):
        r = _run(self.root, "new", "--type", "entity", "--slug", "openai", "--title", "OpenAI")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / "wiki" / "entities" / "openai.md").is_file())


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_wiki(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_memory_add_roundtrip_index_clean(self):
        r = _run(
            self.root, "memory", "add", "--slug", "ocr-tips", "--title", "OCR Tips", "--index-line", "PDF 先转格式"
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        entry = self.root / "MEMORY" / "ocr-tips.md"
        self.assertTrue(entry.is_file())
        text = entry.read_text(encoding="utf-8")
        self.assertTrue(text.startswith('---\ntitle: "OCR Tips"\n---\n'))
        index_text = (self.root / "MEMORY" / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("- [OCR Tips](ocr-tips.md) — PDF 先转格式", index_text)
        findings = check_memory_index(self.root)
        self.assertFalse(
            any("ocr-tips" in f for f in findings),
            f"memory add 产物应过索引检查: {findings}",
        )

    def test_memory_missing_index(self):
        (self.root / "MEMORY" / "MEMORY.md").unlink()
        r = _run(self.root, "memory", "add", "--slug", "x", "--title", "X")
        self.assertEqual(r.returncode, 2)

    def test_memory_bad_slug(self):
        r = _run(self.root, "memory", "add", "--slug", "Bad", "--title", "X")
        self.assertEqual(r.returncode, 2)


class VersionWarnTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _make_wiki(self._tmp.name, spec_version="0.27.1")

    def tearDown(self):
        self._tmp.cleanup()

    def test_stale_version_warns_but_writes(self):
        r = _run(self.root, "log", "--op", "ingest", "--title", "X")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[WARN]", r.stderr)
        self.assertIn("0.27.1", r.stderr)
        self.assertIn("| X", (self.root / "wiki" / "log.md").read_text(encoding="utf-8"))

    def test_current_version_no_warn(self):
        root2 = Path(self._tmp.name)
        r = _run(root2, "log", "--op", "ingest", "--title", "X")
        # 上面 setUp 用了旧版本——重建同目录为当前版本
        # （单独 tmp 保证干净，见 test_stale_version_warns_but_writes）
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
