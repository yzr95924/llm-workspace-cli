---
name: yzr-llm-wiki-management
description: |
  维护本地 markdown 个人 wiki（raw/ 原始资料 + LLM 维护的 wiki/ 内容页）。
  当用户要求摄取 / 重摄取论文、剪藏、笔记等资料，接入外部代码仓，
  查询 / 总结 / 对比 / 综合 wiki 内容，归档结论，lint 体检或 format 升级时使用；
  在 wiki 根内收到这类消化 / 总结 / 体检请求，即使没提 skill 名也应使用本 skill。
  不适用：云端或团队 wiki（Notion / Confluence / Outline 等）；wiki 注册 / 元数据配置 /
  增删 wiki、session 启停及跨 wiki / workspace 层操作；MEMORY/ 的写入与治理。
---

## 输入与输出

- **输入**：wiki 根 = session cwd；不在根内时读 `$LLM_WIKI_ROOT`；仍定不了就问用户
  wiki 根须含 `AGENTS.md` 与 `wiki_metadata.toml`，否则本 skill 不适用并告知用户。
  根确定后，不读取、搜索或写入其他 wiki
- **输出**：更新 wiki/ 内容页并按写入纪律同步 index / log / tags；query 答案与 lint 报告在会话交付

## 执行原则

- **按操作预读**：ingest、query 归档、lint 修复、upgrade 启动前，读完 wiki 根
  `AGENTS.md`（本 wiki 的纪律与 format 版本）、`wiki/index.md`（有哪些页、归哪些类）、
  `wiki/log.md`（最近约 30 行，避免重复动作）、`scripts/SCRIPTS.md`（wiki 可无
  scripts/；跑自定义脚本前先查其分节契约）。纯读的 query 与 lint 报告只读
  `AGENTS.md` + `wiki/index.md`，lint 要定优先级时再补读 log；
  超过 100 页（经验阈值）的 wiki 加一次 `wiki/` 全域全文搜索，补 index 看不全的页间引用
- **机械操作走 CLI**：写操作走 `llmw wiki write` 系列，格式与滚动窗口截断由 `write` 保证，lint 只兜底带外手改；
  `write` 不支持的形态直接编辑文件。建不建页、怎么综合、矛盾怎么裁，由 agent 判断
- **代码分析**：围绕问题解释代码，不把复述实现细节当作分析；可引用关键函数和变量名支撑结论
- **不自行立规**：不绕开 wiki 根 `AGENTS.md` 与本 skill 另立约定；两处都没提的，先问用户再写
- **不跨 wiki**：一个 wiki 一个主题，不建跨 wiki 交叉引用；跨主题需求告知用户另开 wiki
- **git 收尾建议**：可在流程收尾建议用户 commit，未启用 git 时不提
- **不豁免必做项**：用户说“随便 / 赶时间”时，`tags` 等必填字段与按写入纪律应记的 log 也不能省

## 工作流

按操作类型选择对应文档，读全文后执行

- 摄取 / 重摄取资料：`ref/ingest-workflow.md`；外部代码仓接入：`ref/external-repo.md`
- 查询 / 对比 / 综合：`ref/query-workflow.md`
- 健康检查：`ref/lint-workflow.md`
- format 升级：`ref/upgrade-workflow.md`；lint 报 `wiki-format-version-stale` /
  `wiki-format-version-unparsed` 类 finding 或 fixtures 不合规也走此路
