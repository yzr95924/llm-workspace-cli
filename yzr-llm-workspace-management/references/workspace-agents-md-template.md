# {{WORKSPACE_DISPLAY_NAME}} Workspace — LLM 维护守则

> 这是本 workspace 的**纪律配置**——给跨 wiki 工作的 LLM 看的"工作守则"。你（即 LLM）
> 必须在每次跨 wiki 操作前先读这份文件；任何对 workspace 根级文件的写入都必须符合
> 这里规定的边界。
>
> **本文件（`AGENTS.md`）是本 workspace 纪律的单一真源（SSOT）**——工具无关。由 workspace CLI 在初始化时按
> 本 skill 的官方模板拷贝生成（模板与配套工具随 skill 分发，不在本 workspace 内）；后续可由用户编辑，**但**
> 任何与本 skill 的核心原则冲突的修改都视为"非标准配置"，skill 行为不再保证一致。
>
> **关键**：本文件里凡 `@path/to/file` 形式的引用（如 `@MEMORY/MEMORY.md`），都用 Read 工具
> **必须**读取（不是"按需"）——它们与你**当前任务**直接相关。不自动展开 `@import` 的 agent 尤须手动执行，否则漏上下文。
>
> **读取机制（agent 中立）**：维护本 workspace 的 agent 应在每次跨 wiki 操作前读本文件。在 workspace
> 根目录内工作时——经同目录薄壳 `CLAUDE.md`（`@AGENTS.md` 递归展开）自动加载，或被原生读 `AGENTS.md`
> 的 agent 直读。在别处工作时由 skill 经 `$LLMW_WORKSPACE` 按需读取——**不依赖 symlink**，
> 多终端 / 跨项目都能用。（薄壳 `CLAUDE.md` 仅服务于经薄壳加载的 agent，无独立纪律。）
>
> **作用域（scope）声明**：本文件（`AGENTS.md` + 同目录 `CLAUDE.md` 薄壳）**仅约束跨 wiki
> 工作**——即 agent cwd 在 workspace 根目录或外部 cwd 下调用本 skill（跨 wiki 维护工作流）
> 的场景。**当 agent cwd 落到本 workspace 下某个 `<wiki>/` 子目录内、改跑单 wiki 维护时，
> 本文件不应被加载**——该目录的纪律由 `<wiki>/AGENTS.md`
> 接管，特别要警惕 MEMORY scope 边界（workspace `MEMORY/` = 跨 wiki；`<wiki>/MEMORY/` =
> 单 wiki）与 ingest / log 写入归属（wiki 内写 `<wiki>/wiki/` + `<wiki>/wiki/log.md`，
> 而非 workspace 级 `INDEX.md` / `STATS.md`）。不同 agent 的 `@AGENTS.md` 级联行为各异
>（是否自动加载同目录 `CLAUDE.md` / 展开嵌套 `@import` 取决于实现），识别到 cwd 在本 workspace
> 下某个 `<wiki>/` 子目录时应跳过本目录的 `CLAUDE.md` / `AGENTS.md`，避免与
> `<wiki>/AGENTS.md` 的单 wiki 纪律冲突。

@MEMORY/MEMORY.md

## 一、本 workspace 的边界

### workspace 根文件 / 目录的归属

| 路径 | 维护方 | 说明 |
| --- | --- | --- |
| `workspace.toml` | workspace CLI | wiki 注册表 + 结构数据；skill **只读**（迁移例外见 §六） |
| `<CLI 内部配置 *.toml>` | workspace CLI | 模型注册表（含 API key）/ 主机本地运行时等；skill **不读不写**；文件名 / 拆分归 CLI 自由 |
| `.gitignore` | workspace CLI | 排除承载密钥 / 凭据的 CLI 配置等敏感文件（清单见探测器 `gitignore-skeleton`） |
| `AGENTS.md` | **用户**（CLI init 时拷 SSOT 模板） | workspace 纪律 SSOT（工具无关）；skill 只读（迁移例外见 §六） |
| `CLAUDE.md`（薄壳） | **用户**（CLI init 时拷薄壳模板） | `@AGENTS.md`，仅供经薄壳自动加载的 agent（迁移例外同 §六） |
| `INDEX.md` / `STATS.md` | 跨 wiki 维护 agent（本 skill） | workspace 入口文档 + 结构化统计 |
| `LINT.md` | 跨 wiki 维护 agent（本 skill） | 最近一次 workspace lint 报告（快照） |
| `cross_queries/` | 跨 wiki 维护 agent（本 skill） | 跨 wiki 综合答案归档 |
| `MEMORY/` | CLI init 建骨架 + 跨 wiki 维护 agent（本 skill） | 跨 wiki agent 私有记忆 |
| `<wiki-name>/` | workspace CLI + 单 wiki 维护（纪律见各 `<wiki>/AGENTS.md`） | 每个 wiki 是独立子仓 |

### 三层职责切分（与各 wiki 的 AGENTS.md 区分）

- **workspace CLI**：管 `workspace.toml` + CLI 内部配置（模型注册表等 `*.toml`）/ `.gitignore` + 每个 wiki 子仓元数据；
  不写 INDEX/STATS/LINT/MEMORY/cross_queries
- **跨 wiki 维护（本 skill）**：管 INDEX/STATS/LINT/MEMORY/cross_queries + 跨 wiki 编排；
  不写 workspace.toml / CLI 内部配置 / .gitignore / AGENTS.md / CLAUDE.md（迁移例外见 §六）
- **单 wiki 维护**：管各 wiki 的 ingest / query / lint + `<wiki>/MEMORY/`（纪律见各 `<wiki>/AGENTS.md`）

