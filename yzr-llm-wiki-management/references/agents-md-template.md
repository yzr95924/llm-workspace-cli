# {{TOPIC_NAME}} Wiki — LLM 维护守则

> 这是本 wiki 的**纪律配置**——给维护本 wiki 的 LLM 看的"工作守则"。你（即 LLM）
> 必须在每次操作前先读这份文件；任何对 wiki 的写入都必须符合这里规定的边界。
>
> **本文件（`AGENTS.md`）是本 wiki 纪律的单一真源（SSOT）**——工具无关。由 workspace CLI 在初始化时按
> 本 skill 的官方模板拷贝生成（模板与配套工具随 skill 分发，不在本 wiki 内）；后续可由用户编辑，**但**
> 任何与本 skill 的核心原则冲突的修改都视为"非标准配置"，skill 行为不再保证一致。
> **本 wiki 特有的纪律 / 偏好请沉淀到 `MEMORY/`**（由下方 `@import` 加载，会话常驻），不要写进本文件——
> 模板升级时本文件按 skill 最新模板**全量重渲染**，本地修改一律不保留。
>
> **关键**：本文件里凡 `@path/to/file` 形式的引用（如 `@MEMORY/MEMORY.md`、`@scripts/SCRIPTS.md`），
> 都用 Read 工具**必须**读取（不是"按需"）——它们与你**当前任务**直接相关。不自动展开 `@import` 的 agent 尤须手动执行，
> 否则漏上下文。

@MEMORY/MEMORY.md

@scripts/SCRIPTS.md

## 一、本 wiki 的边界

### `raw/` —— 真相之源（**LLM 只读，用户可改**）

