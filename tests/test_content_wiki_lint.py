#!/usr/bin/env python3
"""test_content_wiki_lint — llmw.content.wiki_lint 端到端测试（聚焦 check_related_links）

stdlib unittest + subprocess 调真实模块（无 mock）：在 tmp 目录搭最小 scratch
wiki，断言 related / compared 字段的路径基准（「wiki 根相对」= **内容根
`wiki/` 相对**）解析正确——wiki 根相对形式 `concepts/X.md` 命中真实文件时不报
`related-broken-link`；真坏链接仍报。

背景：0.22.0 引入 `check_related_links` 时 `target = wiki_root / item` 误把 wiki 的内容
根相对路径（`concepts/X.md`）当**最外层根相对**解析（缺 `wiki/` 段，因为
`wiki_root` 是 `<wiki>/`，真实文件在 `<wiki>/wiki/concepts/X.md`），导致按 wiki 根相对基准
正确写的 related 必被误报 `related-broken-link`。本测试覆盖该基准 bug——改 lint
前 test_wiki_root_relative_form_* / test_compared_field_* 失败，改后全绿。

运行:
  pytest tests/test_content_wiki_lint.py
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_INDEX_MD = """\
---
title: Idx
description: d
type: index
tags: []
created: 2026-07-21
updated: 2026-07-21
---
# Idx
"""

_LOG_MD = """\
---
title: Log
description: d
type: log
tags: []
created: 2026-07-21
updated: 2026-07-21
---
# Log

## 2026-07-21 setup
- init
"""


def _page(title, ptype, extra=""):
    """生成一页 markdown：5 必填 frontmatter + 可选 extra 字段行 + 空 H1 正文。"""
    fm = (
        "---\n"
        f"title: {title}\n"
        "description: d\n"
        f"type: {ptype}\n"
        "tags: []\n"
        "created: 2026-07-21\n"
        "updated: 2026-07-21\n"
        f"{extra}"
        "---\n"
    )
    return fm + f"# {title}\n"


def build_minimal_wiki(root):
    """搭最小可跑通的 scratch wiki（wiki/index.md + log.md + raw/）。"""
    root = Path(root)
    (root / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "index.md").write_text(_INDEX_MD, encoding="utf-8")
    (root / "wiki" / "log.md").write_text(_LOG_MD, encoding="utf-8")
    return root


def run_lint(root):
    """跑 `llmw wiki --path=<root> lint --no-git`（唯一 CLI 入口），返回 (exit_code, stdout)。"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "llmw",
            "wiki",
            "--path=" + str(root),
            "lint",
            "--no-git",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return proc.returncode, proc.stdout


