"""test_content_external_anchor — llmw.content.external_anchor 端到端测试

focus：store roundtrip (save 严格 / load lenient / 空 → 删文件) + 4 命令
(add/remove/list/rebuild relink；clone 路径不进单测以避免网络依赖 + CI 时长膨胀)。

运行：
  pytest tests/test_content_external_anchor.py -q
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHONPATH = str(REPO)


# ---------- Store 层直测 ----------


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ext = self.root / "ext"
        self.ext.mkdir()
        self.anchor = self.ext / ".symlink-anchor.toml"

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_and_load_roundtrip(self):
        from llmw.content.external_anchor import load, save

        entries = [
            {
                "symlink": "linux",
                "target": "~/src/linux",
                "captured_at": "2026-08-22",
                "kind": "external-repo",
                "remote_url": "https://example.com/linux.git",
                "branch": "master",
            }
        ]
        save(self.anchor, entries)
        assert self.anchor.is_file()
        text = self.anchor.read_text(encoding="utf-8")
        assert "[[entry]]" in text
        assert 'symlink = "linux"' in text
        assert "schema_version = 1" in text

        loaded = load(self.anchor)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["symlink"] == "linux"
        assert loaded[0]["target"] == "~/src/linux"
        assert loaded[0]["remote_url"] == "https://example.com/linux.git"

    def test_save_empty_entries_deletes_file(self):
        from llmw.content.external_anchor import save

        save(
            self.anchor,
            [
                {
                    "symlink": "x",
                    "target": "/t",
                    "captured_at": "2026-01-01",
                    "kind": "external-repo",
                }
            ],
        )
        assert self.anchor.is_file()
        save(self.anchor, [])
        assert not self.anchor.is_file()

    def test_save_validates_required_fields(self):
        from llmw.content.external_anchor import save

        with self.assertRaises(ValueError):
            save(self.anchor, [{"symlink": "x"}])  # 缺 target/captured_at/kind

    def test_save_validates_name_regex(self):
        from llmw.content.external_anchor import save

        with self.assertRaises(ValueError):
            save(
                self.anchor,
                [
                    {
                        "symlink": "Bad_Name",
                        "target": "/t",
                        "captured_at": "d",
                        "kind": "external-repo",
                    }
                ],
            )

    def test_save_validates_kind(self):
        from llmw.content.external_anchor import save

        with self.assertRaises(ValueError):
            save(
                self.anchor,
                [{"symlink": "x", "target": "/t", "captured_at": "d", "kind": "other"}],
            )

    def test_load_missing_file_returns_none(self):
        from llmw.content.external_anchor import load

        assert load(self.anchor) is None

    def test_load_corrupt_returns_none(self):
        from llmw.content.external_anchor import load

        self.anchor.write_text("!not toml at all\n{{{\n", encoding="utf-8")
        assert load(self.anchor) is None

    def test_load_filters_invalid_entries(self):
        from llmw.content.external_anchor import load

        # 手改写一份：一条 valid + 一条缺 kind
        self.anchor.write_text(
            "schema_version = 1\n\n"
            '[[entry]]\nsymlink = "good"\ntarget = "/g"\ncaptured_at = "2026-01-01"\n'
            'kind = "external-repo"\n\n'
            '[[entry]]\nsymlink = "bad"\ntarget = "/b"\ncaptured_at = "2026-01-01"\n',
            encoding="utf-8",
        )
        loaded = load(self.anchor)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["symlink"] == "good"


# ---------- 命令层 subprocess ----------


def _run(args, cwd=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    p = subprocess.run(
        [sys.executable, "-m", "llmw.cli"] + args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    return p


class CommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # wiki 根
        self.wiki = self.root / "wiki"
        self.wiki.mkdir()
        # 非 git target
        self.nongit = self.root / "nongit"
        self.nongit.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _wiki_args(self):
        # 全局 flag 必须等号形式（SpaceFormNotAllowed 纪律）
        return ["wiki", f"--path={self.wiki}", "external"]

    def test_add_non_git_and_list(self):
        p = _run(
            self._wiki_args() + ["add", str(self.nongit), "--name=nongit"],
            cwd=str(self.wiki),
        )
        assert p.returncode == 0, p.stderr
        assert (self.wiki / "raw" / "external" / "nongit").is_symlink()
        assert (self.wiki / "raw" / "external" / ".symlink-anchor.toml").is_file()

        # list --json 可读 + status ok
        p = _run(self._wiki_args() + ["list", "--json"], cwd=str(self.wiki))
        assert p.returncode == 0, p.stderr
        rows = json.loads(p.stdout)
        assert len(rows) == 1
        assert rows[0]["name"] == "nongit"
        assert rows[0]["status"] == "ok"
        # 非 git target → 无 remote/branch
        assert rows[0]["remote"] == ""
        assert rows[0]["branch"] == ""

    def test_add_duplicate_rejected(self):
        _run(self._wiki_args() + ["add", str(self.nongit), "--name=x"])
        p = _run(self._wiki_args() + ["add", str(self.nongit), "--name=x"])
        assert p.returncode == 1
        # 重复拒绝有两种文案：路径已占用（symlink 已存在）或 已含 entry（anchor 重复）
        assert ("已占用" in p.stderr) or ("已含 entry" in p.stderr)

    def test_add_bad_name_rejected(self):
        p = _run(self._wiki_args() + ["add", str(self.nongit), "--name=Bad_Name"])
        assert p.returncode == 1
        assert "kebab-case" in p.stderr

    def test_add_nonexistent_target_rejected(self):
        p = _run(self._wiki_args() + ["add", str(self.root / "nope"), "--name=x"])
        assert p.returncode == 1
        assert "不存在" in p.stderr

    def test_remove_deletes_symlink_and_anchor_entry(self):
        _run(self._wiki_args() + ["add", str(self.nongit), "--name=x"])
        p = _run(self._wiki_args() + ["remove", "x"])
        assert p.returncode == 0, p.stderr
        assert not (self.wiki / "raw" / "external" / "x").exists()
        # last entry → anchor file 应当被删
        assert not (self.wiki / "raw" / "external" / ".symlink-anchor.toml").is_file()
        # external dir 应当被 rmdir
        assert not (self.wiki / "raw" / "external").exists()

    def test_remove_non_symlink_rejected(self):
        (self.wiki / "raw" / "external").mkdir(parents=True, exist_ok=True)
        (self.wiki / "raw" / "external" / "real").mkdir()  # 普通目录，非 symlink
        # 手写 anchor entry 指向 real
        (self.wiki / "raw" / "external" / ".symlink-anchor.toml").write_text(
            'schema_version = 1\n\n[[entry]]\nsymlink = "real"\n'
            'target = "/t"\ncaptured_at = "d"\nkind = "external-repo"\n',
            encoding="utf-8",
        )
        p = _run(self._wiki_args() + ["remove", "real"])
        assert p.returncode == 1
        assert "普通文件/目录" in p.stderr
        # 被保护的目录仍要存在
        assert (self.wiki / "raw" / "external" / "real").is_dir()

    def test_remove_unknown_entry_error(self):
        _run(self._wiki_args() + ["add", str(self.nongit), "--name=x"])
        p = _run(self._wiki_args() + ["remove", "y"])
        assert p.returncode == 1

    def test_list_no_anchor_noop(self):
        p = _run(self._wiki_args() + ["list"])
        assert p.returncode == 0
        assert "(no external entries)" in p.stderr

    def test_rebuild_relink(self):
        """删 symlink 留 anchor，rebuild 应 relink。"""
        _run(self._wiki_args() + ["add", str(self.nongit), "--name=x"])
        (self.wiki / "raw" / "external" / "x").unlink()
        p = _run(self._wiki_args() + ["rebuild", "--yes"])
        assert p.returncode == 0, p.stderr
        assert (self.wiki / "raw" / "external" / "x").is_symlink()

    def test_rebuild_no_anchor_noop(self):
        p = _run(self._wiki_args() + ["rebuild"])
        assert p.returncode == 0
        assert "无 anchor 文件" in p.stderr

    def test_add_refuses_to_overwrite_corrupt_anchor(self):
        """anchor 文件存在但损坏 → add 拒绝静默覆盖（保护手工修复现场）。"""
        ext_dir = self.wiki / "raw" / "external"
        ext_dir.mkdir(parents=True, exist_ok=True)
        corrupt = ext_dir / ".symlink-anchor.toml"
        corrupt.write_text("!not toml at all\n{{{\n", encoding="utf-8")
        p = _run(self._wiki_args() + ["add", str(self.nongit), "--name=x"])
        assert p.returncode == 1
        assert "解析失败" in p.stderr
        # 损坏的文件保持原样，没被覆盖
        assert corrupt.read_text(encoding="utf-8").startswith("!not toml")

    def test_add_with_git_identity_best_effort(self):
        """git 仓 target：应读出 remote_url + branch（用 file:// 或本地初始化）。"""
        g = self.root / "gitty"
        g.mkdir()
        # 初始化 git 仓 + 设 fake origin
        subprocess.run(["git", "init", "-q", str(g)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(g),
                "remote",
                "add",
                "origin",
                "https://example.com/g.git",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(g),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "x",
            ],
            check=True,
        )
        p = _run(self._wiki_args() + ["add", str(g), "--name=gitty"])
        assert p.returncode == 0, p.stderr
        p = _run(self._wiki_args() + ["list", "--json"])
        rows = json.loads(p.stdout)
        assert rows[0]["remote"] == "https://example.com/g.git"
        # HEAD 默认是 master 或 main，取决于 git 配置；只断言非空
        assert rows[0]["branch"] != ""


if __name__ == "__main__":
    unittest.main()
