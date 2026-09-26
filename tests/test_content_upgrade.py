#!/usr/bin/env python3
"""test_content_upgrade — `llmw wiki upgrade` / lint upgrade-plan 契约测试

钉住 agent 可见契约（此前零覆盖，改动靠人工审计）：
  1. upgrade 终态 `status` 合法 + `current_format` 来自 wiki AGENTS.md 版本钉
     （不冒充 CLI 常量——曾经恒等于 WIKI_FORMAT_VERSION，字段说谎）
  2. lint plan `fixtures_actions[]` 每条含 `to_action` 与 severity / rule_ref
     字段（agent 直接可执行）
  3. `agent_rules` 不含已退役动作（frontmatter-rename / file-move）与
     "不调 ingest / query / lint" 矛盾项（workflow 第 4/5 步必须跑 lint）
  4. skeleton check 的 expected/actual 语义：expected = 缺失清单（agent 照补），
     actual = 缺失计数；不再指向 agent 读不到的包内 fixtures

stdlib unittest + subprocess 调真实 CLI；scratch wiki 复用 test_content_wiki_fixtures
的 build_wiki（同一套字节金标准，避免两处漂移）。

运行:
  pytest tests/test_content_upgrade.py
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

import llmw  # noqa: E402
from test_content_wiki_fixtures import _render_agents_md, build_wiki  # noqa: E402

OLD_VERSION = "0.25.0"  # 真实历史版本——永远小于当前 target_format

LEGAL_STATUS = {
    "dry_run",
    "done",
    "done_with_residue",
    "blocked_drift",
    "verify_failed",
    "error",
}


def run_wiki(root, *args):
    """跑 `llmw wiki --path=<root> <args...> --json`，返回 (rc, report|None, stderr)。"""
    cmd = [sys.executable, "-m", "llmw", "wiki", "--path=" + str(root)]
    cmd.extend(args)
    cmd.append("--json")
    run_env = dict(os.environ, PYTHONPATH=str(REPO))
    run_env.pop("LLM_WIKI_ROOT", None)
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


class UpgradeStatusContractTest(unittest.TestCase):
    def test_current_format_comes_from_wiki_pin(self):
        """AGENTS.md 钉 OLD_VERSION → current_format 如实报 OLD_VERSION（不是 CLI 常量）。"""
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d, agents_md=_render_agents_md(format_version=OLD_VERSION))
            rc, report, err = run_wiki(d, "upgrade")
            self.assertEqual(rc, 0, err)
            self.assertIn(report["status"], LEGAL_STATUS)
            self.assertEqual(report["status"], "dry_run")
            self.assertEqual(report["current_format"], OLD_VERSION)
            self.assertEqual(report["target_format"], llmw.WIKI_FORMAT_VERSION)

    def test_clean_wiki_reaches_done(self):
        """clean scratch wiki → upgrade --apply 终态 done，版本钉随 render 落地。"""
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            rc, report, err = run_wiki(d, "upgrade", "--apply")
            self.assertEqual(rc, 0, err)
            self.assertEqual(report["status"], "done", report)
            self.assertEqual(report["current_format"], llmw.WIKI_FORMAT_VERSION)


class LintPlanContractTest(unittest.TestCase):
    def plan_for(self, d):
        rc, report, err = run_wiki(d, "lint", "--check-version", "--apply")
        self.assertEqual(rc, 0, err)
        self.assertIsNotNone(report, "lint --apply --json 未输出 JSON")
        return report["upgrade_plan"]

    def test_fixtures_actions_carry_executable_fields(self):
        """不合规 fixtures → plan.fixtures_actions[] 每条含 to_action / severity / rule_ref。"""
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            scripts = Path(d) / "scripts" / "SCRIPTS.md"
            text = scripts.read_text(encoding="utf-8")
            scripts.write_text("---\ntitle: Scripts\n---\n\n" + text, encoding="utf-8")
            plan = self.plan_for(d)
            strip = [
                a
                for a in plan["fixtures_actions"]
                if a["type"] == "fixtures-fix-strip-frontmatter"
            ]
            self.assertEqual(len(strip), 1, plan["fixtures_actions"])
            action = strip[0]
            self.assertIn("to_action", action)
            self.assertIn("severity", action)
            self.assertIn("rule_ref", action)

    def test_agent_rules_no_retired_or_contradictory_entries(self):
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d)
            rules = "\n".join(self.plan_for(d)["agent_rules"])
            self.assertNotIn("frontmatter-rename", rules)
            self.assertNotIn("file-move", rules)
            self.assertNotIn("不调 ingest / query / lint", rules)
            # 版本钉 / 骨架走 upgrade --apply，不手改 byte-owned
            self.assertIn("llmw wiki upgrade --apply", rules)
            self.assertIn("byte-owned", rules)


class DryRunVisibilityTest(unittest.TestCase):
    def test_dropped_sections_surface_in_dry_run(self):
        """新骨架没有的自定义 ## 段在 dry-run plan 前置可见——唯一数据丢失路径。"""
        custom_index = (
            "---\n"
            'title: "Test Index"\n'
            "type: index\n"
            'okf_version: "0.1"\n'
            "tags: [index]\n"
            "created: 2026-06-28 00:00\n"
            "updated: 2026-06-28 00:00\n"
            "---\n\n"
            "# Test Wiki\n\n"
            "> 说明块\n\n"
            "## MyCategory\n\n"
            "- [x](concepts/x.md) — 自定义段条目\n"
        )
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d, index_md=custom_index)
            rc, report, err = run_wiki(d, "upgrade")
            self.assertEqual(rc, 0, err)
            item = next(p for p in report["plan"] if p["file"] == "wiki/index.md")
            self.assertEqual(item["dropped_sections"], ["MyCategory"])


class SkeletonExpectedContractTest(unittest.TestCase):
    def test_expected_lists_missing_signals(self):
        """scripts-md-skeleton 失败时 expected = 缺失清单（含段标题名），actual = 计数。"""
        bad_scripts = "# Scripts\n\n单行，无说明块与 ## 索引\n"
        with tempfile.TemporaryDirectory() as d:
            build_wiki(d, scripts_md=bad_scripts)
            from llmw.content.wiki_fixtures import run_checks

            report = run_checks(Path(d), llmw.WIKI_FORMAT_VERSION)
            chk = next(c for c in report["checks"] if c["id"] == "scripts-md-skeleton")
            self.assertIs(chk["passed"], False)
            self.assertIn("## 索引", chk["expected"])
            self.assertIn("说明块", chk["expected"])
            self.assertEqual(chk["actual"], "缺失 2 项骨架信号")
            # 不再指向包内 assets（agent 读不到）
            self.assertNotIn("包内", chk["expected"])
            self.assertNotIn("fixtures", chk["expected"])


if __name__ == "__main__":
    unittest.main()
