#!/usr/bin/env python3
"""test_content_upgrade_workspace — `llmw upgrade`（workspace 侧）契约测试

钉住此前零覆盖的 workspace 升级引擎（gitignore managed block 曾是死路径：
`_extract_managed_block` 的子串与 gitignore.py SSOT 的两个 marker 都匹配不上，
plan_resync 恒判"无 drift"、apply 分支不可达）：

  1. `_extract_managed_block` 能按 SSOT marker 提取块
  2. stale managed block → plan_resync 产出 gitignore-block 动作（带 diff）
  3. `upgrade --apply --yes` → block 更新为当前 GITIGNORE_LINES，终态 done
  4. `current_format` 如实报 AGENTS.md 版本钉（不冒充 CLI 常量）

stdlib unittest + 真实 CLI；scratch workspace 复用
test_content_workspace_fixtures.build_workspace（同一套字节金标准，避免两处漂移）。

运行:
  pytest tests/test_content_upgrade_workspace.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from test_content_workspace_fixtures import (  # noqa: E402
    CLEAN_GITIGNORE,
    OLD_VERSION,
    _clean_workspace_toml,
    _render_agents_md,
    build_workspace,
)


def run_ws_upgrade(root, *args):
    """跑 `llmw --workspace=<root> upgrade <args...> --json`，返回 (rc, report, stderr)。"""
    cmd = [sys.executable, "-m", "llmw", "--workspace=" + str(root), "upgrade"]
    cmd.extend(args)
    cmd.append("--json")

    run_env = dict(os.environ, PYTHONPATH=str(REPO))
    run_env.pop("LLMW_WORKSPACE", None)
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=run_env,
    )
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        report = None
    return proc.returncode, report, proc.stderr


def _stale_gitignore():
    """CLEAN_GITIGNORE 去掉 3 条扩展规则 → 老版 managed block（缺 workspace_local 等）。"""
    return (
        CLEAN_GITIGNORE.replace("workspace_local.toml\n", "")
        .replace(".llmw-trash/\n", "")
        .replace("**/opencode.json\n", "")
    )


class ExtractManagedBlockTest(unittest.TestCase):
    def test_extract_managed_block_uses_ssot_markers(self):
        """marker 子串必须与 gitignore.py SSOT 对齐（曾是恒 None 的根因）。"""
        from llmw.content.upgrade_workspace import _extract_managed_block
        from llmw.workspace.gitignore import (
            GITIGNORE_LINES,
            GITIGNORE_MARKER_END,
            GITIGNORE_MARKER_START,
        )

        text = (
            "# 用户自定义规则\n*.log\n\n"
            + GITIGNORE_MARKER_START
            + "\n"
            + "\n".join(GITIGNORE_LINES)
            + "\n"
            + GITIGNORE_MARKER_END
            + "\n"
        )
        block = _extract_managed_block(text)
        self.assertIsNotNone(block, "SSOT marker 形态的 managed block 应能提取")
        self.assertTrue(block.startswith(GITIGNORE_MARKER_START))
        self.assertTrue(block.endswith(GITIGNORE_MARKER_END))

    def test_extract_managed_block_absent_returns_none(self):
        from llmw.content.upgrade_workspace import _extract_managed_block

        self.assertIsNone(_extract_managed_block("*.tmp\n"))


class StaleBlockPlanTest(unittest.TestCase):
    def test_stale_block_yields_gitignore_block_action(self):
        """stale block → plan_resync 产出带 diff 的 gitignore-block 动作（曾恒 no-op）。"""
        from llmw.content.upgrade_workspace import plan_resync

        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, gitignore=_stale_gitignore())
            plan = plan_resync(Path(tmp))
        item = next(p for p in plan if p["rel_path"] == ".gitignore")
        self.assertEqual(item["action"], "gitignore-block")
        self.assertIsNotNone(item["diff"], "stale block 应产生 diff")
        self.assertIn("new_full_text", item)


class UpgradeApplyHealsBlockTest(unittest.TestCase):
    def test_apply_updates_stale_block_and_reaches_done(self):
        from llmw.workspace.gitignore import GITIGNORE_LINES

        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, gitignore=_stale_gitignore())
            rc, report, err = run_ws_upgrade(tmp, "--apply", "--yes")
            self.assertEqual(rc, 0, err)
            self.assertIsNotNone(report, "upgrade --json 未输出 JSON")
            ws = report["workspace"]
            self.assertEqual(ws["status"], "done", ws)
            text = (Path(tmp) / ".gitignore").read_text(encoding="utf-8")
            for rule in GITIGNORE_LINES:
                self.assertIn(rule, text, f"managed block 应含 {rule}")

    def test_apply_user_rules_outside_block_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, gitignore="*.custom-log\n\n" + _stale_gitignore())
            rc, report, err = run_ws_upgrade(tmp, "--apply", "--yes")
            self.assertEqual(rc, 0, err)
            text = (Path(tmp) / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("*.custom-log", text, "block 外用户规则不应被动")


class WorkspaceCurrentFormatTest(unittest.TestCase):
    def test_current_format_reflects_agents_pin(self):
        """AGENTS.md 钉 OLD_VERSION → current_format 如实报（不是 CLI 常量）。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(
                tmp,
                agents_md=_render_agents_md(format_version=OLD_VERSION),
                workspace_toml=_clean_workspace_toml(format_version=OLD_VERSION),
            )
            rc, report, err = run_ws_upgrade(tmp)
        self.assertEqual(rc, 0, err)
        ws = report["workspace"]
        self.assertEqual(ws["status"], "dry_run")
        self.assertEqual(ws["current_format"], OLD_VERSION)


if __name__ == "__main__":
    unittest.main()
