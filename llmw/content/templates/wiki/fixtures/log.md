---
title: "{{TOPIC_NAME}} Log"
type: log
tags: [log]
created: {{SETUP_DATE}}
updated: {{SETUP_DATE}}
---

> 追加条目用 `llmw wiki write log`；手工编辑时按下列格式并自行截断。启用 git 时，
> 完整历史可用 `git log -p -- wiki/log.md` 查看。
>
> 格式：`## [YYYY-MM-DD HH:MM] <op> | <title>`（op ∈ {{LOG_OPS}}；日期也可只写
> `YYYY-MM-DD`）。`ingest` 条目可追加第三段 `| <raw 相对路径>`（wiki 根相对、`raw/`
> 开头）。标题不超过一行；URL 与详细摘要写进对应页面。
>
> 滚动窗口：条目超过 {{LOG_RETENTION_LIMIT}} 条时删除最旧的，保留最近
> {{LOG_RETENTION_LIMIT}} 条（frontmatter 与说明块不动）。

## [{{SETUP_DATE}}] setup | Initial scaffold by llmw CLI
