# Upgrade（升级 wiki format）详细流程

> 升级按两个真源分工：
> - **CLI `llmw [wiki] upgrade`**——修复骨架（byte-owned 全量重渲染 / block-owned .gitignore
>   managed 块 / header-owned 换头保 growth / legacy paths 移动 / self-verify / blocked_drift
>   3 终态契约）
> - **lint plan `actions[]`**（内容页 frontmatter legacy，agent 走 Edit/Write）——由
>   `llmw wiki lint --check-version [--apply --json]` 输出；`actions[]` 自含 to_action
>
> 任何 breaking 变更的语义合并规则必须落 §六，不再另设历史档案；版本演进叙事看 git log。

## 触发

用户说"升级 wiki / 迁移 / 检查 wiki 版本 / 老格式 / format 升级 / 是否需要
reformat"；或 `llmw wiki lint` 报告 `wiki-format-version-stale` / legacy warn。

## 为什么需要这一步

每个 wiki 仓在 `<wiki-root>/AGENTS.md` §七 钉一份 `Wiki Format 版本`（CLI init 时从本 skill
`metadata.wiki_format_version` 镜像，单源对齐）。本 workflow 处理 format 演进后的**检测 + 修复**，
老 wiki 有意识保留部分旧字段避免一刀切。

## 职责切分（**关键**——三方分工）

- **CLI `llmw [wiki] upgrade`**（**骨架修复者**）：处理 byte-owned 全量重渲染
  （AGENTS.md / CLAUDE.md）+ header-owned 换头保 growth + `.gitignore` managed 块 + legacy
  paths 移动 + self_verify + blocked_drift 门禁（本地定制 diff 需 `--yes` 确认）。退出 3 终态
  JSON：`dry_run` / `blocked_drift` / `done` / `done_with_residue` / `verify_failed`
- **lint plan `actions[]`**（**内容页 frontmatter legacy**，目前仅注册 `type-memory-value`）：
  由 `llmw wiki lint --check-version --apply --json` stdout 输出；`actions[]` 自含 `to_action`，agent 直接用 Edit/Write 落
- **agent 职责**：① drift 裁定（blocked_drift 时与用户决定本地定制搬 MEMORY/ 还是丢弃）
  ② 内容页 legacy 修复（按 plan `actions[]` 自含 `to_action` 落） ③ §六 语义合并（index 重复 / MEMORY 归并）
- **迁移期不走 `llmw wiki write`**——机械写命令只认识当前形态
- **迁移依据 SSOT**：CLI `plan_resync`（骨架）+ lint plan `actions[]`（内容页）+ §六（语义）
- **不**追加 log 条目——迁移不是 wiki 操作事件

## 流程（agent 驱动，5 步）

1. **操作前置**：跑 orient ritual（AGENTS.md 已自动加载；`wiki/index.md` + `wiki/log.md`
   最近 ~30 行）

