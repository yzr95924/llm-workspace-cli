# Upgrade workflow

CLI `llmw wiki upgrade`：修骨架（四类所有权以 wiki 根 `AGENTS.md` 为准）与 legacy
paths；lint plan 只生成方案不落盘；agent 负责 drift 裁定、fixtures 修复与语义合并。
机械动作以 CLI 输出为准，本文只保留裁定规则。升级期不调用 `llmw wiki write`、不追加
log，也不删除 wiki 内容。

## 流程

1. 读 wiki 根 `AGENTS.md`、`wiki/index.md`、`wiki/log.md`
2. Dry-run：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --json
   ```

   先看 `plan[].dropped_sections` 与 diff，再决定是否 apply
3. 有 `render` / `gitignore-block` diff 或 `dropped_sections` 时，`--apply` 不加
   `--yes` 会停在 `blocked_drift`。仅当三条同时成立才可直接 `--apply --yes`：
   - `dropped_sections` 为空
   - `agents_md_pristine` 为 `true`；`false` 呈用户裁定，`null` 问用户
   - 计划不含 `gitignore-block` diff
4. 跑 `llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version`；有 fixtures 不合规时
   加 `--apply --json` 取 `upgrade_plan`，按 `fixtures_actions[].to_action` 与
   `agent_rules` 编辑文件
5. 复跑：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --apply --json
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

6. 按终态收口：`done` 且 `needs_upgrade` 为 false 即完成；`blocked_drift` 回第 3 步；
   `done_with_residue` 逐项读 `residue[].note` 与用户裁定；`verify_failed` 按
   `verified.failures` 修完重跑；lint 仍有 fixtures 不合规则报告并转人工

## 手工迁移

旧实例的 `raw/discussions/` 不自动迁移：目标不存在时由用户执行
`mv raw/discussions discussions`；目标已存在时先合并内容再删旧目录。

## 语义合并

- 同一链接出现多个 index 条目：保留信息最完整的一条，优先 reviewed 标识新、有
  description、updated 新的条目
- 同一 title 出现在多个路径：lint 报 `duplicate-title`，由用户裁定是实体重命名还是
  概念拆页
- 老 wiki 缺标准类别：按 fixtures plan 补 H2，并在新段加
  `<!-- agent: TODO 归类旧页 -->` 提醒后续归类
