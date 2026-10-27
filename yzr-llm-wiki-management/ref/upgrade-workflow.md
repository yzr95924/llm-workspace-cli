# Upgrade（升级 wiki format）详细流程

**优先级裁定**：边界与纪律以本文档 + wiki 根 `AGENTS.md` 为准；每条动作的具体
改法与执行顺序以 lint plan 自带的 `agent_rules[]` + 各 action 说明为准（CLI 输出
真源，本文不重述，重述必漂移）。格式版本以 `<wiki-root>/AGENTS.md` 当前配置表的
`Wiki Format 版本` 行为准；breaking 变更的语义合并见[章节](#语义合并规则)

## 职责切分（**关键**：三方分工）

- **CLI `llmw wiki upgrade`**：修骨架（四类所有权，清单以 wiki 根 `AGENTS.md`
  的骨架所有权一节为准）+ legacy paths 移动；`render` / `gitignore-block`
  类 diff 需 `--yes`，否则停于 `blocked_drift`
- **lint plan（`llmw wiki lint --check-version --apply --json`）**：stdout 输出
  `upgrade_plan`，**只输出 plan、不落盘**，改动由 agent 编辑文件落地
- **agent 职责**：按流程裁定 drift、按 plan 落 fixtures 修复、按
  [章节](#语义合并规则)做语义合并
- **升级期不走 `llmw wiki write`**（机械写命令只认识当前形态）；`wiki/log.md`
  的处理见[章节](#边界)

## 流程（agent 驱动）

1. **操作前置**：读完 wiki 根三份文档（`AGENTS.md`、`wiki/index.md`、`wiki/log.md`）

2. **dry-run 看骨架计划**：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --json
   ```

   默认 dry-run。**将被丢弃的自定义 `##` 段在此以 `dropped_sections` 直接列出，
   这是 `--apply` 前唯一的可见时机**；先看计划再决定 `--apply`

3. **裁定 drift**（仅 `render` / `gitignore-block` 类 diff 触发）：`--apply` 不加
   `--yes` 遇这类 diff 即进 `blocked_drift`。**可直接 `--apply --yes`，当且仅当
   三条同时成立**：

   - (a) `dropped_sections` 为空
   - (b) `AGENTS.md` 未被手改：读 dry-run / `blocked_drift` 的 JSON 输出
     `agents_md_pristine`（三态只裁定它）：`true` → 成立；`false` → 疑似手改，
     停呈用户裁定；`null` → 问用户，答未改视同成立，无法确认视同不成立
   - (c) 计划不含 `gitignore-block` diff：该 diff 不适用三态，无论单独出现还是
     与 `render` 并存，其完整 diff 一律呈用户裁定

   任一不满足 → 停，附归因结论呈用户裁定，按裁定重跑；三条成立而自行
   `--apply --yes` 的，交付说明注明判据已核

4. **查 fixtures 不合规 + 按 plan 修复**（lint 侧）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   - 报告 `needs_upgrade` / fixtures 不合规项
   - 版本行缺失 / 无法解析（`wiki-format-version-unparsed`）→ 跑
     `upgrade --apply` 恢复版本行；wiki 版本比 llmw 支持的新（`-ahead`）→
     不动 wiki，见[章节](#边界)
   - 有 fixtures 不合规 → 重跑上条命令加 `--apply --json` 拿 `upgrade_plan`，
     按 plan 自带规则编辑文件落地

5. **验证**：重跑以下两条命令（upgrade 幂等；**不**带 `--yes`，防 drift 再现被
   静默放行）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --apply --json
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   按终态处置：

   - `done` + `needs_upgrade == false` → 告知用户完成
   - `blocked_drift` → 回到裁定 drift 一步
   - `done_with_residue` → 逐项读 `residue[]` 的 `note`（处置建议自带）与用户裁定
   - `verify_failed` → 按 `verified.failures[]` 修完重跑（幂等）
   - lint 侧仍有 fixtures 不合规 → 报告 + 转人工

**不**调用 ingest / query（保持职责单一）

## 边界

- **不**删除 wiki 内容（即便某 source 页的 raw 已不存在）：加 `archived: true` 并移出
  index；lint 不再要求归档页入 index 或 raw 仍存在
  替代
- **不**手改 `wiki/log.md` / `wiki/index.md` 的 frontmatter：骨架键缺失只按
  fixtures plan（`fixtures-fix-skeleton`）补齐
- **不**手改 `AGENTS.md`（byte-owned）：版本行与骨架由
  `llmw wiki upgrade --apply` 重渲染落地
- **wiki 版本比 llmw 支持版本新**（`-ahead`）：**不**阻断、**不**改 wiki
- `wiki/log.md` 升级期原样保留：不追加条目（升级不是 wiki 操作事件）、不合并不
  截断不改格式（超过保留上限也不在升级期截断）；仅新增行不合规时修
- 其余边界以 wiki 根 `AGENTS.md` 为准（raw 只读等全局纪律）

## 语义合并规则

CLI 不替代语义判断，以下是 wiki/index.md 跨条目合并规则：

- 同 `<relative-path>` link 但多条目出现 → 留信息最完整的一条，余删。优先级：
  `✓ reviewed <date>` 标识最新 > 有 `description` 摘要 > `updated` 最新
- 同 `<title>` 但不同 `<relative-path>` → lint 报 `duplicate-title`，**转人工
  裁定**：是 entity 重命名（保留新路径，老条目信息并入后删）还是概念拆页
  （重命名其一）
- 老 wiki 缺标准类别 → 缺失 H2 由 fixtures plan（`fixtures-fix-skeleton`）补齐
  （缺哪些类别见 plan `expected`）；agent 在新 H2 下加一行
  `<!-- agent: TODO 归类旧页 -->` 占位提醒归类
