"""llmw add <name> — 经 llm-wiki-management 创建 wiki（spec §3.3）。"""

import re
import subprocess
import sys

from wiki_workspace import _compat, errors, manifest, workspace
from wiki_workspace.commands import _common

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _dependency_help():
    return (
        "Install from: https://github.com/yzr95924/llm-wiki-management\n"
        "Or set LLM_WIKI_MANAGEMENT_PATH=/path/to/llm-wiki-management"
    )


def run(args):
    name = args.name
    if not KEBAB_RE.match(name):
        errors.emit_error(
            "invalid-wiki-name",
            "wiki 名 '{}' 必须 kebab-case".format(name),
            hint="llmw add {}".format(name.lower()),
        )
        return errors.EXIT_USER_ERROR

    try:
        m = _common.load_manifest(args)
        root = _common.resolve_root(args)
    except errors.CommandError as exc:
        return exc.exit_code

    if name in m.wikis:
        errors.emit_error("wiki-already-exists", "wiki '{}' 已存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR

    wiki_dir = root / name
    if wiki_dir.exists() and any(wiki_dir.iterdir()):
        errors.emit_error("wiki-already-exists", "目录 {} 已存在且非空".format(wiki_dir))
        return errors.EXIT_USER_ERROR

    # 硬依赖（spec §1.4）
    skill_root = _compat.find_skill_root(workspace_root=root)
    if skill_root is None:
        errors.emit_error(
            "dep-not-found",
            "llm-wiki-management not found at any of:\n"
            "  - $LLM_WIKI_MANAGEMENT_PATH\n"
            "  - ../llm-wiki-management/SKILL.md\n"
            "  - ~/.claude/skills/llm-wiki-management/SKILL.md",
            hint=_dependency_help(),
        )
        return errors.EXIT_ENV_ERROR

    setup_script = skill_root / "scripts" / "setup_wiki.py"
    topic = args.topic or (args.display_name or name)

    if args.no_git:
        errors.emit_warn("--no-git 未被当前 setup_wiki.py 支持；已忽略")

    cmd = [sys.executable, str(setup_script), topic, str(wiki_dir)]
    errors.emit_debug("subprocess: {} (cwd={})".format(cmd, root))
    result = subprocess.run(cmd, cwd=str(root))
    if result.returncode != 0:
        errors.emit_error(
            "setup-script-failed",
            "setup_wiki.py 退出码 {}".format(result.returncode),
            hint="wiki 目录可能已部分创建；可手动 rm -rf {} 后重试".format(wiki_dir),
        )
        return errors.EXIT_ENV_ERROR

    # 成功 → 追加 manifest 条目（原子写）
    entry = manifest.WikiEntry(
        name=name,
        path=name,
        display_name=args.display_name or topic,
        created=workspace.today_iso(),
        description=args.description or "",
        model=args.model,
        tags=list(args.tag or []),
    )
    m.wikis[name] = entry
    workspace.save_manifest(root, m)

    print("Created wiki '{}' at {}".format(name, wiki_dir))
    print("  下一步：llmw enter {}".format(name))
    return errors.EXIT_OK
