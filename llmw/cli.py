"""argparse 顶层 + 全局 flag + 子命令分派"""

import argparse
import json
import os
import sys
from pathlib import Path
from llmw import __version__
from llmw.errors import LlmwError, InternalError, SpaceFormNotAllowed, format_error


def _flag(args, name: str):
    """全局 flag 读取（default=SUPPRESS 的 parent 语义，见 _common_flags docstring）。"""
    return getattr(args, name, False)


# 参数风格：带值 flag 一律 `--flag=value`（= 连接），拒绝空格分隔的 `--flag value`。
# 严谨、无歧义：带值 flag 与其值在同一 token 内绑定，不靠相邻位置隐式推断。
# bool flag（store_true / store_false / count）不带值，不受此约束，保持原样。
# 位置参数（config KEY VALUE 等子动作 / 自由值）不套用 = 约束。
# 新增带值 flag 直接 `add_argument("--flag", ...)`——判定走 action 类型，无需维护白名单。
# 新增 bool flag 直接 `add_argument(..., action="store_true"/"store_false")`。


# 带值 action 判定走公开 API（nargs），不依赖 argparse 私有类名（_StoreAction 等，
# 版本升级可能改名导致判定静默失效）：
#   - nargs != 0 → 消费值的 option（单值 None / 多值 int / 其余非零）
#   - nargs == 0 → 不带值（store_true/false/count/version/help）
# 子 parser 判定：nargs == argparse.PARSER（公开常量，_SubParsersAction 的专用值）。
def _takes_value(action) -> bool:
    return action.nargs != 0


def _is_subparsers(action) -> bool:
    return action.nargs == argparse.PARSER


def _walk_parsers(parser):
    """深度优先遍历 parser 及其所有（嵌套）子 parser，跳过已访问（防 parents 共享成环）。"""
    seen = set()
    stack = [parser]
    while stack:
        p = stack.pop()
        pid = id(p)
        if pid in seen:
            continue
        seen.add(pid)
        yield p
        for action in p._actions:
            if _is_subparsers(action):
                stack.extend(action.choices.values())


def _collect_value_flags(parser):
    """收集 parser 树内所有"带值 flag"的 -- 长选项名（精确字符串集合）。

    bool flag（store_true / store_false / count）与短选项（-q / -y）不带值 / 不受 = 约束，不纳入。
    """
    names = set()
    for p in _walk_parsers(parser):
        for action in p._actions:
            if action.option_strings and _takes_value(action):
                names.update(o for o in action.option_strings if o.startswith("--"))
    return names


def _enforce_equals_form(parser, argv):
    """强制带值 flag 用 `--flag=value`，拒绝空格分隔的 `--flag value`。

    argparse 原生同时接受两种形式；本函数在 parse 前预扫描 argv——凡是带值 flag 以
    裸 `--flag`（精确匹配、不带 =）形式出现，即试图用空格传值，抛 SpaceFormNotAllowed。
    同时禁用前缀缩写（allow_abbrev=False），堵住 `--pref value` 缩写绕过路径。
    bool flag / 未知 flag / 位置参数不受影响。
    """
    for p in _walk_parsers(parser):
        p.allow_abbrev = False
    value_flags = _collect_value_flags(parser)
    for tok in argv:
        if tok in value_flags:
            raise SpaceFormNotAllowed(tok)