## 二、跨 wiki 约定

### xref 格式

跨 wiki 链接走相对 workspace 根路径，例：

```markdown
[huawei_storage wiki 的 storage-architecture](../huawei_storage_wiki/wiki/concepts/storage-architecture.md)
```

**不用 wikilink，不用绝对路径**。xref 由跨 wiki 维护 agent 的 link 工作流统一维护，
禁止各 wiki 互相对对方 source 页做交叉写入（除非用户明确要求）。

### topic 重叠处理

若两个 wiki topic 部分重叠：

- **不合并**——每个 wiki 是用户精心策划的主题边界
- 在 `<workspace>/MEMORY/` 记一条"重叠 wiki 关联"，方便 query 跨扫
- xref 走单向（不互相编辑对方的 source 页）

### wiki 命名

新 wiki 命名**推荐**纯 kebab-case（如 `llm-inference-opt`）；CLI 允许
`[a-z0-9_-]{1,64}`，但推荐避免下划线。

## 三、查询 / 综合纪律

### query 4 模式判定

跨 wiki 综合查询按 4 模式判定（route / synthesis / compare / local）。**空 INDEX.md 时**：

- 用户说"扫描 / 刷新 INDEX" → **scan**（先建 INDEX，再回答）
- 用户说"总结 / 综合所有 wiki" → **scan + synthesis**（先建 INDEX，再路由）

### good query 必有"是否归档"环节

跨 wiki synthesis 的好答案应问"是否归档到 `<workspace>/cross_queries/<slug>.md`"；
单 wiki 部分的子答案问"是否归档到对应 `<wiki>/wiki/syntheses/<slug>.md`"。

## 四、lint 纪律

跨 wiki 维护的 lint 工作流：

- **workspace 级** deterministic 检查（跨 wiki 重复实体 / 失效链接 / 未注册 wiki 子目录）+ 半定性检查（主题重叠 / tag 体系）
- **单 wiki 级** lint 由各 `<wiki>/AGENTS.md` 定义的单 wiki 维护工作流覆盖，跨 wiki 维护**不重复**

最近一次 lint 报告落 `<workspace>/LINT.md`（快照，每次 lint 覆盖）。

## 五、Memory 纪律

`<workspace>/MEMORY/` 是 LLM agent 的**跨 wiki**私有记忆。**禁止**写单 wiki 观察
（那些归 `<wiki>/MEMORY/`）。

何时写：

- 跨 wiki 的关联（"X 类主题放 A wiki，Y 类放 B wiki"）
- 用户对 workspace 组织的偏好（"我更喜欢按时间线而非主题分 wiki"）
- workspace-wide lint 模式（"最近 N 次 lint 总是报某类问题"）
- 跨 wiki 综合经验（"这类问题需要先 scan 再答"）

何时**不**写：

- 单 wiki 的踩坑 → 归 `<wiki>/MEMORY/`
- 跨 wiki 综合答案本身 → 归 `<workspace>/cross_queries/`
- 一次性观察 → 直接 chat，不写 MEMORY

**条目形式按事实颗粒度选**：

- **完整条目**——需要解释"为什么这么做"或"将来怎么用"（含上下文 / 解决步骤 / 未来如何避免）→
  建 `MEMORY/<slug>.md`（frontmatter 5 必填 + 推荐 `wikis` 数组 + 推荐 `description`）+ 索引行
  `- <slug> — 一句话摘要 → [正文](<slug>.md)`
- **短条目**——纯 reminder / 单一偏好 / 无需 why + how → 索引行直接 `- 一句话事实`，
  不单独建 `.md` 文件
- 两种格式可在同一 `MEMORY/MEMORY.md` 共存；lint `memory-not-indexed` 只兜底
  "有 .md 但未索引"，短条目无 .md 不进该检查

frontmatter 5 必填（`title` / `type` / `created` / `updated` / `tags`，**仅约束完整条目**），
推荐 `wikis` 字段（涉及 wiki 名数组）与 `description`——指 `MEMORY/<slug>.md` 经验条目
（`MEMORY.md` 索引本身无 frontmatter，被本文件 `@MEMORY/MEMORY.md` import 会话常驻）。
**写每条经验后必须同步追加 `MEMORY.md` 索引一行**（按"条目形式"选完整或短格式），
否则下次会话读不到。

## 六、当前配置

> 本表 4 个变量（Workspace 名 / 创建日期 / Workspace Spec 版本 / CLI 版本）是仅有的
> per-workspace 内容——spec 升级重渲染时**保留旧值**（`Workspace Spec 版本` 用迁移目标版本）。
> 本文件特有纪律 / 偏好一律沉淀到 `MEMORY/`（由顶部 `@MEMORY/MEMORY.md` 加载，会话常驻），
> 不写进本文件——否则升级重渲染时丢失。
>
> **迁移例外**：spec 升级时，agent 经用户确认可全量重渲染本文件 + 薄壳 `CLAUDE.md`、
> 补 `.gitignore` 骨架、bump `workspace.toml` 的 `templates_version` 单字段；本地定制先逐条与用户裁定
> 搬 `MEMORY/` 或丢弃。

| 字段 | 值 |
| --- | --- |
| Workspace 名 | {{WORKSPACE_DISPLAY_NAME}} |
| 创建日期 | {{SETUP_DATE}} |
| Workspace 根 | <由 LLMW_WORKSPACE 环境变量或 init 时确定> |
| Workspace Spec 版本 | {{WORKSPACE_SPEC_VERSION}} |
| CLI 版本 | {{CLI_VERSION}} |
