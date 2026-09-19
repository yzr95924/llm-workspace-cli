# Ingest 详细流程

Ingest 把 `raw/` 里的原始资料变成 wiki 内的**摘要页** + 同步相关 entity / concept
页 + 更新 index + 追加 log。一份资料通常涉及 **1 source 页 + 0~N entity / concept
页 + 1 index 更新 + 1 log 条目**。

## 入口与触发

**主动触发**：用户说"摄取 X 到 wiki" / "把 raw/articles/foo.md ingest" /
"raw/articles/ 里这批都摄取一下"。

**被动触发**：用户跑 `llmw wiki ingest-diff` 发现未摄取项，问"这些是不是要 ingest"。

**定期触发**：用户设 cron / 习惯——每周一次把 `raw/articles/` 新增的全部 ingest。

## 流程详解

### Step 1：识别需要摄取的文件

```bash
# 日常：同时找全新文件 + raw 被更新过的已归档文件
llmw wiki --path="$LLM_WIKI_ROOT" ingest-diff --check-stale
```

- 扫 `raw/` 递归（`assets/` 与 `discussions/` 子树除外），对照所有 `wiki/sources/*.md` 的
  `frontmatter.sources` 建立 raw 路径 → source 页映射
- 输出需要关注的文件清单（plain text 或 `--json`），按 reason 分三类：
  - `untracked`——从未摄取的全新文件
  - `stale-raw`（仅 `--check-stale`）——已有 source 页，但 raw 文件 mtime 晚于 source
    页 `updated`，说明 raw 被用户更新过，需**重新摄取**
  - `log-only-no-source-page`——log 有 ingest 记录但 source 页缺失，需重建
- 退出码：0 = 无需关注；1 = 有需要处理的项；2 = 运行错误（stderr 自明）

**注意**：判定"已摄取"的依据是**对应 source 页存在且 frontmatter.sources 含此路径**。
仅在 log.md 里有引用但 source 页被删的视为**未摄取**——这种情况需要重建 source 页。

### Step 2：评估规模

待摄取文件 < 3 → 一次性处理；≥ 3 → 走「批处理摄取」路径。
> 20 → 先询问用户"是否先处理这 5 个"，分多批推进。

**分批策略**：按主题聚类（同一议题 / 同一作者 / 同一时间段优先），不要按文件
名随机排序。

### Step 3：写 source 页

对每个待摄取文件（untracked 或 stale-raw）。**stale-raw 的关键差异**：对应 source 页已
存在 → 用 **Edit** 更新正文 + 把 `updated` 改今天（`created` 保留原值），**不要** Write
覆盖、不要重建 entity / concept 的"参考来源"段（只追加新来源）：

> **若重摄发现新内容与已有 entity / concept 页主张矛盾**——不要静默覆盖旧说法，走
> [`page-templates.md「矛盾处理 Update Policy」`](page-templates.md)
> （双方设 `contested: true` + `contradictions` 互指、正文显式记录两种说法）。这是 `contested` 信号最常见的产生时机。
>
> **生命周期纪律（stale-raw / 重摄取）**：被更新的 source 页如果原来 `reviewed: true`，
> 编辑完跑 `llmw wiki write touch <page>`（自动 `updated`=现在 + 删 `reviewed`/`reviewed_at`）。
> 事件表与"两道闸门"细节见 [page-templates.md「生命周期规则」](page-templates.md)。

1. **完整读取 raw 资料**——若是 PDF / 图片，先做 OCR / 视觉识别
2. **提取元数据**：标题、作者 / 来源、发布时间、URL（若有）、关键标签
3. **生成 slug**——kebab-case 短标题（例 `attention-is-all-you-need`），文件名
   `<slug>.md`
4. **脚手架走 `llmw wiki write new --type=source --slug=... --title=... --sources=raw/...`**
   （自动生成 5 必填 frontmatter + H1，slug 校验 + 拒覆盖）——然后 Edit 写正文，
   使用 source 模板（见 [`page-templates.md「source（资料页）」`](page-templates.md)，字段定义不重抄）：
   - 摘要（200-500 字）——核心论点 / 关键数据 / 与本 wiki 其他资料的关系
   - 关键引用——可独立成段的引文 / 数字 / 结论
   - 链接出去的 cross-refs——相关 entity / concept / source 页
   - 正文含交互流 / 架构关系时优先配图——判定与选型见 [`page-templates.md「图示使用指引」`](page-templates.md)
   - `created`：全新文件设 today；stale-raw 重摄取保留原值
   - **认知质量信号（可选）**：fast-moving / 争议 / 单一弱来源的 source 页，建议在 frontmatter
     标 `contested: true`（仅当**确属矛盾未裁定**时）——信号语义详见
     [`page-templates.md「可选：可信度与认知质量信号」`](page-templates.md)
