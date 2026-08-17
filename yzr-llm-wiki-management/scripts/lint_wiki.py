#!/usr/bin/env python3
"""
lint_wiki.py — deterministic 健康检查

跑 references/lint-checklist.md 的 §二（deterministic 全部项）+ external symlink 检查。
半定性检查（§三，矛盾主张 / 缺失交叉引用等需理解语义的）由 agent 现场做。

用法：
  python3 lint_wiki.py [<WIKI_ROOT>] [--severity <LEVEL>] [--no-git] [--migrate-confidence]
  python3 lint_wiki.py [<WIKI_ROOT>] --check-version [--json] [--apply]

--severity 过滤：error | warn | info | all（默认 all）
--no-git 跳过 raw/ 的 git status 检查（CI 或裸仓场景）。默认**自动检测**：
  仅当 wiki 根目录在 git 仓内且 raw/ 被 git 跟踪时才跑 raw 不可变性检查；
  裸目录树 / 无 git / raw 未纳入 git → 自动跳过并打印提示（不报错，不阻断）。
--migrate-confidence 一次性迁移老 `confidence:` 字段（0.5.0 引入）到新
  `reviewed` + `reviewed_at`（0.7.0+）。互斥模式，不做常规 lint。
  已被 `--check-version --apply` 覆盖；保留仅供旧用法兼容。
--check-version 扫描当前 wiki 的 spec 版本（解析 CLAUDE.md §八 "Wiki Spec 版本"），
  与 SKILL 仓 metadata.wiki_spec_version 比对，列出老格式 legacy 现场。默认仅打印报告
   （不动任何文件）；加 `--apply` 把 migration plan 以 JSON 输出到 **stdout**（agent 直接
   消费，**不落盘**——升级全程 wiki 根无任何中间文件残留）供按 references/migrate-workflow.md
   用 Edit/Write 修复；加 `--json` 输出机器可读 JSON。互斥模式。

退出码：
- 0 = 全部指定严重性级别内无 finding / --check-version 报告完成（无论是否需迁移）
- 1 = 有 finding（仅常规 lint 模式）
- 2 = 运行错误
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

# 复用 ingest_diff 的轻量 frontmatter 解析 + log_format 的日期解析 helper
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_diff import parse_frontmatter_simple  # noqa: E402
from log_format import (
    LOG_LINE_RE,  # noqa: E402
    parse_date_or_datetime,  # noqa: E402
)

# 0.18.0+ fixtures 一致性检查脚本——`--check-version` 自动调一次；
# 其 JSON 输出并入 report["fixtures_check"] + plan["fixtures_actions"]。
# standalone 调用方也可直接跑：scripts/check_wiki_fixtures.py <wiki_root> --json
CHECK_FIXTURES_SCRIPT = "check_wiki_fixtures.py"  # 与本脚本同目录

VALID_TYPES = {
    "entity",
    "concept",
    "source",
    "comparison",
    "synthesis",
    # MEMORY 扩展类型（spec §5.2「或新的 memory 类型按需扩展，本 spec 不限制」）：
    # - `memory`：MEMORY/*.md 自用语义，与 wiki 5 类内容页区分
    # - `memory-entry`：lint-checklist §5.1 提示的 0.6.0 迁移目标（兼容老 MEMORY 写法）
    "memory",
    "memory-entry",
}
# reviewed 字段仅在值为严格 `true` 时合法；缺省 / 其它值（含 "true" 字符串、yes、1、false）判非法
WIKI_SUBDIRS = ("entities", "concepts", "sources", "comparisons", "syntheses")
MEMORY_SUBDIR = "MEMORY"
EXTERNAL_SUBDIR = "external"
ANCHOR_FILENAME = ".symlink-anchor.toml"  # 0.17.0+: TOML 替代旧 .symlink-anchor.json
DISCUSSIONS_SUBDIR = "discussions"  # raw/ 下用户 + LLM 协作草稿层（spec §15）；与 external/ 并列的 raw/ 写权限例外
MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
EXTERNAL_URL_RE = re.compile(r"^(https?:|mailto:|//)")
SOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 绝对路径检测（Unix + Windows）——见 check_frontmatter 的 `sources-absolute-path` 用途。
# - Unix 绝对路径：以 `/` 起始
# - Windows 盘符：`C:\` / `C:/`（兼容正反斜杠，大小写不敏感）
# - Windows UNC：`\\server\share` 形式（双反斜杠起始）
_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_absolute_path(p: str) -> bool:
    """平台无关的"绝对路径"判定

    之所以不走 pathlib.PurePath.is_absolute()：它对 `PureWindowsPath` / `PurePosixPath`
    的行为分平台（同一字符串在 Linux 上跑会判 False，在 Windows 上跑会判 True）。
    lint 必须在 POSIX 主机上跑也能正确判 Windows 绝对路径，故自己写跨平台规则。

    返回 True 的 3 种形式：
    - `/foo/bar`（Unix 绝对）
    - `C:\\foo\\bar` / `C:/foo/bar`（Windows 盘符）
    - `\\\\server\\share`（Windows UNC）

    注：先剥首尾成对引号——`parse_frontmatter_simple` 对 list 元素保留引号（`sources:
    - '/etc/passwd'` 解析为字面 "'/etc/passwd'"），不剥的话单引号包裹的 Unix 绝对路径会被漏判。
    """
    if not p:
        return False
    stripped = p.strip()
    if len(stripped) >= 2 and stripped[0] in ("'", '"') and stripped[-1] == stripped[0]:
        stripped = stripped[1:-1]
    if not stripped:
        return False
    if stripped.startswith("/"):
        return True
    if stripped.startswith("\\\\"):
        return True
    if _WIN_DRIVE_RE.match(stripped):
        return True
    return False


# Wiki spec 当前版本（与 SKILL.md metadata.wiki_spec_version 同步）。
# SSOT 仍是 SKILL.md；这里硬编码 + SKILL 仓升版本时同步改。
# 详见 references/wiki-spec.md §10「版本钉死」。
# 模块加载时 `_assert_spec_version_sync()` 会自动对照 SKILL.md frontmatter；
# 失同步时打印 warning 到 stderr（不中断——vendored 副本布局不同时静默跳过）。
CURRENT_WIKI_SPEC = "0.36.0"


def _assert_spec_version_sync() -> None:
    """运行时校验 CURRENT_WIKI_SPEC 与 SKILL.md metadata.wiki_spec_version 一致。

    脚本常量是 SSOT 的副本（lint 的迁移目标 `to_version` 直接读这里），SKILL.md
    frontmatter 是人读的真源——两边都改才不会漂移。本函数在模块 import 时跑一次，
    不一致时给 stderr warning 提醒维护者修；vendored 副本 / 找不到 SKILL.md 时静默。
    """
    try:
        skill_md = Path(__file__).resolve().parent.parent / "SKILL.md"
    except (OSError, ValueError):
        return
    if not skill_md.is_file():
        return
    try:
        # wiki_spec_version 在 frontmatter 的 metadata: 块下，行首有缩进；
        # 正则允许前导空白。匹配失败时静默（vendored / 旧版本 SKILL.md 可能无此字段）。
        m = re.search(
            r"^[ \t]*wiki_spec_version:[ \t]*(\S+)[ \t]*$",
            skill_md.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    except OSError:
        return
    if m is None:
        return
    declared = m.group(1).strip()
    if declared != CURRENT_WIKI_SPEC:
        sys.stderr.write(
            f"[lint_wiki] WARNING: CURRENT_WIKI_SPEC ({CURRENT_WIKI_SPEC}) "
            f"!= SKILL.md metadata.wiki_spec_version ({declared}). "
            f"升 wiki spec 版本时需同步改脚本常量（SSOT = SKILL.md metadata，"
            f"见 references/wiki-spec.md §10「版本钉死」）。\n"
        )


_assert_spec_version_sync()

# 已知 legacy pattern 的"pattern key"——为后续扩展预留，每个 key 是一类迁移动作。
# rule_ref 是迁移依据的溯源指针；修复语义自含于 plan actions 的 remove/add_or_modify/to_action
# 字段 + references/migrate-workflow.md §六（语义合并规则）——不另设历史档案。
LEGACY_PATTERN_KEYS = {
    "confidence-field": "migrate-workflow.md §6.1",
    # 0.19.0 反转：MEMORY/*.md 上 `type: memory` / `type: memory-entry` 重新合法（spec §5.2）；
    # 本规则仅对 wiki 5 类内容页误用 reserved `type: memory` 报错。
    "type-memory-value": "migrate-workflow.md §6.1 + wiki-spec.md §5.2",
    "claudemd-tag-section": "migrate-workflow.md step 5（action 自带 to_action）",
    "claudemd-not-thinshell": "migrate-workflow.md step 5（action 自带 to_action）+ agents-md-template.md",
}

# 严重性等级
SEV_RANK = {"error": 0, "warn": 1, "info": 2}


def is_external_url(url: str) -> bool:
    return bool(EXTERNAL_URL_RE.match(url.strip()))


def find_md_files(wiki_root: Path) -> Dict[str, List[Path]]:
    """收集所有 wiki/**/*.md，按 type 分类（用子目录名判定）

    MEMORY 子目录扫到独立的 'memory' 桶：走 frontmatter 校验但**不**强制 index 覆盖。
    """
    out = {
        "index": [],  # type: List[Path]
        "log": [],
        "entities": [],
        "concepts": [],
        "sources": [],
        "comparisons": [],
        "syntheses": [],
        "memory": [],
    }  # type: Dict[str, List[Path]]
    wiki_dir = wiki_root / "wiki"
    if not wiki_dir.is_dir():
        return out
    for sub in WIKI_SUBDIRS:
        d = wiki_dir / sub
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                out[sub].append(p)
    # MEMORY/ 单独扫：0.10.0+ 起与 wiki/ 平级、位于 <wiki-root>/MEMORY/（不在 wiki/ 下）
    mem_dir = wiki_root / MEMORY_SUBDIR
    if mem_dir.is_dir():
        for p in sorted(mem_dir.glob("*.md")):
            out["memory"].append(p)
    out["index"].append(wiki_dir / "index.md")
    out["log"].append(wiki_dir / "log.md")
    return out


def is_git_repo(path: Path) -> bool:
    """判定 path 是否在 git 仓内（`.git/` 子目录存在即可，不依赖 git CLI）。

    wiki 默认是裸目录树，git 仅 setup 时 `--git` opt-in；本函数用于自动跳过
    无 git 场景下的 raw/ 不可变性检查，避免无脑报"raw 已被改"（无 git 时
    本来就没有"未提交改动"概念）。"""
    if not path.is_dir():
        return False
    cur = path.resolve()
    while True:
        if (cur / ".git").exists():
            return True
        parent = cur.parent
        if parent == cur:
            return False
        cur = parent


def _git_porcelain_paths(line: str) -> List[str]:
    """从 `git status --porcelain` v1 一行提取全部 path（相对 cwd）。

    普通行返回 1 个 path；rename/copy 行（`XY <old> -> <new>`，git 实测 old 在 `->` 前、
    new 在后）返回 [old, new] 两个。格式：前 2 字符 = XY 状态，第 3 字符 = 空格；
    含特殊字符的 path 被 C 风格双引号包裹。
    """
    if len(line) < 4:
        return []
    rest = line[3:]
    if " -> " in rest:
        paths = rest.split(" -> ", 1)
    else:
        paths = [rest]
    return [p.strip().strip('"') for p in paths]


def check_raw_immutable(wiki_root: Path, use_git: bool) -> List[str]:
    """1. raw/ 是否被改（仅在 wiki 是 git 仓时跑；否则跳过）

    返回元组 (findings, skipped_reason)：
    - findings：原始改动列表（可能为空）
    - skipped_reason：跳过时的提示文本；未跳过时为空字符串。
      调用方决定怎么展示（lint 输出 / 退出码 / 副作用）。
    """
    if not use_git:
        return ([], "")
    raw_dir = wiki_root / "raw"
    if not raw_dir.is_dir():
        return ([], "")
    # 自动检测：不在 git 仓内就直接跳过，不依赖 git CLI；这是"裸目录树
    # wiki 默认支持"的关键路径——强假设 wiki 是 git 仓会让裸目录树误报。
    if not is_git_repo(wiki_root):
        return ([], "raw-immutable-skipped: 未启用 git（无 .git/），跳过 raw/ 不可变性检查")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "raw/"],
            cwd=str(wiki_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except FileNotFoundError:
        # git CLI 不在 PATH（极少见，.git/ 存在但 git 没装）——同样跳过
        return ([], "raw-immutable-skipped: 未找到 git CLI，跳过 raw/ 不可变性检查")
    if result.returncode != 0:
        # 是 git 仓但 raw/ 没被 git 跟踪（`.gitignore` 忽略或从未 add）——
        # 这种情况没有"未提交改动"概念（git 一无所知），跳过
        return ([], "raw-immutable-skipped: raw/ 未纳入 git 跟踪，跳过 raw/ 不可变性检查")
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    # raw/discussions/ 是用户 + LLM 协作的草稿层（spec §15），双方可写——
    # 其未提交改动不属于"raw 被违规改"，从 raw-modified 信号中排除（与 §13 raw/external/
    # 并列为本 skill 的两处 raw/ 写权限例外）。external/ 的 symlink 本身被 .gitignore
    # 排除（spec §13.4），不会出现在 git status 里，故此处只需过滤 discussions/。
    discussions_prefix = "raw/" + DISCUSSIONS_SUBDIR + "/"
    # rename 两侧都可能涉及 discussions/（§15.3 archive mv 跨边界：discussions/ → articles/），
    # 任一路径命中即排除，避免合法归档误报 raw-modified
    lines = [ln for ln in lines if not any(p.startswith(discussions_prefix) for p in _git_porcelain_paths(ln))]
    if not lines:
        return ([], "")
    findings = [f"raw-modified: raw/ 有 {len(lines)} 处未提交改动：{lines[0]}{' ...' if len(lines) > 1 else ''}"]
    return (findings, "")


def _parse_anchor(anchor_path: Path):
    """解析 .symlink-anchor.toml；返回 List[Dict]（每个 entry 一条）或 None（损坏/无有效 entry）

    0.17.0+ schema：顶层 [[entry]] 数组，每 entry 含 symlink / target / captured_at / kind 必填。
    顶层 schema_version = <int>（可选）。返回前已过滤掉缺必填字段 / kind 非 'external-repo' 的 entry。

    解析策略：手写最小 TOML 解析（避免 tomli/tomllib 依赖）——只支持 skill 实际写出的形态：
      - `schema_version = 1`（顶层标量）
      - `[[entry]]` 数组 of tables 头
      - key = "value"（双引号字符串）
      - # 注释（行首 / 行尾 `#` 之后）
    """
    try:
        text = anchor_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    entries = []  # type: List[Dict[str, str]]
    current = None  # type: Optional[Dict[str, str]]
    for raw_line in text.splitlines():
        # 行内注释：仅在引号外剥离（skill anchor 实际写出的字符串不含 #，简化处理）
        if "#" in raw_line:
            # 找不在双引号内的 #；找到就切掉
            in_str = False
            cut = -1
            for i, ch in enumerate(raw_line):
                if ch == '"':
                    in_str = not in_str
                elif ch == "#" and not in_str:
                    cut = i
                    break
            if cut >= 0:
                raw_line = raw_line[:cut]
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        # [[entry]] 数组 of tables 头
        m = re.match(r"^\[\[(\w+)\]\]\s*$", stripped)
        if m:
            if current is not None:
                entries.append(current)
            current = {}
            continue
        # key = "value"
        m = re.match(r'^([a-z_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', stripped)
        if m:
            key, raw_val = m.group(1), m.group(2)
            # 处理 TOML 字符串转义：\\ \" \n \t \r（其他保持原样）
            val = re.sub(
                r"\\(.)",
                lambda mo: {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    '"': '"',
                    "\\": "\\",
                }.get(mo.group(1), mo.group(1)),
                raw_val,
            )
            if current is not None:
                current[key] = val
            # 顶层标量（如 schema_version）落到一个伪 dict 不予返回——仅 entry 数组有意义
            continue
        # key = bare value（int / bool）——顶层 schema_version 等
        m = re.match(r"^([a-z_]+)\s*=\s*([0-9]+|true|false)\s*$", stripped)
        if m:
            # 顶层标量忽略；entry 内 bool/int 我们 schema 不需要
            continue
        # 未知行：lenient 跳过（不阻断；agent 写错时 lint 报 external-anchor-corrupt）

    if current is not None:
        entries.append(current)

    if not entries:
        return None

    # 过滤有效 entry：最小必填 4 字段 + kind = 'external-repo'
    valid = []  # type: List[Dict[str, str]]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        symlink = entry.get("symlink")
        target = entry.get("target")
        captured_at = entry.get("captured_at")
        kind = entry.get("kind")
        if not isinstance(symlink, str) or not symlink:
            continue
        if not isinstance(target, str) or not target:
            continue
        if not isinstance(captured_at, str):
            continue
        if kind != "external-repo":
            continue
        valid.append(entry)
    return valid if valid else None


def check_external_symlinks(wiki_root: Path) -> List[str]:
    """10. raw/external/ 下 symlink 的健康检查（0.17.0+ 扁平 + TOML anchor）

    触发条件：扫 `raw/external/` 顶层，关联 `.symlink-anchor.toml` 的 [[entry]] 数组：
    - external-anchor-missing（error）：symlink 存在但 anchor 文件本身不在
    - external-anchor-corrupt（error）：anchor 解析失败或 0 个有效 entry
    - external-source-name-invalid（error）：symlink 命名不合 `^[a-z0-9][a-z0-9-]*$`
    - external-anchor-orphan（warn）：symlink 存在但 anchor 中无对应 entry（漏录）
    - external-symlink-missing（error）：anchor 有 entry 但 external/ 顶层无对应 symlink
    - external-target-dead（error）：entry.target 路径不存在
    - external-target-drift（warn）：symlink 实际解析 vs anchor target 不一致

    返回 finding 列表；该目录不存在/无 symlink 且无 anchor 时返回空。
    """
    findings = []  # type: List[str]
    external_dir = wiki_root / "raw" / EXTERNAL_SUBDIR
    if not external_dir.is_dir():
        return findings

    # 列出 external/ 顶层：symlinks + 误建的子目录
    try:
        top_entries = list(external_dir.iterdir())
    except OSError:
        return findings

    symlink_names = set()  # type: Set[str]
    # 收集所有 symlink（含 broken symlink —— lexists 行为；symlink-to-dir 也算 symlink）
    for entry in top_entries:
        if entry.name.startswith("."):
            continue
        if entry.name in symlink_names:
            continue  # 罕见：重名，跳过
        # 必须先判 is_symlink：symlink-to-dir 时 is_dir() 也为 True，
        # 但 0.17.0+ 仍把它当 symlink 用（target 是目录是合法的）
        if entry.is_symlink():
            # symlink 命名规范
            if not SOURCE_NAME_RE.match(entry.name):
                rel = entry.relative_to(wiki_root).as_posix()
                findings.append(
                    f"external-source-name-invalid: {rel} symlink 名 '{entry.name}' 不符合 "
                    f"^[a-z0-9][a-z0-9-]*$（kebab-case 短名）"
                )
            symlink_names.add(entry.name)
            continue
        # 非 symlink：子目录（旧 layout 残留）或普通文件
        if entry.is_dir():
            rel = entry.relative_to(wiki_root).as_posix()
            findings.append(
                f"external-source-name-invalid: {rel}/ 是子目录，但 raw/external/ 为扁平布局——"
                f"symlink + anchor 应直接 in external/，不要开 <source-name>/ 子目录"
            )
            continue
        # 普通文件
        rel = entry.relative_to(wiki_root).as_posix()
        findings.append(
            f"external-source-name-invalid: {rel} 是普通文件，但 raw/external/ 顶层只允许 "
            f"symlink + '{ANCHOR_FILENAME}'（扁平布局）"
        )

    # 解析 anchor 文件
    anchor_path = external_dir / ANCHOR_FILENAME
    entries = None  # type: Optional[List[Dict[str, str]]]
    if not anchor_path.is_file():
        if symlink_names:
            # symlink 存在但 anchor 不存在
            findings.append(
                f"external-anchor-missing: raw/external/ 下有 symlink "
                f"{sorted(symlink_names)} 但缺 '{ANCHOR_FILENAME}'（spec §13 必填）"
            )
        return findings
    entries = _parse_anchor(anchor_path)
    if entries is None:
        findings.append(f"external-anchor-corrupt: raw/external/{ANCHOR_FILENAME} 解析失败或 0 个有效 entry")
        return findings

    # entry name → entry dict
    entry_by_symlink = {e["symlink"]: e for e in entries if "symlink" in e}

    # 双向校验：symlink ↔ entry
    # (1) 每个 symlink 必须有对应 entry
    for sl_name in sorted(symlink_names):
        if sl_name not in entry_by_symlink:
            rel = (external_dir / sl_name).relative_to(wiki_root).as_posix()
            findings.append(f"external-anchor-orphan: {rel} 是 symlink 但 anchor 无对应 [[entry]]（spec §13 必填关联）")
            continue
        anchor = entry_by_symlink[sl_name]
        rel = (external_dir / sl_name).relative_to(wiki_root).as_posix()
        target_path = Path(anchor["target"]).expanduser()
        if not target_path.exists():
            findings.append(
                f"external-target-dead: {rel} 的 anchor target='{anchor['target']}' "
                f"已不存在（captured_at={anchor.get('captured_at', '?')}）；"
                f"用户需重新锚定或删除 symlink"
            )
            continue
        # target 存活时：target 路径与当前 symlink 解析不一致 = target 被迁移了
        # 0.14.0+ anchor target 允许 ~/...，比较前 expanduser + resolve：
        # 仅 expanduser 不够——若 home 目录（如 /home/yzr → /apsarapangu/...）本身是
        # symlink，字面 expanduser 后仍带中间 symlink，会与 sl_path.resolve() 不等
        # 而误报 drift。resolve() 把锚和 symlink 拉到同一物理路径再比。
        sl_path = external_dir / sl_name
        try:
            current_target = str(sl_path.resolve())
        except OSError:
            current_target = ""
        try:
            expanded_anchor_target = str(Path(anchor["target"]).expanduser().resolve())
        except OSError:
            expanded_anchor_target = ""
        if current_target and expanded_anchor_target != current_target:
            findings.append(
                f"external-target-drift: {rel} 当前 symlink 解析为 "
                f"'{current_target}'，但 anchor 记录 '{anchor['target']}'"
                f"（展开后 '{expanded_anchor_target}'）；"
                f"anchor 需更新"
            )

    # (2) 每个 entry 必须有对应 symlink
    for entry in entries:
        sl_name = entry.get("symlink", "")
        if sl_name not in symlink_names:
            target = entry.get("target", "?")
            findings.append(
                f"external-symlink-missing: anchor [[entry]] symlink='{sl_name}' target='{target}' "
                f"但 raw/external/{sl_name} symlink 不存在（spec §13 必填关联）"
            )

    return findings


def check_frontmatter(wiki_root: Path) -> List[str]:
    """2. frontmatter 完整性 + 3. source/synthesis 的 sources 字段

    校验口径分两类（spec §5.2 vs §9）：
    - wiki 5 类内容页（entities/concepts/sources/comparisons/syntheses）：
      5 必填（title/type/created/updated/tags）+ 推荐 description
    - MEMORY/*.md：仅 `title` 必填，其余 5 字段全 optional（frontmatter 是
      可选 decoration；MEMORY 不在 wiki/index.md 列出、无 reviewed 概念、
      tag 不共享 wiki taxonomy——5 必填的 rationale 对 MEMORY 多半不成立）
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    # 跳过不存在的 index / log
    # wiki 5 类内容页：完整 5 必填校验
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter_simple(text)
            rel = p.relative_to(wiki_root).as_posix()
            # 必填字段
            for field in ("title", "type", "created", "updated", "tags"):
                if field not in fm:
                    findings.append(f"missing-frontmatter: {rel} 缺 '{field}' 字段")
            # type 合法
            t = fm.get("type")
            if t is not None and t not in VALID_TYPES:
                findings.append(f"invalid-type: {rel} type='{t}' 非法；应为 {sorted(VALID_TYPES)} 之一")
            # source / synthesis 的 sources 必填且非空
            if t in ("source", "synthesis"):
                srcs = fm.get("sources", [])
                if not isinstance(srcs, list) or not srcs:
                    findings.append(f"missing-sources: {rel} type={t} 缺 'sources' 字段或为空")
                else:
                    # 对 source 页：每个 src 必须是 raw/ 下现存路径
                    if t == "source":
                        for s in srcs:
                            if not isinstance(s, str):
                                continue
                            # 0.13.0+：source 页的 sources 必须用相对路径（基于 wiki 根），
                            # 绝对路径（Unix `/...`、Windows 盘符 `C:\...` / UNC
                            # `\\server\...`）会让 wiki 失去跨机器可移植性。命中后
                            # continue 跳过后续 sources-out-of-root / sources-missing——同一根因，
                            # 不重复报错。
                            if _is_absolute_path(s):
                                findings.append(
                                    f"sources-absolute-path: {rel} sources 含绝对路径 '{s}'；"
                                    f"必须用相对 wiki 根的路径（如 raw/articles/... 或 "
                                    f"raw/external/<source-name>/...），与 lint-checklist §二.3 一致"
                                )
                                continue
                            # raw/discussions/ 禁止作 source（spec §15）——
                            # discussions/ 是用户 + LLM 双方可写的协作草稿层，不是"用户掌控的
                            # 真相源"；放开口子 = provenance 后门（LLM 自产内容被当 raw 真相
                            # ingest 回 wiki）。要引用其内容先 mv 到 raw/articles 等正式子树走标准
                            # ingest（spec §15.3）。命中后 continue 跳过后续 external / missing——
                            # 同一根因不重复报错。
                            if s.startswith("raw/" + DISCUSSIONS_SUBDIR + "/"):
                                findings.append(
                                    f"source-in-discussions: {rel} sources='{s}' 指向 "
                                    f"raw/{DISCUSSIONS_SUBDIR}/——discussions/ 是协作草稿层"
                                    f"（spec §15），不可作 source 真相源；先 mv 到 raw/articles "
                                    f"等正式子树再 ingest"
                                )
                                continue
                            # 0.17+ raw/external/<symlink>/... 例外（spec §13.3）：
                            # symlink 跟随 .resolve() 会落到 wiki 根外，本不该判
                            # sources-out-of-root。改为：解析 <symlink> 段、查 anchor +
                            # symlink 存在 + 文件跟随后可访问，全部合法才放过。
                            if s.startswith("raw/external/"):
                                parts = Path(s).parts
                                # 路径段应为 [raw, external, <symlink>, ...]，
                                # 段数 < 3 视为语法错（缺 symlink 名或后续 path）
                                if len(parts) < 3:
                                    findings.append(
                                        f"sources-malformed: {rel} sources='{s}' "
                                        f"raw/external/ 路径需 <symlink>/<path-under-target>"
                                    )
                                    continue
                                sl_name = parts[2]
                                # anchor 文件必须存在（0.17+ TOML）
                                anchor = wiki_root / "raw" / EXTERNAL_SUBDIR / ANCHOR_FILENAME
                                if not anchor.is_file():
                                    findings.append(
                                        f"sources-external-anchor-missing: {rel} sources='{s}' "
                                        f"但 {anchor.relative_to(wiki_root).as_posix()} 不存在"
                                    )
                                    continue
                                # symlink 文件本身必须存在
                                sl_path = wiki_root / "raw" / EXTERNAL_SUBDIR / sl_name
                                if not sl_path.is_symlink() and not sl_path.exists():
                                    findings.append(
                                        f"sources-external-symlink-missing: {rel} sources='{s}' "
                                        f"symlink {sl_name} 不存在"
                                    )
                                    continue
                                # 路径跟随 symlink 后可访问——不 .resolve() 避免相对 wiki
                                # 根判定；只检查可访问性（文件或目录皆可——external repo
                                # 本身是 git 仓即目录，sources 可指向整个仓作语料）
                                sp = wiki_root / s
                                if not sp.exists():
                                    findings.append(f"sources-missing: {rel} sources='{s}' 路径不可访问")
                                continue
                            sp = (wiki_root / s).resolve()
                            try:
                                sp.relative_to(wiki_root.resolve())
                            except ValueError:
                                findings.append(f"sources-out-of-root: {rel} sources='{s}'不在 wiki 根下")
                                continue
                            if not sp.is_file():
                                findings.append(f"sources-missing: {rel} sources='{s}'但文件不存在")
    # MEMORY/*.md（排除 MEMORY/MEMORY.md 索引）：仅 title 必填；其余 5 字段全 optional。
    # frontmatter 整体仍可选（与短条目「1 行索引行」形态对齐）；有就按"有就校验"的
    # 弱规则（type 若取则在 VALID_TYPES 内；tags 若取则是 list）。
    for p in pages["memory"]:
        # 跳过 MEMORY/MEMORY.md（索引，无 frontmatter；不校验字段）
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        rel = p.relative_to(wiki_root).as_posix()
        # title 是唯一必填字段（与文件名 slug 配合做交叉校验 / grep 找页）
        if "title" not in fm:
            findings.append(f"missing-frontmatter: {rel} 缺 'title' 字段")
        # type 若取则必须合法（含 memory / memory-entry 扩展）
        t = fm.get("type")
        if t is not None and t not in VALID_TYPES:
            findings.append(f"invalid-type: {rel} type='{t}' 非法；应为 {sorted(VALID_TYPES)} 之一")
        # tags 若取则必须是 list（否则 wiki tag-not-in-taxonomy 后续会跳过解析）
        if "tags" in fm and not isinstance(fm["tags"], list):
            findings.append(f"invalid-tags: {rel} tags 应为 list，当前类型不符")
    return findings


def resolve_link(base: Path, link: str) -> Optional[Path]:
    """把 Markdown 链接解析为绝对路径；外部 URL / 锚点返回 None"""
    link = link.strip()
    # 去掉锚点
    link = link.split("#", 1)[0]
    # 去掉 query
    link = link.split("?", 1)[0]
    if not link:
        return None
    if is_external_url(link):
        return None
    # 相对路径
    target = (base.parent / link).resolve()
    return target


def check_link_integrity(wiki_root: Path) -> List[str]:
    """4. 路径引用完整性"""
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    all_pages = []
    for sub in WIKI_SUBDIRS + ("index", "log", "memory"):
        all_pages.extend(pages[sub])
    for p in all_pages:
        if not p.is_file():
            continue
        rel = p.relative_to(wiki_root).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in MD_LINK_RE.finditer(text):
            url = m.group(2)
            target = resolve_link(p, url)
            if target is None:
                continue
            # 只检查 wiki 范围内的链接（raw/ 下的图不在范围）
            try:
                target.relative_to(wiki_root.resolve() / "wiki")
            except ValueError:
                continue
            if not target.is_file():
                findings.append(
                    f"broken-link: {rel} 引用 '{url}' 解析为 {target.relative_to(wiki_root).as_posix()}，但文件不存在"
                )
    return findings


def check_index_coverage(wiki_root: Path) -> List[str]:
    """5. index.md 覆盖"""
    findings = []  # type: List[str]
    index_path = wiki_root / "wiki" / "index.md"
    if not index_path.is_file():
        return ["index-missing: wiki/index.md 不存在"]
    index_text = index_path.read_text(encoding="utf-8", errors="replace")
    # 收集 index 引用的所有相对路径
    indexed = set()  # type: Set[str]
    for m in MD_LINK_RE.finditer(index_text):
        url = m.group(2)
        target = resolve_link(index_path, url)
        if target is None:
            continue
        try:
            rel = target.relative_to(wiki_root).as_posix()
        except ValueError:
            continue
        indexed.add(rel)
    # 找所有非 index / log 的页面
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            rel = p.relative_to(wiki_root).as_posix()
            if rel not in indexed:
                findings.append(f"orphan-page: {rel} 未在 wiki/index.md 中列出")
    return findings


def check_log_format(wiki_root: Path) -> List[str]:
    """6. log.md 格式"""
    findings = []  # type: List[str]
    log_path = wiki_root / "wiki" / "log.md"
    if not log_path.is_file():
        return ["log-missing: wiki/log.md 不存在"]
    text = log_path.read_text(encoding="utf-8", errors="replace")
    # 跳过 frontmatter
    body_start = 0
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
        if m:
            body_start = m.end()
    body = text[body_start:]
    for i, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        if line.startswith("## "):
            if not LOG_LINE_RE.match(line):
                findings.append(
                    f"log-format: wiki/log.md 第 {i} 行格式不合规：'{line[:60]}{'...' if len(line) > 60 else ''}'"
                )
    return findings


# log.md 滚动窗口上限——超过则建议截断保最近 N 条（详见 wiki-spec §4.1 Log retention）
LOG_RETENTION_LIMIT = 50

# source 页 stale 摘要阈值（days）——`updated` 距今超过此值报 stale-summary（详见 lint-checklist §二.7）
STALE_SUMMARY_DAYS = 90

# 0.23.0 短暂引入的 INLINED_INDEX_MAX 内联条数护栏已删除（0.24.0+ 恢复 @import 收口；
# MEMORY.md / SCRIPTS.md 索引走 @import 加载，AGENTS.md 仅单行引用、不占 L1 词数），
# 同步删除 check_inlined_memory_index_size() 与 inlined-memory-index-bloating warn。


def check_log_truncation(wiki_root: Path) -> List[str]:
    """10. log.md 滚动窗口——条目数超过 LOG_RETENTION_LIMIT 建议截断

    log.md 只保最近 N 条操作（完整历史靠 git：`git log -p -- wiki/log.md`）。
    判定依据：按 LOG_LINE_RE 正则匹配行数。lint 只报告；截断由 agent 用 Edit/Write
    删最老条目保最近 N 条（脚本不修改 wiki 内容——见本文件顶部职责声明）。
    log-missing 已被 check_log_format 报告，这里跳过重复报错。
    """
    findings = []  # type: List[str]
    log_path = wiki_root / "wiki" / "log.md"
    if not log_path.is_file():
        return findings
    text = log_path.read_text(encoding="utf-8", errors="replace")
    body_start = 0
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
        if m:
            body_start = m.end()
    body = text[body_start:]
    entry_count = sum(1 for line in body.splitlines() if LOG_LINE_RE.match(line))
    if entry_count > LOG_RETENTION_LIMIT:
        findings.append(
            f"log-truncation-recommended: wiki/log.md 含 {entry_count} 条目，超过 {LOG_RETENTION_LIMIT} "
            f"滚动窗口上限；按 wiki-spec §4.1 截断保最近 {LOG_RETENTION_LIMIT} 条"
            f"（完整历史查 git log -p -- wiki/log.md）"
        )
    return findings


def check_stale_summaries(wiki_root: Path, threshold_days: int = STALE_SUMMARY_DAYS) -> List[str]:
    """7. 过期摘要"""
    findings = []  # type: List[str]
    sources_dir = wiki_root / "wiki" / "sources"
    if not sources_dir.is_dir():
        return findings
    today = date.today()
    for p in sources_dir.glob("*.md"):
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        updated = fm.get("updated")
        upd_date = parse_date_or_datetime(updated)
        if upd_date is None:
            continue
        age = (today - upd_date).days
        if age > threshold_days:
            rel = p.relative_to(wiki_root).as_posix()
            findings.append(
                f"stale-summary: {rel} type=source updated={updated} ({age} 天前，超过 {threshold_days} 天阈值)"
            )
    return findings


# Tag taxonomy 解析常量
TAG_TAXONOMY_HEADER_RE = re.compile(r"^###\s+Tag Taxonomy")
TAXONOMY_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
TAG_KV_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Tag taxonomy 主流位置（0.8.0+）：wiki/tags.md，无 frontmatter，纯裸 bullet 列表。
TAG_FILE_PRIMARY = "wiki/tags.md"
# 旧格式 fallback：CLAUDE.md 的 `### Tag Taxonomy` 段。
# 兼容 wiki 升级前未迁移 / 跨 spec 过渡期；新 wiki 不会写这一段。
TAG_SECTION_HEADER = "### Tag Taxonomy"


def _parse_tag_bullets(text: str) -> Set[str]:
    """从裸 bullet 文本里提取 kebab-case tag 集合

    解析规则（兼容两种来源：wiki/tags.md 全文 / CLAUDE.md Tag Taxonomy 段内容）：
    - 每行形如 `- category：tag1 / tag2 / tag3`（中文 / 英文分隔符都支持）
      或 `- tag`（无分类）
    - 多个 tag 用 `/` `，` `,` 任一字符分隔
    - 跳过 code block fence、HTML comment、空行
    - 只保留 kebab-case（`^[a-z0-9][a-z0-9-]*$`）的 tag
    - 不要求特殊 heading——传给本函数的 text 应当已是"目标内容段"（已剔除非 bullet 行）
    """
    tags = set()  # type: Set[str]
    for line in text.splitlines():
        stripped = line.strip()
        # 跳过空行 / 注释 / code block
        if not stripped or stripped.startswith("<!--") or stripped.startswith("```"):
            continue
        # 提取 bullet 内容
        m = TAXONOMY_BULLET_RE.match(stripped)
        if not m:
            continue
        content = m.group(1).strip()
        # 分类形式："category：tag1 / tag2"——第一个 ： 或 : 是分隔符
        sep_match = re.match(r"^([^：:]+)[：:]\s*(.+)$", content)
        if sep_match:
            tag_part = sep_match.group(2)
        else:
            tag_part = content
        # 多 tag 分隔
        for t in re.split(r"[/，,]", tag_part):
            t = t.strip().strip("`").strip("*").strip()
            if t and TAG_KV_RE.match(t):
                tags.add(t)
    return tags


def _extract_claudemd_tag_section(text: str) -> str:
    """从 CLAUDE.md 全文抽出 `### Tag Taxonomy` 段的内容文本（不含 heading 自身）

    段界定：到下一个 #/##/### 标题结束（heading 重复出现仍算段内）。
    段内每行 raw 保留（空行 / code block / comment / bullet 混合），交由
    `_parse_tag_bullets` 过滤。
    """
    out_lines = []  # type: List[str]
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if TAG_TAXONOMY_HEADER_RE.match(stripped):
            in_section = True
            continue
        if in_section and re.match(r"^#{1,4}\s", stripped) and not TAG_TAXONOMY_HEADER_RE.match(stripped):
            break
        if not in_section:
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def parse_tag_taxonomy(wiki_root: Path) -> Set[str]:
    """读 tag 白名单，返回允许 tag 集合

    来源优先级（0.8.0+）：
    1. `<wiki_root>/wiki/tags.md`（**新主流位置**）—— LLM 拥有、按需扩展
    2. fallback：`<wiki_root>/CLAUDE.md` 的 `### Tag Taxonomy` 段
       （旧 wiki / 跨 spec 过渡期；迁移通过 `--check-version --apply` 完成）

    解析失败 / 文件不存在 / 解析出 0 个 tag → 返回空集合（调用方应静默跳过，
    避免新 setup 的 wiki 必报错）。
    """
    primary = wiki_root / TAG_FILE_PRIMARY
    if primary.is_file():
        text = primary.read_text(encoding="utf-8", errors="replace")
        return _parse_tag_bullets(text)
    # Legacy fallback（0.11.0+）：SSOT 的 Tag Taxonomy 段——优先 AGENTS.md，再老 CLAUDE.md
    for candidate in ("AGENTS.md", "CLAUDE.md"):
        spec_file = wiki_root / candidate
        if not spec_file.is_file():
            continue
        try:
            text = spec_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return set()
        section = _extract_claudemd_tag_section(text)
        if section:
            return _parse_tag_bullets(section)
    return set()


def check_tag_taxonomy(wiki_root: Path) -> List[str]:
    """11. tag 是否在 taxonomy 白名单内

    来源：`wiki/tags.md`（0.8.0+），fallback 见 `parse_tag_taxonomy`。
    找不到任何 taxonomy 源 / 解析出 0 个 tag → 静默跳过
    （避免新 setup 的 wiki 必报错）。启用 taxonomy 后，对每个内容页（5 类 +
    MEMORY 非 MEMORY.md）的 frontmatter.tags 元素做包含校验；不在白名单 → info 级。
    """
    findings = []  # type: List[str]
    allowed = parse_tag_taxonomy(wiki_root)
    if not allowed:
        return findings
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    # MEMORY/*.md 不进 tag 白名单校验——按 wiki-spec §5「MEMORY agent 私有」定位：
    # MEMORY 私有 tag（lint / external-repo / symlink 等）是 LLM 工作上下文分类，
    # 不应跟 wiki 用户面共享 taxonomy（spec §9.1 tag 白名单是防 wiki 索引/过滤漂移）。
    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        tags = fm.get("tags", [])
        if not isinstance(tags, list):
            continue
        rel = p.relative_to(wiki_root).as_posix()
        for t in tags:
            if not isinstance(t, str):
                continue
            t = t.strip().strip("\"'")
            if not t:
                continue
            if t not in allowed:
                findings.append(f"tag-not-in-taxonomy: {rel} tags 含 '{t}' 不在 CLAUDE.md 的 Tag Taxonomy 白名单")
    return findings


def check_filename_kebab(wiki_root: Path) -> List[str]:
    """8. 文件名 kebab-case 规范"""
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS + ("index", "log"):
        for p in pages[sub]:
            stem = p.stem
            if not SOURCE_NAME_RE.match(stem):
                rel = p.relative_to(wiki_root).as_posix()
                findings.append(
                    f"filename-not-kebab: {rel} 文件名 '{p.name}' 应使用 kebab-case（小写字母 + 数字 + 短横线）"
                )
    # MEMORY/* 走同一规则，但排除 MEMORY.md（索引，大写不报错）
    for p in pages["memory"]:
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        stem = p.stem
        if not SOURCE_NAME_RE.match(stem):
            rel = p.relative_to(wiki_root).as_posix()
            findings.append(
                f"filename-not-kebab: {rel} 文件名 '{p.name}' 应使用 kebab-case（小写字母 + 数字 + 短横线）"
            )
    return findings


def check_duplicate_titles(wiki_root: Path) -> List[str]:
    """9. 重复标题"""
    findings = []  # type: List[str]
    title_to_files = {}  # type: Dict[str, List[str]]
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter_simple(text)
            title = fm.get("title")
            if not isinstance(title, str):
                continue
            rel = p.relative_to(wiki_root).as_posix()
            title_to_files.setdefault(title, []).append(rel)
    for title, files in title_to_files.items():
        if len(files) > 1:
            findings.append(f"duplicate-title: '{title}' 出现在 {len(files)} 个页面：{', '.join(files)}")
    return findings


# 页面正文行数阈值——超过则建议拆分。
# SSOT：其他文件 prose 提到「单页正文阈值」时，统一引用此常量，避免散弹式散落。
PAGE_SIZE_THRESHOLD = 300


def _strip_frontmatter_body(text):
    """返回去掉 frontmatter 后的正文（frontmatter 不计入页面体量）"""
    body_start = 0
    if text.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
        if m:
            body_start = m.end()
    return text[body_start:]


def check_page_size(wiki_root, threshold=PAGE_SIZE_THRESHOLD):
    """12. 页面体量——正文非空行数 > threshold 的内容页建议拆分

    仅检查 5 类内容页（entities/concepts/sources/comparisons/syntheses）——MEMORY/*
    按 wiki-spec §5.2「正文无长度上限」(agent 私有定位)。计非空行（纯空行不计），避免空行撑大计数。
    阈值见模块顶部 PAGE_SIZE_THRESHOLD（SSOT）。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    for sub in WIKI_SUBDIRS:
        for p in pages[sub]:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            body = _strip_frontmatter_body(text)
            n = sum(1 for ln in body.splitlines() if ln.strip())
            if n > threshold:
                rel = p.relative_to(wiki_root).as_posix()
                findings.append(
                    f"oversized-page: {rel} 正文 {n} 行（非空），超过 {threshold} 阈值——"
                    f"建议拆成子主题页 + cross-link（CLAUDE.md「Page Thresholds」）"
                )
    return findings


def check_quality_signals(wiki_root):
    """13. 可信度与认知质量信号——reviewed / contested / contradictions

    deterministic 子检查（字段全部可选；省略 = 不评，lint 不报）：

    A. 可信度信号 reviewed（0.7.0+）：
    - pending-review（info）：非 log/index 页未含 reviewed: true——新常态，仅提示
    - reviewed-stale（warn）：reviewed: true 存在但 updated > reviewed_at——LLM 修改后漏清戳
    - invalid-reviewed-value（warn）：reviewed 取值非严格 true（如 "true" 字符串、yes、1、false）
    - reviewed-at-missing（warn）：reviewed: true 存在但缺 reviewed_at
    - reviewed-at-orphan（warn）：reviewed_at 存在但缺 reviewed: true

    B. 认知质量信号 contested / contradictions（0.5.0+）：
    - contested-page（warn）：contested: true 的页——含未解决矛盾
    - contradiction-target-missing（warn）：contradictions 指向不存在的页
    - contradiction-asymmetric（warn）：A 把 B 列入 contradictions 但 B 未反向标注 A
      （字段语义要求双向标注，见 page-templates.md §一）

    C. 迁移期检测（0.5.0 → 0.7.0 过渡）：
    - legacy-confidence-field（warn）：出现已退役的 confidence: 字段

    D. index.md 标识漂移（0.7.0+）：
    - index-review-badge-drift（warn）：wiki/index.md 上的 ✓/✗ 标识与被链页 frontmatter 不一致

    字段语义见 page-templates.md §一「可选：可信度与认知质量信号」。
    只把作者已写 / 已渲染的信号拎出来；判定"某页是否真的经过认真审核"是半定性工作。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    # MEMORY/*.md 不进 reviewed 校验——按 wiki-spec §5.2「与 wiki 内容页的区别」：
    # MEMORY 是 agent 私有记忆，无「人工 review」的语义角色。MEMORY/MEMORY.md
    # （索引）本就 excluded。
    # 字段语义（reviewed / reviewed_at / contested / contradictions）仍可被 MEMORY
    # 写、用作 agent 内部信号；只是不进 lint 兜底报告。

    # contradictions 对端映射：page_rel -> set(已解析且存在的 target wiki 相对路径)
    contra_out = {}  # type: Dict[str, Set[str]]
    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        rel = p.relative_to(wiki_root).as_posix()

        # —— A. 可信度信号 reviewed ——
        # 用 raw-line 扫描而非 parse_frontmatter_simple：后者会自动剥引号，
        # 而 `reviewed` 语义要求严格 boolean 字面量 `true`（`reviewed: "true"` 视为非法）
        reviewed_raw = _raw_field_value(text, "reviewed")
        reviewed_at_raw = fm.get("reviewed_at")
        is_reviewed = reviewed_raw == "true"
        has_reviewed_at = reviewed_at_raw is not None and str(reviewed_at_raw).strip() != ""

        # invalid-reviewed-value: reviewed 存在但取值非严格 true
        if reviewed_raw is not None and not is_reviewed:
            findings.append(f"invalid-reviewed-value: {rel} reviewed='{reviewed_raw}' 非法；应为严格 true 或省略")

        # reviewed-at-missing / reviewed-at-orphan: 两个字段应成对
        if is_reviewed and not has_reviewed_at:
            findings.append(f"reviewed-at-missing: {rel} reviewed=true 但缺 reviewed_at")
        if has_reviewed_at and not is_reviewed:
            findings.append(f"reviewed-at-orphan: {rel} reviewed_at='{reviewed_at_raw}' 但缺 reviewed=true")

        # reviewed-stale: LLM 修改后漏清戳（updated > reviewed_at）
        if is_reviewed and has_reviewed_at:
            updated = fm.get("updated")
            if updated and str(updated).strip() > str(reviewed_at_raw).strip():
                findings.append(
                    f"reviewed-stale: {rel} reviewed=true reviewed_at={reviewed_at_raw} "
                    f"但 updated={updated} — LLM 修改后未清 reviewed，建议重新审核"
                )

        # pending-review: 未审核页面（新常态，info）
        if not is_reviewed:
            findings.append(f"pending-review: {rel} 未审核 — 待人工复审后置 reviewed: true")

        # —— C. 迁移期检测 ——
        if "confidence" in fm:
            findings.append(
                f"legacy-confidence-field: {rel} 含已退役 confidence 字段——请运行 lint_wiki.py --migrate-confidence"
            )

        # —— B. 认知质量信号 contested / contradictions ——
        if str(fm.get("contested", "")).strip().strip("\"'").lower() == "true":
            findings.append(f"contested-page: {rel} contested=true — 含未解决矛盾主张，需裁定后移除该标记")

        contras = fm.get("contradictions", [])
        if isinstance(contras, list) and contras:
            resolved = set()  # type: Set[str]
            for c in contras:
                if not isinstance(c, str):
                    continue
                target = resolve_link(p, c)
                if target is None:
                    continue
                try:
                    target_rel = target.relative_to(wiki_root.resolve()).as_posix()
                except ValueError:
                    continue
                if target.is_file():
                    resolved.add(target_rel)
                else:
                    findings.append(
                        f"contradiction-target-missing: {rel} contradictions 含 '{c}'，但该页不存在（{target_rel}）"
                    )
            if resolved:
                contra_out[rel] = resolved

    # 对称性：A 标 B → B 应标 A
    for src, targets in contra_out.items():
        for tgt in targets:
            back = contra_out.get(tgt)
            if back is None or src not in back:
                findings.append(
                    f"contradiction-asymmetric: {src} 把 {tgt} 标为矛盾对端，"
                    f"但 {tgt} 的 contradictions 未反向标注 {src}（要求双向标注）"
                )

    # —— D. index.md 标识漂移 ——
    findings.extend(_check_index_review_badges(wiki_root))

    return findings


# index.md 条目正则：`- [title](path)` 后跟可选 description + 可选 ✓/✗ 标识
_INDEX_ENTRY_RE = re.compile(
    r"^\s*-\s*\[[^\]]+\]\(([^)]+)\)(.*)$",
    re.MULTILINE,
)
# 标识正则：`✓ reviewed YYYY-MM-DD` 或 `✗ pending review`（无外层方括号，与 page-templates.md §一设计一致）
_REVIEWED_BADGE_RE = re.compile(r"✓\s+reviewed\s+(\d{4}-\d{2}-\d{2})\b|✗\s+pending\s+review\b")


def _raw_field_value(text: str, key: str):
    """从原始 frontmatter 文本中提取 key 的字面值，不剥离引号

    parse_frontmatter_simple 会自动剥引号（`reviewed: "true"` → `'true'`），但
    `reviewed` 字段语义要求严格 boolean 字面量 `true`，需看原始字面以区分
    `reviewed: true` 与 `reviewed: "true"` / `reviewed: 'true'` / `reviewed: yes` 等。
    返回 None 表示该 key 不在 frontmatter 中；返回 "" 表示 key 在但值为空。
    """
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return None
    for line in fm_match.group(1).splitlines():
        m = re.match(r"^" + re.escape(key) + r":\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


def _check_index_review_badges(wiki_root):
    """index.md 上的 ✓/✗ 标识与被链页 frontmatter 不一致时报警

    三种漂移都查：
    - 被链页 reviewed=true 但 index 缺标识
    - 被链页 reviewed=true 但 index 日期错
    - 被链页未 reviewed 但 index 有 ✓ reviewed 标识
    """
    findings = []  # type: List[str]
    index_path = wiki_root / "wiki" / "index.md"
    if not index_path.is_file():
        return findings
    text = index_path.read_text(encoding="utf-8", errors="replace")
    wiki_root_resolved = wiki_root.resolve()
    for m in _INDEX_ENTRY_RE.finditer(text):
        path = m.group(1).strip()
        rest = m.group(2)
        # 跳过外链 / 锚点
        if is_external_url(path) or path.startswith("#"):
            continue
        target = (index_path.parent / path).resolve()
        try:
            target.relative_to(wiki_root_resolved)
        except ValueError:
            continue
        if not target.is_file():
            continue  # 已被 orphan-page / broken-link 覆盖
        target_text = target.read_text(encoding="utf-8", errors="replace")
        # 用 raw-line 扫描 reviewed 字段，绕过 parse_frontmatter_simple 的剥引号
        # 行为——`reviewed: "true"` 应判未审核（与 check_quality_signals 严格一致）
        reviewed = _raw_field_value(target_text, "reviewed")
        target_fm = parse_frontmatter_simple(target_text)
        reviewed_at = target_fm.get("reviewed_at")
        is_reviewed = reviewed == "true"
        reviewed_at_s = str(reviewed_at).strip() if reviewed_at is not None else ""
        badge_match = _REVIEWED_BADGE_RE.search(rest)
        # 从条目路径反推被链页标题（用于 finding 信息）
        title_match = re.match(r"\s*-\s*\[([^\]]+)\]", m.group(0))
        title = title_match.group(1) if title_match else path

        if is_reviewed and reviewed_at_s:
            if badge_match is None:
                findings.append(
                    f"index-review-badge-drift: wiki/index.md 条目 '{title}' 缺标识 — "
                    f"被链页 reviewed=true reviewed_at={reviewed_at_s}"
                )
            else:
                # 检查日期是否一致（仅 ✓ reviewed 才带日期）
                if "✓" in badge_match.group(0):
                    actual_date_match = re.search(r"(\d{4}-\d{2}-\d{2})", badge_match.group(0))
                    actual_date = actual_date_match.group(1) if actual_date_match else None
                    if actual_date != reviewed_at_s:
                        findings.append(
                            f"index-review-badge-drift: wiki/index.md 条目 '{title}' "
                            f"标识为 '{badge_match.group(0)}' 但被链页 reviewed=true reviewed_at={reviewed_at_s} — 日期错"
                        )
                else:
                    # 是 ✗ pending review 但被链页其实是 reviewed
                    findings.append(
                        f"index-review-badge-drift: wiki/index.md 条目 '{title}' 标识为 '{badge_match.group(0)}' "
                        f"但被链页 reviewed=true reviewed_at={reviewed_at_s} — 标识类型错"
                    )
        else:
            # 被链页未 reviewed，index 不应有 ✓ reviewed 标识（✗ pending review 与缺省都允许）
            if badge_match and "✓" in badge_match.group(0):
                findings.append(
                    f"index-review-badge-drift: wiki/index.md 条目 '{title}' "
                    f"标识为 '{badge_match.group(0)}' 但被链页未 reviewed — 多余标识"
                )
    return findings


def check_memory_index(wiki_root: Path) -> List[str]:
    """14. MEMORY.md 索引一致性——MEMORY/*.md（非 MEMORY.md）必须被索引列出

    MEMORY.md 是单一真源（无 frontmatter）；由 `<wiki-root>/AGENTS.md` 顶部
    `@MEMORY/MEMORY.md` `@import` 自动加载全文（0.24.0+；详见 wiki-spec §5.1）。
    本检查只扫 `MEMORY.md ## 索引` 段对 `MEMORY/*.md` 的覆盖——0.23.0 短暂的双轨
    （MEMORY.md + AGENTS.md §一内联段并集）已废，单一真源下不再需要双处同步。

    不走 wiki/index.md 强制入口；但每条经验条目需在 `MEMORY.md` 列一行，否则
    下次 `@import` 加载后该 agent 视角下 MEMORY 沦为死库。

    反向（索引列了某 `<slug>.md` 但文件不存在）也在此检查：`memory-index-dangling`
    warn——索引行指向不存在的文件 = 索引与磁盘脱节（MEMORY 纪律"不删除条目"被违反
    或文件被误移），下次会话按索引读必落空。注意只能靠链接判定：短条目
    （`- 一句话事实`）无链接、不算 dangling。

    MEMORY.md 不存在时静默跳过（老 wiki 迁移期 / spec <0.6.0，不报错）。
    severity = info（轻量索引非强制入口，类比 tag-not-in-taxonomy）。

    短条目（0.10.0+ 引入，与项目 CLAUDE.md 同步）：MEMORY.md 索引行可无对应 .md 文件
    （`- 一句话事实` 格式），不进本检查范围——只兜底"有 .md 但未索引"。

    0.10.0+ 路径变更：MEMORY/ 从 wiki/ 下移到 <wiki-root>/MEMORY/（与 wiki/ 平级）。
    """
    findings = []  # type: List[str]
    mem_dir = wiki_root / MEMORY_SUBDIR  # 0.10.0+ 移到 wiki 根下；老 wiki 走 --check-version --apply
    memory_index = mem_dir / "MEMORY.md"
    if not memory_index.is_file():
        return findings
    # 0.24.0+ 单一真源：只扫 MEMORY.md 索引（`@import` 已自动加载全文）；任一条 `<slug>.md`
    # 未列入 MEMORY.md 索引即报 `memory-not-indexed` info。
    indexed = set()  # type: Set[str]
    mem_dir_resolved = mem_dir.resolve()
    # 0.24.0+ 单一真源：MEMORY.md `## 索引` 段对 MEMORY/*.md 的覆盖即可
    # （AGENTS.md 不再持有副本，`@import` 透明加载——无需双轨兜底）。
    try:
        text = memory_index.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for m in MD_LINK_RE.finditer(text):
        target = resolve_link(memory_index, m.group(2))
        if target is None:
            continue
        # 只关心 MEMORY/ 范围内的链接
        try:
            target.relative_to(mem_dir_resolved)
        except ValueError:
            continue
        if target.is_file():
            indexed.add(target.name)
        else:
            # 反向：索引指向的 <slug>.md 不存在（短条目无链接、不进来）——索引与磁盘脱节
            findings.append(
                f"memory-index-dangling: MEMORY/MEMORY.md 索引指向 "
                f"{target.relative_to(wiki_root).as_posix()}，但该文件不存在"
            )
    # 扫 MEMORY/*.md（排除 MEMORY.md 本身）；任一不在 indexed → memory-not-indexed
    if not mem_dir.is_dir():
        return findings
    for p in sorted(mem_dir.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        if p.name not in indexed:
            rel = p.relative_to(wiki_root).as_posix()
            findings.append(
                f"memory-not-indexed: {rel} 未在 MEMORY/MEMORY.md 索引中列出；"
                f"该条目下次会话读不到 "
                f"（追加一行：- <slug> — <一句话> → [正文](<slug>.md)）"
            )
    return findings


def check_related_links(wiki_root: Path) -> List[str]:
    """15. related / compared 路径引用完整性（0.22.0+）

    校验 wiki 内容页 frontmatter 的 `related`（concept 页）与 `compared`
    （comparison 页）字段——按 spec §9「路径格式约定」解析为**内容根 `wiki/`
    相对**（`concepts/X.md` → `<wiki>/wiki/concepts/X.md`），文件不存在则报
    `related-broken-link` warn。注意基准陷阱：`wiki_root` 是最外层 `<wiki>/`
    （其下才是 `wiki/` 内容根），故解析须补 `wiki/` 段——与 source 页 `sources`
    字段走最外层 `raw/` 基准（见 check_frontmatter）刻意区分。

    路径格式约定（spec §9 类型特化字段）：**内容根 `wiki/` 相对路径**（如
    `concepts/transformer.md`），不带前导 `./`、不带 `../` 跨目录、也不带
    `wiki/` 前缀——与正文 Markdown 链接（约定用文件相对路径）形成清晰的两层约定。

    为什么是 warn 而非 error：frontmatter 路径字段是机器消费（lint / cross-page
    综合），不是人直接阅读内容；与正文 `broken-link`（error）严重性区分开，
    让 LLM 在批量 ingest 时不被元数据小毛病阻断。

    与 §二.4 `broken-link` 的区别：本检查覆盖 frontmatter 字段（`related` /
    `compared`），§二.4 覆盖正文 markdown 链接。两者都用 wiki 根或文件相对解析，
    路径校验，但作用域正交。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        rel = p.relative_to(wiki_root).as_posix()
        # related / compared 字段——两字段同语义（按 wiki 根相对路径引用 wiki
        # 内其它页），合并扫描。`contradictions` 走文件相对（§二.13 既有逻辑），
        # 不在本检查范围——约定有意保留两层区分
        for field_name in ("related", "compared"):
            items = fm.get(field_name, [])
            if not isinstance(items, list) or not items:
                continue
            for idx, item in enumerate(items):
                if not isinstance(item, str):
                    continue
                # 防御：若元素是外部 URL（语义上不该出现但防御性兜底）→ 跳过
                if is_external_url(item):
                    continue
                # spec §9：related / compared 是内容根 wiki/ 相对（concepts/X.md），
                # 不是最外层根相对——wiki_root 是 <wiki>/，真实内容页在 <wiki>/wiki/<sub>/，
                # 故补 wiki/ 段。不 .resolve() 避免跟随实际不存在的目录/文件时静默吞错
                # （is_file() 已能准确判定）
                target = wiki_root / "wiki" / item
                if not target.is_file():
                    findings.append(
                        f"related-broken-link: {rel} {field_name}[{idx}]='{item}' "
                        f"按内容根 wiki/ 相对解析为 wiki/{item}，但文件不存在"
                    )
    return findings


def severity_of(finding: str) -> str:
    """从 finding 的类别前缀推断严重性"""
    if finding.startswith(
        (
            "raw-modified",
            "missing-frontmatter",
            "invalid-type",
            "sources-missing",
            "sources-malformed",
            "sources-out-of-root",
            "sources-absolute-path",
            "sources-external-anchor-missing",
            "sources-external-symlink-missing",
            "source-in-discussions",
            "broken-link",
            "orphan-page",
            "index-missing",
            "log-missing",
            "external-anchor-missing",
            "external-anchor-corrupt",
            "external-target-dead",
            "external-source-name-invalid",
            "external-symlink-missing",
        )
    ):
        return "error"
    if finding.startswith(("external-anchor-orphan", "external-target-drift")):
        return "warn"
    if finding.startswith(
        ("stale-summary", "log-format", "filename-not-kebab", "duplicate-title", "log-truncation-recommended")
    ):
        return "warn"
    if finding.startswith(
        (
            "contested-page",
            "reviewed-stale",
            "invalid-reviewed-value",
            "reviewed-at-missing",
            "reviewed-at-orphan",
            "index-review-badge-drift",
            "legacy-confidence-field",
            "contradiction-target-missing",
            "contradiction-asymmetric",
            "oversized-page",
            "related-broken-link",
            "memory-index-dangling",
        )
    ):
        return "warn"
    if finding.startswith(("tag-not-in-taxonomy", "pending-review", "memory-not-indexed")):
        return "info"
    if finding.startswith(("wiki-spec-version-stale", "wiki-spec-version-ahead", "wiki-spec-version-unparsed")):
        return "warn"
    return "info"


def migrate_confidence(wiki_root: Path) -> int:
    """0.5.0 → 0.7.0 一次性迁移：把老 confidence 字段转成新 reviewed + reviewed_at

    行为：
    - confidence: high → 写 reviewed: true + reviewed_at: <today>，移除 confidence
    - confidence: medium / low / 其它 → 仅移除 confidence（默认未审核）
    - 已含 reviewed / reviewed_at 字段的页面 → 跳过（migration-conflict），不覆盖人工决策

    不写 log 条目（迁移是脚本运行，不是 wiki 操作事件）。
    不做常规 lint 检查（互斥模式）。
    """
    today = date.today().isoformat()
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    for p in pages["memory"]:
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        target_pages.append(p)

    n_migrated = 0  # confidence: high → reviewed: true + reviewed_at
    n_removed = 0  # confidence: medium/low/其它 → 仅移除
    n_skipped = 0  # 冲突（已有 reviewed/reviewed_at）

    for p in target_pages:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        if "confidence" not in fm:
            continue
        rel = p.relative_to(wiki_root).as_posix()
        conf_value = str(fm["confidence"]).strip().strip("\"'").lower()

        # 冲突：已有 reviewed 字段——不覆盖人工决策
        if "reviewed" in fm or "reviewed_at" in fm:
            print(f"  [SKIP] {rel}: 已有 reviewed/reviewed_at 字段（migration-conflict）")
            n_skipped += 1
            continue

        new_text = _migrate_confidence_in_text(text, conf_value, today)
        if new_text == text:
            continue
        p.write_text(new_text, encoding="utf-8")
        if conf_value == "high":
            n_migrated += 1
            print(f"  [MIGRATE] {rel}: confidence=high → reviewed=true reviewed_at={today}")
        else:
            n_removed += 1
            print(f"  [REMOVE] {rel}: confidence={conf_value} → 移除 confidence 字段")

    print()
    print(f"Migration summary: {n_migrated} migrated, {n_removed} removed, {n_skipped} skipped (conflicts)")
    return 0


def _migrate_confidence_in_text(text: str, conf_value: str, today: str) -> str:
    """修改单个文件的 frontmatter：移除 confidence 行；high 时在 updated 后插入 reviewed + reviewed_at

    操作：line-by-line scan in frontmatter block。不引入额外缩进以保持简单，
    复用现有 frontmatter 解析器期望的 `key: value` 单行格式。
    """
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return text
    fm_text = fm_match.group(1)
    body = text[fm_match.end() :]

    new_lines = []  # type: List[str]
    inserted_reviewed = False
    for line in fm_text.splitlines():
        # 移除 confidence 行（任意值，包括非法）
        if re.match(r"^\s*confidence:\s*", line):
            continue
        new_lines.append(line)
        # high → 在 updated 行之后插入 reviewed + reviewed_at
        if not inserted_reviewed and conf_value == "high" and re.match(r"^\s*updated:\s*", line):
            new_lines.append("reviewed: true")
            new_lines.append("reviewed_at: " + today)
            inserted_reviewed = True

    new_fm = "\n".join(new_lines)
    if not new_fm.endswith("\n"):
        new_fm += "\n"
    return "---\n" + new_fm + "---\n" + body


# ---------------------------------------------------------------------------
# --check-version：扫描 wiki 的 spec 版本 + 老格式 legacy 现场
# 设计见 yzr-llm-wiki-management/docs/superpowers/specs/<date>-migrate-design.md
# 职责：纯探测（不动 wiki 内容）；agent 拿到 plan 后按 references/migrate-workflow.md 走 Edit/Write 修复。
# ---------------------------------------------------------------------------

# CLAUDE.md §八 表格行匹配：
# | Wiki Spec 版本 | 0.7.0 |
# 兼容用户编辑后的格式变体（多余空格、备注尾部等）；semver 走单独正则抓取。
CLAUDE_VERSION_ROW_RE = re.compile(r"^\s*\|\s*Wiki Spec 版本\s*\|\s*([^|]+?)\s*\|")
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")


def parse_spec_version(wiki_root: Path) -> Optional[str]:
    """从 wiki 纪律 SSOT §八 表里抽 "Wiki Spec 版本"。

    0.11.0+：SSOT 是 <wiki-root>/AGENTS.md（薄壳 CLAUDE.md 不持版本）。
    老 wiki（0.10.0-）：SSOT 是 <wiki-root>/CLAUDE.md，按候选顺序 fallback 兼容。

    返回 semver 字符串（如 "0.11.0"）；找不到或解析失败返回 None。

    设计权衡：仅解析 §八 表的"Wiki Spec 版本"行，不扫描全文（避免误抓正文里出现的
    版本号）。用户编辑表格时若格式被破坏（例如把"Wiki Spec 版本"改成"Wiki 版本"），
    解析失败——提示用户人工填回，而不是猜。
    """
    for candidate in ("AGENTS.md", "CLAUDE.md"):
        spec_file = wiki_root / candidate
        if not spec_file.is_file():
            continue
        try:
            text = spec_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = CLAUDE_VERSION_ROW_RE.match(line)
            if not m:
                continue
            cell = m.group(1).strip()
            # 单元格可能含备注（如 "0.7.0 (current)"），抓首个 semver
            semver = SEMVER_RE.search(cell)
            if semver:
                return semver.group(0)
            # 单元格写了非 semver 文本——视为解析失败
            return None
    return None


def check_spec_version(wiki_root: Path) -> List[str]:
    """常规 lint 也查 wiki 版本与 SKILL（CURRENT_WIKI_SPEC）是否一致；不一致提示走升级流程。

    与 cmd_check_version 复用同一 parse_spec_version + _compare_semver，但本函数只产
    warn finding 提示（不产 plan——plan 由 --check-version --apply 落）。让用户日常
    lint 时就能感知「wiki 版本落后/领先 SKILL」，而不必显式跑 --check-version 才发现。
    """
    findings = []  # type: List[str]
    current = parse_spec_version(wiki_root)
    if current is None:
        findings.append(
            "wiki-spec-version-unparsed: AGENTS.md §八「Wiki Spec 版本」行无法解析"
            "（缺 AGENTS.md / CLAUDE.md 或表格格式破坏）——"
            "跑 `lint_wiki.py --check-version` 诊断"
        )
        return findings
    cmp = _compare_semver(current, CURRENT_WIKI_SPEC)
    if cmp == "older":
        findings.append(
            f"wiki-spec-version-stale: AGENTS.md §八 版本 {current} 落后 SKILL {CURRENT_WIKI_SPEC}——"
            "跑 `lint_wiki.py --check-version --apply` 走升级流程"
        )
    elif cmp == "newer":
        findings.append(
            f"wiki-spec-version-ahead: AGENTS.md §八 版本 {current} 领先 SKILL {CURRENT_WIKI_SPEC}——"
            "升级 SKILL 仓（lint_wiki.py）对齐"
        )
    # equal / unknown → 无 finding
    return findings


def _run_fixtures_check(wiki_root: Path) -> Dict[str, object]:
    """调 scripts/check_wiki_fixtures.py 同仓子进程；返其 JSON 输出。

    失败兜底：脚本找不到 / 跑挂时返空 dict（不带 'checks' 字段）—— caller 据此判断
    「fixtures check 未跑」，不应阻 lint 主流程。subprocess 跑挂时把 stderr 回显到
    本脚本 stderr（便于调试——不影响主报告）。
    """
    script_path = Path(__file__).resolve().parent / CHECK_FIXTURES_SCRIPT
    if not script_path.is_file():
        return {"skipped": True, "reason": f"{CHECK_FIXTURES_SCRIPT} not found at {script_path}"}
    try:
        proc = subprocess.run(  # noqa: UP021
            [sys.executable, str(script_path), str(wiki_root), "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # noqa: UP022
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"skipped": True, "reason": f"{CHECK_FIXTURES_SCRIPT} exec failed: {e}"}
    if proc.returncode not in (0, 1):  # 0 = pass, 1 = 有 finding
        sys.stderr.write(f"[lint_wiki] fixtures check 非 0/1 退出: rc={proc.returncode}\n")
        sys.stderr.write(proc.stderr)
        return {"skipped": True, "reason": f"non-pass exit code {proc.returncode}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"skipped": True, "reason": f"invalid JSON from fixtures check: {e}"}


def _has_confidence_field(text: str) -> bool:
    """frontmatter 顶层 `confidence: <value>` 行——不递归嵌套对象，匹配现存写法。"""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return False
    for line in m.group(1).splitlines():
        if re.match(r"^\s*confidence:\s*\S+", line):
            return True
    return False


def _has_legacy_confidence_conflict(text: str) -> bool:
    """冲突页：同时含老 confidence 字段与新 reviewed 字段——agent 跳过 + 转人工。"""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return False
    has_confidence = False
    has_reviewed = False
    for line in m.group(1).splitlines():
        if re.match(r"^\s*confidence:\s*\S+", line):
            has_confidence = True
        if re.match(r"^\s*reviewed:\s*\S+", line):
            has_reviewed = True
    return has_confidence and has_reviewed


def _has_type_memory(page_rel: str, text: str) -> bool:
    """frontmatter `type: memory` 在 wiki 5 类内容页上误用——0.19.0 起仅对 wiki 内容页生效。

    MEMORY/*.md 上 `type: memory` / `type: memory-entry` 是 0.19.0 合法值
    （spec §5.2——MEMORY frontmatter 解耦 + 扩展 `memory` / `memory-entry` 两类），
    故跳过 `page_rel` 起始于 `MEMORY/` 的页面。

    Args:
        page_rel: 页面相对 wiki 根的 POSIX 路径（如 `wiki/sources/x.md` / `MEMORY/foo.md`）
        text: 页面全文

    Returns:
        True 当且仅当页面**不在** MEMORY/ 下且 frontmatter 含 `type: memory`
    """
    # MEMORY/*.md 上 `type: memory` / `type: memory-entry` 在 0.19.0+ 合法，跳过
    if page_rel.startswith("MEMORY/"):
        return False

    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return False
    for line in m.group(1).splitlines():
        if re.match(r"^\s*type:\s*memory\s*$", line):
            return True
    return False


def detect_legacy_patterns(wiki_root: Path) -> Dict[str, object]:
    """扫已知 legacy 现场，按 pattern key 分组 + 标记冲突。

    返回结构（供 build_migration_plan 与 --json 输出复用）：
    {
      "patterns": {
        "confidence-field":     [{"file": "wiki/sources/x.md", "conflict": False}, ...],
        # 0.19.0+：仅 wiki 5 类内容页误用 reserved `type: memory` 触发；MEMORY/*.md 不进此列表
        "type-memory-value":    [{"file": "wiki/<entities|concepts|sources|comparisons|syntheses>/x.md", "conflict": False}],
        "claudemd-tag-section": [{"file": "CLAUDE.md", "conflict": False}],
      },
      "conflicts": [
        {"file": "wiki/sources/<legacy-page>.md", "reason": "同时含 confidence + reviewed 字段"}
      ],
    }
    """
    pages = find_md_files(wiki_root)
    out = {
        "patterns": {k: [] for k in LEGACY_PATTERN_KEYS},  # type: Dict[str, List[Dict[str, object]]]
        "conflicts": [],  # type: List[Dict[str, str]]
    }  # type: Dict[str, object]

    # 扫所有内容页 + MEMORY 经验条目（不含 MEMORY.md 索引本身）
    candidates = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        candidates.extend(pages[sub])
    for p in pages["memory"]:
        if p.name == "MEMORY.md" and p.parent.name == MEMORY_SUBDIR:
            continue
        candidates.append(p)

    for p in candidates:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(wiki_root).as_posix()

        if _has_confidence_field(text):
            conflict = _has_legacy_confidence_conflict(text)
            out["patterns"]["confidence-field"].append({"file": rel, "conflict": conflict})  # type: ignore
            if conflict:
                out["conflicts"].append(  # type: ignore
                    {"file": rel, "reason": "同时含 legacy confidence 字段与 reviewed 字段——agent 跳过 + 转人工裁定"}
                )

        if _has_type_memory(rel, text):
            out["patterns"]["type-memory-value"].append({"file": rel, "conflict": False})  # type: ignore

    # 文件级 legacy：CLAUDE.md 仍含 `### Tag Taxonomy` 段（0.8.0+ 移到 wiki/tags.md）
    # 只要 heading 行存在就报 legacy——含 bullets 时迁移内容；空段只清 heading
    claude_md = wiki_root / "CLAUDE.md"
    if claude_md.is_file():
        try:
            claude_text = claude_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            claude_text = ""
        if any(TAG_TAXONOMY_HEADER_RE.match(line.strip()) for line in claude_text.splitlines()):
            out["patterns"]["claudemd-tag-section"].append(  # type: ignore
                {"file": "CLAUDE.md", "conflict": False}
            )
        # claudemd-not-thinshell（0.11.0+）：CLAUDE.md 仍是 SSOT 形态——不含 `@AGENTS.md` 薄壳行
        # 且行数 > 30（薄壳模板 ≤ 30 行）→ 老 wiki 未拆 SSOT，由 claudemd-to-agents-md-split 迁移
        claude_lines = claude_text.splitlines()
        has_agents_import = any(line.strip() == "@AGENTS.md" for line in claude_lines)
        if not has_agents_import and len(claude_lines) > 30:
            out["patterns"]["claudemd-not-thinshell"].append(  # type: ignore
                {"file": "CLAUDE.md", "conflict": False}
            )

    return out


def _compare_semver(current: Optional[str], skill: str) -> str:
    """返回 'equal' / 'older' / 'newer' / 'unknown'。semver 简单元组比较；缺值=unknown。"""
    if not current:
        return "unknown"

    def parse(v: str) -> Optional[tuple]:
        m = SEMVER_RE.search(v)
        if not m:
            return None
        try:
            return tuple(int(x) for x in m.group(0).split("."))
        except ValueError:
            return None

    c = parse(current)
    s = parse(skill)
    if not c or not s:
        return "unknown"
    if c < s:
        return "older"
    if c > s:
        return "newer"
    return "equal"


def build_migration_plan(
    wiki_root: Path,
    current_spec: Optional[str],
    legacy: Dict[str, object],
    fixtures_check: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """把 detect_legacy_patterns 的发现 + fixtures-check 的发现组织成 agent 可执行的 plan。

    每个 action 含 file / type / rule_ref / 具体 remove & add_or_modify；
    agent 按 references/migrate-workflow.md 引用 rule_ref 走 Edit/Write。
    fixtures-fix-* 类动作落进 `fixtures_actions[]`，与 legacy pattern 的 actions[] 平行——
    agent 走 plan 时两套都得跑（fixtures 修复优先于内容页 frontmatter 修复）。
    """
    today = date.today().isoformat()
    actions = []  # type: List[Dict[str, object]]
    fixtures_actions = []  # type: List[Dict[str, object]]

    # confidence-field → 0.5.0/0.7.0 迁移规则
    for entry in legacy["patterns"]["confidence-field"]:  # type: ignore
        if entry["conflict"]:  # type: ignore
            continue  # 冲突页不进 plan
        fpath = entry["file"]  # type: ignore
        # 读 frontmatter 拿 confidence 值——决定 migrated vs removed
        full = wiki_root / fpath
        text = full.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter_simple(text)
        conf_value = str(fm.get("confidence", "")).strip().strip("\"'").lower()
        action = {
            "file": fpath,
            "type": "frontmatter-rename",
            "rule_ref": LEGACY_PATTERN_KEYS["confidence-field"],
            "remove": ["confidence"],
            "add_or_modify": {},
        }  # type: Dict[str, object]
        if conf_value == "high":
            action["add_or_modify"] = {"reviewed": True, "reviewed_at": today}  # type: ignore
        actions.append(action)

    # type-memory-value → 0.19.0 迁移规则（仅作用于 wiki 5 类内容页；MEMORY/*.md 在 0.19.0+ 合法不会被此规则扫到）
    for entry in legacy["patterns"]["type-memory-value"]:  # type: ignore
        fpath = entry["file"]  # type: ignore
        actions.append(
            {
                "file": fpath,
                "type": "frontmatter-retype",
                "rule_ref": LEGACY_PATTERN_KEYS["type-memory-value"],
                "remove": ["type"],
                # 0.19.0 起 `memory-entry` 是合法扩展值；误用 reserved `type: memory` 应改为 wiki 内容页对应的 5 类之一（agent 按页面真实语义裁定）
                "add_or_modify": {"type": "memory-entry"},  # 占位默认——agent 改 plan 时按页面语义替换
                "note": "0.19.0 起仅 wiki 5 类内容页误用 reserved `type: memory` 触发；MEMORY/*.md 上 `type: memory` 已合法。Agent 应按页面真实语义决定：wiki 内容页改为对应 5 类（entity/concept/source/comparison/synthesis）之一；不要把 wiki 内容页改成 `memory-entry`（那是 MEMORY 桶的扩展值）。",
            }
        )

    # claudemd-tag-section → 0.8.0+ 迁移规则：把 CLAUDE.md 的 Tag Taxonomy 段搬到 wiki/tags.md
    # 一条组合动作：创建 wiki/tags.md + 删除 CLAUDE.md 中该段（含 heading + 子 bullet）
    # 模式列表要么空要么含一个 CLAUDE.md 条目——按是否有 legacy 决定是否生成 action
    if legacy["patterns"]["claudemd-tag-section"]:  # type: ignore
        actions.append(
            {
                "file": "wiki/tags.md",
                "type": "tag-taxonomy-migrate",
                "rule_ref": LEGACY_PATTERN_KEYS["claudemd-tag-section"],
                "from_file": "CLAUDE.md",
                "section_header": TAG_SECTION_HEADER,
                "to_action": (
                    "读 CLAUDE.md 中 `### Tag Taxonomy` 段所有 bullet 内容"
                    "（用本脚本 `_extract_claudemd_tag_section` 函数语义——到下一个 #/##/### 标题结束）。"
                    "若段有 bullet：在 <wiki_root>/wiki/tags.md 写入该内容"
                    "（无 frontmatter，文件顶部加简短 H1 标题如 `# Tags` + 一句说明，文末保留原 bullet 列表）；"
                    "若段为空（heading 在无 bullet），跳过 wiki/tags.md 写入。"
                    "完成后从 CLAUDE.md Edit 删除整个 `### Tag Taxonomy` 段"
                    "（含 heading 行 + 直到下一标题前的所有 bullet / 空行）。"
                    "若 wiki/tags.md 已存在，先检查内容是否相同——相同则跳过写入；不同给迁移冲突，转人工"
                ),
            }
        )

    # claudemd-not-thinshell → 0.11.0+ 迁移：老 CLAUDE.md（SSOT）拆为 AGENTS.md（SSOT）+ CLAUDE.md（薄壳）
    if legacy["patterns"]["claudemd-not-thinshell"]:  # type: ignore
        actions.append(
            {
                "file": "AGENTS.md",
                "type": "claudemd-to-agents-md-split",
                "rule_ref": LEGACY_PATTERN_KEYS["claudemd-not-thinshell"],
                "from_file": "CLAUDE.md",
                "to_action": (
                    "把 <wiki_root>/CLAUDE.md 的全部纪律正文（SSOT 内容）搬到 <wiki_root>/AGENTS.md。"
                    "AGENTS.md 顶部按 references/agents-md-template.md 的说明块格式：SSOT 声明 + agent 中立"
                    "读取机制段 + @import 行（@MEMORY/MEMORY.md + @scripts/SCRIPTS.md），随后接原 CLAUDE.md"
                    "正文（§一~§八）。然后把 <wiki_root>/CLAUDE.md 重写为薄壳（@AGENTS.md + 薄壳声明，"
                    "参考 references/claude-md-template.md），保留已替换的主题名。若 AGENTS.md 已存在——内容"
                    "相同则跳过；不同给迁移冲突，转人工。AGENTS.md §八 Wiki Spec 版本由后续通用步骤改为 to_version。"
                ),
            }
        )

    # 0.18.0+ fixtures 一致性 → fixtures_actions[]
    # 每条 fixtures-check 失败项生成一条对应 fixtures-fix-* 动作；action 字段含
    # expected / actual 让 agent 一眼看清"该改成什么"；rule_ref 指向 lint-checklist.md
    # §三 anchor / §三.5 MEMORY / §三.6 log 等具体段落。
    if fixtures_check and not fixtures_check.get("skipped"):
        for fc in fixtures_check.get("checks", []) or []:  # type: ignore
            if fc.get("passed") is not False:  # type: ignore
                continue
            cid = fc["id"]  # type: ignore
            fpath = fc["file"]  # type: ignore
            expected = fc.get("expected", "")  # type: ignore
            actual = fc.get("actual", "")  # type: ignore
            rule_ref = fc.get("rule_ref", "")  # type: ignore
            severity = fc.get("severity", "error")  # type: ignore
            base = {
                "check_id": cid,
                "file": fpath,
                "severity": severity,
                "rule_ref": rule_ref,
                "expected": expected,
                "actual": actual,
            }
            if cid == "gitignore-external-track-toml":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-gitignore",
                        "to_action": (
                            "Edit .gitignore：把旧 `!raw/external/**/.symlink-anchor.json` 行替换为"
                            " `!raw/external/.symlink-anchor.toml`；保留 `raw/external/*` 排除行不动；"
                            "保留其它规则不动"
                        ),
                    }
                )
            elif cid == "agents-version-is-current":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-agents-version",
                        "to_action": (
                            f"Edit {fpath} §八 Wiki Spec 版本行单元格改为 `{expected}`（实际为 `{actual}`）——"
                            "参考 lint-checklist.md §三.1 + wiki-spec.md §10"
                        ),
                    }
                )
            elif cid == "agents-md-template-sync":
                # 0.26.0+ 模板渲染比对失败 → 全量重渲染（不是单行 Edit）；
                # 详见 migrate-workflow.md §5 step 6 + wiki-spec.md §10.1
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-agents-md-resync",
                        "to_action": (
                            "AGENTS.md 全量重渲染（0.26.0+ 模板同步机制，4 步）："
                            "(1) 从旧 AGENTS.md §八 提取 主题 / 创建日期 / CLI 版本（主题 fallback："
                            "H1 `# <主题> Wiki — LLM 维护守则`）；"
                            "(2) 渲染 references/agents-md-template.md——{{TOPIC_NAME}} / {{SETUP_DATE}} / "
                            "{{CLI_VERSION}} 用旧值，{{WIKI_SPEC_VERSION}} 用 to_version；"
                            "(3) diff 旧文件 vs 渲染稿：旧文件**多出的行/段** = 本地定制，逐条列给用户裁定——"
                            "搬 MEMORY/（一行事实写 MEMORY/MEMORY.md 索引短条目；含 why 的建 "
                            "MEMORY/<slug>.md 完整条目 + 索引行）或丢弃；"
                            "(4) Write 渲染稿覆盖 AGENTS.md——成长内容仅 §八 四行变量，其余以模板为准"
                        ),
                    }
                )
            elif cid == "symlink-anchor-flat-not-legacy":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-anchor-merge",
                        "to_action": (
                            "按 lint-checklist §五.3 走 5 步："
                            "(1) 扫 raw/external/<source-name>/ 子目录；"
                            "(2) 读 .symlink-anchor.json 内容；"
                            "(3) 把 <source-name>/<symlink> mv 到 raw/external/ 顶层（重名冲突转人工）；"
                            "(4) 构造 [[entry]] 块（含 symlink/target/captured_at/kind + 可选 git 身份字段），追加到 raw/external/.symlink-anchor.toml；"
                            "(5) 删 raw/external/<source-name>/ 整个目录"
                        ),
                    }
                )
            elif cid == "symlink-anchor-toml-schema":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-anchor-schema",
                        "to_action": (
                            "按 wiki-spec §13.2 修 raw/external/.symlink-anchor.toml："
                            "schema_version=1 顶层 + 每 [[entry]] 必填 4 字段 + git 身份字段可选。"
                            "若文件损坏，重写（先备份为 .bak，重新汇总 entries）"
                        ),
                    }
                )
            elif cid == "symlink-anchor-toml-symlink-matches":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-anchor-symlink-matches",
                        "to_action": (
                            "双向校验：anchor 有 entry 但 symlink 缺 → `mkdir -p raw/external && ln -s <target> raw/external/<symlink>`；"
                            "symlink 有但 anchor 无 entry → 补一条 `[[entry]]` 块（含 symlink/target/captured_at/kind + 可选 git 身份字段）"
                        ),
                    }
                )
            elif cid in ("memory-index-no-frontmatter", "scripts-md-no-frontmatter", "tags-md-no-frontmatter"):
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-strip-frontmatter",
                        "to_action": f"Edit {fpath}：删除首部 `---...---` YAML frontmatter 块，保留正文",
                    }
                )
            elif cid == "memory-entries-indexed":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-memory-index",
                        "to_action": (
                            "按 wiki-spec §5.1 在 MEMORY/MEMORY.md 索引追加缺失条目："
                            "`- [<slug>](<slug>.md) — 一句话 → [正文](<slug>.md)`"
                        ),
                    }
                )
            elif cid == "log-md-format-strict":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-log-format",
                        "to_action": (
                            f"Edit {fpath} 不合规行：每行匹配 `^## [YYYY-MM-DD HH:MM] (ingest|query|lint|setup) | .+$`（HH:MM 可选；老 wikis date-only 仍合法，宽容解析）；"
                            "迁移期不变更 history（仅当行确属违规，才 Edit 修复格式；保留日期 + 类型 + 简介）"
                        ),
                    }
                )
            elif cid == "index-md-categories-stable":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-index-categories",
                        "to_action": (
                            f"按 wiki-spec §3 补齐 {fpath} 缺类别：5 标题齐全 "
                            "(Entities / Concepts / Sources / Comparisons / Syntheses)，顺序可调"
                        ),
                    }
                )
            elif cid.endswith(("-skeleton", "-frontmatter-complete", "-init-rules-complete")):
                # 0.20.0+ 骨架字段级比对 check（信号来自 references/canonical +
                # references/fixtures/gitignore.txt；新增 *-skeleton 类 check 自动匹配此分支）
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-skeleton",
                        "to_action": (
                            f"Edit {fpath}：按 references/canonical（或 fixtures/gitignore.txt）"
                            "补齐 expected 列出的缺失骨架字段（frontmatter 键 / H1 / 说明块 / "
                            "段标题 / .gitignore 段）。成长型内容（index 类别下条目 / log 历史 / "
                            "MEMORY 经验 / tag bullet）**不动**——只补结构骨架"
                        ),
                    }
                )
            else:
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-unknown",
                        "to_action": f"按 rule_ref ({rule_ref}) 与 {cid} 描述自行处理",
                    }
                )

    plan = {
        "generated_at": today,
        "from_version": current_spec,
        "to_version": CURRENT_WIKI_SPEC,
        "skill_path": "yzr-llm-wiki-management/SKILL.md",
        "spec_doc": "yzr-llm-wiki-management/references/wiki-spec.md",
        "rule_doc": "yzr-llm-wiki-management/references/migrate-workflow.md",
        "actions": actions,
        "fixtures_actions": fixtures_actions,
        "skipped_conflicts": legacy.get("conflicts", []),  # type: ignore
        "agent_rules": [
            "按 actions[] 顺序逐项修；每个 action 前打印依据 rule_ref",
            "frontmatter-rename：用 Edit 改 frontmatter（删老字段、加新字段；不动 updated）",
            "file-move：先读源 → 写目标 → 删源",
            "frontmatter-retype：按 action.note 与 wiki-spec §5.2 决定具体改法",
            "skipped_conflicts[] 永远不自动覆盖——转人工",
            "claudemd-to-agents-md-split：老 CLAUDE.md 正文搬到 AGENTS.md + CLAUDE.md 重写为薄壳",
            "改完后用 Edit 把 AGENTS.md §八 Wiki Spec 版本行改为 to_version",
            "不写 log 条目（迁移是脚本运行，不是 wiki 操作事件）",
            "不调 ingest / query / lint——保持职责单一",
            # 0.18.0+ fixtures：
            "fixtures_actions[] 与 actions[] 平行处理——先走 fixtures_actions 修约定文件（如 .gitignore / anchor TOML）",
            "再走 actions[] 修内容页 frontmatter / log；fixtures 修复是后续内容页编辑的前置",
            "fixtures-fix-anchor-merge / -anchor-schema / -anchor-symlink-matches 三条都是『多文件迁移』型 action——必须按 to_action 5 步走，单 Edit 不能完成",
            "fixtures-fix-strip-frontmatter 仅删首部 frontmatter 块，保留全文正文一字不动",
            "fixtures-fix-skeleton（0.20.0+）：按 expected 补缺失骨架字段（frontmatter 键 / H1 / 说明块 / 段标题 / .gitignore 段），单 Edit 可落；成长型内容（index 类别 / log 历史 / MEMORY 经验 / tag bullet）不动",
            "fixtures-fix-agents-md-resync（0.26.0+）：AGENTS.md 全量重渲染——§八 变量保留旧值（Wiki Spec 版本行用 to_version），旧文件多出的定制行/段逐条与用户裁定搬 MEMORY/ 或丢弃；其余以模板渲染稿为准，不做局部 Edit",
            "fixtures 改造与 lint-checklist §五『语义合并规则』配合读——结构性合规由 fixtures-fix-* 完成，跨条目语义合并由 LLM 按 §五判断",
        ],
    }  # type: Dict[str, object]
    return plan


def cmd_check_version(wiki_root: Path, apply: bool, json_mode: bool) -> int:
    """--check-version 子命令主入口。

    - 解析 AGENTS.md（老 wiki fallback CLAUDE.md）§八 wiki_spec_version
    - 探测已知 legacy 现场
    - 默认打印人读报告（不写文件）
    - --json 输出机器可读 JSON
    - --apply 把 migration plan 以 JSON 输出到 stdout（agent 修复路径的依据；不落盘）
    """
    current_spec = parse_spec_version(wiki_root)
    comparison = _compare_semver(current_spec, CURRENT_WIKI_SPEC)
    legacy = detect_legacy_patterns(wiki_root)

    # 数 legacy pattern 总数（不算 conflicts，因为 conflicts 不进 plan）
    total_patterns = 0
    for entries in legacy["patterns"].values():  # type: ignore
        total_patterns += len(entries)  # type: ignore
    needs_migration = (comparison == "older") or (total_patterns > 0)

    # 0.18.0+ 调一次 fixtures-check——子进程调 scripts/check_wiki_fixtures.py；
    # 输出并入 report["fixtures_check"]。脚本跑挂时 fixtures_check 含 skipped=True，标识"未跑"。
    fixtures_check = _run_fixtures_check(wiki_root)
    if not fixtures_check.get("skipped"):
        # 有 findings 时也可触发 needs_migration（fixture 不合规也算"待迁移"）
        f_sum = fixtures_check.get("summary", {})  # type: ignore
        if f_sum.get("error", 0) > 0 or f_sum.get("warn", 0) > 0:  # type: ignore
            needs_migration = True

    report = {
        "current_spec": current_spec,
        "skill_spec": CURRENT_WIKI_SPEC,
        "comparison": comparison,
        "needs_migration": needs_migration,
        "legacy_patterns": legacy["patterns"],  # type: ignore
        "conflicts": legacy["conflicts"],  # type: ignore
        "fixtures_check": fixtures_check,  # 0.18.0+ 新增；fixtures 结构化校验结果
    }

    if json_mode:
        # JSON 模式：输出 report；apply 时再附 plan
        if apply:
            plan = build_migration_plan(wiki_root, current_spec, legacy, fixtures_check)
            report["migration_plan"] = plan
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    # 人读模式
    print("=== Wiki Spec 版本检查 ===")
    print(f"  current_spec : {current_spec or '(解析失败)'}")
    print(f"  skill_spec   : {CURRENT_WIKI_SPEC}")
    print(f"  comparison   : {comparison}")
    print(f"  needs_migration: {needs_migration}")
    print()

    # 当前版本比 SKILL 新 → 告警，不阻断
    if comparison == "newer":
        print(f"[WARN] wiki 用比 SKILL 更新的 spec（{current_spec} > {CURRENT_WIKI_SPEC}）")
        print("       请升级 SKILL 仓；本子命令不会修改 wiki")
        print()
        _print_fixtures_check(fixtures_check, indent="")
        return 0

    # 解析失败 → 提示用户填 CLAUDE.md §八
    if current_spec is None:
        print("[WARN] 无法解析 <wiki-root>/AGENTS.md（老 wiki CLAUDE.md）§八 'Wiki Spec 版本'")
        print("       请确认该行存在且格式为: | Wiki Spec 版本 | 0.x.y |")
        print("       解析失败不影响 legacy pattern 探测（下方继续输出）")
        print()

    # legacy pattern 列表
    legacy_empty = total_patterns == 0 and not legacy["conflicts"]  # type: ignore
    fixtures_skipped = bool(fixtures_check.get("skipped"))
    fixtures_empty = fixtures_skipped or not any(
        c.get("passed") is False
        for c in fixtures_check.get("checks", [])  # type: ignore
    )
    if legacy_empty and fixtures_empty:
        print("No legacy patterns / fixtures issues found. ✓")
        return 0

    if not legacy_empty:
        print(f"[LEGACY] 共 {total_patterns} 处老格式现场")
        for pattern_key, entries in legacy["patterns"].items():  # type: ignore
            if not entries:  # type: ignore
                continue
            rule_ref = LEGACY_PATTERN_KEYS.get(pattern_key, "?")
            print(f"  - {pattern_key} ({len(entries)}) → {rule_ref}")
            for entry in entries:  # type: ignore
                flag = " [CONFLICT]" if entry.get("conflict") else ""  # type: ignore
                print(f"      {entry['file']}{flag}")  # type: ignore

        if legacy["conflicts"]:  # type: ignore
            print()
            print(f"[CONFLICTS] {len(legacy['conflicts'])} 处冲突页——agent 不自动覆盖")  # type: ignore
            for c in legacy["conflicts"]:  # type: ignore
                print(f"  - {c['file']}: {c['reason']}")  # type: ignore

    # fixtures-check 段（0.18.0+）
    _print_fixtures_check(fixtures_check, indent="")

    # apply 时把 migration plan 以 JSON 输出到 stdout（agent 直接消费；不落盘，升级无中间文件残留）
    if apply:
        plan = build_migration_plan(wiki_root, current_spec, legacy, fixtures_check)
        print("\n[PLAN] migration plan 已生成（stdout JSON 输出，agent 直接消费，不落盘）")
        print(
            f"       actions: {len(plan['actions'])}, skipped_conflicts: {len(plan['skipped_conflicts'])}, "  # type: ignore
            f"fixtures_actions: {len(plan.get('fixtures_actions', []))}"  # type: ignore
        )
        print("       agent 按 plan.actions[] + plan.fixtures_actions[] 走 Edit/Write 修复（规则见 plan.rule_doc）")
        print("--- migration-plan JSON begin ---")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        print("--- migration-plan JSON end ---")
    else:
        print()
        print("[HINT] 加 --apply 输出 migration plan（stdout JSON）供 agent 走 Edit/Write 修复（默认 dry-run）")
        print("       加 --json  输出机器可读 JSON")

    return 0


def _print_fixtures_check(fixtures_check: Dict[str, object], indent: str = "") -> None:
    """人读模式打印 fixtures-check 段。被 cmd_check_version 调用。
    跑挂时只一行 skip 提示；其余按 fixture summary 打印。
    """
    if fixtures_check.get("skipped"):
        print(f"{indent}[FIXTURES] skipped: {fixtures_check.get('reason', '(unknown)')}")
        return
    checks = fixtures_check.get("checks", [])  # type: ignore
    summary = fixtures_check.get("summary", {})  # type: ignore
    print(
        f"{indent}[FIXTURES] error={summary.get('error', 0)} "  # type: ignore
        f"warn={summary.get('warn', 0)} "  # type: ignore
        f"pass={summary.get('pass', 0)} "  # type: ignore
        f"skip={summary.get('skip', 0)}"  # type: ignore
    )
    failed = [c for c in checks if c.get("passed") is False]  # type: ignore
    if not failed:
        return
    print(f"{indent}  - failed:")
    for c in failed:
        sev = str(c.get("severity", "")).upper()  # type: ignore
        cid = c.get("id", "")  # type: ignore
        fpath = c.get("file", "")  # type: ignore
        rr = c.get("rule_ref", "")  # type: ignore
        print(f"{indent}      [{sev}] {cid} ({fpath})")
        if c.get("expected"):  # type: ignore
            print(f"{indent}          期望: {c['expected']}")  # type: ignore
        if c.get("actual"):  # type: ignore
            print(f"{indent}          实际: {c['actual']}")  # type: ignore
        if rr:
            print(f"{indent}          rule: {rr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic health check for a local LLM wiki.")
    parser.add_argument("wiki_root", nargs="?", help="wiki 根目录；默认从 $LLM_WIKI_ROOT 读")
    parser.add_argument(
        "--severity", choices=["error", "warn", "info", "all"], default="all", help="过滤输出严重性（默认 all）"
    )
    parser.add_argument("--no-git", action="store_true", help="跳过 raw/ 的 git status 检查")
    parser.add_argument(
        "--migrate-confidence",
        action="store_true",
        help="一次性迁移老 confidence 字段到新 reviewed + reviewed_at（互斥模式，不做常规 lint）。已被 --check-version --apply 覆盖；保留仅供旧用法兼容。",
    )
    parser.add_argument(
        "--check-version",
        action="store_true",
        help="扫描 wiki 的 spec 版本（CLAUDE.md §八）与已知 legacy 老格式现场；默认 dry-run。加 --apply 输出 migration plan（stdout JSON，不落盘），加 --json 输出机器可读 JSON。互斥模式。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="与 --check-version 联用：输出机器可读 JSON 而不是人读报告",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="与 --check-version 联用：把 migration plan 以 JSON 输出到 stdout 供 agent 修复（不落盘）",
    )
    args = parser.parse_args()

    # `--no-git` 与"自动检测"叠加：传了 `--no-git` 就完全不检测；不传时
    # 脚本自动按 `.git/` 存在与否决定跑 / 跳。两种路径都允许，不强制用户
    # 必须装 git 或必须 init 仓——保留"裸目录树 wiki 默认支持"立场。
    effective_use_git = not args.no_git

    if args.wiki_root:
        wiki_root = Path(args.wiki_root).expanduser().resolve()
    elif os.environ.get("LLM_WIKI_ROOT"):
        wiki_root = Path(os.environ["LLM_WIKI_ROOT"]).expanduser().resolve()
    else:
        print("ERROR: 需提供 wiki_root 参数或设置 $LLM_WIKI_ROOT", file=sys.stderr)
        return 2

    if not (wiki_root / "wiki").is_dir():
        print(f"ERROR: {wiki_root}/wiki 不存在（wiki 还没 setup？）", file=sys.stderr)
        return 2

    # --migrate-confidence 是互斥模式：跑迁移，不跑常规 lint
    if args.migrate_confidence:
        return migrate_confidence(wiki_root)

    # --check-version 是互斥模式：跑版本扫描，不跑常规 lint
    if args.check_version:
        return cmd_check_version(wiki_root, apply=args.apply, json_mode=args.json)

    # 跑所有检查
    all_findings = []  # type: List[str]
    info_notes = []  # type: List[str]  # 不计入 severity 过滤的"说明性输出"（如 raw-immutable 跳过原因）
    # 版本一致性优先报——落后/领先 SKILL 时提示走 --check-version 升级流程
    all_findings.extend(check_spec_version(wiki_root))
    raw_findings, raw_skip = check_raw_immutable(wiki_root, effective_use_git)
    all_findings.extend(raw_findings)
    if raw_skip:
        info_notes.append(raw_skip)
    all_findings.extend(check_frontmatter(wiki_root))
    all_findings.extend(check_link_integrity(wiki_root))
    all_findings.extend(check_index_coverage(wiki_root))
    all_findings.extend(check_log_format(wiki_root))
    all_findings.extend(check_log_truncation(wiki_root))
    all_findings.extend(check_stale_summaries(wiki_root))
    all_findings.extend(check_filename_kebab(wiki_root))
    all_findings.extend(check_duplicate_titles(wiki_root))
    all_findings.extend(check_tag_taxonomy(wiki_root))
    all_findings.extend(check_external_symlinks(wiki_root))
    all_findings.extend(check_page_size(wiki_root))
    all_findings.extend(check_quality_signals(wiki_root))
    all_findings.extend(check_memory_index(wiki_root))
    # check_inlined_memory_index_size(wiki_root) — 0.23.0- 内联方案 bloat guard；0.24.0+ 已删
    all_findings.extend(check_related_links(wiki_root))

    # 过滤
    if args.severity != "all":
        threshold = SEV_RANK[args.severity]
        all_findings = [f for f in all_findings if SEV_RANK[severity_of(f)] <= threshold]

    # 输出：跳过提示（INFO 级别但不受 --severity 过滤；让用户始终能看到）
    if info_notes:
        print("\n[NOTES]")
        for n in info_notes:
            print(f"  {n}")

    # 输出
    if not all_findings:
        print("No issues found. ✓")
        return 0

    # 按严重性分组
    by_sev = {"error": [], "warn": [], "info": []}  # type: Dict[str, List[str]]
    for f in all_findings:
        by_sev[severity_of(f)].append(f)

    for sev in ("error", "warn", "info"):
        if by_sev[sev]:
            print(f"\n[{sev.upper()}] ({len(by_sev[sev])})")
            for f in by_sev[sev]:
                print(f"  {f}")

    print()
    print(f"Total: {len(all_findings)} finding(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
