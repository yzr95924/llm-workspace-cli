"""wiki enter — 启动 AI agent session（默认 opencode；workspace_local.toml#enter_cli 切换）。

- claude：resolved model 经 `<wiki>/.claude/settings.local.json` env 块（Local 层）交付；
  cmd 只 `--add-dir`（claude 自读 CLAUDE.md）；不注入 subprocess env / --setting-sources。
- opencode（默认）：不解析 model，写 `<wiki>/opencode.json` instructions 键（同步模板
  顶层 @import——opencode 不解析 AGENTS.md 的 @path 引用）。
- qodercli：裸启动，只传目录。

窗口模型：agent 开成当前 tmux session 的窗口；tmux 外按可见 session 数选路（恰 1 个
直接开入，0/≥2 兜底 llm_workspace + TTY attach）。fire-and-forget：建成返回 0。
spawn 收口在 _spawn()；窗口原语见 llmw/wiki/byobu.py。
"""

import shlex
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import List, NamedTuple, Optional, Tuple

from llmw._compat import TOMLDecodeError
from llmw.backends import DEFAULT_BACKEND, KNOWN_BACKENDS
from llmw.errors import (
    ByobuNotFound,
    ClaudeNotFound,
    SchemaVersionUnsupported,
    WikiDirMissing,
)
from llmw.models import overlay, overlay_opencode
from llmw.models.redact import redact_api_key
from llmw.models.resolve import resolve_for_wiki
from llmw.models.store import ModelEntry
from llmw.wiki import byobu
from llmw.wiki.manager import resolve_wiki_path
from llmw.wiki.store import load as wiki_load
from llmw.workspace import local_store


def _build_cmd(wiki_path: Path) -> List[str]:
    """claude argv：只 `--add-dir`（自读 CLAUDE.md）；不传 --setting-sources（overlay 在
    Local 层已稳赢 user 配置）/ 不传 --system-prompt（自动聚合，显式注入会双计入）。
    """
    return ["claude", "--add-dir", str(wiki_path)]


def _build_cmd_qodercli(wiki_path: Path) -> List[str]:
    return ["qodercli", "--add-dir", str(wiki_path)]


def _build_cmd_opencode(wiki_path: Path) -> List[str]:
    """opencode argv：位置参数 project dir（启动后自读 AGENTS.md；模型 session 内切换）。"""
    return ["opencode", str(wiki_path)]


class _TargetSession(NamedTuple):
    session: str
    ensure: bool
    outside: bool  # llmw 进程不在 tmux 内（attach 决策）
    reuse_sole: bool  # tmux 外复用唯一可见 session（透明文案用）


def _select_target_session() -> _TargetSession:
    cur = byobu.current_session()
    if cur is not None:
        return _TargetSession(cur, False, False, False)
    visible = byobu.visible_sessions()
    if len(visible) == 1:
        # 恰一个可见 session：直接开入（不建第二个——第二个会把裸 byobu 直达变成菜单）
        return _TargetSession(visible[0], False, True, True)
    # 0 → 总得建一个；≥2 → 有歧义不猜（选哪个都是替用户做主）
    return _TargetSession(byobu.BYOBU_SESSION, True, True, False)


def _print_dry_run_spawn(
    wiki_path: Path,
    name: str,
    window_name: str,
    cmd: List[str],
    backend: str,
) -> None:
    print("[llmw] cmd:", file=sys.stdout)
    print(f"  {' '.join(cmd)}", file=sys.stdout)
    print(
        f"[llmw] env: LLM_WIKI_ROOT={wiki_path}（命令前缀注入，兼容 tmux ≥2.7）",
        file=sys.stdout,
    )
    quoted = " ".join(shlex.quote(a) for a in cmd)
    print(
        f"[llmw] window: {window_name}（作用域 = 当前 tmux session；"
        "不在 tmux 内 → 恰一个可见 session 直接在其中开窗，"
        f"否则兜底 {byobu.BYOBU_SESSION} + attach）",
        file=sys.stdout,
    )
    print(
        "[llmw]   复用: 窗口名 + @llmw_wiki + @llmw_backend + 非 dead 四条件命中"
        " → select-window，不新建；backend 不符 → 拒绝（先 stop 或 --window-suffix）",
        file=sys.stdout,
    )
    print("[llmw]   新建: 无带标同名窗口时将执行", file=sys.stdout)
    print(
        f"  byobu-tmux new-window -t <session> -P -F '#{{window_id}}' "
        f"-n {window_name} -c {wiki_path} LLM_WIKI_ROOT={wiki_path} {quoted}",
        file=sys.stdout,
    )
    print(
        f"  byobu-tmux set-option -w -t @N @llmw_wiki {name} "
        f"&& set-option -w -t @N @llmw_started $(date +%s) "
        f"&& set-option -w -t @N @llmw_backend {backend}",
        file=sys.stdout,
    )
    print("[llmw] --dry-run: 未执行", file=sys.stdout)


