#!/usr/bin/env python3
"""test_check_workspace_fixtures.py — check_workspace_fixtures.py 的端到端测试

stdlib unittest + subprocess 调真实脚本（无 mock）：在 tmp 目录搭 scratch workspace
（clean / 老版 / 各类 drift），断言 --json 报告结构与 finding 内容。

运行:
  python3 scripts/test_check_workspace_fixtures.py        # 在 skill 仓根或 scripts/ 下均可
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "check_workspace_fixtures.py"
SKILL_ROOT = Path(__file__).resolve().parent.parent
AGENTS_TEMPLATE = (SKILL_ROOT / "references" / "workspace-agents-md-template.md").read_text(encoding="utf-8")
CLAUDE_TEMPLATE = (SKILL_ROOT / "references" / "workspace-claude-md-template.md").read_text(encoding="utf-8")
CANONICAL_MEMORY_INDEX = (SKILL_ROOT / "references" / "canonical" / "memory-index.md").read_text(encoding="utf-8")

OLD_VERSION = "0.6.2"  # 真实历史版本——永远小于当前 target_spec

# 与 workspace-spec §10 的最小 .gitignore 逐字一致
CLEAN_GITIGNORE = """# >>> llmw (managed by llmw) >>>
workspace_models.toml
# IDE 项目级 settings（可能含 token）：`**/` 锚定 workspace 根 + 任意深度子目录
# `settings*.json` 同时覆盖 `settings.json` + `settings.local.json` + `settings.<env>.json` 等变体
**/.claude/settings*.json
**/.qoder/settings*.json
# <<< llmw <<<

# OS / 编辑器
.DS_Store
.idea/
.vscode/
*.swp
*.swo

# Obsidian 配置（保留 vault 内容）
.obsidian/workspace*
.obsidian/cache

# 临时文件
*.tmp
*.bak
"""

# 0.7.0 前格式的 AGENTS.md（无「当前配置」表，§六 变更历史散文行）——老 workspace 形态
OLD_AGENTS_MD = """# Old Workspace — LLM 维护守则

> 这是本 workspace 的**纪律配置**——给跨 wiki 工作的 LLM 看的"工作守则"。

@MEMORY/MEMORY.md

## 一、本 workspace 的边界

（老格式正文，与新模板不同——template-sync 必然报 drift）

## 六、变更历史

