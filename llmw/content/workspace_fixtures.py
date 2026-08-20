#!/usr/bin/env python3
"""workspace_fixtures — workspace fixtures 一致性检查（升级时专用；CLI 入口 `llmw check-fixtures`）

从 fixture 视角校验一个已存在 workspace 的
"约定文件"（AGENTS.md / CLAUDE.md / .gitignore / MEMORY/MEMORY.md / workspace.toml
templates_version）是否满足当前 workspace spec 的结构要求。本模块只校验**结构性字节合规**；
修复由 agent 按报告里的 fix 动作走 SKILL.md §6 Upgrade 工作流——本模块不写任何文件。

用法:
  llmw check-fixtures --workspace=<WORKSPACE_ROOT> [--json] [--target-spec <semver>]

缺省 --target-spec 时读 llmw.WORKSPACE_SPEC_VERSION（包内常量；SKILL.md 前端的版本 SSOT 由 CI gate 比对）。
standalone（不依赖其他脚本 / 第三方库；Python 3.7+）。

退出码:
  0 = 全部 check pass（或仅 warn / skip）
  1 = 至少一条 error 级 check fail
  2 = 运行错误（路径 / 参数 / 文件 IO）

设计权衡:
- 不落 .migration-plan.json——workspace 修复面恒定 ≤ 4 个结构文件，报告即清单；
  中断后重跑本脚本即可续（检测幂等）。零中间产物。
- AGENTS.md / CLAUDE.md 走**模板渲染比对**：从 §六「当前配置」表提取 4 变量（老格式
  fallback H1 + §六 散文行），渲染 references/workspace-*-template.md 后字节比对——
  一次性覆盖"旧版本残留 + 本地改动"全部漂移。定制纪律应沉淀到 MEMORY/，不进 AGENTS.md。
- 版本新旧（agents-version-is-current）与正文同步（agents-md-template-sync）正交：
  后者渲染时用 workspace 自钉版本替换 {{WORKSPACE_SPEC_VERSION}}。
- workspace.toml 的 wiki_spec 分量只展示不比对（跨 skill 指针：该跑各 wiki 的 upgrade
  由 yzr-llm-wiki-management 负责，本脚本不读兄弟 skill 的版本）。
"""

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from llmw import WORKSPACE_SPEC_VERSION
from llmw import __version__ as CLI_VERSION
from llmw.config import workspace_templates_dir
from llmw.content.render import render_workspace_agents_md, render_workspace_claude_md

ENV_WORKSPACE_ROOT = "LLMW_WORKSPACE"

SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
CREATED_AT_TOML_RE = re.compile(r'^\s*created_at\s*=\s*"([^"]+)"', re.MULTILINE)

# §六「当前配置」表行（机读版本钉死）
WS_NAME_ROW_RE = re.compile(r"^\|\s*Workspace 名\s*\|\s*(.+?)\s*\|\s*$")
SETUP_DATE_ROW_RE = re.compile(r"^\|\s*创建日期\s*\|\s*(.+?)\s*\|\s*$")
SPEC_VERSION_ROW_RE = re.compile(r"^\|\s*Workspace Spec 版本\s*\|\s*(.+?)\s*\|\s*$")
CLI_VERSION_ROW_RE = re.compile(r"^\|\s*CLI 版本\s*\|\s*(.+?)\s*\|\s*$")
# fallback：H1 `# <名> Workspace — LLM 维护守则` + 0.7.0- 老 §六 散文行
H1_NAME_RE = re.compile(r"^#\s+(.+?)\s+Workspace\s+—\s+LLM 维护守则\s*$")
LEGACY_ROW_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|.*llmw v([0-9.]+)\s*/\s*workspace-spec v([0-9.]+).*\|\s*$")

