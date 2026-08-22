#!/usr/bin/env python3
"""
wiki_lint — deterministic 健康检查（llmw wiki lint）

跑 references/lint-checklist.md 的 §二（deterministic 全部项）+ external symlink 检查。
半定性检查（§三，矛盾主张 / 缺失交叉引用等需理解语义的）由 agent 现场做。

用法：
  llmw wiki lint --name=X | --path=DIR [--severity <LEVEL>] [--no-git]
  llmw wiki lint --name=X | --path=DIR --check-version [--json] [--apply]

--severity 过滤：error | warn | info | all（默认 all）
--no-git 跳过 raw/ 的 git status 检查（CI 或裸仓场景）。默认**自动检测**：
  仅当 wiki 根目录在 git 仓内且 raw/ 被 git 跟踪时才跑 raw 不可变性检查；
  裸目录树 / 无 git / raw 未纳入 git → 自动跳过并打印提示（不报错，不阻断）。
--check-version 扫描当前 wiki 的 format 版本（解析 AGENTS.md 末尾「当前配置」表 `Wiki Format 版本` 字段），
  与本 skill metadata.wiki_format_version 比对，列出老格式 legacy 现场。默认仅打印报告
   （不动任何文件）；加 `--apply` 把 upgrade plan 以 JSON 输出到 **stdout**（agent 直接
   消费，**不落盘**——升级全程 wiki 根无任何中间文件残留）供按 references/upgrade-workflow.md
   用 Edit/Write 修复；加 `--json` 输出机器可读 JSON。互斥模式。

退出码：
- 0 = 全部指定严重性级别内无 finding / --check-version 报告完成（无论是否需迁移）
- 1 = 有 finding（仅常规 lint 模式）
- 2 = 运行错误
"""

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

# 复用 ingest_diff 的轻量 frontmatter 解析 + log_format 的日期解析 helper
from llmw.content._check_common import (  # noqa: E402
    SEMVER_RE,
)
from llmw.content._check_common import (
    compare_semver as _compare_semver,
)
from llmw.content.ingest_diff import parse_frontmatter_simple  # noqa: E402
from llmw.content.log_format import (  # noqa: E402
    LOG_LINE_RE,
    parse_date_or_datetime,
)

# fixtures 一致性检查——`--check-version` 自动调一次；结果并入
# report["fixtures_check"] + plan["fixtures_actions"]（直接函数调用，非子进程）。

VALID_TYPES = {
    "entity",
    "concept",
    "source",
    "comparison",
    "synthesis",
    # MEMORY 扩展类型（page-templates.md §一：`或新的 memory 类型按需扩展`）：
    # - `memory`：MEMORY/*.md 自用语义，与 wiki 5 类内容页区分
    # - `memory-entry`：MEMORY 经验条目标识（与 `memory` 同属 MEMORY 桶）
    "memory",
    "memory-entry",
}
# reviewed 字段仅在值为严格 `true` 时合法；缺省 / 其它值（含 "true" 字符串、yes、1、false）判非法
WIKI_SUBDIRS = ("entities", "concepts", "sources", "comparisons", "syntheses")
MEMORY_SUBDIR = "MEMORY"
# raw/external 与 source 命名共用同一 kebab-case 正则——SSOT 在 llmw.content.external_anchor（CLI
# anchor 写路径持有该正则与子目录/文件名常量；lint 仅消费）。
from llmw.content.external_anchor import (  # noqa: E402
    ANCHOR_FILENAME,
    EXTERNAL_SUBDIR,
    SOURCE_NAME_RE,
)
from llmw.content.external_anchor import load as load_anchor  # noqa: E402

DISCUSSIONS_SUBDIR = "discussions"  # raw/ 下用户 + LLM 协作草稿层；与 external/ 并列的 raw/ 写权限例外
MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
EXTERNAL_URL_RE = re.compile(r"^(https?:|mailto:|//)")

# 代码区剔除：Markdown 语义上 fenced block / 行内 code span 里的 [..](..) 不是链接
# （渲染器不 linkify），裸文本扫 MD_LINK_RE 会误报——三处 finditer 调用点统一先剔除。
# 替换为等长空白：保行号 / 偏移稳定（如需按 finditer 偏移回溯原文不受影响）。
_CODE_FENCE_RE = re.compile(r"^(?P<fence>```|~~~)[^\n]*\n.*?^(?P=fence)[^\n]*$", re.M | re.S)
_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")


