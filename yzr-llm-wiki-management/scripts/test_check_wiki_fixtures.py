#!/usr/bin/env python3
"""test_check_wiki_fixtures.py — check_wiki_fixtures.py 的端到端测试

stdlib unittest + subprocess 调真实脚本（无 mock）：在 tmp 目录搭 scratch wiki
（clean / 各类 drift），断言 --json 报告结构与 finding 内容。standalone——不依赖
CLI / lint_wiki.py，只读 SKILL 仓的模板 + canonical + fixtures。

运行:
  python3 scripts/test_check_wiki_fixtures.py        # 在 skill 仓根或 scripts/ 下均可
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "check_wiki_fixtures.py"
SKILL_ROOT = Path(__file__).resolve().parent.parent
AGENTS_TEMPLATE = (SKILL_ROOT / "references" / "agents-md-template.md").read_text(encoding="utf-8")
CANONICAL_DIR = SKILL_ROOT / "references" / "canonical"
WIKI_GITIGNORE = (SKILL_ROOT / "references" / "fixtures" / "gitignore.txt").read_text(encoding="utf-8")

OLD_VERSION = "0.25.0"  # 真实历史版本——永远小于当前 target_spec


def _target_spec():
    """读 SKILL.md metadata.wiki_spec_version（与脚本同一 SSOT）。"""
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^[ \t]*wiki_spec_version:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)
    if not m:
        raise AssertionError("SKILL.md 缺 metadata.wiki_spec_version")
    return m.group(1).strip()


def _fixtures_check_count():
    """读 SKILL.md metadata.fixtures_check_count——check 注册数的 SSOT 声明（metadata 侧）。

    代码侧真源是 CHECK_REGISTRY；本测试断言两侧一致（metadata 改动不改代码时测试 fail），
    让"20/21"这类计数改动必须同时落 metadata + 代码。
    """
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^[ \t]*fixtures_check_count:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)
    if not m:
        raise AssertionError("SKILL.md 缺 metadata.fixtures_check_count")
    return int(m.group(1).strip())


TARGET_SPEC = _target_spec()
FIXTURES_CHECK_COUNT = _fixtures_check_count()


def _render_agents_md(topic="Test", date="2026-06-28", cli="0.1.0", spec=None):
    return (
        AGENTS_TEMPLATE.replace("{{TOPIC_NAME}}", topic)
        .replace("{{SETUP_DATE}}", date)
        .replace("{{CLI_VERSION}}", cli)
        .replace("{{WIKI_SPEC_VERSION}}", spec or TARGET_SPEC)
    )


def _wiki_metadata(missing=None):
    """构造合规 wiki_metadata.toml；missing=要剔除的字段名集合（测 reads-satisfied 反例）。"""
    fields = [
        ("schema_version", "2"),
        ("name", '"Test"'),
        ("topic", '"Test"'),
        ("created_at", '"2026-06-28T00:00:00Z"'),
        ("updated_at", '"2026-06-28T00:00:00Z"'),
        ("display_name", '"Test"'),
        ("description", '"d"'),
        ("tags", '["x"]'),
        ("model", '"m1"'),
    ]
    missing = missing or set()
    return "\n".join(f"{k} = {v}" for k, v in fields if k not in missing) + "\n"


def _canonical(name):
    return (CANONICAL_DIR / name).read_text(encoding="utf-8")


def build_wiki(
    root,
    agents_md=None,
    gitignore=None,
    wiki_metadata=None,
    index_md=None,
    log_md=None,
    tags_md=None,
    memory_index=None,
    scripts_md=None,
):
    """搭 scratch wiki；缺省 = clean 合规形态，传参覆盖单件（None=默认，False=不建）。"""
    root = Path(root)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "MEMORY").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "raw" / "articles").mkdir(parents=True, exist_ok=True)
    (root / "raw" / "assets").mkdir(parents=True, exist_ok=True)
    if agents_md is not False:
        (root / "AGENTS.md").write_text(agents_md if agents_md is not None else _render_agents_md(), encoding="utf-8")
    if gitignore is not False:
        (root / ".gitignore").write_text(gitignore if gitignore is not None else WIKI_GITIGNORE, encoding="utf-8")
    if wiki_metadata is not False:
        (root / "wiki_metadata.toml").write_text(
            wiki_metadata if wiki_metadata is not None else _wiki_metadata(), encoding="utf-8"
        )
    if index_md is not False:
        (root / "wiki" / "index.md").write_text(
            index_md if index_md is not None else _canonical("index.md"), encoding="utf-8"
        )
    if log_md is not False:
        (root / "wiki" / "log.md").write_text(log_md if log_md is not None else _canonical("log.md"), encoding="utf-8")
    if tags_md is not False:
        (root / "wiki" / "tags.md").write_text(
            tags_md if tags_md is not None else _canonical("tags.md"), encoding="utf-8"
        )
    if memory_index is not False:
        (root / "MEMORY" / "MEMORY.md").write_text(
            memory_index if memory_index is not None else _canonical("memory-index.md"), encoding="utf-8"
        )
    if scripts_md is not False:
        (root / "scripts" / "SCRIPTS.md").write_text(
            scripts_md if scripts_md is not None else _canonical("scripts.md"), encoding="utf-8"
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
    run_env.pop("LLM_WIKI_ROOT", None)
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


class CleanWikiTest(unittest.TestCase):
    def test_clean_wiki_no_error(self):
        """clean wiki：所有 check pass 或 skip（symlink ×3 + memory-entries 无条目 skip），无 error。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp)
            code, report = run_check(tmp)
        self.assertEqual(report["target_spec"], TARGET_SPEC)
        self.assertEqual(report["summary"]["error"], 0, f"clean wiki 不应有 error：{report['summary']}")
        for c in report["checks"]:
            self.assertIsNot(c["passed"], False, f"clean 下 {c['id']} 不应 fail：{c}")

    def test_check_count_matches_metadata(self):
        """check 总数 = SKILL.md metadata.fixtures_check_count（metadata 与代码两侧对账）。

        代码侧注册数变化（新增 / 删除 check）但 metadata 未同步 → 本测试 fail。
        """
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp)
            _, report = run_check(tmp)
        self.assertEqual(
            len(report["checks"]),
            FIXTURES_CHECK_COUNT,
            f"实际 check 数 {len(report['checks'])} != metadata.fixtures_check_count "
            f"({FIXTURES_CHECK_COUNT})——改代码时需同步 SKILL.md frontmatter",
        )


