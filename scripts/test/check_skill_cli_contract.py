#!/usr/bin/env python3
"""CI gate：skill ↔ CLI 外部契约一致性（语法面）。

兑现 MEMORY「改 CLI 外部契约必同步 skill 引用」的机械兜底：CLI 改子命令 / flag /
finding 名 / JSON 字段 / rule_ref 指针，而 skill 文本未同步 → 本 gate 红。
语义面（行为描述如"只扫不修"）gate 管不到，靠纪律人工保证。

检查面（10 类）：
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
  3. rule_ref（CLI → skill，skill 域）：llmw/content/*.py + CONTRACT_MDS（skill
     文档 / 模板 / 仓根文档）里的 `<file>.md「节名」` 指针 → 对应 skill 文件与
     标题必须都存在。**名称锚点校验**：引用名须唯一命中一个标题（子串匹配，
     剥 backtick / 跳过 fenced code）——命中 0 = 死指针，命中 >1 = 歧义（改引用名
     或标题消歧）。标题编号已退役（节号随插入整体漂移）；引用侧禁回退由 7c 兜底。
     支持形式：链接内（``[`baz.md「名」`](url)``）/ 链接后（``[`baz.md`](url)「名」``）
     / 裸文本（``baz.md「名」``）
  4. 终态词 / JSON 字段（skill → CLI）：upgrade-workflow 提到的终态词与 plan
     字段必须在 upgrade.py / wiki_lint.py 字面量存在
    5. 裸 semver（skill + 模板 + 仓根文档）：prose 内不得出现裸版本号
      ``v?\\d+\\.\\d+\\.\\d+``（bump 版本时漏改 prose 即静默腐烂）；豁免
      ``wiki_format_version:`` 键行（SSOT 本身）与 ``upgrade-workflow.md`` 整
      文件（按设计它是唯一允许锚定历史版本的文件，头部规矩保证新迁移锚点只落此处）
   6. AGENTS.md 模板依赖守卫（skill↔模板解耦）：
      - 7a 节号禁令：CONTRACT_MDS + llmw/**/*.py 中 `AGENTS.md` 字面量后紧跟
        `§<数字|中文数字>` 即红，`(wiki|workspace) 后接 §N` bare shorthand 同样红
        （节号是模板内部编号，重排即断；引用必须用节名 / 字段名 / landmark）。
        零误报：regex 要求 §N 与 "AGENTS.md" 字面量之间最多 6 个非 word 字符，
        排除 `AGENTS.md + [ref.md] §二` 形式（§ 实指 ref.md）；模板自身"本文件 §N"
        自引用用"本文件"字面量不触发——模板作者自 grep
      - 7b landmark 存在性：skill 依赖的 AGENTS.md 模板锚点字符串（节名 / 字段名 /
        @import 链）必须在对应模板中出现；模板改了某 landmark → CI 红，同 commit
        更新 skill 引用 + LANDMARKS 列表
      - 7c skill 域节号禁令（防迁移回潮）：CONTRACT_MDS + llmw/**/*.py 中 skill
        文档字面量（8 个 basename）后 ~60 字符内出现 `§<数字|中文数字>` 即红；
        SKILL_MDS 自身出现裸 `§N` 同样红。外部规范引用豁免（`OKF §N`）。
        引用一律 `<file>.md「节名」`，标题不再编号
      - 7d 裸「」残留节号兜底：SKILL_MDS 内引号内容以旧节号开头（`「5. x」` /
        `「四、x」`）即红——无 basename 前缀，RULE_REF_RE 与 7a/7c 均扫不到
        （2026-09 迁移曾漏网 2 处）。模板域标题仍带编号，不在此扫描
   7. 布局 token（skill↔目录结构解耦）：skill markdown 里所有 `wiki/<dir>/` 形式的
      目录路径 token，`<dir>` 必须在 llmw.content.wiki_lint.WIKI_SUBDIRS
      （CLI SSOT）集合内。改目录名时残留旧路径被当场点名，零人工维护
   8. rule_ref 格式闸：llmw/**/*.py 中 rule_ref 值指向 skill 文档必须带 `.md`
      扩展名（`lint-checklist「名」` 这类缺 .md = gate 3 扫不到的死指针）
   9. module 限定符号禁令（skill↔CLI 解耦）：SKILL_MDS 内 backtick span 命中两形态
      之一即红——(a) `llmw.` 前缀（含多点包内路径，如 `llmw.content` /
      `llmw.content.external_anchor._REQUIRED_FIELDS`）；(b) 单点 `模块.符号`
      （第二段含大写，如 `wiki_lint.VALID_TYPES`）。skill 文本引 CLI 资产只用命令名 /
      finding 名 / 裸常量名（裸常量名合规：指标类按 skill 纪律引名不引字面量），包内
      路径写进 skill = "skill 读 CLI 代码"（boundary-map「单向约束」）。只扫 SKILL_MDS：
      模板 / 仓根文档是 CLI 自身文档，引用自身常量合法。零误报——`MEMORY/MEMORY.md`
      （斜杠）/ `page-templates.md`（第二段无大写且无 llmw. 前缀）/ `llmw wiki lint`
      （空格命令形态）/ `LOG_RETENTION_LIMIT`（无点）均不匹配
  10. agent 可见指令文本禁内部引用（CLI → agent 文本）：llmw/**/*.py 内 ast 键值配对 +
      关键字实参取 `to_action` / `agent_rules` / `note` / `rule_ref` 的值，命中包路径
      （`llmw.` / `llmw/*`）/ `module.SYMBOL`（第二段含大写）/ `包内 <路径>` /
      `fixtures/*.txt` 即红。这 4 个键是 agent 实际执行的指令 / 溯源的指针，只能引
      命令名 / 输出自带字段 / 实例内可读路径——引包内实现 = agent 读不到 = 不可执行
      （面 9 管 skill→CLI 方向，本面管 CLI→agent 文本方向）。desc / argparse help
      是 CLI 自述自身、hint 是用户排障诊断，均不在扫描范围

命令表面 SSOT = llmw.cli.build_parser() 单一 argparse 树（write 子树经
llmw.content.wiki_write.build_subparsers 组合；无模块 standalone 入口）。

standalone，Python 3.7+（与项目最低支持版本对齐），stdlib only。
用法：``python3 scripts/test/check_skill_cli_contract.py``
"""

