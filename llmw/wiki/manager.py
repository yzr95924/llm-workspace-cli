"""wiki 级业务: add / remove / rename / show / config / stop"""

import errno
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from llmw import WIKI_FORMAT_VERSION, __version__
from llmw._compat import TOMLDecodeError
from llmw.errors import (
    BackupFailed,
    ByobuCommandFailed,
    ByobuNotFound,
    InvalidConfigKey,
    InvalidWikiName,
    KeyNotUnsettable,
    MissingRequiredFlag,
    ModelDefaultAmbiguous,
    ModelDefaultNotSet,
    ModelNotInRegistry,
    MultipleRunningSessions,
    NoRunningSession,
    PurgeRequiresConfirmation,
    SchemaVersionUnsupported,
    StopRequiresConfirmation,
    WikiDirMissing,
    WikiExists,
    WikiNotFound,
)
from llmw.models.manager import require_model_in_registry
from llmw.models.resolve import resolve_for_wiki
from llmw.fsutil import now_iso8601, safe_rmtree
from llmw.wiki import byobu, init_wiki
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store
from llmw.workspace.gitignore import ensure_workspace_gitignore


def resolve_wiki_path(workspace_root: Path, name: str) -> Path:
    """查注册表 → wiki 绝对路径；未注册 → WikiNotFound（各命令共用唯一实现）。"""
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    return workspace_root / ws.wikis[name].path


def _print_git_hint(wiki_dir: Path) -> None:
    """git 红线：CLI 不碰 git——落盘后打印手动 hint（.gitkeep 已由 init_wiki 放好）。"""
    print(f"[llmw] wiki 已落盘为纯目录树: {wiki_dir}", file=sys.stdout)
    print("[llmw] 若需 git 版本控制,请手动执行:", file=sys.stdout)
    print(f"[llmw]   cd {wiki_dir}", file=sys.stdout)
    print(
        "[llmw]   git init && git symbolic-ref HEAD refs/heads/main",
        file=sys.stdout,
    )
    print(
        '[llmw]   git add . && git commit -m "Initial wiki scaffold"',
        file=sys.stdout,
    )
    print(
        "[llmw] .gitkeep 占位文件已放入空目录;后续 raw/ 真实文件由你 `git add` 后纳入跟踪。",
        file=sys.stdout,
    )


