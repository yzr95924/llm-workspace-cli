#!/usr/bin/env python3
"""test_agents_md_fingerprint — AGENTS.md 写盘指纹 ↔ agents_md_pristine 三态契约。

  1. `wiki add` 出生即记指纹（== 落盘 AGENTS.md 字节 sha256）
  2. store save/load round-trip 存活
  3. dry-run / blocked_drift 输出 agents_md_pristine：无指纹 null → apply 回填 → true；
     手改 / 删文件 → false；`--yes` 重写后指纹刷新
  4. 幂等 apply（无写盘动作）即回填指纹

subprocess 调真实 CLI；scratch wiki 复用 build_wiki。运行: pytest tests/test_agents_md_fingerprint.py
"""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from llmw.wiki import manager as wiki_manager  # noqa: E402
from llmw.wiki import store as wiki_store  # noqa: E402
from llmw.workspace import store as ws_store  # noqa: E402
from test_content_upgrade import run_wiki  # noqa: E402
from test_content_wiki_fixtures import build_wiki  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AddBirthFingerprintTest(unittest.TestCase):
    def test_add_records_birth_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            ws_root = Path(d) / "ws"
            ws_root.mkdir()
            ws_store.create_skeleton(ws_root)
            wiki_manager.add(
                ws_root, "t", topic="T", display_name="T", description="d", tags=["x"]
            )
            wiki_dir = ws_root / "t"
            meta = wiki_store.load(wiki_dir)
            self.assertEqual(meta.agents_md_sha256, _sha256(wiki_dir / "AGENTS.md"))


class StoreRoundTripTest(unittest.TestCase):
    def test_field_survives_save(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            wiki_store.create_skeleton(p, "foo", "Foo")
            meta = wiki_store.load(p)
            self.assertEqual(meta.agents_md_sha256, "")
            meta.agents_md_sha256 = "ab" * 32
            meta.bump()
            wiki_store.save(p, meta)
            self.assertEqual(wiki_store.load(p).agents_md_sha256, "ab" * 32)


class UpgradeThreeStateTest(unittest.TestCase):
    def _backfill(self, root):
        """幂等 apply → done，指纹回填。"""
        rc, report, err = run_wiki(root, "upgrade", "--apply")
        self.assertEqual(rc, 0, err)
        self.assertEqual(report["status"], "done")
        self.assertEqual(
            wiki_store.load(root).agents_md_sha256, _sha256(root / "AGENTS.md")
        )

    def test_null_then_backfill_then_true(self):
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            root = Path(d)
            rc, report, err = run_wiki(root, "upgrade")
            self.assertEqual(rc, 0, err)
            self.assertEqual(report["status"], "dry_run")
            self.assertIsNone(report["agents_md_pristine"])
            self._backfill(root)
            rc, report, err = run_wiki(root, "upgrade")
            self.assertEqual(rc, 0, err)
            self.assertIs(report["agents_md_pristine"], True)

    def test_idempotent_apply_keeps_metadata_untouched(self):
        """指纹已正确的干净 wiki 再 apply：metadata 零写盘（updated_at 不动）。"""
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            root = Path(d)
            self._backfill(root)
            before = wiki_store.load(root)
            rc, report, err = run_wiki(root, "upgrade", "--apply")
            self.assertEqual(rc, 0, err)
            self.assertEqual(report["status"], "done")
            after = wiki_store.load(root)
            self.assertEqual(after.updated_at, before.updated_at)

    def test_hand_edit_false_and_yes_resync(self):
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            root = Path(d)
            self._backfill(root)
            agents = root / "AGENTS.md"
            agents.write_text(
                agents.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8"
            )

            rc, report, err = run_wiki(root, "upgrade")
            self.assertEqual(rc, 0, err)
            self.assertIs(report["agents_md_pristine"], False)

            rc, report, err = run_wiki(root, "upgrade", "--apply")
            self.assertEqual(rc, 1, err)
            self.assertEqual(report["status"], "blocked_drift")
            self.assertIs(report["agents_md_pristine"], False)

            rc, report, err = run_wiki(root, "upgrade", "--apply", "--yes")
            self.assertEqual(rc, 0, err)
            self.assertEqual(report["status"], "done")
            self.assertEqual(wiki_store.load(root).agents_md_sha256, _sha256(agents))

            rc, report, err = run_wiki(root, "upgrade")
            self.assertEqual(rc, 0, err)
            self.assertIs(report["agents_md_pristine"], True)

    def test_missing_file_with_fingerprint_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            root = Path(d)
            self._backfill(root)
            (root / "AGENTS.md").unlink()
            rc, report, err = run_wiki(root, "upgrade")
            self.assertEqual(rc, 0, err)
            self.assertIs(report["agents_md_pristine"], False)


if __name__ == "__main__":
    unittest.main()
