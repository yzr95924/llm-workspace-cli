# MEMORY

> LLM agent 的持久化记忆索引（无 frontmatter）。
>
> **加载机制**：`<wiki-root>/AGENTS.md` 顶部单行 `@MEMORY/MEMORY.md` 自动加载本文件全文；
> 不展开 `@import` 的 agent 由 AGENTS.md 顶部 Read 指令兜底（直接 `Read MEMORY/MEMORY.md`）。
>
> 条目增删时**只改本文件**——`@import` 引用自动同步指向全文，AGENTS.md 不持有副本，无漂移。
> 各条目正文（`MEMORY/<slug>.md`）按需 `Read`，lint `memory-not-indexed` 兜底漏列（见
> `yzr-llm-wiki-management/references/lint-checklist.md` §二.14）。
>
> 何时写 / 文件命名 / 维护纪律见 SKILL §4 Memory（本文件不重复，避免口径分裂）。

## 索引

<!-- 每条一行：短横线 + slug + 一句话摘要 + 指向 <slug>.md 正文的 Markdown 链接 -->
（暂无条目）