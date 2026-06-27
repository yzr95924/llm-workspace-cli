"""llmw enter <name> — 在 wiki 里 spawn Claude Code（spec §3.7）。"""

import shutil
import subprocess

from wiki_workspace import _compat, errors
from wiki_workspace.commands import _common

SYSTEM_PROMPT_TEMPLATE = """\
You are operating inside an llmw-managed workspace:

  workspace root: {workspace_root}
  wiki name:      {wiki_name}
  wiki root:      {wiki_root}
  skill:          {llm_wiki_management_path}

The llm-wiki-management skill is available (or should be installed).
Use it for ingest / query / lint operations on this wiki.
The wiki's CLAUDE.md ({wiki_root}/CLAUDE.md) contains its schema — read it first
before any write operation."""


def _build_cmd(w, root, wiki_root, model):
    skill_root = _compat.find_skill_root(workspace_root=root)
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        workspace_root=root,
        wiki_name=w.name,
        wiki_root=wiki_root,
        llm_wiki_management_path=skill_root or "(not found)",
    )
    cmd = ["claude"]
    if model:
        cmd += ["--model", model]
    cmd += ["--add-dir", str(root), "--add-dir", str(wiki_root)]
    cmd += ["--system-prompt", prompt]
    return cmd


def run(args):
    try:
        m = _common.load_manifest(args)
        root = _common.resolve_root(args)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    if name not in m.wikis:
        errors.emit_error("wiki-not-found", "wiki '{}' 不存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR
    w = m.wikis[name]
    wiki_root = (root / w.path).resolve()
    model = args.model or w.effective_model(m.default_model)

    # CLAUDE.md 存在性检查
    has_md = (wiki_root / "CLAUDE.md").is_file()
    if not has_md and args.claude_md_check == "fail":
        errors.emit_error(
            "wiki-not-found", "{} 缺 CLAUDE.md（--claude-md-check=fail）".format(wiki_root)
        )
        return errors.EXIT_USER_ERROR
    if not has_md:
        errors.emit_warn("{} 缺 CLAUDE.md".format(wiki_root))

    # 软依赖：仅 warn
    skill_root = _compat.find_skill_root(workspace_root=root)
    if skill_root is None:
        errors.emit_warn("llm-wiki-management 未找到；enter 仍将启动")

    cmd = _build_cmd(w, root, wiki_root, model)

    # dry-run 仅打印，不要求 claude 已安装（便于无 claude 的环境预览命令）
    if args.dry_run:
        print("Would run: " + " ".join(cmd))
        print("(cwd: {})".format(wiki_root))
        return errors.EXIT_OK

    if shutil.which("claude") is None:
        errors.emit_error("claude-not-in-path", "`claude` 不在 PATH", hint="安装 Claude Code CLI")
        return errors.EXIT_ENV_ERROR

    proc = subprocess.run(cmd, cwd=str(wiki_root), check=False)
    return proc.returncode
