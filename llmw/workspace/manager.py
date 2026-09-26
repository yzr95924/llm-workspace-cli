"""workspace 级业务: init / config / list"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from llmw._compat import TOMLDecodeError
from llmw.backends import DEFAULT_BACKEND, KNOWN_BACKENDS
from llmw.errors import (
    InvalidConfigKey,
    KeyNotUnsettable,
    ModelDefaultAmbiguous,
    ModelDefaultNotSet,
    ModelNotInRegistry,
    RegistryMissing,
    SchemaVersionUnsupported,
    WikiDirMissing,
    WikiNotFound,
    WorkspaceExists,
)
from llmw.workspace import store as ws_store
from llmw.workspace.gitignore import ensure_workspace_gitignore

# config KEY 白名单: name -> (can_set, can_unset, type)
CONFIG_KEYS = {
    "enter_cli": (True, True, str),  # → workspace_local.toml；白名单见 _check_enter_cli
    "created_at": (False, False, str),  # 只读, workspace.toml
    "schema_version": (False, False, int),  # 只读, workspace.toml
}

# 路由到 workspace_local.toml 的运行时配置 key (主机相关)。schema v2 起这些字段
# 不再存于 workspace.toml (结构数据)；config get/set/unset 据 LOCAL_KEYS 决定落点。
# (enter_byobu 已删除——窗口路径全环境成立。)
LOCAL_KEYS = frozenset({"enter_cli"})


def _check_enter_cli(value: str) -> None:
    """enter_cli 白名单校验；非白名单值抛 InvalidConfigKey。

    白名单真源是 llmw/backends.py 的 KNOWN_BACKENDS（单一真源）。
    """
    if value not in KNOWN_BACKENDS:
        raise InvalidConfigKey(
            f"enter_cli 值 '{value}' 不在白名单",
            hint=f"可选: {', '.join(sorted(KNOWN_BACKENDS))}",
        )


# ===== init =====


def _is_effectively_empty(path: Path) -> bool:
    """目录是否视为空（忽略 .git / .gitignore，允许 git 空仓直接 init）。

    忽略 .gitignore 的必要性：它是 init 自己写的文件，不忽略会挡住自身 re-init（自反矛盾）。
    """
    ignored = {".git", ".gitignore"}
    return all(entry.name in ignored for entry in path.iterdir())


def init(path: Path, display_name: str = "LLM Wiki Workspace") -> Path:
    """初始化 workspace 根；git 由用户自理（CLI 不碰 git；git 空仓允许直接 init）。"""
    path = path.resolve()
    if path.exists():
        if not _is_effectively_empty(path):
            raise WorkspaceExists(
                f"路径已存在且非空: {path}",
                hint="指定空目录或先备份内容（仅含 .git / .gitignore 的 git 空仓可直接 init）",
            )
    else:
        path.mkdir(parents=True)

    ws_store.create_skeleton(path)

    # .gitignore 无条件生成（便于后续补 git）；registry 空骨架落盘（save 内置 chmod 600）
    ensure_workspace_gitignore(path)

    from llmw.models.store import (
        create_skeleton as create_models_skeleton,
        save as save_models,
    )

    save_models(path, create_models_skeleton())

    print(f"[llmw] workspace 已初始化于 {path}", file=sys.stdout)
    print(
        f"[llmw] cd {path} 后可用 `llmw wiki add <name>` 新建第一个 wiki",
        file=sys.stdout,
    )
    return path


# ===== config =====


def _check_key(key: str) -> tuple:
    if key not in CONFIG_KEYS:
        raise InvalidConfigKey(
            f"KEY '{key}' 不在白名单",
            hint=f"可用 KEY: {', '.join(sorted(CONFIG_KEYS.keys()))}",
        )
    return CONFIG_KEYS[key]


def _current_value(ws, local, key):
    """从正确的源取 KEY 当前值：LOCAL_KEYS → workspace_local.toml，其余 → workspace.toml。"""
    if key in LOCAL_KEYS:
        return getattr(local, key, None)
    return getattr(ws, key, None)


def config_get(workspace_root: Path, key: Optional[str]) -> None:
    """无 KEY: dump (local 运行时 + workspace 结构); 有 KEY: 打印该字段值。"""
    from llmw.workspace import local_store

    ws = ws_store.load(workspace_root)
    local = local_store.load(workspace_root)
    if key is None:
        # dump
        print(f"# workspace: {workspace_root}")
        if local.enter_cli is not None:
            print(f"enter_cli = {local.enter_cli}")
        else:
            print(f"# enter_cli: <unset> (= {DEFAULT_BACKEND})")
        print(f"created_at = {ws.created_at}")
        print(f"schema_version = {ws.schema_version}")
        wikis = list(ws.wikis.keys())
        if wikis:
            print(f"wikis = {', '.join(sorted(wikis))}")
        else:
            print("# wikis: <empty>")
        return

    if key not in CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在白名单")
    val = _current_value(ws, local, key)
    if val is None:
        print("<unset>")
    else:
        print(val)


def config_set(workspace_root: Path, key: str, value: str) -> None:
    """所有可 set 的 KEY 都路由到 workspace_local.toml (结构 KEY 全只读)。"""
    from llmw.workspace import local_store

    can_set, _, expected_type = _check_key(key)
    if not can_set:
        raise InvalidConfigKey(f"KEY '{key}' 不可 set（只读）")
    if key == "enter_cli":
        _check_enter_cli(value)
    parsed = expected_type(value)
    local = local_store.load(workspace_root)
    setattr(local, key, parsed)
    local_store.save(workspace_root, local)
    print(f"✓ {key} = {value!r}", file=sys.stdout)


def config_unset(workspace_root: Path, key: str) -> None:
    """所有可 unset 的 KEY 都路由到 workspace_local.toml (结构 KEY 全只读)。"""
    from llmw.workspace import local_store

    can_set, can_unset, _ = _check_key(key)
    if not can_unset:
        raise KeyNotUnsettable(f"KEY '{key}' 不可 unset")
    local = local_store.load(workspace_root)
    setattr(local, key, None)
    local_store.save(workspace_root, local)
    print(f"✓ {key} unset", file=sys.stdout)


def config_interactive(workspace_root: Path) -> None:
    """TTY 下 `llmw config` 无参数进入; 非 TTY 打印字段列表后退出 0。"""
    from llmw.workspace import local_store

    if not sys.stdin.isatty():
        print("[llmw] config 子命令: get KEY / set KEY VALUE / unset KEY")
        print(f"[llmw] workspace: {workspace_root}")
        print("[llmw] 可用 KEY:")
        for i, key in enumerate(CONFIG_KEYS, 1):
            can_set, can_unset, _ = CONFIG_KEYS[key]
            ro = " (只读)" if not can_set else ""
            print(f"  {i}. {key}{ro}")
        return

    ws = ws_store.load(workspace_root)
    local = local_store.load(workspace_root)
    keys = list(CONFIG_KEYS.keys())
    while True:
        print("\nworkspace 配置项 (local 运行时 + workspace.toml 结构):")
        for i, key in enumerate(keys, 1):
            can_set, can_unset, _ = CONFIG_KEYS[key]
            val = _current_value(ws, local, key)
            cur = repr(val) if val is not None else "<unset>"
            ro = " (只读)" if not can_set else ""
            print(f"  {i}. {key}{ro}    当前: {cur}")

        try:
            choice = input(f"\n选择要编辑的项 [1-{len(keys)}, q 退出]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice.lower() in ("q", ""):
            return
        try:
            idx = int(choice) - 1
            key = keys[idx]
        except (ValueError, IndexError):
            print("[llmw] 输入无效，重试")
            continue

        can_set, _, _ = CONFIG_KEYS[key]
        if not can_set:
            print(f"⚠ {key} 是只读字段，无法编辑")
            try:
                again = input("继续编辑？[Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if again in ("n", "no"):
                return
            continue

        cur = _current_value(ws, local, key) or ""
        prompt = "输入新值（回车跳过 / '-' 清空）: "
        try:
            new_val = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if new_val == "":
            pass  # 跳过
        elif new_val == "-":
            config_unset(workspace_root, key)
            local = local_store.load(workspace_root)  # 编辑只动 local
        else:
            config_set(workspace_root, key, new_val)
            local = local_store.load(workspace_root)

        try:
            again = input("继续编辑？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if again in ("n", "no"):
            return


# ===== list =====


def _gather_wiki_rows(
    workspace_root: Path, ws, tag_filter: Optional[List[str]]
) -> List[dict]:
    """list 聚合：遍历 registry + 读 metadata + resolve model + last_activity。

    单 wiki 元数据损坏 → warning + 降级空值（列表不整体失败）；ws / registry 预载后循环复用。
    """
    from llmw.models.resolve import resolve_for_wiki
    from llmw.models.store import load as registry_load

    # registry 预载一次；失败 → None，resolve 内部按原语义重载并抛对应异常
    # （循环内 except 统一降级 model_info=None）
    try:
        registry = registry_load(workspace_root)
    except Exception:
        registry = None

    rows = []
    for name in sorted(ws.wikis.keys()):
        entry = ws.wikis[name]
        wiki_path = workspace_root / entry.path
        exists = wiki_path.is_dir()
        meta = None
        if exists:
            toml_p = wiki_path / "wiki_metadata.toml"
            if toml_p.is_file():
                from llmw.wiki.store import load as wiki_load

                try:
                    meta = wiki_load(wiki_path)
                except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
                    print(
                        f"[llmw] warning: 无法读取 {name} 的 wiki_metadata.toml: "
                        f"{type(e).__name__}: {e}",
                        file=sys.stderr,
                    )
                    meta = None

        if tag_filter:
            tags = meta.tags if meta else []
            if not all(t in tags for t in tag_filter):
                continue

        # 通过 resolve 拿 model 来源（若失败则不阻断 list，回落 meta.model / 空值，表格显示 "-"）
        model_info = None
        try:
            entry_obj = resolve_for_wiki(workspace_root, name, ws=ws, registry=registry)
            model_info = {
                "model_id": entry_obj.model_id,
                "name": entry_obj.name,
                "source": "wiki override"
                if (meta and meta.model)
                else "registry default",
            }
        except (
            WikiNotFound,
            WikiDirMissing,
            ModelNotInRegistry,
            ModelDefaultNotSet,
            ModelDefaultAmbiguous,
            RegistryMissing,
            OSError,
            TOMLDecodeError,
        ):
            model_info = None

        # last_activity: 派生自 <wiki>/wiki/log.md mtime(与 wiki show 同款派生,见 wiki/manager.py:show)
        last_activity = None
        if exists:
            log_md_p = wiki_path / "wiki" / "log.md"
            if log_md_p.is_file():
                last_activity = datetime.fromtimestamp(
                    log_md_p.stat().st_mtime, tz=timezone.utc
                ).isoformat()

        rows.append(
            {
                "name": name,
                "path": entry.path,
                "exists": exists,
                "display_name": meta.display_name if meta else "",
                "tags": list(meta.tags) if meta else [],
                "model": model_info["model_id"]
                if model_info
                else (meta.model if meta else None),
                "model_source": model_info["source"] if model_info else None,
                "created_at": meta.created_at if meta else None,
                "last_activity": last_activity,
            }
        )
    return rows


def _render_list_json(rows: List[dict]) -> None:
    import json

    out = [
        {
            "name": r["name"],
            "path": r["path"],
            "display_name": r["display_name"] or None,
            "tags": r["tags"],
            "model": r["model"],
            "model_source": r["model_source"],
            "wiki_dir_exists": r["exists"],
            "last_activity": r["last_activity"],
        }
        for r in rows
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _short_time(value):
    """表格展示用短时间：'2026-08-22T12:34:56+00:00' → '2026-08-22 12:34'；缺失返回 '-'。"""
    if not value:
        return "-"
    return f"{value[:10]} {value[11:16]}"


def _disp_width(text):
    """显示宽度：CJK / 全角字符按 2 列计，其余按 1 列计（对齐用，非精确 Unicode 标准）。"""
    w = 0
    for ch in text:
        code = ord(ch)
        if (
            0x1100 <= code <= 0x115F  # Hangul Jamo
            or 0x2E80 <= code <= 0xA4CF  # CJK 部首 / 康熙 / 注音等
            or 0xAC00 <= code <= 0xD7A3  # Hangul 音节
            or 0xF900 <= code <= 0xFAFF  # CJK 兼容表意
            or 0xFE30 <= code <= 0xFE4F  # CJK 兼容形式
            or 0xFF00 <= code <= 0xFF60  # 全角形式
            or 0xFFE0 <= code <= 0xFFE6
            or 0x20000 <= code <= 0x3FFFD  # CJK 扩展 A+
        ):
            w += 2
        else:
            w += 1
    return w


def _disp_pad(text, width):
    """按显示宽度右补空格到 width 列（str.ljust 对中文会少补，导致列错位）。"""
    return text + " " * max(0, width - _disp_width(text))


def _render_list_table(rows: List[dict]) -> None:
    """精简单行表格（时间列短格式，完整时间戳走 --json）。

    列宽按显示宽度计（中文 2 列）；行 prefix 固定 2 列，保证列不顶歪。
    """
    created_cells = [_short_time(r["created_at"]) for r in rows]
    last_activity_cells = [_short_time(r["last_activity"]) for r in rows]
    model_cells = [r["model"] or "-" for r in rows]
    name_w = max(_disp_width(r["name"]) for r in rows + [{"name": "NAME"}])
    created_w = max(_disp_width(c) for c in created_cells + ["CREATED"])
    last_activity_w = max(
        _disp_width(c) for c in last_activity_cells + ["LAST_ACTIVITY"]
    )
    model_w = max(_disp_width(c) for c in model_cells + ["MODEL"])
    print(
        f"  {_disp_pad('NAME', name_w)}  "
        f"{_disp_pad('CREATED', created_w)}  "
        f"{_disp_pad('LAST_ACTIVITY', last_activity_w)}  "
        f"{_disp_pad('MODEL', model_w)}"
    )
    for r, created, last_act, model_cell in zip(
        rows, created_cells, last_activity_cells, model_cells
    ):
        prefix = "⚠ " if not r["exists"] else "  "
        print(
            f"{prefix}{_disp_pad(r['name'], name_w)}  "
            f"{_disp_pad(created, created_w)}  "
            f"{_disp_pad(last_act, last_activity_w)}  "
            f"{_disp_pad(model_cell, model_w)}"
        )


def list_wikis(
    workspace_root: Path, as_json: bool = False, tag_filter: Optional[List[str]] = None
) -> int:
    """聚合与渲染分离（_gather_wiki_rows + _render_*）；输出到 stdout。"""
    ws = ws_store.load(workspace_root)
    rows = _gather_wiki_rows(workspace_root, ws, tag_filter)

    if as_json:
        _render_list_json(rows)
        return 0

    if not rows:
        print("# (no wikis registered)")
        return 0
    _render_list_table(rows)
    return 0
