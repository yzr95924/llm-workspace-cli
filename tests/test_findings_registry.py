#!/usr/bin/env python3
"""test_findings_registry — lint finding 注册表双向穷举校验。

背景：severity 映射漏配曾复发（sources-* 三条落默认 info；missing-sources /
invalid-tags 补 severity 时又漏），根因是"发射点"与"映射表"两处手工维护。
现在 ``llmw/content/findings.py`` 是唯一注册表，本测试保证：

1. 源码里发射的每个 finding 名都在注册表（漏配即红）
2. 注册表每条都被源码发射（死条目即红）
3. ``severity_of`` 返回值与注册表一致

新增检查时若只改一边，本测试失败——这就是设计目的。
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 发射形态：f"name: ..." / "name: ..."（含多段拼接的首段）
_EMIT_RE = re.compile(r'[fF]?"([a-z][a-z0-9]*(?:-[a-z0-9]+)+): ')


def _lint_src() -> str:
    return (REPO / "llmw" / "content" / "wiki_lint.py").read_text(encoding="utf-8")


def _emitted_names() -> set:
    return set(_EMIT_RE.findall(_lint_src()))


class FindingsRegistryTest(unittest.TestCase):
    def setUp(self):
        from llmw.content import findings

        self.findings = findings

    def test_every_emitted_name_registered(self):
        """发射点 → 注册表：源码里每个 finding 名必须已注册。"""
        unregistered = _emitted_names() - set(self.findings.FINDINGS)
        unregistered -= set(self.findings.NOTE_PREFIXES)
        self.assertEqual(
            unregistered,
            set(),
            "以下 finding 名在 wiki_lint.py 发射但未注册（findings.py 补条目）："
            + ", ".join(sorted(unregistered)),
        )

    def test_no_dead_registry_entries(self):
        """注册表 → 发射点：注册表每条必须在源码里真实发射（防改名后遗留死条目）。"""
        dead = set(self.findings.FINDINGS) - _emitted_names()
        self.assertEqual(
            dead,
            set(),
            "以下注册表条目在 wiki_lint.py 无发射点（已改名 / 已删除）："
            + ", ".join(sorted(dead)),
        )

    def test_severity_matches_registry(self):
        for name, spec in self.findings.FINDINGS.items():
            self.assertIn(spec.severity, ("error", "warn", "info"), name)
            self.assertEqual(
                self.findings.severity_of(name + ": x"), spec.severity, name
            )

    def test_unknown_name_defaults_info(self):
        self.assertEqual(self.findings.severity_of("unknown-finding: x"), "info")

    def test_explain_all_and_single(self):
        self.assertEqual(self.findings.explain(), 0)
        self.assertEqual(self.findings.explain("all"), 0)
        self.assertEqual(self.findings.explain("raw-modified"), 0)
        self.assertEqual(self.findings.explain("no-such-finding"), 1)


if __name__ == "__main__":
    unittest.main()