class RelatedLinksResolutionTest(unittest.TestCase):
    def test_wiki_root_relative_form_concepts_not_reported(self):
        """page-templates.md「共有 frontmatter 段」约定的 wiki 根相对形式 concepts/beta.md（基准 = 内容根 wiki/）
        命中真实文件 wiki/concepts/beta.md 时，不应报 related-broken-link。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "concepts" / "beta.md").write_text(
                _page("Beta", "concept"), encoding="utf-8"
            )
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                _page("Alpha", "concept", extra="related: [concepts/beta.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertNotIn(
            "related-broken-link", stdout, f"wiki 根相对形式不应误报：\n{stdout}"
        )

    def test_genuinely_missing_target_still_reported(self):
        """真坏链接（目标确实不存在）仍须报 related-broken-link——确保基准修正没把检查改瞎。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                _page("Alpha", "concept", extra="related: [concepts/nonexistent.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertIn("related-broken-link", stdout, "真坏链接应被报出：\n" + stdout)

    def test_compared_field_same_semantics(self):
        """compared 字段与 related 同语义（page-templates.md「共有 frontmatter 段」同基准）——wiki 根相对形式同样不应误报。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "comparisons").mkdir(parents=True, exist_ok=True)
            (root / "wiki" / "concepts" / "beta.md").write_text(
                _page("Beta", "concept"), encoding="utf-8"
            )
            (root / "wiki" / "comparisons" / "cmp.md").write_text(
                _page("Cmp", "comparison", extra="compared: [concepts/beta.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertNotIn(
            "related-broken-link",
            stdout,
            f"compared wiki 根相对形式不应误报：\n{stdout}",
        )


class DiscussionsSourceGuardTest(unittest.TestCase):
    """`type: source` 页 `sources:` 不得指向 `discussions/` 或旧 `raw/discussions/`。"""

    def test_source_pointing_at_root_discussions_is_reported(self):
        """source 页 sources 指向 discussions/ → 报 source-in-discussions（error）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
            (root / "wiki" / "sources" / "draft.md").write_text(
                _page("Draft", "source", extra="sources: [discussions/foo.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertIn(
            "source-in-discussions", stdout, "指向 discussions/ 应被报出：\n" + stdout
        )

    def test_source_pointing_at_legacy_raw_discussions_is_reported(self):
        """source 页 sources 指向旧 raw/discussions/ → 仍报 source-in-discussions。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
            (root / "wiki" / "sources" / "draft.md").write_text(
                _page("Draft", "source", extra="sources: [raw/discussions/foo.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertIn("source-in-discussions", stdout, "旧路径应被报出：\n" + stdout)

    def test_source_pointing_at_articles_not_reported(self):
        """正常 raw/articles/ source 不触发 source-in-discussions（防 over-fire 回归）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "raw" / "articles").mkdir(parents=True, exist_ok=True)
            (root / "raw" / "articles" / "foo.md").write_text("body", encoding="utf-8")
            (root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
            (root / "wiki" / "sources" / "art.md").write_text(
                _page("Art", "source", extra="sources: [raw/articles/foo.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertNotIn(
            "source-in-discussions", stdout, f"正常 source 不应误报：\n{stdout}"
        )


class ReviewedStaleDateTest(unittest.TestCase):
    """`reviewed-stale` 按日期比较：同日"改正文 → 人工复审"是合法终态不报；
    updated 日期晚于 reviewed_at 才报（原字符串比较把同日合法态误报）。"""

    _PAGE = (
        "---\n"
        "title: Alpha\n"
        "description: d\n"
        "type: concept\n"
        "tags: []\n"
        "created: 2026-07-21\n"
        "updated: {updated}\n"
        "reviewed: true\n"
        "reviewed_at: 2026-07-21\n"
        "---\n"
        "# Alpha\n"
    )

    def test_same_day_update_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                self._PAGE.format(updated="2026-07-21 10:00"), encoding="utf-8"
            )
            _, stdout = run_lint(root)
        self.assertNotIn("reviewed-stale", stdout, f"同日改后复审不应报：\n{stdout}")

    def test_next_day_update_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                self._PAGE.format(updated="2026-07-22 08:00"), encoding="utf-8"
            )
            _, stdout = run_lint(root)
        self.assertIn("reviewed-stale", stdout, f"次日更新应报：\n{stdout}")


class SeverityOfTest(unittest.TestCase):
    """severity_of() 映射守护——P1 漏映射（sources-* 三条落默认 info）曾让
    `--severity error` 静默滤掉 error 级 finding。加映射单测防止再漏。"""

    def setUp(self):
        from llmw.content import wiki_lint

        self.severity_of = wiki_lint.severity_of

    def test_sources_family_error(self):
        """sources-* 全族必须 error（含曾漏映射的三条）。"""
        for prefix in (
            "sources-missing",
            "sources-malformed",
            "sources-out-of-root",
            "sources-absolute-path",
            "sources-external-anchor-missing",
            "sources-external-symlink-missing",
            "source-in-discussions",
        ):
            self.assertEqual(
                self.severity_of(prefix + ": x"), "error", f"{prefix} 应为 error"
            )

    def test_representative_others(self):
        self.assertEqual(self.severity_of("missing-sources: x"), "error")
        self.assertEqual(self.severity_of("invalid-tags: x"), "error")
        self.assertEqual(self.severity_of("external-anchor-orphan: x"), "warn")
        self.assertEqual(self.severity_of("log-format: x"), "warn")
        self.assertEqual(self.severity_of("unknown-finding: x"), "info")


if __name__ == "__main__":
    unittest.main()
