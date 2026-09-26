# Upgrade（升级 wiki format）详细流程

**优先级裁定**：边界与纪律以本文档 + wiki 根 `AGENTS.md` 为准；每条动作的具体改法与执行
顺序以 plan 自带的 `agent_rules[]` + 各 action 说明为准（CLI 输出真源，本文不重述，重述必
漂移）。版本钉在 `<wiki-root>/AGENTS.md` 末尾"当前配置"表的 `Wiki Format 版本` 字段；
breaking 变更的语义合并规则见 [章节](#语义合并规则)；版本演进叙事看 git log

## 职责切分（**关键**：三方分工）

- **CLI `llmw wiki upgrade`（骨架修复者）**：修骨架（四类所有权，canonical 见 wiki 根
  `AGENTS.md`"骨架所有权四分表"）+ legacy paths 移动。**旧文件里新骨架没有的自定义 `##`
  段会被丢弃**：dry-run 以 `dropped_sections` 列出、写盘后记入 `residue[]`；`render` /
  `gitignore-block` 类 diff 需 `--yes`，否则停于 `blocked_drift`。growth 类只换头保条目，
  不算 drift
- **lint plan（`--check-version --apply --json`）**：stdout 输出 `upgrade_plan`，两条并行
  数组（内容页 `actions[]` / 约定文件 `fixtures_actions[]`）；**只输出 plan、不落盘**（与
  `llmw wiki upgrade --apply` 相反，后者写盘），改动由 agent 用 Edit/Write 落；
  `skipped_conflicts[]` 页跳过转人工
- **agent 职责**：(1) drift 裁定（`blocked_drift` 时与用户决定本地定制搬 MEMORY/ 还是丢弃）
  (2) 按 plan 落 legacy / fixtures 修复 (3) [章节](#语义合并规则) 语义合并
- **迁移期不走 `llmw wiki write`**（机械写命令只认识当前形态）；**不**追加 log 条目（迁移
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
   遇这类 diff 即进 `blocked_drift` 并输出具体 diff → agent 逐条对比（本地定制 =
   AGENTS.md / CLAUDE.md 内多出模板渲染稿的行 / 段）→ 与用户裁定**搬 MEMORY/**（一行事实写
   MEMORY.md 索引短条目；含 why 建 `MEMORY/<slug>.md` 完整条目）或**丢弃** → 重跑
   `llmw wiki --path=... upgrade --apply --yes` 落地

4. **查内容页 legacy + 按 plan 修复**（lint 侧）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   - 报告 `needs_upgrade` / legacy pattern groups / fixtures 不合规项
   - 版本行缺失 / 无法解析（`wiki-format-version-unparsed`）→ 跑 `upgrade --apply` 恢复钉版
     （CLI 重渲染 AGENTS.md）；wiki 版本比 llmw 支持的新（`-ahead`）→ 不动 wiki，见
     [章节](#边界)
   - 有 legacy / fixtures 现场 → `--apply --json` 拿 `upgrade_plan`，按 plan 自带规则用
     Edit 落

5. **验证**：重跑第 2、4 步命令，按终态处置：

   - `done` + `needs_upgrade == false` + 无残留 legacy → 告知用户完成
   - `blocked_drift` → 回第 3 步裁定
   - `done_with_residue` → 逐项读 `residue[]` 的 `note`（处置建议自带）与用户裁定；
     `content-page-transform`（解析失败）类转人工
   - `verify_failed` → 按 `verified.failures[]` 修完重跑（幂等）
   - lint 侧仍有 legacy / fixtures 现场 → 报告 + 转人工

**不**调用 ingest / query（保持职责单一）。样例 trace 见 `examples.md` 样例四

## 边界

- **不**删除 wiki 内容（即便 raw 已不存在 source 页）：用 `archived: true` 替代
- **不**改 MEMORY 条目内容：迁移期唯一允许的 `MEMORY.md` 改动是索引行对齐（补缺失行）
- **不**手改 `wiki/log.md` / `wiki/index.md` 的 frontmatter：骨架键缺失只按 fixtures plan
  （`fixtures-fix-skeleton`）补齐
- **不**手改 `AGENTS.md` / `CLAUDE.md`（byte-owned）：版本钉与骨架由
  `llmw wiki upgrade --apply` 重渲染落地
- **wiki 版本比 llmw 支持版本新**（`-ahead`）：**不**阻断、**不**改 wiki，CLI 自带 WARN
  引导升级安装
- 其余边界以 wiki 根 `AGENTS.md` 为准（raw 只读等全局纪律）

## 语义合并规则

CLI 不替代语义判断：本节定义**跨 entry 的语义合并**（index 重复条目 / 多 MEMORY 条目归并）

**wiki/index.md 条目合并**：

- 同 `<relative-path>` link 但多条目出现 → 留信息最完整的一条（优先级：含 `✓ reviewed
  <date>` badge 最新 reviewed_at > 含 `description` 摘要 > `updated` 最新者），余删
- 同 `<title>` 但不同 `<relative-path>` → lint 报 `duplicate-title`，**转人工裁定**：是
  entity 重命名（保留新路径合并到老）还是概念拆页（重命名其一）由人决定
- 老 wiki 缺标准类别 → 缺失 H2 由 fixtures plan（`fixtures-fix-skeleton`）补齐（缺哪些类别
  见 plan `expected`）；agent 在新 H2 下加一行 `<!-- agent: TODO 归类旧页 -->` 占位提醒归类

**MEMORY 经验条目合并**：

- 两条 entries 描述同一 case（grep 可判定）→ 留更新日期晚者，旧 entry 文末追加
  `# superseded by <new-slug>`，**不**删除（踩坑记录沉淀价值大）
- 或合并为一条多 bullet（`- 原因: ... / - 解法: ... / - 验证: ...`），短经验优先合并，
  长经验（> 30 行）优先 supersede
- 无论哪种，**必须**同步 `MEMORY/MEMORY.md` 索引一行：合并后删旧 slug 行加新行；supersede
  后旧 slug 行保留但加 supersede 提示

**wiki/log.md 迁移期不改**：不合并 / 不截断 / 不改格式，原样搬（即使超过日常保留上限也不在
迁移期截断，截断是日常运行期行为，`llmw wiki write log` 自动生效）；仅新增行不合规时修
