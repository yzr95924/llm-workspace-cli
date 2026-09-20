"""内容页 type 的 SSOT——type ↔ 子目录 ↔ index 类别段映射 + lint 合法值集合。

新增 / 改名 type 只改本文件，消费方不要重复枚举。
"""

# 顺序 = 展示顺序（--explain / 错误文案按此罗列），非字母序
CONTENT_TYPES = ("entity", "concept", "source", "comparison", "synthesis")

TYPE_TO_DIR = {
    "entity": "entities",
    "concept": "concepts",
    "source": "sources",
    "comparison": "comparisons",
    "synthesis": "syntheses",
}

TYPE_TO_SECTION = {
    "entity": "Entities",
    "concept": "Concepts",
    "source": "Sources",
    "comparison": "Comparisons",
    "synthesis": "Syntheses",
}

WIKI_SUBDIRS = tuple(TYPE_TO_DIR[t] for t in CONTENT_TYPES)

# MEMORY 扩展值：不属内容页类型，仅供 lint 兼容既有页（MEMORY 分桶按路径，不写 type）
MEMORY_TYPE_ALIASES = ("memory", "memory-entry")

VALID_TYPES = frozenset(CONTENT_TYPES) | frozenset(MEMORY_TYPE_ALIASES)

TYPES_DISPLAY = " / ".join(CONTENT_TYPES)