def strip_code_regions(text: str) -> str:
    """剔 fenced code block 与行内 code span（等长空白替换），返回处理后的文本。"""
    text = _CODE_FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return _CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


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


# Wiki format 当前版本——SSOT 是 SKILL.md metadata.wiki_format_version（frontmatter），
# 经 llmw/__init__ 单源读取，不再维护常量副本（单仓后漂移源消失）。
# 详见 MEMORY/format-version-bump-single-repo.md。
from llmw import WIKI_FORMAT_VERSION  # noqa: E402

CURRENT_WIKI_FORMAT = WIKI_FORMAT_VERSION

# 已知 legacy pattern 的"pattern key"——为后续扩展预留，每个 key 是一类迁移动作。
# rule_ref 是迁移依据的溯源指针；修复语义自含于 plan actions 的 remove/add_or_modify/to_action
# 字段 + references/upgrade-workflow.md §六（语义合并规则）——不另设历史档案。
LEGACY_PATTERN_KEYS = {
    # 历史迁移 pattern（confidence-field / claudemd-tag-section / claudemd-not-thinshell）
    # 已于 2026-08 随"场景清零"退役删除；未来退役字段时按需注册新 key。
    # 拦 wiki 5 类内容页误用 reserved `type: memory`（MEMORY/*.md 上 type: memory /
    # memory-entry 合法，仅内容页误用才触发本规则）。
    "type-memory-value": "page-templates.md §一",
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
    # MEMORY/ 单独扫：与 wiki/ 平级、位于 <wiki-root>/MEMORY/（不在 wiki/ 下）
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
    # raw/discussions/ 是用户 + LLM 协作的草稿层，双方可写——
    # 其未提交改动不属于"raw 被违规改"，从 raw-modified 信号中排除（与 §13 raw/external/
    # 并列为本 skill 的两处 raw/ 写权限例外）。external/ 的 symlink 本身被 .gitignore
    # 排除，不会出现在 git status 里，故此处只需过滤 discussions/。
    discussions_prefix = "raw/" + DISCUSSIONS_SUBDIR + "/"
    # rename 两侧都可能涉及 discussions/（§15.3 archive mv 跨边界：discussions/ → articles/），
    # 任一路径命中即排除，避免合法归档误报 raw-modified
    lines = [ln for ln in lines if not any(p.startswith(discussions_prefix) for p in _git_porcelain_paths(ln))]
    if not lines:
        return ([], "")
    findings = [f"raw-modified: raw/ 有 {len(lines)} 处未提交改动：{lines[0]}{' ...' if len(lines) > 1 else ''}"]
    return (findings, "")


def check_external_symlinks(wiki_root: Path) -> List[str]:
    """10. raw/external/ 下 symlink 的健康检查（扁平 + TOML anchor）

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
                f"{sorted(symlink_names)} 但缺 '{ANCHOR_FILENAME}'（必填）"
            )
        return findings
    entries = load_anchor(anchor_path)
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
            findings.append(f"external-anchor-orphan: {rel} 是 symlink 但 anchor 无对应 [[entry]]（必填关联）")
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
                f"但 raw/external/{sl_name} symlink 不存在（必填关联）"
            )

    return findings


def check_frontmatter(wiki_root: Path) -> List[str]:
    """2. frontmatter 完整性 + 3. source/synthesis 的 sources 字段

    校验口径分两类（vs §9）：
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
                                    f"raw/external/<source-name>/...），与 lint-checklist.md §二.3 一致"
                                )
                                continue
                            # raw/discussions/ 禁止作 source——
                            # discussions/ 是用户 + LLM 双方可写的协作草稿层，不是"用户掌控的
                            # 真相源"；放开口子 = provenance 后门（LLM 自产内容被当 raw 真相
                            # ingest 回 wiki）。要引用其内容先 mv 到 raw/articles 等正式子树走标准
                            # ingest。命中后 continue 跳过后续 external / missing——
                            # 同一根因不重复报错。
                            if s.startswith("raw/" + DISCUSSIONS_SUBDIR + "/"):
                                findings.append(
                                    f"source-in-discussions: {rel} sources='{s}' 指向 "
                                    f"raw/{DISCUSSIONS_SUBDIR}/——discussions/ 是协作草稿层"
                                    f"，不可作 source 真相源；先 mv 到 raw/articles "
                                    f"等正式子树再 ingest"
                                )
                                continue
                            # 0.17+ raw/external/<symlink>/... 例外：
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
        for m in MD_LINK_RE.finditer(strip_code_regions(text)):
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
    for m in MD_LINK_RE.finditer(strip_code_regions(index_text)):
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
    body = _strip_frontmatter_body(text)
    for i, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        if line.startswith("## "):
            if not LOG_LINE_RE.match(line):
                findings.append(
                    f"log-format: wiki/log.md 第 {i} 行格式不合规：'{line[:60]}{'...' if len(line) > 60 else ''}'"
                )
    return findings