| 日期 | 变更 |
| --- | --- |
| 2026-06-30 | workspace CLI 初始化生成（llmw v0.1.0 / workspace-spec v0.6.2） |
"""


def _target_spec():
    """读 SKILL.md metadata.workspace_spec_version（与脚本同一 SSOT）。"""
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^[ \t]*workspace_spec_version:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)
    if not m:
        raise AssertionError("SKILL.md 缺 metadata.workspace_spec_version")
    return m.group(1).strip()


TARGET_SPEC = _target_spec()


def _render_agents_md(name="Test", date="2026-07-01", spec=None, cli="0.1.0"):
    return (
        AGENTS_TEMPLATE.replace("{{WORKSPACE_DISPLAY_NAME}}", name)
        .replace("{{SETUP_DATE}}", date)
        .replace("{{WORKSPACE_SPEC_VERSION}}", spec or TARGET_SPEC)
        .replace("{{CLI_VERSION}}", cli)
    )


def _render_claude_md(name="Test"):
    return CLAUDE_TEMPLATE.replace("{{WORKSPACE_DISPLAY_NAME}}", name)


def _clean_workspace_toml(spec=None):
    return (
        "schema_version = 1\n"
        'created_at = "2026-07-01T00:00:00"\n'
        f'templates_version = "workspace_spec = {spec or TARGET_SPEC}; wiki_spec = 0.26.0"\n'
        "\n[wikis]\n"
    )


def build_workspace(root, agents_md=None, claude_md=None, gitignore=None, memory_index=None, workspace_toml=None):
    """搭 scratch workspace；缺省 = clean 0.7.0+ 形态，传参覆盖单件（None=默认，False=不建）。"""
    root = Path(root)
    (root / "MEMORY").mkdir(parents=True, exist_ok=True)
    if agents_md is not False:
        (root / "AGENTS.md").write_text(agents_md if agents_md is not None else _render_agents_md(), encoding="utf-8")
    if claude_md is not False:
        (root / "CLAUDE.md").write_text(claude_md if claude_md is not None else _render_claude_md(), encoding="utf-8")
    if gitignore is not False:
        (root / ".gitignore").write_text(gitignore if gitignore is not None else CLEAN_GITIGNORE, encoding="utf-8")
    if memory_index is not False:
        (root / "MEMORY" / "MEMORY.md").write_text(
            memory_index if memory_index is not None else CANONICAL_MEMORY_INDEX, encoding="utf-8"
        )
    if workspace_toml is not False:
        (root / "workspace.toml").write_text(
            workspace_toml if workspace_toml is not None else _clean_workspace_toml(), encoding="utf-8"
        )
    return root


def run_check(root, extra_args=None, env=None):
    """跑脚本 --json，返回 (exit_code, report_dict)。"""
    cmd = [sys.executable, str(SCRIPT_PATH)]
    if root is not None:
        cmd.append(str(root))
    cmd.append("--json")
    cmd.extend(extra_args or [])
    run_env = dict(os.environ)
    run_env.pop("LLMW_WORKSPACE", None)
    if env:
        run_env.update(env)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, env=run_env)
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(
            f"脚本未输出合法 JSON：exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        ) from None
    return proc.returncode, report


def check_by_id(report, cid):
    for c in report["checks"]:
        if c["id"] == cid:
            return c
    raise AssertionError(f"报告缺 check {cid}（实有: {[c['id'] for c in report['checks']]}）")


class CleanWorkspaceTest(unittest.TestCase):
    def test_clean_workspace_all_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        self.assertEqual(code, 0, f"clean workspace 应 exit 0：{report}")
        self.assertEqual(report["target_spec"], TARGET_SPEC)
        self.assertEqual(report["summary"]["error"], 0)
        for c in report["checks"]:
            self.assertIs(c["passed"], True, f"clean 下 {c['id']} 应 pass：{c}")


class AgentsVersionCheckTest(unittest.TestCase):
    def test_stale_version_row_fails_with_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 版本行落后、正文其余与新模板一致——与 template-sync 正交（后者应 pass）
            build_workspace(tmp, agents_md=_render_agents_md(spec=OLD_VERSION))
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-version-is-current")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["comparison"], "older")
        self.assertEqual(c["fix"]["type"], "workspace-fix-agents-version")
        sync = check_by_id(report, "agents-md-template-sync")
        self.assertIs(sync["passed"], True, "版本行落后不影响正文同步（正交）")

    def test_unparsable_version_row_fails_unknown(self):
        drifted = _render_agents_md().replace(
            f"| Workspace Spec 版本 | {TARGET_SPEC} |", "| Workspace Spec 版本 | 待定 |"
        )
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, agents_md=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-version-is-current")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["comparison"], "unknown")


class AgentsTemplateSyncTest(unittest.TestCase):
    def test_local_customization_fails_resync(self):
        drifted = _render_agents_md() + "\n## 本地加的私货段\n\n- 某条本 workspace 特有纪律\n"
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, agents_md=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-md-template-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-agents-md-resync")
        self.assertIn("行与模板渲染稿不一致", c["actual"])

    def test_old_workspace_fallback_extraction(self):
        """0.7.0- 老格式（无「当前配置」表）：§六 散文行 fallback 提取出版本 → comparison=older 而非 unknown。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, agents_md=OLD_AGENTS_MD)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        ver = check_by_id(report, "agents-version-is-current")
        self.assertIs(ver["passed"], False)
        self.assertEqual(ver["comparison"], "older", f"老 §六 散文行应 fallback 解析出 0.6.2：{ver}")
        sync = check_by_id(report, "agents-md-template-sync")
        self.assertIs(sync["passed"], False)
        self.assertEqual(sync["fix"]["type"], "workspace-fix-agents-md-resync")


