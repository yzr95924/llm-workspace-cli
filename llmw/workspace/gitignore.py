"""workspace 级 .gitignore managed block 维护（横切关注点，独立成模块）

被 workspace init / workspace.store 迁移 / wiki add 的 purge / wiki enter 的
opencode overlay 共同消费——原先散落在 workspace.manager 的私有函数 + 三处
跨模块 import 私有名（store 反向依赖 manager 成环），现收口为公开 API。
"""

import re
from pathlib import Path

from llmw.fsutil import atomic_write

# workspace 级 .gitignore managed block 内容（spec workspace-spec.md §10 + llmw 自有扩展）
# 前 3 行严格对齐 spec §10（registry + Claude Code / Qoder IDE 项目级 overlay）。
# 单仓模型：wiki 是 workspace 直属子目录，**/.<agent>/settings*.json 通配覆盖所有
# wiki 的 overlay secret，不依赖 per-wiki .gitignore / wiki scaffold（见 §10）。
# 后 3 行为 llmw 自有扩展（spec §10 字面未列，"至少包含"语义下保留以避免误提交，
# 见 MEMORY 驳正条目）：
# - workspace_local.toml  主机相关运行时配置 (enter_cli，schema v2 起从 workspace.toml
#                          拆出；跨主机各异，必须本地化)
# - .llmw-trash/          wiki remove --purge 写入的备份目录
# - **/opencode.json      enter_cli=opencode 的 overlay 落盘（含明文 apiKey，与
#                          settings*.json 同一安全模型，见 llmw/models/overlay_opencode.py）
GITIGNORE_LINES = (
    "workspace_models.toml",
    "**/.claude/settings*.json",
    "**/.qoder/settings*.json",
    "workspace_local.toml",
    ".llmw-trash/",
    "**/opencode.json",
)

# spec §10: workspace .gitignore 的通用忽略段（OS / 编辑器 / Obsidian / 临时）。
# 全新 init 时与 managed block 一同落盘；已有 .gitignore 时不追加（尊重外部来源）。
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
    """确保 workspace 级 .gitignore 含 llmw managed block + 通用忽略段（spec §10）。

    - 文件不存在 → 创建（managed block + OS / Obsidian / 临时通用段）
    - 文件存在 → 仅更新 managed marker 区间（secret 排除行），通用段不动
      （已有 .gitignore 视为用户/外部来源，不覆盖其内容）
    """
    gitignore = workspace_root / ".gitignore"
    marker_start = "# >>> llmw (managed by llmw) >>>"
    marker_end = "# <<< llmw <<<"
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
