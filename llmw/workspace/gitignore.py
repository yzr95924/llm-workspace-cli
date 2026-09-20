"""workspace 级 .gitignore managed block 维护（init / purge / upgrade 共用的公开 API）。"""

import re
from pathlib import Path

from llmw.fsutil import atomic_write

# managed block 内容（本文件 SSOT）。前 3 行对齐 registry + Claude / Qoder overlay
# secret；后 3 行为 llmw 自有扩展：workspace_local.toml（主机相关运行时）/
# .llmw-trash/（purge 备份）/ **/opencode.json（机器本地生成，含遗留明文兜底）。
GITIGNORE_LINES = (
    "workspace_models.toml",
    "**/.claude/settings*.json",
    "**/.qoder/settings*.json",
    "workspace_local.toml",
    ".llmw-trash/",
    "**/opencode.json",
)

# managed block 边界 marker（SSOT）——所有提取 / 替换 / 渲染消费方引此常量，不得复刻字面量
GITIGNORE_MARKER_START = "# >>> llmw (managed by llmw) >>>"
GITIGNORE_MARKER_END = "# <<< llmw <<<"

# 通用忽略段（OS / 编辑器 / Obsidian / 临时）；仅全新 init 落盘，已有 .gitignore 不追加
_GITIGNORE_COMMON = """\
# OS / 编辑器
.DS_Store
.idea/
.vscode/
*.swp
*.swo

# Obsidian 配置（保留 vault 内容）
.obsidian/workspace*
.obsidian/cache

# 临时文件
*.tmp
*.bak
"""


def ensure_workspace_gitignore(workspace_root: Path) -> None:
    """确保 .gitignore 含 managed block：文件不存在则连通用段一起建，已存在只换 block 区间。"""
    gitignore = workspace_root / ".gitignore"
    marker_start = GITIGNORE_MARKER_START
    marker_end = GITIGNORE_MARKER_END
    block = marker_start + "\n" + "\n".join(GITIGNORE_LINES) + "\n" + marker_end

    if not gitignore.is_file():
        atomic_write(gitignore, block + "\n\n" + _GITIGNORE_COMMON)
        return

    text = gitignore.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(marker_start) + r".*?" + re.escape(marker_end), re.DOTALL
    )
    m = pattern.search(text)
    if m:
        if m.group(0) == block:
            return  # 已是最新 block
        new_text = pattern.sub(block, text)  # 老 block → 替换为最新
    else:
        # 无 block → 追加（保证前导换行 + 末尾换行）
        sep = "" if (text.endswith("\n") or not text) else "\n"
        tail = "" if text.endswith("\n") else "\n"
        new_text = text + sep + block + tail
    atomic_write(gitignore, new_text)