# log.md 滚动窗口上限——超过则建议截断保最近 N 条
LOG_RETENTION_LIMIT = 50

# source 页 stale 摘要阈值（days）——`updated` 距今超过此值报 stale-summary（详见 lint-checklist.md §二.7）
STALE_SUMMARY_DAYS = 90


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
    body = _strip_frontmatter_body(text)
    entry_count = sum(1 for line in body.splitlines() if LOG_LINE_RE.match(line))
    if entry_count > LOG_RETENTION_LIMIT:
        findings.append(
            f"log-truncation-recommended: wiki/log.md 含 {entry_count} 条目，超过 {LOG_RETENTION_LIMIT} "
            f"滚动窗口上限；建议截断保最近 {LOG_RETENTION_LIMIT} 条"
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
TAXONOMY_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
TAG_KV_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Tag taxonomy 主流位置：wiki/tags.md，无 frontmatter，纯裸 bullet 列表。
TAG_FILE_PRIMARY = "wiki/tags.md"


def _parse_tag_bullets(text: str) -> Set[str]:
    """从裸 bullet 文本里提取 kebab-case tag 集合

    解析规则（来源：wiki/tags.md 全文）：
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


def parse_tag_taxonomy(wiki_root: Path) -> Set[str]:
    """读 tag 白名单，返回允许 tag 集合

    来源：`<wiki_root>/wiki/tags.md`（LLM 拥有、按需扩展）。

    解析失败 / 文件不存在 / 解析出 0 个 tag → 返回空集合（调用方应静默跳过，
    避免新 setup 的 wiki 必报错）。
    """
    primary = wiki_root / TAG_FILE_PRIMARY
    if primary.is_file():
        text = primary.read_text(encoding="utf-8", errors="replace")
        return _parse_tag_bullets(text)
    return set()


def check_tag_taxonomy(wiki_root: Path) -> List[str]:
    """11. tag 是否在 taxonomy 白名单内

    来源：`wiki/tags.md`。找不到或解析出 0 个 tag → 静默跳过
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
    # MEMORY/*.md 不进 tag 白名单校验——MEMORY 是 agent 私有记忆（AGENTS.md 模板 §五）：
    # MEMORY 私有 tag（lint / external-repo / symlink 等）是 LLM 工作上下文分类，
    # 不应跟 wiki 用户面共享 taxonomy（tag 白名单是防 wiki 索引/过滤漂移）。
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
                findings.append(f"tag-not-in-taxonomy: {rel} tags 含 '{t}' 不在 wiki/tags.md 白名单")
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
    agent 私有定位（正文无长度上限）。计非空行（纯空行不计），避免空行撑大计数。
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
                    f"建议拆成子主题页 + cross-link（page-templates.md「Page Thresholds」）"
                )
    return findings


