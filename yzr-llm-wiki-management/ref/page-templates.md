# 页面模板

按 `type` 分 5 种。**5 类内容页**共有 frontmatter 段 + 类型特定字段 + 自由正文

**本文件 = content-owned 页写作纪律的 canonical**（frontmatter 字段语义 / 建页阈值 /
认知质量信号 / 矛盾处理 / 图示指引，AGENTS.md 模板不承载写页规则）；lint 校验规则以
`llmw wiki lint --explain=all` 为准，不在此镜像

**frontmatter 写法约束**（对齐 `llmw wiki ingest-diff` 的轻量 YAML 解析器）：仅支持单行
`key: value`、inline 数组 `[a, b, c]`、`- item` 列表项三种形式。**不要**用多行折叠 `>` /
`|`、YAML 锚点 `&` / `*`、嵌套 map——解析器会静默失败返回空 dict

## 共有 frontmatter 段

适用 5 类内容页（entities / concepts / sources / comparisons / syntheses）；**MEMORY/*.md
规则不同**——canonical 见 `<wiki-root>/MEMORY/MEMORY.md` fixture 头部说明块

| 字段 | 必填性 | 语义 |
| --- | --- | --- |
| `title` | 必填 | 人类可读标题，不带文件扩展名 |
| `description` | 推荐 | 一句话摘要；`index.md` 条目摘要的唯一来源（不在 index 手写第二份，防漂移） |
| `type` | 必填 | entity / concept / source / comparison / synthesis——驱动子目录 + index 分组 + lint |
| `tags` | 必填（可空数组） | 取值必须严格在 `wiki/tags.md` 白名单内（canonical 见其头部说明块） |
| `created` / `updated` | 必填 | 写入用 `YYYY-MM-DD HH:MM`；lint 宽容解析 date-only / HH:MM / HH:MM:SS |
| `reviewed` / `reviewed_at` / `contested` / `contradictions` | 可选 | 认知质量信号，见下节 |
| 类型特定（`sources` / `compared` / `threads` / `aliases` 等） | 按类型 | 见 [章节](#各类型模板) |

5 必填 = OKF §9 conformance 与 lint 校验的最小交集。`index.md` / `log.md` 是
**reserved 文件**（自带 frontmatter，`type: index` / `type: log` 仅作标记），lint 跳过——
不算概念页 type

### 可选：可信度与认知质量信号

**为什么需要**：LLM 写入的页若不标注，时间一长会被当成"既成事实"——**认知腐烂**，
比断链 / 孤儿更隐蔽。`reviewed` 系 = 人工审核背书（query 优先采信、index ✓/✗）；
`contested` 系 = 矛盾未裁定告警（与可信度正交：可既 reviewed 又 contested）

- `reviewed: true`——**仅**在为 `true` 时写。缺省 = 未审核；与
  `reviewed_at: <YYYY-MM-DD>` 成对出现（单独写任一字段 lint 报 warn）
- `contested: true`——**仅**在为 `true` 时写。表示存在**尚未裁定**的矛盾主张（搭配
  `contradictions` 指向对端），供 lint 集中拎出复审
- `contradictions: [<wiki 页路径>]`——与本页主张冲突的页数组。**双向标注**（A 标 B，
  B 也标 A；lint 检查对称性）

#### 生命周期规则

`reviewed: true` 是"我对这一刻的内容背书"的快照，**不是永久标签**——任何对页面正文的
LLM 修改都让戳失效，必须**删除** `reviewed` + `reviewed_at` 回到默认未审核态，由人重新审
（漏清戳由 lint `reviewed-stale` 兜底）。判定表：

| 事件 | 对 `reviewed` / `reviewed_at` 的操作 |
| --- | --- |
| LLM 创建新页 | 不写（默认未审核） |
| 人标记已审核 | 写 `reviewed: true` + `reviewed_at: <今天>` |
| LLM 修改页（含 ingest 重摄取、query 归档、任何 Edit/Write） | **必须删除这两个字段**（回到默认未审核） |
| LLM 仅改 `updated` 字段（无正文变化） | 不动（meta 操作，不算内容变更） |

**何时设 `reviewed: true`**：人读完正文 + 交叉引用 + 关键 raw 资料，确认主张站得住；
遇 `contested: true` 或 `contradictions` 非空**不**应盲目标，先裁定冲突再标。
已审过的页被 LLM 修改后回默认未审核态，等人再次复审

#### 矛盾处理 Update Policy

ingest 时遇到"新资料与已有页冲突"，**不要静默覆盖**：

1. **先看日期**——更新的来源一般覆盖旧的；但若旧来源更权威（如官方技术报告 vs 博客），
   保留两者并进入第 2 步
2. **判定是否真矛盾**——版本差异（同一对象 v1 vs v2 的某属性）、上下文差异（不同评测
   条件）不算矛盾，加注明即可；确属矛盾进入第 3 步
3. **显式记录两种说法**——页面正文写出 A 说 X（来源 + 日期）、B 说 Y（来源 + 日期），
   不要"和稀泥"挑一个；双方 frontmatter 都设 `contested: true` + `contradictions` 互指
4. **等 lint 复审**——下次 lint 会把 `contested` 页拎出来；与用户一起裁定后移除
   `contested`（如该页已审核，按生命周期规则判断是否需重新审）

## 各类型模板

每类只列**路径 + 类型特定字段 + 正文骨架**（节名即契约，写入时按它落；节名按需保留 /
拆分；5 必填 frontmatter 由 `llmw wiki write new` 生成）。实跑 trace 见
`examples.md`——按需 Read

### entity（实体页）

路径：`wiki/entities/<slug>.md`；类型字段：`aliases: [<别名>]`（可选，自由文本）

```markdown
# <Title>

## 简述

<一段话：本 entity 是谁/什么，附 primary source 链接>

## 关键属性

- <客观属性 bullet>

## 已知变体

- <变体（版本 / 型号 / 形态）>

## 参考来源 / Sources

* [<source page>](<relative-path>) — <说明>
```

### concept（概念页）

路径：`wiki/concepts/<slug>.md`；类型字段：`related: [<concepts/x.md>, ...]`（相关概念，wiki 根相对）

```markdown
# <Title>

## 定义

<形式化定义 + primary source>

## 数学形式 / 形式化

<若适用：LaTeX / mermaid / 表格>

## 关键性质

- <区别于相邻概念的关键属性>

## 变体

- <变体>（来源：[<source>](<path>)）

## 相关概念

- [<concept>](<path>) — <关系说明>

## 参考来源 / Sources

* [<source page>](<relative-path>) — <说明>
```

### source（资料页）

路径：`wiki/sources/<slug>.md`；类型字段：`sources`（必填——raw/ 现存路径，
**不得指向 `raw/discussions/`**，草稿非真相源，见 `ingest-workflow.md`）、
`authors` / `published` / `url` / `venue`（可选）

```markdown
# <Title>

**作者**：<authors>
**来源**：[<raw path>](../../raw/<...>)

## 摘要

<一段话：核心主张 + 在本 wiki 主题域里的位置>

## 关键贡献

1. <贡献>

## 关键数字 / 实验结果

- <关键数据 / 性能 / 复杂度>

## 与本 wiki 其它资料的关系

- 启发了 [<other source>](<path>)
- 核心概念见 [<concept>](../concepts/<slug>.md)

## 引文（可独立成段）

> "<原文 quote>" —— <出处>
```

### comparison（对比页）

路径：`wiki/comparisons/<slug>.md`；类型字段：`compared: [<concepts/a.md>, ...]`（必填，wiki 根相对）

```markdown
# <Title>

## 对比对象

- [<A>](../concepts/<a>.md) — <路线 1 一句话>
- [<B>](../concepts/<b>.md) — <路线 2 一句话>

## 维度对比

| 维度 | <A> | <B> |
| --- | --- | --- |
| <维度> | <A 属性> | <B 属性> |

## 适用场景

- <场景> → <选 A / B / 视情况>

## 参考来源 / Sources

* [<source page>](<relative-path>)
```

### synthesis（综合页）

路径：`wiki/syntheses/<slug>.md`；类型字段：`threads: [<线索标题>]`（必填）、
`sources: [<wiki 内页路径>]`（必填，**不是 raw/**）

```markdown
# <Title>

## 主线

<要回答的核心问题 + 多线索概览>

## 线索一：<thread 1>

- <要点>（来源：[<source>](<path>)）

## 交叉与综合

- <跨线索的连接 / 共性>

## 观察 / 待研究

1. <观察 / 待研究问题>

## 参考来源 / Sources

* 列在 frontmatter `sources` 字段
```

**逐段溯源（synthesis / 多源 comparison 专属）**：frontmatter `sources` 只能定位"引了
哪些来源"，无法追溯"某句主张来自哪篇"。对**来源可分的断言**用标准 Markdown 脚注 `[^n]`
（文末 `[^n]: ...` 指向 source 页；**不要**用 pandoc 行内 `^[...]`）；纯推论无需脚注

### index（index.md）

路径：`wiki/index.md`（**唯一一份**，`type: index` 是 reserved）。字节金标准在 fixture
`index.md.txt`；条目纪律 canonical 在 fixture 头部说明块；正路走
`llmw wiki write index add|remove`（从页 frontmatter 派生 title/description，类别段内字母序）。
lint 口径：`llmw wiki lint --explain=index-missing` / `--explain=orphan-page`

### log.md（log）

路径：`wiki/log.md`（**唯一一份**，`type: log` 是 reserved）。每行格式 / op 取值 / 滚动窗口
截断：canonical 在 fixture `log.md.txt` 头部；正路走 `llmw wiki write log`（格式 + 截断自动
保证）；带外手改按 fixture 格式 + 手工截断。lint 口径：
`llmw wiki lint --explain=log-format` / `--explain=log-truncation-recommended`

## 模板使用规则

1. **新建**——走 `llmw wiki write new`（frontmatter 5 必填自动落）；正文按上节骨架写
2. **修改**——保留 frontmatter 全部字段；`updated` 改当天日期
3. **重写**——若 `type` / `sources` 等关键字段需要变，**先和用户确认**
4. **归档 query 答案**——按答案性质选 `comparison`（对比）或 `synthesis`（综合）

### 建页 / 追加 / 归档阈值（Page Thresholds）

不是每个 entity / concept 都值得独立成页——没阈值 wiki 会被名词堆爆。
**宁可错过一个 entity 也不要堆十个空页**——堆一千个空 entity，lint 报告会被噪声淹没

| 动作 | 触发条件 |
| --- | --- |
| **新建 entity / concept 页** | 该 entity / concept 在 ≥ 2 个 source 页中被提到 **或** 是某 source 页的中心主题 |
| **追加到已有页** | source 页提到一个已被覆盖的 entity / concept——追加"参考来源"段即可（不重写） |
| **不创建页** | 路过提及（脚注 / 一次出现的名字）、领域外的细节、与本 wiki 主题无关 |
| **拆分页** | 单页正文超过阈值——阈值与拆分建议见 lint `oversized-page` finding（触发时输出自带）；拆成子主题 + cross-link |
| **归档页** | 内容被完全取代 / 主题域变化——加 `archived: true`、从 `index.md` 移除 |

## 图示使用指引

advisory（建议式）——图用于压缩过程性 / 结构性内容，不强制；密度优先，图是正文的
压缩，不是装饰

- **优先配图**——交互流程 / pipeline / 状态机 / 组件-模块关系 / 层级结构；散文写这类
  内容超过 2-3 句仍绕不清时，换一张图
- **不配图**——静态定义、简单枚举、单点结论；一页一般 ≤ 2 图（超了先自问是否该拆页，
  阈值见 [章节](#建页--追加--归档阈值page-thresholds)）
- **mermaid 为默认**（`flowchart` / `sequenceDiagram`）——中文标签无碍，GitHub 网页 /
  md-to-html 均可渲染；**源码本身保持可读**：短标签、线性流、节点 ≤ ~12，超了就拆图或退回文字
- **ASCII 图仅限**目录树 / 纯英文短标签结构（围栏用 `text`）——**禁止中文标签进
  ASCII 框**：LLM 数中英混排显示宽度几乎必错，对齐必崩
- **表格仍是对比类内容首选**；LaTeX 公式照旧；**不用二进制图片**——检索 / diff /
  可移植性三损（wiki 的文本性是一等约束）
- **维护**——图是主张的一部分，改主张必同步改图（stale / `reviewed` 判定对图与文字一视
  同仁）；**关键结论在图外保留文字**——agent 靠 grep 检索，图里的信息等于不存在
