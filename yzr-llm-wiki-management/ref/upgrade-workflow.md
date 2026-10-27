# Upgrade（升级 wiki format）详细流程

边界与纪律以本文和 wiki 根 `AGENTS.md` 为准；每条动作的具体改法与执行顺序以 lint plan
自带的 `agent_rules[]` 与各 action 说明为准（CLI 输出为准，本文不重述）。格式版本以
`<wiki-root>/AGENTS.md` 当前配置表的 `Wiki Format 版本` 行为准；breaking 变更的语义
合并见[章节](#语义合并规则)。

## 职责切分（关键：三方分工）

- CLI `llmw wiki upgrade`：修骨架（四类所有权，清单以 wiki 根 `AGENTS.md` 的骨架所有权
  一节为准）与 legacy paths 移动；`render` / `gitignore-block` 类 diff 或存在将丢弃的
  自定义段时，`--apply` 需 `--yes`，否则停在 `blocked_drift`
- lint plan（`llmw wiki lint --check-version --apply --json`）：在 stdout 输出含
  `upgrade_plan` 的检查报告，只生成 plan、不落盘，改动由 agent 编辑文件落地
- agent：按流程裁定 drift、按 plan 修 fixtures、按[章节](#语义合并规则)做语义合并
- 升级期不走 `llmw wiki write`（机械写命令只认识当前形态）；`wiki/log.md`
  的处理见[章节](#边界)

## 流程（agent 驱动）

1. 操作前置：读完 wiki 根三份文档（`AGENTS.md`、`wiki/index.md`、`wiki/log.md`）

2. dry-run 看骨架计划：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --json
   ```

   默认 dry-run。将被丢弃的自定义 `##` 段在 JSON 的 `plan[].dropped_sections` 与人读输出
   中列出，这是 `--apply` 前唯一的可见时机；先看计划再决定 `--apply`。

3. 裁定 drift（`render` / `gitignore-block` 类 diff 或将丢弃自定义段时触发）：
   `--apply` 不加 `--yes` 遇上述计划即进 `blocked_drift`。可直接 `--apply --yes`，
   当且仅当三条同时成立：

   - `dropped_sections` 为空
   - `AGENTS.md` 未被手改：读 dry-run / `blocked_drift` 的 JSON 输出字段
     `agents_md_pristine`（三态只用于裁定这一个对象）：`true` 成立；`false` 疑似手改，
     停止并呈用户裁定；`null` 问用户，答未改视同成立，无法确认视同不成立
   - 计划不含 `gitignore-block` diff：该 diff 不适用三态，无论单独出现还是与 `render`
     并存，其完整 diff 一律呈用户裁定

   任一不满足即停止，附归因结论呈用户裁定，按裁定重跑。三条成立而自行
   `--apply --yes` 的，交付说明注明判据已核。

4. 查 fixtures 不合规并按 plan 修复（lint 侧）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   - 报告 `needs_upgrade` 与 fixtures 不合规项
   - 版本行缺失或无法解析（`wiki-format-version-unparsed`）时，跑
     `upgrade --apply` 恢复版本行；wiki 版本比 llmw 支持的新（`-ahead`）时
     `upgrade` 拒绝执行，不动 wiki，见[章节](#边界)
   - 有 fixtures 不合规时，重跑上条命令加 `--apply --json` 取 `upgrade_plan`，
     按 plan 自带规则编辑文件落地

5. 验证：重跑以下两条命令（upgrade 幂等；不带 `--yes`，防 drift 再现被静默放行）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade --apply --json
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

   按终态处置：

   - `done` 且 `needs_upgrade` 为 false：告知用户完成
   - `blocked_drift`：回到裁定 drift 一步
   - `done_with_residue`：逐项读 `residue[]` 的 `note`（自带处置建议），与用户裁定
   - `verify_failed`：按 `verified.failures[]` 修完重跑（幂等）
   - lint 侧仍有 fixtures 不合规：报告并转人工

升级流程不调用 ingest / query（保持职责单一）。

## 边界

- 不删除 wiki 内容：即使某 source 页的 raw 已不存在，也只加 `archived: true` 并移出
  index；lint 对归档页不要求入 index，也不要求 raw 仍存在
- 不手改 `wiki/log.md` / `wiki/index.md` 的 frontmatter：骨架键缺失只按
  fixtures plan（`fixtures-fix-skeleton`）补齐
- 不手改 `AGENTS.md`（byte-owned）：版本行与骨架由
  `llmw wiki upgrade --apply` 重渲染落地
- wiki 版本比 llmw 支持版本新（`-ahead`）：lint 只警告，`upgrade`（含 dry-run）拒绝
  执行且不写盘，更新 llmw 后重试
- `wiki/log.md` 升级期只替换文件头说明块，既有 `##` 条目全部保留：不追加条目
  （升级不是 wiki 操作事件）、不合并、不截断（超过保留上限也不在升级期截断）；既有行
  格式不合规时按 fixtures plan 最小修复（保留原日期、op 与标题），合法历史不重写
- 其余边界以 wiki 根 `AGENTS.md` 为准（raw 只读等全局纪律）

## 语义合并规则

CLI 不替代语义判断，以下合并规则由 agent 判断执行：

- 同一 `<relative-path>` 链接出现多个 index 条目：留信息最完整的一条，其余删除。保留
  优先级：`✓ reviewed <date>` 标识最新、有 `description` 摘要、`updated` 最新
- 同一 `<title>` 出现在不同 `<relative-path>`：lint 报 `duplicate-title`，转人工
  裁定是 entity 重命名（保留新路径，老条目信息并入后删）还是概念拆页
  （重命名其一）
- 老 wiki 缺标准类别：缺失 H2 由 fixtures plan（`fixtures-fix-skeleton`）补齐
  （缺哪些类别见 plan `expected`）；agent 在新 H2 下加一行
  `<!-- agent: TODO 归类旧页 -->` 占位提醒归类