def _report_spawn_result(
    target: _TargetSession,
    window_name: str,
    created: bool,
    collected: bool,
    overlay_refreshed: bool = False,
) -> None:
    if created:
        print(
            f"[llmw] ✓ 已在 tmux session '{target.session}' 新建窗口 '{window_name}'",
            file=sys.stdout,
        )
        if target.reuse_sole:
            print(
                "[llmw]   （tmux 外唯一可见 session，窗口直接开入其中，"
                f"不建 {byobu.BYOBU_SESSION}）",
                file=sys.stdout,
            )
        if collected:
            print(
                "[llmw]   （同名已退出残留窗口已清理）",
                file=sys.stdout,
            )
    else:
        note = (
            "；overlay 已刷新落盘，但运行中的 agent 不会重读"
            if overlay_refreshed
            else ""
        )
        print(
            f"[llmw] ✓ 复用已有窗口 '{window_name}'（agent 已在运行{note}）",
            file=sys.stdout,
        )


def _spawn(
    wiki_path: Path,
    name: str,
    window_name: str,
    cmd: List[str],
    backend: str,
    dry_run: bool,
    overlay_refreshed: bool = False,
) -> int:
    """最终 spawn 收口（三 backend 共用）：当前 tmux session 开窗/复用；
    不在 tmux 内 → _select_target_session 按可见 session 数选路：恰 1 个直接在
    其中开窗（reuse_sole），0 / ≥2 兜底 session llm_workspace + TTY attach / 非
    TTY hint。

    backend 随窗口打标（@llmw_backend），供 status 的 BACKEND 列与 STATE 模式路由。
    overlay_refreshed：复用窗口时是否已写过 overlay（claude/opencode=True；qodercli=False）。
    """
    if dry_run:
        _print_dry_run_spawn(wiki_path, name, window_name, cmd, backend)
        return 0

    target = _select_target_session()
    created, _, collected = byobu.spawn_window(
        byobu.SpawnSpec(
            session=target.session,
            window_name=window_name,
            wiki=name,
            cwd=str(wiki_path),
            cmd_argv=cmd,
            env={"LLM_WIKI_ROOT": str(wiki_path)},
            backend=backend,
            ensure=target.ensure,
        )
    )
    _report_spawn_result(target, window_name, created, collected, overlay_refreshed)
    if target.outside:
        # tmux 外路径（兜底或唯一可见 session 复用）：TTY → attach（落点 = 该窗口，
        # select/new 已置其为 current）；非 TTY（脚本）→ 只建不 attach，打印 hint
        if sys.stdout.isatty():
            byobu.attach_session(target.session)
        else:
            print(
                f"[llmw] 查看窗口: byobu attach -t {target.session}",
                file=sys.stdout,
            )
    return 0


class _EnterPlan(NamedTuple):
    workspace_root: Path
    name: str
    wiki_path: Path
    meta_p: Path
    backend: str
    ov: ModuleType
    model: ModelEntry
    context_file: Path
    backend_label: str
    cmd: List[str]


def _warn_missing_context(name: str, claude_md: Path, meta_p: Path) -> None:
    if not claude_md.is_file():
        print(
            f"[llmw] warning: wiki '{name}' 缺少 CLAUDE.md，session 启动后将没有 schema 上下文",
            file=sys.stderr,
        )
    if not meta_p.is_file():
        print(f"[llmw] warning: wiki '{name}' 缺少 wiki_metadata.toml", file=sys.stderr)


def _resolve_backend(workspace_root: Path) -> Tuple[str, bool]:
    """选 backend：非法值 warning + 回退默认（不静默吞用户意图）。

    返回 (backend, explicit)：explicit = 生效 backend 来自 workspace_local.toml
    显式配置（False = 走默认或非法值回退）。enter 文案据此区分"（默认）"与配置来源。
    """
    local = local_store.load(workspace_root)
    configured = local.enter_cli
    backend = configured or DEFAULT_BACKEND
    if backend not in KNOWN_BACKENDS:
        print(
            f"[llmw] warning: workspace_local.toml#enter_cli 值 '{backend}' 不在白名单，"
            f"已回退 {DEFAULT_BACKEND}（可选: {', '.join(sorted(KNOWN_BACKENDS))}）",
            file=sys.stderr,
        )
        backend = DEFAULT_BACKEND
    return backend, configured == backend


