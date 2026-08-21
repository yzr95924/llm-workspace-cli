"""wiki enter — 启动 AI agent session (默认 claude；workspace_local.toml#enter_cli 切换 qodercli/opencode)

claude 路径（默认，overlay.apply 写 <wiki>/.claude/settings.local.json）：resolved model 通过写 <wiki>/.claude/settings.local.json
的 env 块（Local 层，优先级 > User）交付，lazy on enter。不再注入 subprocess env、不再传
--setting-sources——user 配置（~/.claude/settings.json）正常加载，overlay 在 Local 层稳赢。
只传 `--add-dir` 让 claude 自读 `<wiki>/CLAUDE.md`，不显式注入 --system-prompt（避免双计入）。

opencode 路径（enter_cli = "opencode"）：与 claude 同族——resolve_for_wiki 生效，但 overlay
落盘是 <wiki>/opencode.json（llmw/models/overlay_opencode.py；项目级配置优先级 > 全局），
不含 habit template。cmd 用位置参数传 wiki 目录（opencode 自读 AGENTS.md）。

qodercli 路径（enter_cli = "qodercli"）：跳过 overlay.apply / 不解析 model /
不写 .claude/——只把 wiki 目录传给 qodercli（qodercli 自读 AGENTS.md）。

窗口模型（设计 doc/session-visibility-design.md §2.2，byobu 为 enter 硬依赖）：
enter 把 agent 开成"当前 tmux session 的一个窗口"（W' 模型）——tmux 内发起 → 自动聚焦；
不在 tmux 内 → 兜底 session `llm_workspace` + TTY attach。窗口名 = `<wiki>-<suffix>`
（缺省 `-main`，经 `--window-suffix` 只传后缀；R1），复用判定 = 窗口名 + `@llmw_wiki`
+ `@llmw_backend` + pane 非 dead 四条件（R2；命中 dead 尸体 → kill-window 收尸后按
无窗口新开；backend 不符 → 拒绝 + hint，防"切换 agent"意图被吞），
新开时打标 `@llmw_wiki` / `@llmw_started`（R3）。fire-and-forget：窗口建成
即返回 0，不等 agent 退出、退出码不来自 agent。最终 spawn 统一收口在 _spawn()。
"""

import shlex
import shutil
import sys
from pathlib import Path
from typing import List, Optional

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
from llmw.wiki import byobu
from llmw.wiki.manager import resolve_wiki_path
from llmw.wiki.store import load as wiki_load
from llmw.workspace import local_store
from llmw.workspace.gitignore import ensure_workspace_gitignore


def _build_cmd(wiki_path: Path) -> List[str]:
    """构造 claude 子进程 argv：仅 --add-dir，让 claude 自读 <wiki>/CLAUDE.md。

    不传 --setting-sources：claude 默认加载 user+project+local。cwd=wiki 子目录 → 读到
    <wiki>/.claude/settings.local.json（Local，优先级 > User）→ overlay 稳赢，user 配置同时
    加载。早期版本传 --setting-sources project,local 排除 user，是为防其 env 块盖掉优先级
    更低的 subprocess env overlay；现 overlay 已在 Local 层文件里，无需排除 user。

    不传 --system-prompt：claude 会从 cwd + --add-dir 自动聚合 CLAUDE.md；显式注入会双计入
    并让两 backend 行为分叉（qodercli 路径就不传）。
    """
    return ["claude", "--add-dir", str(wiki_path)]


def _build_cmd_qodercli(wiki_path: Path) -> List[str]:
    """构造 qodercli 子进程 argv：--add-dir。

    qodercli 不读 .claude/settings.local.json，不依赖 model env 注入（qodercli 自读 AGENTS.md）。
    """
    return ["qodercli", "--add-dir", str(wiki_path)]


