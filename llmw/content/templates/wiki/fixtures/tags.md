# Tags

> agent 在 ingest / query 中遇到新 tag 时直接追加白名单，无需询问用户。
>
> 取值规则：tag 严格小写 kebab-case（与文件名一致）；单页建议 3-7 个，白名单总数
> 建议 10-20 个。
>
> 格式（lint 解析依赖）：每行一条裸 bullet，`- <tag>` 或 `- <分类>：<tag1> / <tag2>`。
> 分类前缀仅展示、不入白名单；多个 tag 用 `/`、`，` 或 `,` 分隔。bullet 不能包在
> code block 或 HTML 注释里；解析不到 tag 时跳过白名单校验。

<!-- tag 白名单起点（upgrade 嫁接锚点，勿删） -->
