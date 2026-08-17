# Query 详细流程

Query 是 wiki 的"消费侧"——把多份资料综合成答案，**好答案归档回 wiki**让复利继续。

## 一、为什么 query 比"读 source"多一道

直接读 source 是"档案式"——只看到一份资料的视角。Query 跨页综合，暴露：

- **联系**——A 和 B 都涉及 self-attention，但角度不同
- **矛盾**——A 说 context window 200K，B 说 128K
- **趋势**——多份资料汇聚出的"领域方向"

**这是 wiki 真正的价值**——比 RAG 多的是"复利结构"。

## 二、入口与触发

- 用户问"wiki 里有 X 吗" / "wiki 里关于 Y 有什么"
- 用户问"对比 A 和 B" / "总结一下 X" / "为什么 A 比 B 好"
- 隐式触发：ingest 完成后 agent 主动建议"要不要查一下新内容和已有内容的联系？"

## 三、流程详解

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

### Step 2.5：标注候选页的可信度

读完所有候选页后，agent 按 frontmatter `reviewed` 字段分三栏：

```text
已审核（reviewed: true）—— 优先采信
  - concepts/transformer.md
  - sources/attention-is-all-you-need.md
未审核（reviewed 缺省 / 不为 true）—— 辅助采信，需标注
  - concepts/flash-attention-2.md
跨页矛盾（contested: true）—— 候选页里有未裁定冲突，参考其 contradictions 字段
```

**为什么需要这一步**：wiki 的复利价值依赖"已沉淀主张可被信任"——人工审过的页面
（`reviewed: true`）应作为优先引用源，未审页面作为补充并显式标注。`lint_wiki.py` §二.13
会把未审页面标 `pending-review`（info），但 query 时是否优先采信是 agent 决策，不在 lint 范围内。

### Step 2.6：综合答案时优先采信 reviewed

| 场景 | 行为 |
| --- | --- |
| 同一问题只有 reviewed 页能答 | 正常引用，不额外标注 |
| 同一问题只有 un-reviewed 页能答 | 引用 + 显式标注「（本页未经人工复审）」 |
| 同一问题两种页都有，结论一致 | 引用 reviewed 页为主，un-reviewed 作为补充 |
| 同一问题两种页都有，结论冲突 | 标注「存在两种说法：X（来源 A，已审核）/ Y（来源 B，未审核），以 X 为准」+ 建议人复审 B |

**与现有 `contested` / `contradictions` 字段的关系**：`contested: true` 是 wiki 内
**矛盾未裁定**的标记，query 时同样优先采信 reviewed 的那一侧（与本设计协同）。
`contradictions` 是冲突对端链接——本设计不重复约定，沿用。

### Step 3：综合答案

答案结构（按需组合）：

1. **直接回答**——用引用形式，每条事实带 `(来源: <page path>)`；un-reviewed 页面额外标「未经人工复审」
2. **对比表**（如果是 query "A vs B" 类）——Markdown 表格，行 = 维度，列 = 对象，
   单元格用引用形式
3. **时间线 / 演进**（如果是 query "X 的演进" 类）——按 source 页 published 排序
4. **矛盾标注**（如果发现冲突）——不要"和稀泥"：
   > A 说 X（来源: ...），B 说 Y（来源: ...）。这可能是定义差异 / 上下文差异 /
   > 数据更新，建议进一步调研。

### Step 4：询问归档

**好答案必须问"是否归档"**——以下任一满足都问：

- 答案本质是"对比" / "综合" / "发现新联系"
- 答案长度 > 200 字且可能复用
- 答案涉及 ≥ 3 个 source 页

**问题模板**：

> 这段答案本质是 `<comparison / synthesis / finding>`，是否归档为
> `wiki/comparisons/<slug>.md`（或 `wiki/syntheses/<slug>.md`）？建议标题：
> `<title>`。

用户拒绝 → 尊重，不强求；用户同意 → 走 Step 5。

### Step 5：归档 query 答案

使用 [`page-templates.md`](page-templates.md) §二 的 comparison / synthesis 模板。

- `comparison` 页：focus 在 "A vs B"，frontmatter `compared: [<path-a>, <path-b>]`
- `synthesis` 页：focus 在 "跨多个 source 的综合洞察"，frontmatter `threads: [<主题>...]`
- 正文：把对话里的答案整理成可独立阅读的页面；**synthesis 页对来源可分的断言用标准脚注
  `[^n]` 逐段溯源**（写法见 [page-templates.md §二.5](page-templates.md#5-synthesis综合页)），
  让每个论点都能不重读 raw 就回溯到具体 source——这是 synthesis 区别于 source 摘要的关键
- 正文引用上游易变事实时同样过感知测试——见
  [ingest-workflow.md §七](ingest-workflow.md#七正文引用的稳定性漂移点规避) 漂移点规避
- 脚手架：`wiki_write.py new --type comparison|synthesis --slug ... --title ...`
- 同步 index：`wiki_write.py index add <page>`
- 追加 log：`wiki_write.py log --op query --title "<title>"`

### Step 6：若启用 git，建议 commit（同 ingest）；裸目录树 wiki 跳过此步

## 四、Query 答案格式参考（指向 examples.md 样例三）

> 三种典型 answer 形式（直接回答 / 对比 / synthesis）已在
> [`examples.md`](examples.md) 样例三「query 一个跨实体问题」用综合 markdown 展示。
> 本节不重抄。

## 五、Query 的边界

- **不**全量 grep wiki——先看 index，启发式读
- **不**绕过 frontmatter 直接读 raw——raw 已在 source 页消化过
- **不**在不询问用户的情况下归档——必须先展示 + 询问
- **不**"和稀泥"式综合——矛盾要显式标注
- **不**引用未存在于 wiki 的来源——只引用 wiki 内的页面

## 六、Query 失败的常见原因

- **index.md 没维护**——所有路径都找不到；先修 index
- **source 页过期**——读到的信息已经过时；建议先 lint
- **概念粒度不一致**——同名页在不同页里指不同东西；提示用户合并或重命名
