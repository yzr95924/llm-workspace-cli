"""llmw.content.upgrade_workspace — workspace 骨架升级引擎

确定性执行 `llmw upgrade`（workspace 级）：重渲染 workspace 根的 byte-owned 文件
(AGENTS.md / CLAUDE.md)、managed block 重放 .gitignore、header-owned MEMORY.md 段嫁接、
自验 fixtures checker 0 error、版本钉 `templates_version` 的 workspace_format 分量 bump。

流程与 wiki 侧 (upgrade.py) 同构：

    idle → preflight（drift diff）→ resync → verifying → bump → done
                              ↘ blocked_drift（diff 非空 + 非 dry-run 无 --yes）
                              ↘ verifying fail → exit 2（版本钉不落）

3 终态 JSON 契约（--json 恒可用）：

    status: done | blocked_drift（workspace 侧恒无 residue）
    - done           : 4 类骨架处理 + 自检 0 error
    - blocked_drift  : 自定义内容将被覆盖，dry-run 输出 diff 停住

退出码：
    0 = done
    1 = blocked_drift
    2 = 自验证失败 / 内部错误

变量 SSOT: workspace.toml.created_at (setup_date) + llmw.WORKSPACE_FORMAT_VERSION（包内常量；SKILL.md 前端版本由 CI gate 与常量比对）
+ 版本常量；display_name 例外（workspace.toml 未存），仍需从现有 AGENTS.md「当前配置」表 / H1 提取。
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from llmw import WORKSPACE_FORMAT_VERSION
from llmw import __version__ as CLI_VERSION
from llmw.config import workspace_templates_dir
from llmw.content import render as _render
from llmw.content import upgrade as _wiki_upgrade
from llmw.content import workspace_fixtures
from llmw.content._check_common import read_text as _read_text  # noqa: E402
from llmw.fsutil import atomic_write
from llmw.workspace import store as ws_store
from llmw.workspace.gitignore import ensure_workspace_gitignore

# workspace 骨架 4 类文件
_BYTE_OWNED = ("AGENTS.md", "CLAUDE.md")
_BLOCK_OWNED = (".gitignore",)
_HEADER_OWNED = ("MEMORY/MEMORY.md",)

# templates_version 解析正则（保留 wiki_format 分量，只换 workspace_format；接受 legacy *_spec 形式）
_TV_PARSE = re.compile(
    r"(?:workspace_format|workspace_spec)\s*=\s*([0-9]+\.[0-9]+\.[0-9]+)\s*;\s*(?:wiki_format|wiki_spec)\s*=\s*([0-9]+\.[0-9]+\.[0-9]+)"
)


# ===== 辅助 =====


def _extract_display_name_and_setup_date(ws_root: Path):
    """从现有 AGENTS.md 提取 display_name + 从 workspace.toml.created_at 派生 setup_date。

    display_name 例外：workspace.toml 没存该字段（仅 AGENTS.md 持有），故从「当前配置」表 / H1 提取。
    setup_date SSOT：workspace.toml.created_at[:10]。
    """
    display_name = None
    agents_text = _read_text(ws_root / "AGENTS.md")
    if agents_text:
        display_name = workspace_fixtures._extract_row(agents_text, workspace_fixtures.WS_NAME_ROW_RE)
        if not display_name:
            h1 = next((ln for ln in agents_text.splitlines() if ln.startswith("# ")), "")
            m = workspace_fixtures.H1_NAME_RE.match(h1)
            if m:
                display_name = m.group(1).strip()

    setup_date = ""
    ws_toml_text = _read_text(ws_root / "workspace.toml")
    if ws_toml_text:
        m = workspace_fixtures.CREATED_AT_TOML_RE.search(ws_toml_text)
        if m:
            setup_date = m.group(1)[:10]

    return display_name, setup_date


def _compute_gitignore_block(current_text: str) -> Optional[str]:
    """跑 ensure_workspace_gitignore 于 sandbox，返回其生成的 .gitignore 内容。

    复用公开 API（gitignore.py:ensure_workspace_gitignore），不引入新的 helper。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        dst = sandbox / ".gitignore"
        try:
            dst.write_text(current_text or "", encoding="utf-8")
        except OSError:
            return current_text
        try:
            ensure_workspace_gitignore(sandbox)
        except OSError:
            return current_text
        return _read_text(dst) or current_text


