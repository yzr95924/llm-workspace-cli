#!/usr/bin/env python3
"""CI gate：skill ↔ CLI 外部契约一致性（语法面）。

各检查面的清单、扫描域与豁免理由以文内 "# --- N" 节标签与常量注释为 canonical，
此处不重复（顶层重复 = 第二份真相）。

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
SKILL_MDS = sorted([p for p in WIKI_SKILL.rglob("*.md")])

# 面 1（命令 + 风格 + 跨行）扫全仓命令面。有意排除 tests/（可执行测试自带 loud
# failure）。templates 既含 byte-owned
# 模板 md 也含 *.txt 内容 fixtures（都含 llmw 命令）。
CONTRACT_MDS = sorted(
    set(SKILL_MDS)
    | set(TEMPLATES.rglob("*.md"))
    | set(TEMPLATES.rglob("*.txt"))
    | {REPO / "README.md"}
)

FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
INLINE_CMD_RE = re.compile(r"`(llmw[^`\n]*)`")
# 跨行允许的正则——仅用于"发现本该行内命令被换行切开"的检查；非贪婪 + 排除
# 单引号内 backtick，DOTALL 让 . 匹配换行。
WRAPPED_INLINE_RE = re.compile(r"`(llmw[^`]*?)`", re.DOTALL)
# 裸 semver —— bump wiki_format_version 时漏改 prose 会静默腐烂（无 lint 兜底）；
# 豁免：SKILL frontmatter 的 wiki_format_version: 键行（SSOT 本身）+
# upgrade-workflow.md 整文件（按设计它是唯一允许锚定历史版本的文件）。
SEMVER_RE = re.compile(r"\bv?\d+\.\d+\.\d+\b")
SEMVER_KEY_SKIP_RE = re.compile(r"^\s*wiki_format_version\s*:")
SEMVER_FILE_SKIP = {"upgrade-workflow.md"}
# 面 2 severity 镜像模式：`` `finding-name`（error|warn|info`` = 旧 checklist 镜像格式；
# 口径改走 `llmw wiki lint --explain` 注册表（findings.py），出现即红。
SEVERITY_MENTION_RE = re.compile(
    r"`([a-z][a-z0-9]+(?:-[a-z0-9]+)+)`（\*{0,2}(?:error|warn|info)"
)
# 面 2b 裸 token 存在性：prose 反引号内全小写 kebab token（finding 名同形）必须能落到
# 某命名空间——(a) findings 注册表 / (b) CLI 源码既有字面量（fixtures action、upgrade
# action、ingest reason 等值域）/ (c) 下方示例数据白名单。防 rename 后 prose 裸名引用
# 静默陈旧（镜像禁令只覆盖 severity 括注格式，管不到分支触发键 / 指针之外的裸引用）。
KEBAB_TOKEN_RE = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")
# 非 CLI 命名空间白名单（token 不是对 CLI 代码真源的引用，无 rename 对账对象）：
# - 示例数据：slug / 仓名
# - content-owned schema 值：workspace 产物 frontmatter `type` 枚举（无代码对应物）
KEBAB_TOKEN_ALLOW = {
    "attention-is-all-you-need",
    "linux-kernel",
    "workspace-memory",
    "yzr-memory-management",
}
# 面 7a 节号禁令：AGENTS.md 字面量 + ≤6 个非 word 字符（空白 / backtick / 标点）+
# `§<数字|中文数字>`。`AGENTS.md + `[ref/external-repo.md`](...) §三` 形式
# 中「+ [」含 word char 路径段 → regex 不匹配（§三实指 external-repo.md，非 AGENTS.md）。
AGENTS_SECTION_REF_RE = re.compile(r"AGENTS\.md[^\w\n]{0,6}§[0-9一二三四五六七八九十]+")
# 面 7a 扩展：裸 "wiki §N" shorthand（缺 AGENTS.md 字面量但仍指模板节号）。
# 前置 (?:^|[\s<>/`]) 排除 wiki 名后缀（如 `huawei_storage_wiki/wiki/` 中第一个 wiki
# 前接 word char 不匹配）。
TEMPLATE_BARE_SHORTHAND_RE = re.compile(
    r"(?:^|[\s<>/`])wiki\s+§[0-9一二三四五六七八九十]+"
)
# 面 8 rule_ref 格式闸：.py rule_ref 字段 / to_action / finding 消息指向 skill 文档必须
# 带 .md 扩展名——否则面 3 的锚点/旧形态检测都匹配不到，等于死指针。regex 抓裸
# basename 后跟 `§` / 「 / # 三种邻接（token 后无 `.md`）；负向先行 `(?!\.md)` 排除
# 已带 .md 的正确形式。不抓散文 "SKILL 目录" / "SKILL scan"（后不跟这些符号）。
RULE_REF_BARE_RE = re.compile(
    r"\b(SKILL|lint-workflow|page-templates|upgrade-workflow|ingest-workflow"
    r"|query-workflow|external-repo|examples|formats)(?!\.md)(?: §[一二三四五六七八九十0-9]|[^\w\n]{0,3}[「#])"
)

# 面 7a 的 .py 扫描域——只扫 llmw/**/*.py（排除 tests/）。tests/ 有 §N 形式的 test 输入
# （详见 test_content_wiki_fixtures.py 的 template-no-outbound-refs 单测），必误报。
PY_CONTRACT = sorted(p for p in (REPO / "llmw").rglob("*.py") if "tests" not in p.parts)
# 面 7b 模板 landmark（依赖清单）：skill 运行期依赖的模板锚点字符串；模板改了任一
# landmark，gate 红，同 commit 必须同步 skill 引用。
PROSE_EXEMPTIONS = [
    ("ref/lint-workflow.md", "**不**自动修——只报告，修由用户 / agent 决定"),
    ("SKILL.md", "格式 + 滚动窗口截断由 `write` 保证，lint 只兜底带外手改"),
    ("ref/upgrade-workflow.md", "**CLI `llmw wiki upgrade`（骨架修复者）**：修骨架"),
    ("ref/ingest-workflow.md", "含义与退出码\n输出自明"),
]

WIKI_TEMPLATE_LANDMARKS = [
    "当前配置",
    "Wiki Format 版本",
    "@MEMORY/MEMORY.md",
    "@scripts/SCRIPTS.md",
    "Query 纪律",
    "raw/discussions/",
    "### `MEMORY/`",
]
# 面 8 布局 token：skill 里 `wiki/<dir>/` token，dir 必须在 WIKI_SUBDIRS 集合。
# 前置 `[\s<>/]` 排除 wiki 名后缀（如 `huawei_storage_wiki/wiki/...` 中第一个 `wiki`
# 前接 word char，不匹配）；`[a-z][a-z0-9]*` 排除 wiki 名（如 `~/wiki/llm-systems/`
# 含 hyphen，不匹配）——WIKI_SUBDIRS 全小写无分隔符。
LAYOUT_TOKEN_RE = re.compile(r"(?:^|[\s<>/])wiki/([a-z][a-z0-9]*)/")
# 面 9 module 限定符号禁令：抓两种"包内路径 / 符号"形态——
#   (a) `llmw.` 前缀（含多点：llmw.content / llmw.content.external_anchor._REQUIRED_FIELDS）
#   (b) 单点 ident.IDENT（第二段含大写：wiki_lint.VALID_TYPES）
# 「单向约束」：skill 文本不读 CLI 代码，只用命令名 / finding 名 / 裸常量名。
# 只扫 SKILL_MDS；模板 / 仓根文档是 CLI 自身文档，引用自身常量合法（如 fixtures/README.md
# 的 llmw.WIKI_FORMAT_VERSION）。零误报：MEMORY/MEMORY.md（斜杠）/
# page-templates.md（第二段无大写）llmw wiki lint（空格命令形态）均不匹配。
MODULE_SYMBOL_RE = re.compile(
    r"`(llmw\.[^`\n]*|[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*)`"
)

# 面 10 agent 可见指令文本禁内部引用：CLI 输出的执行指令（to_action / agent_rules /
# note / rule_ref）只能引 (a) 命令名 (b) 输出自带字段 (c) 实例内可读路径——
# agent 读不到 CLI 代码（「单向约束」），引包内实现 = 不可执行指令。
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


TERMINAL_TOKENS = {
    "blocked_drift": ("upgrade-workflow.md", "examples.md"),
    "done_with_residue": ("upgrade-workflow.md",),
    "verify_failed": ("upgrade-workflow.md",),
    "needs_upgrade": ("upgrade-workflow.md", "examples.md"),
    "upgrade_plan": ("upgrade-workflow.md",),
    "skipped_conflicts": ("upgrade-workflow.md", "lint-workflow.md"),
    "fixtures_actions": ("upgrade-workflow.md", "lint-workflow.md"),
    "agent_rules": ("upgrade-workflow.md", "lint-workflow.md", "examples.md"),
    # plan 自述的语义字段：本文档只指路，字段词汇归 CLI（agent 按 plan 自带规则落）
    # 注：本表方向是**文档 → CLI**（文档提到才查 CLI 有无该字面量）；CLI 新增枚举值而
    # 文档未跟随时本表查不出（如 upgrade.py 的 `growth-graft-error`），该类漂移靠人工审计
    "to_action": ("lint-workflow.md", "external-repo.md"),
    # 注：子串匹配——`actions` 会被 `fixtures_actions` 掩盖，只能抓字段整体消失，
    # 抓不住孤立重命名；且面 4 只覆盖 ref/*.md（SKILL.md 的提及扫不到）
    "actions": ("upgrade-workflow.md", "lint-workflow.md"),
    # drift 判定的唯一判据（CLI 只对 render / gitignore-block 的 diff 设门禁）
    "gitignore-block": ("upgrade-workflow.md", "examples.md"),
    # finding 名（doc 侧分支依据）：升级触发（版本三态）/ 语义合并判定
    "wiki-format-version-stale": ("upgrade-workflow.md", "lint-workflow.md"),
    "wiki-format-version-unparsed": ("upgrade-workflow.md", "lint-workflow.md"),
    "duplicate-title": ("upgrade-workflow.md",),
    # 唯一数据丢失路径的前置可见字段（dry-run plan / residue）
    "dropped_sections": ("upgrade-workflow.md",),
}


def _read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def _src_text():
    return "\n".join(_read(p) for p in sorted(CONTENT.glob("*.py")))


def _lits(path):
    """源码字符串常量拼接（docstring 除外）——面 2b / 面 4 的值域对账源。

    注释与 docstring 里的死 token 不得参与对账：否则常量改名后，
    旧名靠文内残留续命，prose 死引用扫不出来。
    """
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:
        return ""
    doc_ids = set()
    holders = [tree] + [
        n for n in ast.walk(tree) if isinstance(n, (ast.ClassDef, ast.FunctionDef))
    ]
    for n in holders:
        body = getattr(n, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and _str_const(body[0].value) is not None
        ):
            doc_ids.add(id(body[0].value))
    parts = []
    for n in ast.walk(tree):
        if id(n) in doc_ids:
            continue
        s = _str_const(n)
        if s is not None:
            parts.append(s)
    return "\n".join(parts)


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


# ---------- 3. rule_ref（CLI → skill） ----------


_BASENAMES = (
    "SKILL|upgrade-workflow|page-templates|lint-workflow|ingest-workflow"
    "|query-workflow|external-repo|examples"
)
# 旧「节名」邻接形态（已退役→ 锚点链接）：`basename.md` 后紧跟可选 backtick /
# 链接闭合 / 空白，再接「」，出现即红。
RULE_REF_RE = re.compile(r"(?:" + _BASENAMES + r")\.md`?\s*(?:\]\([^)]*\)\s*)?「")
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


def _resolve_targets(fname):
    """引用目标候选列表。单 skill（wiki）域内 SKILL.md / ref/* 定位。"""
    if fname == "SKILL.md":
        return [WIKI_SKILL / fname]
    return [WIKI_SKILL / "ref" / fname]


# 锚点形态：markdown 链接 ](path#slug)（path 为空 = 同文件）；纯文本 base.md#slug
# （CLI .py 字符串与跨 skill 引用位）。
_MD_ANCHOR_RE = re.compile(r"\]\((?P<path>[^)\s#]*)#(?P<slug>[^)\s]+)\)")
_PLAIN_ANCHOR_RE = re.compile(
    r"(?P<base>" + _BASENAMES + r")\.md#(?P<slug>[^\s)\]，。；、`「」（）<>\"'—]+)"
)


def _gh_slug(value):
    """GitHub 标题 slug——github-slugger@2 语义在本仓字符集上的移植（实测 130 标题一致）。"""
    v = re.sub(r"[^\w \-]", "", value.strip().lower())
    return v.replace(" ", "-")


def _file_slugs(md_text):
    """文件全部标题的 slug 集；重复标题按 GitHub ToC 规则追加 -N。"""
    slugs, in_code, seen = set(), False, {}
    for line in md_text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        base = _gh_slug(m.group("title").replace("`", ""))
        n = seen.get(base, 0)
        seen[base] = n + 1
        slugs.add(base if n == 0 else "{}-{}".format(base, n))
    return slugs


def _check_link_anchor(md_path, path_str, slug, rel, stats, errors):
    stats["anchors"] += 1
    target = md_path if not path_str else (md_path.parent / path_str).resolve()
    if not target.is_file():
        errors.append(
            "[anchor] {} → ({}) 目标文件不存在".format(rel, path_str + "#" + slug)
        )
        return
    slugs = _file_slugs(_read(target))
    if slug not in slugs:
        near = sorted(s for s in slugs if s.startswith(slug[:6]))[:3]
        errors.append(
            "[anchor] {} → #{} 非 {} 的标题锚点（相近候选: {}）".format(
                rel, slug, target.name, " / ".join(near) or "无"
            )
        )


def _check_plain_anchor(base, slug, rel, stats, errors):
    stats["anchors"] += 1
    targets = [t for t in _resolve_targets(base + ".md") if t.is_file()]
    if not targets:
        errors.append("[anchor] {} 指向不存在的 {}.md".format(rel, base))
        return
    if not any(slug in _file_slugs(_read(t)) for t in targets):
        errors.append("[anchor] {} → {}#{} 非标题锚点".format(rel, base, slug))


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
        "finding_mirrors": 0,
        "finding_tokens": 0,
        "anchors": 0,
        "tokens": 0,
        "semver": 0,
        "landmarks": 0,
        "layout_tokens": 0,
        "rule_ref_checks": 0,
        "module_symbols": 0,
        "agent_text_refs": 0,
        "enum_pins": 0,
        "exemptions": 0,
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

    # --- 2. finding 口径（prose 不得镜像清单；入口 = lint --explain 注册表）---
    skill_all = "\n".join(_read(p) for p in SKILL_MDS)
    for md in SKILL_MDS:
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            for name in SEVERITY_MENTION_RE.findall(line):
                stats["finding_mirrors"] += 1
                errors.append(
                    "[finding-mirror] {}:{} :: prose 镜像 finding `{}`（severity 括注形式）——"
                    "口径唯一入口是 `llmw wiki lint --explain`"
                    "（注册表 SSOT = llmw/content/findings.py）".format(
                        _rel(md), lineno, name
                    )
                )
    if "--explain" not in skill_all:
        errors.append(
            "[finding] skill 文本未提及 `--explain`（finding 含义/severity/修法的唯一入口）"
        )

    # --- 2b. finding 名单向存在性（防 rename 后 prose 裸引用静默陈旧）---
    import llmw.content.findings as _findings_mod  # pylint: disable=import-outside-toplevel

    registry_names = set(_findings_mod.FINDINGS)
    cli_src_all = "\n".join(_lits(p) for p in PY_CONTRACT)
    kebab_tokens = set()
    for md in SKILL_MDS:
        rel = _rel(md)
        for lineno, line in enumerate(_read(md).splitlines(), start=1):
            for tok in KEBAB_TOKEN_RE.findall(line):
                kebab_tokens.add(tok)
                if (
                    tok in registry_names
                    or tok in cli_src_all
                    or tok in KEBAB_TOKEN_ALLOW
                ):
                    continue
                errors.append(
                    "[finding-stale] {}:{} :: prose 引用 `{}` 不在 findings 注册表，"
                    "也不存在于 CLI 源码——疑似 rename 残留；改引用或补白名单".format(
                        rel, lineno, tok
                    )
                )
    stats["finding_tokens"] = len(kebab_tokens)

    # --- 3. 锚点链接：](path#slug) / ](#slug) + 纯文本 base.md#slug；旧 .md「节名」= 红 ---

    def _scan_anchors(path_obj, text, is_md):
        rel = _rel(path_obj)
        for m in RULE_REF_RE.finditer(text):
            errors.append(
                "[anchor] {} 用已退役的 .md「节名」邻接形态 → 改 [章节](file.md#slug)：{}".format(
                    rel, m.group(0).replace("\n", " ")[:60]
                )
            )
        spans = []
        if is_md:
            for m in _MD_ANCHOR_RE.finditer(text):
                spans.append(m.span())
                p = m.group("path")
                if p.startswith(("http://", "https://", "mailto:")):
                    continue
                _check_link_anchor(path_obj, p, m.group("slug"), rel, stats, errors)
        for m in _PLAIN_ANCHOR_RE.finditer(text):
            if any(s <= m.start() < e for s, e in spans):
                continue
            _check_plain_anchor(m.group("base"), m.group("slug"), rel, stats, errors)

    for py in sorted(CONTENT.glob("*.py")):
        _scan_anchors(py, _read(py), is_md=False)
    for md in CONTRACT_MDS:
        _scan_anchors(md, _read(md), is_md=True)

    # --- 4. 终态词 / JSON 字段 ---
    upgrade_py = _lits(CONTENT / "upgrade.py")
    lint_py = _lits(CONTENT / "wiki_lint.py")
    for token, files in TERMINAL_TOKENS.items():
        for fname in files:
            p = WIKI_SKILL / "ref" / fname
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
    wiki_tpl_text = _read(WIKI_TEMPLATE) if WIKI_TEMPLATE.is_file() else ""

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
                "[template-shorthand] {}:{} :: 裸 `wiki §N` shorthand"
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
    # 在 .py 中匹配 "SKILL §N" / "lint-workflow「名」" 等形式；负向先行排除带 .md 的。
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
                    "（「单向约束」：CLI 重构不能让 skill 失效）".format(
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
                    "（「单向约束」：agent 读不到包内实现）".format(
                        rel, lineno, key, m.group(0)
                    )
                )

    # --- 11. 枚举 coverage（CLI SSOT → skill 文档） ---
    import llmw.content.ingest_diff as _ingest_diff_mod  # pylint: disable=import-outside-toplevel
    import llmw.content.page_types as _page_types_mod  # pylint: disable=import-outside-toplevel

    _iw = _read(WIKI_SKILL / "ref" / "ingest-workflow.md")
    for _reason in _ingest_diff_mod.REASONS:
        stats["enum_pins"] += 1
        if _reason not in _iw:
            errors.append(
                "[enum-cov] ingest-workflow.md 未提及 reason `{}`（REASONS SSOT 新增 / 改名须同 commit 同步）".format(
                    _reason
                )
            )
    for _doc in (WIKI_SKILL / "SKILL.md", WIKI_SKILL / "ref" / "page-templates.md"):
        stats["enum_pins"] += 1
        if _page_types_mod.TYPES_DISPLAY not in _read(_doc):
            errors.append(
                "[enum-cov] {} 缺类型枚举 `{}`".format(
                    _rel(_doc), _page_types_mod.TYPES_DISPLAY
                )
            )
    _req_rows = re.findall(
        r"^\|\s*(`[^|]+`(?:\s*/\s*`[^`]+`)*)\s*\|\s*必填",
        _read(WIKI_SKILL / "ref" / "page-templates.md"),
        re.MULTILINE,
    )
    _doc_required = set()
    for _cell in _req_rows:
        _doc_required.update(re.findall(r"`([a-z_]+)`", _cell))
    stats["enum_pins"] += 1
    if _doc_required != set(_page_types_mod.REQUIRED_FRONTMATTER_FIELDS):
        errors.append(
            "[enum-cov] page-templates.md 必填表 {} != REQUIRED_FRONTMATTER_FIELDS {}".format(
                sorted(_doc_required),
                sorted(_page_types_mod.REQUIRED_FRONTMATTER_FIELDS),
            )
        )
    # byte-owned 模板侧：「写入纪律」加粗 op 名 ⊆ LOG_OPS
    from llmw.content import log_format as _lf_mod  # pylint: disable=import-outside-toplevel

    _tmpl_ops = set(re.findall(r"\*\*([a-z]+)\*\*＝", wiki_tpl_text))
    for _op in _tmpl_ops:
        stats["enum_pins"] += 1
        if _op not in _lf_mod.LOG_OPS:
            errors.append(
                "[enum-cov] AGENTS.md 模板写入纪律提及 op `{}` 不在 LOG_OPS {}".format(
                    _op, _lf_mod.LOG_OPS
                )
            )

    # env 契约变量名钉住（同族非枚举）：cli 兜底读 / enter 注入 / SKILL.md 输入行三方
    # 引用同一变量名——ref/ 命令示例与裸命令定位全靠它，rename 是接口契约变更，须三方同 commit。
    _env = "LLM_WIKI_ROOT"
    for _label, _p in (
        ("cli 兜底读", REPO / "llmw" / "cli.py"),
        ("enter 注入", REPO / "llmw" / "wiki" / "enter.py"),
        ("SKILL.md 输入行", WIKI_SKILL / "SKILL.md"),
    ):
        stats["enum_pins"] += 1
        if _env not in _read(_p):
            errors.append(
                "[env-cov] {}（{}）缺 `{}`——env 变量名是 CLI ↔ skill 接口契约，"
                "rename 须三方同 commit 同步".format(_label, _rel(_p), _env)
            )

    # --- 12. 语义断言豁免登记（锚点存在性） ---
    for _ex_file, _ex_anchor in PROSE_EXEMPTIONS:
        stats["exemptions"] += 1
        if _ex_anchor not in _read(WIKI_SKILL / _ex_file):
            errors.append(
                "[exemption] {} 豁免锚点失效：`{}`（断言改写 / 删除须同 commit 更新登记）".format(
                    _ex_file, _ex_anchor[:50]
                )
            )

    # --- 报告 ---
    print(
        "contract (skill+templates+repo-docs → CLI): {} cmd, {} finding_mirrors, "
        "{} finding_tokens, {} anchors, {} tokens, {} semver, {} landmarks, "
        "{} layout_tokens, {} rule_ref_fmt_checks, {} module_symbols, "
        "{} agent_text_refs, {} enum_pins, {} exemptions".format(
            stats["cmds"],
            stats["finding_mirrors"],
            stats["finding_tokens"],
            stats["anchors"],
            stats["tokens"],
            stats["semver"],
            stats["landmarks"],
            stats["layout_tokens"],
            stats["rule_ref_checks"],
            stats["module_symbols"],
            stats["agent_text_refs"],
            stats["enum_pins"],
            stats["exemptions"],
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
