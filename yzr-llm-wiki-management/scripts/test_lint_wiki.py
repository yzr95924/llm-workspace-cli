#!/usr/bin/env python3
"""test_lint_wiki.py — lint_wiki.py 的端到端测试（聚焦 check_related_links）

stdlib unittest + subprocess 调真实脚本（无 mock）：在 tmp 目录搭最小 scratch
wiki，断言 related / compared 字段的路径基准（spec §9「wiki 根相对」= **内容根
`wiki/` 相对**）解析正确——spec 形式 `concepts/X.md` 命中真实文件时不报
`related-broken-link`；真坏链接仍报。

背景：0.22.0 引入 `check_related_links` 时 `target = wiki_root / item` 误把 spec
的内容根相对路径（`concepts/X.md`）当**最外层根相对**解析（缺 `wiki/` 段，因为
`wiki_root` 是 `<wiki>/`，真实文件在 `<wiki>/wiki/concepts/X.md`），导致按 spec
正确写的 related 必被误报 `related-broken-link`。本测试覆盖该基准 bug——改 lint
前 test_spec_form_* / test_compared_field_* 失败，改后全绿。

运行:
  python3 scripts/test_lint_wiki.py        # 在 skill 仓根或 scripts/ 下均可
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "lint_wiki.py"

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
    """跑 lint_wiki.py --no-git，返回 (exit_code, stdout)。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(root), "--no-git"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return proc.returncode, proc.stdout


class RelatedLinksResolutionTest(unittest.TestCase):
    def test_spec_form_concepts_relative_not_reported(self):
        """spec §9 约定的 wiki 根相对形式 concepts/beta.md（基准 = 内容根 wiki/）
        命中真实文件 wiki/concepts/beta.md 时，不应报 related-broken-link。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "concepts" / "beta.md").write_text(_page("Beta", "concept"), encoding="utf-8")
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                _page("Alpha", "concept", extra="related: [concepts/beta.md]\n"), encoding="utf-8"
            )
            _, stdout = run_lint(root)
        self.assertNotIn("related-broken-link", stdout, f"spec 形式不应误报：\n{stdout}")

    def test_genuinely_missing_target_still_reported(self):
        """真坏链接（目标确实不存在）仍须报 related-broken-link——确保基准修正没把检查改瞎。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "concepts" / "alpha.md").write_text(
                _page("Alpha", "concept", extra="related: [concepts/nonexistent.md]\n"), encoding="utf-8"
            )
            _, stdout = run_lint(root)
        self.assertIn("related-broken-link", stdout, "真坏链接应被报出：\n" + stdout)

    def test_compared_field_same_semantics(self):
        """compared 字段与 related 同语义（spec §9 同基准）——wiki 根相对形式同样不应误报。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "comparisons").mkdir(parents=True, exist_ok=True)
            (root / "wiki" / "concepts" / "beta.md").write_text(_page("Beta", "concept"), encoding="utf-8")
            (root / "wiki" / "comparisons" / "cmp.md").write_text(
                _page("Cmp", "comparison", extra="compared: [concepts/beta.md]\n"), encoding="utf-8"
            )
            _, stdout = run_lint(root)
        self.assertNotIn("related-broken-link", stdout, f"compared spec 形式不应误报：\n{stdout}")


class DiscussionsSourceGuardTest(unittest.TestCase):
    """spec §15：`type: source` 页 `sources:` 不得指向 `raw/discussions/`。"""

    def test_source_pointing_at_discussions_is_reported(self):
        """source 页 sources 指向 raw/discussions/ → 报 source-in-discussions（error）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
            (root / "wiki" / "sources" / "draft.md").write_text(
                _page("Draft", "source", extra="sources: [raw/discussions/foo.md]\n"),
                encoding="utf-8",
            )
            _, stdout = run_lint(root)
        self.assertIn("source-in-discussions", stdout, "指向 discussions/ 应被报出：\n" + stdout)

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
        self.assertNotIn("source-in-discussions", stdout, f"正常 source 不应误报：\n{stdout}")


