# Query 详细流程

Query 把 wiki 里多份资料综合成答案，好答案归档回 wiki 继续可用；边界以 wiki 根
`AGENTS.md` 的 Query 纪律节为准

## 定位候选页

预读按本 skill 执行原则的分级：纯读只读 wiki 根 `AGENTS.md` + `wiki/index.md`。
按关键词 / 类别扫 index（哪个类别看用户问法：概念 → `concepts/`、对比两实体 →
先看 `comparisons/` 已归档的、素材在 `sources/`、演进 → 查 concept 页 inbound
links）。**启发式搜索，不做全量 grep**：关键词命中 index 摘要 / page title /
`tags` 字段 = 必看；读页时仅命中正文 = 看上下文决定（执行原则里大 wiki 的全域
全文搜索补链不在此限）

## 读相关页

- **不读 raw**：raw 已在 source 页消化过；仅当 source 摘要与 raw 疑似矛盾时回
  raw 复核
- **不全量读**：只读直接相关的 3~10 页（经验阈值）
- **记下 inbound 链接**：这些是相关上下文的强信号

## 按 reviewed 与 contested 分级采信

两个正交维度：`reviewed: true` = 人工审核背书（缺省 = 未审核）；
`contested: true` = 存在未裁定矛盾（配 `contradictions` 指向对端）。综合时按
下列规则：

- 只有已审核页能答：正常引用，不额外标注
- 只有未审核页能答：引用 + 显式标注"（本页未经人工复审）"
- 两种都有、结论一致：引用已审核页为主，未审核页作补充
- 两种都有、结论冲突：两说并列、各带来源，**不**用 reviewed 身份单方裁定；已
  审核一侧标注"优先参考，待人工复审裁定"
- 结论冲突但双方都未标 contested：在答案外提醒用户走
  [章节](page-templates.md#矛盾处理) 补标注

## 综合答案

按需组合：

- **直接回答**：每条事实带 `（来源：<page path>）`，未审核页额外标"未经人工复审"
- **对比表**（"A vs B" 类）：行 = 维度、列 = 对象、单元格用引用形式
- **时间线**（"X 的演进" 类）：按 source 页 published 排序
- **矛盾标注**：按上节分级采信规则，不和稀泥

## 是否归档

满足任一即向用户提议归档，合并成一个问题、附建议类型与标题："这段答案本质是
`<comparison / synthesis>`，是否归档为 `wiki/comparisons/<slug>.md`（或
`wiki/syntheses/<slug>.md`）？建议标题：`<title>`"。触发条件：答案本质是对比 /
综合 / 新联系；长度 > 200 字；涉及 ≥ 3 个 source 页（数字均为经验阈值）。归档
写回以用户**明示同意**为前提：拒绝、或拿不到明示同意（含用户不在场、按默认
继续的场景）一律不归档——不落页、不动 index、不记 log（wiki 无痕）；同意 =
走下一步。归档提议只用本次回答已有的信息，作为本轮 query 收尾；提出后不再做任何
归档准备，用户之后明确同意才进入归档流程

## 归档 query 答案

脚手架 `llmw wiki write new --type=comparison --slug=... --title=...`（或
`--type=synthesis`），类型必填字段照[章节](page-templates.md#各类型模板)
直接编辑补齐。**不走 `--sources` flag**：它专属于 source 页（落 `raw/` 相对路径），
synthesis 的 `sources` frontmatter 字段是 wiki 内页路径

- 记录跨页矛盾：`contested` + `contradictions` 互指，字段基准与语义见
  [章节](page-templates.md#可信度与认知质量信号)
- 正文把对话答案整理成可独立阅读的页面；synthesis 逐段溯源（脚注 `[^n]`）见
  [章节](page-templates.md#synthesis综合页)
- 正文含交互流 / 架构关系时优先配图，见
  [章节](page-templates.md#图示使用指引)
- 正文引用上游易变事实时过一遍
  [章节](ingest-workflow.md#正文引用的稳定性漂移点规避)

## 簿记与收尾

- 同步 index：`llmw wiki write index add <page>`
- 追加 log：`llmw wiki write log --op=query --title="<title>"`
- 相关 entity / concept 页按需追加"参考来源"段（纪律见 wiki 根 `AGENTS.md`
  写后必同步条）；凡改过既有页正文 → `llmw wiki write touch <page>`

## Query 失败的常见原因

index 没维护 / source 页过期 / 同名页指不同东西，都有对应 lint finding，
先跑 `llmw wiki lint` 按输出行动