# -- 公开 check 注册表（顺序 = 输出顺序）--
CHECK_REGISTRY = [
    {
        "id": "agents-version-is-current",
        "severity": "error",
        "file": "AGENTS.md",
        "rule_ref": "repo AGENTS.md §当前配置 + upgrade 引擎",
        "desc": "AGENTS.md §六 Workspace Spec 版本行需与 --target-spec 一致",
    },
    {
        "id": "agents-md-template-sync",
        "severity": "error",
        "file": "AGENTS.md",
        "rule_ref": "llmw/content/upgrade.py 升级引擎",
        "desc": "AGENTS.md 与包内 workspace-agents-md-template.md 渲染稿字节一致（§六 四变量替换后）；定制纪律应沉淀到 MEMORY/",
    },
    {
        "id": "claude-md-template-sync",
        "severity": "error",
        "file": "CLAUDE.md",
        "rule_ref": "repo AGENTS.md 模板重渲染 + upgrade 引擎",
        "desc": "CLAUDE.md 薄壳与包内 workspace-claude-md-template.md 渲染稿字节一致（仅 {{WORKSPACE_DISPLAY_NAME}} 替换）",
    },
    {
        "id": "gitignore-skeleton",
        "severity": "error",
        "file": ".gitignore",
        "rule_ref": ".gitignore fixture + llmw/workspace/gitignore.py",
        "desc": ".gitignore 段结构齐全：llmw 托管块（标记 + 3 规则）+ OS/编辑器 + Obsidian + 临时文件段各 ≥1 规则（容忍段内删规则）",
    },
    {
        "id": "memory-index-skeleton",
        "severity": "error",
        "file": "MEMORY/MEMORY.md",
        "rule_ref": "MEMORY 产物契约（yzr-llm-workspace-management SKILL.md 附录 A6）+ upgrade 引擎",
        "desc": "MEMORY/MEMORY.md 无 frontmatter + 含 H1 / 说明块 / ## 索引（成长条目不动；缺失文件按 fixtures/memory-index.txt 重建）",
    },
    {
        "id": "workspace-toml-templates-version-sync",
        "severity": "warn",
        "file": "workspace.toml",
        "rule_ref": "repo AGENTS.md §当前配置",
        "desc": "workspace.toml templates_version 的 workspace_spec 分量与 target 一致（不阻断；wiki_spec 分量只展示不比对）",
    },
    {
        "id": "workspace-toml-reads-satisfied",
        "severity": "error",
        "file": "workspace.toml",
        "rule_ref": "workspace-toml-reads-satisfied（读取契约 check）",
        "desc": "workspace.toml 含 SKILL scan/upgrade 读取的字段：templates_version + 每个 [wikis.<name>] 的 path / created_at",
    },
    {
        "id": "template-no-outbound-refs",
        "severity": "error",
        "file": "workspace-agents-md-template.md",
        "rule_ref": "repo AGENTS.md 模板 + check-fixtures 探测",
        "desc": "workspace-agents-md-template.md 不含任何指向 skill 目录的出边引用（workspace-claude-md-template.md / SKILL.md / references/ / skill 名 / 阿拉伯数字 §节号；零白名单）",
    },
]


def _read_text(path: Path) -> Optional[str]:
    """读文件文本；失败返 None（不抛异常；fixture-check 静默容错）。"""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _skill_spec_version() -> Optional[str]:
    """workspace spec 版本（SSOT = llmw.WORKSPACE_SPEC_VERSION 包内常量）。"""
    return WORKSPACE_SPEC_VERSION


def _compare_semver(a: Optional[str], b: Optional[str]) -> str:
    """返 'equal' / 'older' / 'newer' / 'unknown'。"""
    if not a or not b:
        return "unknown"

    def parse(v: str) -> Optional[Tuple[int, int, int]]:
        m = SEMVER_RE.search(v)
        if not m:
            return None
        try:
            return tuple(int(x) for x in m.group(0).split("."))  # type: ignore
        except ValueError:
            return None

    av, bv = parse(a), parse(b)
    if not av or not bv:
        return "unknown"
    if av < bv:
        return "older"
    if av > bv:
        return "newer"
    return "equal"


def _extract_row(text: str, row_re: "re.Pattern[str]") -> Optional[str]:
    """从表格提取某字段行单元格；未命中返 None。"""
    for line in text.splitlines():
        m = row_re.match(line)
        if m:
            return m.group(1).strip()
    return None


def _extract_template_vars(agents_text: str) -> Dict[str, Optional[str]]:
    """提取模板渲染 4 变量：§六 表优先；老格式 fallback H1（名）+ §六 散文行（日期 / CLI / spec）。"""
    legacy_date = legacy_cli = legacy_spec = None  # type: Optional[str]
    for line in agents_text.splitlines():
        m = LEGACY_ROW_RE.match(line)
        if m:
            legacy_date, legacy_cli, legacy_spec = m.group(1), m.group(2), m.group(3)
            break
    name = _extract_row(agents_text, WS_NAME_ROW_RE)
    if name is None:
        h1 = next((ln for ln in agents_text.splitlines() if ln.startswith("# ")), "")
        h1m = H1_NAME_RE.match(h1)
        if h1m:
            name = h1m.group(1).strip()
    spec_cell = _extract_row(agents_text, SPEC_VERSION_ROW_RE)
    spec_semver = SEMVER_RE.search(spec_cell) if spec_cell else None
    return {
        "name": name,
        "date": _extract_row(agents_text, SETUP_DATE_ROW_RE) or legacy_date,
        "cli": _extract_row(agents_text, CLI_VERSION_ROW_RE) or legacy_cli,
        "spec": spec_semver.group(0) if spec_semver else legacy_spec,
    }