class LogLineRegexConsistencyTest(unittest.TestCase):
    """log 条目正则双份（log_format.py SSOT + check_wiki_fixtures.py vendored 副本）必须逐字一致。

    vendored 副本是 0.28.0 有意为之（standalone 约束）；本测试守护它不漂移。
    """

    def test_log_line_re_pattern_identical(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import log_format  # noqa: E402

        vendored = (SKILL_ROOT / "scripts" / "check_wiki_fixtures.py").read_text(encoding="utf-8")
        m = re.search(r"LOG_LINE_RE = re\.compile\(\n(.*?)\n\)", vendored, re.DOTALL)
        self.assertIsNotNone(m, "check_wiki_fixtures.py 未找到 vendored LOG_LINE_RE")
        parts = []
        for ln in m.group(1).splitlines():
            lit = re.match(r'\s*r?"(.*)"\s*$', ln)
            self.assertIsNotNone(lit, f"无法解析 vendored 正则片段行: {ln!r}")
            parts.append(lit.group(1))
        self.assertEqual(
            "".join(parts),
            log_format.LOG_LINE_RE.pattern,
            "两脚本 log 条目正则漂移——改 log_format.py 时需同步 vendored 副本",
        )


class WikiMetadataReadsSatisfiedTest(unittest.TestCase):
    def test_six_fields_present_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp)
            _, report = run_check(tmp)
        c = check_by_id(report, "wiki-metadata-reads-satisfied")
        self.assertIs(c["passed"], True)

    def test_missing_topic_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, wiki_metadata=_wiki_metadata(missing={"topic"}))
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "wiki-metadata-reads-satisfied")
        self.assertIs(c["passed"], False)
        self.assertIn("topic", c["actual"])

    def test_missing_multiple_fields_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, wiki_metadata=_wiki_metadata(missing={"name", "created_at"}))
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "wiki-metadata-reads-satisfied")
        self.assertIs(c["passed"], False)
        self.assertIn("name", c["actual"])
        self.assertIn("created_at", c["actual"])

    def test_missing_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, wiki_metadata=False)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "wiki-metadata-reads-satisfied")
        self.assertIs(c["passed"], False)
        self.assertIn("不存在", c["actual"])


