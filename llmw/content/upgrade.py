"""llmw.content.upgrade — wiki 骨架升级引擎

确定性执行 upgrade（`llmw wiki upgrade`）：重渲染 byte-owned 文件 + growth 文件段嫁接
+ legacy 路径表 + 版本钉写回 + 自检 fixtures checker 0 error。

主流程（幂等，任意版本/中间态可重跑）：

    idle → preflight（drift diff）→ resync → verifying → done
                              ↘ blocked_drift（diff 非空 + 非 dry-run 未 --yes）
                              ↘ verifying fail → exit 2（版本钉不落）

3 终态 JSON 契约（--json 恒可用，agent 判定依据）：

    status: done | done_with_residue | blocked_drift
    - done            : 骨架全渲染 + 自检 0 error + 无残留
    - done_with_residue: 骨架完成，残留清单需 agent
    - blocked_drift   : pre-constraint 自定义将被覆盖，dry-run 输出 diff 停住

退出码（main()）:
    0 = done / done_with_residue
    1 = blocked_drift（diff 非空 + 非 dry-run 无 --yes）
    2 = 自验证失败（版本钉不落）/ 内部错误

变量 SSOT: metadata toml + 版本常量（不从旧文件反提取，详见 render.py）。
"""

import argparse
import difflib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from llmw import WIKI_SPEC_VERSION
from llmw import __version__ as CLI_VERSION
from llmw.content import render as _render
from llmw.content import wiki_fixtures
from llmw.fsutil import atomic_write
from llmw.wiki import store as wiki_store

ENV_LLM_WIKI_ROOT = "LLM_WIKI_ROOT"


# ===== plan_resync: 计算 resync 计划（不写盘）=====


def _read_text(p: Path) -> Optional[str]:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _load_meta(wiki_root: Path) -> Optional[Dict[str, str]]:
    """读 wiki_metadata.toml 必要字段；失败返 None。"""
    try:
        meta = wiki_store.load(wiki_root)
    except Exception:
        return None
    return {
        "name": getattr(meta, "name", "") or "",
        "topic": getattr(meta, "topic", "") or "",
        "created_at": getattr(meta, "created_at", "") or "",
    }


def _render_growth_headers(*, old_text: str, fixture_text: str, rel_path: str) -> str:
    """growth 文件换头 + 按段嫁接：保留旧 ## 段条目，用新 frontmatter / 说明块 / ## 段头。

    算法（按文件类型分三支）:
    - 标准段文件 (index.md / tags.md / MEMORY.md / SCRIPTS.md):
      1. 解析旧文件 frontmatter + 说明块（> 段）+ ## 段体
      2. 用新 fixture 的 frontmatter + 说明块 + ## 段头
      3. 对每个 ## 段：若旧文件有同名段 → 填旧段条目；无 → 填 fixture 占位
    - 追加式文件 (log.md):
      只换 frontmatter + 说明块头（H1 + > 引用）；所有 ## 条目保留（log 是 append-only）。
    解析失败 → 返空串（caller 判为 blocked_drift，不静默丢条目）。
    """
    import re

    # log.md 特例：append-only，所有 ## 条目保留
    if rel_path.endswith("log.md"):
        return _graft_log(old_text, fixture_text)

    def _split(text: str):
        fm = None  # type: Optional[str]
        intro = []  # type: List[str]
        sections = {}  # type: Dict[str, List[str]]
        cur_h2 = None  # type: Optional[str]
        lines = text.splitlines(keepends=True)
        i = 0
        # Frontmatter (可选)
        if lines and lines[0].rstrip() == "---":
            j = 1
            while j < len(lines) and lines[j].rstrip() != "---":
                j += 1
            if j < len(lines):
                fm = "".join(lines[: j + 1])
                i = j + 1
        # Intro (frontmatter 后到第一个 ## 之间)
        while i < len(lines) and not lines[i].startswith("## "):
            intro.append(lines[i])
            i += 1
        # Sections (## 起)
        while i < len(lines):
            m = re.match(r"^## (.+)$", lines[i].rstrip())
            if m:
                cur_h2 = m.group(1).strip()
                sections[cur_h2] = []
                i += 1
                while i < len(lines) and not lines[i].startswith("## "):
                    sections[cur_h2].append(lines[i])
                    i += 1
            else:
                i += 1
        return fm, intro, sections

    old_fm, old_intro, old_sections = _split(old_text)
    new_fm, new_intro, new_sections = _split(fixture_text)

    if new_fm is None and new_sections is None:
        return ""

    out = []
    if new_fm is not None:
        out.append(new_fm)
    out.extend(new_intro)
    for h2, new_body in new_sections.items():
        out.append(f"## {h2}\n")
        old_body = old_sections.get(h2)
        # Growth 判据：旧段条目非空 / 非占位符（纯空白 + `_（暂无...）_` / HTML 注释）
        if old_body and _has_growth(old_body):
            out.extend(old_body)
        else:
            out.extend(new_body)
    return "".join(out)