# pylint: disable=missing-docstring

import argparse
import ast
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
FINDING_IN_SRC_RE = re.compile(r'[fF]"([a-z][a-z0-9]+(?:-[a-z0-9]+)+): ')
SEVERITY_MENTION_RE = re.compile(
    r"`([a-z][a-z0-9]+(?:-[a-z0-9]+)+)`（\*{0,2}(?:error|warn|info)"
)
# 面 7a 节号禁令：AGENTS.md 字面量 + ≤6 个非 word 字符（空白 / backtick / 标点）+
# `§<数字|中文数字>`。`AGENTS.md + `[references/external-repo.md`](...) §三` 形式
# 中「+ [」含 word char 路径段 → regex 不匹配（§三实指 external-repo.md，非 AGENTS.md）。
AGENTS_SECTION_REF_RE = re.compile(r"AGENTS\.md[^\w\n]{0,6}§[0-9一二三四五六七八九十]+")
# 面 7a 扩展：裸 "wiki §N" / "workspace §N" shorthand（缺 AGENTS.md 字面量但仍指模板节号）。
# 前置 (?:^|[\s<>/`]) 排除 wiki 名后缀（如 `huawei_storage_wiki/wiki/` 中第一个 wiki
# 前接 word char 不匹配）。
TEMPLATE_BARE_SHORTHAND_RE = re.compile(
    r"(?:^|[\s<>/`])(?:wiki|workspace)\s+§[0-9一二三四五六七八九十]+"
)
# 面 8 rule_ref 格式闸：.py rule_ref 字段 / to_action / finding 消息指向 skill 文档必须
# 带 .md 扩展名——否则 gate 3 RULE_REF_RE 匹配不到等于死指针。regex 抓裸 basename
# 后跟旧式 `§` 或新式 `「` 两种形态（token 后无 `.md`）；负向先行 `(?!\.md)` 排除
# 已带 .md 的正确形式。不抓散文 "SKILL 目录" / "SKILL scan"（后不跟 § / 「）。
RULE_REF_BARE_RE = re.compile(
    r"\b(SKILL|lint-checklist|page-templates|upgrade-workflow|ingest-workflow"
    r"|query-workflow|external-repo|examples|formats)(?!\.md)(?: §[一二三四五六七八九十0-9]|[^\w\n]{0,3}「)"
)

