"""wiki enter — 启动 AI agent session (默认 claude；workspace.toml#enter_cli=qodercli 切换)

Phase 2 交付（§9.5）：resolved model 通过写 <wiki>/.claude/settings.local.json 的 env 块
（Local 层，优先级 > User）交付，lazy on enter。不再注入 subprocess env、不再传
--setting-sources——user 配置（~/.claude/settings.json）正常加载，overlay 在 Local 层稳赢。

qodercli 路径（workspace.toml#enter_cli = "qodercli"）：跳过 overlay.apply / 不解析 model /
不写 .claude/——只把 wiki 目录传给 qodercli（qodercli 自读 AGENTS.md）。

claude 路径（默认）：同样只传 `--add-dir` 让 claude 自读 `<wiki>/CLAUDE.md`，不显式注入
--system-prompt（避免与自读结果双计入、与 qodercli 行为对齐；cwd=wiki 子目录让自读稳）。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from llmw._compat import TOMLDecodeError
from llmw.errors import (
    ClaudeNotFound,
    SchemaVersionUnsupported,
    WikiDirMissing,
    WikiNotFound,
)
from llmw.models import overlay
from llmw.models.redact import redact_api_key
from llmw.models.resolve import resolve_for_wiki
from llmw.wiki.store import load as wiki_load
from llmw.workspace import store as ws_store


def _resolve_wiki_path(workspace_root: Path, name: str) -> Path:
    ws = ws_store.load(workspace_root)
    if name not in ws.wikis:
        raise WikiNotFound(
            f"wiki '{name}' 不在当前 workspace 中",
            hint="运行 `llmw list` 查看已注册 wiki",
        )
    return workspace_root / ws.wikis[name].path


def _build_cmd(wiki_path: Path):
    """构造 claude 子进程 argv：仅 --add-dir，让 claude 自读 <wiki>/CLAUDE.md。

    不传 --setting-sources：claude 默认加载 user+project+local。cwd=wiki 子目录 → 读到
    <wiki>/.claude/settings.local.json（Local，优先级 > User）→ overlay 稳赢，user 配置同时
    加载。早期版本传 --setting-sources project,local 排除 user，是为防其 env 块盖掉优先级
    更低的 subprocess env overlay；现 overlay 已在 Local 层文件里，无需排除 user。

    不传 --system-prompt：claude 会从 cwd + --add-dir 自动聚合 CLAUDE.md；显式注入会双计入
    并让两 backend 行为分叉（qodercli 路径就不传）。
    """
    return ["claude", "--add-dir", str(wiki_path)], None


def _build_cmd_qodercli(wiki_path: Path):
    """构造 qodercli 子进程 argv：--add-dir。

    qodercli 不读 .claude/settings.local.json，不依赖 model env 注入（qodercli 自读 AGENTS.md）。
    与 _build_cmd 同样只返 cmd，二者签名一致便于 call site 复用。
    """
    return ["qodercli", "--add-dir", str(wiki_path)], None


def enter(workspace_root: Path, name: str, dry_run: bool = False) -> int:
    wiki_path = _resolve_wiki_path(workspace_root, name)

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

    # 选 backend：workspace.toml#enter_cli；未设走 claude
    ws = ws_store.load(workspace_root)
    backend = ws.enter_cli or "claude"
    agent_bin = "qodercli" if backend == "qodercli" else "claude"

    # 检查 agent CLI 在 PATH（dry-run 时跳过）
    if not dry_run and shutil.which(agent_bin) is None:
        raise ClaudeNotFound(
            f"{agent_bin} 不在 PATH",
            hint="安装或加到 PATH 后重试；可用 --dry-run 看命令",
        )

    # qodercli 路径：跳过 resolve / overlay；只传目录
    if backend == "qodercli":
        cmd, prompt = _build_cmd_qodercli(wiki_path)

        if dry_run:
            print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
            print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
            print(
                "[llmw] backend:   qodercli (workspace.toml#enter_cli)",
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
            print("[llmw] cmd:", file=sys.stdout)
            print(f"  qodercli --add-dir {wiki_path}", file=sys.stdout)
            print(f"[llmw] env: LLM_WIKI_ROOT={wiki_path}", file=sys.stdout)
            print("[llmw] --dry-run: 未执行", file=sys.stdout)
            return 0

        os.chdir(wiki_path)
        # 注入 LLM_WIKI_ROOT,让 SKILL 在外部 session 也能定位当前 wiki
        subprocess_env = {**os.environ, "LLM_WIKI_ROOT": str(wiki_path)}
        result = subprocess.run(cmd, env=subprocess_env)
        return result.returncode

    # claude 路径（默认）：resolve → overlay → subprocess
    # Phase 2：通过 resolve 拿最终 model（失败会阻断 enter，在任何写盘之前）
    model = resolve_for_wiki(workspace_root, name)

    cmd, prompt = _build_cmd(wiki_path)

    # dry-run
    if dry_run:
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
        overlay_path, would_write = overlay.inspect(wiki_path, model)
        print(f"[llmw] workspace: {workspace_root}", file=sys.stdout)
        print(f"[llmw] wiki:      {name} ({wiki_path})", file=sys.stdout)
        print(
            "[llmw] backend:   claude (默认)",
            file=sys.stdout,
        )
        print(
            f"[llmw] resolved model: {model.name} ({model.model_id})",
            file=sys.stdout,
        )
        source = "wiki override" if (meta and meta.model) else "registry default"
        print(f"[llmw] source: {source}", file=sys.stdout)
        tag = "(will write)" if would_write else "(up to date, skip)"
        print(f"[llmw] overlay file: {overlay_path}  {tag}", file=sys.stdout)
        print(f"[llmw]   ANTHROPIC_MODEL      = {model.name}", file=sys.stdout)
        print(f"[llmw]   ANTHROPIC_BASE_URL   = {model.base_url}", file=sys.stdout)
        print(
            f"[llmw]   ANTHROPIC_AUTH_TOKEN = {redact_api_key(model.api_key)}",
            file=sys.stdout,
        )
        # Habit template（非用户可配的代码内常量, 随 overlay 一同写入）
        print("[llmw]   (habit template)", file=sys.stdout)
        # 用最长 key 长度对齐 value 列（habit template 组内对齐, 不与 model env 共享列）
        width = max(len(k) for k in overlay._HABIT_TEMPLATE)
        for k, v in overlay._HABIT_TEMPLATE.items():
            print(f"[llmw]     {k:{width}s} = {v}", file=sys.stdout)
        if claude_md.is_file():
            print(
                f"[llmw] CLAUDE.md: ✓ found ({claude_md.stat().st_size} bytes)",
                file=sys.stdout,
            )
        else:
            print("[llmw] CLAUDE.md: ✗ missing", file=sys.stdout)
        print("[llmw] cmd:", file=sys.stdout)
        print(f"  claude --add-dir {wiki_path}", file=sys.stdout)
        print(f"[llmw] env: LLM_WIKI_ROOT={wiki_path}", file=sys.stdout)
        print("[llmw] --dry-run: 未执行", file=sys.stdout)
        return 0

    # 真正执行：lazy 写 overlay（Local 层）→ subprocess 透传 os.environ（无 env overlay，无 --setting-sources）
    overlay.apply(wiki_path, model)
    os.chdir(wiki_path)
    # 注入 LLM_WIKI_ROOT,让 SKILL 在外部 session 也能定位当前 wiki
    # (SKILL.md:57,126,208,333 + claude-md-template.md:11,146 + scripts/ingest_diff.py:215
    #  + lint-checklist.md:15,17 一致期望该环境变量)。用 env= 显式传避免污染父进程 os.environ。
    subprocess_env = {**os.environ, "LLM_WIKI_ROOT": str(wiki_path)}
    result = subprocess.run(cmd, env=subprocess_env)
    return result.returncode
