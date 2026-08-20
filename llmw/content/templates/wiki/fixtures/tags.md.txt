# Tags

> 本 wiki 的 `tags` 字段白名单。LLM agent 在 ingest / query 时遇到新 tag **直接追加**
> 到本文件，无需询问用户；用户审计可**直接删除**误判的 bullet，下次 lint 会把
> `tag-not-in-taxonomy`（info 级）报给还引用已删 tag 的页面，由用户裁定二选一：
> 重新加回 / 从页面删除 tag。
>
> 维护纪律与 lint 解析约束见 `yzr-llm-wiki-management/references/wiki-spec.md` §9.1 / §11；
> 模板同步段在 [`../AGENTS.md`](../AGENTS.md)「Tag Taxonomy」（tags.md
> 为白名单主流位置，AGENTS.md 段（老 wiki 为 CLAUDE.md）保留作 fallback 提示路径）。

<!-- 每行一条 bullet：`- <tag>`；裸 bullet 不能包在 code block / HTML comment 里——lint 只读裸文本 -->
（暂无 tag —— 在此追加 `- <tag>` bullet）