# 面 7a 的 .py 扫描域——只扫 llmw/**/*.py（排除 tests/）。tests/ 有 §N 形式的 test 输入
# （详见 test_content_wiki_fixtures.py 的 template-no-outbound-refs 单测），必误报。
PY_CONTRACT = sorted(p for p in (REPO / "llmw").rglob("*.py") if "tests" not in p.parts)
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
# 面 9 module 限定符号禁令：抓两种"包内路径 / 符号"形态——
#   (a) `llmw.` 前缀（含多点：llmw.content / llmw.content.external_anchor._REQUIRED_FIELDS）
#   (b) 单点 ident.IDENT（第二段含大写：wiki_lint.VALID_TYPES）
# boundary-map「单向约束」：skill 文本不读 CLI 代码，只用命令名 / finding 名 / 裸常量名。
# 只扫 SKILL_MDS；模板 / 仓根文档是 CLI 自身文档，引用自身常量合法（如 fixtures/README.md
# 的 llmw.WIKI_FORMAT_VERSION）。零误报：MEMORY/MEMORY.md（斜杠）/
# page-templates.md（第二段无大写）llmw wiki lint（空格命令形态）均不匹配。
MODULE_SYMBOL_RE = re.compile(
    r"`(llmw\.[^`\n]*|[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*)`"
)

# 面 10 agent 可见指令文本禁内部引用：CLI 输出的执行指令（to_action / agent_rules /
# note / rule_ref）只能引 (a) 命令名 (b) 输出自带字段 (c) 实例内可读路径——
# agent 读不到 CLI 代码（boundary-map「单向约束」），引包内实现 = 不可执行指令。
# ast 键值配对 + 关键字实参精确取这 4 个键的值（递归 List / f-string），不用行窗口启发式。
# 不扫 desc / argparse help（CLI 自述自身合法）；不扫 hint（错误诊断文本，安装完整性
# 路径对用户排障合法；真执行指令应落 to_action / agent_rules）。
AGENT_TEXT_KEYS = ("to_action", "agent_rules", "note", "rule_ref", "expected", "actual")
AGENT_TEXT_BAN_RE = re.compile(
    r"llmw\.[A-Za-z_][A-Za-z0-9_.]*"  # 包路径（llmw.content / llmw.content.render.x）
    r"|llmw/[A-Za-z0-9_./-]+"  # 包内路径（文件或目录）
    r"|[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*"  # module.SYMBOL（第二段含大写）
    r"|包内\s+[A-Za-z0-9_.{}/-]+"  # "包内 <路径 / 文件名>" 俗称（"包内常量"等中文不匹配）
    r"|fixtures/[A-Za-z0-9_.-]+\.(?:txt|md)"  # fixture 相对路径
)


def _str_const(node):
    """取字符串字面量；3.7（ast.Str）与 3.8+（ast.Constant）双兼容，非字符串返 None。"""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    s = getattr(node, "s", None)  # Python 3.7 的 ast.Str（3.8+ 已并入 Constant）
    return s if isinstance(s, str) else None


def _subscript_key(node):
    """取 `x["key"] = ...` 的字符串键；兼容 py<=3.8 的 ast.Index 包装。"""
    sl = node.slice
    if sl.__class__.__name__ == "Index":  # pragma: no cover - Python <= 3.8
        sl = sl.value
    return _str_const(sl)


def _iter_agent_texts(tree):
    """产出 agent 可见指令文本的 (lineno, key, text)——ast.Dict 里键 ∈ AGENT_TEXT_KEYS 的值。

    递归进 List / Tuple / Set / BinOp（拼接）/ JoinedStr（f-string）/ IfExp；不递归嵌套
    Dict（其自身会被 ast.walk 另行访问，避免同一文本按外层键重复归属）。
    """

    def _walk(node):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for e in node.elts:
                for item in _walk(e):
                    yield item
        elif isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                for item in _walk(side):
                    yield item
        elif isinstance(node, ast.JoinedStr):
            for v in node.values:
                for item in _walk(v):
                    yield item
        elif isinstance(node, ast.FormattedValue):
            for item in _walk(node.value):
                yield item
        elif isinstance(node, ast.IfExp):
            for side in (node.body, node.orelse):
                for item in _walk(side):
                    yield item
        else:
            s = _str_const(node)
            if s is not None:
                yield node.lineno, s

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                key = _str_const(k)
                if key in AGENT_TEXT_KEYS:
                    for lineno, text in _walk(v):
                        yield lineno, key, text
        elif isinstance(node, ast.Call):  # 关键字实参形式（hint="…" / note="…"）
            for kw in node.keywords:
                if kw.arg in AGENT_TEXT_KEYS:
                    for lineno, text in _walk(kw.value):
                        yield lineno, kw.arg, text
        elif isinstance(node, ast.Assign):  # out["to_action"] = … 形式
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    key = _subscript_key(target)
                    if key in AGENT_TEXT_KEYS:
                        for lineno, text in _walk(node.value):
                            yield lineno, key, text


