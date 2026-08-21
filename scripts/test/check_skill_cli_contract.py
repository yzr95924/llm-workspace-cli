#!/usr/bin/env python3
"""CI gate：skill ↔ CLI 外部契约一致性（语法面）。

兑现 MEMORY「改 CLI 外部契约必同步 skill 引用」的机械兜底：CLI 改子命令 / flag /
finding 名 / JSON 字段 / rule_ref 指针，而 skill 文本未同步 → 本 gate 红。
语义面（行为描述如"只扫不修"）gate 管不到，靠纪律人工保证。

检查面（7 类）：
  1. 命令调用（skill + 模板 + 仓根文档 → CLI）：skill markdown / byte-owned
     模板（llmw/content/templates 全 md + fixtures *.txt）/ 仓根 AGENTS.md +
     CLAUDE.md + README.md 里的 `llmw ...` 调用，子命令路径 + flag 必须存在于
     SSOT 树；**带值 flag 必须等号形式**（CLI 全局拒绝空格分隔，写空格形式 =
     运行即拒的静默 drift）；**行内命令不得跨换行**（跨行 span checker 提取
     不到）。代码块严格校验；行内 backtick 只校验第二 token 为小写命令形态
     的片段，散文提及跳过。**有意不扫 MEMORY/（含历史命令与反例，必误报）
     与 tests/（可执行测试自带 loud failure）**。
  2. finding 名（双向，skill 域）：lint-checklist 里 `` `name`（severity`` 模式
     → 必须存在于 wiki_lint.py / wiki_fixtures.py 字面量；wiki_lint.py 的
     finding 前缀 → 必须在 skill 文本有文档（allowlist 收编有意不文档化的
     例外）
  3. rule_ref（CLI → skill，skill 域）：llmw/content/*.py 里的 "<file>.md §X"
     指针 → 对应 skill 文件与小节标题必须存在
  4. 终态词 / JSON 字段（skill → CLI）：upgrade-workflow 提到的终态词与 plan
     字段必须在 upgrade.py / wiki_lint.py 字面量存在
    5. 裸 semver（skill + 模板 + 仓根文档）：prose 内不得出现裸版本号
      ``v?\\d+\\.\\d+\\.\\d+``（bump 版本时漏改 prose 即静默腐烂）；豁免
      ``wiki_format_version:`` 键行（SSOT 本身）与 ``upgrade-workflow.md`` 整
      文件（按设计它是唯一允许锚定历史版本的文件，头部规矩保证新迁移锚点只落此处）
   6. AGENTS.md 模板依赖守卫（skill↔模板解耦）：
      - 7a 节号禁令：CONTRACT_MDS 中 `AGENTS.md` 字面量后紧跟 `§<数字|中文数字>` 即红
        （节号是模板内部编号，重排即断；节名是语义锚点，引用只用节名 / 字段名 /
        landmark）。模板自身「本文件 §N」自引用用 "本文件" 不触发，模板作者自 grep
      - 7b landmark 存在性：skill 依赖的 AGENTS.md 模板锚点字符串（节名 / 字段名 /
        @import 链）必须在对应模板中出现；模板改了某 landmark → 改 skill 引用的 commit
        同 commit 更新 LANDMARKS 列表
   7. 布局 token（skill↔目录结构解耦）：skill markdown 里所有 `wiki/<dir>/` 形式的
      目录路径 token，`<dir>` 必须在 llmw.content.wiki_lint.WIKI_SUBDIRS
      （CLI SSOT）集合内。改目录名时所有残留旧路径被当场点名，零人工维护

命令表面 SSOT = llmw.cli.build_parser() 单一 argparse 树（write 子树经
llmw.content.wiki_write.build_subparsers 组合；无模块 standalone 入口）。

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
TEMPLATES = CONTENT / "templates"

# 面 2/3/4（finding / rule_ref / 终态词）只走 skill 域——模板 / 仓根文档不是
# finding 的文档真源，rule_ref 的目标是 skill 文件，升级终态词只定义在 skill 工作流里。
SKILL_MDS = sorted(
    [p for p in WIKI_SKILL.rglob("*.md")]
    + [p for p in (REPO / "yzr-llm-workspace-management").rglob("*.md")]
)

# 面 1（命令 + 风格 + 跨行）扫全仓命令面。有意排除 MEMORY/（历史命令 + 反例
# 必误报）与 tests/（可执行测试自带 loud failure）。templates 既含 byte-owned
# 模板 md 也含 *.txt 内容 fixtures（都含 llmw 命令）。
CONTRACT_MDS = sorted(
    set(SKILL_MDS)
    | set(TEMPLATES.rglob("*.md"))
    | set(TEMPLATES.rglob("*.txt"))
    | {REPO / "AGENTS.md", REPO / "CLAUDE.md", REPO / "README.md"}
)

FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
INLINE_CMD_RE = re.compile(r"`(llmw[^`\n]*)`")
# 跨行允许的正则——仅用于"发现本该行内命令被换行切开"的检查；非贪婪 + 排除
# 单引号内 backtick，DOTALL 让 . 匹配换行。
WRAPPED_INLINE_RE = re.compile(r"`(llmw[^`]*?)`", re.DOTALL)
# 裸 semver —— bump wiki_format_version 时漏改 prose 会静默腐烂（无 lint 兜底）；
# 豁免：SKILL frontmatter 的 wiki_format_version: / workspace_format_version: 键行
# （SSOT 本身）+ upgrade-workflow.md 整文件（按设计它是唯一允许锚定历史版本的文件）。
SEMVER_RE = re.compile(r"\bv?\d+\.\d+\.\d+\b")
SEMVER_KEY_SKIP_RE = re.compile(r"^\s*(?:wiki|workspace)_format_version\s*:")
SEMVER_FILE_SKIP = {"upgrade-workflow.md"}
RULE_REF_RE = re.compile(
    r"(SKILL\.md|(?:upgrade-workflow|page-templates|lint-checklist|ingest-workflow"
    r"|query-workflow|external-repo|examples)\.md)(?:\s*§([一二三四五六七八九十0-9][0-9.]*)?)?"
)
FINDING_IN_SRC_RE = re.compile(r'[fF]"([a-z][a-z0-9]+(?:-[a-z0-9]+)+): ')
SEVERITY_MENTION_RE = re.compile(
    r"`([a-z][a-z0-9]+(?:-[a-z0-9]+)+)`（\*{0,2}(?:error|warn|info)"
)
# 面 7a 节号禁令：AGENTS.md 字面量 + ≤6 个非 word 字符（空白 / backtick / 标点）+
# `§<数字|中文数字>`。`AGENTS.md + [`references/external-repo.md`](...) §二` 形式
# 中「+ [」含 word char 路径段 → regex 不匹配（§二实指 external-repo.md，非 AGENTS.md）。
AGENTS_SECTION_REF_RE = re.compile(r"AGENTS\.md[^\w\n]{0,6}§[0-9一二三四五六七八九十]+")
# 面 7b 模板 landmark（依赖清单）：skill 运行期依赖的模板锚点字符串；模板改了任一
# landmark，gate 红，同 commit 必须同步 skill 引用。
WIKI_TEMPLATE_LANDMARKS = [
    "当前配置",
    "Wiki Format 版本",
    "@MEMORY/MEMORY.md",
    "@scripts/SCRIPTS.md",
    "Query 纪律",
    "raw/discussions/",
    "### `MEMORY/`",
]
WORKSPACE_TEMPLATE_LANDMARKS = [
    "当前配置",
    "Workspace Format 版本",
    "@MEMORY/MEMORY.md",
    "跨 wiki 约定",
    "Memory 纪律",
]
# 面 8 布局 token：skill 里 `wiki/<dir>/` token，dir 必须在 WIKI_SUBDIRS 集合。
# 前置 `[\s<>/]` 排除 wiki 名后缀（如 `huawei_storage_wiki/wiki/...` 中第一个 `wiki`
# 前接 word char，不匹配）；`[a-z][a-z0-9]*` 排除 wiki 名（如 `~/wiki/llm-systems/`
# 含 hyphen，不匹配）——WIKI_SUBDIRS 全小写无分隔符。
LAYOUT_TOKEN_RE = re.compile(r"(?:^|[\s<>/])wiki/([a-z][a-z0-9]*)/")

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


def _collect_value_flags(parser, flags=None):
    """递归收集全树的带值 flag（nargs None/1）——风格检查用。"""
    if flags is None:
        flags = set()
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for sp in action.choices.values():
                _collect_value_flags(sp, flags)
            continue
        for opt in action.option_strings:
            if opt.startswith("--") and action.nargs in (None, 1):
                flags.add(opt)
    return flags


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
        # README 风格的"或"写法：`[--X\|-Y]` / `[A|B]` ——按 `|` 拆开分别校验
        if "|" in t:
            alts = re.split(r"\\?\|", t)
            for alt in alts:
                a = alt.strip().lstrip("[").rstrip("]").strip("`")
                if not a:
                    continue
                if a.startswith("--"):
                    name = a.split("=", 1)[0]
                    if _flag_consumes(chain_flags, name) is None:
                        loc = " / ".join(k for k in _chain_path(tokens, i))
                        return "未知 flag {}（{}）".format(name, loc)
                elif a in subs:
                    cur = subs[a]
                    flags, subs = _walk_parser(cur)
                    chain_flags.update(flags)
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


def _iter_wrapped_inline(md_text):
    """找出被换行切开的行内命令段（本该行内一条命令，跨行会被 INLINE 正则漏提）。

    先剔除围栏代码块（FENCE_RE.sub），避免代码块内的单 backtick 被错误配对；
    再用 DOTALL 正则匹配所有 backtick 段，含换行的即违例。
    """
    stripped = FENCE_RE.sub("", md_text)
    for m in WRAPPED_INLINE_RE.finditer(stripped):
        span = m.group(1)
        if "\n" in span:
            yield span


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

    # 命令表面 SSOT = llmw.cli.build_parser() 单一 argparse 树（write 子树由
    # build_subparsers 组合进树，无第二定义处）
    root = llmw.cli.build_parser()
    value_flags = _collect_value_flags(root)
    errors = []
    stats = {
        "cmds": 0,
        "fwd_findings": 0,
        "bwd_findings": 0,
        "rule_refs": 0,
        "tokens": 0,
        "semver": 0,
        "landmarks": 0,
        "layout_tokens": 0,
    }

    # --- 1. 命令调用（含风格检查：带值 flag 必须等号形式；含跨行断命令检查）---
    def _rel(p):
        return str(p.relative_to(REPO))

    def _check_style(rel_name, tokens):
        for tok in tokens:
            t = tok.strip("`[]")
            if t in value_flags:
                errors.append(
                    "[style] {} :: `{}` 带值 flag 须等号形式（{}=VALUE；CLI 全局拒绝空格分隔）".format(
                        rel_name, t, t
                    )
                )

    for md in CONTRACT_MDS:
        rel = _rel(md)
        text = _read(md)
        for tokens in _iter_code_block_cmds(text):
            stats["cmds"] += 1
            err = validate_cmd(tokens[1:], root)
            if err:
                errors.append("[cmd] {} :: {}".format(rel, err))
            _check_style(rel, tokens[1:])
        for tokens in _iter_inline_cmds(text):
            stats["cmds"] += 1
            err = validate_cmd(tokens[1:], root)
            if err:
                errors.append("[cmd-inline] {} :: `{}`".format(rel, " ".join(tokens)))
            _check_style(rel, tokens[1:])
        for span in _iter_wrapped_inline(text):
            errors.append(
                "[wrap] {} :: 行内命令不得跨换行（checker 提取需单行）：`{}`".format(
                    rel, " ".join(span.split())
                )
            )

    # --- 2.5. 裸 semver（时间性信息不得内联 prose） ---
    for md in CONTRACT_MDS:
        if md.name in SEMVER_FILE_SKIP:
            continue
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            if SEMVER_KEY_SKIP_RE.match(line):
                continue
            if SEMVER_RE.search(line):
                stats["semver"] += 1
                errors.append(
                    "[semver] {}:{} :: 裸版本号不得内联 prose（bump 版本时漏改 = 静默腐烂）：{}".format(
                        rel, lineno, line.strip()[:80]
                    )
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

    # --- 6. AGENTS.md 模板依赖守卫 ---
    WIKI_TEMPLATE = TEMPLATES / "wiki" / "agents-md-template.md"
    WORKSPACE_TEMPLATE = TEMPLATES / "workspace" / "workspace-agents-md-template.md"
    wiki_tpl_text = _read(WIKI_TEMPLATE) if WIKI_TEMPLATE.is_file() else ""
    ws_tpl_text = _read(WORKSPACE_TEMPLATE) if WORKSPACE_TEMPLATE.is_file() else ""

    # 6a 节号禁令：CONTRACT_MDS 中 AGENTS.md 字面量紧邻 §N → 红
    for md in CONTRACT_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            if AGENTS_SECTION_REF_RE.search(line):
                errors.append(
                    "[agents-section] {}:{} :: skill 引用 AGENTS.md 禁用节号（模板"
                    "内重组即断）→ 改用节名 / 字段名 / landmark 字符串：{}".format(
                        rel, lineno, line.strip()[:80]
                    )
                )

    # 6b 模板 landmark 存在性（按 skill 实际引用的 AGENTS.md 分桶）
    for landmark in WIKI_TEMPLATE_LANDMARKS:
        stats["landmarks"] += 1
        if landmark not in wiki_tpl_text:
            errors.append(
                "[landmark] wiki AGENTS.md 模板缺 landmark `{}`（skill 依赖它，"
                "模板改了须同 commit 同步 skill 引用）".format(landmark)
            )
    for landmark in WORKSPACE_TEMPLATE_LANDMARKS:
        stats["landmarks"] += 1
        if landmark not in ws_tpl_text:
            errors.append(
                "[landmark] workspace AGENTS.md 模板缺 landmark `{}`（skill 依赖它，"
                "模板改了须同 commit 同步 skill 引用）".format(landmark)
            )

    # --- 7. 布局 token（skill ↔ 目录结构） ---
    import llmw.content.wiki_lint as _wiki_lint_mod  # pylint: disable=import-outside-toplevel

    valid_dirs = set(_wiki_lint_mod.WIKI_SUBDIRS)
    for md in SKILL_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            for m in LAYOUT_TOKEN_RE.finditer(line):
                stats["layout_tokens"] += 1
                dir_name = m.group(1)
                if dir_name not in valid_dirs:
                    errors.append(
                        "[layout] {}:{} :: skill 使用 wiki/{}/{}/ 但 WIKI_SUBDIRS 无此目录"
                        "（CLI SSOT 改了目录名须同 commit 同步 skill 引用）".format(
                            rel, lineno, dir_name, dir_name
                        )
                    )

    # --- 报告 ---
    print(
        "contract (skill+templates+repo-docs → CLI): {} cmd, {} fwd findings, "
        "{} bwd findings, {} rule_refs, {} tokens, {} semver, {} landmarks, {} layout_tokens".format(
            stats["cmds"],
            stats["fwd_findings"],
            stats["bwd_findings"],
            stats["rule_refs"],
            stats["tokens"],
            stats["semver"],
            stats["landmarks"],
            stats["layout_tokens"],
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
