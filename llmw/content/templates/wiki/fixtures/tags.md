# Tags

> LLM agent 在 ingest / query 时遇到新 tag **直接追加**到本文件，无需询问用户。
>
> **取值规则**：tag 严格小写 + kebab-case（与文件名命名一致）；单页 `tags` 建议 3-7 个，
> 过多说明页面主题过散，考虑拆分或聚焦；白名单 tag 总数 10-20 个是建议值（**非权威阈值**，由用户 / agent
> 按主题复杂度酌情伸缩）。
>
> **格式约束（lint 解析依赖）**：每行一条裸 bullet，两种形态：`- <tag>` 或 `- <分类>：<tag1> / <tag2>`
> （分类前缀仅作展示、不入白名单，可用中文，如 `- 模型：model / architecture`）；
> 多个 tag 用 `/` `，` `,` 分隔。bullet 不能包在 code block / HTML comment 里（lint 只读裸文本）。
> lint 找不到任何 tag 来源或解析出 0 个 tag 时**静默跳过**（不报错）。

<!-- tag 白名单起点（upgrade 嫁接锚点，勿删） -->
