#!/usr/bin/env python3
"""external_anchor — raw/external/ 写路径（anchor + symlink 注册表变换）

CLI 接管 anchor (`raw/external/.symlink-anchor.toml`) 与对应 symlink 的写路径；
skill 仅在"接哪台仓、叫啥名、notes 写啥"这些判断上介入。

子命令（经 `llmw wiki --name=X external <action>` 或 `--path=DIR external <action>`）：
  add <target> --name <n> [--notes "..."]   注册 entry + 建 symlink
  remove <name>                              删 entry + 删 symlink（target 仓永不碰）
  list                                       NAME/TARGET/REMOTE/BRANCH/STATUS + --json
  rebuild [--target NAME=PATH ...] [--yes]   按 anchor 重建（含 clone 外部仓）

anchor 单文件 `[[entry]]` 数组。schema v1，最小必填 4 字段
(`symlink` / `target` / `captured_at` / `kind="external-repo"`) + 可选 git 身份字段
(`remote_url` / `branch`) + 可选 `notes`。**不**记 commit（anchor 记录"接入意图"，
commit 是机器快照会腐坏）。

退出码：0 = 成功（含 no-op）；1 = 用户错误（参数非法、entry 已存在/缺失）；
2 = 环境错误（git 不在 PATH、网络失败、非 TTY 无 --yes 拒绝执行）。
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from llmw._compat import toml_dump
from llmw.fsutil import atomic_write  # noqa: E402

SOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
EXTERNAL_SUBDIR = "external"
ANCHOR_FILENAME = ".symlink-anchor.toml"
SCHEMA_VERSION = 1
_REQUIRED_FIELDS = ("symlink", "target", "captured_at", "kind")
_VALID_KIND = "external-repo"

# ---------- 路径 ----------


def _external_dir(wiki_root: Path) -> Path:
    return wiki_root / "raw" / EXTERNAL_SUBDIR


def _anchor_path(wiki_root: Path) -> Path:
    return _external_dir(wiki_root) / ANCHOR_FILENAME


# ---------- Store: load (lenient) / save (strict) ----------


def load(anchor_path: Path) -> Optional[List[Dict[str, str]]]:
    """解析 .symlink-anchor.toml；返回 List[Dict]（每个有效 entry 一条）或 None（损坏/无有效 entry）

    与原 wiki_lint._parse_anchor 完全等价（含未知行 lenient 跳过、缺必填字段/非
    external-repo kind 的 entry 过滤、0 有效 entry → None）。
    """
    try:
        text = anchor_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    entries = []  # type: List[Dict[str, str]]
    current = None  # type: Optional[Dict[str, str]]
    for raw_line in text.splitlines():
        # 行内注释：仅在引号外剥离（anchor 实际写出字符串不含 #）
        if "#" in raw_line:
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
        m = re.match(r"^\[\[(\w+)\]\]\s*$", stripped)
        if m:
            if current is not None:
                entries.append(current)
            current = {}
            continue
        m = re.match(r'^([a-z_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', stripped)
        if m:
            key, raw_val = m.group(1), m.group(2)
            val = re.sub(
                r"\\(.)",
                lambda mo: {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(mo.group(1), mo.group(1)),
                raw_val,
            )
            if current is not None:
                current[key] = val
            continue
        m = re.match(r"^([a-z_]+)\s*=\s*([0-9]+|true|false)\s*$", stripped)
        if m:
            continue

    if current is not None:
        entries.append(current)
    if not entries:
        return None

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
        if kind != _VALID_KIND:
            continue
        valid.append(entry)
    return valid if valid else None


def _validate_entry(entry: Dict) -> Tuple[Optional[str], int]:
    """save 路径的严格校验；返回 (error_msg_or_None, exit_code)。"""
    if not isinstance(entry, dict):
        return ("entry 必须是 dict", 3)
    missing = [f for f in _REQUIRED_FIELDS if f not in entry or not entry[f]]
    if missing:
        return ("entry 缺必填字段: {}".format(", ".join(missing)), 1)
    symlink = str(entry["symlink"])
    if not SOURCE_NAME_RE.match(symlink):
        return (
            f"entry symlink '{symlink}' 不合 ^[a-z0-9][a-z0-9-]*$（kebab-case 短名）",
            1,
        )
    if entry.get("kind") != _VALID_KIND:
        return (f"entry kind 必须是 '{_VALID_KIND}'（当前唯一支持）", 1)
    return (None, 0)


def save(anchor_path: Path, entries: List[Dict]) -> None:
    """严格校验 + 原子写 + schema_version=1。不 chmod（无 secret）。

    空 entry 列表 → 删除 anchor 文件（注册表无意图状态）+ 顺手清 external_dir 空目录。
    """
    for entry in entries:
        err, code = _validate_entry(entry)
        if err:
            raise ValueError(f"[{code}] {err}")
    if not entries:
        if anchor_path.is_file():
            try:
                anchor_path.unlink()
            except OSError:
                pass
        # 若 external_dir 空（无 symlink 也没 anchor），顺手清掉避免 lint 误判
        ext_dir = anchor_path.parent
        try:
            if ext_dir.is_dir() and not any(ext_dir.iterdir()):
                ext_dir.rmdir()
        except OSError:
            pass
        return
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    # TOML 键用 `[[entry]]` 单数（与模板 / fixtures / skill 文档描述 SSOT 对齐）
    data = {"schema_version": SCHEMA_VERSION, "entry": list(entries)}
    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(anchor_path, buf.getvalue())


# ---------- git 身份字段 best-effort ----------


def _git_read(target: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """读 target 的 git 身份字段：(is_repo, remote_url_or_None, branch_or_None)。

    git 不在 PATH → 抛 FileNotFoundError，调用方转环境错误。
    """
    check = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check.returncode != 0:
        return (False, None, None)
    remote = None
    r = subprocess.run(
        ["git", "-C", str(target), "config", "--get", "remote.origin.url"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if r.returncode == 0:
        s = r.stdout.decode("utf-8", errors="replace").strip()
        if s:
            remote = s
    branch = None
    b = subprocess.run(
        ["git", "-C", str(target), "branch", "--show-current"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if b.returncode == 0:
        s = b.stdout.decode("utf-8", errors="replace").strip()
        if s:
            branch = s
    if branch is None:
        # git 2.22 之前无 --show-current；回退到 symbolic-ref --short HEAD
        # （git 1.8.1+；detached HEAD 返回非零 → None，正好是我们想要的语义）
        sb = subprocess.run(
            ["git", "-C", str(target), "symbolic-ref", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if sb.returncode == 0:
            s = sb.stdout.decode("utf-8", errors="replace").strip()
            if s:
                branch = s
    return (True, remote, branch)


def _target_for_anchor(target: Path) -> str:
    """落盘 target 字段：优先 ~/... home-relative；否则绝对。"""
    home = os.environ.get("HOME")
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target
    if home:
        home_path = Path(home).resolve()
        try:
            rel = resolved.relative_to(home_path)
            return "~/" + rel.as_posix()
        except ValueError:
            pass
    return str(resolved)


def _expand(target_str: str) -> Path:
    return Path(target_str).expanduser()


# ---------- cmd ----------


def cmd_add(wiki_root: Path, args) -> Tuple[Optional[str], int]:
    name = args.entry_name
    target_raw = args.target
    notes = getattr(args, "notes", None) or None

    if not SOURCE_NAME_RE.match(name):
        return (
            f"anchor entry 名必须 kebab-case (^[a-z0-9][a-z0-9-]*$): {name}",
            1,
        )
    try:
        target = _expand(target_raw).resolve()
    except OSError as e:
        return (f"target 路径无法展开: {target_raw} ({e})", 1)
    if not target.exists():
        return (f"target 不存在: {target}", 1)

    external_dir = _external_dir(wiki_root)
    external_dir.mkdir(parents=True, exist_ok=True)
    sl_path = external_dir / name
    if sl_path.exists() or sl_path.is_symlink():
        return (f"路径已占用: {sl_path}", 1)

    anchor_path = _anchor_path(wiki_root)
    if anchor_path.is_file():
        existing = load(anchor_path)
        if existing is None:
            # 文件存在但解析失败 / 0 有效 entry → 不静默覆盖
            # （保护手工修复现场；用户要先备份再删，或手工修 TOML 后重跑）
            return (
                f"anchor 文件存在但解析失败（可能损坏）: {anchor_path}；"
                "请先备份后删除或手工修复 TOML，再用 add 重建 entries",
                1,
            )
    else:
        existing = []
    for e in existing:
        if e.get("symlink") == name:
            return (f"anchor 已含 entry '{name}'；先 remove 再 add", 1)

    remote = None
    branch = None
    warns = []
    try:
        is_repo, remote, branch = _git_read(target)
        if not is_repo:
            warns.append("target 不是 git 仓；remote_url/branch 省略（rebuild 时只能 relink 不能 clone）")
        else:
            if not remote:
                warns.append("git 仓但无 origin remote；remote_url 省略")
            if not branch:
                warns.append("detached HEAD；branch 省略")
    except FileNotFoundError:
        warns.append("git 不在 PATH；remote_url/branch 省略，rebuild 能力受限")

    entry = {
        "symlink": name,
        "target": _target_for_anchor(target),
        "captured_at": date.today().isoformat(),
        "kind": _VALID_KIND,
    }
    if remote:
        entry["remote_url"] = remote
    if branch:
        entry["branch"] = branch
    if notes:
        entry["notes"] = notes

    new_entries = list(existing) + [entry]
    try:
        save(anchor_path, new_entries)
    except ValueError as e:
        return (str(e), 1)
    sl_path.symlink_to(target)
    msg = "已添加 entry '{}' → {}（target='{}'）".format(name, target, entry["target"])
    if warns:
        msg += "；{}".format("；".join(warns))
    print("[llmw] " + msg, file=sys.stderr)
    return (None, 0)


def cmd_remove(wiki_root: Path, args) -> Tuple[Optional[str], int]:
    name = args.entry_name
    external_dir = _external_dir(wiki_root)
    sl_path = external_dir / name
    anchor_path = _anchor_path(wiki_root)

    if not anchor_path.is_file():
        return (f"anchor 文件不存在: {anchor_path}", 1)
    existing = load(anchor_path)
    if existing is None:
        return (f"anchor 解析失败或空: {anchor_path}", 1)
    new = [e for e in existing if e.get("symlink") != name]
    if len(new) == len(existing):
        return (f"anchor 中无 entry '{name}';若是孤儿 symlink（anchor 无对应 entry）请手动 rm {sl_path}", 1)

    if sl_path.exists() or sl_path.is_symlink():
        if not sl_path.is_symlink():
            return (
                f"路径 '{sl_path}' 不是 symlink（是普通文件/目录，可能是用户资产），拒绝删除",
                1,
            )
        try:
            sl_path.unlink()
        except OSError as e:
            return (f"symlink 删除失败: {e}", 2)

    try:
        save(anchor_path, new)
    except ValueError as e:
        return (str(e), 1)
    print(f"[llmw] 已删除 entry '{name}' + symlink {sl_path}", file=sys.stderr)
    return (None, 0)


def _entry_status(wiki_root: Path, entry: Dict) -> Tuple[str, str]:
    """返回 (status, detail)：ok / missing / dead / drift / orphan。"""
    external_dir = _external_dir(wiki_root)
    sl_path = external_dir / entry.get("symlink", "")
    target_str = entry.get("target", "")
    if not (sl_path.exists() or sl_path.is_symlink()):
        return ("missing", "")
    if not sl_path.is_symlink():
        return ("orphan", "非 symlink，是普通文件/目录")
    if not sl_path.exists():
        return ("dead", f"target '{target_str}' 不存在")
    try:
        current = str(sl_path.resolve())
    except OSError:
        return ("dead", "symlink 无法解析")
    expanded = _expand(target_str)
    try:
        expected = str(expanded.resolve())
    except OSError:
        expected = ""
    if expected and current != expected:
        return (
            "drift",
            f"actual={current} expected={expected}",
        )
    return ("ok", "")


def cmd_list(wiki_root: Path, args) -> Tuple[Optional[str], int]:
    anchor_path = _anchor_path(wiki_root)
    if not anchor_path.is_file():
        # 无注册表 = 无 external 仓；输出空状态，不报错
        if getattr(args, "json", False):
            print("[]")
        else:
            print("(no external entries)", file=sys.stderr)
        return (None, 0)
    entries = load(anchor_path)
    if entries is None:
        return (f"anchor 解析失败或空: {anchor_path}", 1)
    rows = []
    for e in entries:
        status, detail = _entry_status(wiki_root, e)
        rows.append(
            {
                "name": e.get("symlink", ""),
                "target": e.get("target", ""),
                "remote": e.get("remote_url", ""),
                "branch": e.get("branch", ""),
                "captured": e.get("captured_at", ""),
                "status": status,
                "detail": detail,
            }
        )
    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("(no entries)", file=sys.stderr)
            return (None, 0)
        hdr = ("NAME", "STATUS", "TARGET", "REMOTE", "BRANCH", "CAPTURED")
        cols = [[r["name"], r["status"], r["target"], r["remote"], r["branch"], r["captured"]] for r in rows]
        widths = [max(len(hdr[i]), max(len(c[i]) for c in cols)) for i in range(len(hdr))]
        print("  ".join(h.ljust(widths[i]) for i, h in enumerate(hdr)))
        print("  ".join("-" * widths[i] for i in range(len(hdr))))
        for c in cols:
            print("  ".join(c[i].ljust(widths[i]) for i in range(len(hdr))))
        stats = {}
        for r in rows:
            stats[r["status"]] = stats.get(r["status"], 0) + 1
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(stats.items()))
        print(f"({summary})", file=sys.stderr)
    return (None, 0)


def _parse_target_overrides(values):
    """解析 --target NAME=PATH (可重复) 返回 dict。"""
    overrides = {}
    for raw in values or []:
        if "=" not in raw:
            raise argparse.ArgumentTypeError(f"--target 必须是 NAME=PATH 形式: {raw}")
        name, _, path = raw.partition("=")
        if not name or not path:
            raise argparse.ArgumentTypeError(f"--target 必须非空 NAME 与 PATH: {raw}")
        overrides[name] = path
    return overrides


def cmd_rebuild(wiki_root: Path, args) -> Tuple[Optional[str], int]:
    anchor_path = _anchor_path(wiki_root)
    if not anchor_path.is_file():
        print("[llmw] 无 anchor 文件，跳过（no-op）", file=sys.stderr)
        return (None, 0)
    entries = load(anchor_path)
    if entries is None:
        return (f"anchor 解析失败或空: {anchor_path}", 1)
    try:
        overrides = _parse_target_overrides(getattr(args, "target", None))
    except argparse.ArgumentTypeError as e:
        return (str(e), 1)
    yes = getattr(args, "yes", False)

    plan = []  # type: List[Tuple[Dict, str, str]]
    for e in entries:
        name = e.get("symlink", "")
        status, _ = _entry_status(wiki_root, e)
        override = overrides.get(name)
        effective_target_str = override if override else e.get("target", "")
        effective_target = _expand(effective_target_str)

        if status == "ok" and not override:
            plan.append((e, "skip", "symlink 已正确指向 {}".format(e.get("target", ""))))
            continue
        if override or status in ("missing", "dead", "drift"):
            if effective_target.exists():
                plan.append((e, "relink", f"symlink → {effective_target}"))
            elif e.get("remote_url"):
                plan.append(
                    (
                        e,
                        "clone_relink",
                        "git clone {} → {} (branch: {})".format(
                            e.get("remote_url"),
                            effective_target,
                            e.get("branch", "<default>"),
                        ),
                    )
                )
            else:
                plan.append(
                    (
                        e,
                        "unrebuildable",
                        f"target 不存在且无 remote_url；请用 --target {name}=PATH 或手工处理",
                    )
                )
        else:
            plan.append((e, "unhandled", f"status={status}; 请用 --target 或手工处理"))

    print(f"[llmw] rebuild 计划（{len(plan)} 个 entry）:", file=sys.stderr)
    for e, act, detail in plan:
        print("  {} :: {} -> {}".format(e.get("symlink"), act, detail), file=sys.stderr)

    actionable = [p for p in plan if p[1] in ("relink", "clone_relink")]
    if not actionable:
        print("[llmw] 无需动作", file=sys.stderr)
        return (None, 0)
    if not yes:
        if not sys.stdin.isatty():
            return (
                "非 TTY 下 rebuild 需要 --yes 确认（或先 `external list` 检视状态后用 `--target NAME=PATH` 指定",
                2,
            )
        try:
            ans = input("执行上述计划?[y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            return ("rebuild 已取消", 0)

    clone_failed = []
    relink_failed = []
    for e, act, _ in actionable:
        name = e.get("symlink", "")
        override = overrides.get(name)
        target_str = override if override else e.get("target", "")
        target = _expand(target_str)
        symlink_path = _external_dir(wiki_root) / name
        if act == "clone_relink":
            remote = e.get("remote_url", "")
            branch = e.get("branch", "")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["git", "clone", remote, str(target)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except FileNotFoundError:
                return ("git 不在 PATH，无法 clone", 2)
            except subprocess.CalledProcessError as ex:
                clone_failed.append(f"{name}: clone {remote} → {target} 失败 ({ex})")
                continue
            if branch:
                try:
                    subprocess.run(
                        ["git", "-C", str(target), "checkout", branch],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except subprocess.CalledProcessError as ex:
                    clone_failed.append(f"{name}: checkout '{branch}' 失败 ({ex})")
                    continue
            stored = _target_for_anchor(target)
            for ent in entries:
                if ent.get("symlink") == name:
                    ent["target"] = stored
                    break
        try:
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            symlink_path.symlink_to(target)
        except OSError as ex:
            relink_failed.append(f"{name}: symlink 创建失败 ({ex})")
    if clone_failed or relink_failed:
        try:
            save(anchor_path, entries)
        except ValueError as e:
            return (str(e), 1)
        return (
            "rebuild 部分失败:{}{}".format(
                "\n  clone: {}".format("; ".join(clone_failed)) if clone_failed else "",
                "\n  relink: {}".format("; ".join(relink_failed)) if relink_failed else "",
            ).strip(),
            2,
        )
    try:
        save(anchor_path, entries)
    except ValueError as e:
        return (str(e), 1)
    print(f"[llmw] rebuild 完成（{len(actionable)} 个动作执行）", file=sys.stderr)
    return (None, 0)


# ---------- main ----------


def build_subparsers(sub) -> None:
    """把 add / remove / list / rebuild 挂到给定的 subparsers action。

    external 子树的 flag SSOT 在此——llmw.cli.build_parser() 经本函数组合出完整
    命令树；无独立入口。
    """
    p_add = sub.add_parser(
        "add",
        help="注册 entry + 建 symlink（target 必须是已存在路径）",
    )
    p_add.add_argument("target", help="target 路径（已存在；支持 ~ 与相对路径）")
    p_add.add_argument(
        "--name",
        required=True,
        dest="entry_name",
        help="anchor entry 名（kebab-case，与 symlink 同名）",
    )
    p_add.add_argument("--notes", default=None, help="可选自由 notes")
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser(
        "remove",
        help="删 entry + 删 symlink（target 仓本体永不触碰）",
    )
    p_rm.add_argument("entry_name", help="anchor entry 名")
    p_rm.set_defaults(func=cmd_remove)

    p_list = sub.add_parser(
        "list",
        help="表 NAME/TARGET/REMOTE/BRANCH/STATUS（ok/missing/dead/drift）",
    )
    p_list.add_argument("--json", action="store_true", dest="json", help="机器可读 JSON")
    p_list.set_defaults(func=cmd_list)

    p_re = sub.add_parser(
        "rebuild",
        help="按 anchor 重建 symlink（target 不存在时按 remote_url clone + checkout branch）",
    )
    p_re.add_argument(
        "--target",
        action="append",
        dest="target",
        metavar="NAME=PATH",
        help="覆盖 entry 的 target（跨 home 布局时；可重复）",
    )
    p_re.add_argument("--yes", "-y", action="store_true", help="跳过单次确认")
    p_re.set_defaults(func=cmd_rebuild)


def dispatch(wiki_root: Path, args) -> int:
    """cli.py external dispatch 入口：按 args.func 分派到 cmd_*。"""
    err, code = args.func(wiki_root, args)
    if err:
        print(f"[llmw] error: {err}", file=sys.stderr)
    return code
