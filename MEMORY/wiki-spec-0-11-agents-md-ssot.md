---
name: wiki-spec-0-11-agents-md-ssot
description: wiki/workspace 纪律文件从 CLAUDE.md SSOT 改 AGENTS.md SSOT + CLAUDE.md 薄壳（0.11.0/0.4.0），套用 yzr-multi-agent-context 方法；两 spec 对称，改 SSOT 引用要同步两 skill
metadata:
  type: project
---

wiki-spec 0.11.0 + workspace-spec 0.4.0（2026-07-04）：wiki 产物与 workspace 产物的纪律文件从
`<root>/CLAUDE.md` 作单一真源，改为 `<root>/AGENTS.md`（工具无关 SSOT）+ `<root>/CLAUDE.md`
（`@AGENTS.md` 薄壳，仅供该 agent 自动加载）。套用 `yzr-multi-agent-context` skill 的方法
（该 skill 自身声明"不处理被拷贝的产物文件"——这里是**借其方法**到 wiki/workspace 产物这个它
不覆盖的场景，不是调用它）。

**关键决策**：

- `@import`（`@MEMORY/MEMORY.md` / `@scripts/SCRIPTS.md`）写在 **AGENTS.md 内**，不进薄壳
  （ssot R2：两边都能加载——agent 经薄壳 `@AGENTS.md` 递归展开，其他 agent 能否展开取决于实现，
  最坏当显式指针 + orient ritual 显式 Read 兜底）
- 版本号（`wiki_spec_version` / `workspace_spec_version`）在 **AGENTS.md**（wiki §八 / workspace §六），
  薄壳不持版本——`lint_wiki.py::parse_spec_version` 优先 AGENTS.md、fallback CLAUDE.md（兼容老 wiki）
- `lint_wiki.py` 新增 `claudemd-not-thinshell` legacy pattern（CLAUDE.md 行数 > 30 且无 `@AGENTS.md`）+
  `claudemd-to-agents-md-split` migrate action（老 CLAUDE.md SSOT → AGENTS.md + 薄壳）
- workspace 侧无 lint 脚本，老 workspace 迁移靠 workspace CLI（对齐其现有"靠 CLI"风格）
- 模板各拆两份：`agents-md-template.md`（SSOT）+ `claude-md-template.md`（薄壳，≤ 30 行）

**Why:** agent 中立性审计发现 wiki/workspace 产物的纪律机制绑死特定 agent（`CLAUDE.md` 自动加载 +
`@import` 递归展开），Codex / Gemini CLI 等其他 agent 维护时"索引会话常驻"收益消失，且 skill 既未声明
特定 agent 专属、也未提供跨 agent 路径。改 AGENTS.md SSOT + 薄壳后，一套真源、agent（薄壳加载 +
直接读 `AGENTS.md`）双工具共存——产物内容本来就几乎全工具无关（§纪律正文），只有顶部读取机制段 +
`@import` 是特定 agent 特有。

**How to apply:** 改 wiki-spec 或 workspace-spec 的 SSOT 文件引用时，两 spec 是**对称设计**
（wiki-spec §2 ↔ workspace-spec §4；模板 agents-md-template/claude-md-template 各两份；canonical/
fixtures 各一套）——改一处要查另一处 + 两 SKILL.md + 模板 + canonical/fixtures 同步。`<wiki>/CLAUDE.md`
类引用现在指薄壳，SSOT 语义一律 `AGENTS.md`；`<workspace>` skill 读 wiki 时读 `<wiki>/AGENTS.md`。
关联 [[wiki-workspace-spec-type-coupling]]（type enum 耦合）、[[skill-source-vs-runtime-vendor]]、
[[memory-synced-to-skill-source]]（本决策的行为层已落 wiki-spec/workspace-spec/SKILL.md，本条只记为什么 + 耦合提醒）。