def _extract_managed_block(text: str) -> Optional[str]:
    """从 .gitignore 文本抽出 llmw managed block（含 marker），未找到返 None。"""
    lines = text.splitlines(keepends=True)
    start = end = -1
    for i, ln in enumerate(lines):
        if ">>> llmw (managed by llmw) <<<" in ln:
            if start == -1:
                start = i
            else:
                end = i
                break
    if start == -1 or end == -1:
        return None
    return "".join(lines[start : end + 1])


def _diff_text(old: str, new: str) -> Optional[str]:
    if old == new:
        return None
    import difflib

    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm="", n=3, fromfile="(current)", tofile="(target)"
    )
    result = "\n".join(lines)
    return result if result else None


def _render_growth_memory(old_text: str) -> str:
    """MEMORY/MEMORY.md 段嫁接：保留旧 ## 索引 下的条目，用新 fixture 的头部 + ## 索引 段头。

    memory-index.txt 无 frontmatter，结构 = H1 + 说明块 + `## 索引` + 占位 / 条目示例。
    """
    fixture_text = _read_text(workspace_templates_dir() / "fixtures" / "memory-index.txt")
    if fixture_text is None:
        return old_text  # fixture 缺失 → 保持原样（让 check 报 error，self_verify 拦住）
    return _wiki_upgrade._render_growth_headers(old_text=old_text, fixture_text=fixture_text, rel_path="MEMORY.md")


# ===== plan_resync =====


def plan_resync(ws_root: Path) -> List[Dict[str, object]]:
    """计算 workspace 根的升级计划；不写盘。"""
    plan = []  # type: List[Dict[str, object]]

    display_name, setup_date = _extract_display_name_and_setup_date(ws_root)

    # --- byte-owned ---
    for rel in _BYTE_OWNED:
        p = ws_root / rel
        current = _read_text(p)
        if rel == "AGENTS.md":
            if not display_name or not setup_date:
                # 变量缺失 → 标 blocked（不静默生成空模板）
                plan.append(
                    {
                        "rel_path": rel,
                        "action": "render",
                        "blocked": True,
                        "blocked_reason": f"无法提取 {'display_name' if not display_name else 'setup_date'}",
                        "diff": None,
                    }
                )
                continue
            target = _render.render_workspace_agents_md(
                display_name=display_name,
                setup_date=setup_date,
                cli_version=CLI_VERSION,
                format_version=WORKSPACE_FORMAT_VERSION,
            )
        else:  # CLAUDE.md
            if not display_name:
                plan.append(
                    {
                        "rel_path": rel,
                        "action": "render",
                        "blocked": True,
                        "blocked_reason": "无法提取 display_name",
                        "diff": None,
                    }
                )
                continue
            target = _render.render_workspace_claude_md(display_name=display_name)

        diff = _diff_text(current or "", target)
        plan.append(
            {
                "rel_path": rel,
                "action": "render",
                "target": target,
                "diff": diff,
                "newly_created": current is None,
            }
        )

    # --- block-owned (.gitignore) ---
    for rel in _BLOCK_OWNED:
        p = ws_root / rel
        current = _read_text(p) or ""
        new_full = _compute_gitignore_block(current)
        cur_block = _extract_managed_block(current)
        new_block = _extract_managed_block(new_full or "")
        if cur_block == new_block:
            plan.append(
                {
                    "rel_path": rel,
                    "action": "gitignore-block",
                    "diff": None,
                    "newly_created": current == "",
                }
            )
        else:
            diff = _diff_text(cur_block or "(无 managed block)", new_block or "(生成失败)")
            plan.append(
                {
                    "rel_path": rel,
                    "action": "gitignore-block",
                    "new_block": new_block,
                    "new_full_text": new_full,
                    "diff": diff,
                    "newly_created": current == "",
                }
            )

    # --- header-owned (MEMORY/MEMORY.md) ---
    for rel in _HEADER_OWNED:
        p = ws_root / rel
        current = _read_text(p)
        if current is None:
            # MEMORY.md 不存在 → 直接用 fixture（CLI init 时该建，缺失则补）
            fixture_text = _read_text(workspace_templates_dir() / "fixtures" / "memory-index.txt")
            plan.append(
                {
                    "rel_path": rel,
                    "action": "growth-graft",
                    "diff": None,
                    "target": fixture_text,
                    "newly_created": True,
                }
            )
            continue
        new_text = _render_growth_memory(current)
        diff = _diff_text(current, new_text)
        plan.append(
            {
                "rel_path": rel,
                "action": "growth-graft",
                "target": new_text,
                "diff": diff,
                "newly_created": False,
            }
        )

    return plan