class GitPorcelainPathsTest(unittest.TestCase):
    """`_git_porcelain_paths`——raw-modified 排除 discussions/ 的解析基础。"""

    def setUp(self):
        # 直接 import 模块（与 subprocess 端到端测试互补——本 helper 是纯函数）
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lint_wiki  # noqa: E402

        self.lint_wiki = lint_wiki

    def test_plain_path(self):
        paths = self.lint_wiki._git_porcelain_paths
        self.assertEqual(paths(" M raw/articles/foo.md"), ["raw/articles/foo.md"])
        self.assertEqual(paths("?? raw/discussions/draft.md"), ["raw/discussions/draft.md"])
        self.assertEqual(paths("?? raw/discussions/"), ["raw/discussions/"])

    def test_rename_returns_both_sides(self):
        """rename `R <old> -> <new>`（git 实测 old 在前、new 在后）返回 [old, new]——
        两侧都判，覆盖 §15.3 archive mv 跨边界（discussions/ → articles/）。"""
        paths = self.lint_wiki._git_porcelain_paths
        self.assertEqual(paths("R  raw/old.md -> raw/new.md"), ["raw/old.md", "raw/new.md"])
        # archive mv：discussions/ 迁出到 articles/，old 侧命中 discussions 前缀也要排除
        self.assertEqual(
            paths("R  raw/discussions/x.md -> raw/articles/x.md"),
            ["raw/discussions/x.md", "raw/articles/x.md"],
        )

    def test_quoted_path(self):
        paths = self.lint_wiki._git_porcelain_paths
        # 含空格的路径被双引号包裹
        self.assertEqual(paths('?? "raw/discussions/my draft.md"'), ["raw/discussions/my draft.md"])

    def test_too_short_line(self):
        self.assertEqual(self.lint_wiki._git_porcelain_paths("XY"), [])


class SeverityOfTest(unittest.TestCase):
    """severity_of() 映射守护——P1 漏映射（sources-* 三条落默认 info）曾让
    `--severity error` 静默滤掉 error 级 finding。加映射单测防止再漏。"""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lint_wiki  # noqa: E402

        self.severity_of = lint_wiki.severity_of

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
            self.assertEqual(self.severity_of(prefix + ": x"), "error", f"{prefix} 应为 error")

    def test_representative_others(self):
        self.assertEqual(self.severity_of("memory-not-indexed: x"), "info")
        self.assertEqual(self.severity_of("memory-index-dangling: x"), "warn")
        self.assertEqual(self.severity_of("external-anchor-orphan: x"), "warn")
        self.assertEqual(self.severity_of("log-format: x"), "warn")
        self.assertEqual(self.severity_of("unknown-finding: x"), "info")


class MemoryIndexDanglingTest(unittest.TestCase):
    """反向悬空检查：MEMORY.md 索引指向的 <slug>.md 不存在 → memory-index-dangling（warn）。"""

    def _memory_index(self, extra_line="", with_link=False):
        body = "# MEMORY\n\n> 索引说明\n\n## 索引\n\n"
        if with_link:
            body += "- foo — 一句话 → [正文](foo.md)\n"
        else:
            body += "- 一句话事实（短条目，无链接）\n"
        return body + extra_line

    def test_dangling_index_link_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "MEMORY").mkdir(parents=True, exist_ok=True)
            (root / "MEMORY" / "MEMORY.md").write_text(self._memory_index(with_link=True), encoding="utf-8")
            _, stdout = run_lint(root)
        self.assertIn("memory-index-dangling", stdout, "索引指向缺失文件应报出：\n" + stdout)

    def test_short_entry_no_link_not_reported(self):
        """短条目（无链接的纯索引行）不算 dangling。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "MEMORY").mkdir(parents=True, exist_ok=True)
            (root / "MEMORY" / "MEMORY.md").write_text(self._memory_index(), encoding="utf-8")
            _, stdout = run_lint(root)
        self.assertNotIn("memory-index-dangling", stdout, f"短条目不应误报：\n{stdout}")

    def test_existing_file_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_minimal_wiki(tmp)
            (root / "MEMORY").mkdir(parents=True, exist_ok=True)
            (root / "MEMORY" / "MEMORY.md").write_text(self._memory_index(with_link=True), encoding="utf-8")
            (root / "MEMORY" / "foo.md").write_text("---\ntitle: Foo\n---\n\n# Foo\n", encoding="utf-8")
            _, stdout = run_lint(root)
        self.assertNotIn("memory-index-dangling", stdout, f"文件存在不应误报：\n{stdout}")


if __name__ == "__main__":
    unittest.main()