def _check_enter_env(agent_bin: str, dry_run: bool) -> None:
    if dry_run:
        return
    if not byobu.byobu_available():
        raise ByobuNotFound(
            "byobu-tmux 不在 PATH",
            hint="安装 byobu（如 apt install byobu / brew install byobu），然后重试",
        )
    if shutil.which(agent_bin) is None:
        raise ClaudeNotFound(
            f"{agent_bin} 不在 PATH",
            hint="安装或加到 PATH 后重试；可用 --dry-run 看命令",
        )


def _build_enter_plan(
    workspace_root: Path,
    name: str,
    wiki_path: Path,
    meta_p: Path,
    claude_md: Path,
    backend: str,
    model: ModelEntry,
) -> _EnterPlan:
    ov, cmd = overlay, _build_cmd(wiki_path)
    suffix = (
        "（默认）" if backend == DEFAULT_BACKEND else "(workspace_local.toml#enter_cli)"
    )
    backend_label = f"{backend} {suffix}"
    return _EnterPlan(
        workspace_root=workspace_root,
        name=name,
        wiki_path=wiki_path,
        meta_p=meta_p,
        backend=backend,
        ov=ov,
        model=model,
        context_file=claude_md,
        backend_label=backend_label,
        cmd=cmd,
    )


def enter(
    workspace_root: Path,
    name: str,
    dry_run: bool = False,
    window_suffix: Optional[str] = None,
) -> int:
    wiki_path = resolve_wiki_path(workspace_root, name)

    if not wiki_path.is_dir():
        raise WikiDirMissing(
            f"wiki 子目录不存在: {wiki_path}",
            hint="可能被外部 rm；可 `git checkout` 恢复或重新 add",
        )

    claude_md = wiki_path / "CLAUDE.md"
    meta_p = wiki_path / "wiki_metadata.toml"
    _warn_missing_context(name, claude_md, meta_p)

    backend, explicit = _resolve_backend(workspace_root)
    _check_enter_env(backend, dry_run)  # backend 值即 agent 二进制名

    # qodercli 路径：裸启动——跳过 resolve / overlay；只传目录
    if backend == "qodercli":
        return _enter_bare(
            workspace_root,
            name,
            wiki_path,
            claude_md,
            backend,
            _build_cmd_qodercli(wiki_path),
            dry_run,
            window_suffix,
        )

    # opencode 路径（默认）：不解析 model，但写 instructions overlay
    # （opencode 不解析 @import，用 config instructions 替代）
    if backend == "opencode":
        return _enter_opencode(
            workspace_root,
            name,
            wiki_path,
            claude_md,
            dry_run,
            window_suffix,
            explicit,
        )

    # claude 路径：resolve → overlay → spawn。resolve 拿最终 model
    # （失败阻断 enter，在任何写盘之前）
    model = resolve_for_wiki(workspace_root, name)
    plan = _build_enter_plan(
        workspace_root, name, wiki_path, meta_p, claude_md, backend, model
    )

    if dry_run:
        return _enter_dry_run(plan, window_suffix)
    return _execute_plan(plan, window_suffix)


def _execute_plan(plan: _EnterPlan, window_suffix: Optional[str]) -> int:
    plan.ov.apply(plan.wiki_path, plan.model)
    return _spawn(
        plan.wiki_path,
        plan.name,
        _window_name(plan.name, window_suffix),
        plan.cmd,
        plan.backend,
        dry_run=False,
        overlay_refreshed=True,
    )


