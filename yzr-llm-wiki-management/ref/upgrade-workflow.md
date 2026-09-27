# Upgrade（升级 wiki format）详细流程

**优先级裁定**：边界与纪律以本文档 + wiki 根 `AGENTS.md` 为准；每条动作的具体改法与执行
顺序以 lint plan 自带的 `agent_rules[]` + 各 action 说明为准（CLI 输出真源，本文不重述，重述必
漂移）。版本钉在 `<wiki-root>/AGENTS.md` 末尾"当前配置"表的 `Wiki Format 版本` 字段；
breaking 变更的语义合并规则见 [章节](#语义合并规则)；版本演进叙事看 git log

## 职责切分（**关键**：三方分工）

- **CLI `llmw wiki upgrade`（骨架修复者）**：修骨架（四类所有权，canonical 见 wiki 根
  `AGENTS.md`"骨架所有权四分表"）+ legacy paths 移动；`render` / `gitignore-block` 类 diff
  需 `--yes`，否则停于 `blocked_drift`
- **lint plan（`--check-version --apply --json`）**：stdout 输出 `upgrade_plan`，**只输出
  plan、不落盘**，改动由 agent 用 Edit/Write 落
- **agent 职责**：（1）drift 裁定（Step 3） （2）按 plan 落 fixtures 修复（Step 4）
  （3）[章节](#语义合并规则) 语义合并
- **升级期不走 `llmw wiki write`**（机械写命令只认识当前形态）；**不**追加 log 条目（升级
  不是 wiki 操作事件）

## 流程（agent 驱动，5 步）

1. **操作前置**：跑 orient ritual（按 [章节](../SKILL.md#执行原则) 四件套）

2. **dry-run 看骨架计划**：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade
   ```

   默认 dry-run。**将被丢弃的自定义 `##` 段在此以 `dropped_sections` 直接列出，这是
   `--apply` 前唯一的可见时机**；先看计划再决定 `--apply`

3. **裁定 drift**（仅 `render` / `gitignore-block` 类 diff 触发）：`--apply` 不加 `--yes`
   遇这类 diff 即进 `blocked_drift`。**可直接 `--apply --yes`，当且仅当两条同时成立**：

   - (a) `dropped_sections` 为空
   - (b) diff 删除侧每行都出自钉定版本的模板渲染，重建该渲染逐行比对（模板取自 llmw 仓
     git 历史，`git log -S'<钉定版本>' -- llmw/__init__.py` 定位 commit）；任一行对不上
     即不成立

   任一不满足 → 停，附归因结论呈用户裁定，按裁定重跑；自行放行的，交付说明注明判据已核

4. **查 fixtures 不合规 + 按 plan 修复**（lint 侧）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   - 报告 `needs_upgrade` / fixtures 不合规项
   - 版本行缺失 / 无法解析（`wiki-format-version-unparsed`）→ 跑 `upgrade --apply` 恢复
     版本钉；wiki 版本比 llmw 支持的新（`-ahead`）→ 不动 wiki，见 [章节](#边界)
   - 有 fixtures 现场 → `--apply --json` 拿 `upgrade_plan`，按 plan 自带规则用
     Edit 落

5. **验证**：重跑以下两条命令（upgrade 幂等；**不**带 `--yes`——防 drift 再现被静默放行）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --apply --json
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   按终态处置：

   - `done` + `needs_upgrade == false` → 告知用户完成
   - `blocked_drift` → 回第 3 步裁定
   - `done_with_residue` → 逐项读 `residue[]` 的 `note`（处置建议自带）与用户裁定
   - `verify_failed` → 按 `verified.failures[]` 修完重跑（幂等）
   - lint 侧仍有 fixtures 不合规 → 报告 + 转人工

**不**调用 ingest / query（保持职责单一）

## 边界

- **不**删除 wiki 内容（即便某 source 页的 raw 已不存在）：用 `archived: true` 替代
- **不**手改 `wiki/log.md` / `wiki/index.md` 的 frontmatter：骨架键缺失只按 fixtures plan
  （`fixtures-fix-skeleton`）补齐
- **不**手改 `AGENTS.md`（byte-owned）：版本钉与骨架由
  `llmw wiki upgrade --apply` 重渲染落地
- **wiki 版本比 llmw 支持版本新**（`-ahead`）：**不**阻断、**不**改 wiki
- 其余边界以 wiki 根 `AGENTS.md` 为准（raw 只读等全局纪律）

## 语义合并规则

CLI 不替代语义判断：本节定义 **wiki/index.md 跨条目的语义合并**

**wiki/index.md 条目合并**：

- 同 `<relative-path>` link 但多条目出现 → 留信息最完整的一条，余删。优先级：
  `✓ reviewed <date>` badge 最新 > 有 `description` 摘要 > `updated` 最新
- 同 `<title>` 但不同 `<relative-path>` → lint 报 `duplicate-title`，**转人工裁定**：是
  entity 重命名（保留新路径，老条目信息并入后删）还是概念拆页（重命名其一）
- 老 wiki 缺标准类别 → 缺失 H2 由 fixtures plan（`fixtures-fix-skeleton`）补齐（缺哪些类别
  见 plan `expected`）；agent 在新 H2 下加一行 `<!-- agent: TODO 归类旧页 -->` 占位提醒归类

**wiki/log.md 升级期不改**：不合并 / 不截断 / 不改格式，原样保留（超过保留上限也不在
升级期截断）；仅新增行不合规时修