def check_quality_signals(wiki_root):
    """13. 可信度与认知质量信号——reviewed / contested / contradictions

    deterministic 子检查（字段全部可选；省略 = 不评，lint 不报）：

    A. 可信度信号 reviewed：
    - pending-review（info）：非 log/index 页未含 reviewed: true——新常态，仅提示
    - reviewed-stale（warn）：reviewed: true 存在但 updated > reviewed_at——LLM 修改后漏清戳
    - invalid-reviewed-value（warn）：reviewed 取值非严格 true（如 "true" 字符串、yes、1、false）
    - reviewed-at-missing（warn）：reviewed: true 存在但缺 reviewed_at
    - reviewed-at-orphan（warn）：reviewed_at 存在但缺 reviewed: true

    B. 认知质量信号 contested / contradictions：
    - contested-page（warn）：contested: true 的页——含未解决矛盾
    - contradiction-target-missing（warn）：contradictions 指向不存在的页
    - contradiction-asymmetric（warn）：A 把 B 列入 contradictions 但 B 未反向标注 A
      （字段语义要求双向标注，见 page-templates.md §一）

    C. index.md 标识漂移：
    - index-review-badge-drift（warn）：wiki/index.md 上的 ✓/✗ 标识与被链页 frontmatter 不一致

    字段语义见 page-templates.md §一「可选：可信度与认知质量信号」。
    只把作者已写 / 已渲染的信号拎出来；判定"某页是否真的经过认真审核"是半定性工作。
    """
    findings = []  # type: List[str]
    pages = find_md_files(wiki_root)
    target_pages = []  # type: List[Path]
    for sub in WIKI_SUBDIRS:
        target_pages.extend(pages[sub])
    # MEMORY/*.md 不进 reviewed 校验——MEMORY 与 wiki 内容页的 frontmatter 规则解耦：
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
    `@MEMORY/MEMORY.md` `@import` 自动加载全文。
    本检查只扫 `MEMORY.md ## 索引` 段对 `MEMORY/*.md` 的覆盖——0.23.0 短暂的双轨
    （MEMORY.md + AGENTS.md「本 wiki 的边界」节内联段并集）已废，单一真源下不再需要双处同步。

    不走 wiki/index.md 强制入口；但每条经验条目需在 `MEMORY.md` 列一行，否则
    下次 `@import` 加载后该 agent 视角下 MEMORY 沦为死库。

    反向（索引列了某 `<slug>.md` 但文件不存在）也在此检查：`memory-index-dangling`
    warn——索引行指向不存在的文件 = 索引与磁盘脱节（MEMORY 纪律"不删除条目"被违反
    或文件被误移），下次会话按索引读必落空。注意只能靠链接判定：短条目
    （`- 一句话事实`）无链接、不算 dangling。

    MEMORY.md 不存在时静默跳过（不报错）。
    severity = info（轻量索引非强制入口，类比 tag-not-in-taxonomy）。

    短条目（与 wiki skill SKILL.md §4 Memory 同步）：MEMORY.md 索引行可无对应 .md 文件
    （`- 一句话事实` 格式），不进本检查范围——只兜底"有 .md 但未索引"。

    路径变更：MEMORY/ 从 wiki/ 下移到 <wiki-root>/MEMORY/（与 wiki/ 平级）。
    """
    findings = []  # type: List[str]
    mem_dir = wiki_root / MEMORY_SUBDIR  # 移到 wiki 根下；老 wiki 走 --check-version --apply
    memory_index = mem_dir / "MEMORY.md"
    if not memory_index.is_file():
        return findings
    # 单一真源：只扫 MEMORY.md 索引（`@import` 已自动加载全文）；任一条 `<slug>.md`
    # 未列入 MEMORY.md 索引即报 `memory-not-indexed` info。
    indexed = set()  # type: Set[str]
    mem_dir_resolved = mem_dir.resolve()
    # 单一真源：MEMORY.md `## 索引` 段对 MEMORY/*.md 的覆盖即可
    # （AGENTS.md 不再持有副本，`@import` 透明加载——无需双轨兜底）。
    try:
        text = memory_index.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for m in MD_LINK_RE.finditer(strip_code_regions(text)):
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
    """15. related / compared 路径引用完整性

    校验 wiki 内容页 frontmatter 的 `related`（concept 页）与 `compared`
    （comparison 页）字段——按 page-templates.md §一「路径格式约定」解析为**内容根 `wiki/`
    相对**（`concepts/X.md` → `<wiki>/wiki/concepts/X.md`），文件不存在则报
    `related-broken-link` warn。注意基准陷阱：`wiki_root` 是最外层 `<wiki>/`
    （其下才是 `wiki/` 内容根），故解析须补 `wiki/` 段——与 source 页 `sources`
    字段走最外层 `raw/` 基准（见 check_frontmatter）刻意区分。

    路径格式约定（类型特化字段）：**内容根 `wiki/` 相对路径**（如
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
                # related / compared 是内容根 wiki/ 相对（按 page-templates.md §一）（concepts/X.md），
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
    if finding.startswith(("wiki-format-version-stale", "wiki-format-version-ahead", "wiki-format-version-unparsed")):
        return "warn"
    return "info"


# ---------------------------------------------------------------------------
# --check-version：扫描 wiki 的 format 版本 + 老格式 legacy 现场
# 职责：纯探测（不动 wiki 内容）；agent 拿到 plan 后按 references/upgrade-workflow.md 走 Edit/Write 修复。
# ---------------------------------------------------------------------------

# AGENTS.md 末尾「当前配置」表格式版本行匹配：
# | Wiki Format 版本 | 0.7.0 |
# 兼容用户编辑后的格式变体（多余空格、备注尾部等）；semver 走单独正则抓取。
CLAUDE_FORMAT_ROW_RE = re.compile(r"^\s*\|\s*Wiki Format 版本\s*\|\s*([^|]+?)\s*\|")


