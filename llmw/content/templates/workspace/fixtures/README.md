# Fixtures

workspace CLI init 时落盘的 `<workspace>/MEMORY/MEMORY.md` 的**字节金标准**——与
wiki management 侧的 fixtures 机制同构（同仓兄弟包，同一套字节金标准约定）。

## 范围

| fixture | CLI 何时生成 | 后续谁维护 |
| --- | --- | --- |
| `memory-index.txt` | init 时刻 | **skill**（追加跨 wiki 经验到 `MEMORY/` + 同步 `MEMORY.md` 索引） |

**不在 fixture 范围**：

- `AGENTS.md`（SSOT）+ `CLAUDE.md`（薄壳）——有 `{{WORKSPACE_DISPLAY_NAME}}` 等占位符，走
  `llmw check-fixtures` 的模板渲染字节比对（`agents-md-template-sync` /
  `claude-md-template-sync`；模板在 `../workspace-agents-md-template.md` +
  `../workspace-claude-md-template.md`），与 wiki 的 `agents-md-template.md` / `claude-md-template.md` 同（占位符模板不进 fixtures）
- `workspace.toml` / CLI 内部配置 toml / `.gitignore`——TOML / gitignore，schema 由 CLI store 模块承载

## 用法

CLI init 时把 `memory-index.txt` **逐字拷贝**为 `<workspace>/MEMORY/MEMORY.md`（无占位符）。
完整 gate 走 `llmw check-fixtures` 探测器断言（CLI 仓 CI 跑 real `llmw init` 后执行）。

workspace 级文件契约（INDEX/STATS/LINT/cross_queries/MEMORY 格式）见 yzr-llm-workspace-management SKILL.md 附录 A2-A6。