def _render_agents_template(template: str, vars: Dict[str, Optional[str]], spec: str) -> str:
    return (
        template.replace("{{WORKSPACE_DISPLAY_NAME}}", vars["name"] or "")
        .replace("{{SETUP_DATE}}", vars["date"] or "")
        .replace("{{WORKSPACE_SPEC_VERSION}}", spec)
        .replace("{{CLI_VERSION}}", vars["cli"] or "")
    )


def _agents_reference() -> Tuple[Optional[str], Path]:
    """读包内 workspace-agents-md-template.md。"""
    tpl_path = workspace_templates_dir() / "workspace-agents-md-template.md"
    return _read_text(tpl_path), tpl_path


def check_agents_version_is_current(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#1: AGENTS.md §六 Workspace Spec 版本行与 target_spec 一致（新旧判定）。

    与 template-sync 正交：只管版本新旧，不管正文同步。0.7.0- 老格式无表 → fallback
    §六 散文行含旧版 `llmw vX / workspace-spec vY` 格式时提取
    """
    out = {"passed": True, "severity": "error", "file": "AGENTS.md"}  # type: Dict[str, object]
    text = _read_text(ws_root / "AGENTS.md")
    if text is None:
        out["passed"] = None
        out["skipped"] = "AGENTS.md 不存在"
        return out
    target = info.get("target_spec")
    found = _extract_template_vars(text)["spec"]
    if found is None:
        out["passed"] = False  # type: ignore
        out["comparison"] = "unknown"
        out["actual"] = "无法解析 §六 Workspace Spec 版本行（含老 §六 散文行 fallback）"
        out["expected"] = target or "(未指定 target)"
        out["fix"] = {
            "type": "workspace-fix-agents-md-resync",
            "to_action": "按 SKILL.md §6 全量重渲染 AGENTS.md（agent 人工提取 4 变量；版本行解析失败时单字段 Edit 不可信）",
        }
        return out
    cmp = _compare_semver(found, target)
    if cmp != "equal":
        out["passed"] = False  # type: ignore
        out["comparison"] = cmp
        out["actual"] = found
        out["expected"] = target
        note = (
            "更新本 skill 安装后再迁移"
            if cmp == "newer"
            else "若 agents-md-template-sync 同报 drift，改走 resync 全量重渲染一并覆盖"
        )
        out["fix"] = {
            "type": "workspace-fix-agents-version",
            "to_action": f"Edit AGENTS.md §六 表：`Workspace Spec 版本` 行改为 {target}（{note}）",
        }
    return out


def check_agents_md_template_sync(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#2: AGENTS.md 与 render.py 渲染稿字节一致。

    设计文档 §7.2: 渲染输入尽量从 workspace.toml + 版本常量派生; **display_name 例外**——
    workspace.toml 没有该字段（init 时只写到 AGENTS.md），仍需从 AGENTS.md §六 表
    （或 H1 fallback）提取。其它 3 变量均 SSOT 派生，模板措辞改后本 check 自动跟随。

    与 check#1 的关系: 本 check 直接用 CURRENT spec 版本渲染, 旧 workspace 必然字节差
    → 也会 drift。**冗余 benign**: 两者都推荐 upgrade, 一次修复。check#1 仅做 currency
    信息报告 + 老格式 fallback。
    """
    out = {"passed": True, "severity": "error", "file": "AGENTS.md"}  # type: Dict[str, object]
    ws_text = _read_text(ws_root / "AGENTS.md")
    if ws_text is None:
        out["passed"] = None
        out["skipped"] = "AGENTS.md 不存在"
        return out

    # Variable 1 (例外): display_name 从 AGENTS.md §六 / H1 提取（ws.toml 没存）
    display_name = _extract_row(ws_text, WS_NAME_ROW_RE)
    if display_name is None:
        h1 = next((ln for ln in ws_text.splitlines() if ln.startswith("# ")), "")
        h1m = H1_NAME_RE.match(h1)
        if h1m:
            display_name = h1m.group(1).strip()
    if not display_name:
        out["passed"] = False  # type: ignore
        out["expected"] = (
            "AGENTS.md §六 Workspace 名 / H1 可解析为 display_name（ws.toml 不存该字段，"
            "本 check 必须从此提取；模板变量 SSOT 见设计文档 §7.2）"
        )
        out["actual"] = "Workspace 名提取失败——走 workspace-fix-agents-md-resync"
        out["fix"] = {
            "type": "workspace-fix-agents-md-resync",
            "to_action": (
                "人工确认 display_name 后按 llmw.content.render 全量重渲染 AGENTS.md；"
                "本地定制逐条与用户裁定搬 MEMORY/ 或丢弃"
            ),
        }
        return out

    # Variable 2 (SSOT): workspace.toml.created_at → setup_date
    ws_toml_text = _read_text(ws_root / "workspace.toml")
    if ws_toml_text is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "workspace.toml 不存在, 无法派生 setup_date"
        return out
    cm = CREATED_AT_TOML_RE.search(ws_toml_text)
    if cm is None:
        out["passed"] = None  # type: ignore
        out["skipped"] = "workspace.toml 缺 created_at, 无法派生 setup_date"
        return out
    setup_date = cm.group(1)[:10]

    # Variables 3+4 (SSOT): 版本常量
    rendered = render_workspace_agents_md(
        display_name=display_name,
        setup_date=setup_date,
        cli_version=CLI_VERSION,
        spec_version=WORKSPACE_SPEC_VERSION,
    )

    if rendered != ws_text:
        diff = list(difflib.unified_diff(ws_text.splitlines(), rendered.splitlines(), lineterm="", n=0))
        changed = [ln for ln in diff if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
        preview = "; ".join(ln[:60] for ln in changed[:4])
        out["passed"] = False  # type: ignore
        out["expected"] = "AGENTS.md 与 llmw.content.render 渲染稿字节一致（定制纪律沉淀到 MEMORY/，不进本文件）"
        out["actual"] = f"{len(changed)} 行与渲染稿不一致（首处: {preview}）" if preview else "与渲染稿不一致"
        out["fix"] = {
            "type": "workspace-fix-agents-md-resync",
            "to_action": (
                f"按 llmw.content.render.render_workspace_agents_md 全量重渲染 AGENTS.md（display_name={display_name}）→ "
                "diff 旧文件，多出的本地定制逐条与用户裁定搬 MEMORY/ 或丢弃 → Write 覆盖"
            ),
        }
    return out


def check_claude_md_template_sync(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#3: CLAUDE.md 薄壳与 render.py 渲染稿字节一致。

    薄壳唯一变量是 {{WORKSPACE_DISPLAY_NAME}}；workspace.toml 没存 display_name,
    仍需从 AGENTS.md §六 表 / H1 提取。
    """
    out = {"passed": True, "severity": "error", "file": "CLAUDE.md"}  # type: Dict[str, object]
    tpl_path = workspace_templates_dir() / "workspace-claude-md-template.md"
    if not tpl_path.is_file():
        out["passed"] = None
        out["skipped"] = f"{tpl_path} 未找到（无法模板比对）"
        return out
    agents_text = _read_text(ws_root / "AGENTS.md")
    display_name = None
    if agents_text is not None:
        display_name = _extract_row(agents_text, WS_NAME_ROW_RE)
        if display_name is None:
            h1 = next((ln for ln in agents_text.splitlines() if ln.startswith("# ")), "")
            h1m = H1_NAME_RE.match(h1)
            if h1m:
                display_name = h1m.group(1).strip()
    if not display_name:
        out["passed"] = None
        out["skipped"] = "AGENTS.md 缺失或 Workspace 名不可解析（无法渲染薄壳比对）"
        return out

    rendered = render_workspace_claude_md(display_name=display_name)

    ws_text = _read_text(ws_root / "CLAUDE.md")
    if ws_text is None:
        out["passed"] = False  # type: ignore
        out["expected"] = "CLAUDE.md 薄壳存在（@AGENTS.md + 声明）"
        out["actual"] = "CLAUDE.md 不存在"
        out["fix"] = {
            "type": "workspace-fix-claude-md-create",
            "to_action": f"按 llmw.content.render.render_workspace_claude_md(display_name={display_name}) 渲染创建 CLAUDE.md",
        }
        return out
    if rendered != ws_text:
        out["passed"] = False  # type: ignore
        out["expected"] = "CLAUDE.md 与 llmw.content.render 渲染稿字节一致（不含纪律正文；版本在 AGENTS.md §六）"
        out["actual"] = "与薄壳模板渲染稿不一致"
        out["fix"] = {
            "type": "workspace-fix-claude-md-resync",
            "to_action": f"按 llmw.content.render.render_workspace_claude_md(display_name={display_name}) 渲染 Write 覆盖 CLAUDE.md",
        }
    return out


# .gitignore 骨架：llmw 托管块标记 + 块内 3 必填规则；3 个段头各需 ≥1 规则（段内删规则容忍）
GITIGNORE_LLMW_START_RE = re.compile(r"^#\s*>>>\s*llmw")
GITIGNORE_LLMW_END_RE = re.compile(r"^#\s*<<<\s*llmw")
GITIGNORE_LLMW_REQUIRED_RULES = ("workspace_models.toml", "**/.claude/settings*.json", "**/.qoder/settings*.json")
GITIGNORE_SECTIONS = ("# OS / 编辑器", "# Obsidian 配置", "# 临时文件")


def check_gitignore_skeleton(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#4: .gitignore 段结构齐全（llmw 托管块 3 规则 + 3 段各 ≥1 规则）。

    只查结构不绑死具体规则行——容忍用户删段内单条规则（如纯 Linux 删 .DS_Store）；
    但 llmw 托管块 3 条敏感文件规则缺一不可（0.5.0/0.6.0/0.6.1 连续加固的对象）。
    """
    out = {"passed": True, "severity": "error", "file": ".gitignore"}  # type: Dict[str, object]
    text = _read_text(ws_root / ".gitignore")
    if text is None:
        out["passed"] = False  # type: ignore
        out["expected"] = ".gitignore 含 llmw 托管块 + OS/编辑器 + Obsidian + 临时文件段"
        out["actual"] = ".gitignore 不存在"
        out["fix"] = {
            "type": "workspace-fix-gitignore-skeleton",
            "to_action": "按 llmw/workspace/gitignore.py 的 GITIGNORE_MANAGED_BLOCK 常量逐字创建",
        }
        return out

    lines = text.splitlines()
    missing = []  # type: List[str]

    # llmw 托管块：标记 + 块内 3 规则
    start = next((i for i, ln in enumerate(lines) if GITIGNORE_LLMW_START_RE.match(ln)), None)
    end = next((i for i, ln in enumerate(lines) if GITIGNORE_LLMW_END_RE.match(ln)), None)
    if start is None or end is None or end <= start:
        missing.append("llmw 托管块标记（`# >>> llmw ... >>>` / `# <<< llmw <<<`）")
        block_rules = set()  # type: set
    else:
        block_rules = {ln.strip() for ln in lines[start + 1 : end] if ln.strip() and not ln.strip().startswith("#")}
    for rule in GITIGNORE_LLMW_REQUIRED_RULES:
        if rule not in block_rules:
            missing.append(f"llmw 托管块规则 `{rule}`")

    # 3 段：段头存在 + 段内 ≥1 规则（到下一段头 / EOF 计）
    header_idx = {}
    for i, ln in enumerate(lines):
        for sec in GITIGNORE_SECTIONS:
            if ln.startswith(sec) and sec not in header_idx:
                header_idx[sec] = i
    for sec in GITIGNORE_SECTIONS:
        if sec not in header_idx:
            missing.append(f"段 `{sec.lstrip('# ')}`")
            continue
        nxt = min(
            [header_idx[s] for s in GITIGNORE_SECTIONS if s in header_idx and header_idx[s] > header_idx[sec]]
            + [len(lines)]
        )
        rules = [ln for ln in lines[header_idx[sec] + 1 : nxt] if ln.strip() and not ln.strip().startswith("#")]
        if not rules:
            missing.append(f"段 `{sec.lstrip('# ')}` 内 ≥1 规则")

    if missing:
        out["passed"] = False  # type: ignore
        out["expected"] = "llmw 托管块（标记 + 3 规则）+ OS/编辑器 + Obsidian 配置 + 临时文件 段各 ≥1 规则"
        out["actual"] = "缺：" + "；".join(missing)
        out["fix"] = {
            "type": "workspace-fix-gitignore-skeleton",
            "to_action": "按 llmw/workspace/gitignore.py 的 GITIGNORE_MANAGED_BLOCK 常量单 Edit 补 .gitignore 缺失段 / 规则（不动用户自定义规则）",
        }
    return out


def check_memory_index_skeleton(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#5: MEMORY/MEMORY.md 骨架（无 frontmatter + H1 + 说明块 + ## 索引）。

    成长内容（## 索引 下的经验条目）不动；文件缺失按包内 fixtures/memory-index.txt 重建。
    """
    out = {"passed": True, "severity": "error", "file": "MEMORY/MEMORY.md"}  # type: Dict[str, object]
    text = _read_text(ws_root / "MEMORY" / "MEMORY.md")
    if text is None:
        out["passed"] = False  # type: ignore
        out["expected"] = "MEMORY/MEMORY.md 存在（无 frontmatter + H1 + 说明块 + ## 索引）"
        out["actual"] = "MEMORY/MEMORY.md 不存在"
        out["fix"] = {
            "type": "workspace-fix-memory-index-init",
            "to_action": "按包内 fixtures/memory-index.txt 逐字创建 MEMORY/MEMORY.md",
        }
        return out

    missing = []  # type: List[str]
    if text.lstrip().startswith("---"):
        missing.append("首部 YAML frontmatter 块（索引文件应无 frontmatter）")
    if not any(ln.startswith("# ") for ln in text.splitlines()):
        missing.append("H1")
    if not any(ln.startswith(">") for ln in text.splitlines()):
        missing.append("说明块（`>` 引用）")
    if not any(ln.strip() == "## 索引" for ln in text.splitlines()):
        missing.append("`## 索引` 段")

    if missing:
        out["passed"] = False  # type: ignore
        out["expected"] = "无 frontmatter + H1 + 说明块 + ## 索引（成长条目不动）"
        out["actual"] = "缺 / 多出：" + "；".join(missing)
        out["fix"] = {
            "type": "workspace-fix-memory-index-skeleton",
            "to_action": "单 Edit 修 MEMORY/MEMORY.md 骨架（删 frontmatter / 补 H1 / 说明块 / ## 索引；不动 ## 索引 下成长条目）",
        }
    return out


TEMPLATES_VERSION_RE = re.compile(r'^[ \t]*templates_version[ \t]*=[ \t]*"([^"]*)"', re.MULTILINE)
TV_WORKSPACE_SPEC_RE = re.compile(r"workspace_spec\s*=\s*([0-9]+\.[0-9]+\.[0-9]+)")
TV_WIKI_SPEC_RE = re.compile(r"wiki_spec\s*=\s*([0-9]+\.[0-9]+\.[0-9]+)")


def check_workspace_toml_templates_version(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#6: workspace.toml templates_version 的 workspace_spec 分量与 target 一致（warn）。

    不阻断（spec §14：旧 spec 产物仍可读）。wiki_spec 分量只展示不比对——跨 skill
    指针，提示用户跑各 wiki 的 upgrade（yzr-llm-wiki-management），本脚本不读兄弟 skill 版本。
    """
    out = {"passed": True, "severity": "warn", "file": "workspace.toml"}  # type: Dict[str, object]
    text = _read_text(ws_root / "workspace.toml")
    if text is None:
        out["passed"] = None
        out["skipped"] = "workspace.toml 不存在（CLI 未 init？）"
        return out
    m = TEMPLATES_VERSION_RE.search(text)
    if m:
        wiki_m = TV_WIKI_SPEC_RE.search(m.group(1))
        if wiki_m:
            out["wiki_spec"] = wiki_m.group(1)
    found = None
    if m:
        spec_m = TV_WORKSPACE_SPEC_RE.search(m.group(1))
        if spec_m:
            found = spec_m.group(1)
    if found is None:
        out["passed"] = False  # type: ignore
        out["comparison"] = "unknown"
        out["actual"] = "templates_version 缺失或 workspace_spec 分量不可解析"
        out["expected"] = (
            f'templates_version = "workspace_spec = {info.get("target_spec") or "<target>"}; wiki_spec = ..."'
        )
        out["fix"] = {
            "type": "workspace-fix-templates-version",
            "to_action": f"upgrade 收尾 Edit workspace.toml：templates_version 的 workspace_spec 分量改为 {info.get('target_spec') or '<target>'}（单字段，其余不动）",
        }
        return out
    cmp = _compare_semver(found, info.get("target_spec"))
    if cmp != "equal":
        out["passed"] = False  # type: ignore
        out["comparison"] = cmp
        out["actual"] = found
        out["expected"] = info.get("target_spec")
        out["fix"] = {
            "type": "workspace-fix-templates-version",
            "to_action": f"upgrade 收尾 Edit workspace.toml：templates_version 的 workspace_spec 分量改为 {info.get('target_spec') or '<target>'}（单字段，其余不动）",
        }
    return out


TEMPLATES_VERSION_KEY_RE = re.compile(r"^[ \t]*templates_version[ \t]*=", re.MULTILINE)
WIKIS_SECTION_RE = re.compile(r"^\[wikis\.([^\]]+)\]\s*$", re.MULTILINE)
NEXT_SECTION_RE = re.compile(r"^\[", re.MULTILINE)


def check_workspace_toml_reads_satisfied(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """check#7: workspace.toml 含 SKILL scan/upgrade 读取的字段（读取契约自洽）。

    校验顶层 templates_version + 每个 [wikis.<name>] 的 path / created_at（SKILL scan
    遍历 + INDEX 排序用）。workspace.toml 不存在 → skip（复用 templates-version-sync
    的 skip 语义，不重复报）。minimal TOML 风格：只认 key = 行 + [section] 头，不引入 tomli。

    读取契约 co-location：本 check 校验的字段 = SKILL scan/upgrade 实际读取的字段。若 SKILL
    将来新读 workspace.toml 某字段，必须同步加到这里 + yzr-llm-workspace-management SKILL.md 附录 A1「读取契约」
    表——两处（本 check / spec §2）一致，gate 才有效（清单漂移 = check 不报警 = gate 失效）。
    """
    out = {"passed": True, "severity": "error", "file": "workspace.toml"}  # type: Dict[str, object]
    text = _read_text(ws_root / "workspace.toml")
    if text is None:
        out["passed"] = None
        out["skipped"] = "workspace.toml 不存在（CLI 未 init？）"
        return out
    missing = []  # type: List[str]
    if not TEMPLATES_VERSION_KEY_RE.search(text):
        missing.append("templates_version（顶层）")
    for sm in WIKIS_SECTION_RE.finditer(text):
        wiki_name = sm.group(1)
        body_start = sm.end()
        nxt = NEXT_SECTION_RE.search(text, body_start)
        body = text[body_start : nxt.start()] if nxt else text[body_start:]
        for field in ("path", "created_at"):
            if not re.search(rf"^[ \t]*{field}[ \t]*=", body, re.MULTILINE):
                missing.append(f"[wikis.{wiki_name}].{field}")
    if missing:
        out["passed"] = False  # type: ignore
        out["expected"] = "workspace.toml 含 SKILL 读取字段：templates_version + 每个 [wikis].path/created_at"
        out["actual"] = "缺：" + "；".join(missing)
    return out


# 模板零出边引用（架构不变量：纪律正文唯一维护点 = 模板，模板是引用图汇点）。
# 任何指向 skill 目录文件 / 阿拉伯数字 §节号的引用都会被本 check 报 error——workspace 侧
# agent 读不到 skill 目录、解析不了这些指针（模板自己都写着"模板与配套工具随 skill 分发，不在本 workspace 内"），
# 对运行时读者是死指针；改纪律只改模板对应段，spec / SKILL.md 单向指入模板。
TEMPLATE_OUTBOUND_PATTERNS = (
    "workspace-spec.md",  # 文件已删除，保留禁令防历史引用回渗
    "workspace-claude-md-template.md",
    "SKILL.md",
    "references/",
    "yzr-llm-workspace-management",
    "yzr-llm-wiki-management",
)
TEMPLATE_OUTBOUND_SECTION_RE = re.compile(r"§[0-9]")


def _scan_template_outbound_refs(text):
    """扫模板文本中的出边引用，返回 ["<行号>:<模式>", ...]（空 = 干净）。

    独立成函数便于测试——检测逻辑直接喂合成文本；check 函数做文件 IO + 报告。
    """
    hits = []  # type: List[str]
    for ln_no, ln in enumerate(text.splitlines(), 1):
        for pat in TEMPLATE_OUTBOUND_PATTERNS:
            if pat in ln:
                hits.append(f"{ln_no}:{pat}")
        if TEMPLATE_OUTBOUND_SECTION_RE.search(ln):
            hits.append(f"{ln_no}:§节号引用")
    return hits


def check_template_no_outbound_refs(ws_root: Path, info: Dict[str, str]) -> Dict[str, object]:
    """包内 workspace-agents-md-template.md 不含任何指向 skill 目录的出边引用。

    模板随 init 拷贝进 workspace 成为 AGENTS.md——workspace 侧 agent 读不到 skill 目录，模板内
    一切 `workspace-claude-md-template.md` / `SKILL.md` /
    `references/` / skill 名 / 阿拉伯数字 §节号 引用都是死指针（零白名单，含 provenance
    声明也不得携带——全部改写为自包含措辞）。skill 目录内文件 → 模板 单向引用由本
    check 机械强制；对每个 workspace 报告同一结果（模板是全局文件），违反时 error 逼
    skill 侧修复。
    """
    out = {"passed": True, "severity": "error", "file": "workspace-agents-md-template.md"}  # type: Dict[str, object]
    template = _read_text(workspace_templates_dir() / "workspace-agents-md-template.md")
    if template is None:
        out["passed"] = None
        out["skipped"] = "workspace-agents-md-template.md 未找到（无法模板自检）"
        return out
    hits = _scan_template_outbound_refs(template)
    if hits:
        out["passed"] = False
        out["expected"] = "模板不含任何指向 skill 目录的引用（自包含措辞；spec / SKILL.md 单向指入模板）"
        out["actual"] = "出边引用: " + "; ".join(hits[:8])
    return out


# (check_id, 函数) 映射——顺序同 CHECK_REGISTRY
CHECK_FUNCS = [
    ("agents-version-is-current", check_agents_version_is_current),
    ("agents-md-template-sync", check_agents_md_template_sync),
    ("claude-md-template-sync", check_claude_md_template_sync),
    ("gitignore-skeleton", check_gitignore_skeleton),
    ("memory-index-skeleton", check_memory_index_skeleton),
    ("workspace-toml-templates-version-sync", check_workspace_toml_templates_version),
    ("workspace-toml-reads-satisfied", check_workspace_toml_reads_satisfied),
    ("template-no-outbound-refs", check_template_no_outbound_refs),
]


def run_checks(ws_root: Path, target_spec: Optional[str]) -> Dict[str, object]:
    info = {"target_spec": target_spec or ""}
    summary = {"error": 0, "warn": 0, "info": 0, "pass": 0, "skip": 0}  # type: Dict[str, int]
    checks_out = []  # type: List[Dict[str, object]]
    func_map = dict(CHECK_FUNCS)
    for reg in CHECK_REGISTRY:
        cid = reg["id"]
        result = func_map[cid](ws_root, info)
        passed = result.get("passed")
        severity = reg["severity"]
        if passed is True:
            summary["pass"] += 1
        elif passed is False:
            summary[severity] = summary.get(severity, 0) + 1
        else:
            summary["skip"] += 1
        checks_out.append(
            {
                "id": cid,
                "file": result.get("file", ""),
                "passed": passed,
                "severity": severity,
                "rule_ref": reg["rule_ref"],
                "desc": reg["desc"],
                "expected": result.get("expected", ""),
                "actual": result.get("actual", ""),
                "skipped": result.get("skipped", ""),
                "comparison": result.get("comparison", ""),
                "fix": result.get("fix", {}),
                "wiki_spec": result.get("wiki_spec", ""),
            }
        )
    return {
        "workspace_root": str(ws_root),
        "target_spec": target_spec,
        "checks": checks_out,
        "summary": summary,
    }


def _format_human(report: Dict[str, object]) -> str:
    """人读报告（默认输出）。"""
    lines = []  # type: List[str]
    lines.append("=== Workspace fixtures 一致性检查 ===")
    lines.append(f"  workspace_root: {report['workspace_root']}")
    lines.append(f"  target_spec   : {report['target_spec'] or '(未指定)'}")
    s = report["summary"]  # type: ignore
    lines.append(f"  error={s['error']} warn={s['warn']} info={s['info']} pass={s['pass']} skip={s['skip']}")  # type: ignore
    lines.append("")
    for c in report["checks"]:  # type: ignore
        passed = c.get("passed")
        sev = str(c["severity"]).upper()
        if passed is True:
            tag = "✓"
        elif passed is False:
            tag = "✗"
        else:
            tag = "·"
        lines.append(f"[{tag}] [{sev}] {c['id']} ({c['file']})")
        if c.get("rule_ref"):
            lines.append(f"        规则: {c['rule_ref']}")
        if passed is False:
            if c.get("expected"):
                lines.append(f"        期望: {c['expected']}")
            if c.get("actual"):
                lines.append(f"        实际: {c['actual']}")
            fix = c.get("fix") or {}
            if fix.get("type"):
                lines.append(f"        修复: [{fix['type']}] {fix.get('to_action', '')}")
        elif passed is None and c.get("skipped"):
            lines.append(f"        skip: {c['skipped']}")
    return "\n".join(lines)


def _format_rules_md() -> str:
    """--list-rules markdown 输出。"""
    lines = []  # type: List[str]
    lines.append("## Workspace fixtures 规则清单")
    lines.append("")
    lines.append("| ID | Severity | File | 规则引用 | 说明 |")
    lines.append("|---|---|---|---|---|")
    for reg in CHECK_REGISTRY:
        rid = reg["id"]
        sev = reg["severity"]
        ft = reg.get("file", "")
        rr = reg["rule_ref"]
        desc = reg["desc"]
        lines.append(f"| `{rid}` | {sev} | `{ft}` | {rr} | {desc} |")
    return "\n".join(lines)


def _rules_json() -> List[Dict[str, object]]:
    """--list-rules JSON 输出。"""
    return [
        {
            "id": reg["id"],
            "severity": reg["severity"],
            "file": reg.get("file", ""),
            "rule_ref": reg["rule_ref"],
            "desc": reg["desc"],
        }
        for reg in CHECK_REGISTRY
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_workspace_fixtures",
        description="检查已存在 workspace 的 fixtures 一致性（升级检查专用）",
    )
    parser.add_argument("workspace_root", nargs="?", help="workspace 根目录；默认从 $LLMW_WORKSPACE 读")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON 而不是人读报告")
    parser.add_argument(
        "--target-spec",
        default=None,
        help="目标 workspace spec 版本（缺省读 llmw.WORKSPACE_SPEC_VERSION 包内常量）",
    )
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="内省：输出 CHECK_REGISTRY 规则清单（不扫描文件，无需 workspace_root）",
    )
    args = parser.parse_args(argv)

    if args.list_rules:
        if args.json:
            print(json.dumps(_rules_json(), indent=2, ensure_ascii=False))
        else:
            print(_format_rules_md())
        return 0

    if args.workspace_root:
        ws_root = Path(args.workspace_root).expanduser().resolve()
    elif os.environ.get(ENV_WORKSPACE_ROOT):
        ws_root = Path(os.environ[ENV_WORKSPACE_ROOT]).expanduser().resolve()
    else:
        print("ERROR: 需提供 workspace_root 参数或设置 $LLMW_WORKSPACE", file=sys.stderr)
        return 2

    if not ws_root.is_dir():
        print(f"ERROR: {ws_root} 不是目录", file=sys.stderr)
        return 2

    target_spec = args.target_spec or _skill_spec_version()

    report = run_checks(ws_root, target_spec)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_human(report))

    # 退出码：仅 error 级 fail 置 1（warn / skip 不阻断）
    s = report["summary"]  # type: ignore
    if s["error"] > 0:  # type: ignore
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
