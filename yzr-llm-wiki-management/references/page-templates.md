# 页面模板

按 `type` 分 5 种。**所有页面**共有 frontmatter 段（见下）+ 类型特定字段 + 自由正文。

> **本文件是 content-owned 产物（wiki 内容页）纪律的 canonical**——frontmatter 字段
> 全集 / 建页阈值 / 认知质量信号 / 矛盾处理 Update Policy 的唯一维护点（0.37.0 起
> 从 AGENTS.md 模板迁入；模板不再承载写页规则）。改规则只改本文件 + bump
> `wiki_spec_version`。

> **本章顺序说明**：下面按**教学序**列出（基础 → 综合：entity → concept → source
> → comparison → synthesis）。spec 强制**字母序**用于目录结构与 `type` 取值表——
> 见 [wiki-spec.md §1 / §9](wiki-spec.md)。

## 目录

- [一、共有 frontmatter 段](#一共有-frontmatter-段)
- [二、各类型模板](#二各类型模板)
  - [1. `entity`（实体页）](#1-entity实体页)
  - [2. `concept`（概念页）](#2-concept概念页)
  - [3. `source`（资料页）](#3-source资料页)
  - [4. `comparison`（对比页）](#4-comparison对比页)
  - [5. `synthesis`（综合页）](#5-synthesis综合页)
  - [6. `index`（index.md）](#6-indexindexmd)
  - [7. `log.md`（log）](#7-logmdlog)
- [三、模板使用规则](#三模板使用规则)

> **frontmatter 写法约束**（与 `llmw wiki ingest-diff` 内的轻量 YAML 解析器对齐）：仅支持单行
> `key: value`、inline 数组 `[a, b, c]`、`- item` 列表项三种形式。**不要**使用多行折叠 `>` /
> `|`、YAML 锚点 `&` / `*`、嵌套 map——脚本会静默解析失败、返回空 dict、后续 ingest 与 lint
> 行为未定义。

## 一、共有 frontmatter 段

> **适用范围**：本节模板适用于 wiki 5 类内容页（entities / concepts / sources /
> comparisons / syntheses）。**MEMORY/*.md 的 frontmatter 规则不同**——仅 `title`
> 必填，其余 5 字段全 optional；详见 [`wiki-spec.md` §5.2](wiki-spec.md#52-memorymd非-memorymd) +
> [`lint-checklist.md` §二.2](lint-checklist.md#2-frontmatter-完整性) 末尾。

```yaml
---
title: <string, 必填>
description: <一句话摘要, 推荐>  # 推荐（OKF v0.1 推荐字段）；index.md 条目摘要从它来，避免漂移
type: <entity|concept|source|comparison|synthesis, 必填>  # 5 类内容页；index/log 是 reserved（见 §6 / §7）
tags: [<string array>, 必填但可空数组>]
created: <YYYY-MM-DD HH:MM, 必填>  # lint 也接受 YYYY-MM-DD
updated: <YYYY-MM-DD HH:MM, 必填>  # lint 也接受 YYYY-MM-DD
# —— 以下为可选「可信度与认知质量信号」（见下方同名段）——
reviewed: <true, 可选>            # 仅在为 true 时写：人工已审核该页
reviewed_at: <YYYY-MM-DD, 可选>   # 审核日期；与 reviewed: true 成对出现
contested: <true, 可选>           # 仅在为 true 时写：本页含未解决的矛盾主张
contradictions: [<wiki 页路径数组>, 可选]  # 与本页主张冲突的页面（双向标注：A 标 B，B 也标 A）
---
```

**字段说明**：

- `title`——人类可读标题，不要带文件扩展名
- `description`——**推荐**（OKF v0.1 推荐字段）。一句话总结本页；`index.md` 条目摘要从它来，
  避免在 index 里手写第二份、与正文漂移（lint 抓不到这种不一致）
- `type`——驱动 lint 校验 + index 分组；合法值仅上述 5 种（`llmw wiki lint` 强制）。`index.md` /
  `log.md` 是 **reserved 文件**（结构见 §6 / §7），自带 frontmatter，其中 `type: index` /
  `type: log` 仅作标记、lint 跳过它们——不算概念页 type
- `tags`——用于跨页搜索 + 未来可能的 dataview 查询。**取值必须严格在
  [`wiki/tags.md`](wiki-spec.md#91-tag-白名单来源) 白名单内**——agent 在 ingest /
  query 遇到新 tag 时**直接追加**到 `wiki/tags.md`（无需询问用户），保持字典随 wiki 生长；
  用户可随时打开 `wiki/tags.md` **直接删除**误判的 bullet，下次 lint 把残留引用以
  `tag-not-in-taxonomy`（info）报回来再裁定。详 lint 语义见
  [`lint-checklist.md`](lint-checklist.md#11-tag-taxonomy-校验)
- `created` / `updated`——**严格** `YYYY-MM-DD HH:MM` 格式（lint 解析用；
  `YYYY-MM-DD` 也接受，按精度宽容解析三种格式：date-only /
  HH:MM / HH:MM:SS）
- 类型特定字段（`sources` / `compared` / `threads`）见各模板
- `reviewed` / `reviewed_at` / `contested` / `contradictions`——**可选**可信度与认知质量信号，见下

### 可选：可信度与认知质量信号

> **为什么需要**：wiki 的复利价值依赖"已沉淀的主张可被信任"。但 LLM 自动写入的页面——
> 尤其是凭单篇弱来源的断言——一旦写进 wiki 不再标注，时间一长会被当成"既成事实"，这是**认知腐烂**，
> 比断链 / 孤儿更隐蔽。本段两类信号把腐烂显性化：
>
> - **`reviewed` / `reviewed_at`** —— 人工**审核背书**："我读过了，愿意为它背书"。
>   query 阶段 agent 据此优先采信；lint 报告 `pending-review` 清单；`index.md` 上以 ✓ / ✗ 标记。
> - **`contested` / `contradictions`** —— **认知冲突未裁定**的告警："这里有两个说法打架，等人复审"。
>   与可信度正交：一个页面可以既 `reviewed: true` 又 `contested: true`（"我审核过，确实有矛盾待裁定"）。

四个字段（**全部可选**；`reviewed` 与 `reviewed_at` 应成对出现，`contested` 与 `contradictions` 同）：

- `reviewed: true`——**仅**在为 `true` 时写。人工**已审核该页**的可信度背书。
  - 缺省 = 未审核（lint 报 `pending-review` info，新常态，不算腐烂）
  - lint 校验：`reviewed` 取值必须严格为 `true`（裸 token，不是 `"true"` 字符串、`yes`、`1`、`false`）
  - 与 `reviewed_at` 必须成对出现，单独写任一字段给 `reviewed-at-missing` / `reviewed-at-orphan` warn
- `reviewed_at: <YYYY-MM-DD>`——审核日期。与 `reviewed: true` 配套。
  - lint 校验：`updated > reviewed_at` 时给 `reviewed-stale` warn（LLM 修改后未清 reviewed，戳过期）
- `contested: true`——**仅**在为 `true` 时写。表示本页存在**尚未裁定**的矛盾主张
  （搭配 `contradictions` 指向对端）。lint 把所有 `contested: true` 的页集中拎出供用户复审，
  避免悬而未决的冲突被后续 ingest 静默继承
- `contradictions: [path-a, path-b]`——与本页主张**冲突**的 wiki 页路径数组（相对路径，
  与交叉引用同写法）。**双向标注**：A 把 B 列进 `contradictions`，B 也应把 A 列进来；
  lint 检查这种对称性（单向 = `contradiction-asymmetric` warn）

#### 生命周期规则（LLM 必读）

**生命周期纪律（LLM 必读）**：`reviewed: true` 是"我对这一刻的内容背书"的快照，
**不是永久标签**——任何对页面正文的 LLM 修改都让戳失效，必须**删除** `reviewed` +
`reviewed_at` 回到默认未审核状态，由人重新审。`llmw wiki lint` 用 `reviewed-stale`
兜底（`reviewed: true` 存在且 `updated > reviewed_at` 时给 warn）。判定表 + lint 语义如下：

| 事件 | 对 `reviewed` / `reviewed_at` 的操作 |
| --- | --- |
| LLM 创建新页 | 不写（默认未审核） |
| 人标记已审核 | 写 `reviewed: true` + `reviewed_at: <今天>` |
| LLM 修改页（含 ingest 重摄取、query 归档、refine、任何 Edit/Write） | **必须删除这两个字段**（回到默认未审核） |
| LLM 仅改 `updated` 字段（无正文变化） | 不动（meta 操作，不算内容变更） |

**两道闸门**：

1. **纪律闸门**——生命周期纪律 canonical = 本节（0.37.0 起迁入；AGENTS.md 模板只留
   "写页规则见 skill 页面模板文档"指针）
2. **lint 兜底**——`reviewed-stale` 触发条件：`reviewed: true` 存在 **且** `updated > reviewed_at`，
   把 LLM 漏清戳的页面拎出来提示人复审

**何时设 `reviewed: true`**：

- 人读完页面所有正文 + 交叉引用 + 关键 raw 资料，确认主张站得住 → 写 `reviewed: true` + `reviewed_at: <今天>`
- 不是看完了就一定审——遇到 `contested: true` 或 `contradictions` 非空时**不**应盲目标 reviewed，
  应先裁定冲突再标
- 已审过的页被 LLM 修改后，回到默认未审核状态，等人再次复审

**矛盾处理 Update Policy**（ingest 时遇到"新资料与已有页冲突"时，**不要静默覆盖**，
按以下顺序处理——0.37.0 起由本文件承载）：

1. **先看日期**——更新的来源一般覆盖旧的；但若旧来源更权威（如官方技术报告 vs 博客），
   保留两者并进入第 2 步
2. **判定是否真矛盾**——版本差异（同一对象 v1 vs v2 的某个属性）、上下文差异
   （不同评测条件）不算矛盾，加注明即可；确属矛盾进入第 3 步
3. **显式记录两种说法**——在页面正文写出 A 说 X（来源 + 日期）、B 说 Y（来源 + 日期），
   不要"和稀泥"挑一个；双方 frontmatter 都设 `contested: true` + `contradictions` 互指
4. **等 lint 复审**——下次 lint 会把 `contested` 页拎出来；与用户一起裁定后，
   移除 `contested`（如该页已审核，按生命周期规则判断是否需重新审）

## 二、各类型模板

> **本节约定**：每类模板只列**路径 + 必填 frontmatter + 极简正文骨架**（节名 + 一句
> "..."占位）。**完整正文示例**（source 摘要实例）见 [`examples.md`](examples.md)
> 样例二——按需 Read，避免本文件膨胀。

### 1. `entity`（实体页）

路径：`wiki/entities/<slug>.md`

```yaml
---
title: <必填>
description: <推荐>
type: entity
tags: [<必填但可空>]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
aliases: [<可选>, <可选>]  # 别名数组，方便搜索（不受 §8 kebab-case 文件名规则约束）
---
```

正文骨架（节名按需保留/拆分）：

```markdown
# <Title>

## 简述

<一段话总结 entity 是谁/什么，附 primary source 链接>

## 关键属性

- <bullet list：本 entity 的客观属性>

## 已知变体

- <变体 1（版本 / 型号 / 形态）>
- <变体 2>

## 参考来源 / Sources

* [<source page>](<relative-path>) — <简短说明>
```

### 2. `concept`（概念页）

路径：`wiki/concepts/<slug>.md`

```yaml
---
title: <必填>
description: <推荐>
type: concept
tags: [<必填但可空>]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
related: [<concepts/x.md>, <concepts/y.md>]  # 相关概念路径数组，wiki 根相对
---
```

正文骨架：

```markdown
# <Title>

## 定义

<一段话给出概念的形式化定义 + primary source>

## 数学形式 / 形式化

<若适用：LaTeX / mermaid / 表格>

## 关键性质

- <bullet：本概念区别于相邻概念的关键属性>

## 变体

- <变体 1>（来源：[<source>](<path>)）
- <变体 2>

## 相关概念

- [<concept 1>](<path>) — <关系说明>
- [<concept 2>](<path>)

## 参考来源 / Sources

* [<source page>](<relative-path>) — <说明>
```

### 3. `source`（资料页）

路径：`wiki/sources/<slug>.md`

```yaml
---
title: <必填>
description: <推荐>
type: source
tags: [<必填但可空>]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
sources:  # 必填——指向 raw/ 现存路径（不得指向 raw/discussions/——草稿非真相源，spec §15）
  - raw/articles/<slug>.md
authors: [<name1>, <name2>]  # 可选
published: YYYY-MM-DD          # 可选
url: <https://...>             # 可选（源材料原始链接）
venue: <会议名 / 期刊>          # 可选
---
```

正文骨架：

```markdown
# <Title>

**作者**：<authors>
**来源**：[<raw path>](../../raw/<...>)（必填项；absent → lint sources-missing）

## 摘要

<一段话——核心主张 + 在本 wiki 主题域里的位置>

## 关键贡献

1. <贡献 1>
2. <贡献 2>
3. <贡献 3>

## 关键数字 / 实验结果

- <bullet：关键数据 / 性能 / 复杂度>

## 与本 wiki 其它资料的关系

- 启发了 [<other source>](<path>)
- 核心概念见 [<concept 1>](../concepts/<slug>.md)

## 引文（可独立成段）

> "<原文 quote>" —— <出处>
```

### 4. `comparison`（对比页）

路径：`wiki/comparisons/<slug>.md`

```yaml
---
title: <必填>
description: <推荐>
type: comparison
tags: [<必填但可空>]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
compared:  # 必填——被对比对象路径数组，wiki 根相对
  - concepts/<a>.md
  - concepts/<b>.md
---
```

正文骨架：

```markdown
# <Title>

## 对比对象

- [<entity/concept 1>](../concepts/<a>.md) — <路线 1 一句话>
- [<entity/concept 2>](../concepts/<b>.md) — <路线 2 一句话>

## 维度对比

| 维度 | <A> | <B> |
| --- | --- | --- |
| <维度 1> | <A 在此维度的属性> | <B 在此维度的属性> |
| <维度 2> | ... | ... |

## 适用场景

- <场景 1> → <选 A / B / 视情况>
- <场景 2>

## 参考来源 / Sources

* [<source page>](<relative-path>)
```

### 5. `synthesis`（综合页）

路径：`wiki/syntheses/<slug>.md`

```yaml
---
title: <必填>
description: <推荐>
type: synthesis
tags: [<必填但可空>]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
threads:  # 必填——线索标题数组（synthesis 区分多线索的"主线"）
  - <thread-1-title>
  - <thread-2-title>
sources:  # 必填——wiki 内其它页路径（不是 raw/）；详见 wiki-spec §9 类型特化
  - <concepts/x.md>
  - <sources/y.md>
---
```

正文骨架：

```markdown
# <Title>

## 主线

<一段话——综合页要回答的核心问题 + 多线索概览>

## 线索一：<thread 1 title>

- <要点 1>（来源：[<source>](<path>)）
- <要点 2>

## 线索二：<thread 2 title>

- <要点 1>
- <要点 2>

## 交叉与综合

- <综合观察：跨线索的连接 / 共性>

## 观察 / 待研究

1. <观察 1>
2. <待研究问题>

## 参考来源 / Sources

* 列在 frontmatter `sources` 字段
```

> **逐段溯源（synthesis 专属）**：synthesis 页通常综合 ≥ 3 个 source，主张散落在不同段落、
> 各自从不同来源得出。仅靠 frontmatter `sources` 只能定位"本页引用了哪些来源"，**无法**
> 追溯"某句具体主张来自哪篇"。因此 synthesis 正文对**来源可分的断言**用标准 Markdown 脚注
> `[^n]` 标注，文末给出 `[^n]: ...` 指向 source 页——让每个可被引用的论点都能不重读 raw 就回溯。
> 用标准脚注 `[^n]`（**不要**用 pandoc 的行内 `^[...]`，与本 skill "通用 Markdown" 立场一致，
> 且不依赖 Obsidian / 特定渲染器）。单段纯推论 / 综合判断无需脚注；只对**可追溯到具体来源**
> 的断言标。comparison 页若同样综合多源、断言来源可分，也照此办理。

### 6. `index`（index.md）

路径：`wiki/index.md`（**唯一一份**，不允许新建）

```yaml
---
title: "<Topic> Index"
type: index
okf_version: "0.1"
tags: [index]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
---
```

正文骨架：

```markdown
# <Topic> Wiki

> 本 wiki 由 LLM 维护，用户只读 + 提供 raw 资料 + 提问题。边界纪律见
> [`../AGENTS.md`](../AGENTS.md)；条目纪律与扩容护栏见本文件头部说明块（canonical）。

## Entities

- [<title>](entities/<slug>.md) — <一句话摘要，取自 description 字段>

## Concepts

- [<title>](concepts/<slug>.md) — <摘要>

## Sources

- [<title>](sources/<slug>.md) — <摘要>

## Comparisons

- [<title>](comparisons/<slug>.md) — <摘要>

## Syntheses

- [<title>](syntheses/<slug>.md) — <摘要>
```

**lint 检查**：

- 每个非 log / index 的 wiki 页**必须**在对应类别里出现
- 类别标题固定（Entities / Concepts / Sources / Comparisons / Syntheses）
- 条目格式：`* [<title>](<relative-path>) — <一句话摘要>`；**摘要应取自被链接页 frontmatter 的
  `description`**，不要在 index 里手写第二份（避免漂移）

### 7. `log.md`（log）

路径：`wiki/log.md`（**唯一一份**）

```yaml
---
title: "<Topic> Log"
type: log
tags: [log]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
---
```

正文（**每行匹配** `^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] (ingest|query|lint|setup) \| .+$`，lint 校验；
ingest/query/lint/setup 行推荐带 HH:MM；date-only 也合法）：

```markdown
## [2026-06-24 14:30] setup | Initial scaffold by llmw CLI
## [2026-06-24 14:35] ingest | <source page title>
## [2026-06-24 15:10] query | <answer summary>
## [2026-06-24 16:00] lint | First health check
```

**lint 检查**：

- 每行匹配正则
- 滚动窗口：条目数 > `LOG_RETENTION_LIMIT`（50）时报 `log-truncation-recommended`；
  正路 `llmw wiki write log` 写入时自动截断（frontmatter 不动）

## 三、模板使用规则

1. **首次创建**——用对应模板填充 frontmatter
2. **修改时**——保留 frontmatter 全部字段；`updated` 改当天日期
3. **重写时**——若 `type` / `sources` 等关键字段需要变，**先和用户确认**
4. **归档 query 答案**——根据答案性质选 `comparison`（对比）或 `synthesis`（综合）
5. **完整正文示例**——本文件只留 frontmatter SSOT + 极简骨架（节名 + `...` 占位）；
   真实 wiki 里 5 类模板的填充实例见 [`examples.md`](examples.md) 样例二 / 样例三
   （source 摘要 + 综合 markdown）——按需 Read，无需把详细实例塞进本文件

### 建页 / 追加 / 归档阈值（Page Thresholds）

不是每个 entity / concept 都值得独立成页——没阈值 wiki 会被名词堆爆，几个月后 index 翻不到底。
（0.37.0 起由本文件承载；**宁可错过一个 entity 也不要堆十个空页**——"克制"是 wiki 长期
可用性的具体化，堆一千个空 entity 后 lint 报告会被噪声淹没。）

| 动作 | 触发条件 |
| --- | --- |
| **新建 entity / concept 页** | 该 entity / concept 在 ≥ 2 个 source 页中被提到 **或** 是某 source 页的中心主题 |
| **追加到已有页** | source 页提到一个已被覆盖的 entity / concept——追加"参考来源"段即可（不重写） |
| **不创建页** | 路过提及（脚注 / 一次出现的名字）、领域外的细节、与本 wiki 主题无关 |
| **拆分页** | 单页正文超过阈值（SSOT = `llmw wiki lint` 的 `PAGE_SIZE_THRESHOLD` 常量）——拆成子主题 + cross-link |
| **归档页** | 内容被完全取代 / 主题域变化——加 `archived: true`、从 `index.md` 移除（log 走 `ingest` 或 `lint` op，记一条说明性条目） |
