"""wiki enter — 启动 agent session（backend 由 workspace_local.toml#enter_cli 选）。

两 backend 均裸启动只传目录；AGENTS.md（含 @import 展开）由 agent 原生加载。

窗口开在当前 tmux session；tmux 外按可见 session 数选路（0/≥2 兜底 llm_workspace + attach）。
fire-and-forget：建成返回 0；窗口原语见 byobu.py。
"""

import shlex
import shutil
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from llmw.backends import DEFAULT_BACKEND, KNOWN_BACKENDS
from llmw.errors import AgentNotFound, ByobuNotFound, WikiDirMissing
from llmw.wiki import byobu
from llmw.wiki.manager import resolve_wiki_path
from llmw.workspace import local_store


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
        print(
            f"[llmw] ✓ 复用已有窗口 '{window_name}'（agent 已在运行）",
            file=sys.stdout,
        )


def _spawn(
    wiki_path: Path,
    name: str,
    window_name: str,
    cmd: List[str],
    backend: str,
    dry_run: bool,
) -> int:
    """两 backend 共用的 spawn 收口：开窗/复用 + 打标；tmux 外按可见 session 数选路。"""
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
    _report_spawn_result(target, window_name, created, collected)
    if target.outside:
        # 非 TTY（脚本）只建不 attach，打印 hint
        if sys.stdout.isatty():
            byobu.attach_session(target.session)
        else:
            print(
                f"[llmw] 查看窗口: byobu attach -t {target.session}",
                file=sys.stdout,
            )
    return 0


def _warn_missing_context(name: str, agents_md: Path, meta_p: Path) -> None:
    if not agents_md.is_file():
        print(
            f"[llmw] warning: wiki '{name}' 缺少 AGENTS.md，session 启动后将没有 schema 上下文",
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
        raise AgentNotFound(
            f"{agent_bin} 不在 PATH",
            hint="安装或加到 PATH 后重试；可用 --dry-run 看命令",
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

    agents_md = wiki_path / "AGENTS.md"
    meta_p = wiki_path / "wiki_metadata.toml"
    _warn_missing_context(name, agents_md, meta_p)

    backend, explicit = _resolve_backend(workspace_root)
    _check_enter_env(backend, dry_run)  # backend 值即 agent 二进制名

    cmd = (
        _build_cmd_qodercli(wiki_path)
        if backend == "qodercli"
        else _build_cmd_opencode(wiki_path)
    )

    if dry_run:
        # backend 既可能是默认也可能是显式配置——suffix 据 explicit 如实标注来源
        suffix = "(workspace_local.toml#enter_cli)" if explicit else "（默认）"
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(f"[llmw] backend:   {backend} {suffix}", file=sys.stdout)
        print(
            "[llmw] (模型由 agent 内部自由切换；AGENTS.md 由 agent 原生加载)",
            file=sys.stdout,
        )
        if agents_md.is_file():
            print(
                f"[llmw] AGENTS.md: ✓ found ({agents_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print("[llmw] AGENTS.md: ✗ missing", file=sys.stdout)

    return _spawn(
        wiki_path,
        name,
        _window_name(name, window_suffix),
        cmd,
        backend,
        dry_run,
    )


def _window_name(wiki: str, window_suffix: Optional[str]) -> str:
    return byobu.window_name_for(wiki, window_suffix or "main")
