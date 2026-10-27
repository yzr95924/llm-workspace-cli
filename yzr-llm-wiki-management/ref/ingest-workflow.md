# Ingest 详细流程

Ingest 把 `raw/` 的原始资料消化成 wiki 内容页。默认 1 份 raw 对应 1 个 source 页，
跨主题才拆；一次摄取通常还涉及 0 至 N 个 entity / concept 页、index 更新与 log 条目。

## 准备

- 先读 wiki 根三份文档：`AGENTS.md`（纪律与 format 版本）、`wiki/index.md`（有哪些页、
  归哪些类）、`wiki/log.md`（最近约 30 行，避免重复动作）

```bash
# 找全新 / raw 有更新待重摄取 / log 有记录但 source 页缺失待重建的文件
llmw wiki --path="$LLM_WIKI_ROOT" ingest-diff --check-stale
```

输出按 reason 区分 `untracked` / `stale-raw` / `log-only-no-source-page`；可发现范围是
`*.md` / `*.markdown` / `*.txt`，PDF / 图片等不在其中，用户点名或另有清单时按本文逐个处理

- **评估规模**：少于 3 份逐份处理；3 份及以上走批处理摄取；超过 20 份先按主题聚类
  （同议题 / 同作者 / 同时间段优先，不按文件名随机排），再问用户先处理哪一簇、逐批推进
  （数字均为经验阈值，非 CLI 强制）
- **对齐要点**（交互式处理单篇或少量文件、且用户没给明确方向时）：确认主题方向、
  重点交叉的 entity、用户点名要保留的要点。用户已明示方向时直接执行，不输出摄取计划
  等用户确认；批处理跳过对齐

## 单篇处理

命中 `stale-raw` 的文件不建新页：source 页已存在，增量更新正文，不要整页覆盖（整页
重写会丢失既有正文）；frontmatter `sources` 只追加新来源，同一 raw 路径重摄取保持原样，
不重写整块。
`stale-raw` 判据按日期比较：raw 文件的修改日期晚于 source 页 `updated` 的日期（同日
不算）。给这种页单独补链再跑 `write touch` 会把 `updated` 推到今天，掩盖还没重新消化
的内容。不在本次任务范围的 `stale-raw` 项，不动其 source 页（补链留到重摄取时做），
或在交付时注明已顺延处理。

对每个待摄取文件：

1. 完整读取 raw：PDF / 图片先做 OCR / 视觉识别；页面内容须消化、提炼、加交叉引用，
   不复制 raw 原文
2. slug 默认从 raw 文件名派生（去扩展名、规范化 kebab-case，例
   `attention-is-all-you-need`）；另取标题时向用户说明理由
3. 新建页面：`llmw wiki write new --type=source --slug=... --title=... --description=... --sources=raw/...`，
   再补写正文；节结构与字段（含元数据落点、摘要写法）以
   [章节](page-templates.md#source资料页) 为准。正文含交互流 / 架构关系时优先配图，
   判定见[章节](page-templates.md#图示使用指引)
4. 发现矛盾：重摄取时冒出与既有页冲突的说法，不静默覆盖，走
   [章节](page-templates.md#矛盾处理)
5. 生命周期：凡改过页面正文就跑 `llmw wiki write touch <page>`（含后续步骤对既有页
   的追加与补链），规则见[章节](page-templates.md#生命周期规则)
6. 判断是否新建 entity / concept 页：判据见
   [章节](page-templates.md#建页--追加--归档阈值page-thresholds)。entity / concept
   按主题域归位；例：单篇反复提到 self-attention 且无页，建 `concepts/self-attention.md`；
   偶然提到一次 GPU，不建

同步 entity / concept 页：

- 已有相关页：不重排，只往 `## 参考来源 / Sources` 段末尾追加（条目格式照 page-templates
  骨架该节）
- 新建页：走 page-templates 的 entity / concept 骨架

记录：

- `llmw wiki write index add <page>`；新建了 entity / concept 页后回看一遍，既有
  source 页里该指向新页的交叉引用补上
- `llmw wiki write log --op=ingest --title="<source 页 title>" --raw="raw/<相对路径>"`：
  `--raw` 记录被摄取文件，是 `ingest-diff` 判定 `log-only-no-source-page` 的精确依据
  （未记录时按 title slug 归一化兜底）；sources 指向 external 目录（整仓语料）时不传
  `--raw`（该 flag 只接受文件）；批处理走 `--bulk`（见批处理摄取一节）

## 批处理摄取（3 份及以上 raw 同时摄入）

1. 读所有 raw：先列清单，再并行读全文
2. 聚合 entity / concept：跨所有 raw 找候选并去重（同一概念只对应一个 wiki 页）
3. 统一搜索：对全部候选名称做一轮全文搜索，列出已存在与待新建两栏
4. 按序写入：source 页（按主题聚类顺序，便于交叉引用），再 entity / concept 页（先建
   新页，再往既有页追加参考来源），再 index（所有页写完后逐页 `write index add`），
   最后 log（`write log --op=ingest --bulk --topic="<主题概览>" --count=<N>` 一条记录
   整批，不逐文件追加，避免一次 ingest 在 log 塞入过多条目）
5. 报告：哪些页新建、哪些页更新、哪些因聚合而合并

## 验证

交付前重跑 `llmw wiki ingest-diff --check-stale`：本次范围内、该命令可发现的文件不再报
待处理；未动的 stale 项（如顺延补链的）与非文本素材的处理结果在交付说明列明。