def _graft_log(old_text: str, fixture_text: str) -> str:
    """log.md 专用：只换 frontmatter + 说明块（H1 + > 引用），保留所有 ## 条目。

    log 是 append-only 文件，每个 ## 条目 = 一次操作记录，不应被替换/去重。
    """

    def _split_head(text: str):
        """返 (head, body) 其中 head = frontmatter + 说明块（H1 + > 行 + 注释行），
        body = 第一个 ## 起的所有行。"""
        lines = text.splitlines(keepends=True)
        i = 0
        # frontmatter
        if lines and lines[0].rstrip() == "---":
            j = 1
            while j < len(lines) and lines[j].rstrip() != "---":
                j += 1
            if j < len(lines):
                i = j + 1
        # 说明块（H1 + 后续 > 行 / HTML 注释 / 空白，到第一个 ## 止）
        while i < len(lines) and not lines[i].startswith("## "):
            i += 1
        head = "".join(lines[:i])
        body = "".join(lines[i:])
        return head, body

    new_head, _ = _split_head(fixture_text)
    _, old_body = _split_head(old_text)
    return new_head + old_body


def _has_growth(lines: List[str]) -> bool:
    """段体行是否含真实 growth 内容（非空 / 非占位符 / 非注释）。"""
    import re

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("<!--"):
            continue
        if re.match(r"^_\([^)]+\)_$", s):
            continue  # `_（暂无内容）_` 等占位符
        if s.startswith("<!--") and "-->" in s:
            continue
        return True
    return False


BYTE_OWNED = {"AGENTS.md": True, "CLAUDE.md": True}
GROWTH_FILES = {
    "wiki/index.md": "fixtures/index.md.txt",
    "wiki/log.md": "fixtures/log.md.txt",
    "wiki/tags.md": "fixtures/tags.md.txt",
    "MEMORY/MEMORY.md": "fixtures/memory-index.txt",
    "scripts/SCRIPTS.md": "fixtures/scripts.md.txt",
}
GITIGNORE_REL = ".gitignore"


def _render_byte_owned(*, topic: str, setup_date: str) -> Dict[str, str]:
    """byte-owned 文件渲染（AGENTS.md / CLAUDE.md）。"""
    return {
        "AGENTS.md": _render.render_wiki_agents_md(
            topic=topic,
            setup_date=setup_date,
            cli_version=CLI_VERSION,
            spec_version=WIKI_SPEC_VERSION,
        ),
        "CLAUDE.md": _render.render_wiki_claude_md(topic=topic),
    }


def _render_fixture(fixture_name: str) -> str:
    """读 reference fixture 文本 + 替换占位符；返原始文本（不做 substitute，caller 按需）。"""
    from llmw.config import wiki_spec_templates_dir

    return _render._read_template(wiki_spec_templates_dir() / fixture_name)


def _apply_substitute(text: str, *, topic: str, setup_date: str) -> str:
    try:
        return _render._substitute(text, {"TOPIC_NAME": topic, "SETUP_DATE": setup_date})
    except Exception:
        return text


