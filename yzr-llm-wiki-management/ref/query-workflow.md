# Query workflow

综合 wiki 内容页与 `discussions/` 草稿回答问题；有归档价值的结论经用户同意后写回 wiki。

## 流程

1. 读 wiki 根 `AGENTS.md` 与 `wiki/index.md`；用问题关键词检索 `discussions/` 的文件名
   与正文，只读直接相关草稿；候选页不足或证据不够时对 `wiki/` 做全域关键词搜索
2. 按 index、页面标题、`tags` 和 inbound 链接定位候选页；只读直接相关页面（3-10 页
   为常见范围，候选不足时不硬凑、候选过多时分批读）。raw 默认不读，只有 source 摘要
   与 raw 疑似矛盾时回查；log 只帮判断近期动作，不当证据
3. 作答时综合内容，不拼接页面原文：
   - 每条事实带 `（来源：<page path>）`；引用 discussions 草稿另标
     `（讨论稿，未整理）`并给具体路径；引用未审核页时标注未经人工复审
   - `contested` 页或证据冲突时两说并列、各带来源，不用 `reviewed` 身份单方裁定；
     已审核与未审核冲突时，已审核侧标注优先参考、待人工复审裁定；两说一致时以已
     审核页为主
   - 冲突双方都未标 `contested` 时，在答案外提醒用户补标注，本轮不代标；处理方式见
     [章节](page-templates.md#矛盾处理)
   - discussions 与 wiki 冲突不按草稿新旧覆盖，交用户裁定；raw 与 wiki 摘要矛盾时
     以 raw 为准并在交付说明提醒用户修正摘要
   - 引 raw、外部仓或网络事实时用稳定锚点（代码符号 / PDF 章节 / 网页记值加日期）
4. 答案本质是对比 / 综合 / 新联系、超过 200 字或涉及 3 个以上 source 页时，提议归档为
   comparison 或 synthesis；用户明示同意前不建页、不改 index、不记 log
5. 同意归档后先读 `wiki/log.md` 最近约 30 行与 `wiki/tags.md`，再建页。
   命令模板（synthesis 同理）：

   ```bash
   llmw wiki --path=<wiki-root> write new --type=comparison --slug=<slug> --title=<t> --description=<d> --tags=<tag>
   ```

   类型字段与正文规格见[章节](page-templates.md#页面规格)。
   comparison 手动补 `compared:`；synthesis 手动补 `threads:` 与 `sources:`。
   依赖 discussions、新 raw 或外部仓新事实的结论先转正式 source 页再归档；
   归档页只引用 wiki 内页
6. 同步收尾（所有正文编辑完成后统一执行）：
   - 改过正文的每页跑 `llmw wiki --path="$LLM_WIKI_ROOT" write touch <page>`
   - 新建页跑 `llmw wiki --path="$LLM_WIKI_ROOT" write index add <page>`；改过既有
     reviewed 页正文后也重新 `index add` 刷新徽标
   - 记 `llmw wiki --path="$LLM_WIKI_ROOT" write log --op=query --title="<title>"`
7. 跑 `llmw wiki --path="$LLM_WIKI_ROOT" lint --severity=error`：本次改动不引入
   error 级 finding（既有 finding 列入交付说明）
