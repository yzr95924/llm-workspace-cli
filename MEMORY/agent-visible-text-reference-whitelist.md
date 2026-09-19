---
name: agent-visible-text-reference-whitelist
description: agent 可见文本（skill 文档 + CLI 指令字段）引 CLI 资产的三类白名单 + 契约文档最小化；gate 面 9/10 双向守护
metadata:
  type: project
---

**Why:** agent 读不到 CLI 包内实现（[[boundary-map]]「单向约束」），所以 skill 文档或 CLI 输出的指令文本里出现包内路径 / 内部符号 = agent 执行不了的指令。2026-09-19 审计实证两侧：skill 文本引 `llmw.content` 包路径（面 9 抓 2 处）；CLI 自己吐的 `to_action` / `rule_ref` 里写 `llmw/content/...`、`external_anchor._REQUIRED_FIELDS`、`包内 fixtures/`（面 10 抓 21 处）。同一次审计还实证**文档重述 CLI 字段词汇必漂移**：`upgrade-workflow.md` 声称 `actions[]` 自含 `to_action`，实际 `to_action` 只在 `fixtures_actions[]`；`actions[]` 的 `frontmatter-retype` 还带自相矛盾的 `remove` / `add_or_modify` 机器字段（照它落会把内容页标成 `memory-entry`，静默骗过 lint——比报错更糟）。

**How to apply:**

- **白名单三类**（唯一可引）：(a) 命令名（`llmw wiki upgrade --apply`）(b) 本次输出自带字段（`expected` / `actual` / `rule_ref`）(c) 实例内可读路径（`wiki/index.md` 头部说明块 / `AGENTS.md` / `MEMORY/MEMORY.md`）。
- **禁四类**：`llmw.` 包路径、`llmw/*` 文件或目录路径、`module.SYMBOL`（第二段含大写）、"包内 <路径>" 俗称。
- **契约文档最小化**：plan / report 自带字段词汇与执行顺序（`agent_rules[]` + 各 action 说明），skill 文档只写 agent 必须感知的（触发 / 分工 / drift 裁定 / 语义合并 / 边界），**不重述** CLI 字段。
- **引名不引值（数值类）**：阈值 / 计数类内部常量（`PAGE_SIZE_THRESHOLD` / `LOG_RETENTION_LIMIT` / `STALE_SUMMARY_DAYS`）文档只写「阈值」+ 数值来源（finding 文本自带 / 实例内可读文件）——agent 需要数值行动时不能靠常量名；版本类常量（`CURRENT_WIKI_FORMAT`）可留名（报告自带对照值）。
- **机械守护**：gate 面 9（skill→CLI，扫 SKILL_MDS backtick span）+ 面 10（CLI→agent 文本，ast 取 `to_action` / `agent_rules` / `note` / `rule_ref` / `expected` / `actual` 六键的值；`desc` / argparse help / `hint` 不扫——CLI 自述与排障诊断）。**方向盲区**：两侧都只查"文本提到 → CLI 有无该字面量"，CLI 新增枚举值而文档没跟上查不出（如 `growth-graft-error`），该类靠人工审计。
- **byte-owned 不手改**：`AGENTS.md` / `CLAUDE.md` 的版本行与骨架一律走 `llmw wiki upgrade --apply` 重渲染；CLI 指令文本不得让 agent 手改（旧 `agent_rules` 曾指示单格 Edit，且只手改过不了 `agents-md-template-sync` 的整文件字节比对）。