class AgentsVersionCheckTest(unittest.TestCase):
    def test_stale_version_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, agents_md=_render_agents_md(spec=OLD_VERSION))
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-version-is-current")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["comparison"], "older")
        # 版本落后与正文同步正交（正文仍与新模板一致 → template-sync pass）
        sync = check_by_id(report, "agents-md-template-sync")
        self.assertIs(sync["passed"], True)


class AgentsTemplateSyncTest(unittest.TestCase):
    def test_local_customization_fails(self):
        drifted = _render_agents_md() + "\n## 本地私货段\n\n- 本 wiki 特有纪律\n"
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, agents_md=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-md-template-sync")
        self.assertIs(c["passed"], False)


class TemplateNoOutboundRefsTest(unittest.TestCase):
    """模板零出边引用（0.33.0+ 架构不变量）——检测逻辑喂合成文本 + 端到端干净 pass。"""

    def _scan(self, text):
        """直接调用脚本内的扫描函数（不改真实模板文件）。"""
        sys.path.insert(0, str(SCRIPT_PATH.parent))
        try:
            from check_wiki_fixtures import _scan_template_outbound_refs

            return _scan_template_outbound_refs(text)
        finally:
            sys.path.remove(str(SCRIPT_PATH.parent))

    def test_clean_text_no_hits(self):
        self.assertEqual(self._scan("# 标题\n\n- 自包含措辞（见本文件顶部「关键」段）\n"), [])

    def test_skill_file_refs_detected(self):
        text = "见 `wiki-spec.md` §15 与 `page-templates.md` §一\n且 lint-checklist.md、SKILL.md、references/、yzr-llm-wiki-management、OKF 都算"
        hits = self._scan(text)
        for pat in (
            "wiki-spec.md",
            "page-templates.md",
            "lint-checklist.md",
            "SKILL.md",
            "references/",
            "yzr-llm-wiki-management",
            "OKF",
        ):
            self.assertTrue(any(pat in h for h in hits), f"{pat} 应被检出: {hits}")

    def test_arabic_section_ref_detected(self):
        self.assertTrue(any("§节号" in h for h in self._scan("详见 spec §13.3")))

    def test_chinese_section_ref_ok(self):
        self.assertEqual(self._scan("详见本文件 §二「页面类型」段"), [])

    def test_check_passes_on_clean_wiki(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp)
            code, report = run_check(tmp)
        self.assertEqual(code, 0)
        c = check_by_id(report, "template-no-outbound-refs")
        self.assertIs(c["passed"], True)


class SkeletonCheckTest(unittest.TestCase):
    """代表性骨架 / 结构 check 的反例（覆盖 SKELETON_SPECS 机制 + 结构 check）。"""

    def test_memory_index_frontmatter_fails(self):
        drifted = "---\ntitle: MEMORY\n---\n\n" + _canonical("memory-index.md")
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, memory_index=drifted)
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "memory-index-no-frontmatter")
        self.assertIs(c["passed"], False)

    def test_index_md_missing_categories_warns(self):
        drifted = '---\ntitle: Test\ntype: index\nokf_version: "0.1"\ntags: [index]\ncreated: 2026-06-28\nupdated: 2026-06-28\n---\n\n# Test Wiki\n\n> 说明\n'
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, index_md=drifted)
            code, report = run_check(tmp)
        c = check_by_id(report, "index-md-categories-stable")
        self.assertIs(c["passed"], False)


class ReportSchemaTest(unittest.TestCase):
    def test_json_report_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp)
            _, report = run_check(tmp)
        for key in ("wiki_root", "target_spec", "checks", "summary"):
            self.assertIn(key, report)
        for key in ("error", "warn", "info", "pass", "skip"):
            self.assertIn(key, report["summary"])
        for c in report["checks"]:
            for key in ("id", "file", "passed", "severity", "rule_ref", "desc"):
                self.assertIn(key, c, f"check {c['id']} 缺字段 {key}")


if __name__ == "__main__":
    unittest.main()
