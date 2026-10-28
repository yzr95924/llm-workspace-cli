---
name: yzr-llm-wiki-management
description: |
  维护本地 markdown 个人 wiki（raw/ 原始资料 + agent 维护的 wiki/ 内容页）。
  当用户要求摄取 / 重摄取论文、剪藏、笔记等资料，接入外部代码仓，
  查询 / 总结 / 对比 / 综合 wiki 内容，归档结论，lint 体检或 format 升级时使用；
  在 wiki 根内收到这类消化 / 总结 / 体检请求，即使没提 skill 名也应使用本 skill。
  不适用：云端或团队 wiki（Notion / Confluence / Outline 等）；wiki 注册 / 元数据配置 /
  增删 wiki、session 启停及跨 wiki / workspace 层操作；MEMORY/ 的写入与治理。
---

## 输入与输出

- **输入**：wiki 根 = session cwd；不在根内时读 `$LLM_WIKI_ROOT`；仍定不了就问用户。
  wiki 根须含 `AGENTS.md` 与 `wiki_metadata.toml`，否则本 skill 不适用并告知用户。
  llmw 内容命令只认 `--path=<wiki 根>`、`--name` 或 `$LLM_WIKI_ROOT`，不按 cwd 推断；
  根未注入 env 时，把示例中的 `--path="$LLM_WIKI_ROOT"` 换成解析出的根路径
- **输出**：写操作更新 wiki/ 内容页，并按 wiki 根 `AGENTS.md` 的写入纪律同步
  index / log / tags；查询答案与 lint 报告在会话内交付

## 执行原则

- **机械操作走 CLI**：内容页、index / log 的常规写操作走 `llmw wiki write` 系列，格式与滚动窗口截断由 `write` 保证，lint 只兜底带外手改；
  `write` 覆盖不了的形态直接编辑文件（anchor 等 CLI 专属对象仍走各自子命令）。建不建页、
  怎么综合、矛盾怎么记，由 agent 判断；裁定归用户
- **不跨 wiki**：wiki 根确定后，不读取、搜索或写入其他 wiki；一个 wiki 一个主题，
  不建跨 wiki 交叉引用；跨主题需求告知用户另开 wiki
- **不自行立规**：不绕开 wiki 根 `AGENTS.md` 与本 skill 另立约定；两处规则冲突时停下问用户，
  都没规定的常规判断不必逐条请示

## 工作流

按操作类型选择对应文档，读全文后执行

- 摄取 / 重摄取资料：`ref/ingest-workflow.md`；外部代码仓接入：`ref/external-repo.md`
- 查询 / 总结 / 对比 / 综合 / 归档结论：`ref/query-workflow.md`
- lint 体检：`ref/lint-workflow.md`
- format 升级：`ref/upgrade-workflow.md`；lint 报 `wiki-format-version-stale` /
  `wiki-format-version-unparsed` 类 finding 或 fixtures 不合规也走此路
