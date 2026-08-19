---
name: wiki-spec-0-11-agents-md-ssot
description: wiki/workspace 纪律文件 AGENTS.md SSOT + CLAUDE.md 薄壳；两 spec 对称设计，改 SSOT 引用要同步两 skill
metadata:
  type: project
---

wiki-spec 0.11.0 + workspace-spec 0.4.0 起：wiki / workspace 产物的纪律文件以
`<root>/AGENTS.md` 为单一真源（工具无关 SSOT），`<root>/CLAUDE.md` 为 `@AGENTS.md` 薄壳
（仅供特定 agent 自动加载）。

**关键决策**：

- `@import`（`@MEMORY/MEMORY.md` / `@scripts/SCRIPTS.md`）写在 **AGENTS.md 内**，不进薄壳
  （最坏当显式指针 + orient ritual 显式 Read 兜底）
- 版本号在 **AGENTS.md**（wiki §八 / workspace §六），薄壳不持版本——
  `lint_wiki.py::parse_spec_version` 优先 AGENTS.md、fallback CLAUDE.md（兼容老 wiki）
- `lint_wiki.py` 有 `claudemd-not-thinshell` legacy pattern + `claudemd-to-agents-md-split`
  migrate action（老 CLAUDE.md SSOT → AGENTS.md + 薄壳）；workspace 侧无 lint 脚本，迁移靠 CLI
- 模板各拆两份：`agents-md-template.md`（SSOT）+ `claude-md-template.md`（薄壳，≤ 30 行）

**Why:** agent 中立性——`CLAUDE.md` 自动加载 + `@import` 递归展开绑死特定 agent，Codex / Gemini CLI
等维护时"索引会话常驻"收益消失。AGENTS.md SSOT + 薄壳后一套真源、双工具共存。

**How to apply:** 改 wiki-spec 或 workspace-spec 的 SSOT 文件引用时，两 spec 是**对称设计**
（wiki-spec §2 ↔ workspace-spec §4；模板 agents-md/claude-md 各两份；canonical/fixtures 各一套）——
改一处要查另一处 + 两 SKILL.md + 模板 + canonical/fixtures 同步。`<wiki>/CLAUDE.md` 类引用现指薄壳，
SSOT 语义一律 `AGENTS.md`；workspace skill 读 wiki 时读 `<wiki>/AGENTS.md`。
关联 [[wiki-workspace-spec-type-coupling]]（type enum 耦合）。