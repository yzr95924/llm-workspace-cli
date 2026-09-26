# Ingest 详细流程

Ingest 把 `raw/` 的原始资料消化成 wiki 内容页，通常一份资料涉及 **1 source 页 +
0~N entity / concept 页 + 1 index 更新 + 1 log 条目**

## 流程详解

### Step 1：识别需要摄取的文件

```bash
# 找全新 / raw 有更新待重摄取 / log 有记录但 source 页缺失待重建的文件
llmw wiki --path="$LLM_WIKI_ROOT" ingest-diff --check-stale
```

输出按 reason 分类（`untracked` / `stale-raw` / `log-only-no-source-page`），含义与退出码
输出自明；流程其他环节报错（raw 不可读 / log、index 参数缺失）同样按 CLI 提示修即可。

### Step 2：评估规模

< 3 份逐份处理；≥ 3 份走 [章节](#批处理摄取-3-份-raw-同时摄入)；> 20 份先问用户"是否先处理
主题 X 这 N 份"、分多批推进（N / 主题 X 取自第一个主题聚类的结果；数字均为经验建议阈值，
非 CLI 强制）。**分批按主题聚类**（同议题 / 同作者 / 同时间段优先），不按文件名随机排

### Step 2.5：与用户对齐要点（仅交互式单篇 / 少量）

确认主题方向 / 重点交叉的 entity / 用户点名要保留的要点；批处理或用户已明示方向时跳过

### Step 3：写 source 页

**stale-raw 差异**：source 页已存在 → 用 **Edit** 更新正文，frontmatter `sources` 只追加
新路径、不重写整块，**不要** Write 覆盖

对每个待摄取文件：

1. **完整读取 raw**：PDF / 图片先做 OCR / 视觉识别
2. **提取元数据**：标题、作者 / 来源、发布时间、URL、关键标签
3. **生成 slug**：kebab-case 短标题（例 `attention-is-all-you-need`）
4. **脚手架**：`llmw wiki write new --type=source --slug=... --title=... --sources=raw/...`
   （自动落必填 frontmatter + H1，slug 校验 + 拒覆盖）→ Edit 写正文；节结构与字段
   （含元数据落点、摘要写法）以 [章节](page-templates.md#source资料页) 为准。
   ingest 特有纪律：
   - 正文含交互流 / 架构关系时优先配图，判定见
     [章节](page-templates.md#图示使用指引)
   - 确属矛盾未裁定时才标 `contested: true`（语义见
     [章节](page-templates.md#可选可信度与认知质量信号)）
5. **重摄取发现矛盾**：不静默覆盖，走
   [章节](page-templates.md#矛盾处理-update-policy)（双方 `contested: true` +
   `contradictions` 互指）
6. **生命周期**：编辑过 source 页就跑 `llmw wiki write touch <page>`（自动把 `updated`
   置今天、删 `reviewed` / `reviewed_at` 戳），不要手工改 `updated`，见
   [章节](page-templates.md#生命周期规则)
7. **是否新建 entity / concept 页**：见 [章节](#判定是否新建-entity--concept-页)

### Step 4：同步 entity / concept 页

- **已有相关页**：不重写，只追加 `## 参考来源 / Sources` 段，每条新 source 一行
  `* [Source Title](../sources/<slug>.md) — 一句话关联点`；**只追加不重排**
- **新建页**：走 page-templates 的 entity / concept 骨架

### Step 5：更新 `wiki/index.md`

- `llmw wiki write index add <page>`：CLI 从页 frontmatter 抽 title / description，
  定位类别段 + 字母序插入（不在 index 手写摘要，防漂移）
- 新建了 entity / concept 页时**反向检查**：既有 source 页是否该加指向新页的 cross-ref

### Step 6：追加 `log.md`

- `llmw wiki write log --op=ingest --title="<source 页 title>" --raw="raw/<相对路径>"`：
  格式 + 滚动窗口截断自动保证；`--raw` 记录被摄取文件（wiki 根相对、`raw/` 起头，
  是 `ingest-diff` 判定 log-only-no-source-page 的精确依据）
- 一次 ingest 多个文件 → `--title` 与 `--raw` 重复且按序配对；批处理走 `--bulk`（见下节）

### Step 7：建议 commit（启用 git 时）

- commit message：`ingest: <title>` 或 `ingest: <N> files from raw/articles/`；agent
  提示用户："wiki 已更新，建议 commit。要我帮你 commit 吗？"
- 裸目录树 wiki 跳过此步

**收尾**：主动问用户"要不要查一下新内容与已有内容的联系？"（query 流程见
[章节](query-workflow.md#流程详解)）

## 批处理摄取（≥ 3 份 raw 同时摄入）

**为什么批处理**：逐份处理 N 份 = N 次 search + N 次 index 更新 + N 条 log，既慢又易因中间
步骤失败导致不一致；批处理把主流程收敛成一次写入，副作用面最小

1. **Read 所有 raw**：先列清单，再并行 Read
2. **聚合 entity / concept**：跨所有 raw 找候选，**去重合并**（同一概念只对应一个 wiki 页）
3. **一次 search**：用 Grep 一次搜完全部候选名称；产出"已存在 / 待新建"两栏
4. **一次写入**，按序成片落：source 页（按主题聚类顺序，便于交叉引用）→ entity / concept
   页（先建新、再追加旧的"参考来源"段）→ index（所有页写完后集中补，每页一次
   `write index add`）→ log（`write log --op=ingest --bulk --topic="<主题概览>" --count=<N>`
   一条，不逐文件追加，避免 log 被一次 ingest 撑爆）
5. **报告**：哪些是新建页 / 更新页 / 因聚合而合并

## 判定"是否新建 entity / concept 页"

阈值 canonical 见 [章节](page-templates.md#建页--追加--归档阈值page-thresholds)

**单篇 ingest 视角的套用**：本 raw 的中心主题 / 反复出现的核心概念 → 建；路过 / 类比 /
背景提及 → 不建；已有同名 / 近义页 → 先 search 再定（写前必搜）。例：反复提到
"self-attention" 且无页 → 建 `concepts/self-attention.md`；偶然提到一次 "GPU" → 不建

## 正文引用的稳定性（漂移点规避）

写 wiki 页正文、或对话作答中引用上游事实时，先做**感知测试**：这条引用依据的上游事实
变化时，wiki 有任何机制（lint / anchor / stale 检查）能发现吗？不能 = 漂移点，它会静默
腐烂成"既成事实"，必须改写

引用精度与稳定性成反比：降精度、加锚点、打时间戳

| 漂移点 | 反例 | 改写 |
| --- | --- |
| 位置引用 | `foo.py:812`、PDF 第 34 页 | 引符号名 / 章节标题；git 仓引 commit SHA |
| 瞬态数值 | "star 数 1.2w"、跑分 | 值 + "截至 YYYY-MM-DD"；或只引来源不录值 |
| 版本绑定 | "最新版支持 X" | 写死版本号（"v2.3 起"）；禁裸"最新 / 目前" |
| 完整枚举 | 全参数清单 | 代表性例子 + "完整清单见来源"；清单属来源不属 wiki |
| 归属信息 | "由张三维护" | 引角色不引人名 |

## 反模式

- 一份资料写 5 个 source 页（粒度过细）：按"主题"分，不是按"raw 文件 1:1"
- source 页只复制 raw 内容：必须消化、提炼、加 cross-refs
- 跨主题的 entity 混在一起：本 skill 假设一个 wiki 一个主题；跨主题用不同的 wiki

## raw/discussions/ 草稿消化（可选入口）

完整纪律（路径 / 谁可写 / CLI 契约三道 / 归档路径两条 / 滑坡防线）由 wiki 根 `AGENTS.md`
的 `raw/discussions/` 节承载，agent 自动加载必读
