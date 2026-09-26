---
name: yzr-llm-wiki-management
description: |
  当用户在本地 Markdown 个人 wiki（LLM owns wiki 模式）内工作时使用本 skill——覆盖：摄取
  raw/ 资料（论文 / 剪藏 / 外部代码仓）、查询与跨页综合 / 矛盾协调、结论归档回 wiki、
  孤儿 / 过期摘要 lint、format 升级。
  触发："把这篇论文摄取进 wiki" / "wiki 里有没有 / 总结一下关于 X 的内容" / "把 X 仓库
  纳入 wiki"。只要命中上述意图——即使没提 skill 名，也务必使用本 skill。
  不适用：云端 / 团队 wiki（Notion / Confluence / Outline 等）；wiki 元数据配置、增删
  wiki、session 启停（单条 llmw 命令，直接跑即可）；跨 wiki / workspace 层操作（无专门
  skill，按用户指示处理）；MEMORY/ 的写入与治理（归 yzr-memory-management skill）；cwd 不是
  wiki 根（无 `wiki_metadata.toml` + AGENTS.md 骨架）
metadata:
  author: Zuoru YANG
  category: knowledge-base
  wiki_format_version: 0.44.0
---

# LLM Wiki Management

## 输入与输出

| 方向 | 内容 |
| --- | --- |
| 输入 | wiki 根 = session cwd（否则 `$LLM_WIKI_ROOT` 或问用户）；正文路径相对 wiki 根，`ref/` 相对 skill 目录 |
| 输出 | `wiki/` 内容页（entity / concept / source / comparison / synthesis）+ `wiki/log.md` / `wiki/index.md` / `wiki/tags.md` 条目 |

## 执行原则

### 核心原则

**先对齐现状再动笔（orient ritual，所有操作通用）**——每次 ingest / query / lint 启动前
按序读完四件套，任一未读完不写任何 wiki 内容：

1. **确认 wiki 根 `AGENTS.md` 已在上下文**——拿主题名与「当前配置」表的 `Wiki Format
   版本` 行；MEMORY 全文随其自动加载
2. `Read wiki/index.md`——有哪些页、归哪些类，避免重复创建 / 漏交叉引用
3. `Read wiki/log.md`（最近 ~30 行）——最近活动，避免重复 ingest / 漏归档
4. `scripts/SCRIPTS.md`（随 AGENTS.md 自动加载；wiki 可无 scripts/）——跑 `scripts/`
   自定义脚本前先查其分节契约

100+ 页的 wiki 加一次 `wiki/` 全域 `Grep "<topic>"`——补 index.md 看不全的页间引用

**机械归 CLI，语义归 agent**——写操作正路 = `llmw wiki write` 系列（适用 ingest / query / lint；
upgrade 迁移期豁免，红线见下方 Upgrade 节）：格式 + 滚动窗口截断由 `write` 保证，lint 只兜底带外手改。
建不建页 / 怎么综合 / 矛盾怎么裁是语义判断——没有命令替你判断，也不因用户"随便 / 赶时间"而省略。
**逃生舱**：命令不支持的形态手写 Edit/Write 合法——write 是默认路径不是闸门

### 边界

- **不**绕过 `AGENTS.md` 自创约定——若 AGENTS.md 没说的，**先问用户**再写
- **不**建跨 wiki xref——确有需求告知用户
- 其余边界纪律以 wiki 根 `AGENTS.md` 为准（自动加载，会话常驻）；流程特有反模式见
  [章节](ref/external-repo.md#反模式) / [章节](ref/ingest-workflow.md#反模式)
- **违反字面 = 违反精神**——对 [章节](#核心原则) 与本段纪律做"效果等同"的绕法（如手写
  `Edit` / `Write` 替代 `llmw wiki write` 再声称走了逃生舱）算违反
- 实跑观察：用户说"随便 / 赶时间"时最易合理化省略（漏必填 `tags`、跳 log）——态度不是豁免

## 工作流

### Ingest（摄取新资料）

**触发**："把这篇摄取到 wiki" / `raw/` 有新文件 / 跑 `llmw wiki ingest-diff` 发现未摄取项

**外部代码仓作为语料**（"把 X 仓库纳入 wiki"）：**不**内嵌拷仓，走 symlink 路径——
`llmw wiki external add <target> --name=<n> [--notes=...]`（symlink + anchor 一律经 CLI
落盘）→ `llmw wiki ingest-diff` 扫描；接入决策 / 漂移刷新 / 跨主机重建见
`ref/external-repo.md`（相应操作前必读）

**流程预告**：识别 → 对齐要点 → source 页 → entity / concept 同步 → index / log 簿记 →
commit，全文见 `ref/ingest-workflow.md`（执行前必读）；≥ 3 份 raw 同时摄入走批处理路径——
[章节](ref/ingest-workflow.md#批处理摄取-3-份-raw-同时摄入)

### Query（跨页综合）

**触发**："wiki 里有 X 吗" / "总结 wiki 中关于 Y 的内容" / "对比 A 和 B"

**流程预告**：`index.md` 定位 → 只读相关页（不读 raw）→ `reviewed` / `contested` 采信分级
→ 综合 → 符合条件时询问归档，全文见 `ref/query-workflow.md`（执行前必读）

### Lint（健康检查）

**触发**："lint wiki" / 定期（频率阈值见 [章节](ref/lint-workflow.md#lint-频率)）/ 大型 wiki 主动建议

**流程预告**：`llmw wiki lint`（deterministic）→ agent 半定性 → 报告 + 询问用户先修哪些，
全文见 `ref/lint-workflow.md`（执行前必读）；finding 口径（含义 / severity / 修法）=
`llmw wiki lint --explain=all`；fixtures 一致性归 `llmw wiki check-fixtures`（常规 lint
只在 `--check-version` 时附带）

### Upgrade（升级 wiki format）

**触发**：用户说"升级 wiki / 迁移 / 检查 wiki 版本 / 老格式 / format 升级 / 是否需要
reformat"；或 `llmw wiki lint` 报告 `wiki-format-version-stale` / legacy warn

**红线**：迁移期不走 `llmw wiki write`；**不**追加 log 条目。三方职责、流程与裁定细则见
`ref/upgrade-workflow.md`（执行前必读）

## 参考样例

完整样例（ingest / query / lint / upgrade）见 `ref/examples.md`——按需 Read