5. **决策点：是否需要新建 entity / concept 页**——判定阈值与例见
   「判定"是否新建 entity / concept 页"」节

### Step 4：同步 entity / concept 页

**若已有相关 entity / concept 页**：

- **不重写**——只追加"## 参考来源 / Sources"段
- 每条新 source 写一行：`* [Source Title](../sources/<slug>.md) — 一句话关联点`
- **保持顺序**：新追加的放最前面或最后面，整个文件**只追加**不重排

**若新建 entity / concept 页**：

- 走 [`page-templates.md`](page-templates.md)「entity（实体页）」/「concept（概念页）」 的 entity / concept 模板
- frontmatter 含 `created=updated=today`
- 正文含：定义 / 关键属性 / 已知出现于（指向 source 页列表）

### Step 5：更新 `wiki/index.md`

- `llmw wiki write index add <wiki/sources/<slug>.md>`（或新建的 entity / concept 页）
  ——CLI 从页 frontmatter 抽 title / description，定位类别段、字母序插入
  （条目格式 `- [<title>](<path>) — <description>`，摘要直接复制 frontmatter
  `description` 防漂移）
- 若新建了 entity / concept 页：同时**反向检查**——之前 source 页是否该有指向新页的
  cross-ref？没有就加（这是"维护交叉引用"的一部分）

### Step 6：追加 `log.md`

- `llmw wiki write log --op=ingest --title="<source 页 title>"`——严格格式 + 滚动窗口
  截断自动保证（上限见 `wiki/log.md` 头部；超限时 lint finding 自带数值）
- 一次 ingest 多个文件 → **重复 `--title`**（每条对应一个 source 页）；
  批处理走 `--bulk --topic ... --count ...`（见「批处理摄取」）

### Step 7：建议 commit（启用 git 时）

> **前提**：本步仅在 wiki 启用了 git 时执行；裸目录树 wiki 直接跳过（无版本控制，
> 由用户决定是否后续手动 `git init` + 回填 history）。

- 不是必须，但强烈建议——wiki 改动可追溯
- commit message 格式：`ingest: <title>` 或 `ingest: <N> files from raw/articles/`
- agent 应提示用户："wiki 已更新，建议 commit。message 草稿：`<msg>`，要我帮你
  commit 吗？"

**收尾建议**：无论是否 commit，主动问用户"要不要查一下新内容与已有内容的
联系？"（query 触发约定见 [`query-workflow.md「入口与触发」`](query-workflow.md)）。

## frontmatter 字段参考（source 页）

> 字段全集 + 语义定义见 [`page-templates.md「共有 frontmatter 段」`](page-templates.md) +
> [`page-templates.md「source（资料页）」`](page-templates.md)；骨架由 `llmw wiki write new` 生成。

本节只列 source 页**特化**注意事项（page-templates.md「source（资料页）」已有的字段定义不重抄）：

- `sources` 必填——`raw/` 下相对路径数组，至少 1 条（`raw/discussions/` 路径 lint 报
  `source-in-discussions`，需先归档到 `raw/articles/` 或重摄取）
- 推荐 `description`
- 可选 `authors` / `published` / `url` / `venue`——便于反向溯源（index 摘要只取 `description`）

## 批处理摄取（≥ 3 份 raw 同时摄入）

> 主 SKILL.md「Ingest」只留 pointer；批处理的详细 5 步 + 为什么批处理 +
> log 标题前缀约定一律写在本节。

当 `llmw wiki ingest-diff` 返回 ≥ 3 个待摄取文件，或用户明确说"把这堆一起 ingest / 整批过稿"，
走批处理路径而非逐份处理。

### 5 步流程

