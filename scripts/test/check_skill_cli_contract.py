#!/usr/bin/env python3
"""CI gate：skill ↔ CLI 外部契约一致性（语法面）。

兑现 MEMORY「改 CLI 外部契约必同步 skill 引用」的机械兜底：CLI 改子命令 / flag /
finding 名 / JSON 字段 / rule_ref 指针，而 skill 文本未同步 → 本 gate 红。
语义面（行为描述如"只扫不修"）gate 管不到，靠纪律人工保证。

检查面（4 类）：
  1. 命令调用（skill → CLI）：skill markdown 里的 `llmw ...` 调用，子命令路径 +
     flag 必须存在于 llmw.cli argparse 树（代码块严格校验；行内 backtick 只校验
     第二 token 为小写命令形态的片段，散文提及跳过）
  2. finding 名（双向）：lint-checklist 里 `` `name`（severity`` 模式 → 必须存在于
     wiki_lint.py / wiki_fixtures.py 字面量；wiki_lint.py 的 finding 前缀 → 必须
     在 skill 文本有文档（allowlist 收编有意不文档化的例外）
  3. rule_ref（CLI → skill）：llmw/content/*.py 里的 "<file>.md §X" 指针 →
     对应 skill 文件与小节标题必须存在
  4. 终态词 / JSON 字段（skill → CLI）：upgrade-workflow 提到的终态词与 plan 字段
     必须在 upgrade.py / wiki_lint.py 字面量存在

standalone，Python 3.7+（与项目最低支持版本对齐），stdlib only。
用法：``python3 scripts/test/check_skill_cli_contract.py``
"""

# pylint: disable=missing-docstring

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

WIKI_SKILL = REPO / "yzr-llm-wiki-management"
CONTENT = REPO / "llmw" / "content"

SKILL_MDS = sorted(
    [p for p in WIKI_SKILL.rglob("*.md")]
    + [p for p in (REPO / "yzr-llm-workspace-management").rglob("*.md")]
)

FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
INLINE_CMD_RE = re.compile(r"`(llmw[^`\n]*)`")
RULE_REF_RE = re.compile(
    r"(SKILL\.md|(?:upgrade-workflow|page-templates|lint-checklist|ingest-workflow"
    r"|query-workflow|external-repo|examples)\.md)(?:\s*§([一二三四五六七八九十0-9][0-9.]*)?)?"
)
FINDING_IN_SRC_RE = re.compile(r'[fF]"([a-z][a-z0-9]+(?:-[a-z0-9]+)+): ')
SEVERITY_MENTION_RE = re.compile(
    r"`([a-z][a-z0-9]+(?:-[a-z0-9]+)+)`（\*{0,2}(?:error|warn|info)"
)

# CLI→skill 反向检查的有意例外（在 skill 侧只按 family 提及 / NOTES 级提示，不逐名文档化）
BACKWARD_ALLOWLIST = set()

TERMINAL_TOKENS = {
    "dry_run": ("upgrade-workflow.md",),
    "blocked_drift": ("upgrade-workflow.md",),
    "done_with_residue": ("upgrade-workflow.md",),
    "verify_failed": ("upgrade-workflow.md",),
    "needs_upgrade": ("upgrade-workflow.md", "lint-checklist.md", "examples.md"),
    "upgrade_plan": ("upgrade-workflow.md", "lint-checklist.md", "examples.md"),
    "skipped_conflicts": ("upgrade-workflow.md",),
    "fixtures_actions": ("upgrade-workflow.md",),
    "agent_rules": ("upgrade-workflow.md",),
}


def _read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def _src_text():
    return "\n".join(_read(p) for p in sorted(CONTENT.glob("*.py")))


def _py_src(name):
    return _read(CONTENT / name)


# ---------- 1. 命令调用（skill → CLI） ----------


def _walk_parser(parser):
    """返回 (该层 flag → nargs 判定, 子命令 → parser)。"""
    flags = {}
    subs = {}
    for action in parser._actions:  # noqa: SLF001
        for opt in action.option_strings:
            if action.nargs == 0:
                flags[opt] = 0
            elif action.nargs in (None, 1):
                flags[opt] = 1
            else:
                flags[opt] = "*"
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for name, sp in action.choices.items():
                subs[name] = sp
    return flags, subs