def _tags_submenu(cur_tags: List[str]) -> List[str]:
    """tags 交互子菜单（a 添加 / r 移除 / s 替换 / d 完成）；add 与 config 交互共用。"""
    while True:
        print(f"  tags [当前: {cur_tags}]: <a 添加 / r 移除 / s 替换 / d 完成>")
        try:
            op = input("    操作: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if op == "a":
            t = input("    新 tag: ").strip()
            if t:
                wiki_store.validate_tag(t)
                if t not in cur_tags:
                    cur_tags.append(t)
        elif op == "r":
            if not cur_tags:
                print("    (空)")
                continue
            for i, t in enumerate(cur_tags):
                print(f"      {i + 1}. {t}")
            try:
                idx = int(input("    移除编号: ").strip()) - 1
                if 0 <= idx < len(cur_tags):
                    cur_tags.pop(idx)
            except (ValueError, EOFError, KeyboardInterrupt):
                pass
        elif op == "s":
            t = input("    全部 tags (逗号分隔): ").strip()
            new_tags = [x.strip() for x in t.split(",") if x.strip()]
            for x in new_tags:
                wiki_store.validate_tag(x)
            cur_tags = new_tags
        elif op == "d":
            break
    return cur_tags


def _interactive_fill_metadata(workspace_root, wiki_dir, meta):
    """交互填充 display_name / description / tags / model（model 走 registry 校验）。"""

    def ask(label, cur):
        suffix = " [当前: <未设置>]" if not cur else f" [当前: {cur!r}]"
        try:
            v = input(f"  {label}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise
        return v

    # display_name
    v = ask("display_name", meta.display_name)
    if v:
        meta.display_name = v
    # description
    v = ask("description", meta.description)
    if v:
        meta.description = v
    # tags
    meta.tags = _tags_submenu(list(meta.tags))

    # model（与 config set 同校验：须在 registry 中；TTY 下不阻断 add，只警告——用户可稍后 config set）
    v = ask("model", meta.model or "")
    if v:
        try:
            require_model_in_registry(workspace_root, v)
        except (ModelNotInRegistry, ModelDefaultNotSet) as e:
            print(
                f"    [校验失败] {e.message}——model 字段未写入，稍后可用 "
                f"`llmw wiki --name={meta.name} config set model=...` 补",
                file=sys.stderr,
            )
        else:
            meta.model = v

    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print("[llmw] metadata 已写入 wiki_metadata.toml", file=sys.stdout)


def add(
    workspace_root: Path,
    name: str,
    topic: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Path:
    wiki_store.validate_name(name)

    ws = ws_store.load(workspace_root)
    if name in ws.wikis:
        raise WikiExists(f"wiki '{name}' 已存在")

    if model is not None:
        require_model_in_registry(workspace_root, model)

    wiki_dir = workspace_root / name

    init_wiki.check_not_initialized(wiki_dir)

    if not sys.stdin.isatty():
        missing = []
        if display_name is None:
            missing.append("--display-name")
        if description is None:
            missing.append("--description")
        if not tags:
            missing.append("--tag")
        if model is None:
            missing.append("--model")
        if missing:
            raise MissingRequiredFlag(
                f"非 TTY 下 add 缺 metadata flag: {', '.join(missing)}",
                hint="补齐 flag 重试，或在 TTY 下用交互模式",
            )

    if topic is None:
        topic = name

    # 空目录可已存在；覆盖场景已由 check_not_initialized 阻断
    wiki_dir.mkdir(parents=False, exist_ok=True)

    # 先落 metadata（UTC created_at），SETUP_DATE 由其派生（与 checker 读同字段）；
    # [:16] = YYYY-MM-DD HH:MM（字节金标准粒度）
    meta = wiki_store.create_skeleton(wiki_dir, name, topic)
    setup_date = (meta.created_at or "").replace("T", " ")[:16]

    init_wiki.render_and_write(
        wiki_dir,
        topic,
        setup_date,
        cli_version=__version__,
        format_version=WIKI_FORMAT_VERSION,
    )

    if sys.stdin.isatty():
        try:
            _interactive_fill_metadata(workspace_root, wiki_dir, meta)
        except (EOFError, KeyboardInterrupt):
            print("\n[llmw] 跳过剩余 metadata", file=sys.stderr)
        meta = wiki_store.load(wiki_dir)  # reload
    else:
        if display_name is not None:
            meta.display_name = display_name
        if description is not None:
            meta.description = description
        if tags:
            meta.tags = tags
        if model is not None:
            meta.model = model
        meta.bump()
        wiki_store.save(wiki_dir, meta)

    ws.wikis[name] = ws_store.WikiEntry(
        name=name,
        path=name,
        created_at=now_iso8601(),
    )
    ws_store.save(workspace_root, ws)

    print(f"[llmw] wiki 已创建: {name} ({wiki_dir})", file=sys.stdout)
    # git 红线：统一打印手动 hint（--git 为 vestigial flag）
    _print_git_hint(wiki_dir)
    return wiki_dir


def _purge_with_backup(
    workspace_root: Path,
    wiki_path: Path,
    name: str,
    no_backup: bool,
) -> None:
    """purge 物理删除：默认备份到 .llmw-trash/（失败阻断不删）；--no-backup 直接 rmtree。

    Raises: BackupFailed（备份任一失败）。
    """
    # 先确保 .gitignore 含 .llmw-trash/ 排除（失败只 warning，不阻断备份）
    try:
        ensure_workspace_gitignore(workspace_root)
    except OSError as e:
        print(
            f"[llmw] warning: workspace .gitignore 更新失败: {e}——"
            f"建议手动确保含 `.llmw-trash/` 排除行",
            file=sys.stderr,
        )

    if no_backup:
        safe_rmtree(wiki_path)
        print(f"[llmw] --no-backup: 直接删除 {wiki_path}", file=sys.stdout)
        return

    # 备份名带时间戳（冒号不能进路径，剥掉）
    ts = now_iso8601().replace(":", "")
    trash_root = workspace_root / ".llmw-trash"
    backup_path = trash_root / f"{name}-{ts}"

    try:
        trash_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise BackupFailed(
            f"无法创建备份目录 {trash_root}: {e}",
            hint="检查 workspace 目录权限",
        )

    if backup_path.exists():
        # 同一秒内两次 purge 才可能撞上;极少但要给清晰错误
        raise BackupFailed(
            f"备份目标已存在: {backup_path}",
            hint="同一秒内连续 purge 两次? 重试",
        )

    try:
        # 同一 FS 下 POSIX rename 原子（wiki_path 与 backup_path 同在 workspace）
        wiki_path.rename(backup_path)
    except OSError as e:
        raise BackupFailed(
            f"备份移动失败: {wiki_path} → {backup_path}: {e}",
            hint="检查磁盘空间 + 权限; --no-backup 跳过备份直接删",
        )

    print(f"[llmw] 备份: {backup_path}", file=sys.stdout)


def remove(
    workspace_root: Path,
    name: str,
    purge: bool = False,
    yes: bool = False,
    no_backup: bool = False,
) -> None:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(f"wiki '{name}' 不在当前 workspace 中")

    wiki_path = resolve_wiki_path(workspace_root, name)

    if purge and not yes:
        if not sys.stdin.isatty():
            raise PurgeRequiresConfirmation(
                "非 TTY 下 --purge 需要 --yes 确认",
                hint="加 --yes 或在 TTY 下手动确认",
            )
        try:
            ans = (
                input(f"将删除 {wiki_path} 子目录及所有内容，确认？[y/N]: ")
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            print()
            ans = "n"
        if ans not in ("y", "yes"):
            print("[llmw] 取消")
            return

    del ws.wikis[name]
    ws_store.save(workspace_root, ws)

    if purge:
        if wiki_path.is_dir():
            _purge_with_backup(workspace_root, wiki_path, name, no_backup=no_backup)

    suffix = " 并删除子目录" if purge else ""
    print(f"[llmw] wiki '{name}' 已取消注册{suffix}", file=sys.stdout)


def stop(
    name: str,
    window_suffix: Optional[str] = None,
    yes: bool = False,
) -> int:
    """kill wiki 的带标窗口：0 → NoRunningSession；N 且未给 suffix → MultipleRunningSessions；恰 1 → 确认后 kill。

    不查注册表——窗口枚举即现实（关是低频高危动作，显式消歧优先）。
    """
    if not byobu.byobu_available():
        raise ByobuNotFound(
            "byobu-tmux 不在 PATH",
            hint="安装 byobu（如 apt install byobu / brew install byobu）",
        )
    window_name = byobu.window_name_for(name, window_suffix) if window_suffix else None

    candidates = [
        r
        for r in byobu.list_windows()
        if r.wiki == name and (window_name is None or r.window_name == window_name)
    ]
    if not candidates:
        raise NoRunningSession(
            f"wiki '{name}' 没有运行中的 session",
            hint="运行 `llmw status` 查看所有运行中的窗口",
        )
    if len(candidates) > 1:
        listing = "\n".join(
            f"  {r.window_name}  (session {r.session}, {r.window_id})"
            for r in candidates
        )
        raise MultipleRunningSessions(
            f"wiki '{name}' 有 {len(candidates)} 个运行中的窗口：\n{listing}",
            hint="加 --window-suffix=SUFFIX 指定目标窗口（如 --window-suffix=ingest）",
        )

    row = candidates[0]
    wid, wname, session = row.window_id, row.window_name, row.session
    dead = row.dead == byobu.DEAD_FLAG

    if not yes:
        if not _confirm_stop(name, wname, dead):
            print("[llmw] 取消")
            return 0

    if not byobu.kill_window(wid):
        raise ByobuCommandFailed(
            f"kill-window 失败 (window={wid})",
            hint="窗口可能已被外部关闭；运行 `llmw status` 确认",
        )
    suffix_note = "（已退出残留）" if dead else ""
    print(
        f"[llmw] ✓ 已终止窗口 '{wname}' (session '{session}'){suffix_note}",
        file=sys.stdout,
    )
    return 0


def _confirm_stop(name: str, wname: str, dead: bool) -> bool:
    if not sys.stdin.isatty():
        raise StopRequiresConfirmation(
            "非 TTY 下 stop 需要 --yes 确认",
            hint="加 --yes 或在 TTY 下手动确认",
        )
    status_desc = "清理已退出残留" if dead else "运行中 agent 将被终止"
    try:
        ans = (
            input(
                f"将 kill 窗口 '{wname}'（wiki '{name}'，{status_desc}），确认？[y/N]: "
            )
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        print()
        ans = "n"
    return ans in ("y", "yes")


def _restore_meta(meta, old: str, old_topic: str, wiki_dir: Path) -> None:
    """rename 回滚：meta.name/topic 恢复 + save（best-effort，失败打 warning）。"""
    meta.name = old
    meta.topic = old_topic
    try:
        wiki_store.save(wiki_dir, meta)
    except OSError as rollback_err:
        print(
            f"[llmw] warning: 回滚 metadata 失败: {rollback_err}; "
            f"{wiki_dir}/wiki_metadata.toml 可能停留在改名后的 name，请手动检查",
            file=sys.stderr,
        )


def rename(
    workspace_root: Path,
    old: str,
    new: str,
    as_json: bool = False,
    quiet: bool = False,
) -> None:
    """rename wiki ``old`` → ``new``：3 阶段原地 rename（metadata → 目录 → workspace.toml）+ 廉价回滚。

    子目录走 POSIX rename（O(1)，raw/ 零拷贝）；topic 默认值 == old 时同步。
    失败策略：每步失败都回滚到 rename 前一致状态。
    Raises: InvalidWikiName / WikiNotFound / WikiExists / WikiDirMissing / SchemaVersionUnsupported / OSError。
    """
    wiki_store.validate_name(new)
    if old == new:
        raise InvalidWikiName(
            f"--old 与 --new 均为 '{old}', 无变更",
            hint="提供不同的 new 名",
        )

    ws = ws_store.load(workspace_root)
    if old not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{old}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    if new in ws.wikis:
        raise WikiExists(f"wiki '{new}' 已存在")

    old_path = resolve_wiki_path(workspace_root, old)
    new_path = workspace_root / new
    if new_path.exists():
        # 防 registry 与 fs 不一致 (残留空目录 / 手工 mkdir)
        raise WikiExists(
            f"目标路径已存在: {new_path}",
            hint="清理后重试, 或选别的 new 名",
        )
    if not old_path.is_dir() or not (old_path / "wiki_metadata.toml").is_file():
        # registry 有登记但磁盘目录不完整 (被手动移走 / 删除 / 残缺)
        raise WikiDirMissing(
            f"wiki 目录或 wiki_metadata.toml 缺失: {old_path}",
            hint=f"registry 仍登记 '{old}', 但磁盘目录不完整; 检查是否被手动移走",
        )

    # created_at 跨 rename 保留,维持时间锚点
    created_at = ws.wikis[old].created_at

    # ===== Phase 1: 原地改 old_path 的 metadata (name→new) =====
    # wiki_store.save 走 atomic_write (tmp + rename), 失败不留半成品 → old_path 完全不动。
    # 目录名此刻仍为 old, 与 metadata.name=new 短暂不一致, Phase 2 原子 rename 后即对齐。
    meta = wiki_store.load(old_path)  # SchemaVersionUnsupported / TOMLDecodeError 透传
    old_topic = meta.topic
    meta.name = new
    if meta.topic == old:
        meta.topic = new
    meta.bump()
    wiki_store.save(old_path, meta)

    # ===== Phase 2: 原子重命名 old_path → new_path (O(1), 同 FS) =====
    # POSIX rename 同 FS 下只改目录项, 不动 inode 数据 / symlink → raw/ 下大量文件零拷贝。
    # 跨 FS 抛 EXDEV (workspace 目录应同 FS; NFS 不安全, 见 AGENTS.md)。
    try:
        old_path.rename(new_path)
    except OSError as e:
        # 回滚 Phase 1: metadata 的 name/topic 恢复成 rename 前
        _restore_meta(meta, old, old_topic, old_path)
        if e.errno == errno.EXDEV:
            print(
                "[llmw] hint: old/new 不在同一文件系统 (EXDEV); workspace 目录应位于"
                "同一 FS, NFS 挂载不安全 (见 AGENTS.md)",
                file=sys.stderr,
            )
        raise

    # ===== Phase 3: 切换 workspace.toml (del old / add new) =====
    try:
        ws.wikis[new] = ws_store.WikiEntry(name=new, path=new, created_at=created_at)
        del ws.wikis[old]
        ws_store.save(workspace_root, ws)
    except (OSError, TOMLDecodeError):
        # 回滚 Phase 2 + 1: fs rename 回来 + metadata 恢复
        try:
            new_path.rename(old_path)
            _restore_meta(meta, old, old_topic, old_path)
        except OSError as rollback_err:
            print(
                f"[llmw] warning: 回滚失败: {rollback_err}; fs/registry 可能不一致, "
                f"手动检查 {new_path} 与 workspace.toml",
                file=sys.stderr,
            )
        raise

    topic_changed = old_topic == old

    if as_json:
        out = {
            "old": old,
            "new": new,
            "path": str(new_path),
            "topic_changed": topic_changed,
            "topic_old": old_topic if topic_changed else None,
            "topic_new": new if topic_changed else None,
            "created_at": created_at,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not quiet:
        print(f"[llmw] wiki 已重命名: {old} → {new}", file=sys.stdout)
        print(f"[llmw]   path: {new_path}", file=sys.stdout)
        if topic_changed:
            print(
                f"[llmw]   topic: {old_topic} → {new} (随 name 同步)",
                file=sys.stdout,
            )
        print(f"[llmw]   created_at 保留: {created_at}", file=sys.stdout)
    else:
        # 安静模式: 只保留主信息行, 抑制 path / topic / created_at 详情
        print(f"[llmw] wiki 已重命名: {old} → {new}", file=sys.stdout)


def _show_collect(workspace_root: Path, name: str) -> Dict:
    wiki_path = resolve_wiki_path(workspace_root, name)
    meta = None
    if (wiki_path / "wiki_metadata.toml").is_file():
        try:
            meta = wiki_store.load(wiki_path)
        except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
            print(
                f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            meta = None

    claude_md_p = wiki_path / "CLAUDE.md"
    raw_p = wiki_path / "raw"
    wiki_sub_p = wiki_path / "wiki"
    claude_md_exists = claude_md_p.is_file()
    raw_count = sum(1 for _ in raw_p.rglob("*") if _.is_file()) if raw_p.is_dir() else 0
    wiki_count = (
        sum(1 for _ in wiki_sub_p.rglob("*.md") if _.is_file())
        if wiki_sub_p.is_dir()
        else 0
    )
    # last_activity 派生自 log.md mtime（不吃 skill 配合；缺失 → None）
    last_activity = None
    log_md_p = wiki_sub_p / "log.md"
    if log_md_p.is_file():
        last_activity = datetime.fromtimestamp(
            log_md_p.stat().st_mtime, tz=timezone.utc
        ).isoformat()

    # 通过 resolve 拿最终 model + 来源
    final_model = None
    model_source = None
    try:
        m = resolve_for_wiki(workspace_root, name)
        final_model = m.model_id
        model_source = "wiki override" if (meta and meta.model) else "registry default"
    except (
        WikiNotFound,
        WikiDirMissing,
        ModelNotInRegistry,
        ModelDefaultNotSet,
        ModelDefaultAmbiguous,
    ):
        # resolve 失败 → 退化：只能从 wiki_metadata.model 推断（不再有 workspace
        # default_model 兜底——该字段已删，"默认 model" 由 registry is_default 表达）。
        final_model = meta.model if meta else None
        if final_model:
            model_source = "wiki.metadata.model"

    return {
        "name": name,
        "path": str(wiki_path),
        "meta": meta,
        "claude_md_exists": claude_md_exists,
        "raw_p": raw_p,
        "wiki_sub_p": wiki_sub_p,
        "raw_count": raw_count,
        "wiki_count": wiki_count,
        "last_activity": last_activity,
        "final_model": final_model,
        "model_source": model_source,
    }


def show(workspace_root: Path, name: str, as_json: bool = False) -> None:
    d = _show_collect(workspace_root, name)
    meta = d["meta"]
    wiki_path = d["path"]
    final_model = d["final_model"]
    model_source = d["model_source"]
    last_activity = d["last_activity"]

    if as_json:
        out = {
            "name": d["name"],
            "path": wiki_path,
            "topic": meta.topic if meta else None,
            "display_name": meta.display_name if meta else None,
            "description": meta.description if meta else None,
            "tags": list(meta.tags) if meta else [],
            "model": final_model,
            "model_source": model_source,
            "schema_version": meta.schema_version if meta else None,
            "created_at": meta.created_at if meta else None,
            "last_activity": last_activity,
            "existence": {
                "claude_md": d["claude_md_exists"],
                "wiki_metadata_toml": meta is not None,
                "raw_dir": d["raw_p"].is_dir(),
                "wiki_dir": d["wiki_sub_p"].is_dir(),
            },
            "counts": {
                "raw_files": d["raw_count"],
                "wiki_pages": d["wiki_count"],
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    created_line = meta.created_at if meta else "-"
    model_line = final_model or "-"
    if model_source:
        model_line += f"  (source: {model_source})"
    rows = [
        ("NAME", d["name"]),
        ("PATH", wiki_path),
        ("TOPIC", meta.topic if meta else "-"),
        ("DISPLAY_NAME", meta.display_name if meta else "-"),
        ("DESCRIPTION", meta.description if meta else "-"),
        ("TAGS", ",".join(meta.tags) if meta and meta.tags else "-"),
        ("MODEL", model_line),
        ("CREATED_AT", created_line),
        ("LAST_ACTIVITY", last_activity or "-"),
        ("CLAUDE_MD", "✓ found" if d["claude_md_exists"] else "✗ missing"),
        ("WIKI_METADATA", "✓ found" if meta else "✗ missing"),
        (
            "RAW_DIR",
            f"{'✓ found' if d['raw_p'].is_dir() else '✗ missing'} ({d['raw_count']} files)",
        ),
        (
            "WIKI_DIR",
            f"{'✓ found' if d['wiki_sub_p'].is_dir() else '✗ missing'} ({d['wiki_count']} pages)",
        ),
    ]
    label_w = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"{label.ljust(label_w)}  {value}")


# wiki config KEY 白名单: name -> (can_set, can_unset)
WIKI_CONFIG_KEYS = {
    "display_name": (True, True),
    "description": (True, True),
    "tags": (True, True),
    "model": (True, True),
    # name / topic / schema_version / created_at / updated_at 全部只读
}


def wiki_config_get(workspace_root: Path, name: str, key: Optional[str]) -> None:
    wiki_dir = resolve_wiki_path(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key is None:
        print(f"# wiki: {name} ({wiki_dir}/wiki_metadata.toml)")
        for k in WIKI_CONFIG_KEYS:
            v = getattr(meta, k)
            print(f"{k} = {v!r}")
        return
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(
            f"KEY '{key}' 不在 wiki 白名单",
            hint=f"可用 KEY: {', '.join(WIKI_CONFIG_KEYS.keys())}",
        )
    val = getattr(meta, key)
    if val is None or val == "" or val == []:
        print("<unset>")
    else:
        print(val if not isinstance(val, list) else ",".join(val))


def wiki_config_set(workspace_root: Path, name: str, key: str, value: str) -> None:
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在 wiki 白名单")
    can_set, _ = WIKI_CONFIG_KEYS[key]
    if not can_set:
        raise InvalidConfigKey(f"KEY '{key}' 不可 set（只读）")
    if not value:
        # 空值语义与 unset 冲突（set 的 "" 若落盘为 None 会写出非法 TOML）——拒绝并指路
        raise InvalidConfigKey(
            f"KEY '{key}' 的 set 值不能为空",
            hint=f"清空该字段请用 `llmw wiki --name={name} config unset {key}`",
        )
    wiki_dir = resolve_wiki_path(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key == "tags":
        new_tags = [t.strip() for t in value.split(",") if t.strip()]
        for t in new_tags:
            wiki_store.validate_tag(t)
        meta.tags = new_tags
    elif key == "model":
        require_model_in_registry(workspace_root, value)
        meta.model = value
    else:
        setattr(meta, key, value)
    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print(f"✓ {key} 已更新", file=sys.stdout)


def wiki_config_unset(workspace_root: Path, name: str, key: str) -> None:
    if key not in WIKI_CONFIG_KEYS:
        raise InvalidConfigKey(f"KEY '{key}' 不在 wiki 白名单")
    can_set, can_unset = WIKI_CONFIG_KEYS[key]
    if not can_unset:
        raise KeyNotUnsettable(f"KEY '{key}' 不可 unset")
    wiki_dir = resolve_wiki_path(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    if key == "tags":
        meta.tags = []
    elif key in ("display_name", "description"):
        setattr(meta, key, "")
    elif key == "model":
        meta.model = None
    meta.bump()
    wiki_store.save(wiki_dir, meta)
    print(f"✓ {key} unset", file=sys.stdout)


def wiki_config_interactive(workspace_root: Path, name: str) -> None:
    """wiki config 无参数: 默认就是交互模式（不要求 TTY）"""
    wiki_dir = resolve_wiki_path(workspace_root, name)
    meta = wiki_store.load(wiki_dir)
    keys = list(WIKI_CONFIG_KEYS.keys())
    while True:
        print(f'\nwiki "{name}" 配置项 ({wiki_dir}/wiki_metadata.toml):')
        for i, key in enumerate(keys, 1):
            v = getattr(meta, key)
            cur = repr(v) if v else "<unset>"
            print(f"  {i}. {key}    当前: {cur}")
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

        if key == "tags":
            # 子菜单与 add 交互共用（_tags_submenu），一处实现两处行为
            meta.tags = _tags_submenu(list(meta.tags))
        elif key == "model":
            # model 是 registry 引用, 必须校验存在; 失败则提示重试, 不退出交互
            # （与 wiki_config_set 行为一致, 但交互式走重试而非 raise, 避免丢失已填字段）
            while True:
                try:
                    new_v = input("输入新值（回车跳过 / '-' 清空）: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break  # 跳过, 不改动 model
                if new_v == "":
                    break  # 跳过
                if new_v == "-":
                    meta.model = None
                    break
                try:
                    require_model_in_registry(workspace_root, new_v)
                except ModelDefaultNotSet as e:
                    print(f"    [校验失败] {e.message}")
                    continue
                except ModelNotInRegistry as e:
                    print(f"    [校验失败] {e.message}")
                    continue
                meta.model = new_v
                break
        else:
            # display_name / description: 自由文本, 无校验
            try:
                new_v = input("输入新值（回车跳过 / '-' 清空）: ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if new_v == "":
                pass
            elif new_v == "-":
                setattr(meta, key, "")
            else:
                setattr(meta, key, new_v)
        meta.bump()
        wiki_store.save(wiki_dir, meta)
        try:
            again = input("继续编辑？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if again in ("n", "no"):
            return