# CLI→skill 反向检查的有意例外（在 skill 侧只按 family 提及 / NOTES 级提示，不逐名文档化）
BACKWARD_ALLOWLIST = set()

TERMINAL_TOKENS = {
    "blocked_drift": ("upgrade-workflow.md", "examples.md"),
    "done_with_residue": ("upgrade-workflow.md",),
    "verify_failed": ("upgrade-workflow.md",),
    "needs_upgrade": ("upgrade-workflow.md", "examples.md"),
    "upgrade_plan": ("upgrade-workflow.md",),
    "skipped_conflicts": ("upgrade-workflow.md", "lint-checklist.md"),
    "fixtures_actions": ("upgrade-workflow.md", "lint-checklist.md"),
    "agent_rules": ("upgrade-workflow.md", "lint-checklist.md", "examples.md"),
    # plan 自述的语义字段：本文档只指路，字段词汇归 CLI（agent 按 plan 自带规则落）
    # 注：本表方向是**文档 → CLI**（文档提到才查 CLI 有无该字面量）；CLI 新增枚举值而
    # 文档未跟随时本表查不出（如 upgrade.py 的 `growth-graft-error`），该类漂移靠人工审计
    "to_action": ("lint-checklist.md", "external-repo.md"),
    # 注：子串匹配——`actions` 会被 `fixtures_actions` 掩盖，只能抓字段整体消失，
    # 抓不住孤立重命名；且面 4 只覆盖 references/*.md（SKILL.md 的提及扫不到）
    "actions": ("upgrade-workflow.md", "lint-checklist.md"),
    # drift 判定的唯一判据（CLI 只对 render / gitignore-block 的 diff 设门禁）
    "gitignore-block": ("upgrade-workflow.md", "examples.md"),
    # finding 名（doc 侧分支依据）：升级触发（版本三态）/ 语义合并判定
    "wiki-format-version-stale": ("upgrade-workflow.md", "lint-checklist.md"),
    "wiki-format-version-unparsed": ("upgrade-workflow.md", "lint-checklist.md"),
    "duplicate-title": ("upgrade-workflow.md",),
    # 唯一数据丢失路径的前置可见字段（dry-run plan / residue）
    "dropped_sections": ("upgrade-workflow.md",),
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


_BASENAMES = (
    "SKILL|upgrade-workflow|page-templates|lint-checklist|ingest-workflow"
    "|query-workflow|external-repo|examples|formats"
)
# 名称锚点引用（规范邻接形式）：`basename.md「节名」` / `` `basename.md`](url)「节名」 ``
# / `` [`basename.md「节名」`](url) ``——basename 与「」之间只允许 backtick / 空白 /
# 链接闭合，不允许夹带散文（否则「」可能属于同行的另一个文件）。
RULE_REF_RE = re.compile(
    r"(?P<base>(?:" + _BASENAMES + r")\.md)`?\s*(?:\]\([^)]*\)\s*)?「(?P<name>[^」]+)」"
)
# 面 7c 节号禁令：skill 文档字面量后 ~60 字符内出现 §N（外部规范引用 OKF 豁免）。
SKILL_REF_SECTION_RE = re.compile(
    r"(?:" + _BASENAMES + r")\.md[^\n]{0,60}(?<!OKF )§[0-9一二三四五六七八九十]+"
)
# 面 7c 裸节号：SKILL_MDS 内出现 §N（同样豁免 OKF）。
BARE_SECTION_RE = re.compile(r"(?<!OKF )§[0-9一二三四五六七八九十]")
# 面 7d 裸「」残留节号兜底：引号内容以旧节号开头（`「5. Upgrade」` / `「四、x」`）。
# 无 basename 前缀 → RULE_REF_RE（需 basename.md）与 7a/7c 均覆盖不到。锚定引号
# 内**开头**，避免误伤散文引号（`「Python 3.11」` 类）。仅扫 SKILL_MDS——模板域
# 标题仍带编号，引用其节名（如 `「一、本 wiki 的边界」`）属合法。
BARE_NUMBERED_QUOTE_RE = re.compile(
    r"「(?:[0-9]+[.、]|[一二三四五六七八九十]+[、.])[^」]*」"
)


_HEADING_RE = re.compile(r"^#{2,6}\s+(?P<title>.+?)\s*$")


def _heading_hits(md_text, name):
    """「名称」在标题里的命中列表（子串匹配；剥 backtick；跳过 fenced code）。"""
    wanted = name.replace("`", "").strip()
    hits = []
    in_code = False
    for lineno, line in enumerate(md_text.splitlines(), 1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RE.match(line)
        if m and wanted in m.group("title").replace("`", ""):
            hits.append((lineno, m.group("title")))
    return hits


def _resolve_targets(fname):
    """引用目标候选列表。SKILL.md / references/* 两 skill 同名——候选都查（任一满足即过）。"""
    if fname == "SKILL.md":
        return [
            d / fname
            for d in (
                REPO / "yzr-llm-wiki-management",
                REPO / "yzr-llm-workspace-management",
            )
        ]
    return [
        d / "references" / fname
        for d in (
            REPO / "yzr-llm-wiki-management",
            REPO / "yzr-llm-workspace-management",
        )
    ]


def _check_rule_ref(fname, name, src_label, stats, errors):
    stats["rule_refs"] += 1
    targets = [t for t in _resolve_targets(fname) if t.is_file()]
    if not targets:
        errors.append("[rule_ref] {} 指向不存在的 {}".format(src_label, fname))
        return
    per_target = [(t, _heading_hits(_read(t), name)) for t in targets]
    if any(len(hits) == 1 for _t, hits in per_target):
        return
    multi = [(t, hits) for t, hits in per_target if len(hits) > 1]
    if multi:
        errors.append(
            "[rule_ref-ambiguous] {} → {}「{}」命中多个标题（{}）——改引用名或标题消歧".format(
                src_label,
                fname,
                name,
                " / ".join(
                    "{}: {}".format(t.name, " ".join("L{}".format(h[0]) for h in hits))
                    for t, hits in multi
                ),
            )
        )
        return
    errors.append(
        "[rule_ref-title] {} → {}「{}」标题不存在".format(src_label, fname, name)
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
        "rule_ref_checks": 0,
        "module_symbols": 0,
        "agent_text_refs": 0,
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

    # --- 3. rule_ref（CLI → skill）+ 「节名」目标标题存在性 ---
    # 3a. llmw/content/*.py：CLI 输出字符串 / docstring / 注释 / rule_ref 字段（纯文本形式）
    for py in sorted(CONTENT.glob("*.py")):
        for fname, name in RULE_REF_RE.findall(_read(py)):
            _check_rule_ref(fname, name, _rel(py), stats, errors)
    # 3b. CONTRACT_MDS（skill 文档 / 模板 / 仓根文档）：
    #     `basename.md「节名」`（链接内 / 链接后 / 裸文本三种形式同一 regex 覆盖）
    for md in CONTRACT_MDS:
        rel = _rel(md)
        text = _read(md)
        seen = set()
        for m in RULE_REF_RE.finditer(text):
            fname = m.group("base")
            name = m.group("name")
            key = (fname, name)
            if key in seen:
                continue
            seen.add(key)
            _check_rule_ref(fname, name, rel, stats, errors)

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

    # 6a 节号禁令：CONTRACT_MDS + llmw/**/*.py 中 AGENTS.md 字面量紧邻 §N /
    # "wiki §N" / "workspace §N" bare shorthand → 红
    def _check_7a(rel, line, lineno):
        if AGENTS_SECTION_REF_RE.search(line):
            errors.append(
                "[agents-section] {}:{} :: 引用 AGENTS.md 禁用节号（模板内重组即断）"
                "→ 改用节名 / 字段名 / landmark 字符串：{}".format(
                    rel, lineno, line.strip()[:80]
                )
            )
        if TEMPLATE_BARE_SHORTHAND_RE.search(line):
            errors.append(
                "[template-shorthand] {}:{} :: 裸 `wiki §N` / `workspace §N` shorthand"
                "（模板内重组即断）→ 改用「节名」形式：{}".format(
                    rel, lineno, line.strip()[:80]
                )
            )

    for md in CONTRACT_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            _check_7a(rel, line, lineno)
    for py in PY_CONTRACT:
        rel = _rel(py)
        for lineno, line in enumerate(_read(py).splitlines(), start=1):
            _check_7a(rel, line, lineno)

    # 7c skill 域节号禁令（防迁移回潮）：标题已不编号 → 引用一律「节名」。
    # basename.md 后 ~60 字符内出现 §N、或 SKILL_MDS 内出现裸 §N → 红（OKF 规范豁免）。
    def _check_7c(rel, line, lineno, bare=False):
        pat = BARE_SECTION_RE if bare else SKILL_REF_SECTION_RE
        if pat.search(line):
            errors.append(
                "[skill-section] {}:{} :: skill 域禁用节号（标题已不编号，插入即整体漂移）"
                "→ 改用 `<file>.md「节名」`：{}".format(rel, lineno, line.strip()[:80])
            )

    for md in CONTRACT_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            _check_7c(rel, line, lineno)
    for py in PY_CONTRACT:
        rel = _rel(py)
        for lineno, line in enumerate(_read(py).splitlines(), start=1):
            _check_7c(rel, line, lineno)
    for md in SKILL_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            _check_7c(rel, line, lineno, bare=True)

    # 7d 兜底：SKILL_MDS 内裸「」引号以旧节号开头 → 红（迁移漏网的 2 处即此形态）
    for md in SKILL_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            if BARE_NUMBERED_QUOTE_RE.search(line):
                errors.append(
                    "[stale-quote-number] {}:{} :: 引号内残留旧节号（标题已去编号，"
                    "该引用已失效）→ 改用节名：{}".format(
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

    # --- 8. rule_ref 格式闸（裸 basename 无 .md → gate 3 扫不到 = 死指针） ---
    # 在 .py 中匹配 "SKILL §N" / "lint-checklist「名」" 等形式；负向先行排除带 .md 的。
    # prose "SKILL 目录" / "SKILL scan" 后不跟 § / 「，自然不匹配。
    for py in PY_CONTRACT:
        rel = _rel(py)
        for lineno, line in enumerate(_read(py).splitlines(), start=1):
            for m in RULE_REF_BARE_RE.finditer(line):
                stats["rule_ref_checks"] += 1
                basename = m.group(1)
                errors.append(
                    "[rule_ref-format] {}:{} :: rule_ref 指向 skill 文档 "
                    "`{}` 但引用缺 .md 扩展名（gate 3 扫不到 = 死指针）".format(
                        rel, lineno, basename
                    )
                )

    # --- 9. module 限定符号禁令（skill 文本不读 CLI 代码） ---
    for md in SKILL_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            for m in MODULE_SYMBOL_RE.finditer(line):
                stats["module_symbols"] += 1
                errors.append(
                    "[module-symbol] {}:{} :: skill prose 引 CLI 包内符号 `{}`——"
                    "skill 文本不读 CLI 代码，只用命令名 / finding 名 / 裸常量名"
                    "（boundary-map「单向约束」：CLI 重构不能让 skill 失效）".format(
                        rel, lineno, m.group(1)
                    )
                )

    # --- 10. agent 可见指令文本禁内部引用（CLI → agent 文本） ---
    for py in PY_CONTRACT:
        rel = _rel(py)
        try:
            tree = ast.parse(_read(py))
        except SyntaxError:
            continue
        for lineno, key, text in _iter_agent_texts(tree):
            for m in AGENT_TEXT_BAN_RE.finditer(text):
                stats["agent_text_refs"] += 1
                errors.append(
                    "[agent-text-ref] {}:{} :: agent 可见指令 `{}` 引 CLI 内部资产 `{}`——"
                    "只能引命令名 / 输出自带字段 / 实例内可读路径"
                    "（boundary-map「单向约束」：agent 读不到包内实现）".format(
                        rel, lineno, key, m.group(0)
                    )
                )

    # --- 报告 ---
    print(
        "contract (skill+templates+repo-docs → CLI): {} cmd, {} fwd findings, "
        "{} bwd findings, {} rule_refs, {} tokens, {} semver, {} landmarks, "
        "{} layout_tokens, {} rule_ref_fmt_checks, {} module_symbols, "
        "{} agent_text_refs".format(
            stats["cmds"],
            stats["fwd_findings"],
            stats["bwd_findings"],
            stats["rule_refs"],
            stats["tokens"],
            stats["semver"],
            stats["landmarks"],
            stats["layout_tokens"],
            stats["rule_ref_checks"],
            stats["module_symbols"],
            stats["agent_text_refs"],
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