def plan_resync(wiki_root: Path, *, meta: Dict[str, str]) -> List[Dict[str, object]]:
    """计算 resync 计划（不写盘）→ [{rel_path, action, old?, new?, diff?}]

    action: 'render' (byte-owned 全量重渲染) / 'growth-graft' (growth 换头保条目) /
            'create' (缺失文件从 fixture 创建) / 'gitignore-block' (.gitignore managed 块替换)
    """
    plan = []  # type: List[Dict[str, object]]
    topic = meta["topic"]
    # SETUP_DATE: UTC created_at → "YYYY-MM-DD HH:MM" (replace "T" with space, take first 16 chars)
    raw_ca = meta["created_at"]
    if raw_ca.endswith("Z"):
        raw_ca = raw_ca[:-1]
    setup_date = raw_ca.replace("T", " ")[:16]

    # byte-owned
    byte_rendered = _render_byte_owned(topic=topic, setup_date=setup_date)
    for rel, new_text in byte_rendered.items():
        old_text = _read_text(wiki_root / rel)
        action = "render"
        if old_text is None:
            action = "create"
            plan.append({"rel_path": rel, "action": action, "new": new_text})
        elif old_text != new_text:
            diff = list(
                difflib.unified_diff(
                    old_text.splitlines(), new_text.splitlines(), lineterm="", n=0, fromfile=rel, tofile=rel
                )
            )
            plan.append({"rel_path": rel, "action": action, "old": old_text, "new": new_text, "diff": "\n".join(diff)})
        # else: already up-to-date, no action

    # growth files
    for rel, fixture_name in GROWTH_FILES.items():
        fixture_text = _render_fixture(fixture_name)
        fixture_text = _apply_substitute(fixture_text, topic=topic, setup_date=setup_date)
        old_text = _read_text(wiki_root / rel)
        if old_text is None:
            plan.append({"rel_path": rel, "action": "create", "new": fixture_text})
            continue
        new_text = _render_growth_headers(old_text=old_text, fixture_text=fixture_text, rel_path=rel)
        if not new_text:
            plan.append({"rel_path": rel, "action": "growth-graft-error", "error": "parsing failed"})
            continue
        if old_text != new_text:
            diff = list(
                difflib.unified_diff(
                    old_text.splitlines(), new_text.splitlines(), lineterm="", n=0, fromfile=rel, tofile=rel
                )
            )
            plan.append(
                {
                    "rel_path": rel,
                    "action": "growth-graft",
                    "old": old_text,
                    "new": new_text,
                    "diff": "\n".join(diff),
                }
            )

    # .gitignore managed block 替换（仅替换 llmw managed 块，段外用户自定义规则不动）
    gi_path = wiki_root / GITIGNORE_REL
    old_gi = _read_text(gi_path)
    if old_gi is not None:
        from llmw.workspace.gitignore import GITIGNORE_LINES

        marker_s = "# >>> llmw (managed by llmw) >>>"
        marker_e = "# <<< llmw <<<"
        new_block = marker_s + "\n" + "\n".join(GITIGNORE_LINES) + "\n" + marker_e
        import re

        pat = re.compile(re.escape(marker_s) + r".*?" + re.escape(marker_e), re.DOTALL)
        m = pat.search(old_gi)
        if m and m.group(0) != new_block:
            new_gi = pat.sub(new_block, old_gi)
            diff = list(
                difflib.unified_diff(
                    old_gi.splitlines(),
                    new_gi.splitlines(),
                    lineterm="",
                    n=0,
                    fromfile=GITIGNORE_REL,
                    tofile=GITIGNORE_REL,
                )
            )
            plan.append(
                {
                    "rel_path": GITIGNORE_REL,
                    "action": "gitignore-block",
                    "old": old_gi,
                    "new": new_gi,
                    "diff": "\n".join(diff),
                }
            )

    return plan


# ===== apply_resync: 写盘 =====


def apply_resync(wiki_root: Path, plan: List[Dict[str, object]]) -> List[Dict[str, str]]:
    """按 plan 写盘；返 changed[] 列表（含 rel_path + action）。"""
    changed = []  # type: List[Dict[str, str]]
    for item in plan:
        rel = item["rel_path"]  # type: ignore
        action = item["action"]  # type: ignore
        new_text = item.get("new")
        if action in ("growth-graft-error",):
            continue  # 不写盘，留作残留
        if new_text is None:
            continue
        target = wiki_root / rel  # type: ignore
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, new_text)  # type: ignore
        changed.append({"file": str(rel), "action": str(action)})
    return changed


