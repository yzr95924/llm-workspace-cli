#!/usr/bin/env python3
"""test_content_workspace_fixtures — llmw.content.workspace_fixtures 端到端测试

stdlib unittest + subprocess 调真实模块（无 mock）：在 tmp 目录搭 scratch workspace
（clean / 老版 / 各类 drift），断言 --json 报告结构与 finding 内容。

运行:
  pytest tests/test_content_workspace_fixtures.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES_WS = REPO / "llmw" / "content" / "templates" / "workspace"
AGENTS_TEMPLATE = (TEMPLATES_WS / "workspace-agents-md-template.md").read_text(
    encoding="utf-8"
)
CLAUDE_TEMPLATE = (TEMPLATES_WS / "workspace-claude-md-template.md").read_text(
    encoding="utf-8"
)
FIXTURES_MEMORY_INDEX = (TEMPLATES_WS / "fixtures" / "memory-index.txt").read_text(
    encoding="utf-8"
)

OLD_VERSION = "0.6.2"  # 真实历史版本——永远小于当前 target_format

# 与 llmw/workspace/gitignore.py 的 gitignore managed block 逐字一致
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


def _target_format():
    """包内常量 llmw.WORKSPACE_FORMAT_VERSION（与 SKILL.md frontmatter 同 commit 对齐，CI gate 守护）。"""
    sys.path.insert(0, str(REPO))
    import llmw

    return llmw.WORKSPACE_FORMAT_VERSION


TARGET_FORMAT = _target_format()


def _render_agents_md(name="Test", date="2026-07-01", format_version=None, cli="0.1.0"):
    return (
        AGENTS_TEMPLATE.replace("{{WORKSPACE_DISPLAY_NAME}}", name)
        .replace("{{SETUP_DATE}}", date)
        .replace("{{WORKSPACE_FORMAT_VERSION}}", format_version or TARGET_FORMAT)
        .replace("{{CLI_VERSION}}", cli)
    )


def _render_claude_md(name="Test"):
    return CLAUDE_TEMPLATE.replace("{{WORKSPACE_DISPLAY_NAME}}", name)


def _clean_workspace_toml(format_version=None):
    return (
        "schema_version = 1\n"
        'created_at = "2026-07-01T00:00:00"\n'
        f'templates_version = "workspace_format = {format_version or TARGET_FORMAT}; wiki_format = 0.26.0"\n'
        "\n[wikis]\n"
    )


def build_workspace(
    root,
    agents_md=None,
    claude_md=None,
    gitignore=None,
    memory_index=None,
    workspace_toml=None,
):
    """搭 scratch workspace；缺省 = clean 形态，传参覆盖单件（None=默认，False=不建）。"""
    root = Path(root)
    (root / "MEMORY").mkdir(parents=True, exist_ok=True)
    if agents_md is not False:
        (root / "AGENTS.md").write_text(
            agents_md if agents_md is not None else _render_agents_md(),
            encoding="utf-8",
        )
    if claude_md is not False:
        (root / "CLAUDE.md").write_text(
            claude_md if claude_md is not None else _render_claude_md(),
            encoding="utf-8",
        )
    if gitignore is not False:
        (root / ".gitignore").write_text(
            gitignore if gitignore is not None else CLEAN_GITIGNORE, encoding="utf-8"
        )
    if memory_index is not False:
        (root / "MEMORY" / "MEMORY.md").write_text(
            memory_index if memory_index is not None else FIXTURES_MEMORY_INDEX,
            encoding="utf-8",
        )
    if workspace_toml is not False:
        (root / "workspace.toml").write_text(
            workspace_toml if workspace_toml is not None else _clean_workspace_toml(),
            encoding="utf-8",
        )
    return root


def run_check(root, extra_args=None, env=None):
    """跑 `llmw --workspace=<root> check-fixtures --json`，返回 (exit_code, report_dict)。"""
    cmd = [sys.executable, "-m", "llmw"]
    if root is not None:
        cmd.append("--workspace=" + str(root))
    cmd.append("check-fixtures")
    cmd.append("--json")
    cmd.extend(extra_args or [])
    run_env = dict(os.environ, PYTHONPATH=str(REPO))
    run_env.pop("LLMW_WORKSPACE", None)
    if env:
        run_env.update(env)
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
        raise AssertionError(
            f"CLI 未输出合法 JSON：exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        ) from None
    return proc.returncode, report


def check_by_id(report, cid):
    for c in report["checks"]:
        if c["id"] == cid:
            return c
    raise AssertionError(
        f"报告缺 check {cid}（实有: {[c['id'] for c in report['checks']]}）"
    )


class CleanWorkspaceTest(unittest.TestCase):
    def test_clean_workspace_all_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        self.assertEqual(code, 0, f"clean workspace 应 exit 0：{report}")
        self.assertEqual(report["target_format"], TARGET_FORMAT)
        self.assertEqual(report["summary"]["error"], 0)
        for c in report["checks"]:
            self.assertIs(c["passed"], True, f"clean 下 {c['id']} 应 pass：{c}")


class AgentsVersionCheckTest(unittest.TestCase):
    def test_stale_version_row_fails_with_older(self):
        """版本落后时两个 check 协同 fail（设计文档 §7.2 render-from-metadata 已取消正交性,
        两者都推荐 upgrade——冗余 benign）。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(
                tmp, agents_md=_render_agents_md(format_version=OLD_VERSION)
            )
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-version-is-current")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["comparison"], "older")
        self.assertEqual(c["fix"]["type"], "workspace-fix-agents-version")
        sync = check_by_id(report, "agents-md-template-sync")
        self.assertIs(
            sync["passed"],
            False,
            "render 用 CURRENT format → 字节差 → template-sync 必然 fail",
        )
        self.assertEqual(sync["fix"]["type"], "workspace-fix-agents-md-resync")

    def test_unparsable_version_row_fails_unknown(self):
        drifted = _render_agents_md().replace(
            f"| Workspace Format 版本 | {TARGET_FORMAT} |",
            "| Workspace Format 版本 | 待定 |",
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
        drifted = (
            _render_agents_md() + "\n## 本地加的私货段\n\n- 某条本 workspace 特有纪律\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, agents_md=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-md-template-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-agents-md-resync")
        self.assertIn("行与渲染稿不一致", c["actual"])


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
            "# Obsidian 配置（保留 vault 内容）\n.obsidian/workspace*\n.obsidian/cache\n\n",
            "",
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
        drifted = FIXTURES_MEMORY_INDEX.replace("## 索引", "## 条目")
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, memory_index=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "memory-index-skeleton")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["fix"]["type"], "workspace-fix-memory-index-skeleton")

    def test_growth_entries_still_pass(self):
        grown = FIXTURES_MEMORY_INDEX.replace(
            "（暂无条目）",
            "- some-case — 一句话摘要 → [正文](some-case.md)\n- 一行短事实",
        )
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, memory_index=grown)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        c = check_by_id(report, "memory-index-skeleton")
        self.assertIs(c["passed"], True)

    def test_frontmatter_in_memory_index_fails(self):
        drifted = "---\ntitle: MEMORY\n---\n\n" + FIXTURES_MEMORY_INDEX
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
            build_workspace(
                tmp, workspace_toml=_clean_workspace_toml(format_version=OLD_VERSION)
            )
            code, report = run_check(tmp)
        self.assertEqual(code, 0, "warn 级不阻断退出码")
        c = check_by_id(report, "workspace-toml-templates-version-sync")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["severity"], "warn")
        self.assertEqual(c["comparison"], "older")
        self.assertEqual(c["fix"]["type"], "workspace-fix-templates-version")

    def test_wiki_format_component_surfaced_as_info(self):
        """wiki_format 分量只展示不比对（跨 skill 指针）。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        c = check_by_id(report, "workspace-toml-templates-version-sync")
        self.assertEqual(c.get("wiki_format"), "0.26.0")

    def test_missing_templates_version_fails_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(
                tmp,
                workspace_toml='schema_version = 1\ncreated_at = "2026-07-01T00:00:00"\n\n[wikis]\n',
            )
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
        toml = (
            _clean_workspace_toml()
            + '\n[wikis.alpha]\npath = "alpha"\ncreated_at = "2026-07-01T00:00:00"\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=toml)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], True, c)

    def test_wiki_missing_path_fails(self):
        toml = (
            _clean_workspace_toml()
            + '\n[wikis.alpha]\ncreated_at = "2026-07-01T00:00:00"\n'
        )
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
        """缺 workspace.toml → 该 check skip（passed=None）。

        注：llmw CLI 入口对非 workspace 目录更严格（resolve_workspace_root 先拒），
        到不了本 check；此处直调业务入口 run() 验证 check 自身语义。
        """
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp, workspace_toml=False)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; from pathlib import Path; "
                    "from llmw.content.workspace_fixtures import run; "
                    "sys.exit(run(Path(sys.argv[1]), as_json=True))",
                    tmp,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env=dict(os.environ, PYTHONPATH=str(REPO)),
            )
            report = json.loads(proc.stdout)
        c = check_by_id(report, "workspace-toml-reads-satisfied")
        self.assertIs(c["passed"], None)


class TemplateNoOutboundRefsTest(unittest.TestCase):
    """模板零出边引用（架构不变量）——检测逻辑喂合成文本 + 端到端干净 pass。"""

    def _scan(self, text):
        """直接调用模块内的扫描函数（不改真实模板文件）。"""
        from llmw.content.workspace_fixtures import _scan_template_outbound_refs

        return _scan_template_outbound_refs(text)

    def test_clean_text_no_hits(self):
        self.assertEqual(
            self._scan("# 标题\n\n- 自包含措辞（见本文件顶部「关键」段）\n"), []
        )

    def test_skill_file_refs_detected(self):
        text = "见 workspace-claude-md-template.md 与 SKILL.md\n且 references/、yzr-llm-workspace-management、yzr-llm-wiki-management 都算"
        hits = self._scan(text)
        for pat in (
            "workspace-claude-md-template.md",
            "SKILL.md",
            "references/",
            "yzr-llm-workspace-management",
            "yzr-llm-wiki-management",
        ):
            self.assertTrue(any(pat in h for h in hits), f"{pat} 应被检出: {hits}")

    def test_arabic_section_ref_detected(self):
        self.assertTrue(
            any("§节号" in h for h in self._scan("详见 external-repo.md §1"))
        )

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

    def test_missing_root_and_env_exit_1(self):
        """无 --workspace / $LLMW_WORKSPACE / 默认目录（HOME 重定向到空 tmp）→ 用户错误 exit 1。

        （原模块 standalone 入口对缺 root 报 2；入口统一到 llmw 后走
        WorkspaceNotFound → exit_code=1，属既定错误分层：用户错误 1 / 环境错误 2。）
        """
        with tempfile.TemporaryDirectory() as home_tmp:
            proc = subprocess.run(
                [sys.executable, "-m", "llmw", "check-fixtures", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env={
                    k: v
                    for k, v in dict(
                        os.environ, PYTHONPATH=str(REPO), HOME=home_tmp
                    ).items()
                    if k != "LLMW_WORKSPACE"
                },
            )
        self.assertEqual(proc.returncode, 1)

    def test_json_report_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_workspace(tmp)
            code, report = run_check(tmp)
        for key in ("workspace_root", "target_format", "checks", "summary"):
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
