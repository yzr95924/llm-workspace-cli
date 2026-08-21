#!/usr/bin/env python3
"""test_content_wiki_fixtures — llmw.content.wiki_fixtures 端到端测试

stdlib unittest + subprocess 调真实模块（无 mock）：在 tmp 目录搭 scratch wiki
（clean / 各类 drift），断言 --json 报告结构与 finding 内容。standalone——不依赖
CLI，只读 skill 侧模板 + fixtures。

运行:
  pytest tests/test_content_wiki_fixtures.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from llmw.content.render import render_wiki_agents_md

REPO = Path(__file__).resolve().parents[1]
TEMPLATES_WIKI = REPO / "llmw" / "content" / "templates" / "wiki"
AGENTS_TEMPLATE = (TEMPLATES_WIKI / "agents-md-template.md").read_text(encoding="utf-8")
FIXTURES_DIR = TEMPLATES_WIKI / "fixtures"
WIKI_GITIGNORE = (FIXTURES_DIR / "gitignore.txt").read_text(encoding="utf-8")

OLD_VERSION = "0.25.0"  # 真实历史版本——永远小于当前 target_format


def _target_format():
    """包内常量 llmw.WIKI_FORMAT_VERSION（与 SKILL.md frontmatter 同 commit 对齐，CI gate 守护）。"""
    sys.path.insert(0, str(REPO))
    import llmw

    return llmw.WIKI_FORMAT_VERSION


TARGET_FORMAT = _target_format()


def _render_agents_md(
    topic="Test", setup_date="2026-06-28 00:00", cli="0.1.0", format_version=None
):
    """生产 render 的薄封装；默认参数与 _wiki_metadata.created_at="2026-06-28T00:00:00Z"（[:16] 派生为
    `"2026-06-28 00:00"`）对齐，保证 scratch wiki 的 AGENTS.md 与 metadata + 渲染契约字节一致。"""
    return render_wiki_agents_md(
        topic=topic,
        setup_date=setup_date,
        cli_version=cli,
        format_version=format_version or TARGET_FORMAT,
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


# 锚点 mapping 渲染 fixtures = 原 canonical/ 字面量（canonical/ 已删，fixtures 是唯一字节金标准）。
# SETUP_DATE 与 _wiki_metadata.created_at="2026-06-28T00:00:00Z" 派生后的 checker 渲染值一致
# （"2026-06-28 00:00"），保证 scratch wiki 三处渲染结果字节对齐。
FIXTURE_ANCHORS = {"TOPIC_NAME": "Test", "SETUP_DATE": "2026-06-28 00:00"}


def _fixture(name):
    text = (FIXTURES_DIR / f"{name}.txt").read_text(encoding="utf-8")
    for key, value in FIXTURE_ANCHORS.items():
        text = text.replace("{{" + key + "}}", value)
    return text


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
        (root / "AGENTS.md").write_text(
            agents_md if agents_md is not None else _render_agents_md(),
            encoding="utf-8",
        )
    if gitignore is not False:
        (root / ".gitignore").write_text(
            gitignore if gitignore is not None else WIKI_GITIGNORE, encoding="utf-8"
        )
    if wiki_metadata is not False:
        (root / "wiki_metadata.toml").write_text(
            wiki_metadata if wiki_metadata is not None else _wiki_metadata(),
            encoding="utf-8",
        )
    if index_md is not False:
        (root / "wiki" / "index.md").write_text(
            index_md if index_md is not None else _fixture("index.md"), encoding="utf-8"
        )
    if log_md is not False:
        (root / "wiki" / "log.md").write_text(
            log_md if log_md is not None else _fixture("log.md"), encoding="utf-8"
        )
    if tags_md is not False:
        (root / "wiki" / "tags.md").write_text(
            tags_md if tags_md is not None else _fixture("tags.md"), encoding="utf-8"
        )
    if memory_index is not False:
        (root / "MEMORY" / "MEMORY.md").write_text(
            memory_index if memory_index is not None else _fixture("memory-index"),
            encoding="utf-8",
        )
    if scripts_md is not False:
        (root / "scripts" / "SCRIPTS.md").write_text(
            scripts_md if scripts_md is not None else _fixture("scripts.md"),
            encoding="utf-8",
        )
    return root


def run_check(root, extra_args=None, env=None):
    """跑 `llmw wiki --path=<root> check-fixtures --json`，返回 (exit_code, report_dict)。"""
    cmd = [sys.executable, "-m", "llmw"]
    if root is not None:
        cmd.append("wiki")
        cmd.append("--path=" + str(root))
        cmd.append("check-fixtures")
    else:
        # 无显式 root：走 env fallback 路径（LLMW_WIKI_ROOT）
        cmd.extend(["wiki", "check-fixtures"])
    cmd.append("--json")
    cmd.extend(extra_args or [])
    run_env = dict(os.environ, PYTHONPATH=str(REPO))
    run_env.pop("LLM_WIKI_ROOT", None)
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


class CleanWikiTest(unittest.TestCase):
    def test_clean_wiki_no_error(self):
        """clean wiki：所有 check pass 或 skip（symlink ×3 + memory-entries 无条目 skip），无 error。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp)
            code, report = run_check(tmp)
        self.assertEqual(report["target_format"], TARGET_FORMAT)
        self.assertEqual(
            report["summary"]["error"],
            0,
            f"clean wiki 不应有 error：{report['summary']}",
        )
        for c in report["checks"]:
            self.assertIsNot(c["passed"], False, f"clean 下 {c['id']} 不应 fail：{c}")

    def test_check_registry_self_consistent(self):
        """CHECK_REGISTRY 与 CHECK_FUNCTIONS 两侧自洽（每注册 check 有实现函数）。

        checks 已全搬进 CLI，代码侧是唯一真源——SKILL.md 的 fixtures_check_count 钉
        （跨侧计数同步点）已删除；本测试守住注册表内部一致性 + 每条 check 有修复依据。
        """
        from llmw.content.wiki_fixtures import CHECK_FUNCTIONS, CHECK_REGISTRY

        self.assertEqual(len(CHECK_REGISTRY), len(CHECK_FUNCTIONS))
        registered_ids = {c["id"] for c in CHECK_REGISTRY}
        func_ids = {cid for cid, _ in CHECK_FUNCTIONS}
        self.assertEqual(registered_ids, func_ids)
        for c in CHECK_REGISTRY:
            self.assertTrue(c.get("rule_ref"), f"{c['id']} 缺 rule_ref")
            self.assertTrue(c.get("desc"), f"{c['id']} 缺 desc")


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
            build_wiki(
                tmp, wiki_metadata=_wiki_metadata(missing={"name", "created_at"})
            )
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
        """版本落后时两个 check 协同：version-is-current 报 currency，template-sync
        因渲染用 CURRENT format 必然字节差 → 也 fail。**冗余 benign**——两者都推荐 upgrade。
        旧版 orthogonality 设计已在 render-from-metadata 改造中废弃。"""
        with tempfile.TemporaryDirectory() as tmp:
            build_wiki(tmp, agents_md=_render_agents_md(format_version=OLD_VERSION))
            code, report = run_check(tmp)
        self.assertEqual(code, 1)
        c = check_by_id(report, "agents-version-is-current")
        self.assertIs(c["passed"], False)
        self.assertEqual(c["comparison"], "older")
        # 与 template-sync 同时 fail：两者都指向 upgrade（render-from-metadata 改造后 orthogonality 已取消）
        sync = check_by_id(report, "agents-md-template-sync")
        self.assertIs(sync["passed"], False)
        self.assertIn("渲染稿", str(sync.get("expected", "")))


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
    """模板零出边引用（架构不变量）——检测逻辑喂合成文本 + 端到端干净 pass。"""

    def _scan(self, text):
        """直接调用模块内的扫描函数（不改真实模板文件）。"""
        from llmw.content.wiki_fixtures import _scan_template_outbound_refs

        return _scan_template_outbound_refs(text)

    def test_clean_text_no_hits(self):
        self.assertEqual(
            self._scan("# 标题\n\n- 自包含措辞（见本文件顶部「关键」段）\n"), []
        )

    def test_skill_file_refs_detected(self):
        text = "见 page-templates.md §一 与 lint-checklist.md §二\n且 SKILL.md、references/、yzr-llm-wiki-management、OKF 都算"
        hits = self._scan(text)
        for pat in (
            "page-templates.md",
            "lint-checklist.md",
            "SKILL.md",
            "references/",
            "yzr-llm-wiki-management",
            "OKF",
        ):
            self.assertTrue(any(pat in h for h in hits), f"{pat} 应被检出: {hits}")

    def test_arabic_section_ref_detected(self):
        self.assertTrue(
            any("§节号" in h for h in self._scan("详见 external-repo.md §1"))
        )

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
    """代表性骨架 / 结构 check 的反例（覆盖 SKELETON_REGISTRY 机制 + 结构 check）。"""

    def test_memory_index_frontmatter_fails(self):
        drifted = "---\ntitle: MEMORY\n---\n\n" + _fixture("memory-index")
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
        for key in ("wiki_root", "target_format", "checks", "summary"):
            self.assertIn(key, report)
        for key in ("error", "warn", "info", "pass", "skip"):
            self.assertIn(key, report["summary"])
        for c in report["checks"]:
            for key in ("id", "file", "passed", "severity", "rule_ref", "desc"):
                self.assertIn(key, c, f"check {c['id']} 缺字段 {key}")


if __name__ == "__main__":
    unittest.main()