# ===== legacy_paths: 路径表变换 =====


def _load_legacy_table() -> List[Dict[str, str]]:
    """读 llmw/content/legacy_paths.toml（若存在）；返 [[legacy]] 行列表。"""
    here = Path(__file__).parent
    toml_path = here / "legacy_paths.toml"
    if not toml_path.is_file():
        return []
    try:
        from llmw._compat import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data.get("legacy", []) or []


def apply_legacy_paths(wiki_root: Path) -> List[Dict[str, str]]:
    """执行 legacy_paths.toml 表内移动/删除；返 changed[]。"""
    changed = []  # type: List[Dict[str, str]]
    for entry in _load_legacy_table():
        kind = entry.get("kind", "")
        old_rel = entry.get("old", "")
        new_rel = entry.get("new", "")
        if not old_rel:
            continue
        old_p = wiki_root / old_rel
        new_p = wiki_root / new_rel if new_rel else None
        if kind == "move" and new_p and old_p.exists() and not new_p.exists():
            new_p.parent.mkdir(parents=True, exist_ok=True)
            old_p.rename(new_p)
            changed.append(
                {
                    "file": old_rel,
                    "action": "legacy-move-to-" + (entry.get("new", "") or "?"),
                    "note": entry.get("note", ""),
                }
            )
        elif kind == "remove" and old_p.exists():
            if old_p.is_dir():
                import shutil

                shutil.rmtree(old_p)
            else:
                old_p.unlink()
            changed.append({"file": old_rel, "action": "legacy-remove", "note": entry.get("note", "")})
    return changed


# ===== self_verify =====


def self_verify(wiki_root: Path) -> Dict[str, object]:
    """内联重跑 fixtures checker → 返 {error, warn, pass, skip, failures: [...]}。"""
    report = wiki_fixtures.run_checks(wiki_root, WIKI_SPEC_VERSION)
    summary = report["summary"]  # type: ignore
    # 只保留 failed 的 check（error / warn 级）供诊断；pass/skip 不列出节省噪声
    failures = [c for c in report["checks"] if c.get("passed") is False]  # type: ignore
    return {
        "error": summary.get("error", 0),  # type: ignore
        "warn": summary.get("warn", 0),  # type: ignore
        "pass": summary.get("pass", 0),  # type: ignore
        "skip": summary.get("skip", 0),  # type: ignore
        "failures": failures,
    }


# ===== main entry =====


