"""读命令的共享辅助：解析 workspace、加载 + 校验 manifest。"""

import argparse

from wiki_workspace import errors, manifest, workspace


def resolve_root(args):
    return workspace.find_root(cli_workspace=getattr(args, "workspace", None))


def require_initialized(root):
    if not workspace.is_initialized(root):
        raise errors.CommandError(
            errors.EXIT_USER_ERROR,
            "workspace-not-initialized",
            "在 {} 找不到 .workspace.toml".format(root),
            hint="先运行 llmw init",
        )


def load_manifest(args):
    """解析根、读 + 校验 manifest。任何问题抛 CommandError。
    校验 WARN 只 warn 不 fail。"""
    root = resolve_root(args)
    require_initialized(root)
    try:
        text = workspace.manifest_path(root).read_text(encoding="utf-8")
    except OSError as exc:
        raise errors.CommandError(errors.EXIT_ENV_ERROR, "manifest-parse-failed", str(exc))
    try:
        m, issues = manifest.load_and_validate(text, root)
    except Exception as exc:
        raise errors.CommandError(errors.EXIT_ENV_ERROR, "manifest-parse-failed", str(exc))
    error_issues = [i for i in issues if i.severity == "error"]
    for i in issues:
        if i.severity == "warn":
            errors.emit_warn(i.message)
    if error_issues:
        for i in error_issues:
            errors.emit_error(i.category, i.message)
        raise errors.CommandError(
            errors.EXIT_USER_ERROR,
            "manifest-validation-failed",
            "manifest 校验失败（{} 个 error）".format(len(error_issues)),
        )
    return m


class ArgNamespace(argparse.Namespace):
    """让类型检查器能看到全局 flag 的最小命名空间类型。"""

    workspace = None
    json = False
    quiet = False
    debug = False