def _flag_consumes(flags, name):
    if name in flags:
        return flags[name]
    # --foo=bar 形式已在外层拆掉 '='；前缀匹配（prefix matching argparse 默认开）
    cands = [v for k, v in flags.items() if k.startswith(name)]
    return cands[0] if len(cands) == 1 else None


def _graft(parser, sub_name, new_parser):
    """把委托式子命令的模块 parser 嫁接进树（改 action.choices 原对象）。"""
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            if sub_name in action.choices:
                action.choices[sub_name] = new_parser
                return True
            for sp in action.choices.values():
                if _graft(sp, sub_name, new_parser):
                    return True
    return False


def validate_cmd(tokens, root):
    """tokens 为 'llmw' 之后的片段；返回 None（合法）或错误描述。"""
    cur = root
    chain_flags = {}
    flags, subs = _walk_parser(cur)
    chain_flags.update(flags)
    i = 0
    while i < len(tokens):
        t = tokens[i]
        t = t.strip("`").lstrip("[").rstrip("]")
        if not t:
            i += 1
            continue
        if t.startswith("--"):
            name = t.split("=", 1)[0]
            consumes = _flag_consumes(chain_flags, name)
            if consumes is None:
                loc = " / ".join(k for k in _chain_path(tokens, i))
                return "未知 flag {}（{}）".format(name, loc)
            if "=" not in t and consumes == 1:
                i += 2
                continue
        elif t in subs:
            cur = subs[t]
            flags, subs = _walk_parser(cur)
            chain_flags.update(flags)
        # 位置参数 / flag 值 / 占位符：不校验
        i += 1
    return None


def _chain_path(tokens, idx):
    return [t for t in tokens[:idx] if not t.startswith("-")]


def _iter_code_block_cmds(md_text):
    for block in FENCE_RE.findall(md_text):
        for line in block.splitlines():
            s = line.strip()
            if s.startswith("#") or s.startswith("$ "):
                continue
            # 续行合并
            while s.endswith("\\") and line is not None:
                s = s[:-1]
                break
            if s.startswith("llmw ") or s == "llmw":
                yield s.split()


def _iter_inline_cmds(md_text):
    for span in INLINE_CMD_RE.findall(md_text):
        tokens = span.split()
        # 只校验命令形态片段：第二 token 是小写命令/flag；散文（llmw CLI / llmw 命令）跳过
        if len(tokens) < 2:
            continue
        second = tokens[1].strip("`[]")
        if not re.match(r"^[a-z][a-z0-9_-]*$|--", second):
            continue
        yield tokens


# ---------- 2. finding 名（双向） ----------


def _findings_in_src():
    names = set()
    for py in (CONTENT / "wiki_lint.py", CONTENT / "wiki_fixtures.py"):
        names.update(FINDING_IN_SRC_RE.findall(_read(py)))
    return names


def _lint_finding_prefixes():
    return set(FINDING_IN_SRC_RE.findall(_py_src("wiki_lint.py")))


# ---------- 3. rule_ref（CLI → skill） ----------


CN_NUM = {"10": "十"}


def _section_exists(md_text, section):
    """section 形如 '六' / '6.1' / '二.3' / '一' / '10'。"""
    if section is None:
        return True
    if section in CN_NUM:
        section = CN_NUM[section]
    if "." in section:
        first, second = section.split(".", 1)
        # upgrade-workflow 风格：### 6.1（标题可能带 § 前缀）
        pat = r"^### §?{}\b".format(re.escape(section))
        if re.search(pat, md_text, re.MULTILINE):
            return True
        # page-templates 风格：§二.3 → ### 3.
        return bool(
            re.search(r"^### §?{}\.".format(re.escape(second)), md_text, re.MULTILINE)
        )
    return bool(
        re.search(r"^##+ §?{}".format(re.escape(section)), md_text, re.MULTILINE)
    )


# ---------- 主流程 ----------