def parse_format_version(wiki_root: Path) -> Optional[str]:
    """从 wiki 纪律 SSOT §七 表里抽 "Wiki Format 版本"。

    SSOT 是 <wiki-root>/AGENTS.md（薄壳 CLAUDE.md 不持版本）。系统只理解当前格式——
    AGENTS.md 缺失或 §七 行无法解析 = 版本未知，由 wiki-format-version-unparsed 报。

    返回 semver 字符串（如 "0.11.0"）；找不到或解析失败返回 None。

    设计权衡：仅解析 §七 表的"Wiki Format 版本"行，不扫描全文（避免误抓正文里出现的
    版本号）。用户编辑表格时若格式被破坏（例如把"Wiki Format 版本"改成"Wiki 版本"），
    解析失败——提示用户人工填回，而不是猜。
    """
    md_file = wiki_root / "AGENTS.md"
    if not md_file.is_file():
        return None
    try:
        text = md_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = CLAUDE_FORMAT_ROW_RE.match(line)
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


def check_format_version(wiki_root: Path) -> List[str]:
    """常规 lint 也查 wiki 版本与 SKILL（CURRENT_WIKI_FORMAT）是否一致；不一致提示走升级流程。

    与 cmd_check_version 复用同一 parse_format_version + _compare_semver，但本函数只产
    warn finding 提示（不产 plan——plan 由 --check-version --apply 落）。让用户日常
    lint 时就能感知「wiki 版本落后/领先 SKILL」，而不必显式跑 --check-version 才发现。
    """
    findings = []  # type: List[str]
    current = parse_format_version(wiki_root)
    if current is None:
        findings.append(
            "wiki-format-version-unparsed: AGENTS.md 末尾「当前配置」表 `Wiki Format 版本` 行无法解析"
            "（缺 AGENTS.md 或表格格式破坏）——"
            "跑 `lint_wiki.py --check-version` 诊断"
        )
        return findings
    cmp = _compare_semver(current, CURRENT_WIKI_FORMAT)
    if cmp == "older":
        findings.append(
            f"wiki-format-version-stale: AGENTS.md 末尾「当前配置」表 format {current} 落后 SKILL {CURRENT_WIKI_FORMAT}——"
            "跑 `lint_wiki.py --check-version --apply` 走升级流程"
        )
    elif cmp == "newer":
        findings.append(
            f"wiki-format-version-ahead: AGENTS.md 末尾「当前配置」表 format {current} 领先 SKILL {CURRENT_WIKI_FORMAT}——"
            "更新本 skill 安装（lint_wiki.py）对齐"
        )
    # equal / unknown → 无 finding
    return findings


def _run_fixtures_check(wiki_root: Path) -> Dict[str, object]:
    """直接调 wiki_fixtures.run_checks（非子进程）；返其报告 dict。

    失败兜底：调用抛异常时返空 dict（不带 'checks' 字段）—— caller 据此判断
    「fixtures check 未跑」，不应阻 lint 主流程。
    """
    try:
        from llmw.content.wiki_fixtures import run_checks

        return run_checks(wiki_root, CURRENT_WIKI_FORMAT)
    except Exception as e:  # noqa: BLE001
        return {"skipped": True, "reason": f"fixtures check exec failed: {e}"}


