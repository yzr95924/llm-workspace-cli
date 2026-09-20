#!/usr/bin/env python3
"""log.md 行格式 + frontmatter 时间解析的 SSOT（格式权威；文档描述在 page-templates.md）。

LOG_LINE_RE 供 lint 全格式校验；LOG_INGEST_RE 供 ingest_diff 反查 ingest 标题。
"""

import re
from datetime import datetime

# 日期格式（frontmatter created/updated）——按精度从低到高依次尝试
_DATE_ONLY = "%Y-%m-%d"
_DATETIME_MINUTE = "%Y-%m-%d %H:%M"
_DATETIME_SECOND = "%Y-%m-%d %H:%M:%S"


def parse_date_or_datetime(s):
    """`YYYY-MM-DD` / `YYYY-MM-DD HH:MM[:SS]` → date（精度从低到高试）；失败返 None。"""
    if not isinstance(s, str):
        return None
    for fmt in (_DATE_ONLY, _DATETIME_MINUTE, _DATETIME_SECOND):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# 合法 op 集合（SSOT）——LOG_LINE_RE 与 CLI 的 --op choices 共用，新增 op 只改这里
LOG_OPS = ("ingest", "query", "lint", "setup")

# HH:MM 可选（regex 非锚定尾部）；老 wikis 仅 date 仍合法
LOG_LINE_RE = re.compile(
    r"^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] "
    r"(" + "|".join(LOG_OPS) + r") \| .+$"
)

LOG_INGEST_RE = re.compile(r"^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] ingest \| (.+)$")