class ClaudeMdTemplateSyncTest(unittest.TestCase):
    def test_drifted_claude_md_fails_resync(self):
        drifted = _render_claude_md() + "\n本地加的一行\n"
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, claude_md=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "claude-md-template-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-claude-md-resync")

    def test_missing_claude_md_fails_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, claude_md=False)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "claude-md-template-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-claude-md-create")


class GitignoreSkeletonTest(unittest.TestCase):
    def test_missing_section_fails(self):
        drifted = CLEAN_GITIGNORE.replace(
            "# Obsidian 配置（保留 vault 内容）\n.obsidian/workspace*\n.obsidian/cache\n\n", ""
        )
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, gitignore=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "gitignore-skeleton")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-gitignore-skeleton")
        self.assertIn("Obsidian", c["actual"])

    def test_missing_llmw_block_rule_fails(self):
        drifted = CLEAN_GITIGNORE.replace("**/.qoder/settings*.json\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, gitignore=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "gitignore-skeleton")
        self.assertIs(c["passed"], False)
        self.assertIn("qoder", c["actual"])

    def test_user_removed_single_editor_rule_still_passes(self):
        """容忍用户删单条编辑器规则（段还在、段内 ≥1 规则即可）。"""
        customized = CLEAN_GITIGNORE.replace(".idea/\n", "")
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, gitignore=customized)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        c = check_by_id(report, "gitignore-skeleton")
        self.assertIs(c["passed"], True)


class MemoryIndexSkeletonTest(unittest.TestCase):
    def test_missing_memory_index_fails_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, memory_index=False)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "memory-index-skeleton")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-memory-index-init")

    def test_missing_index_heading_fails(self):
        drifted = CANONICAL_MEMORY_INDEX.replace("## 索引", "## 条目")
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, memory_index=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "memory-index-skeleton")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-memory-index-skeleton")

    def test_growth_entries_still_pass(self):
        grown = CANONICAL_MEMORY_INDEX.replace(
            "（暂无条目）", "- some-case — 一句话摘要 → [正文](some-case.md)\n- 一行短事实"
        )
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, memory_index=grown)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        c = check_by_id(report, "memory-index-skeleton")
        self.assertIs(c["passed"], True)

    def test_frontmatter_in_memory_index_fails(self):
        drifted = "---\ntitle: MEMORY\n---\n\n" + CANONICAL_MEMORY_INDEX
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, memory_index=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "memory-index-skeleton")
        self.assertIs(c["passed"], False)
        self.assertIn("frontmatter", c["actual"])


class WorkspaceTomlVersionTest(unittest.TestCase):
    def test_stale_templates_version_warns_but_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=_clean_workspace_toml(spec=OLD_VERSION))
            code, report = run_check(tmp)
        self.assertEqual(code, 0, "warn 级不阻断退出码")
        c = check_by_id(report, "workspace-toml-templates-version-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["severity"], "warn")
        self.assertEqual(c["comparison"], "older")
        self.assertEqual(c["fix"]["type"], "workspace-fix-templates-version")

    def test_wiki_spec_component_surfaced_as_info(self):
        """wiki_spec 分量只展示不比对（跨 skill 指针）。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        c = check_by_id(report, "workspace-toml-templates-version-sync")
        self.assertEqual(c.get("wiki_spec"), "0.26.0")

    def test_missing_templates_version_fails_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml='schema_version = 1\ncreated_at = "2026-07-01T00:00:00"\n\n[wikis]\n')
            code, report = run_check(tmp)
        # check#6（warn）对缺 templates_version 报 unknown 不阻断；但 workspace-toml-reads-satisfied
        # （error）也查 templates_version 缺失 → 整体 exit 1
        self.assertEqual(code, 1)
        c = check_by_id(report, "workspace-toml-templates-version-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["comparison"], "unknown")


class WorkspaceTomlReadsSatisfiedTest(unittest.TestCase):
    def test_clean_no_wiki_passes(self):
        """无 wiki（空 [wikis] table）→ 只校验 templates_version，reads-satisfied pass。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            _, report = run_check(tmp)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], True)

    def test_wiki_with_path_and_created_at_passes(self):
        toml = _clean_workspace_toml() + '\n[wikis.alpha]\npath = "alpha"\ncreated_at = "2026-07-01T00:00:00"\n'
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=toml)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], True, c)

    def test_wiki_missing_path_fails(self):
        toml = _clean_workspace_toml() + '\n[wikis.alpha]\ncreated_at = "2026-07-01T00:00:00"\n'
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=toml)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], False)
        self.assertIn("[wikis.alpha].path", c["actual"])

    def test_wiki_missing_created_at_fails(self):
        toml = _clean_workspace_toml() + '\n[wikis.alpha]\npath = "alpha"\n'
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=toml)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], False)
        self.assertIn("[wikis.alpha].created_at", c["actual"])

    def test_missing_templates_version_fails(self):
        toml = 'schema_version = 1\ncreated_at = "2026-07-01T00:00:00"\n\n[wikis]\n'
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=toml)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], False)
        self.assertIn("templates_version", c["actual"])

    def test_missing_workspace_toml_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=False)
            _, report = run_check(tmp)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], None)