- 路径：`<wiki-root>/raw/{articles,assets,...}/`（子目录可自由扩展，见下文 `external/`）
- 性质：用户策划的原始资料（论文、剪藏、PDF、图片、播客转写、手写笔记等）
- 纪律：
  - **LLM 不写 / 删除 / 移动 raw/ 下文件**——只读；**两处写权限例外**：`raw/external/`
    （symlink + anchor，见下文）+ `raw/discussions/`（协作草稿，见下文）。**这两处例外
    不得外推到 raw/ 其他子树**（papers / articles / clippings 等仍只读）
  - **用户可随时新增 / 更新 raw/**（重新剪藏、重存 PDF 都算）；这是用户的权限，
    不是违反纪律
  - raw 文件一旦被更新（同路径新内容），**由 ingest 重新消化**：更新对应 source
    页的正文 + `updated` 字段，并在 `log.md` 追加一条 ingest。`ingest_diff.py
    --check-stale` 会按 mtime vs source 页 `updated` 标记这类待重新摄取的文件
  - raw 文件路径是 wiki 内 source 页的 `sources` 字段的"永久引用"——改名会断链
  - raw/ 的内容是真相之源；wiki 摘要如与 raw 矛盾，**以 raw 为准**
  - raw/ 进 git（本 wiki 的 `.gitignore` 不排除 `raw/`）；空目录在 init 时由 CLI 放 `.gitkeep` 占位（
    `raw/articles/` + `raw/assets/`），后续真实文件由用户 `git add`（与 wiki/ 行为一致）
- **所有 git 操作由用户触发**（红线）——LLM agent **不**主动 `git init` /
  `git add` / `git commit` / `git config` / `git symbolic-ref`；用户看到 wiki 落盘后自行决定是否 init git

#### `raw/external/` —— 外部代码仓接入（symlink）

- 路径：`<wiki-root>/raw/external/`
- 用途：把本地已有的外部代码仓（Linux kernel、Ray 源码、TensorFlow、NumPy 等）
  作语料纳入 wiki；**不**内嵌拷贝（占空间），走 symlink + 锚定元数据
- **扁平布局**——symlink + anchor 直接在 `raw/external/` 顶层，不要开
  `<source-name>/` 子目录；anchor 单文件记录所有外部仓：

  ```text
  raw/external/
  ├── .symlink-anchor.toml         # TOML: schema_version=1 + [[entry]] 数组
  │                                 # 每 entry: symlink / target / captured_at /
  │                                 # kind='external-repo' 必填 + git 身份字段（可选）
  ├── linux-kernel                  # symlink → ~/src/linux-kernel
  └── ray                          # symlink → ~/src/ray
  ```

- **纪律（用户 + LLM 共有）**：
  - **每 entry 最小必填 4 字段**：`symlink`（kebab-case，对应 `raw/external/`
    同名 symlink）+ `target`（**推荐 `~/src/<name>` home-relative 形式**；
    也接受绝对路径，lint 端 `Path(target).expanduser()` 统一展开判定）+
    `captured_at`（接入当天）+ `kind: "external-repo"`
  - **git 身份字段（可选）**：target 在 git 仓内时推荐记 `remote_url` + `branch`
    ——跨机器重建软链接时用；不记 commit
  - **扁平布局**：所有外部仓的 symlink 直接在 `external/` 顶层，不开 `<source-name>/`
    子目录；后者会被 lint 报 `external-source-name-invalid`（error，需用户确认后改为扁平布局）
  - 没有 anchor 文件 = lint 报 `external-anchor-missing`（error）
  - anchor 解析失败 / 0 个有效 entry = lint 报 `external-anchor-corrupt`（error）
  - symlink 存在但 anchor 无 entry = lint 报 `external-anchor-orphan`（warn）
  - anchor 有 entry 但 symlink 不存在 = lint 报 `external-symlink-missing`（error）
  - target 路径被改 / 删除后，anchor 仍记旧值——lint 立刻报 `external-target-dead`
  - LLM agent **可写** symlink + anchor（首次接入 + 漂移刷新）——这是 `raw/`
    总纪律的**写权限例外之一**；首次接入走标准 ingest 流程（建 symlink + anchor →
    建 source 页 → 追加 log 条目 → 同步 index）
  - **target 仓内文件按角色分**：**wiki 维护操作**（ingest / query / lint /
    migrate）中 target 只读（librarian 角色，不在仓内跑 `git pull` 之类）；**用户明确要求
    的开发协作**（修 bug / 重构 / 仓内 git 操作）**不**属 wiki 操作、**不**受 raw/ 只读约束
    ——target 在 wiki 仓外、有其自身 git、由用户全权处置。代码改动后的 wiki 同步走**既有通道**
    （用户确认 → 受影响 source 页重 ingest）。
    **禁止**以"开发协作"为借口在 wiki 维护操作中顺手改 target
  - LLM **不**编辑 `raw/external/` 之外的 `raw/` 子树（articles / papers / assets /
    clippings 等仍"LLM 只读"；`discussions/` 是另一处写权限例外——见下节）
- `.gitignore` 配置：已排好 `raw/external/*` 排除但保留 `.symlink-anchor.toml`——
  跨机器 clone 时通过 anchor 立即知道"这本来指着哪"；anchor 的
  `remote_url` + `branch` 让新主机 LLM 可重建（重建 = 按 anchor 重建
  symlink → 重 ingest 受影响 source 页）

#### `raw/discussions/` —— 协作草稿层（用户 + LLM 双方可写）

- 路径：`<wiki-root>/raw/discussions/`（协作草稿层；存在时适用本节纪律）
- 用途：用户 + LLM 协作的临时草稿——讨论稿、设计草稿、待整理笔记。**不是**"用户掌控的
  真相源"，不参与复利结构
- 纪律：
  - **用户 + LLM 双方可写**——创建 / 编辑 / 删除都行；这是 `raw/` 总纪律的**第二处写权限
    例外**（第一处是 `raw/external/` 的 symlink + anchor）
  - **不**要求 frontmatter（草稿不是内容页）
  - **不**进 `wiki/index.md`；写 discussions/ **不**追加 `log.md` 条目（非 wiki 操作，
    显式豁免"每次写入必更 log"）
  - **`ingest_diff.py` 跳过** discussions/ 子树——草稿不会被当 untracked 素材列出
    （避免 LLM 把自己写的草稿当 raw 真相 ingest 回 wiki = provenance 后门）
  - **`raw-modified` lint 排除** discussions/——草稿的未提交 git 改动**不**触发"raw 被违规改"
  - **`sources:` 不得指向** `raw/discussions/`——`type: source` 页引用草稿会被 lint 报
    `source-in-discussions`（error）；要引用先走归档路径转正式
  - git 默认跟踪（与 raw/ 其余子树一致）
- **归档路径**（草稿 → wiki 真相，两条都需用户确认）：
  - **消化式**：LLM 把结论写进 `wiki/` 对应页（走标准 ingest 纪律：log / index / 清
    `reviewed` 戳），原稿留删自便，不进 `sources:`
  - **转正式**：用户确认后 LLM `mv raw/discussions/<x>.md raw/articles/<x>.md`（或合适
    子树），此后回归只读真相源、走标准 ingest；这是 raw/ 只读的**第二处 mv 例外**
    （迁入正式子树后 LLM 不可再改）
- **滑坡防线**：discussions/ 的可写性**不得**外推到 raw/ 其他子树（papers /
  articles / clippings 等仍只读）；上节 target 开发协作切分**不得**外推为"raw/ 也能改"；
  不得用 discussions/ 规避 ingest 纪律（绕归档路径漏 log / index / reviewed 戳）

### `wiki/` —— LLM 拥有的复利资产

- 路径：`<wiki-root>/wiki/{entities,concepts,sources,comparisons,syntheses}/`
- 性质：LLM 生成的相互链接的 Markdown 文件
- 纪律：
  - 用户**不写** wiki 页面（编辑 AGENTS.md 除外）
  - 任何 wiki 页面**必须**含 YAML frontmatter（见下）
  - 任何 wiki 页面**必须**在 `wiki/index.md` 中有对应条目
  - 任何 wiki 页面**必须**有 ≥ 1 条 inbound 链接（index 或其它页）

### `log.md` —— 近期活动速览（滚动窗口）

- 路径：`<wiki-root>/wiki/log.md`
- 纪律：
  - 每次 ingest / query / lint 后**必须**追加一条——正路走 `wiki_write.py log`
    （格式 + 滚动窗口截断自动保证）；带外手改才需要手工遵守格式与截断
  - 格式严格：`## [YYYY-MM-DD HH:MM] <op> | <title>`（op ∈ {`ingest`, `query`, `lint`, `setup`}；
    lint 也接受 `YYYY-MM-DD`）；`setup` 首条由 workspace CLI 在初始化时写入；格式不符会被 lint 报告
  - 标题简洁、不超过一行；URL / 详细摘要写在对应页面里
  - 滚动窗口——条目数 > 50（`LOG_RETENTION_LIMIT`）时删最旧的保最近 50 条（frontmatter
    不动）；完整操作历史靠 git（`git log -p -- wiki/log.md`）

### `index.md` —— wiki 单一入口

- 路径：`<wiki-root>/wiki/index.md`
- 纪律：
  - 按类别分组列出所有非 log 页面（entities / concepts / sources / comparisons / syntheses）
  - 每条带链接 + 一句话摘要
  - 每次 wiki 内容变更后**必须**同步（宁可多改）

### `MEMORY/` —— LLM agent 的持久化记忆

- 路径：`<wiki-root>/MEMORY/`
- 性质：LLM agent 在 ingest / query / lint 过程中沉淀的**经验、踩坑、用户偏好**——
  不是 wiki 内容、不是操作时间线，而是 agent 私有记忆（内容页、操作时间线、agent
  记忆三者的分层中的第 3 层）

- **条目形式按事实颗粒度选**：
  - **完整条目**——需要解释"为什么这么做"或"将来怎么用"（含上下文 / 解决步骤 / 未来如何避免）→
    建 `MEMORY/<slug>.md`（frontmatter **仅 `title` 必填** + 其余字段 optional + 正文） +
    索引行 `- <slug> — 一句话 → [正文](<slug>.md)`
  - **短条目**——纯 reminder / 单一偏好 / 无需 why + how → 索引行直接 `- 一句话事实`，
    不单独建 `.md` 文件
  - 两种格式可在同一 `MEMORY/MEMORY.md` 共存；lint `memory-not-indexed` 只兜底"有 .md 但未索引"
- 纪律：
  - 用户**不**直接编辑 MEMORY/（这是 agent 私有记录）
  - 任何 `MEMORY/*.md`（**仅完整条目**）的 frontmatter **仅 `title` 必填**
    ——`type` / `created` / `updated` / `tags` / `description` 全 optional；与 wiki 内容页
    5 必填规则解耦（MEMORY 是 agent 私有记忆，不走 wiki 用户面 5 必填）
  - **`MEMORY/MEMORY.md` 是索引、无 frontmatter**——由本文件 `@MEMORY/MEMORY.md` `@import`
    加载（详见顶部「关键」段）。写每条时**只改 `MEMORY/MEMORY.md`**
    这一份，`@import` 引用自动同步指向全文。条目正文按需 `Read MEMORY/<slug>.md`
  - 索引走 `@import` 不占 L1 词数——MEMORY 沉淀只改 `MEMORY.md`、AGENTS.md 同步单行引用，
    **无**双写漂移（无需条数护栏）
  - **不**强制在 `wiki/index.md` 列出（不在 wiki 单一入口约束范围内）
  - **不**要求 inbound 链接

### `scripts/` —— 本 wiki 仓的自维护脚本目录

- 路径：`<wiki-root>/scripts/`
- 性质：**用户 + LLM agent 共有**的项目级脚本目录——放置项目专属的 ingest 扩展（批量 PDF prep、
  主题模板预处理等）、外部 CLI 胶水（pdf 抽图 / obsidian 同步等）、自动化 hook（pre-commit 校验、
  ingest 前清洗等）。**不**放置本 skill 自带的脚本（它们随 skill 分发，见下方「不适用」条）
- 索引文件：`scripts/SCRIPTS.md`（无 frontmatter，与 `MEMORY/MEMORY.md` 同形态）。
  由本文件顶部 `@scripts/SCRIPTS.md` `@import` 加载全文（详见顶部「关键」段）。
  完整契约（每脚本一段：使用场景 / 调用约定 / 作用 / 前置依赖）由 `@import` 自动可见；
  不自动展开 `@import` 的 agent 必须手动 `Read scripts/SCRIPTS.md` 取分节
- 纪律：
  - **添加 / 修改 / 删除脚本文件**只改 `SCRIPTS.md` 一处即可——`@import` 引用同步指向全文，
    **不**需要在 AGENTS.md 单独同步索引
  - **不**写 frontmatter（scripts/ 是代码，不是 wiki 内容页）
  - **`scripts/` 不参与 `lint_wiki.py` 扫描**——脚本代码质量由维护者自行负责
  - **agent 不自动遍历 `scripts/` 跑任何东西**——必须先看 `SCRIPTS.md`（`@import` 加载后即见）
    知道有哪些脚本，再按"调用约定"显式执行；防止意外 execute
  - git 跟踪策略：默认跟踪；启用 git 时跟 wiki 一起 commit；未启用 git 时跟 wiki 走纯目录树
- 不适用：本 skill 自带的 `lint_wiki.py` / `ingest_diff.py` / `log_format.py` / `wiki_write.py`
  ——这些脚本版本由 skill 管，**不**复制进 `scripts/`（避免版本漂移）

## 二、页面类型、frontmatter 与操作阈值

> 本表是 setup 后在 wiki 内的速查（顺序与该处保持字母序一致：comparison → concept →
> entity → source → synthesis）。

| 类型 | 目录 | `type` 字段 | 关键字段 |
| --- | --- | --- | --- |
| 对比页 | `comparisons/` | `comparison` | `compared`（被对比对象路径数组） |
| 概念页 | `concepts/` | `concept` | `related`（相关概念路径数组） |
| 实体页 | `entities/` | `entity` | `aliases`（别名数组，方便搜索） |
| 资料页 | `sources/` | `source` | `sources`（必填，raw/ 路径） |
| 综合页 | `syntheses/` | `synthesis` | `threads`（线索标题数组）+ `sources`（必填，wiki 内其它页路径） |

**所有页面共有 frontmatter**（字段全集 + 类型特化字段见下文各表与字段说明）：

```yaml
---
title: <页面标题>
description: <一句话摘要>  # 推荐；index.md 摘要来源
type: <entity|concept|source|comparison|synthesis>
tags: [<标签>]
created: YYYY-MM-DD HH:MM
updated: YYYY-MM-DD HH:MM
sources: [<路径数组>]  # 必填：source 页 = raw/ 路径（最外层 <wiki>/ 相对，如 raw/articles/x.pdf）；
                        # synthesis 页 = wiki 内页路径（内容根 wiki/ 相对，如 concepts/x.md）
                        # 两类基准刻意区分；entity / concept 可选
---
```

### Tag Taxonomy（防 tag 漂移）

`tags` 字段是 wiki 索引和过滤的入口；不约束会随 ingest 漂移成噪声。本 wiki 的 tag
白名单放在 [`wiki/tags.md`](wiki/tags.md)；本 wiki 创建时由
workspace CLI 生成空白 wiki/tags.md，由 LLM 与用户共同确认主题分类（**10-20 个一级 tag 是建议值，
非权威阈值**——具体数量由用户/agent 共同裁定，按主题复杂度伸缩）。

**规则**：

- agent 在 ingest / query 时遇到新 tag → **直接追加**到 `wiki/tags.md`（无需询问用户），保持字典随 wiki 生长
- 单页 `tags` 建议 3-7 个；过多说明页面主题过散，考虑拆分或聚焦
- tag 取值严格小写 + kebab-case，与文件名命名一致
- **审计循环**：用户可在 `wiki/tags.md` 中**直接删除**误判的 bullet；下次 lint 把
  `tag-not-in-taxonomy`（info）报到所有还引用已删 tag 的页面，由用户裁定二选一：
  重新加回 / 从页面删除 tag
- `lint_wiki.py` 对 `tags` 中**不**在 wiki/tags.md 白名单的值报
  `tag-not-in-taxonomy`（info 级，不阻断）

> **格式约束（影响 lint 解析）**：`wiki/tags.md` 的 tag 列表必须是**裸 bullet**
> （每行 `- ...`），不能包在 code block / HTML comment 里——`parse_tag_taxonomy` 只读裸文本。
> 格式示例：`- 模型：model / architecture`（中文 / 英文分隔符都支持）。
> 多个 tag 用 `/` `，` `,` 任意一种分隔。`lint_wiki.py` 找不到任何 tag 来源或
> 解析出 0 个 tag 时**静默跳过**（不报错），避免新 setup 的 wiki 必报错。

### Page Thresholds（建页/追加/归档决策）

不是每个 entity / concept 都值得独立成页——没阈值 wiki 会被名词堆爆，几个月后 index 翻不到底。

| 动作 | 触发条件 |
| --- | --- |
| **新建 entity / concept 页** | 该 entity / concept 在 ≥ 2 个 source 页中被提到 **或** 是某 source 页的中心主题 |
| **追加到已有页** | source 页提到一个已被覆盖的 entity / concept——追加"参考来源"段即可（不重写） |
| **不创建页** | 路过提及（脚注 / 一次出现的名字）、领域外的细节、与本 wiki 主题无关 |
| **拆分页** | 单页正文超过阈值（SSOT = `lint_wiki.py` 的 `PAGE_SIZE_THRESHOLD` 常量）——拆成子主题 + cross-link，避免单页过于庞杂 |
| **归档页** | 内容被完全取代 / 主题域变化——加 `archived: true`、从 `index.md` 移除（log 走 `ingest` 或 `lint` op，记一条说明性条目） |

> **为什么有阈值**：宁可错过一个 entity 也不要堆十个空页。"克制"是 wiki 长期可用性的具体化——
> 一次放过一个小 entity 几乎无成本；堆一千个空 entity 后 lint 报告会被噪声淹没。

### 认知质量信号（可选，防"弱主张固化成事实"）

> 本节是速查 + 何时标的指引。四个字段**全部可选**，互不依赖。

四个可选 frontmatter 字段：

| 字段 | 取值 | 何时标 |
| --- | --- | --- |
| `reviewed` | `true`（仅在为 true 时写） | 人工**已审核该页**——写 `reviewed: true` + `reviewed_at: <今天>` |
| `reviewed_at` | `YYYY-MM-DD` | 与 `reviewed: true` 成对出现 |
| `contested` | `true`（仅在为 true 时写） | 本页含**尚未裁定**的矛盾主张——搭配 `contradictions` 指向对端 |
| `contradictions` | wiki 页路径数组 | 与本页主张冲突的页面（**双向标注**：A 标 B，B 也标 A） |

`lint_wiki.py` 会把 `contested: true` / 非对称 `contradictions` 拎出来供复审，
未审核页面会标 `pending-review`（info，新常态）。**核心理念**：单源弱断言一旦写进 wiki
不加标注，时间一长会被当成"既成事实"——这是比断链更隐蔽的腐烂，这些字段让它显性化。

**生命周期规则（LLM 必读）**：`reviewed: true` 是"我对这一刻的内容背书"的快照，**不是永久标签**。
任何对页面正文的 LLM 修改都会让戳失效——必须**删除** `reviewed` + `reviewed_at` 回到默认未审核状态，
由人重新审。`lint_wiki.py` 用 `reviewed-stale` 兜底：`reviewed: true` 存在且
`updated > reviewed_at` 时给 warn，把漏清戳的页面拎出来。

### 矛盾处理 Update Policy（ingest 遇到"新资料与已有页冲突"时）

ingest 时新资料与已有页主张冲突，**不要静默覆盖**，按以下顺序处理：

1. **先看日期**——更新的来源一般覆盖旧的；但若旧来源更权威（如官方技术报告 vs 博客），
   保留两者并进入第 2 步
2. **判定是否真矛盾**——版本差异（同一对象 v1 vs v2 的某个属性）、上下文差异
   （不同评测条件）不算矛盾，加注明即可；确属矛盾进入第 3 步
3. **显式记录两种说法**——在页面正文写出 A 说 X（来源 + 日期）、B 说 Y（来源 + 日期），
   不要"和稀泥"挑一个；双方 frontmatter 都设 `contested: true` + `contradictions` 互指
4. **等 lint 复审**——下次 lint 会把 `contested` 页拎出来；与用户一起裁定后，
   移除 `contested`（如该页已审核，按"生命周期规则"判断是否需重新审）

### Index 扩容（防 index.md 翻不到底）

`index.md` 是 wiki 的单一入口，但条目无限增长后同样会腐烂——给它两条护栏：

| 触发条件 | 动作 |
| --- | --- |
| 单个类别（如 `## Sources`）> 50 条 | 按首字母或子域拆成小段（如 `### A-F` / `### G-M`） |
| `index.md` 总条目 > 200 | 新建 `wiki/_meta/topic-map.md` 按主题聚合页面（index 仍按 type 列，topic-map 按主题导航） |

> 这是"建页阈值"在入口侧的对偶——建页克制控制"有多少页"，扩容规则控制"index 还好不好翻"。
> lint 目前**不**自动检测 index 条目数（与 log-truncation 同理：报告而非强制）；agent 在
> lint 半定性环节（§六）观察 index 体积，超阈值时建议用户拆段 / 建 topic-map。

## 三、写入纪律

1. **写前必搜**——创建新页面前先 grep / search `wiki/` 确认是否已有同名或近义页
2. **写后必同步**——新增 / 改 / 删页面后必须同步：
   - `index.md`（条目增减）
   - 相关的 entity / concept 页（追加"参考来源"段，**不重写**）
   - `log.md`（追加操作条目）
3. **改写而非新建**——若已有同类页，**编辑它**而不是建新的副本
4. **重写时保留 frontmatter**——不要因为改写丢失 `type` / `tags` / `sources` 字段
5. **交叉引用走相对路径**——`[link](../concepts/transformer.md)`，**不要**用 wikilink
   `[[transformer]]`、**不要**用绝对路径
6. **路径稳定**——文件名一旦确定就是永久 ID；想改名时重命名文件 + 更新所有引用（启用
   git 时用 `git mv` 保留 history；未启用 git 时用普通 `mv` + 全量更新引用）

## 四、阅读纪律

1. **读 raw 优先**——source 页的引用若与 raw 矛盾，回到 raw 复核
2. **读 index 起手**——找相关页面前先看 `index.md` 分类
3. **不读 log 内容**做证据——log 是时间线，证据在源页里
4. **跨页综合走 query 操作**——读多页 + 综合 + 给引用，不要拼接

## 五、Query 纪律

1. **先看 index，再读相关页**——不要直接全量 grep
2. **答案带引用**——每条事实带 `(来源: <page path>)`
3. **矛盾显式标注**——不要"和稀泥"
4. **好答案问归档**——对比 / 综合 / 发现新联系 → 询问用户是否写回 wiki

## 六、Lint 纪律

1. **脚本检查 deterministic 部分**——raw/ 不可变性、frontmatter、index 覆盖、断链、log 格式
2. **agent 检查半定性部分**——矛盾、缺失交叉引用、过期主张
3. **修 lint 不要回退 schema**——若 lint 报告与本文件冲突，**先讨论用户**再决定

## 七、本文件本身的纪律

- 本文件是 schema，**不是 wiki 内容**——不要往里塞 wiki 主题相关的笔记
- 改本文件 = 改 skill 行为 = 大事；先和用户确认
- **模板升级时本文件按 skill 最新模板全量重渲染**（本 wiki 的健康检查强制这一条；本地定制先沉淀 `MEMORY/`，
  详见顶部说明）——§八 四行变量
  （主题 / 创建日期 / CLI 版本 / Wiki Spec 版本）是仅有的 per-wiki 内容，升级时保留
- 若 wiki 启用 git，每次改建议 commit 并加清晰的 commit message；未启用 git 跳过此步

## 八、当前配置

| 字段 | 值 |
| --- | --- |
| 主题 | {{TOPIC_NAME}} |
| 创建日期 | {{SETUP_DATE}} |
| Wiki 根 | <由 LLM_WIKI_ROOT 环境变量或 init 时确定> |
| Wiki Spec 版本 | {{WIKI_SPEC_VERSION}} |
| CLI 版本 | {{CLI_VERSION}} |

## 九、yzr 个人工作习惯

本节约定 yzr 的个人工作习惯——agent 与 yzr 协作时必须遵守。这些习惯服务的对象是
用户本人（不是 wiki 机制），当前含四类：

### 语言风格（对用户不用黑话，严谨精确）

对用户说话（汇报 / 回答 / 报告 / 提问 / 对话回复）遵守两条：

- **不用黑话**——本守则的内部术语（ingest / lint / SSOT / 复利 / 三层纪律 等）对用户
  要说成日常语言："把这份资料整理进 wiki" / "检查 wiki 的健康状况" / "开工前先读 wiki
  的守则、索引和日志"；必须提术语时括号给一句白话解释。不写网络行话 / 口头禅
  （"牛逼" / "走起" / "整一个" / "搞一下"）。
- **严谨精确**——动词说清结果（已创建 `wiki/sources/foo.md` / 已更新 3 处字段 /
  未执行并说明原因，不用"处理了 / 搞定了"）；文件给相对路径、数量给具体数字（
  "5 个页面缺 `updated`"，不说"一些页面"）；区分事实与推断（"wiki 记载 X（来源：...）"
  vs "我推测 Y"，没依据的不写进 wiki 正文）；报告按三段——**做了什么 / 没做什么
  （及原因）/ 需要你决定什么**。

### 遇阻退后一步

同一思路连续两次未果 / 修改面越滚越大 / 开始想绕过纪律（"先跑通再说"）——任一信号
出现即停下来，退后一步按三步走：

- **回头看**——倒查当前路径上最早的可疑决策点（误解需求 / 选错文件 / 选错抽象），
  优先修上游，不在下游硬补。
- **第一性原理重审**——剥掉现有实现的惯性，回到"目标是什么、真正的约束是什么"；
  答案与当前做法冲突时，向用户说明后换路，不硬撞。
- **举一反三**——顺手查同类：同模式的其他文件 / 配置 / 页面是否有同样缺陷；汇报
  按"类"报（"同类问题还有 3 处：…"），不只报当前这个点。

### 表达先归纳后落笔

把需求 / 素材写成文字（纪律 / 文档 / 汇报）时，先归纳再落笔，**不**把输入清单
逐项复述成结构：

- **先合并同义**——输入给的几个关键词 / 要求先查语义重叠，重叠的并为一条；一条
  意思全文只说一次，标题 / 导语不重复正文已有的词。
- **每句过删除测试**——写完逐句问"删掉这句读者损失什么"，没损失就删；对纪律类
  文字冗余 = 稀释，每个多余词都在分摊读者注意力。

### 产出风格条件对齐（未安装对应 skill 则整条忽略）

写 wiki 成文产物（页面正文 / 综合 / 对比 / 归档答案）时，若当前 agent 环境已安装
`yzr-writing-review`，落笔前按其评审立场自查；写代码（本 wiki `scripts/` 自维护脚本 +
`raw/external/` target 仓的开发协作）时，若已安装 `yzr-coding-review`，同理按其评审
立场自查。未安装对应 skill → 本条整条忽略：不视为违反纪律、不阻塞工作、不要求安装。
