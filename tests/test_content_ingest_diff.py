"""test_content_ingest_diff — llmw.content.ingest_diff 的 log 记录提取 + 兜底分类回归测试

历史 bug：LOG_INGEST_RE 取组错位（曾把时间当标题 / date-only 行崩溃），现标题走命名组
`title`、时间戳全非捕获。三种合法时间格式逐一锁定。

兜底分类：新条目（write log --raw 落第三段 ` | raw/...`）按路径精确命中；老条目只有
title，与 raw 文件名 stem 靠 `_slugify` 归一化对齐——"Attention Is All You Need" 命中
attention-is-all-you-need.md；命名不对齐则落 untracked。

运行：
  pytest tests/test_content_ingest_diff.py -q
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


class CollectIngestedFromLogTests(unittest.TestCase):
    """collect_ingested_from_log → (标题集合, raw 路径集合)。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _collect(self, lines):
        from llmw.content.ingest_diff import collect_ingested_from_log

        log = self.root / "log.md"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return collect_ingested_from_log(log)

    def test_date_only_line_title(self):
        assert self._collect(["## [2026-09-20] ingest | My Title"]) == (
            {"My Title"},
            set(),
        )

    def test_minute_line_title_not_time(self):
        assert self._collect(["## [2026-09-20 14:30] ingest | My Title"]) == (
            {"My Title"},
            set(),
        )

    def test_second_line_title(self):
        assert self._collect(["## [2026-09-20 14:30:05] ingest | My Title"]) == (
            {"My Title"},
            set(),
        )

    def test_raw_segment_extracted(self):
        assert self._collect(
            ["## [2026-09-20 14:30] ingest | T | raw/articles/foo.md"]
        ) == (
            {"T"},
            {"raw/articles/foo.md"},
        )

    def test_raw_with_spaces(self):
        assert self._collect(
            ["## [2026-09-20 14:30] ingest | T | raw/articles/My Paper v2.md"]
        ) == ({"T"}, {"raw/articles/My Paper v2.md"})

    def test_non_raw_segment_stays_in_title(self):
        assert self._collect(["## [2026-09-20 14:30] ingest | T | wiki/x.md"]) == (
            {"T | wiki/x.md"},
            set(),
        )

    def test_non_ingest_lines_ignored(self):
        assert self._collect(
            [
                "# Log",
                "## [2026-09-20 14:30] query | A question",
                "## [2026-09-20] lint | Fixed orphans",
            ]
        ) == (set(), set())


class SlugifyTests(unittest.TestCase):
    def test_title_and_filename_stem_align(self):
        from llmw.content.ingest_diff import _slugify

        assert _slugify("Attention Is All You Need") == "attention-is-all-you-need"
        assert _slugify("attention_is_all_you_need") == "attention-is-all-you-need"

    def test_pure_cjk_yields_empty(self):
        from llmw.content.ingest_diff import _slugify

        assert _slugify("注意力机制") == ""


class LogOnlyClassificationTests(unittest.TestCase):
    """run() 兜底分类：raw 路径精确命中（新条目）/ 标题 slug 对齐（老条目兜底）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_reasons(self, raw_name, log_line):
        (self.root / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki").mkdir(exist_ok=True)
        (self.root / "raw" / "articles" / raw_name).write_text("raw", encoding="utf-8")
        (self.root / "wiki" / "log.md").write_text(log_line + "\n", encoding="utf-8")
        from llmw.content.ingest_diff import run

        buf = io.StringIO()
        with redirect_stdout(buf):
            run(self.root, as_json=True)
        return [row["reason"] for row in json.loads(buf.getvalue())]

    def test_raw_path_exact_match_ignores_filename(self):
        """新条目记了 raw 路径：文件名与标题无关也精确命中。"""
        reasons = self._run_reasons(
            "paper-v2.md",
            "## [2026-09-20 14:30] ingest | Attention Is All You Need | raw/articles/paper-v2.md",
        )
        assert reasons == ["log-only-no-source-page"]

    def test_slug_named_raw_matches_title_style_log(self):
        reasons = self._run_reasons(
            "attention-is-all-you-need.md",
            "## [2026-09-20 14:30] ingest | Attention Is All You Need",
        )
        assert reasons == ["log-only-no-source-page"]

    def test_spaced_filename_matches_title(self):
        reasons = self._run_reasons(
            "Attention Is All You Need.md",
            "## [2026-09-20 14:30] ingest | Attention Is All You Need",
        )
        assert reasons == ["log-only-no-source-page"]

    def test_unrelated_raw_name_stays_untracked(self):
        reasons = self._run_reasons(
            "paper-v2.md",
            "## [2026-09-20 14:30] ingest | Attention Is All You Need",
        )
        assert reasons == ["untracked"]

    def test_bulk_log_entry_never_matches(self):
        reasons = self._run_reasons(
            "attention-is-all-you-need.md",
            "## [2026-09-20 14:30] ingest | Bulk: attention (5 sources)",
        )
        assert reasons == ["untracked"]


if __name__ == "__main__":
    unittest.main()
