"""llmw init — 脚手架一个新 workspace（spec §3.1）。"""

from pathlib import Path

from wiki_workspace import errors, manifest, workspace

CLAUDE_MD_TEMPLATE = """\
# llmw Workspace

This directory is managed by [llmw](https://github.com/yzr95924/llm_workspace_cli).
- `llmw list` — list wikis
- `llmw add <name>` — create a new wiki
- `llmw enter <name>` — launch Claude Code inside a wiki (auto-loads this CLAUDE.md)
"""


def run(args):
    root = Path(workspace.find_root(cli_workspace=getattr(args, "workspace", None)))
    manifest_file = workspace.manifest_path(root)

    if manifest_file.is_file():
        errors.emit_error(
            "workspace-already-exists",
            "{} 已含 .workspace.toml".format(root),
            hint="换一个目录或先 llmw remove",
        )
        return errors.EXIT_USER_ERROR

    root.mkdir(parents=True, exist_ok=True)
    m = manifest.empty_manifest(workspace.today_iso(), default_model=args.default_model)
    workspace.save_manifest(root, m)
    (root / "CLAUDE.md").write_text(CLAUDE_MD_TEMPLATE, encoding="utf-8")

    if (root / ".git").is_dir():
        errors.emit_info("检测到 git 仓：git add .workspace.toml CLAUDE.md && git commit")
    else:
        errors.emit_info("建议：cd {} && git init".format(root))

    print("Initialized llmw workspace at {}".format(root))
    return errors.EXIT_OK
