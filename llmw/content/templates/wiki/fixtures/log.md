---
title: "{{TOPIC_NAME}} Log"
type: log
tags: [log]
created: {{SETUP_DATE}}
updated: {{SETUP_DATE}}
---

> 追加条目用 `llmw wiki write log`；手工编辑按下列格式自行截断。启用 git 时完整历史
> 用 `git log -p -- wiki/log.md` 查看。
>
> 格式：`## [YYYY-MM-DD HH:MM] <op> | <title>`（op ∈ {{LOG_OPS}}；日期可只写
> `YYYY-MM-DD`）。`ingest` 可追加第三段 `| <raw 相对路径>`（wiki 根相对、`raw/` 开头）。
> 标题一行；URL 与详细摘要写对应页面。
>
> 滚动窗口：超过 {{LOG_RETENTION_LIMIT}} 条删最旧，保留最近 {{LOG_RETENTION_LIMIT}} 条；
> frontmatter 与说明块不动。

## [{{SETUP_DATE}}] setup | Initial scaffold by llmw CLI
