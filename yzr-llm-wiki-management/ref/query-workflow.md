# Query 详细流程

Query 是 wiki 的"消费侧"——把多份资料综合成答案，**好答案归档回 wiki** 让复利继续

## 流程详解

### Step 1：定位候选页

先读 `wiki/index.md`，按关键词 / 类别扫（哪个类别看用户问法：概念→`concepts/`、对比两实体
→`sources/`、演进→查 concept 页 inbound links）。**启发式搜索，不做全量 grep**：关键词命中
index 摘要 / page title / `tags` 字段 → 必看；只命中正文 → 看上下文决定

### Step 2：读相关页

- **不要读 raw**——raw 已在 source 页消化过；仅当 source 摘要与 raw 疑似矛盾时回 raw 复核
- **不要全量读**——只读直接相关的 3~10 页（经验阈值）
- **记下 inbound 链接**——这些是相关上下文的强信号

### Step 2.5：按 reviewed / contested 标注采信等级

读完候选页后按 frontmatter 分三栏标注：已审核（`reviewed: true`，优先采信）/ 未审核（缺省
或非 true，辅助采信需显式标注）/ 跨页矛盾（`contested: true`，未裁定，看 `contradictions`）

综合时按下表采信（`contested: true` 优先采信 reviewed 那一侧）：

| 场景 | 行为 |
| --- | --- |
| 只有 reviewed 页能答 | 正常引用，不额外标注 |
| 只有 un-reviewed 页能答 | 引用 + 显式标注「（本页未经人工复审）」 |
| 两种都有，结论一致 | 引用 reviewed 页为主，un-reviewed 作为补充 |
| 两种都有，结论冲突 | 标注「存在两种说法：X（来源 A，已审核）/ Y（来源 B，未审核），以 X 为准」+ 建议人复审 B |

### Step 3：综合答案

按需组合：直接回答（每条事实带 `（来源：<page path>）`，un-reviewed 页额外标「未经人工复审」）
→ 对比表（"A vs B" 类，行 = 维度、列 = 对象、单元格用引用形式）→ 时间线（"X 的演进" 类，按
source 页 published 排序）→ 矛盾标注（发现冲突时**不要和稀泥**：A 说 X、B 说 Y，各带来源，
注明可能是定义 / 上下文 / 数据更新差异，建议进一步调研）

答案形态与归档的完整实跑 trace 见 `examples.md` 样例二

### Step 4：询问归档

**好答案必须问"是否归档"**——满足任一即问：答案本质是对比 / 综合 / 新联系；长度 > 200 字（经验阈值）且
可能复用；涉及 ≥ 3 个 source 页。问题模板："这段答案本质是 `<comparison / synthesis /
finding>`，是否归档为 `wiki/comparisons/<slug>.md`（或 `wiki/syntheses/<slug>.md`）？
建议标题：`<title>`"

用户拒绝 → 尊重，不强求，亦不追加 log（无 wiki 痕迹）；用户同意 → 走 Step 5

### Step 5：归档 query 答案

用 [章节](page-templates.md#各类型模板) 的 comparison / synthesis 模板。脚手架
`llmw wiki write new --type=comparison --slug=... --title=...`（或 `--type=synthesis`）——
它只落基础字段（title / type / tags / created / updated），类型必填字段照模板用 Edit 补：

- `comparison` 页补 `compared: [<path-a>, <path-b>]`
- `synthesis` 页补 `threads: [<主题>...]` + `sources: [<wiki 内页路径>]`（**不是 raw/**；缺
  `sources` 触发 lint `missing-sources`）——`--sources` flag 是 source 页专属（raw/ 路径），
  synthesis 不走它
- 记录跨页矛盾时：`contested: true` + `contradictions: [对端页]`，且对端页同步互指（单向
  触发 lint `contradiction-asymmetric`；字段语义见
  [章节](page-templates.md#可选可信度与认知质量信号)）
- 正文把对话答案整理成可独立阅读的页面；**synthesis 页对来源可分的断言用标准脚注 `[^n]`
  逐段溯源**（写法见 [章节](page-templates.md#synthesis综合页)），让论点不重读 raw 就能回溯到
  source——这是 synthesis 区别于 source 摘要的关键
- 正文含交互流 / 架构关系时优先配图——见 [章节](page-templates.md#图示使用指引)
- 正文引用上游易变事实时同样过感知测试——见
  [章节](ingest-workflow.md#正文引用的稳定性漂移点规避)

### Step 6：簿记与收尾

- 同步 index：`llmw wiki write index add <page>`
- 追加 log：`llmw wiki write log --op=query --title="<title>"`
- 相关 entity / concept 页按需追加"参考来源"段（纪律见 wiki 根 `AGENTS.md`「写后必同步」）；
  凡 Edit 过既有页正文 → `llmw wiki write touch <page>`
- 启用 git 时建议 commit（同 ingest）；裸目录树 wiki 跳过

## Query 的边界

- **不**引用未存在于 wiki 的来源——只引用 wiki 内的页面
- **不**绕过 source 页直接读 raw（冲突时才回 raw 复核，见 Step 2）
- 其余边界以 wiki 根 `AGENTS.md` Query 纪律节为准

## Query 失败的常见原因

- `index.md` 没维护——所有路径都找不到，先修 index
- source 页过期——读到的信息已过时，建议先 lint
- 概念粒度不一致——同名页在不同页指不同东西，提示用户合并或重命名
