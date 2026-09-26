# Query 详细流程

Query 是 wiki 的"消费侧"——把多份资料综合成答案，**好答案归档回 wiki** 让复利继续。
跨页综合暴露单篇看不到的**联系** / **矛盾** / **趋势**——这是 wiki 比 RAG 多的"复利结构"

## 入口与触发

- 用户问"wiki 里有 X 吗" / "wiki 里关于 Y 有什么"
- 用户问"对比 A 和 B" / "总结一下 X" / "为什么 A 比 B 好"
- 隐式触发：ingest 完成后 agent 主动建议"要不要查一下新内容和已有内容的联系？"

## 流程详解

### Step 1：定位候选页

**先读 `wiki/index.md`**——按关键词 / 类别扫：

- 用户问"`<Concept A>`" → 看 `concepts/` 类别
- 用户问"`<Entity X>` 和 `<Entity Y>` 哪个更好" → 看 `sources/` 找两篇
- 用户问"`<Concept A>` 的演进" → 看 `concepts/<slug>.md` 是否有 inbound
  links

**启发式搜索**（不要做全量 grep）：

- 关键词出现在 index 摘要里 → 必看
- 关键词出现在 page title 里 → 必看
- 关键词出现在 source / concept 页的 `tags` 字段 → 必看
- 关键词在 page 正文里出现但不在上述三个位置 → 看上下文决定

### Step 2：读相关页

- **不要读 raw**——raw 已经在 source 页里消化过；除非发现 source 摘要与 raw 矛盾
- **不要全量读**——只读直接相关的 3~10 页
- **记下 inbound 链接**——这些是相关上下文的强信号

### Step 2.5：按 reviewed / contested 标注采信等级

读完候选页后，agent 按 frontmatter 分三栏标注：

```text
已审核（reviewed: true）—— 优先采信
  - concepts/transformer.md
未审核（reviewed 缺省 / 不为 true）—— 辅助采信，需显式标注
  - concepts/flash-attention-2.md
跨页矛盾（contested: true）—— 未裁定冲突，参考其 contradictions 字段
```

综合时按下表采信（`contested: true` 优先采信 reviewed 那一侧）：

| 场景 | 行为 |
| --- | --- |
| 同一问题只有 reviewed 页能答 | 正常引用，不额外标注 |
| 同一问题只有 un-reviewed 页能答 | 引用 + 显式标注「（本页未经人工复审）」 |
| 同一问题两种页都有，结论一致 | 引用 reviewed 页为主，un-reviewed 作为补充 |
| 同一问题两种页都有，结论冲突 | 标注「存在两种说法：X（来源 A，已审核）/ Y（来源 B，未审核），以 X 为准」+ 建议人复审 B |

### Step 3：综合答案

答案结构（按需组合）：

1. **直接回答**——用引用形式，每条事实带 `（来源：<page path>）`；un-reviewed 页面额外标「未经人工复审」
2. **对比表**（如果是 query "A vs B" 类）——Markdown 表格，行 = 维度，列 = 对象，
   单元格用引用形式
3. **时间线 / 演进**（如果是 query "X 的演进" 类）——按 source 页 published 排序
4. **矛盾标注**（如果发现冲突）——不要"和稀泥"：
   > A 说 X（来源：...），B 说 Y（来源：...）。这可能是定义差异 / 上下文差异 /
   > 数据更新，建议进一步调研

> 答案形态与归档的完整实跑 trace 见 `examples.md` 样例二——本文件不重抄

### Step 4：询问归档

**好答案必须问"是否归档"**——以下任一满足都问：

- 答案本质是"对比" / "综合" / "发现新联系"
- 答案长度 > 200 字且可能复用
- 答案涉及 ≥ 3 个 source 页

**问题模板**：

> 这段答案本质是 `<comparison / synthesis / finding>`，是否归档为
> `wiki/comparisons/<slug>.md`（或 `wiki/syntheses/<slug>.md`）？建议标题：
> `<title>`

用户拒绝 → 尊重，不强求，亦不追加 log（无 wiki 痕迹）；用户同意 → 走 Step 5

### Step 5：归档 query 答案

使用 [章节](page-templates.md#各类型模板)的 comparison / synthesis 模板

- `comparison` 页：focus 在 "A vs B"，frontmatter `compared: [<path-a>, <path-b>]`（必填）
- `synthesis` 页：focus 在 "跨多个 source 的综合洞察"，frontmatter `threads: [<主题>...]` +
  `sources: [<wiki 内页路径>]`（均必填；缺 `sources` 触发 lint `missing-sources`）
- 脚手架只生成基础字段（title / type / tags / created / updated）——上列字段照模板用 Edit
  补；`--sources` flag 是 source 页专属（raw/ 路径），synthesis 不走它
- 归档页若记录跨页矛盾：加 `contested: true` + `contradictions: [对端页]`，且对端页同步互指
  （单向触发 lint `contradiction-asymmetric`；字段语义 canonical 见
  [章节](page-templates.md#可选可信度与认知质量信号)）
- 正文：把对话里的答案整理成可独立阅读的页面；**synthesis 页对来源可分的断言用标准脚注
  `[^n]` 逐段溯源**（写法见 [章节](page-templates.md#synthesis综合页)），
  让每个论点都能不重读 raw 就回溯到具体 source——这是 synthesis 区别于 source 摘要的关键
- 正文含交互流 / 架构关系时优先配图——判定与选型见 [章节](page-templates.md#图示使用指引)
- 正文引用上游易变事实时同样过感知测试——见
  [章节](ingest-workflow.md#正文引用的稳定性漂移点规避) 漂移点规避
- 脚手架：`llmw wiki write new --type=comparison --slug=... --title=...`（或 `--type=synthesis`）
- 同步 index：`llmw wiki write index add <page>`
- 追加 log：`llmw wiki write log --op=query --title="<title>"`
- 交叉引用同步：相关 entity / concept 页按需追加"参考来源"段（纪律 canonical 见 wiki 根
  AGENTS.md「写入纪律」的「写后必同步」条）；凡 Edit 过既有页正文 →
  `llmw wiki write touch <page>`（更新 updated + 清 reviewed 戳）

### Step 6：若启用 git，建议 commit（同 ingest）；裸目录树 wiki 跳过此步

## Query 的边界

- **不**引用未存在于 wiki 的来源——只引用 wiki 内的页面
- **不**绕过 source 页直接读 raw（冲突时才回 raw 复核，见 Step 2）

> 其余边界以 wiki 根 `AGENTS.md` Query 纪律节为准

## Query 失败的常见原因

- **index.md 没维护**——所有路径都找不到；先修 index
- **source 页过期**——读到的信息已经过时；建议先 lint
- **概念粒度不一致**——同名页在不同页里指不同东西；提示用户合并或重命名
