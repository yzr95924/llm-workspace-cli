# Query 详细流程

Query 综合 wiki 内容页回答问题，有归档价值的结论经用户同意后写回 wiki。

## 准备

- 先读 wiki 根 `AGENTS.md` 与 `wiki/index.md`
- 超过 100 页（经验阈值）的 wiki 再加一次 `wiki/` 全域全文搜索，补充 index 看不全的
  页间引用
- 用户同意归档后，补读 `wiki/log.md`（最近约 30 行，避免重复归档），再进入
  [章节](#归档-query-答案)

## 定位候选页

按关键词 / 类别扫 index，类别按用户问法选：问概念看 `concepts/`，对比两个实体先看
`comparisons/`，问素材出处看 `sources/`，问演进查 concept 页的 inbound links。
启发式搜索，不做全量 grep（准备节的大 wiki 全域搜索不在此限）。关键词命中 index 摘要、
page title 或 `tags` 字段的页必看；只命中正文的页按上下文决定。

## 读相关页

- 不读 raw：raw 已在 source 页消化过；仅当 source 摘要与 raw 疑似矛盾时回 raw 复核
- 不拿 log 当证据：log 是时间线，证据在页面里
- 不全量读：只读直接相关的 3 至 10 页（经验阈值）
- 记下 inbound 链接：相关页面的入链是重要线索

## 按 reviewed 与 contested 分级采信

两个维度互相独立：`reviewed: true` 表示人工审核过（缺省为未审核）；`contested: true`
表示存在未裁定矛盾（配 `contradictions` 指向对端）。综合时按下列规则：

- 引用页带 `contested: true`：无论是否已审核，两说并列、各带来源并注明矛盾未裁定，
  不用 reviewed 身份单方裁定
- 已审核与未审核页都有、结论冲突：两说并列、各带来源，不用 reviewed 身份单方裁定；
  已审核一侧标注 `（优先参考，待人工复审裁定）`
- 只有已审核页能答：正常引用，不额外标注
- 只有未审核页能答：引用并显式标注 `（本页未经人工复审）`
- 两种都有、结论一致：以已审核页为主，未审核页作补充
- 结论冲突但双方都未标 contested：在答案外提醒用户按
  [章节](page-templates.md#矛盾处理) 补标注

## 综合答案

按需组合，综合成答案而非拼接页面原文：

- 直接回答：每条事实带 `（来源：<page path>）`，未审核页额外标注未经人工复审；引
  raw / 外部仓 / 网络等非 wiki 上游事实时走稳定锚点（不锚行号 / 页码等易漂移坐标），
  按[章节](page-templates.md#正文引用的稳定性漂移点规避)
- 对比表（A vs B 类）：行是维度、列是对象、单元格用引用形式
- 时间线（X 的演进类）：按 source 页 published 排序

## 是否归档

满足任一条件即向用户提议归档：答案本质是对比 / 综合 / 新联系；长度超过 200 字；
涉及 3 个及以上 source 页（数字均为经验阈值）。提议合并成一个问题，附建议类型、标题
与目标路径，例如“这段答案本质是 `<comparison / synthesis>`，是否归档为对应类别下的
`<slug>.md`（如 `wiki/comparisons/<slug>.md`）？建议标题：`<title>`”。

归档写回必须以用户明示同意为前提：用户拒绝、或拿不到明示同意（用户不在场、按默认
继续的场景）时一律不归档，不建页、不改 index、不记 log。归档提议只用本次回答已有的
信息，作为本轮 query 收尾；提出后不做任何归档准备，用户之后明确同意才进入归档流程。

## 归档 query 答案

用 `llmw wiki write new --type=comparison --slug=... --title=...`（或
`--type=synthesis`）建页，类型字段直接编辑补齐，见[章节](page-templates.md#各类型模板)。
`--sources` flag 不用于建归档页：它只落 raw/ 路径，供 source 页使用。

- 记录跨页矛盾：`contested` + `contradictions` 互指，字段基准与语义见
  [章节](page-templates.md#可信度与认知质量信号)
- 正文把对话答案整理成可独立阅读的页面；synthesis 逐段溯源（脚注 `[^n]`）见
  [章节](page-templates.md#各类型模板)

## 同步与收尾

- 同步 index：`llmw wiki write index add <page>`
- 追加 log：`llmw wiki write log --op=query --title="<title>"`
- 相关 entity / concept 页按需追加参考来源（wiki 根 `AGENTS.md` 写后必同步条）；
  凡改过既有页正文就跑 `llmw wiki write touch <page>`