def _enter_dry_run(plan: _EnterPlan, window_suffix: Optional[str]) -> int:
    meta = None
    if plan.meta_p.is_file():
        try:
            meta = wiki_load(plan.wiki_path)
        except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
            # resolve 已捕过 SchemaVersionUnsupported；这里再捕让 dry-run 还能打印 overlay
            print(
                f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            meta = None
    _print_dry_run_model_backends(plan, meta)
    return _spawn(
        plan.wiki_path,
        plan.name,
        _window_name(plan.name, window_suffix),
        plan.cmd,
        plan.backend,
        dry_run=True,
    )


def _enter_bare(
    workspace_root: Path,
    name: str,
    wiki_path: Path,
    claude_md: Path,
    backend: str,
    cmd: List[str],
    dry_run: bool,
    window_suffix: Optional[str],
) -> int:
    if dry_run:
        suffix = (
            "（默认）"
            if backend == DEFAULT_BACKEND
            else "(workspace_local.toml#enter_cli)"
        )
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(f"[llmw] backend:   {backend} {suffix}", file=sys.stdout)
        print(
            f"[llmw] ({backend} 路径：跳过 overlay.apply / resolve_for_wiki；"
            "模型由 agent 内部自由切换)",
            file=sys.stdout,
        )
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print("[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
    return _spawn(
        wiki_path,
        name,
        _window_name(name, window_suffix),
        cmd,
        backend,
        dry_run,
    )


def _enter_opencode(
    workspace_root: Path,
    name: str,
    wiki_path: Path,
    claude_md: Path,
    dry_run: bool,
    window_suffix: Optional[str],
    explicit: bool,
) -> int:
    cmd = _build_cmd_opencode(wiki_path)
    # opencode 既可能是默认也可能是显式配置——suffix 据 explicit 如实标注来源
    suffix = "(workspace_local.toml#enter_cli)" if explicit else "（默认）"

    if dry_run:
        overlay_path, would_write = overlay_opencode.inspect(wiki_path)
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(f"[llmw] backend:   opencode {suffix}", file=sys.stdout)
        print(
            "[llmw] (opencode 路径：跳过 resolve_for_wiki；模型由 agent 内部自由切换)",
            file=sys.stdout,
        )
        tag = "(will write)" if would_write else "(up to date, skip)"
        print(f"[llmw] overlay file: {overlay_path}  {tag}", file=sys.stdout)
        effective = overlay_opencode.effective_instructions(wiki_path)
        print(
            "[llmw]   instructions = [" + ", ".join(effective) + "]",
            file=sys.stdout,
        )
        if len(effective) < len(overlay_opencode.INSTRUCTION_FILES):
            missing = [
                f for f in overlay_opencode.INSTRUCTION_FILES if f not in effective
            ]
            print(
                "[llmw]   (P1 过滤：下列条目在 wiki 内不存在，已剔除: "
                + ", ".join(missing)
                + ")",
                file=sys.stdout,
            )
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print("[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        return _spawn(
            wiki_path,
            name,
            _window_name(name, window_suffix),
            cmd,
            "opencode",
            dry_run=True,
        )

    overlay_opencode.apply(wiki_path)
    return _spawn(
        wiki_path,
        name,
        _window_name(name, window_suffix),
        cmd,
        "opencode",
        dry_run=False,
        overlay_refreshed=True,
    )


def _print_dry_run_model_backends(plan: _EnterPlan, meta) -> None:
    """claude 路径 dry-run 打印：字段一律取自 ov.render(model) 输出（不手抄 overlay
    内部逻辑，避免展示与实现漂移；api_key 过 redact）。
    """
    overlay_path, would_write = plan.ov.inspect(plan.wiki_path, plan.model)
    print(f"[llmw] workspace: {plan.workspace_root}", file=sys.stdout)
    print(f"[llmw] wiki:      {plan.name} ({plan.wiki_path})", file=sys.stdout)
    print(f"[llmw] backend:   {plan.backend_label}", file=sys.stdout)
    print(
        f"[llmw] resolved model: {plan.model.name} ({plan.model.model_id})",
        file=sys.stdout,
    )
    source = "wiki override" if (meta and meta.model) else "registry default"
    print(f"[llmw] source: {source}", file=sys.stdout)
    tag = "(will write)" if would_write else "(up to date, skip)"
    print(f"[llmw] overlay file: {overlay_path}  {tag}", file=sys.stdout)
    expected = plan.ov.render(plan.model)
    print(
        f"[llmw]   ANTHROPIC_MODEL      = {expected['ANTHROPIC_MODEL']}",
        file=sys.stdout,
    )
    print(
        f"[llmw]   ANTHROPIC_BASE_URL   = {expected['ANTHROPIC_BASE_URL']}",
        file=sys.stdout,
    )
    print(
        f"[llmw]   ANTHROPIC_AUTH_TOKEN = {redact_api_key(expected['ANTHROPIC_AUTH_TOKEN'])}",
        file=sys.stdout,
    )
    # Habit template（非用户可配的代码内常量, 随 overlay 一同写入）——render 输出
    # 中 ANTHROPIC_* 之外的 key 即 habit template
    habit = {k: v for k, v in expected.items() if not k.startswith("ANTHROPIC_")}
    print("[llmw]   (habit template)", file=sys.stdout)
    # 用最长 key 长度对齐 value 列（habit template 组内对齐, 不与 model env 共享列）
    width = max(len(k) for k in habit)
    for k, v in habit.items():
        print(f"[llmw]     {k:{width}s} = {v}", file=sys.stdout)
    if plan.context_file.is_file():
        print(
            f"[llmw] {plan.context_file.name}: ✓ found ({plan.context_file.stat().st_size} bytes)",
            file=sys.stdout,
        )
    else:
        print(f"[llmw] {plan.context_file.name}: ✗ missing", file=sys.stdout)


def _window_name(wiki: str, window_suffix: Optional[str]) -> str:
    return byobu.window_name_for(wiki, window_suffix or "main")
