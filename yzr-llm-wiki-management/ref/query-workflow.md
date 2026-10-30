# Query workflow

综合 wiki 内容页与 `discussions/` 草稿回答问题；有归档价值的结论经用户同意后写回 wiki。

## 流程

1. 读 wiki 根 `AGENTS.md` 与 `wiki/index.md`；用问题关键词检索 `discussions/` 的文件名
   与正文，只读直接相关草稿；超过 100 页的 wiki 再做一次 `wiki/` 全域搜索
2. 按 index、页面标题、`tags` 和 inbound 链接定位候选页；只读直接相关的 3 至 10 页。
   raw 默认不读，只有 source 摘要与 raw 疑似矛盾时回查；log 只帮判断近期动作，不当证据
3. 作答时综合内容，不拼接页面原文：
   - 每条事实带 `（来源：<page path>）`；引用 discussions 草稿另标
     `（讨论稿，未整理）`并给具体路径
   - `contested` 页或证据冲突时两说并列、各带来源，不用 `reviewed` 身份单方裁定；
     已审核与未审核冲突时，已审核侧标注“优先参考，待人工复审裁定”；只有未审核页能答时
     标注未经人工复审；两说一致时以已审核页为主
   - 冲突双方都未标 `contested` 时，在答案外提醒用户补标注，本轮不代标；处理方式见
     [章节](page-templates.md#矛盾处理)
   - discussions 与 wiki 冲突不按草稿新旧覆盖，交用户裁定
   - 引 raw、外部仓或网络事实时按[章节](page-templates.md#写作规则)用稳定锚点
4. 答案本质是对比 / 综合 / 新联系、超过 200 字或涉及 3 个以上 source 页时，提议归档为
   comparison 或 synthesis；用户明示同意前不建页、不改 index、不记 log
5. 同意归档后先读 `wiki/log.md` 最近约 30 行，再建页：
   `llmw wiki write new --type=comparison --slug=<slug> --title=<title>`（synthesis 同理），
   类型字段与正文规格见[章节](page-templates.md#页面规格)。`--sources` flag 不用于
   归档页；依赖 discussions 的结论先经用户确认转入 raw 并 ingest，归档页只引用 wiki 页
6. 同步收尾：`llmw wiki write index add <page>`、
   `llmw wiki write log --op=query --title="<title>"`；改过既有页正文就跑
   `llmw wiki write touch <page>`
