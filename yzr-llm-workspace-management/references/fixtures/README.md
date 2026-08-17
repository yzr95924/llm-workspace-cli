# Fixtures

workspace CLI init 时落盘的 `<workspace>/MEMORY/MEMORY.md` 的**字面量金标准**。与
`yzr-llm-wiki-management` SKILL.md 的 fixtures/canonical 机制同构
（兄弟 skill，同一套字节金标准约定）。

## 范围

| fixture | CLI 何时生成 | 后续谁维护 |
| --- | --- | --- |
| `memory-index.txt` | init 时刻 | **skill**（追加跨 wiki 经验到 `MEMORY/` + 同步 `MEMORY.md` 索引） |

**不在 fixture 范围**：

- `AGENTS.md`（SSOT）+ `CLAUDE.md`（薄壳）——有 `{{WORKSPACE_DISPLAY_NAME}}` 等占位符，走
  `../scripts/check_workspace_fixtures.py` 的模板渲染字节比对（`agents-md-template-sync` /
  `claude-md-template-sync`，0.7.0+；模板在 `../workspace-agents-md-template.md` +
  `../workspace-claude-md-template.md`），与 wiki 的 `agents-md-template.md` / `claude-md-template.md` 同（占位符模板不进 fixtures）
- `workspace.toml` / CLI 内部配置 toml / `.gitignore`——TOML / gitignore，schema 在 spec
  §2 / §3 / §10，不走 markdown fixture

## 用法

CLI init 时把 `memory-index.txt` **逐字拷贝**为 `<workspace>/MEMORY/MEMORY.md`（无占位符）。字节级
比对：落盘后 `cmp -s <workspace>/MEMORY/MEMORY.md ../canonical/memory-index.md`，不一致 = CLI bug。

> `memory-index.txt` 与 `../canonical/memory-index.md` 内容相同（MEMORY.md 无占位符，两份只是机制上
> 对齐 wiki 的 fixtures/canonical 双份）。

详细 schema + 维护纪律见 [`workspace-spec.md` §9](../workspace-spec.md#9-workspace-memoryskill-维护)。