def main():  # pylint: disable=too-many-branches
    import llmw.cli  # pylint: disable=import-outside-toplevel
    from llmw.content import wiki_write  # pylint: disable=import-outside-toplevel

    root = llmw.cli.build_parser()
    # 嫁接委托式子命令：cli.py 把 `wiki write` 的剩余参数 REMAINDER 透传给
    # wiki_write 自己的 parser——flag 真源在模块侧，不在 cli.py 树上

    if not _graft(root, "write", wiki_write.build_parser()):
        raise RuntimeError("graft wiki write 失败")
    errors = []
    stats = {
        "cmds": 0,
        "fwd_findings": 0,
        "bwd_findings": 0,
        "rule_refs": 0,
        "tokens": 0,
    }

    # --- 1. 命令调用 ---
    for md in SKILL_MDS:
        text = _read(md)
        for tokens in _iter_code_block_cmds(text):
            stats["cmds"] += 1
            err = validate_cmd(tokens[1:], root)
            if err:
                errors.append("[cmd] {} :: {}".format(md.name, err))
        for tokens in _iter_inline_cmds(text):
            stats["cmds"] += 1
            err = validate_cmd(tokens[1:], root)
            if err:
                errors.append(
                    "[cmd-inline] {} :: `{}`".format(md.name, " ".join(tokens))
                )

    # --- 2. finding 名 ---
    src_findings = _findings_in_src()
    lint_text = _read(WIKI_SKILL / "references" / "lint-checklist.md")
    skill_all = "\n".join(_read(p) for p in SKILL_MDS)
    for name in SEVERITY_MENTION_RE.findall(lint_text):
        stats["fwd_findings"] += 1
        if name not in src_findings and name not in _py_src("wiki_lint.py"):
            errors.append(
                "[finding fwd] lint-checklist 提及 `{}` 但 CLI 源无此名".format(name)
            )
    for name in sorted(_lint_finding_prefixes()):
        stats["bwd_findings"] += 1
        if name in BACKWARD_ALLOWLIST:
            continue
        if name not in skill_all:
            errors.append(
                "[finding bwd] CLI finding `{}` 未在 skill 文本文档化".format(name)
            )

    # --- 3. rule_ref（SKILL.md 在两个 skill 目录都可能被指） ---
    for py in sorted(CONTENT.glob("*.py")):
        for fname, section in RULE_REF_RE.findall(_read(py)):
            stats["rule_refs"] += 1
            if fname == "SKILL.md":
                cands = [
                    d / fname
                    for d in (
                        REPO / "yzr-llm-wiki-management",
                        REPO / "yzr-llm-workspace-management",
                    )
                ]
                target = next((c for c in cands if c.is_file()), None)
            else:
                target = WIKI_SKILL / "references" / fname
            if target is None or not target.is_file():
                errors.append("[rule_ref] {} 指向不存在的 {}".format(py.name, fname))
                continue
            if not _section_exists(_read(target), section):
                errors.append(
                    "[rule_ref] {} → {} §{} 小节不存在".format(py.name, fname, section)
                )

    # --- 4. 终态词 / JSON 字段 ---
    upgrade_py = _py_src("upgrade.py")
    lint_py = _py_src("wiki_lint.py")
    for token, files in TERMINAL_TOKENS.items():
        for fname in files:
            p = WIKI_SKILL / "references" / fname
            if not p.is_file():
                continue
            if token in _read(p):
                stats["tokens"] += 1
                if token not in upgrade_py and token not in lint_py:
                    errors.append(
                        "[token] {} 提及 `{}` 但 CLI 源无此字面量".format(fname, token)
                    )

    # --- 报告 ---
    print(
        "skill→CLI contract: {} cmd, {} fwd findings, {} bwd findings, "
        "{} rule_refs, {} tokens".format(
            stats["cmds"],
            stats["fwd_findings"],
            stats["bwd_findings"],
            stats["rule_refs"],
            stats["tokens"],
        )
    )
    if errors:
        print("\nFAIL ({}):".format(len(errors)))
        for e in errors:
            print("  - " + e)
        return 1
    print("OK: skill ↔ CLI 外部契约一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
