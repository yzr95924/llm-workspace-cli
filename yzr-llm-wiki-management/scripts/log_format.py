#!/usr/bin/env python3
"""log.md 行格式正则 + created/updated 时间解析的 SSOT。

权威定义与 [`references/page-templates.md` §7](../references/page-templates.md#7-logmdlog) 同步。
若要改格式，必须**同时**改这里 + page-templates.md §7 + references/claude-md-template.md §一
中的格式说明。

三类符号：
- `LOG_LINE_RE`：全 op（ingest/query/lint/setup）——用于 lint 验证 log.md 每行格式合法
- `LOG_INGEST_RE`：仅 ingest op + 抓标题——用于 ingest_diff 从 log.md 提取"被 ingest 过"的标题集合
- `parse_date_or_datetime`：宽容解析 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM[:SS]` → `datetime.date`，
  给 lint/ingest_diff 解析 frontmatter `created` / `updated` 用；解析失败返 None
"""

import re
from datetime import datetime

# 日期格式（frontmatter created/updated）——按精度从低到高依次尝试
_DATE_ONLY = "%Y-%m-%d"
_DATETIME_MINUTE = "%Y-%m-%d %H:%M"
_DATETIME_SECOND = "%Y-%m-%d %H:%M:%S"


def parse_date_or_datetime(s):
    """宽容解析 `YYYY-MM-DD` / `YYYY-MM-DD HH:MM` / `YYYY-MM-DD HH:MM:SS` → `datetime.date`。

    失败（含 None / 非 str / 格式错）返 None；调用方需自行决定"无法判定 = 跳过 lint"。
    三种格式按精度从低到高试，先匹配先返回（保证 `2026-07-27` 不会误吃成 `2026-07-27 00:00`）。
    """
    if not isinstance(s, str):
        return None
    for fmt in (_DATE_ONLY, _DATETIME_MINUTE, _DATETIME_SECOND):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# 文档 SSOT: references/page-templates.md §7
# HH:MM 可选（regex 非锚定尾部）；老 wikis 仅 date 仍合法
LOG_LINE_RE = re.compile(
    r"^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] "
    r"(ingest|query|lint|setup) \| .+$"
)

# 仅 ingest 分支（用于从 log.md 反查 ingest 过的标题；不是 lint 全格式校验）
LOG_INGEST_RE = re.compile(r"^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] ingest \| (.+)$")