def _build_cmd_opencode(wiki_path: Path) -> List[str]:
    """构造 opencode 子进程 argv：位置参数 project dir（等价 claude --add-dir 的角色）。

    opencode 启动后从 cwd 向上自读 AGENTS.md（wiki 骨架含 AGENTS.md，opencode 优先读它、
    CLAUDE.md 兜底）。模型由 <wiki>/opencode.json 顶层 model key 指定（overlay_opencode
    交付），不传 -m——-m 只是"选择已配置 provider/model"，provider 定义仍靠 overlay 文件。
    """
    return ["opencode", str(wiki_path)]


def _spawn(
    wiki_path: Path,
    name: str,
    window_name: str,
    cmd: List[str],
    backend: str,
    dry_run: bool,
) -> int:
    """最终 spawn 收口（三 backend 共用）：当前 tmux session 开窗/复用（W' 模型）；
    不在 tmux 内 → 兜底 session llm_workspace + TTY attach / 非 TTY hint。

    backend 随 R3 打标（@llmw_backend），供 status 的 BACKEND 列与 STATE 模式路由。

    dry-run 打印决策树但不探测 byobu/session 状态（与"dry-run 跳过 PATH 检查"
    同一约定：dry-run 零外部副作用）。
    """
    if dry_run:
        print("[llmw] cmd:", file=sys.stdout)
        print(f"  {' '.join(cmd)}", file=sys.stdout)
        print(
            f"[llmw] env: LLM_WIKI_ROOT={wiki_path}（命令前缀注入，兼容 tmux ≥2.7）",
            file=sys.stdout,
        )
        quoted = " ".join(shlex.quote(a) for a in cmd)
        print(
            f"[llmw] window: {window_name}（作用域 = 当前 tmux session；"
            "不在 tmux 内 → 兜底 "
            f"{byobu.BYOBU_SESSION} + attach）",
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
        return 0

    cur = byobu.current_session()
    if cur is not None:
        session, ensure = cur, False
    else:
        session, ensure = byobu.BYOBU_SESSION, True

    created, _, collected = byobu.spawn_window(
        byobu.SpawnSpec(
            session=session,
            window_name=window_name,
            wiki=name,
            cwd=str(wiki_path),
            cmd_argv=cmd,
            env={"LLM_WIKI_ROOT": str(wiki_path)},
            backend=backend,
            ensure=ensure,
        )
    )
    if created:
        print(
            f"[llmw] ✓ 已在 tmux session '{session}' 新建窗口 '{window_name}'",
            file=sys.stdout,
        )
        if collected:
            print(
                "[llmw]   （同名已退出残留窗口已清理）",
                file=sys.stdout,
            )
    else:
        print(
            f"[llmw] ✓ 复用已有窗口 '{window_name}'（agent 已在运行；"
            "overlay 已刷新落盘，但运行中的 agent 不会重读）",
            file=sys.stdout,
        )
    if cur is None:
        # 兜底路径：TTY → attach（落点 = 该窗口，select/new 已置其为 current）；
        # 非 TTY（脚本）→ 只建不 attach，打印 hint
        if sys.stdout.isatty():
            byobu.attach_session(session)
        else:
            print(f"[llmw] 查看窗口: byobu attach -t {session}", file=sys.stdout)
    return 0


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

    # 软警告（不阻断）
    if not claude_md.is_file():
        print(
            f"[llmw] warning: wiki '{name}' 缺少 CLAUDE.md，session 启动后将没有 schema 上下文",
            file=sys.stderr,
        )
    if not meta_p.is_file():
        print(f"[llmw] warning: wiki '{name}' 缺少 wiki_metadata.toml", file=sys.stderr)

    # 选 backend：workspace_local.toml#enter_cli；未设 → DEFAULT_BACKEND（backends.py 真源）。
    # 手改出非法值（config set 有白名单挡着，兜手改文件）→ warning + 回退默认——
    # 静默降级会吞掉用户意图（巡检 #7：本项目卖点是可见性，自己不该静默）。
    local = local_store.load(workspace_root)
    backend = local.enter_cli or DEFAULT_BACKEND
    if backend not in KNOWN_BACKENDS:
        print(
            f"[llmw] warning: workspace_local.toml#enter_cli 值 '{backend}' 不在白名单，"
            f"已回退 {DEFAULT_BACKEND}（可选: {', '.join(sorted(KNOWN_BACKENDS))}）",
            file=sys.stderr,
        )
        backend = DEFAULT_BACKEND
    agent_bin = backend  # backend 值即二进制名

    # 环境检查（步骤 5；dry-run 跳过）：byobu-tmux + agent CLI 都必须在 PATH——
    # byobu 从可选增强变为 enter 硬依赖（设计 §2.5，窗口路径全环境成立）
    if not dry_run:
        if not byobu.byobu_available():
            raise ByobuNotFound(
                "byobu-tmux 不在 PATH",
                hint="安装 byobu（如 apt install byobu / brew install byobu），"
                "然后重试",
            )
        if shutil.which(agent_bin) is None:
            raise ClaudeNotFound(
                f"{agent_bin} 不在 PATH",
                hint="安装或加到 PATH 后重试；可用 --dry-run 看命令",
            )

    # qodercli 路径：跳过 resolve / overlay；只传目录
    if backend == "qodercli":
        return _enter_qodercli(
            workspace_root, name, wiki_path, claude_md, dry_run, window_suffix
        )

    # claude（默认）/ opencode 路径：resolve → overlay → spawn（两 backend 同族，
    # 只换 overlay 模块 / cmd / 展示文案）
    # 步骤 6a：通过 resolve 拿最终 model（失败阻断 enter，在任何写盘之前）
    model = resolve_for_wiki(workspace_root, name)

    if backend == "opencode":
        ov = overlay_opencode
        cmd = _build_cmd_opencode(wiki_path)
        backend_label = "opencode (workspace_local.toml#enter_cli)"
        context_file = wiki_path / "AGENTS.md"  # opencode 优先读 AGENTS.md
    else:
        ov = overlay
        cmd = _build_cmd(wiki_path)
        backend_label = "claude (默认)"
        context_file = claude_md

    if dry_run:
        return _enter_dry_run(
            workspace_root,
            name,
            wiki_path,
            meta_p,
            backend,
            ov,
            model,
            context_file,
            backend_label,
            cmd,
            window_suffix,
        )

    # opencode 路径特有：overlay 落盘含明文 apiKey，写盘前确保 workspace .gitignore 的
    # **/opencode.json 排除行就位（老 workspace 的 managed block 可能还是旧版少行）。
    # 与 wiki remove --purge 升级 .llmw-trash/ 行同一先例（llmw/wiki/manager.py）。
    # gitignore 写入失败不阻断 enter（用户可手动 gitignore）——但打 warning，不静默。
    if backend == "opencode":
        try:
            ensure_workspace_gitignore(workspace_root)
        except OSError as e:
            print(
                f"[llmw] warning: workspace .gitignore 更新失败: {e}——"
                f"建议手动确保含 `**/opencode.json` 排除行",
                file=sys.stderr,
            )

    # 真正执行：步骤 6b lazy 写 overlay（claude=Local 层 settings.local.json；
    # opencode=项目级 opencode.json）→ _spawn 收口（当前 session 开窗/兜底 attach）
    ov.apply(wiki_path, model)
    return _spawn(
        wiki_path,
        name,
        _window_name(name, window_suffix),
        cmd,
        backend,
        dry_run=False,
    )


def _enter_dry_run(
    workspace_root: Path,
    name: str,
    wiki_path: Path,
    meta_p: Path,
    backend: str,
    ov,
    model,
    context_file: Path,
    backend_label: str,
    cmd: List[str],
    window_suffix: Optional[str],
) -> int:
    """claude/opencode 路径的 dry-run 分支：打印决策树后由 _spawn 统一收尾。"""
    meta = None
    if meta_p.is_file():
        try:
            meta = wiki_load(wiki_path)
        except (OSError, TOMLDecodeError, SchemaVersionUnsupported) as e:
            # resolve 已捕过 SchemaVersionUnsupported；这里再捕让 dry-run 还能打印 overlay
            print(
                f"[llmw] warning: 无法读取 wiki_metadata.toml: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            meta = None
    _print_dry_run_model_backends(
        backend,
        ov,
        model,
        meta,
        workspace_root,
        wiki_path,
        context_file,
        name,
        backend_label,
    )
    return _spawn(
        wiki_path,
        name,
        _window_name(name, window_suffix),
        cmd,
        backend,
        dry_run=True,
    )


def _enter_qodercli(
    workspace_root: Path,
    name: str,
    wiki_path: Path,
    claude_md: Path,
    dry_run: bool,
    window_suffix: Optional[str],
) -> int:
    """qodercli 路径（T12 拆分）：跳过 resolve / overlay；只传目录。

    dry-run 打印专属决策；cmd/env/spawn 方式/未执行 由 _spawn 统一打印（dry-run）
    或执行（real）。
    """
    cmd = _build_cmd_qodercli(wiki_path)

    if dry_run:
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(
            "[llmw] backend:   qodercli (workspace_local.toml#enter_cli)",
            file=sys.stdout,
        )
        print(
            "[llmw] (qodercli 不读 .claude/settings.local.json；跳过 overlay.apply / resolve_for_wiki)",
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
        "qodercli",
        dry_run,
    )


def _print_dry_run_model_backends(
    backend: str,
    ov,
    model,
    meta,
    workspace_root: Path,
    wiki_path: Path,
    context_file: Path,
    name: str,
    backend_label: str,
) -> None:
    """claude/opencode 路径的 dry-run 打印块（T12 拆分）。

    内容不变：workspace/wiki/backend/resolved model/source/overlay 文件（含
    will-write 判定）+ backend 专属 env 行（opencode=provider 块 / claude=ANTHROPIC_*
    + habit template，api_key 过 redact）+ context 文件存在性。

    **展示字段一律取自 ov.render(model) 输出**——render 改字段 dry-run 自动跟随，
    不手抄 overlay 内部逻辑（避免"展示与实现耦合"漂移）。
    """
    overlay_path, would_write = ov.inspect(wiki_path, model)
    print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
    print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
    print(f"[llmw] backend:   {backend_label}", file=sys.stdout)
    print(
        f"[llmw] resolved model: {model.name} ({model.model_id})",
        file=sys.stdout,
    )
    source = "wiki override" if (meta and meta.model) else "registry default"
    print(f"[llmw] source: {source}", file=sys.stdout)
    tag = "(will write)" if would_write else "(up to date, skip)"
    print(f"[llmw] overlay file: {overlay_path}  {tag}", file=sys.stdout)
    expected = ov.render(model)
    if backend == "opencode":
        pid = overlay_opencode.PROVIDER_ID
        prov = expected["provider"][pid]
        print(f"[llmw]   provider.{pid}.npm     = {prov['npm']}", file=sys.stdout)
        print(
            f"[llmw]   provider.{pid}.baseURL = {prov['options']['baseURL']}",
            file=sys.stdout,
        )
        print(
            f"[llmw]   provider.{pid}.apiKey  = {redact_api_key(prov['options']['apiKey'])}",
            file=sys.stdout,
        )
        print(f"[llmw]   model                 = {expected['model']}", file=sys.stdout)
    else:
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
    if context_file.is_file():
        print(
            f"[llmw] {context_file.name}: ✓ found ({context_file.stat().st_size} bytes)",
            file=sys.stdout,
        )
    else:
        print(f"[llmw] {context_file.name}: ✗ missing", file=sys.stdout)


def _window_name(wiki: str, window_suffix: Optional[str]) -> str:
    """R1 定窗口名：`--window-suffix` 拼接为 `<wiki>-<suffix>`，缺省 `<wiki>-main`。

    校验在 byobu.window_name_for 内（suffix `^[a-z0-9_-]{1,16}$` + 总长 ≤40）；
    非法 → InvalidWindowSuffix（exit 1）。dry-run 与 real 都走本函数——窗口名是
    spawn 决策的一部分。
    """
    return byobu.window_name_for(wiki, window_suffix or "main")
