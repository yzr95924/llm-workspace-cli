# Ingest 详细流程

Ingest 把 `raw/` 的原始资料消化成 wiki 内容页。通常一份资料涉及：1 个 source
页 + 0~N 个 entity / concept 页 + index 更新 + log 条目

## 识别需要摄取的文件

```bash
# 找全新 / raw 有更新待重摄取 / log 有记录但 source 页缺失待重建的文件
llmw wiki --path="$LLM_WIKI_ROOT" ingest-diff --check-stale
```

输出按 reason 分类（`untracked` / `stale-raw` / `log-only-no-source-page`），
分类、含义与退出码均输出自明

## 评估规模

< 3 份逐份处理；≥ 3 份走「批处理摄取」；> 20 份先按主题聚类（同议题 / 同作者 /
同时间段优先，不按文件名随机排），再问用户先处理哪一簇、逐批推进（数字均为经验
阈值，非 CLI 强制）

## 对齐要点（仅方向不明时）

交互式单篇 / 少量、且用户没给明确方向时做：确认主题方向、重点交叉的 entity、
用户点名要保留的要点。用户已明示方向 = 直接执行，不主动摊开摄取计划求追认；
批处理跳过本节

## 写 source 页

命中 `stale-raw` 的文件不建新页：source 页还在，**增量更新**正文（**不要**
整页覆盖，整页重写丢既有正文），frontmatter `sources` 只追加新路径、不重写整块。
注意 `stale-raw` 判据是 raw 的修改时间晚于 source 页 `updated`：只给这种页
补链就跑 `touch` 会推前 `updated`、洗掉重摄取信号——不在本次任务范围的
`stale-raw` 项，别动其 source 页（补链留到重摄取时做），或交付时注明已顺延处理

对每个待摄取文件：

1. **完整读取 raw**：PDF / 图片先做 OCR / 视觉识别
2. **slug**：建议默认从 raw 文件名派生（去扩展名、规范化 kebab-case，例
   `attention-is-all-you-need`）；要另取标题时向用户说明理由
3. **脚手架**：`llmw wiki write new --type=source --slug=... --title=... --sources=raw/...`，
   然后补写正文；节结构与字段（含元数据落点、摘要写法）以
   [章节](page-templates.md#source资料页) 为准。正文含交互流 / 架构关系
   时优先配图，判定见[章节](page-templates.md#图示使用指引)
4. **发现矛盾**：重摄取时冒出与既有页冲突的说法，不静默覆盖，走
   [章节](page-templates.md#矛盾处理)
5. **生命周期**：凡改过页面正文就跑 `llmw wiki write touch <page>`（含后续
   步骤对既有页的追加与补链），规则见[章节](page-templates.md#生命周期规则)
6. **是否新建 entity / concept 页**：判据见
   [章节](page-templates.md#建页--追加--归档阈值page-thresholds)。
   例：单篇反复提到 self-attention 且无页，建 `concepts/self-attention.md`；
   偶然提到一次 GPU，不建

## 同步 entity / concept 页

- **已有相关页**：不重排，只往 `## 参考来源 / Sources` 段末尾追加（条目格式照
  page-templates 骨架该节）
- **新建页**：走 page-templates 的 entity / concept 骨架

## 更新 `wiki/index.md`

- `llmw wiki write index add <page>`
- 新建了 entity / concept 页后回看一遍：既有 source 页里该指向新页的交叉引用
  补上

## 追加 `log.md`

- `llmw wiki write log --op=ingest --title="<source 页 title>" --raw="raw/<相对路径>"`：
  `--raw` 记录被摄取文件，是 `ingest-diff` 判定 log-only-no-source-page 的精确
  依据（未记录时按 title slug 归一化兜底）
- 批处理走 `--bulk`（见「批处理摄取」）

## 建议 commit 与收尾

- message 形如 `ingest: <title>` 或 `ingest: <N> files from raw/articles/`
- 收尾关联查询建议写成交付回复末尾一行，不另起确认轮（query 流程见
  query-workflow.md）

## 批处理摄取（≥ 3 份 raw 同时摄入）

1. **读所有 raw**：先列清单，再并行读全文
2. **聚合 entity / concept**：跨所有 raw 找候选并去重（同一概念只对应一个 wiki 页）
3. **一次搜完**：对全部候选名称做一轮全文搜索；产出"已存在 / 待新建"两栏
4. **一次写入**，按序成片落：source 页（按主题聚类顺序，便于交叉引用）→ entity /
   concept 页（先建新、再追加旧的"参考来源"段）→ index（所有页写完后集中补，每页
   一次 `write index add`）→ log（`write log --op=ingest --bulk --topic="<主题概览>" --count=<N>`
   一条，不逐文件追加，避免 log 被一次 ingest 撑爆）
5. **报告**：哪些是新建页 / 更新页 / 因聚合而合并

## 正文引用的稳定性（漂移点规避）

正文或对话作答引用上游可变事实时，先过一遍机械判定：上游事实变了，wiki 有任何
机制（lint / anchor / stale 检查）能发现吗？发现不了的引用就是漂移点，按下列
类别改写

- **位置引用**（`foo.py:812`、PDF 第 34 页）：引符号名 / 章节标题；git 仓引
  commit SHA
- **瞬态数值**（"star 数 1.2w"、跑分）：值 + "截至 YYYY-MM-DD"；或只引来源不录值
- **版本绑定**（"最新版支持 X"）：写死版本号（"v2.3 起"）；禁裸"最新 / 目前"
- **完整枚举**（全参数清单）：代表性例子 + "完整清单见来源"；清单属来源不属 wiki
- **归属信息**（“由张三维护”）：引角色不引人名

日期只标上游事实的有效时点；本次核对 / 回查 / 修订不写进页面标题、节名或正文，
既有这种写法不跟随复制

## 反模式

- 一份资料写 5 个 source 页（粒度过细）：页数跟主题走，默认 1 份 raw 1 页，
  跨主题才拆
- source 页只复制 raw 内容：必须消化、提炼、加交叉引用
- 跨主题的 entity 混在一起

## raw/discussions/ 草稿消化

本入口可选；完整纪律由 wiki 根 `AGENTS.md` 的 `raw/discussions/` 节承载