# ===== apply_resync =====


def apply_resync(ws_root: Path, plan: List[Dict[str, object]]) -> List[Dict[str, str]]:
    """按 plan 写盘；返 changed[{file, action}]。"""
    changed = []  # type: List[Dict[str, str]]
    for item in plan:
        action = item["action"]
        rel = str(item["rel_path"])
        p = ws_root / rel

        if action == "render":
            if item.get("blocked"):
                continue
            new_text = item.get("target")
            if new_text is None:
                continue
            atomic_write(p, new_text)  # type: ignore[arg-type]
            changed.append({"file": rel, "action": "render"})

        elif action == "gitignore-block":
            new_full = item.get("new_full_text")
            if new_full is None:
                continue
            # 只替换 llmw managed block，其余原样
            old_text = _read_text(p) or ""
            old_block = _extract_managed_block(old_text)
            new_block = item.get("new_block") or ""
            if old_block is None and new_block:
                # 文件无 managed block → 在开头插入
                updated = new_block + ("\n" if new_block and not new_block.endswith("\n") else "") + old_text
            elif old_block and new_block:
                updated = old_text.replace(old_block, new_block, 1)
            else:
                updated = old_text
            atomic_write(p, updated)
            changed.append({"file": rel, "action": "gitignore-block"})

        elif action == "growth-graft":
            new_text = item.get("target")
            if new_text is None:
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(p, new_text)  # type: ignore[arg-type]
            changed.append({"file": rel, "action": "growth-graft"})

    return changed


# ===== self_verify =====


def self_verify(ws_root: Path) -> Dict[str, object]:
    report = workspace_fixtures.run_checks(ws_root, WORKSPACE_FORMAT_VERSION)
    summary = report["summary"]  # type: ignore
    failures = [c for c in report["checks"] if c.get("passed") is False]  # type: ignore
    return {
        "error": summary.get("error", 0),  # type: ignore
        "warn": summary.get("warn", 0),  # type: ignore
        "pass": summary.get("pass", 0),  # type: ignore
        "skip": summary.get("skip", 0),  # type: ignore
        "failures": failures,
    }


# ===== bump templates_version =====


def _bump_templates_version(ws_root: Path, target_workspace_format: str) -> bool:
    """仅替换 templates_version.workspace_format 分量；wiki_format 分量保留。
    返是否真的变更。"""
    try:
        ws = ws_store.load(ws_root)
    except Exception:
        return False
    cur = ws.templates_version
    m = _TV_PARSE.search(cur)
    if m:
        new_tv = f"workspace_format={target_workspace_format}; wiki_format={m.group(2)}"
    else:
        # 老格式 / 不可解析 → 直接重写为双分量
        new_tv = f"workspace_format={target_workspace_format}; wiki_format=unknown"
    if new_tv == cur:
        return False
    ws.templates_version = new_tv
    ws_store.save(ws_root, ws)
    return True


# ===== main entry =====