1. **Read 所有 raw**——一次性读完所有待处理 raw（先列清单 + Read 并行）
2. **聚合 entity / concept**——跨所有 raw 找出候选 entity / concept，**去重合并**；
   同一概念在多篇 raw 出现时只对应一个 wiki 页（避免重复创建）
3. **一次 search**——用 `Grep` 在 `wiki/` 全域搜所有候选 entity / concept 名称，**一次**
   搜完（不要 N 次）；产出"已存在 / 待新建"两栏
4. **一次写入**——按以下顺序成片写：
   - source 页（`llmw wiki write new` 脚手架 + Edit 正文，按主题聚类而非 raw 文件名
     顺序——主题相近的先写，便于交叉引用）
   - entity / concept 页（先建新的，再更新已有的——追加"参考来源"段，不重写）
   - `wiki/index.md`（所有改动落定后集中补：**每页一次** `llmw wiki write index add <page>`；
     不要每写一页更一次 index）
   - `wiki/log.md`（`llmw wiki write log --op=ingest --bulk --topic="<主题概览>" --count=<N>`，
     标题里把本批主题说清；不再逐文件分别追加 ingest 条目——避免 log 被一次 ingest 撑爆）
5. **报告**——告诉用户哪些是新建页、哪些是更新页、哪些 entity / concept 因聚合而合并

> **为什么批处理**：逐份处理在 N 份 raw 时要做 N 次 search + N 次 index 更新 + N 条
> log，既慢又容易因中间步骤失败导致不一致；批处理把主流程收敛成一次写入，副作用面最小。
> `Bulk:` 标题前缀保留后续按需 grep 出"批量事件"的能力（无需新增 `bulk-ingest` op）。

## 判定"是否新建 entity / concept 页"

阈值 canonical 见 [`page-templates.md「建页 / 追加 / 归档阈值」`](page-templates.md)。

**单篇 ingest 视角的套用**：本 raw 的中心主题 / 反复出现的核心概念 → 建；路过 / 类比 /
背景提及 → 不建；已有同名 / 近义页 → 先 search 再定（写前必搜）。例：反复提到
"self-attention" 且无页 → 建 `concepts/self-attention.md`；偶然提到一次 "GPU" → 不建。

## 正文引用的稳定性（漂移点规避）

写 wiki 页正文、或对话作答中引用上游事实时，先做**感知测试**：

> 这条引用依据的上游事实变化时，wiki 有任何机制（lint / anchor / stale 检查）
> 能发现吗？不能 = 漂移点——它会静默腐烂成"既成事实"，必须改写。

引用精度与稳定性成反比：降精度、加锚点、打时间戳。

| 漂移点 | 反例 | 改写 |
| --- | --- | --- |
| 位置引用 | `foo.py:812`、PDF 第 34 页 | 引符号名 / 章节标题；git 仓引 commit SHA |
| 瞬态数值 | "star 数 1.2w"、跑分 | 值 + "截至 YYYY-MM-DD"；或只引来源不录值 |
| 版本绑定 | "最新版支持 X" | 写死版本号（"v2.3 起"）；禁裸"最新 / 目前" |
| 完整枚举 | 全参数清单 | 代表性例子 + "完整清单见来源"；清单属来源不属 wiki |
| 归属信息 | "由张三维护" | 引角色不引人名 |

## Ingest 失败的常见原因

- **已存在同名 source 页**——用 Edit 更新而不是 Write 覆盖（`llmw wiki write new` 拒覆盖）
- **wiki/index.md 缺类别段**——补类别段（骨架见 page-templates.md「index（index.md）」）或走
  upgrade fixtures 修复

> raw 不可读 / log/index 参数缺失等场景，CLI 报错信息自明——按提示修即可。

## 反模式

- 一份资料写 5 个 source 页（粒度过细）——按"主题"分，不是按"raw 文件 1:1"
- source 页只复制 raw 内容——必须消化、提炼、加 cross-refs
- 跨主题的 entity 混在一起——本 skill 假设一个 wiki 一个主题；跨主题用不同的 wiki

## raw/discussions/ 草稿消化（可选入口）

> **完整纪律**（路径 / 谁可写 / CLI 契约三道 / 归档路径两条 / 滑坡防线）由
> wiki 根 `AGENTS.md` 的 `raw/discussions/` 节承载——agent 自动加载必读。
