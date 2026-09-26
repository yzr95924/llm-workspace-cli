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

LOG_RETENTION_LIMIT = 50

# 时间戳：HH:MM / :SS 均可选（老 wikis 仅 date 仍合法）；全非捕获——取组只认命名组，
# 避免嵌套可选组把位置索引带偏（见 ingest_diff 的历史 group 错位 bug）
_LOG_TIMESTAMP = r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}(?::\d{2})?)?"

LOG_LINE_RE = re.compile(r"^## \[" + _LOG_TIMESTAMP + r"\] (" + "|".join(LOG_OPS) + r") \| .+$")

# ingest 行可带第三段 ` | <raw 相对路径>`（wiki 根相对、raw/ 前缀；write log --raw 落盘）；
# 老条目只有 title → raw 组不参与（None）。解析歧义免疫：raw 段固定以 "raw/" 起头
LOG_INGEST_RE = re.compile(r"^## \[" + _LOG_TIMESTAMP + r"\] ingest \| (?P<title>.+?)(?: \| (?P<raw>raw/.+?))?$")