def _common_flags() -> argparse.ArgumentParser:
    """全局 flag 的共享 parent。

    经 ``parents=[_common_flags()]`` 同时挂到主 parser 与每个子 parser，使全局 flag
    既可写在子命令前（``llmw --json list``）也可写在子命令后（``llmw list --json``，
    spec §3.1 / 设计 01 §1.3）。``default=SUPPRESS`` 是关键：子 parser 解析时若用户
    没在该位置传该 flag，就不写入 namespace，从而不会用默认值覆盖主 parser 已解析
    到的同名值（argparse 子 parser 默认会 clobber）。故读取处须用 ``getattr``。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="workspace 根路径 (默认: $LLMW_WORKSPACE 或 ~/yzr-llm-wiki-workspace)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="全局: 输出 JSON 格式",
    )
    common.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS,
        help="全局: 打印 traceback",
    )
    common.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=argparse.SUPPRESS,
        help="全局: 抑制 INFO",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_flags()
    parser = argparse.ArgumentParser(
        prog="llmw",
        description="Wiki workspace CLI (manage wikis under one git repo)",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"llmw {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ===== workspace 级 =====
    p_init = sub.add_parser("init", help="初始化 workspace", parents=[common])
    p_init.add_argument("--path", metavar="PATH", default=None)
    p_init.add_argument(
        "--display-name",
        default=None,
        dest="display_name",
        help="workspace display name (写入 AGENTS.md + CLAUDE.md; 默认 'LLM Wiki Workspace')",
    )

    p_config = sub.add_parser(
        "config",
        help="workspace 配置读写 (workspace.toml + workspace_local.toml)",
        parents=[common],
    )
    p_config.add_argument(
        "action", nargs="?", default=None, choices=[None, "get", "set", "unset"]
    )
    p_config.add_argument("key", nargs="?", default=None)
    p_config.add_argument("value", nargs="?", default=None)

    p_list = sub.add_parser("list", help="列出 wiki", parents=[common])
    p_list.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="TAG",
        help="仅列出含此 tag 的 wiki (可重复, AND 关系)",
    )

    p_status = sub.add_parser(
        "status",
        help="一屏查看所有运行中的 wiki agent session（tmux 窗口实时枚举）",
        parents=[common],
    )
    p_status.add_argument(
        "--tmux",
        action="store_true",
        help="输出单行 ●N（运行中窗口数），存在 dead 窗口时后缀 ✗M；供 byobu 状态条集成",
    )

    p_check_fixtures = sub.add_parser(
        "check-fixtures",
        help="workspace 级 fixtures 一致性检查（升级专用探测；dry-run）",
        parents=[common],
    )
    p_check_fixtures.add_argument(
        "--target-spec",
        default=None,
        help="目标 workspace spec 版本（缺省读 llmw.WORKSPACE_SPEC_VERSION 包内常量）",
    )
    p_check_fixtures.add_argument(
        "--list-rules",
        action="store_true",
        help="内省：输出规则清单（不扫描文件）；与 --json 联用具机器可读输出",
    )

    p_upgrade = sub.add_parser(
        "upgrade",
        help="升级 workspace 骨架 + 所有 wiki 骨架（默认 dry-run）",
        parents=[common],
    )
    p_upgrade.add_argument(
        "--apply",
        action="store_true",
        help="显式写盘（覆盖 dry-run 默认）；diff 非空时还需 --yes",
    )
    p_upgrade.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="确认覆盖 drift diff（自定义内容先搬 MEMORY/）",
    )

    # ===== model registry =====
    p_model = sub.add_parser("model", help="workspace model registry", parents=[common])
    model_sub = p_model.add_subparsers(dest="model_action", metavar="ACTION")

    pm_add = model_sub.add_parser("add", help="新增 model 条目", parents=[common])
    pm_add.add_argument("--model-id", default=None, dest="model_id")
    pm_add.add_argument("--name", default=None)
    pm_add.add_argument("--base-url", default=None, dest="base_url")
    pm_add.add_argument("--api-key", default=None, dest="api_key")
    pm_add.add_argument(
        "--context-window",
        type=int,
        default=None,
        dest="context_window",
        help="模型上下文窗口大小（整数 token, 1-10000000）,opencode 路径回写到 limit.context",
    )
    pm_add.add_argument("--default", action="store_true", dest="as_default")

    model_sub.add_parser("list", help="列出所有 model 条目", parents=[common])

    pm_show = model_sub.add_parser("show", help="查看单条 model", parents=[common])
    pm_show.add_argument("--model-id", required=True, dest="model_id")

    pm_sd = model_sub.add_parser("set-default", help="标记默认 model", parents=[common])
    pm_sd.add_argument("--model-id", required=True, dest="model_id")

    model_sub.add_parser("unset-default", help="清空默认标记", parents=[common])

    pm_rm = model_sub.add_parser("remove", help="删除 model 条目", parents=[common])
    pm_rm.add_argument("--model-id", required=True, dest="model_id")
    pm_rm.add_argument("--yes", "-y", action="store_true")

    # ===== wiki 级 =====
    # --name 放 parent 上（不 required）：rename 走 --old/--new 替代 name；
    # 其他子命令 (add/remove/show/config/enter) 依赖 dispatch 时手动校验 args.name。
    # 这样保留 `wiki --name=X <action>` 旧语法 + 新 `wiki rename --old=... --new=...`。
    p_wiki = sub.add_parser("wiki", help="wiki 子命令", parents=[common])
    p_wiki.add_argument("--name", metavar="NAME", help="目标 wiki 名")
    p_wiki.add_argument(
        "--path",
        metavar="DIR",
        help="目标 wiki 根目录（直传，绕过 workspace 解析；供内容子命令，与 --name 二选一）",
    )
    wiki_sub = p_wiki.add_subparsers(dest="wiki_action", metavar="ACTION")

    # add
    pw_add = wiki_sub.add_parser("add", help="新建 wiki", parents=[common])
    pw_add.add_argument("--topic", default=None)
    pw_add.add_argument("--display-name", default=None, dest="display_name")
    pw_add.add_argument("--description", default=None)
    pw_add.add_argument("--tag", action="append", default=[], dest="tags")
    pw_add.add_argument("--model", default=None)
    pw_add.add_argument(
        "--git",
        action="store_true",
        default=False,
        help="vestigial (spec §7): git 操作现已全部由用户手动;"
        "flag 仅为向后兼容保留,无实际效果——落盘后打印的手动 hint 见输出",
    )

    # remove
    pw_rm = wiki_sub.add_parser("remove", help="移除 wiki", parents=[common])
    pw_rm.add_argument(
        "--purge",
        action="store_true",
        help="同时删除 wiki 子目录(默认先备份到 .llmw-trash/)",
    )
    pw_rm.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        help="跳过 --purge 的备份步骤,直接 rmtree(CI / 脚本场景)",
    )
    pw_rm.add_argument("--yes", "-y", action="store_true")

    # rename
    pw_rename = wiki_sub.add_parser(
        "rename",
        help="重命名 wiki (目录 + workspace 索引 + metadata)",
        parents=[common],
    )
    pw_rename.add_argument("--old", required=True, metavar="OLD", help="当前 wiki 名")
    pw_rename.add_argument(
        "--new", required=True, metavar="NEW", help="新 wiki 名 (须符合 NAME_RE)"
    )

    # show
    wiki_sub.add_parser("show", help="查看 wiki 详情", parents=[common])

    # config (sub: get / set / unset)
    pw_cfg = wiki_sub.add_parser(
        "config", help="读写 wiki_metadata.toml", parents=[common]
    )
    pw_cfg.add_argument(
        "cfg_action", nargs="?", default=None, choices=[None, "get", "set", "unset"]
    )
    pw_cfg.add_argument("cfg_key", nargs="?", default=None)
    pw_cfg.add_argument("cfg_value", nargs="?", default=None)

    # enter
    pw_enter = wiki_sub.add_parser(
        "enter",
        help="启动 AI agent session (默认 claude，workspace_local.toml#enter_cli 可切 qodercli/opencode；在当前 tmux session 开窗口，不在 tmux 内 → 兜底 llm_workspace + attach)",
        parents=[common],
    )
    pw_enter.add_argument("--dry-run", action="store_true", dest="dry_run")
    pw_enter.add_argument(
        "--window-suffix",
        default=None,
        dest="window_suffix",
        metavar="SUFFIX",
        help="并行窗口后缀：拼接为 <wiki>-<suffix>（缺省 main）；传了才新开，不传恒为复用跳转",
    )

    # stop
    pw_stop = wiki_sub.add_parser(
        "stop",
        help="终止 wiki 的 agent session 窗口（kill-window；候选 >1 需 --window-suffix 消歧）",
        parents=[common],
    )
    pw_stop.add_argument(
        "--window-suffix",
        default=None,
        dest="window_suffix",
        metavar="SUFFIX",
        help="只匹配 <wiki>-<suffix> 窗口（缺省 = 所有该 wiki 的带标窗口）",
    )
    pw_stop.add_argument("--yes", "-y", action="store_true")

    # ---- 内容层子命令（确定性执行；flags 与行为真源在 llmw/content/* 的 main()）----
    # --name/--path 由 CLI 解析出 wiki root，其余 flag 显式列出（--help 可发现），
    # 组装 argv 转发给模块 main()——模块是 flag 行为唯一真源。
    pw_lint = wiki_sub.add_parser(
        "lint",
        help="deterministic 健康检查（含 spec 版本 / legacy 现场探测）",
        parents=[common],
    )
    pw_lint.add_argument(
        "--severity",
        choices=["error", "warn", "info", "all"],
        default="all",
        help="过滤输出严重性（默认 all）",
    )
    pw_lint.add_argument(
        "--no-git", action="store_true", help="跳过 raw/ 的 git status 检查"
    )
    pw_lint.add_argument(
        "--check-version",
        action="store_true",
        help="扫描 spec 版本 + legacy 现场（互斥模式；默认 dry-run）",
    )
    pw_lint.add_argument(
        "--apply",
        action="store_true",
        help="与 --check-version 联用：把 upgrade plan 以 JSON 输出到 stdout",
    )

    pw_cf = wiki_sub.add_parser(
        "check-fixtures",
        help="wiki fixtures 一致性检查（升级专用探测；dry-run）",
        parents=[common],
    )
    pw_cf.add_argument(
        "--target-spec",
        default=None,
        help="目标 wiki spec 版本（缺省读 llmw.WIKI_SPEC_VERSION 包内常量）",
    )
    pw_cf.add_argument(
        "--list-rules",
        action="store_true",
        help="内省：输出规则清单（不扫描文件）；与 --json 联用具机器可读输出",
    )

    pw_upgrade = wiki_sub.add_parser(
        "upgrade",
        help="升级 wiki 骨架（重渲染 + legacy 路径 + 自检；默认 dry-run）",
        parents=[common],
    )
    pw_upgrade.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只输出计划不写盘（默认；传 --apply 显式写入）",
    )
    pw_upgrade.add_argument(
        "--apply",
        action="store_true",
        help="显式写盘（覆盖 dry-run 默认）；diff 非空时还需 --yes",
    )
    pw_upgrade.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="确认覆盖 drift diff（自定义内容先搬 MEMORY/）",
    )

    pw_id = wiki_sub.add_parser(
        "ingest-diff",
        help="扫 raw/ 找需 LLM 关注的文件（untracked / stale-raw / log-only）",
        parents=[common],
    )
    pw_id.add_argument(
        "--relative", action="store_true", help="输出相对 wiki 根而非 raw/"
    )
    pw_id.add_argument(
        "--check-stale",
        action="store_true",
        help="额外检查已摄取文件：raw mtime 晚于 source 页 updated → 标记 stale-raw",
    )

    pw_write = wiki_sub.add_parser(
        "write",
        help="机械字节写操作（log / index / touch / new / memory）",
        parents=[common],
    )
    pw_write.add_argument(
        "write_args",
        nargs=argparse.REMAINDER,
        metavar="...",
        help="子命令参数（log --op=... / index add <page> / touch <page> / new --type=... / memory add ...），"
        "透传给 llmw.content.wiki_write",
    )

    return parser


def _cmd_status(args) -> int:
    """status 分派：不内在依赖 workspace（真相源是 tmux server）——提到
    resolve_workspace_root 之前分派；R8：默认路径解析失败且有带标窗口时降级孤儿清理
    模式（显式 --workspace/$LLMW_WORKSPACE 失败保持硬报错，防 typo 路径 + 习惯性回 y
    误杀活窗口）。
    """
    from llmw.config import DEFAULT_WORKSPACE, resolve_workspace_root
    from llmw.errors import WorkspaceNotFound
    from llmw.wiki.status import status as wiki_status, status_orphan

    try:
        resolve_workspace_root(_flag(args, "workspace"))  # 存在性检查：失败才进 R8 分支
    except WorkspaceNotFound as e:
        explicit = _flag(args, "workspace") or os.environ.get("LLMW_WORKSPACE")
        if explicit:
            if not Path(explicit).exists():
                e.hint = (e.hint or "") + (
                    "；若 workspace 已删除，不带 --workspace 运行 `llmw status`"
                    " 可交互清理 tmux 残留 session"
                )
            raise
        return status_orphan(
            DEFAULT_WORKSPACE.resolve(),
            e,
            as_json=_flag(args, "json"),
            tmux_line=args.tmux,
        )
    return wiki_status(
        as_json=_flag(args, "json"),
        tmux_line=args.tmux,
    )


def _resolve_content_root(args) -> Path:
    """内容层子命令的 wiki root 解析：--path 直传（不依赖 workspace）或 --name 经 workspace 解析。"""
    from llmw.errors import MissingRequiredFlag, WikiNotFound
    from llmw.workspace import store as ws_store

    path = getattr(args, "path", None)
    name = getattr(args, "name", None)
    if path:
        return Path(path).expanduser().resolve()
    if name:
        from llmw.config import resolve_workspace_root

        ws_root = resolve_workspace_root(_flag(args, "workspace"))
        ws = ws_store.load(ws_root)
        entry = ws.wikis.get(name)
        if entry is None:
            raise WikiNotFound(
                f"wiki '{name}' 不在 workspace 中",
                hint="`llmw wiki add --name=NAME` 注册，或直接用 --path=DIR 指向 wiki 根目录",
            )
        return (ws_root / entry.path).resolve()
    raise MissingRequiredFlag(
        "内容子命令需要 --path=DIR 或 --name=NAME",
        hint="--name 经 workspace 解析；--path 直传任意 wiki 根目录（未注册 wiki / 测试场景）",
    )


def _cmd_wiki_content(args) -> int:
    """wiki 内容层子命令分派（lint / check-fixtures / ingest-diff / write）。

    在 workspace 解析之前处理——--path 直传时不依赖 workspace。
    """
    from llmw.content import ingest_diff, wiki_fixtures, wiki_lint, wiki_write

    # --list-rules 自包含：不扫描文件，不需要 root
    if args.wiki_action == "check-fixtures" and _flag(args, "list_rules"):
        argv = ["--list-rules"]
        if _flag(args, "json"):
            argv.append("--json")
        return wiki_fixtures.main(argv)

    if args.wiki_action == "upgrade":
        from llmw.content import upgrade

        root = _resolve_content_root(args)
        dry_run = not _flag(args, "apply")  # --apply 显式写盘，默认 dry-run
        return upgrade.run_upgrade(
            root,
            dry_run=dry_run,
            yes=_flag(args, "yes"),
            as_json=_flag(args, "json"),
        )

    root = _resolve_content_root(args)
    wa = args.wiki_action

    if wa == "lint":
        argv = [str(root)]
        if args.severity != "all":
            argv += ["--severity", args.severity]
        if args.no_git:
            argv.append("--no-git")
        if args.check_version:
            argv.append("--check-version")
        if _flag(args, "json"):
            argv.append("--json")
        if args.apply:
            argv.append("--apply")
        return wiki_lint.main(argv)

    if wa == "check-fixtures":
        if args.list_rules:
            argv = ["--list-rules"]
            if _flag(args, "json"):
                argv.append("--json")
            return wiki_fixtures.main(argv)
        argv = [str(root)]
        if args.target_spec:
            argv += ["--target-spec", args.target_spec]
        if _flag(args, "json"):
            argv.append("--json")
        return wiki_fixtures.main(argv)

    if wa == "ingest-diff":
        argv = [str(root)]
        if _flag(args, "json"):
            argv.append("--json")
        if args.relative:
            argv.append("--relative")
        if args.check_stale:
            argv.append("--check-stale")
        return ingest_diff.main(argv)

    if wa == "write":
        return wiki_write.main([str(root)] + args.write_args)

    return 1


def main(argv=None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = None
    try:
        _enforce_equals_form(parser, argv)
        args = parser.parse_args(argv)
        if args.command == "init":
            from llmw.config import DEFAULT_WORKSPACE
            from llmw.workspace.manager import init as ws_init

            target = Path(args.path) if args.path else DEFAULT_WORKSPACE
            ws_init(
                Path(target),
                display_name=args.display_name or "LLM Wiki Workspace",
            )
            return 0

        if args.command == "status":
            return _cmd_status(args)

        # wiki 内容层子命令：--path 直传时不依赖 workspace，须在 workspace 解析前分派
        if args.command == "wiki" and args.wiki_action in (
            "lint",
            "check-fixtures",
            "ingest-diff",
            "upgrade",
            "write",
        ):
            return _cmd_wiki_content(args)

        # 下列命令需要先解析 workspace_root；--list-rules 自包含（无需 workspace）先拦截
        if args.command == "check-fixtures" and _flag(args, "list_rules"):
            from llmw.content import workspace_fixtures

            argv_list = ["--list-rules"]
            if _flag(args, "json"):
                argv_list.append("--json")
            return workspace_fixtures.main(argv_list)

        from llmw.config import resolve_workspace_root

        ws_root = resolve_workspace_root(_flag(args, "workspace"))

        if args.command == "check-fixtures":
            from llmw.content import workspace_fixtures

            argv = [str(ws_root)]
            if args.target_spec:
                argv += ["--target-spec", args.target_spec]
            if _flag(args, "json"):
                argv.append("--json")
            return workspace_fixtures.main(argv)

        if args.command == "upgrade":
            from llmw.content import upgrade as _upgrade
            from llmw.content import upgrade_workspace as _ws_upgrade
            from llmw.workspace import store as _ws_store

            dry_run = not _flag(args, "apply")
            yes = _flag(args, "yes")
            as_json = _flag(args, "json")
            worst_rc = 0

            # Phase 1: workspace 骨架
            import io as _io

            ws_buf = _io.StringIO()
            old_stdout, old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout = ws_buf
                sys.stderr = ws_buf
                ws_rc = _ws_upgrade.run_workspace_upgrade(
                    ws_root, dry_run=dry_run, yes=yes, as_json=as_json
                )
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
            ws_out_raw = ws_buf.getvalue()
            ws_rc = max(ws_rc, 0)
            worst_rc = max(worst_rc, ws_rc)

            # workspace 3-terminal JSON：若 as_json 且 ws 阶段产出了 JSON → 解析一次
            ws_result_obj = None
            if as_json and ws_out_raw.strip():
                try:
                    ws_result_obj = json.loads(ws_out_raw)
                except Exception:
                    ws_result_obj = None

            # Phase 2: 逐 wiki
            try:
                ws_toml = _ws_store.load(ws_root)
                wikis = getattr(ws_toml, "wikis", {}) or {}
            except Exception as exc:
                # 加载失败：workspace 骨架升级可能还在跑，记为 not_found 并收尾
                wikis = {}
                if as_json:
                    aggregated_wikis = [
                        {
                            "status": "load_failed",
                            "hint": f"workspace.toml 加载失败：{exc}",
                        }
                    ]
                else:
                    print(
                        f"\n[llmw] warn: workspace.toml 加载失败：{exc}",
                        file=sys.stderr,
                    )
            else:
                aggregated_wikis = []  # type: list
                for wiki_name, entry in wikis.items():
                    wiki_root = (ws_root / getattr(entry, "path", "")).resolve()
                    if not wiki_root.is_dir():
                        aggregated_wikis.append(
                            {
                                "wiki": wiki_name,
                                "status": "not_found",
                                "hint": f"{wiki_root} 不存在",
                            }
                        )
                        worst_rc = max(worst_rc, 2)
                        continue
                    buf = _io.StringIO()
                    old_stdout, old_stderr = sys.stdout, sys.stderr
                    try:
                        sys.stdout = buf
                        sys.stderr = buf
                        rc = _upgrade.run_upgrade(
                            wiki_root, dry_run=dry_run, yes=yes, as_json=as_json
                        )
                    finally:
                        sys.stdout, sys.stderr = old_stdout, old_stderr
                    aggregated_wikis.append(
                        {"wiki": wiki_name, "output": buf.getvalue(), "exit": rc}
                    )
                    worst_rc = max(worst_rc, rc)

            if as_json:
                out = (
                    {"workspace": ws_result_obj}
                    if ws_result_obj is not None
                    else {"workspace": {"raw": ws_out_raw}}
                )
                out["wikis"] = aggregated_wikis
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                print("=== workspace ===")
                print(ws_out_raw.rstrip())
                if ws_rc:
                    print(f"[exit {ws_rc}]")
                if aggregated_wikis:
                    for item in aggregated_wikis:
                        if item.get("status") in ("not_found", "load_failed"):
                            print(f"\n=== {item.get('wiki', '(workspace)')} ===")
                            print(f"[{item['status']}] {item.get('hint', '')}")
                            continue
                        print(f"\n=== {item['wiki']} ===")
                        print(item.get("output", "").rstrip())
                        if item.get("exit"):
                            print(f"[exit {item['exit']}]")
            return worst_rc

        if args.command == "config":
            from llmw.workspace.manager import (
                config_get,
                config_set,
                config_unset,
                config_interactive,
            )

            if args.action is None:
                config_interactive(ws_root)
                return 0
            if args.action == "get":
                config_get(ws_root, args.key)
            elif args.action == "set":
                config_set(ws_root, args.key, args.value)
            elif args.action == "unset":
                config_unset(ws_root, args.key)
            return 0

        if args.command == "model":
            from llmw.models.manager import (
                model_add,
                model_list,
                model_show,
                model_set_default,
                model_unset_default,
                model_remove,
            )

            ma = args.model_action
            if ma == "add":
                model_add(
                    ws_root,
                    model_id=args.model_id,
                    name=args.name,
                    base_url=args.base_url,
                    api_key=args.api_key,
                    context_window=args.context_window,
                    as_default=args.as_default,
                )
            elif ma == "list":
                return model_list(ws_root, as_json=_flag(args, "json"))
            elif ma == "show":
                model_show(ws_root, args.model_id, as_json=_flag(args, "json"))
            elif ma == "set-default":
                model_set_default(ws_root, args.model_id)
            elif ma == "unset-default":
                model_unset_default(ws_root)
            elif ma == "remove":
                model_remove(ws_root, args.model_id, yes=args.yes)
            else:
                print(
                    "[llmw] model 子命令需要 ACTION (add/list/show/set-default/unset-default/remove)",
                    file=sys.stderr,
                )
                return 1
            return 0

        if args.command == "list":
            from llmw.workspace.manager import list_wikis

            return list_wikis(
                ws_root,
                as_json=_flag(args, "json"),
                tag_filter=args.tag or None,
            )

        if args.command == "wiki":
            from llmw.errors import MissingRequiredFlag
            from llmw.wiki.manager import (
                add as wiki_add,
                remove as wiki_rm,
                rename as wiki_rename,
                show as wiki_show,
                wiki_config_get,
                wiki_config_set,
                wiki_config_unset,
                wiki_config_interactive,
            )

            wa = args.wiki_action
            # rename 走 --old/--new 替代 --name; 其余子命令必须有 --name
            if wa != "rename" and not getattr(args, "name", None):
                raise MissingRequiredFlag(
                    "wiki 子命令需要 --name=NAME",
                    hint="rename 走 --old=OLD --new=NEW",
                )
            if wa == "add":
                wiki_add(
                    ws_root,
                    args.name,
                    topic=args.topic,
                    display_name=args.display_name,
                    description=args.description,
                    tags=args.tags or None,
                    model=args.model,
                )
            elif wa == "remove":
                wiki_rm(
                    ws_root,
                    args.name,
                    purge=args.purge,
                    yes=args.yes,
                    no_backup=args.backup is False,
                )
            elif wa == "rename":
                wiki_rename(
                    ws_root,
                    old=args.old,
                    new=args.new,
                    as_json=_flag(args, "json"),
                    quiet=_flag(args, "quiet"),
                )
            elif wa == "show":
                wiki_show(ws_root, args.name, as_json=_flag(args, "json"))
            elif wa == "config":
                if args.cfg_action is None:
                    wiki_config_interactive(ws_root, args.name)
                elif args.cfg_action == "get":
                    wiki_config_get(ws_root, args.name, args.cfg_key)
                elif args.cfg_action == "set":
                    wiki_config_set(ws_root, args.name, args.cfg_key, args.cfg_value)
                elif args.cfg_action == "unset":
                    wiki_config_unset(ws_root, args.name, args.cfg_key)
            elif wa == "enter":
                from llmw.wiki.enter import enter as wiki_enter

                return wiki_enter(
                    ws_root,
                    args.name,
                    dry_run=args.dry_run,
                    window_suffix=args.window_suffix,
                )
            elif wa == "stop":
                from llmw.wiki.manager import stop as wiki_stop

                return wiki_stop(
                    ws_root,
                    args.name,
                    window_suffix=args.window_suffix,
                    yes=args.yes,
                )
            else:
                print(
                    "[llmw] wiki 子命令需要 ACTION (add/remove/rename/show/config/enter/stop)",
                    file=sys.stderr,
                )
                return 1
            return 0

    except LlmwError as e:
        print(format_error(e, debug=getattr(args, "debug", False)), file=sys.stderr)
        return e.exit_code
    except Exception as e:
        if getattr(args, "debug", False):
            raise
        print(format_error(InternalError(str(e)), debug=False), file=sys.stderr)
        return 3

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
