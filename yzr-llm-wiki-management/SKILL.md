---
name: yzr-llm-wiki-management
description: |
  维护本地 Markdown 个人 wiki（raw/ 原始资料 + LLM 维护的 wiki/ 内容页）。
  当用户要求摄取 / 重摄取论文、剪藏、笔记等资料，接入外部代码仓，
  查询 / 总结 / 对比 / 综合 wiki 内容，归档结论，lint 体检或 format 升级时使用；
  在 wiki 根内收到这类消化 / 总结 / 体检请求，即使没提 skill 名也应使用本 skill。
  不适用：云端或团队 wiki（Notion / Confluence / Outline 等）；wiki 注册 / 元数据配置 /
  增删 wiki、session 启停及跨 wiki / workspace 层操作；MEMORY/ 的写入与治理。
---

## 输入与输出

- 输入：wiki 根 = session cwd；不在根内用 `$LLM_WIKI_ROOT`；仍定不了就问用户。
  wiki 根须含 `AGENTS.md` 与 `wiki_metadata.toml`，否则本 skill 不适用并告知用户。
  根确定后，不读取、搜索或写入其他 wiki
- 输出：写 wiki/ 内容页（entity / concept / source / comparison / synthesis）并同步
  index / log / tags 条目，写路径走 `llmw wiki write`；query 答案与 lint 报告本体
  是会话输出，用户认可后才落 wiki

## 执行原则

**先读现状再动笔（写类操作通用）**：ingest、query 归档、lint 修复、upgrade 启动前
按序读完：wiki 根 `AGENTS.md`（主题名与"当前配置"表的 format 版本行）、
`wiki/index.md`（有哪些页、归哪些类）、`wiki/log.md`（最近约 30 行，避免重复动作）、
`scripts/SCRIPTS.md`（wiki 可无 scripts/；跑自定义脚本前先查其分节契约）。
纯读的 query 与 lint 报告只读 `AGENTS.md` + `wiki/index.md`，query 出现归档候选、
lint 要定优先级时再补读 log。100+ 页（经验阈值）的 wiki 加一次 `wiki/` 全域
Grep，补 index 看不全的页间引用

**机械归 CLI，语义归 agent**：写操作正路是 `llmw wiki write` 系列，
格式 + 滚动窗口截断由 `write` 保证，lint 只兜底带外手改。建不建页、怎么综合、
矛盾怎么裁是 agent 的语义判断，没有命令替它判断。仅 `write` 确不支持的形态
才手写 Edit/Write；write 是默认路径，不是闸门

**边界**：

- 不绕过 wiki 根 `AGENTS.md` 与本 skill 自创约定：两处都没提的，先问用户再写
- 不建跨 wiki xref：一个 wiki 一个主题；确有跨主题需求告知用户另开 wiki
- git 操作由用户触发；启用 git 的 wiki 可在流程收尾建议 commit，裸目录树不提
- 用户说"随便 / 赶时间"不豁免必填 `tags` 与 log 步骤，照常走
- 其余纪律（raw 只读、写后必同步、阅读纪律）以 wiki 根 `AGENTS.md` 为准

## 工作流

按操作类型路由，执行前必读对应文档全文；本节只管起步，流程步骤以文档为准

- 摄取新资料：`ref/ingest-workflow.md`；外部代码仓接入走 `ref/external-repo.md`
  （symlink + anchor 经 `llmw wiki external` 落盘，**不**内嵌拷贝仓库）
- 查询 / 对比 / 综合：`ref/query-workflow.md`
- 健康检查：`ref/lint-workflow.md`；finding 口径唯一入口 =
  `llmw wiki lint --explain=all`，本 skill 文本不镜像 severity 清单
- format 升级：`ref/upgrade-workflow.md`；lint 报 `wiki-format-version-stale` /
  `wiki-format-version-unparsed` 类 finding 或 fixtures 不合规也走此路。
  **升级期不走 `llmw wiki write`、不追加 log 条目**
