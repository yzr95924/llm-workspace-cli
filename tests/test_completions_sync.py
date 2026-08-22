"""completions 三件套与 argparse 命令树的同步性校验。

病根：completions 是手写静态脚本（bash/fish/zsh），无 gate 守护；每次 CLI 加新子命令
都必须手动同步三处。本次漂移实例：external / lint / check-fixtures / upgrade /
ingest-diff / write / 多个二级子命令全部缺失，漂移数月零痛感。

校验方法：递归 argparse 树收集所有 subparser 命令词（leaf 名去重），对每个补全脚本断言
该词以"单词"形式出现（前后非 [a-zA-Z0-9-_]）。单词边界级，不区分上下文位置——
仅捕捉"整个命令词缺失"的漂移（这是最常见也最危险的形态；flag 级漂移不在守护范围）。

副作用：已知低风险假绿风险——命令词若同时作为注释字符串出现在补全文件中会绕过检测。
实践中极少发生（subparser 命令词是业务术语，注释里罕有同名）。
"""

import argparse
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
COMP_FILES = [
    REPO / "completions" / "llmw.bash",
    REPO / "completions" / "llmw.fish",
    REPO / "completions" / "_llmw",
]


def _command_words():
    """递归 argparse 树，收集所有 subparser 选择的 leaf 名（去重）。"""
    from llmw.cli import build_parser

    words = set()

    def walk(parser):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    words.add(name)
                    walk(sub)

    walk(build_parser())
    return words


_WORD_RE_CACHE = {}


def _word_re(word):
    if word not in _WORD_RE_CACHE:
        _WORD_RE_CACHE[word] = re.compile(
            r"(?<![a-zA-Z0-9_-])" + re.escape(word) + r"(?![a-zA-Z0-9_-])"
        )
    return _WORD_RE_CACHE[word]


@pytest.mark.parametrize("comp_file", COMP_FILES, ids=lambda p: p.name)
def test_completions_cover_argparse_commands(comp_file):
    assert comp_file.exists(), f"missing completions file: {comp_file}"
    text = comp_file.read_text(encoding="utf-8")
    words = _command_words()
    # 命令词集非空（防御性断言；若 build_parser 结构剧变，测试该立即红）
    assert words, "argparse 树未产出任何 subparser 命令词"
    missing = sorted(w for w in words if not _word_re(w).search(text))
    assert missing == [], (
        f"{comp_file.name} 漏命令词（argparse 树中存在但补全文件未以单词形式出现）: "
        f"{missing}"
    )