def run_workspace_upgrade(ws_root: Path, *, dry_run: bool = True, yes: bool = False, as_json: bool = False) -> int:
    """升级 workspace 根的骨架；返 0/1/2。"""
    plan = plan_resync(ws_root)

    # 1. 变量提取失败 → blocked
    blocked_reasons = [str(item.get("blocked_reason")) for item in plan if item.get("blocked")]
    if blocked_reasons:
        result = {
            "status": "blocked_drift",
            "current_format": WORKSPACE_FORMAT_VERSION,
            "target_format": WORKSPACE_FORMAT_VERSION,
            "changed": [],
            "verified": {},
            "hint": f"变量提取失败：{'; '.join(blocked_reasons)}；需人工确认 display_name / ensure workspace.toml 含 created_at",
        }
        _emit(result, as_json=as_json, to_err=True)
        return 1

    # 2. preflight: blocked_drift（diff 非空 + 非 dry-run + 无 --yes）
    has_diff = any(item.get("diff") for item in plan if item.get("action") in ("render", "gitignore-block"))
    if has_diff and not dry_run and not yes:
        result = {
            "status": "blocked_drift",
            "current_format": WORKSPACE_FORMAT_VERSION,
            "target_format": WORKSPACE_FORMAT_VERSION,
            "changed": [
                {"file": str(item["rel_path"]), "action": str(item["action"])} for item in plan if item.get("diff")
            ],
            "verified": {},
            "hint": "diff 非空，需 --yes 确认（自定义内容先搬 MEMORY/，然后重跑）",
        }
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("== workspace upgrade blocked_drift ==", file=sys.stderr)
            for item in plan:
                if item.get("diff"):
                    print(f"\n--- {item['rel_path']} ---", file=sys.stderr)
                    print(item["diff"], file=sys.stderr)
            print(f"\n[llmw] hint: {result['hint']}", file=sys.stderr)
        return 1

    # 3. dry-run：输出 plan
    if dry_run:
        result = {
            "status": "dry_run",
            "current_format": WORKSPACE_FORMAT_VERSION,
            "target_format": WORKSPACE_FORMAT_VERSION,
            "plan": [
                {
                    "file": str(item["rel_path"]),
                    "action": str(item["action"]),
                    "diff": item.get("diff") or None,
                    "newly_created": bool(item.get("newly_created")),
                }
                for item in plan
            ],
        }
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("== workspace upgrade dry-run ==")
            print(f"current_format={WORKSPACE_FORMAT_VERSION}")
            for item in plan:
                diff_lines = (item.get("diff") or "").count("\n")
                line = f"  [{item['action']}] {item['rel_path']}"
                if item.get("newly_created"):
                    line += "  (newly created)"
                if diff_lines:
                    line += f"  ({diff_lines} diff lines)"
                print(line)
        return 0

    # 4. apply
    changed = apply_resync(ws_root, plan)

    # 5. self_verify
    verified = self_verify(ws_root)
    if verified.get("error", 0) > 0:
        result = {
            "status": "verify_failed",
            "current_format": WORKSPACE_FORMAT_VERSION,
            "target_format": WORKSPACE_FORMAT_VERSION,
            "changed": changed,
            "verified": verified,
            "hint": "自验失败（版本钉不落）",
        }
        _emit(result, as_json=as_json, to_err=True)
        return 2

    # 6. bump templates_version
    bumped = _bump_templates_version(ws_root, WORKSPACE_FORMAT_VERSION)
    if bumped:
        changed.append({"file": "workspace.toml", "action": "templates_version_bump"})

    result = {
        "status": "done",
        "current_format": WORKSPACE_FORMAT_VERSION,
        "target_format": WORKSPACE_FORMAT_VERSION,
        "changed": changed,
        "verified": verified,
    }
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("== workspace upgrade done ==")
        print(f"changed: {len(changed)} actions")
        print(
            f"verified: error={verified.get('error', 0)} warn={verified.get('warn', 0)} pass={verified.get('pass', 0)}"
        )
    return 0


def _emit(result: Dict[str, object], *, as_json: bool, to_err: bool = False) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        stream = sys.stderr if to_err else sys.stdout
        for k, v in result.items():
            print(f"  {k}: {v}", file=stream)