class TemplateNoOutboundRefsTest(unittest.TestCase):
    """模板零出边引用（0.8.0+ 架构不变量）——检测逻辑喂合成文本 + 端到端干净 pass。"""

    def _scan(self, text):
        """直接调用脚本内的扫描函数（不改真实模板文件）。"""
        sys.path.insert(0, str(SCRIPT_PATH.parent))
        try:
            from check_workspace_fixtures import _scan_template_outbound_refs

            return _scan_template_outbound_refs(text)
        finally:
            sys.path.remove(str(SCRIPT_PATH.parent))

    def test_clean_text_no_hits(self):
        self.assertEqual(self._scan("# 标题\n\n- 自包含措辞（见本文件顶部「关键」段）\n"), [])

    def test_skill_file_refs_detected(self):
        text = "见 `workspace-spec.md` §15 与 `workspace-claude-md-template.md`\n且 SKILL.md、references/、yzr-llm-workspace-management、yzr-llm-wiki-management 都算"
        hits = self._scan(text)
        for pat in (
            "workspace-spec.md",
            "workspace-claude-md-template.md",
            "SKILL.md",
            "references/",
            "yzr-llm-workspace-management",
            "yzr-llm-wiki-management",
        ):
            self.assertTrue(any(pat in h for h in hits), f"{pat} 应被检出: {hits}")

    def test_arabic_section_ref_detected(self):
        self.assertTrue(any("§节号" in h for h in self._scan("详见 spec §13.3")))

    def test_chinese_section_ref_ok(self):
        self.assertEqual(self._scan("详见本文件 §六「迁移例外」段"), [])

    def test_check_passes_on_clean_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        self.assertIs(check_by_id(report, "template-no-outbound-refs")["passed"], True)


class CliBehaviorTest(unittest.TestCase):
    def test_env_var_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(None, env={"LLMW_WORKSPACE": tmp})
        self.assertEqual(code, 0)
        self.assertEqual(report["workspace_root"], str(Path(tmp).resolve()))

    def test_missing_root_and_env_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env={k: v for k, v in os.environ.items() if k != "LLMW_WORKSPACE"},
        )
        self.assertEqual(proc.returncode, 2)

    def test_json_report_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        for key in ("workspace_root", "target_spec", "checks", "summary"):
            self.assertIn(key, report)
        for key in ("error", "warn", "info", "pass", "skip"):
            self.assertIn(key, report["summary"])
        expected_ids = {
            "agents-version-is-current",
            "agents-md-template-sync",
            "claude-md-template-sync",
            "gitignore-skeleton",
            "memory-index-skeleton",
            "workspace-toml-templates-version-sync",
            "workspace-toml-reads-satisfied",
            "template-no-outbound-refs",
        }
        self.assertEqual({c["id"] for c in report["checks"]}, expected_ids)
        for c in report["checks"]:
            for key in (
                "id",
                "file",
                "passed",
                "severity",
                "rule_ref",
                "desc",
                "expected",
                "actual",
                "skipped",
                "comparison",
                "fix",
            ):
                self.assertIn(key, c, f"check {c['id']} 缺字段 {key}")


if __name__ == "__main__":
    unittest.main()
