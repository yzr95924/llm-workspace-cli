# Migrate（升级 wiki spec）详细流程

> 本文件从 `SKILL.md` §5 Migrate 整段下沉而来——主 SKILL.md 留 pointer 即可，
> 详细流程按需 Read 本文件。**迁移依据的唯一 SSOT = lint plan 的 `actions[]`
> （自带 `remove` / `add_or_modify` / `to_action`）+ 本文件 §六 语义合并规则**——
> 今后任何 breaking 变更的迁移指令必须落本文件 §六，不再另设历史档案；
> 版本演进叙事看 git log。

## 触发

用户说"升级 wiki / 迁移 / 检查 wiki 版本 / 老格式 / spec 升级 / 是否需要
reformat"；或 `lint_wiki.py` 报告 `legacy-confidence-field` 等迁移期 warn。

## 为什么需要这一步

[`wiki-spec.md` §10](wiki-spec.md#10-版本钉死) 规定每个 wiki 仓在
`<wiki-root>/AGENTS.md` §八 钉一份 `Wiki Spec 版本`（CLI init 时从 SKILL 仓
`metadata.wiki_spec_version` 镜像）。spec 演进时，老 wiki 会**有意识地保留**部分旧字段（如 `confidence`）——避免一刀切破坏用户沉淀的内容。
本节定义**检测 + 自动修复**的 workflow：让用户/agent 对着一份"按 spec 升级的清单"逐项
把 wiki 推到与 SKILL 仓一致的格式。

## 职责切分（**关键**——避免与 ingest / lint 混淆）

- **脚本**（`scripts/lint_wiki.py --check-version`）= 探测器。只扫不修，输出报告 / `--apply`
  时把 migration plan 以 JSON 输出到 stdout，**不**改任何 wiki 内容 / **不**落盘
- **agent**（本节定义）= 修复者。按 stdout 返回的 migration plan（`--apply --json` 的
  `report.migration_plan`）+ [`migrate-workflow.md`](migrate-workflow.md)（§六 语义合并
  规则）用 Edit/Write 改 frontmatter / 移文件 / 补索引 / 改 AGENTS.md §八
- **迁移期不走 `wiki_write.py`**——迁移 = 格式流动期，机械写命令只认识当前形态
  （准入规则例外，见 SKILL.md §设计决策「机械 vs 判断」）
- **迁移依据 SSOT** = plan `actions[]`（`remove` / `add_or_modify` / `to_action` 自含）
  与 本文件 §六（语义合并规则）——不另设历史档案；agent 与脚本都引用
- **不**追加 log 条目——迁移是脚本运行，不是 wiki 操作事件（与 `--migrate-confidence` 一致）

## 流程（agent 驱动，与 SKILL.md §1-§4 风格一致）

1. **操作前置**：跑 orient ritual（AGENTS.md + `wiki/index.md` + `wiki/log.md` 最近 ~30 行）
2. **跑探测**：

   ```bash
   python3 scripts/lint_wiki.py "$LLM_WIKI_ROOT" --check-version
   ```

   - 解析 `<wiki-root>/AGENTS.md` §八 "Wiki Spec 版本"——拿到 `current_spec`
   - 与 SKILL 仓 `metadata.wiki_spec_version`（`scripts/lint_wiki.py` 顶部常量
     `CURRENT_WIKI_SPEC`）比对：相等 / 老 / 新
   - 扫已知 legacy 现场：老字段（`confidence`）+ 其它受 spec 演进影响的内容（legacy
     pattern 清单见 `scripts/lint_wiki.py` 的 `LEGACY_PATTERN_KEYS`，修复语义由
     plan `actions[]` 的 `to_action` / `remove` / `add_or_modify` 字段自含）
     - 退役 `type` 值（`type: memory`）
   - 标记冲突页（同时含老字段与新字段）→ `conflicts[]`，**agent 不覆盖**
3. **dry-run 报告**（默认必走）：
   - 按 legacy pattern 分组列"哪些文件需改、依据 plan.actions[] 的 rule_ref 与
     remove/add 字段"
   - 冲突页单独标红，**绝不自动覆盖**——等用户裁定
   - 询问用户：应用全部 / 部分应用 / 仅看清单
4. **生成 plan**（用户同意应用时）—— **不落盘**，stdout 输出：

   ```bash
   python3 scripts/lint_wiki.py "$LLM_WIKI_ROOT" --check-version --apply --json
   ```

   plan 随 **stdout JSON** 返回（`report.migration_plan`），agent 在**内存**里持有——
   含 `actions[]`（每个含 file / type / rule_ref / remove / add_or_modify）+
   `skipped_conflicts[]` + `agent_rules[]`。**不落盘**任何中间文件，故无"plan 已存在"
   覆盖问题；中途暂停续跑直接重跑 `--apply`（确定性再生成同一份 plan）。
5. **执行修复**（agent 用 Edit/Write）：
   - 按 `actions[]` 顺序逐项修；每个 action 前打印依据 `rule_ref`
   - `frontmatter-rename`：Edit 改 frontmatter（删老字段、加新字段；**不动 `updated`**）
   - `file-move`：先读源 → 写目标 → 删源
   - `frontmatter-retype`：按 `action.note` 与 `wiki-spec §5.2` 决定具体改法
   - **跳过 `skipped_conflicts[]`**——永不自动覆盖人工决策
6. **同步 `<wiki-root>/AGENTS.md` 到当前模板**（模板渲染比对机制，wiki-spec §10.1）：
   - plan 含 `fixtures-fix-agents-md-resync` 时按其 `to_action` 走 4 步：
     (1) 从旧 AGENTS.md §八 提取 主题 / 创建日期 / CLI 版本（主题 fallback H1）；
     (2) 渲染 [`agents-md-template.md`](agents-md-template.md)——三变量用旧值，
     `{{WIKI_SPEC_VERSION}}` 用 `to_version`；
     (3) diff 旧文件 vs 渲染稿，旧文件**多出的行/段** = 本地定制——逐条列给用户裁定：
     搬 `MEMORY/`（一行事实写 MEMORY.md 索引短条目；含 why 建 `MEMORY/<slug>.md` 完整
     条目 + 索引行）或丢弃；
     (4) Write 渲染稿覆盖 AGENTS.md（**不**做局部 Edit——成长内容仅 §八 四行变量）
   - plan 仅含 `fixtures-fix-agents-version`（正文已与模板同步、只版本行落后）时：
     用 Edit 把 §八 Wiki Spec 版本行改为 `to_version` 即可
   - 这是**迁移本身**的操作，**不**触及 reviewed 戳机制（AGENTS.md 不参与 SKILL.md
     核心原则 §10 的 `reviewed-stale` 兜底）
7. **验证**：重跑 `lint_wiki.py --check-version`：
   - 若 `needs_migration == false` 且无残留 legacy → 告知用户完成
   - 若仍有 → 报告残留 pattern + 转人工
8. **清理临时文件**（验证通过后，保证 wiki 干净）：删升级过程产出的 `*.bak` 备份。
   `.migration-plan.json` **自 step 4 起不再产生**（改 stdout 输出，agent 内存持有），
   wiki 根全程无此文件；`*.bak` 唯一产生点是 anchor 重写备份，已无需回滚，残留无意义且
   `.gitignore` 已忽略。

   ```bash
   # `.bak` 唯一产生点是 raw/external/.symlink-anchor.toml 重写备份（深度 3），maxdepth 必须 ≥ 3；
   # find 默认不 follow symlink，不会顺 raw/external/ 下的外部仓 symlink 扫进巨型代码树
   find "$LLM_WIKI_ROOT" -maxdepth 3 -name '*.bak' -delete
   ```

   > **为何不再提 `.migration-plan.json`**：step 4 起该文件不再落盘，升级全程 wiki 根**无此文件**，
   > 残留 by construction 不可能（无需 `rm`）。`*.bak` 仍可能由 anchor 重写产生，故保留删除。
9. **不**追加 log 条目 / **不**触发 ingest / query / lint（保持职责单一）

## `--json` 联用

把报告 + plan 一起输出 JSON，给 agent 程序化消费（CI / 编排场景）。
默认人读报告（含 `[LEGACY]` / `[CONFLICTS]` 分组 + `[HINT]` 提示加 `--apply`）。

## 边界

- **不**修改 `raw/` 下任何文件（即便用户要求）——延续 SKILL.md 核心原则 §1 的 LLM 只读纪律
- **不**删除 wiki 内容（即便 raw 已不存在 source 页）——用 `archived: true` 替代
- **不**对 MEMORY 索引做"自动补行"以外的改动——MEMORY.md 是 LLM 私有记忆清单
- **不**改 `wiki/log.md` / `wiki/index.md` frontmatter（index 6 键 / log 5 键 reserved，迁移不触及）
- **不**在迁移过程中调用 ingest / query / lint（保持职责单一）
- **冲突页绝不自动覆盖**（已在 step 3 / step 5 双重保险）
- **不**给迁移追加 log 条目——迁移是脚本运行，不是 wiki 操作事件
- **`current_spec > skill_spec`**（wiki 比 SKILL 新）：**不**阻断，告警用户升级 SKILL 仓；
  **不**改 wiki

## fixtures 字段更新清单

> **本节回答"升级时每个约定文件要对齐什么"**——集中一处，避免散落在 SKILL.md / spec 各处。
> 权威信号清单是 `scripts/check_wiki_fixtures.py` 的 `SKELETON_SPECS` + `CHECK_REGISTRY`（数 = SKILL.md `metadata.fixtures_check_count`）；
> 本节只做 agent 视角的分类与指路，**不重抄字段名**（否则三处漂移）。

升级 wiki spec 时，约定文件（fixtures）必须对齐当前 spec 的骨架。`check_wiki_fixtures.py`
读 `references/canonical/` + `references/fixtures/gitignore.txt` 作 SSOT 做字段级骨架比对
（改 fixtures → check 自动跟随）。

### 模板渲染件（整文以模板为准）

| 文件 | 模板源 | per-wiki 变量（迁移时保留旧值） |
| --- | --- | --- |
| `AGENTS.md` | `references/agents-md-template.md` | 主题（H1 + §八）/ 创建日期 / CLI 版本（§八）；`{{WIKI_SPEC_VERSION}}` 用 `to_version` |

→ 升级时：`agents-md-template-sync` 提取 §八 变量渲染模板后**字节比对**；任何不一致
（旧版本残留 / 本地改动）产 `fixtures-fix-agents-md-resync` action，agent 走全量重渲染
（step 6 的 4 步），**不**做局部 Edit。本地定制纪律的归处是 `MEMORY/`——重渲染前逐条
与用户裁定搬移或丢弃。

### 纯骨架件（结构不变，只追加 bullet/段/行）—— 全字段骨架比对

| 文件 | 骨架信号源 | 成长内容（迁移**不动**） |
| --- | --- | --- |
| `.gitignore` | `fixtures/gitignore.txt` | 用户自定义新增规则 |
| `MEMORY/MEMORY.md` | `canonical/memory-index.md` | `## 索引` 下经验条目 |
| `scripts/SCRIPTS.md` | `canonical/scripts.md` | `## 索引` 下脚本段 |
| `wiki/tags.md` | `canonical/tags.md` | tag bullet 列表（tags 无 `## 索引`，直接 bullet） |

→ 升级时：脚本查 H1 + 说明块（`>` 引用）+ `## 索引`（tags 除外）+ `.gitignore` 段结构
（OS/编辑器 + Obsidian + 临时文件 三段齐全，各 ≥1 规则）；缺则产 `fixtures-fix-skeleton`
action，agent 单 Edit 补结构骨架，**不动成长内容**。

### 成长型件（只比"结构必填"，不动成长内容）

| 文件 | 结构必填骨架 | 成长内容（永不触碰） |
| --- | --- | --- |
| `wiki/index.md` | frontmatter 6 键（title/type/okf_version/tags/created/updated）+ H1（`# <topic> Wiki`）+ 说明块 + 5 类别标题 | 类别下 source/entity/concept 条目 |
| `wiki/log.md` | frontmatter 5 键（title/type/tags/created/updated）+ `## [date] op \| title` 行格式 | 历史 log 条目（迁移期不改：不截断 / 不改格式） |

→ 升级时：脚本只比结构骨架（frontmatter 键 + H1 + 行格式）；成长内容由 LLM 按
ingest/query 流程维护，迁移不触及。

### .gitignore 段结构（容忍定制）

`gitignore-init-rules-complete` 只查**段注释齐全 + 每段 ≥1 规则**，不绑死具体规则行——
容忍用户删自己不用的编辑器规则（只用 VSCode 的删 `.idea/`、纯 Linux 的删 `.DS_Store`）。
临时文件段 `*.tmp` / `*.bak` 建议保留（`*.bak` 是 anchor 重写备份的中断保险，升级末尾
step 8 会清）；`.migration-plan.json` 已不再产生（migrate 改 stdout 输出 plan，不落盘），
canonical `fixtures/gitignore.txt` 已移除该行，老 wiki 留着也无害。

### 权威源指针

- 骨架信号定义：`scripts/check_wiki_fixtures.py` 的 `SKELETON_SPECS` + `CHECK_REGISTRY`
- 字节金标准：`references/canonical/*.md`（`.gitignore` 见 `references/fixtures/gitignore.txt`）
- 语义合并（跨条目归并）：见 §六

## 与现有 lint 检查的协同

- 迁移后会**自然清理** `legacy-confidence-field` warn（lint §二.13.C）
- 迁移**不**触及 `reviewed-stale` warn（页面正文未改，仅字段重命名；按 SKILL.md
  核心原则 §10 "LLM 修改页面正文"边界，本操作属于元数据重命名，不算正文修改——但若用户谨慎，
  可在迁移后跑 `lint_wiki.py --severity warn` 让人工审视 reviewed 戳）
- 与 `--migrate-confidence`（单点硬编码迁移）的关系：`--migrate-confidence`
  保留仅供旧用法兼容；新流程一律走 `--check-version --apply`（覆盖其功能 + 范围更广）

## 完整样例

见 [`examples.md`](examples.md)（SKILL.md §参考样例 指向它）。

---

## 六、语义合并规则

> `scripts/lint_wiki.py --check-version --apply` 以 stdout JSON 输出的 migration plan（含 `actions[]`
> 修内容页 frontmatter + `fixtures_actions[]` 修约定文件）走 agent 执行时，**结构性字节合规**
> 由 `scripts/check_wiki_fixtures.py` 扫并产出 `fixtures-fix-*` action；**跨 entry 的语义合并**
> （老字段升级、index 重复条目、多 MEMORY 条目归并、0.16.0 → 0.17.0 anchor 多 entry 合并）
> 由 agent 按本节规则走——脚本不替代语义判断。

### 6.1 frontmatter 字段合并

- `confidence: <v>` 单独存在 → 删 `confidence`；若 `v == high` 则加 `reviewed: true` +
  `reviewed_at: <migrate-day YYYY-MM-DD>`。`<migrate-day>` 取 plan 的
  `generated_at` 字段（lint_wiki.py 在 `--apply` 时生成，随 stdout JSON 输出）
- 同时含 `confidence` + `reviewed` → **`legacy-confidence-conflict`**，转人工裁定，
  永远不进 plan（已在 plan["skipped_conflicts"] 里标红）
- `type: memory` / `type: memory-entry`（MEMORY 扩展类型）→ **保留原样**——
  MEMORY 桶的 `type` 字段两类均合法（spec §5.2）；
  无需迁到 `memory-entry` 也无需删除 `type`
- `subpath:` 字段（已退役的 anchor 字段）→ 走 §6.3 anchor 合并处理，不在本节管

### 6.2 wiki/index.md 条目合并

- **同 `<relative-path>` link 但多条目出现** → 留信息最完整的那一条（按以下优先级）：
  1. 含 `✓ reviewed <date>` badge（最新 reviewed_at）
  2. 含 `description` 摘要字段
  3. `updated` 最新者
  余删
- **同 `<title>` 词但不同 `<relative-path>`** → 标红（`✗ duplicate-title`），转人工裁定——
  是 entity 重命名（保留新路径、合并到老路径）还是概念拆页（重命名其中之一）由人决定
- **新分类（如 0.X 引入第六类 `Comparisons`）→ 老 wiki 无该类时**，在 wiki/index.md 末尾
  按 wiki-spec §3 模板加新类别 H2 + 一行 `<!-- agent: TODO 归类旧页 -->` 占位，提醒人工归类
- **`raw/external/<symlink>` 形式的源条目**——改用 symlink 名（kebab-case）而非
  老 `<source-name>/` 子目录；index.md 里所有 `raw/external/<source-name>/...`
  形式条目同步改为 `raw/external/<symlink>/...`

### 6.3 raw/external anchor 合并（0.16.0 → 0.17.0 TOML 迁移）

anchor 从「每仓一份 `<source-name>/.symlink-anchor.json`（JSON object）」改为「单文件
`external/.symlink-anchor.toml`（TOML `[[entry]]` 数组）」。迁移走 5 步：

1. `find raw/external -name .symlink-anchor.json` 找全部老 anchor
2. 对每个 `<source-name>/.symlink-anchor.json`：
   - 读 JSON 拿 `{target, captured_at, kind, ...git-扩展字段}`
   - 扫 `<source-name>/` 下所有 symlink（每个 symlink = 一条 entry）
3. 对每个 symlink `<name>`：
   - 检查 `raw/external/<name>` 是否被占用（symlink 或目录）；占用 → 标 `✗ conflict` 转
     人工决定改名 / 合并 / 跳过
   - 不冲突 → `mv <source-name>/<name> <name>`（移 symlink 到 `external/` 顶层）
4. 构造 `[[entry]]` 块（含 `symlink` + `target` + `captured_at` + `kind='external-repo'` +
   git 仓时可选 `remote_url`/`branch` 身份字段），追加写到
   `raw/external/.symlink-anchor.toml` 末尾（按 symlink 名字典序排版，便于 git diff）
5. `rm -rf raw/external/<source-name>/` 删整个子目录

**subpath 字段退役**：老 anchor 含 `subpath` 时，先创建两个 symlink——
`<name>` → `target` + `<name>-sub` → `target/<subpath>`，再写两条 entry（subpath 信息
落到 entry 的 `notes` 字段，可选）。

**多仓合并**：若老 wiki 有 N 个 `<source-name>/` 子目录同时迁移，按 symlink 字典序排版
新 anchor 文件——每仓一个 `{symlink, target, captured_at, kind, ...}` 块。

**反模式**：

- **不要**用脚本（`Python json.dumps` / `tomllib.dump`）整文件重写——会丢注释、丢
  字段顺序、跨机器 diff 噪音
- **不要**保留任何 `<source-name>/` 子目录——`symlink-anchor-flat-not-legacy` check
  看到会报 error
- **不要**在保留老 anchor JSON 的同时新建 TOML（两份并存会让 lint 报
  `external-anchor-orphan`）——必须删 JSON 才能写到 TOML 同一份 manifest

### 6.4 MEMORY 经验条目合并

- **两条 MEMORY entries 描述同一 case**（`grep` / 关键词检索可判定）→ 留更新日期晚者，
  旧 entry 文末追加一行 `# superseded by <new-slug>`，**不**删除（踩坑记录沉淀价值大）
- **或合并为一条多 bullet 形式**（`- 原因: ... \n - 解法: ... \n - 验证: ...`）——LLM
  按上下文长度 / 复用价值选；短经验优先合并，长经验（> 30 行）优先 supersede
- **索引同步**——无论是 supersede 还是合并，**必须**同步更新 `MEMORY/MEMORY.md` 索引
  一行（合并后删旧 slug 行，加合并后的新行；supersede 后旧 slug 行保留但加 supersede 提示）

### 6.5 wiki/log.md 迁移期不改（不合并 / 不截断）

- 迁移期 log **不**合并 / **不**截断 / **不**改格式——保持现状原样搬过来（即使条目数 >
  `LOG_RETENTION_LIMIT` 也不在迁移期截断；截断是日常运行期行为，见 wiki-spec §4.1）
- 唯一例外：0.16.0- 老 wiki 在 CLI 红线贯彻时 log 含 legacy `git init` 之类无效行——
  保留不修，lint 不报（log-truncation / log-format 都不查 legacy git 行）
- `fixtures-fix-log-format` action 仅当 **新增** 行不合规时落，迁移期**不变更 history**

### 6.6 决策树（脚本 vs LLM 合并）

| 场景 | 工具 |
|---|---|
| 结构性字节缺失（`.gitignore` 旧规则 / `MEMORY.md` 含 frontmatter） | 脚本 → `fixtures-fix-*` action；LLM 用 Edit 落 |
| 跨多 entry 语义归并（`subpath` 拆多 symlink / 重复 MEMORY 合并） | 脚本只 plan；LLM 走 §6.3 / §6.4 规则用 Edit/Write 落 |
| 冲突页（老 + 新字段共存，如 `confidence` + `reviewed`） | 转人工裁定 — 不进 plan；plan["skipped_conflicts"] 标红 |
| log 类（历史 log 修订） | **不**动 — lint 永远不报 log 字段 |
| 子目录 → 扁平（0.17.0 anchor 翻新） | 脚本只报 `symlink-anchor-flat-not-legacy`；LLM 走 §6.3 五步迁移 |

**判定经验**：看完 plan["actions"] + plan["fixtures_actions"] 之后——
若 actions 数量 > 50 或含 ≥ 3 条 `fixtures-fix-anchor-*`，agent 必须先 Read 本文件 §六
走"多步迁移"流程；反之直接顺序 Edit。