def _has_type_memory(page_rel: str, text: str) -> bool:
    """检查 wiki 内容页是否误用保留的 `type: memory`。

    `type: memory` / `type: memory-entry` 仅 MEMORY 桶合法（page-templates.md §一——
    MEMORY frontmatter 解耦 + 扩展 `memory` / `memory-entry` 两类），wiki 内容页
    （entities/concepts/sources/comparisons/syntheses）出现 `type: memory` 是误用。

    Args:
        page_rel: 页面相对 wiki 根的 POSIX 路径（如 `wiki/sources/x.md` / `MEMORY/foo.md`）
        text: 页面全文

    Returns:
        True 当且仅当页面**不在** MEMORY/ 下且 frontmatter 含 `type: memory`
    """
    # MEMORY 桶合法值；本函数只扫内容页
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

    返回结构（供 build_upgrade_plan 与 --json 输出复用）：
    {
      "patterns": {
         # 仅 wiki 5 类内容页误用 reserved `type: memory` 触发；MEMORY/*.md 不进此列表
        "type-memory-value":    [{"file": "wiki/<entities|concepts|sources|comparisons|syntheses>/x.md", "conflict": False}],
      },
      "conflicts": [],
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

        if _has_type_memory(rel, text):
            out["patterns"]["type-memory-value"].append({"file": rel, "conflict": False})  # type: ignore

    return out


def build_upgrade_plan(
    wiki_root: Path,
    current_format: Optional[str],
    legacy: Dict[str, object],
    fixtures_check: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """把 detect_legacy_patterns 的发现 + fixtures-check 的发现组织成 agent 可执行的 plan。

    每个 action 含 file / type / rule_ref / 具体 remove & add_or_modify；
    agent 按 references/upgrade-workflow.md 引用 rule_ref 走 Edit/Write。
    fixtures-fix-* 类动作落进 `fixtures_actions[]`，与 legacy pattern 的 actions[] 平行——
    agent 走 plan 时两套都得跑（fixtures 修复优先于内容页 frontmatter 修复）。
    """
    today = date.today().isoformat()
    actions = []  # type: List[Dict[str, object]]
    fixtures_actions = []  # type: List[Dict[str, object]]

    # type-memory-value：wiki 5 类内容页误用 reserved `type: memory`（MEMORY 桶合法，内容页非法）
    for entry in legacy["patterns"]["type-memory-value"]:  # type: ignore
        fpath = entry["file"]  # type: ignore
        actions.append(
            {
                "file": fpath,
                "type": "frontmatter-retype",
                "rule_ref": LEGACY_PATTERN_KEYS["type-memory-value"],
                "remove": ["type"],
                # `memory-entry` 是 MEMORY 桶扩展值；内容页误用 `type: memory` 应改为对应 5 类之一（agent 按页面真实语义裁定）
                "add_or_modify": {"type": "memory-entry"},  # 占位默认——agent 改 plan 时按页面语义替换
                "note": "wiki 内容页误用 reserved `type: memory`（MEMORY 桶合法）。Agent 应按页面真实语义决定：改为对应 5 类（entity/concept/source/comparison/synthesis）之一；不要把 wiki 内容页改成 `memory-entry`（那是 MEMORY 桶的扩展值）。",
            }
        )

    # fixtures 一致性 → fixtures_actions[]
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
                            f"Edit {fpath} §七 Wiki Format 版本行单元格改为 `{expected}`（实际为 `{actual}`）——"
                            "参考 lint-checklist.md §一（--check-version 子命令段）"
                        ),
                    }
                )
            elif cid == "agents-md-template-sync":
                # 模板渲染比对失败 → 全量重渲染（不是单行 Edit）；本地定制按裁定搬 MEMORY/
                # 详见 llmw.content.upgrade.plan_resync + 仓库 AGENTS.md 骨架所有权四分表
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-agents-md-resync",
                        "to_action": (
                            "AGENTS.md 全量重渲染（模板同步机制，4 步）："
                            "(1) 从旧 AGENTS.md「当前配置」表提取 主题 / 创建日期 / CLI 版本（主题 fallback："
                            "H1 `# <主题> Wiki — LLM 维护守则`）；"
                            "(2) 渲染包内 agents-md-template.md——{{TOPIC_NAME}} / {{SETUP_DATE}} / "
                            "{{CLI_VERSION}} 用旧值，{{WIKI_FORMAT_VERSION}} 用 to_version；"
                            "(3) diff 旧文件 vs 渲染稿：旧文件**多出的行/段** = 本地定制，逐条列给用户裁定——"
                            "搬 MEMORY/（一行事实写 MEMORY/MEMORY.md 索引短条目；含 why 的建 "
                            "MEMORY/<slug>.md 完整条目 + 索引行）或丢弃；"
                            "(4) Write 渲染稿覆盖 AGENTS.md——成长内容仅 §七 四行变量，其余以模板为准"
                        ),
                    }
                )
            elif cid == "symlink-anchor-toml-schema":
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-anchor-schema",
                        "to_action": (
                            "raw/external/.symlink-anchor.toml 损坏：CLI add 拒绝覆盖损坏文件"
                            "（保护手工修复现场）——备份后删除，或手工改对 TOML，再用"
                            " `llmw wiki external add <target> --name=<n>` 重建 entries。"
                            "字段语义见 external-repo.md §一；schema SSOT = CLI `external_anchor._REQUIRED_FIELDS`。"
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
                            "在 MEMORY/MEMORY.md 索引追加缺失条目（fixture 头部说明块规则）："
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
                            f"补齐 {fpath} 缺类别：5 标题齐全（见 fixture 头部模板） "
                            "(Entities / Concepts / Sources / Comparisons / Syntheses)，顺序可调"
                        ),
                    }
                )
            elif cid.endswith(("-skeleton", "-frontmatter-complete", "-init-rules-complete")):
                # 骨架字段级比对 check（信号来自包内 fixtures/；
                # 新增 *-skeleton 类 check 自动匹配此分支）
                fixtures_actions.append(
                    {
                        **base,
                        "type": "fixtures-fix-skeleton",
                        "to_action": (
                            f"Edit {fpath}：按包内 fixtures/（gitignore 见 "
                            "fixtures/gitignore.txt）"
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
        "from_version": current_format,
        "to_version": CURRENT_WIKI_FORMAT,
        "skill_doc": "SKILL.md（yzr-llm-wiki-management skill 根）",
        "format_doc": "references/lint-checklist.md（yzr-llm-wiki-management skill，check 语义参考）",
        "rule_doc": "references/upgrade-workflow.md（yzr-llm-wiki-management skill）",
        "actions": actions,
        "fixtures_actions": fixtures_actions,
        "skipped_conflicts": legacy.get("conflicts", []),  # type: ignore
        "agent_rules": [
            "按 actions[] 顺序逐项修；每个 action 前打印依据 rule_ref",
            "frontmatter-rename：用 Edit 改 frontmatter（删老字段、加新字段；不动 updated）",
            "file-move：先读源 → 写目标 → 删源",
            "frontmatter-retype：按 action.note 与 page-templates.md §一决定具体改法",
            "skipped_conflicts[] 永远不自动覆盖——转人工",
            "改完后用 Edit 把 AGENTS.md 末尾「当前配置」表 `Wiki Format 版本` 行改为 to_version",
            "不写 log 条目（迁移是脚本运行，不是 wiki 操作事件）",
            "不调 ingest / query / lint——保持职责单一",
            # fixtures：
            "fixtures_actions[] 与 actions[] 平行处理——先走 fixtures_actions 修约定文件（如 .gitignore / anchor TOML）",
            "再走 actions[] 修内容页 frontmatter / log；fixtures 修复是后续内容页编辑的前置",
            "fixtures-fix-anchor-schema / -anchor-symlink-matches 各 to_action 自含修 schema / ln / 补 entry 的具体指令",
            "fixtures-fix-strip-frontmatter 仅删首部 frontmatter 块，保留全文正文一字不动",
            "fixtures-fix-skeleton：按 expected 补缺失骨架字段（frontmatter 键 / H1 / 说明块 / 段标题 / .gitignore 段），单 Edit 可落；成长型内容（index 类别 / log 历史 / MEMORY 经验 / tag bullet）不动",
            "fixtures-fix-agents-md-resync：AGENTS.md 全量重渲染——「当前配置」表变量保留旧值（Wiki Format 版本行用 to_version），旧文件多出的定制行/段逐条与用户裁定搬 MEMORY/ 或丢弃；其余以模板渲染稿为准，不做局部 Edit",
            "fixtures 改造与 lint-checklist.md §五『语义合并规则』配合读——结构性合规由 fixtures-fix-* 完成，跨条目语义合并由 LLM 按该节判断",
        ],
    }  # type: Dict[str, object]
    return plan


def cmd_check_version(wiki_root: Path, apply: bool, json_mode: bool) -> int:
    """--check-version 子命令主入口。

    - 解析 AGENTS.md 末尾「当前配置」表 wiki_format_version
    - 探测已知 legacy 现场
    - 默认打印人读报告（不写文件）
    - --json 输出机器可读 JSON
    - --apply 把 upgrade plan 以 JSON 输出到 stdout（agent 修复路径的依据；不落盘）
    """
    current_format = parse_format_version(wiki_root)
    comparison = _compare_semver(current_format, CURRENT_WIKI_FORMAT)
    legacy = detect_legacy_patterns(wiki_root)

    # 数 legacy pattern 总数（不算 conflicts，因为 conflicts 不进 plan）
    total_patterns = 0
    for entries in legacy["patterns"].values():  # type: ignore
        total_patterns += len(entries)  # type: ignore
    needs_upgrade = (comparison == "older") or (total_patterns > 0)

    # 调一次 fixtures-check——直接调 llmw.content 的 run_checks（同一进程）；
    # 输出并入 report["fixtures_check"]。调用失败时 fixtures_check 含 skipped=True，标识"未跑"。
    fixtures_check = _run_fixtures_check(wiki_root)
    if not fixtures_check.get("skipped"):
        # 有 findings 时也可触发 needs_upgrade（fixture 不合规也算"待迁移"）
        f_sum = fixtures_check.get("summary", {})  # type: ignore
        if f_sum.get("error", 0) > 0 or f_sum.get("warn", 0) > 0:  # type: ignore
            needs_upgrade = True

    report = {
        "current_format": current_format,
        "skill_format": CURRENT_WIKI_FORMAT,
        "comparison": comparison,
        "needs_upgrade": needs_upgrade,
        "legacy_patterns": legacy["patterns"],  # type: ignore
        "conflicts": legacy["conflicts"],  # type: ignore
        "fixtures_check": fixtures_check,  # fixtures 结构化校验结果
    }

    if json_mode:
        # JSON 模式：输出 report；apply 时再附 plan
        if apply:
            plan = build_upgrade_plan(wiki_root, current_format, legacy, fixtures_check)
            report["upgrade_plan"] = plan
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    # 人读模式
    print("=== Wiki Format 版本检查 ===")
    print(f"  current_format : {current_format or '(解析失败)'}")
    print(f"  skill_format   : {CURRENT_WIKI_FORMAT}")
    print(f"  comparison   : {comparison}")
    print(f"  needs_upgrade: {needs_upgrade}")
    print()

    # 当前版本比 SKILL 新 → 告警，不阻断
    if comparison == "newer":
        print(f"[WARN] wiki 用比 SKILL 更新的 format（{current_format} > {CURRENT_WIKI_FORMAT}）")
        print("       请更新本 skill 安装；本子命令不会修改 wiki")
        print()
        _print_fixtures_check(fixtures_check, indent="")
        return 0

    # 解析失败 → 提示用户填 AGENTS.md 末尾「当前配置」表
    if current_format is None:
        print("[WARN] 无法解析 <wiki-root>/AGENTS.md 末尾「当前配置」表 `Wiki Format 版本`")
        print("       请确认该行存在且格式为: | Wiki Format 版本 | 0.x.y |")
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

    # fixtures-check 段
    _print_fixtures_check(fixtures_check, indent="")

    # apply 时把 upgrade plan 以 JSON 输出到 stdout（agent 直接消费；不落盘，升级无中间文件残留）
    if apply:
        plan = build_upgrade_plan(wiki_root, current_format, legacy, fixtures_check)
        print("\n[PLAN] upgrade plan 已生成（stdout JSON 输出，agent 直接消费，不落盘）")
        print(
            f"       actions: {len(plan['actions'])}, skipped_conflicts: {len(plan['skipped_conflicts'])}, "  # type: ignore
            f"fixtures_actions: {len(plan.get('fixtures_actions', []))}"  # type: ignore
        )
        print("       agent 按 plan.actions[] + plan.fixtures_actions[] 走 Edit/Write 修复（规则见 plan.rule_doc）")
        print("--- upgrade-plan JSON begin ---")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        print("--- upgrade-plan JSON end ---")
    else:
        print()
        print("[HINT] 加 --apply 输出 upgrade plan（stdout JSON）供 agent 走 Edit/Write 修复（默认 dry-run）")
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


def run(
    wiki_root: Path,
    *,
    severity: str = "all",
    no_git: bool = False,
    check_version: bool = False,
    apply: bool = False,
    json_mode: bool = False,
) -> int:
    """lint 业务入口（cli.py dispatch 直调；flag SSOT 在 llmw.cli argparse 树）。

    no_git: 传 True 完全不检测 git；不传时按 `.git/` 存在与否自动决定
    （裸目录树 wiki 默认支持——不强制用户装 git 或 init 仓）。
    """
    if not (wiki_root / "wiki").is_dir():
        print(f"ERROR: {wiki_root}/wiki 不存在（wiki 还没 setup？）", file=sys.stderr)
        return 2

    effective_use_git = not no_git

    # --check-version 是互斥模式：跑版本扫描，不跑常规 lint
    if check_version:
        return cmd_check_version(wiki_root, apply=apply, json_mode=json_mode)

    # 跑所有检查
    all_findings = []  # type: List[str]
    info_notes = []  # type: List[str]  # 不计入 severity 过滤的"说明性输出"（如 raw-immutable 跳过原因）
    # 版本一致性优先报——落后/领先 SKILL 时提示走 --check-version 升级流程
    all_findings.extend(check_format_version(wiki_root))
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
    all_findings.extend(check_related_links(wiki_root))

    # 过滤
    if severity != "all":
        threshold = SEV_RANK[severity]
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