2. **跑 dry-run 看骨架计划**：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" upgrade
   ```

   默认 dry-run，输出 plan（含每个文件的 action：`render` / `growth-graft` / `create` /
   `gitignore-block`）。先看计划再决定 `--apply`。

3. **裁定 drift（若 plan 含 `render`/`gitignore-block` 的 diff）**：
   - CLI `--apply`（不加 `--yes`）遇 diff 即进 `blocked_drift`，输出未覆盖的具体 diff
   - agent 逐条对比：本地定制 = AGENTS.md/CLAUDE.md 内**多出模板的行/段**，与用户裁定**搬
     MEMORY/**（一行事实写 MEMORY.md 索引短条目；含 why 建 `MEMORY/<slug>.md` 完整条目）
     或**丢弃**
   - 裁定完 → 重跑 `llmw wiki --path=... upgrade --apply --yes` 落地

4. **查内容页 legacy + 跑修复**（lint 侧）：

   ```bash
   llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version
   ```

    - 报告 `needs_upgrade` / legacy pattern groups（当前仅 `type-memory-value`）
    - 若 legacy 有现场 → `--apply --json` 拿 stdout `actions[]`，agent 按 `to_action` 字段用 Edit 落
    - **跳过 `skipped_conflicts[]`**——永不自动覆盖人工决策

5. **验证**：重跑 `llmw wiki upgrade` + `llmw wiki lint --check-version`：
   - `needs_upgrade == false` 且无残留 legacy + upgrade 退出 `done` → 告知用户完成
   - 仍有残留 → 报告残留 + 转人工

**清理**：验证通过后删 `.bak` 备份（anchor TOML 重写唯一产生点，maxdepth 3 防扫进外部 symlink）：

```bash
find "$LLM_WIKI_ROOT" -maxdepth 3 -name '*.bak' -delete
```

**不**追加 log 条目 / **不**调用 ingest / query（保持职责单一）。

## 边界

- **不**删除 wiki 内容（即便 raw 已不存在 source 页）——用 `archived: true` 替代
- **不**对 MEMORY 索引做"自动补行"以外的改动——MEMORY.md 是 LLM 私有记忆清单
- **不**改 `wiki/log.md` / `wiki/index.md` frontmatter（index 6 键 / log 5 键 reserved，迁移不触及）
- **冲突页绝不自动覆盖**（lint `--apply` 的 `skipped_conflicts[]` 保证）
- **`current_format > skill_format`**（wiki 比 SKILL 新）：**不**阻断，告警用户更新本 skill 安装；
  **不**改 wiki

> 其余边界以 wiki 根 `AGENTS.md` 为准（raw 只读等全局纪律）。

## 样例

见 [`examples.md`](examples.md)（升级场景样例五）。

---

## 六、语义合并规则

> lint plan `actions[]` 自含 `to_action`（内容页 legacy 修复直接用 Edit/Write 落）；
> 本文件 §六 定义**跨 entry 的语义合并**（index 重复条目 / 多 MEMORY 条目归并）——agent 按本节规则走。
> 脚本不替代语义判断。

### 6.1 wiki/index.md 条目合并

- **同 `<relative-path>` link 但多条目出现** → 留信息最完整的那一条（按以下优先级）：
  1. 含 `✓ reviewed <date>` badge（最新 reviewed_at）
  2. 含 `description` 摘要字段
  3. `updated` 最新者
  余删
- **同 `<title>` 词但不同 `<relative-path>`** → 标红（`✗ duplicate-title`），转人工裁定——
  是 entity 重命名（保留新路径、合并到老路径）还是概念拆页（重命名其中之一）由人决定
- **新分类引入（如第六类 `Comparisons`）→ 老 wiki 无该类时**，在 wiki/index.md 末尾
  按 fixture 头部模板加新类别 H2 + 一行 `<!-- agent: TODO 归类旧页 -->` 占位，提醒人工归类

### 6.2 MEMORY 经验条目合并

- **两条 MEMORY entries 描述同一 case**（`grep` / 关键词检索可判定）→ 留更新日期晚者，
  旧 entry 文末追加一行 `# superseded by <new-slug>`，**不**删除（踩坑记录沉淀价值大）
- **或合并为一条多 bullet 形式**（`- 原因: ... \n - 解法: ... \n - 验证: ...`）——LLM
  按上下文长度 / 复用价值选；短经验优先合并，长经验（> 30 行）优先 supersede
- **索引同步**——无论是 supersede 还是合并，**必须**同步更新 `MEMORY/MEMORY.md` 索引
  一行（合并后删旧 slug 行，加合并后的新行；supersede 后旧 slug 行保留但加 supersede 提示）

### 6.3 wiki/log.md 迁移期不改（不合并 / 不截断）

- 迁移期 log **不**合并 / **不**截断 / **不**改格式——保持现状原样搬过来（即使条目数 >
  `LOG_RETENTION_LIMIT` 也不在迁移期截断；截断是日常运行期行为，`llmw wiki write log` 自动生效）
- `fixtures-fix-log-format` action 仅当 **新增** 行不合规时落，迁移期**不变更 history**

### 6.4 决策树（CLI 骨架 / agent 语义的判断边界）

| 场景 | 路径 |
|---|---|
| 骨架一致性（AGENTS.md 模板漂移 / growth 头部 / .gitignore 块 / legacy paths） | CLI `upgrade --apply --yes` 直接落 |
| 内容页 frontmatter legacy（`type-memory-value`） | lint `--check-version --apply --json` 拿 `actions[]`，按 `to_action` 用 Edit 落 |
| 跨多 entry 语义归并（重复 index 条目 / 多 MEMORY 归并） | lint plan / fixtures_checks 报现状，agent 走 §6.1 / §6.2 落 |
| log 类（历史 log 修订） | **不**动 — lint 永远不报 log 字段 |

**判定经验**：`llmw wiki upgrade` 退出 `blocked_drift` 时先裁定本地定制；`done_with_residue`
时逐项处理 `residue[]`；`done` 且 lint `--check-version` 干净即完成。