def run_upgrade(wiki_root: Path, *, dry_run: bool = True, yes: bool = False, as_json: bool = False) -> int:
    """升级单 wiki；返退出码 0/1/2。"""
    meta = _load_meta(wiki_root)
    if meta is None:
        result = {
            "status": "error",
            "error": "wiki_metadata.toml 读取失败或字段缺失",
            "hint": "<wiki>/wiki_metadata.toml 必须存在且含 name/topic/created_at",
        }
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"[llmw] error: {result['error']}", file=sys.stderr)
            if result.get("hint"):
                print(f"[llmw] hint: {result['hint']}", file=sys.stderr)
        return 2

    # 1. plan resync
    plan = plan_resync(wiki_root, meta=meta)

    # 2. preflight: 判断 blocked_drift（diff 非空 + 非 dry-run 未 --yes）
    # 注：growth-graft 保留条目，不算 drift；只有 byte-owned render + gitignore-block 算
    has_diff = any(item.get("diff") for item in plan if item.get("action") in ("render", "gitignore-block"))
    if has_diff and not dry_run and not yes:
        # blocked_drift: 输出 diff 但不写盘
        result = {
            "status": "blocked_drift",
            "current_spec": WIKI_SPEC_VERSION,
            "target_spec": WIKI_SPEC_VERSION,
            "changed": [
                {"file": str(item.get("rel_path", "")), "action": str(item.get("action", ""))}
                for item in plan
                if item.get("diff")
            ],
            "residue": [],
            "verified": {"error": 0, "warn": 0, "pass": 0, "skip": 0},
            "hint": "diff 非空，需 --yes 确认（自定义内容先搬 MEMORY/，然后重跑）",
        }
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("== upgrade blocked_drift == ", file=sys.stderr)
            for item in plan:
                if item.get("diff"):
                    print(f"\n--- {item.get('rel_path')} ---", file=sys.stderr)
                    print(item["diff"], file=sys.stderr)
            print(f"\n[llmw] hint: {result['hint']}", file=sys.stderr)
        return 1

    # 3. dry-run: 输出 plan 不写盘
    if dry_run:
        result = {
            "status": "dry_run",
            "current_spec": WIKI_SPEC_VERSION,
            "target_spec": WIKI_SPEC_VERSION,
            "plan": [
                {
                    "file": str(item.get("rel_path", "")),
                    "action": str(item.get("action", "")),
                    "diff": item.get("diff") or None,
                }
                for item in plan
            ],
        }
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("== upgrade dry-run ==")
            print(f"current_spec={result['current_spec']} target_spec={result['target_spec']}")
            for item in plan:
                action = item.get("action", "")
                rel = item.get("rel_path", "")
                diff_lines = (item.get("diff") or "").count("\n")
                print(f"  [{action}] {rel}" + (f"  ({diff_lines} diff lines)" if diff_lines else ""))
        return 0

    # 4. apply resync
    changed = apply_resync(wiki_root, plan)

    # 5. legacy paths
    legacy_changed = apply_legacy_paths(wiki_root)
    changed.extend(legacy_changed)

    # 6. transforms (empty slots placeholder)
    residue = []  # type: List[Dict[str, str]]
    for item in plan:
        if item.get("action") == "growth-graft-error":
            residue.append(
                {
                    "type": "content-page-transform",
                    "note": f"{item.get('rel_path')} growth-graft 解析失败，需人工对照 fixture 重渲染",
                }
            )

    # 7. self-verify
    verified = self_verify(wiki_root)
    if verified.get("error", 0) > 0:
        result = {
            "status": "verify_failed",
            "current_spec": WIKI_SPEC_VERSION,
            "target_spec": WIKI_SPEC_VERSION,
            "changed": changed,
            "residue": residue,
            "verified": verified,
            "error": "自验失败（版本钉不落）",
        }
        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"[llmw] error: {result['error']}", file=sys.stderr)
            print(f"[llmw] verified: error={verified.get('error', 0)} warn={verified.get('warn', 0)}", file=sys.stderr)
        return 2

    # 8. final status
    status = "done" if not residue else "done_with_residue"
    result = {
        "status": status,
        "current_spec": WIKI_SPEC_VERSION,
        "target_spec": WIKI_SPEC_VERSION,
        "changed": changed,
        "residue": residue,
        "verified": verified,
    }
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"== upgrade {status} ==")
        print(f"current_spec={WIKI_SPEC_VERSION}")
        print(f"changed: {len(changed)} files")
        if residue:
            print(f"residue: {len(residue)} items")
            for r in residue:
                print(f"  - [{r.get('type')}] {r.get('note')}")
        print(
            f"verified: error={verified.get('error', 0)} warn={verified.get('warn', 0)} pass={verified.get('pass', 0)}"
        )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="upgrade_wiki",
        description="升级 wiki 骨架（重渲染 + legacy 路径 + 自检）",
    )
    parser.add_argument("wiki_root", nargs="?", help="wiki 根目录；默认从 $LLM_WIKI_ROOT 读")
    parser.add_argument("--json", action="store_true", help="输出 JSON（3 终态契约）")
    parser.add_argument("--dry-run", action="store_true", help="只输出计划不写盘")
    parser.add_argument("--yes", "-y", action="store_true", help="覆盖 drift diff 时需此 flag")
    args = parser.parse_args(argv)

    if args.wiki_root:
        wiki_root = Path(args.wiki_root).expanduser().resolve()
    elif os.environ.get(ENV_LLM_WIKI_ROOT):
        wiki_root = Path(os.environ[ENV_LLM_WIKI_ROOT]).expanduser().resolve()
    else:
        print("ERROR: 需提供 wiki_root 参数或设置 $LLM_WIKI_ROOT", file=sys.stderr)
        return 2

    if not wiki_root.is_dir():
        print(f"ERROR: {wiki_root} 不是目录", file=sys.stderr)
        return 2

    return run_upgrade(wiki_root, dry_run=args.dry_run, yes=args.yes, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
