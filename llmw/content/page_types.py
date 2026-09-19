"""内容页 type 的 SSOT——type ↔ 子目录 ↔ index 类别段映射 + lint 合法值集合。

消费方：wiki_write（write new / index）、wiki_lint（frontmatter 校验 / legacy 扫描文案）、
findings（--explain 文案）、wiki_fixtures（index 类别段检查）、init_wiki（骨架目录）。
消费方**不要**重复枚举——新增 / 改名 type 只改本文件（实例契约随 format bump 走）。
"""

# 5 类内容页。顺序 = 展示顺序（--explain / 错误文案按此罗列），非字母序。
CONTENT_TYPES = ("entity", "concept", "source", "comparison", "synthesis")

# type → wiki 子目录名（复数）
TYPE_TO_DIR = {
    "entity": "entities",
    "concept": "concepts",
    "source": "sources",
    "comparison": "comparisons",
    "synthesis": "syntheses",
}

# type → wiki/index.md 类别段名
TYPE_TO_SECTION = {
    "entity": "Entities",
    "concept": "Concepts",
    "source": "Sources",
    "comparison": "Comparisons",
    "synthesis": "Syntheses",
}

WIKI_SUBDIRS = tuple(TYPE_TO_DIR[t] for t in CONTENT_TYPES)

# MEMORY 扩展值——不属内容页类型；仅 lint 兼容既有页，无逻辑消费（契约 canonical 见
# MEMORY/MEMORY.md fixture 头部：MEMORY 桶不写 `type`，分桶按路径）：
# - `memory`：MEMORY/*.md 自用语义，与 wiki 5 类内容页区分
# - `memory-entry`：MEMORY 经验条目标识（与 `memory` 同属 MEMORY 桶）
MEMORY_TYPE_ALIASES = ("memory", "memory-entry")

# lint 校验用合法集合 = 内容页 5 类 + MEMORY 扩展值
VALID_TYPES = frozenset(CONTENT_TYPES) | frozenset(MEMORY_TYPE_ALIASES)

# 中文文案里的 "entity / concept / source / comparison / synthesis" 形态
TYPES_DISPLAY = " / ".join(CONTENT_TYPES)
