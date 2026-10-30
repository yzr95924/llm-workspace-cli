# Ingest workflow

把 `raw/` 资料消化成 source 页及必要的 entity / concept 页。默认 1 份 raw 对应 1 个
source 页，跨主题才拆。

## 准备

1. 读 wiki 根 `AGENTS.md`、`wiki/index.md`、`wiki/log.md` 最近约 30 行、`wiki/tags.md`
2. 跑 `llmw wiki --path="$LLM_WIKI_ROOT" ingest-diff --check-stale --json`，按
   `untracked` / `stale-raw` / `log-only-no-source-page` 逐项处理；PDF、图片等非文本素材
   只有用户点名或另有清单时才逐个处理
3. 少于 3 份逐份处理；3 份及以上批处理；超过 20 份先按主题聚类，问用户先处理哪一簇
4. 单篇或少量文件且用户未给方向时，先确认主题、重点 entity 和须保留的要点；用户已给
   方向则直接执行
5. 新建页时先读 `wiki/tags.md` 选择既有 tag 或新增；新 tag 直接追加白名单，无需询问

## 处理

1. 完整读取本批 raw；PDF / 图片先 OCR 或视觉识别，列出跨文件重复出现的 entity /
   concept 候选
2. `stale-raw` 不建新页：找到既有 source 页后增量更新正文，不整页覆盖；本次不处理的
   stale 项不动其页面，交付时说明顺延
3. `log-only-no-source-page` 先查 `wiki/log.md` 对应条目、`wiki/index.md` 与搜索
   `wiki/`；确认页面确实缺失（非改名 / 归档）后按 untracked 走新建
4. 新建 source 页（页面规格见[章节](page-templates.md#source资料页)；slug 默认
   来自 raw 文件名）。命令模板：

   ```bash
   llmw wiki --path=<root> write new --type=source --slug=<s> --title=<t> --sources=raw/<p> --description=<d> --tags=<g>
   ```

5. 发现矛盾走[章节](page-templates.md#矛盾处理)；entity / concept 先搜索既有页，能追加
   参考来源就不新建，建页与追加阈值见
   [章节](page-templates.md#生命周期与归档)
6. 新建 entity / concept 页后回看既有 source 页，补上应指向新页的交叉引用
7. **所有正文编辑（含第 6 步的交叉引用追加）全部完成后**，对本批改过正文的每页跑
   `llmw wiki --path="$LLM_WIKI_ROOT" write touch <page>`
8. 逐页跑 `llmw wiki --path="$LLM_WIKI_ROOT" write index add <page>`
9. 写 log：单份用 `llmw wiki --path="$LLM_WIKI_ROOT" write log --op=ingest --title="<title>" --raw="raw/<path>"`；
   3 份及以上用 `llmw wiki --path="$LLM_WIKI_ROOT" write log --op=ingest --bulk --topic="<主题>" --count=<N>` 只记
   一条。external 目录源不传 `--raw`（该 flag 只接受文件）

## 验证

1. 重跑 `llmw wiki --path="$LLM_WIKI_ROOT" ingest-diff --check-stale --json`：本次范围内、该命令
   可发现的文件不再待处理。顺延项与非文本素材的处理结果在交付说明列明
2. 跑 `llmw wiki --path="$LLM_WIKI_ROOT" lint --severity=error`：本次新建 / 编辑的页面
   不引入 error 级 finding（既有 finding 不要求本次修完，在交付说明列明）
