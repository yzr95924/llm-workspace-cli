# Workspace Spec（workspace 仓出生形态 + skill 读取契约）

> 本文档约定 workspace 仓的**出生形态骨架** + 各文件的**归属关系**（谁写谁读）+
> **skill 读取契约**（scan / Q&A / migrate 实际读取的字段）+ 安全约束。
>
> **依赖方向（单向）**：`workspace CLI → SKILL`（CLI 运行时读 SKILL 的 fixtures / 模板落盘骨架）。
> SKILL **不反向依赖** CLI 实现——toml（`workspace.toml` / `wiki_metadata.toml` +
> CLI 内部配置 toml）的**字段全集 schema 归 CLI 代码 SSOT**（CLI 是这些文件的唯一写方；
> 字段随 CLI 演进出/入，如簿记 / 模型路由 / session 启动等 config 字段）。
>
> **spec 只承载设计不变量**：CLI 的具体实现形式——命令名、占位符语法 / 渲染机制、版本戳编码格式、
> `.gitignore` 栅栏标记、环境变量名、CLI 源码路径等——一律**不进 spec**（实现方法多样，spec 钉死
> 只会反向限制 CLI 开发）。这些细节的唯一权威是 [`check_workspace_fixtures.py`](../scripts/check_workspace_fixtures.py)
> （可执行契约）+ [`references/fixtures/`](fixtures/)（字节金标准）+ CLI 代码；本 spec 提及时只描述
> 设计意图 + 指向探测器，不复制字节。
>
> **结构合规的可执行真源**是 [`scripts/check_workspace_fixtures.py`](../scripts/check_workspace_fixtures.py)——
> 本 spec 是它的人类可读说明；两者不一致时**以探测器为准**（spec 滞后不构成 CLI 违规；
> 探测器 pass 即合规，fail 即真违规）。
>
> **生命周期归属**：本 spec 只规定 workspace 仓的"出生形态" + 持续维护期各文件的归属。
> workspace 出生后的所有成长（cross-wiki Q&A / xref / lint / 跨 wiki 编排 / 跨 wiki memory）
> 由 [`yzr-llm-workspace-management`](../SKILL.md) skill 在会话内负责。CLI 在 workspace
> 生命周期的两个边界点被调用：
>
> - **init**：创建（按本 spec §1–§4 + §10–§11 落盘）
> - **delete**：删除（带备份）
>
> 其他时刻调 CLI 属"误用"，CLI 应拒绝。

## 目录

- [§1 目录结构](#1-目录结构)
- [§2 workspace.toml](#2-workspacetoml)
- [§3 CLI 内部配置](#3-cli-内部配置)
- [§4 workspace AGENTS.md（SSOT）+ CLAUDE.md（薄壳）](#4-workspace-agentsmdssot-claudemd薄壳)
- [§5 INDEX.md（skill 维护）](#5-indexmdskill-维护)
- [§6 STATS.md（skill 维护）](#6-statsmdskill-维护)
- [§7 cross_queries/（skill 维护，可选）](#7-cross_queriesskill-维护可选)
- [§8 LINT.md（skill 维护，可选）](#8-lintmdskill-维护可选)
- [§9 workspace MEMORY/（skill 维护）](#9-workspace-memoryskill-维护)
- [§10 .gitignore](#10-gitignore)
- [§11 Git 仓（用户外部创建，CLI 不碰）](#11-git-仓用户外部创建cli-不碰)
- [§12 拒绝条件（强约束）](#12-拒绝条件强约束)
- [§13 Frontmatter 字段约定（skill 写 §5–§9 时用）](#13-frontmatter-字段约定skill-写-59-时用)
- [§14 版本钉死](#14-版本钉死)
- [§15 命名约束](#15-命名约束)
- [§16 不在本 spec 范围内](#16-不在本-spec-范围内)
- [§17 升级迁移（skill 维护）](#17-升级迁移skill-维护)
- [附录 A：CLI 实现自检建议](#附录-acli-实现自检建议)

## §1 目录结构

```text
<workspace-root>/
├── .gitignore                      # CLI init 时写（§10）
├── workspace.toml                  # CLI init 时写（§2）；skill 读取契约字段
├── AGENTS.md                       # CLI init 时按 §4 拷 SSOT 模板；用户所有（工具无关纪律）
├── CLAUDE.md                       # CLI init 时按 §4 拷薄壳模板（@AGENTS.md）；供经薄壳加载的 agent
├── INDEX.md                        # skill scan 时建 + 维护（§5）
├── STATS.md                        # skill scan 时建 + 维护（§6）
├── cross_queries/                  # skill 可选建（§7）
├── LINT.md                         # skill lint 时写（§8）
├── MEMORY/                         # CLI init 建空目录 + 写 MEMORY.md 索引（§9）
└── <wiki-name>/                    # 每个 wiki 一个子目录，遵循 wiki-spec §1 目录结构
```

> **CLI 内部配置（open class，不在上树）**：根目录另有若干 CLI 维护的 `*.toml`（当前实现含
> 模型注册表、主机本地运行时配置等；含密 gitignored；skill **不读不写**）——**文件名 / 格式 / 拆分
> 归 CLI 实现自由，spec 不逐一钉名**（CLI 改名 / 增减 / 合并不构成 spec 违规；含密清单由探测器
> `gitignore-skeleton` check 校验，见 §3、§10）。`workspace.toml` 是例外：skill 读取契约字段（§2）。

**workspace 根文件 / 目录的归属**：

| 文件 / 目录 | init 时刻（CLI） | 后续维护方 | 说明 |
| --- | --- | --- | --- |
| `.gitignore` | CLI 写 | CLI（重 init 时覆盖；普通命令不碰） | 排除承载密钥 / 凭据的 CLI 配置等敏感文件（清单见探测器 `gitignore-skeleton`，§10） |
| `workspace.toml` | CLI 写 | **CLI**（wiki 注册表 CRUD） | wiki 注册表 + 结构数据（schema_version / created_at / templates_version）；运行时配置（session 等）归 CLI 内部，skill 不读；skill **不写**（迁移例外见 §17.2） |
| `<CLI 内部配置 *.toml>` | CLI 写 | **CLI** | 模型注册表（含 API key）/ 主机本地运行时等；skill **不读不写**；含密文件必须 gitignore + 权限保护（清单 / 机制见探测器 `gitignore-skeleton` + §3）；**文件名 / 拆分 / schema 归 CLI SSOT，spec 不逐一钉名** |
| `AGENTS.md` | CLI 按 §4 拷 SSOT 模板 | **用户**（schema 是用户的宪法，工具无关 SSOT）；skill **只读**（迁移例外见 §17.2） | workspace 的"宪法"——三层职责切分 + 跨 wiki 约定 |
| `CLAUDE.md`（薄壳） | CLI 按 §4 拷薄壳模板（`@AGENTS.md`） | **用户**；skill **只读**（迁移例外见 §17.2） | 仅供经薄壳自动加载的 agent |
| `INDEX.md` | CLI **不写**（留空） | **skill**（scan / refresh-index） | workspace 全局入口文档 |
| `STATS.md` | CLI **不写**（留空） | **skill**（scan 时一并刷新） | workspace 结构化统计 |
| `cross_queries/` | CLI **不写**（留空目录） | **skill**（跨 wiki 综合答案归档） | 类比 wiki 内的 `syntheses/` |
| `LINT.md` | CLI **不写**（留空） | **skill**（lint 时写） | workspace 级 lint 报告（最近一次） |
| `MEMORY/` | CLI 写（init 建空目录 + 写 MEMORY.md 索引） | **skill**（写 `*.md` 经验 + 同步 MEMORY.md 索引） | 跨 wiki agent 私有记忆 |
| `<wiki-name>/` | CLI 写（按 wiki-spec §1 目录结构） | **CLI** 写元数据 + **skill**（或 `yzr-llm-wiki-management`）写内容 | 每个 wiki 是独立子仓 |

> **契约边界（不变量）**：spec 只对 **skill 有直接依赖**的根文件钉死名字——
> skill **读** `workspace.toml`（读取契约字段见 §2）+ `AGENTS.md` / `CLAUDE.md`（用户宪法，skill 只读）；
> skill **写** `INDEX.md` / `STATS.md` / `LINT.md` / `cross_queries/` 四份 workspace 级文件 +
> `MEMORY/*.md` 经验条目（同步追加 `MEMORY.md` 索引一行，骨架由 CLI init 写，见 §9）+
> 各 `<wiki-name>/wiki/**`（通过 `yzr-llm-wiki-management`）。**CLI 绝不写** 这些 skill 领地文件。
>
> **CLI 内部配置（open class，不钉名）**：除上述契约文件外，CLI 另维护若干根级配置（当前实现含
> 模型注册表、主机本地运行时配置等 `*.toml`）——skill **不读不写**。这些文件的**名字 / 格式 / 拆分
> 是 CLI 的实现自由，spec 不逐一钉名**：CLI 改名 / 增减 / 合并均不构成 spec 违规。含密配置（承载
> 密钥 / 凭据，如 API key）必须 gitignore + 文件权限保护，**具体清单与机制由探测器**
> `check_workspace_fixtures.py` **`gitignore-skeleton` check 校验，非 spec 枚举**（见 §3、§10）。
>
> **skill 绝不写**：CLI 的根配置（`workspace.toml` + 上述 open class）+ `.gitignore`（§10）+
> 用户宪法（`AGENTS.md` / `CLAUDE.md`）——前两类是 CLI 的领地，最后是用户的宪法
> （**迁移例外**：spec 升级时按 §17.2 放开 4 处单点写入）。skill 也不写
> `<wiki-name>/raw/`（用户所有）。

## §2 workspace.toml

> **维护方**：CLI 在 init 时刻创建 + 后续 wiki 注册表 / 模型配置等元数据 CRUD 命令维护。
> skill **只读**——若需要修改元数据，告诉用户跑 CLI 命令，**人类执行**。

- 路径：`<workspace-root>/workspace.toml`
- 格式：TOML
- **完整字段 schema 由 CLI 代码 SSOT**（CLI 是唯一写方；具体文件路径 / 符号名归 CLI，spec 不钉，CLI 重构不致此指针悬空）。
  CLI 可自由演进运行时字段（簿记类、模型路由类、session 启动类等）——这些是 CLI 的运行时数据，SKILL 不读，
  spec 不跟进（列了字段名只会反向耦合且必滞后）。本节只列 **skill 实际读取** 的字段子集。

> **authority**：下表是 **SKILL 的读取契约**——读方（SKILL）决定读什么，authority 在 SKILL；
> toml 字段全集 authority 在 CLI（见上 SSOT 声明）。「SKILL 读的字段 CLI 是否仍提供」由
> `check_workspace_fixtures.py` 的 `workspace-toml-reads-satisfied` check 校验（读取契约的可执行 gate）。

**skill 读取的字段**（`scan` / `migrate` 用）：

| 字段 | 用途 |
| --- | --- |
| `templates_version` | skill `migrate` 版本比对（§14，含 `workspace_spec` / `wiki_spec` 双分量） |
| `[wikis.<name>].path` | skill `scan` 遍历 wiki 子目录（见 §5 INDEX 生成流程） |
| `[wikis.<name>].created_at` | INDEX 内 wiki 排序 |

- **skill 不读**（CLI 内部字段，不在本 spec 范围）：簿记类 / 模型路由类 / session 启动类等运行时数据——
  具体字段名与用途归 CLI，spec 不跟进
- **CLI 写入场景**：workspace 元数据 CRUD（注册表维护 / 配置增改）——具体命令名归 CLI
- **skill 写入场景**：**无**——只读（迁移例外见 §17.2）

## §3 CLI 内部配置

> **范围**：CLI 维护的根级内部配置（**skill 不读不写**）——当前实现含模型注册表
> （`workspace_models.toml`，承载 API key 等敏感信息）+ 主机本地运行时配置等。这些文件的
> **名字 / 格式 / 拆分是 CLI 的实现自由，spec 不逐一钉名**；本节只约束**含密配置的敏感性
> 与权限**（CLI 改名 / 增减 / 合并不构成本节违规，含密新文件自动适用下述约束）。

- **必须 gitignored**（详见 §10）——承载密钥 / 凭据的 CLI 配置一律排除
- 落盘后以文件系统权限保护（POSIX 上如 `chmod 600`；不支持权限位的 FS 走 best-effort）——具体机制归 CLI
- **完整字段 schema 由 CLI 代码 SSOT**——本 spec 不列字段表。skill 既不读也不写这些文件，
  字段表列了只会反向耦合且必滞后；含密文件具体清单由探测器 `gitignore-skeleton` check 校验，非 spec 枚举

- **CLI 写入场景**：模型注册表 / 运行时配置 CRUD——具体命令名归 CLI
- **skill 写入场景**：**无**——完全无关（不读不写）

## §4 workspace AGENTS.md（SSOT）+ CLAUDE.md（薄壳）

> **agent 中立设计**：workspace 纪律的**单一真源是 `AGENTS.md`**——工具无关。`CLAUDE.md`
> 收敛为薄壳（`@AGENTS.md` + 声明），仅供经薄壳自动加载的 agent 读到 SSOT。原生读 `AGENTS.md` 的
> 其他 agent 直读 SSOT，不依赖薄壳。改纪律请改 `AGENTS.md`，不要改 `CLAUDE.md` 薄壳。
>
> **维护方**：CLI 在 init 时刻按 [`workspace-agents-md-template.md`](workspace-agents-md-template.md)
> （SSOT）+ [`workspace-claude-md-template.md`](workspace-claude-md-template.md)（薄壳）拷两份模板生成。
> 后续修改由 **用户** 完成（AGENTS.md 是 workspace 的 schema，是用户的"宪法"）。
> LLM agent **不得编辑** AGENTS.md / CLAUDE.md；如需变更 schema，**先与用户确认**。
> **唯一例外**：spec 升级迁移时（§17），agent 经用户确认可全量重渲染两份文件。

### AGENTS.md（SSOT）

- 路径：`<workspace-root>/AGENTS.md`
- 内容来源：本仓 `references/workspace-agents-md-template.md`（**权威 canonical 模板**）
- CLI 按 canonical 模板生成，差异**仅限 4 个 per-workspace 值**（模板替换机制——占位符语法 / 渲染引擎——
  归 CLI，spec 不规定）：
  - workspace display name（默认取创建日期或人类指定字符串，如 `"LLM Wiki Workspace"`）
  - 创建日期（当天）
  - workspace spec 版本号（CLI 当前兼容版本）
  - CLI 自身版本号
- 这 4 个值是 AGENTS.md 的**机读变量**——承载位置（H1 + 「当前配置」表，随模板定）是探测器的读取契约，
  用于 §17.1 模板渲染字节比对；具体渲染方式不限
- 模板顶部说明块的自述（"由 workspace CLI 在初始化时按本 skill 的官方模板拷贝生成"）为
  **自包含措辞**——模板是引用图汇点，**零出边**（不指向任何 skill 仓文件；由
  `template-no-outbound-refs` check 强制，见 §17.3），CLI **不得修改**
- **不带 frontmatter**——AGENTS.md 是 plain markdown；与 wiki-spec §2 的 `<wiki>/AGENTS.md` 一致

### CLAUDE.md（薄壳）

- 路径：`<workspace-root>/CLAUDE.md`
- 内容来源：本仓 `references/workspace-claude-md-template.md`（薄壳模板，`@AGENTS.md` + 声明，≤ 30 行）
- CLI 按薄壳模板生成，差异仅限 workspace display name 一个值（薄壳不持 spec 版本——版本在 AGENTS.md 「当前配置」表）
- 不含纪律正文、不含 `@MEMORY` import（那条在 AGENTS.md 内）；仅 `@AGENTS.md` 一行

### 共同约束

- **CLI 写入场景**：workspace 初始化（对已存在 workspace 重新初始化时，§12 拒绝覆盖）
- **skill 写入场景**：**无**——只读

## §5 INDEX.md（skill 维护）

> **维护方**：CLI 在 init 时刻**不创建**（留空）。skill 在 `scan` / `refresh-index` 时
> 创建 + 持续维护。skill 是 LLM 拥有的"workspace 入口文档"——人类只读。
> CLI 不参与 INDEX.md 的任何写入；skill 不依赖 CLI。

- 路径：`<workspace-root>/INDEX.md`
- frontmatter（**5 必填** + 推荐 `description`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 推荐 `"Workspace Index"` |
| `type` | enum | 是 | `workspace-index`（reserved，见 §13） |
| `tags` | array | 是 | 推荐 `[workspace, index]` |
| `created` | date (`YYYY-MM-DD`) | 是 | skill 首次创建时间 |
| `updated` | date (`YYYY-MM-DD`) | 是 | skill 每次刷新时更新为今天 |
| `description` | string | 否 | 一句话概述本 workspace 主题范围 |

- **正文骨架**：

  ```markdown
  # <Workspace Display Name> — Workspace Index

  > workspace 入口文档。每个 wiki 一节，按 wiki name 字母序；同字母序内按 `created_at` 升序。

  ## Wikis

  ### <wiki-name>

  - **display_name**: ...
  - **topic**: ...
  - **description**: ...
  - **tags**: [...]
  - **created**: YYYY-MM-DD
  - **last activity**: YYYY-MM-DD (log entry kind)
  - **page counts**: 0 entities / 0 concepts / 0 sources / 0 comparisons / 0 syntheses
  - **key entities**: [...]
  - **one-line summary**: ...

  ### <another-wiki>

  ... (同上)

  ## Cross-wiki Links

  - <wiki-a> ↔ <wiki-b>: <short description>

  ## Recent Activity (across all wikis)

  - YYYY-MM-DD: <event>
  ```

- **生成流程**（skill `scan`）：
  1. 读 `<workspace>/workspace.toml` 拿 `[wikis]` 注册表
  2. 对每个 wiki，读 `<wiki>/wiki_metadata.toml` + `<wiki>/wiki/index.md` + 末条 `<wiki>/wiki/log.md` 条目
  3. 按 wiki name 字母序聚合写入本文件
  4. 原子写（POSIX `tmp + fsync + rename`）
- **刷新时机**：每次 `scan` / `refresh-index`；大型 workspace 也可 `--quick` 只刷元数据层（不读 wiki/index.md）
- **skill 写入场景**：`scan` / `refresh-index`
- **CLI 写入场景**：**无**

## §6 STATS.md（skill 维护）

> **维护方**：CLI 在 init 时刻**不创建**（留空）。skill 在 `scan` 时一并创建 + 维护。
> 与 INDEX.md 的区别：INDEX.md 给人看（散文 + 列表），STATS.md 给 agent / 脚本看（结构化）。

- 路径：`<workspace-root>/STATS.md`
- frontmatter：同 §5（`type: workspace-stats`）
- **正文骨架**：

  ```markdown
  # <Workspace Display Name> — Workspace Stats

  > 结构化统计。skill scan 时刷新；脚本可解析 frontmatter + 表格。

  ## Overview

  | 指标 | 值 |
  | --- | --- |
  | total_wikis | N |
  | total_pages | M |
  | total_entities | ... |
  | total_concepts | ... |
  | total_sources | ... |
  | total_comparisons | ... |
  | total_syntheses | ... |
  | total_raw_files | ... |
  | cross_wiki_links | K |

  ## Per-wiki

  ### <wiki-name>

  | 指标 | 值 |
  | --- | --- |
  | pages | N |
  | entities | ... |
  | concepts | ... |
  | sources | ... |
  | comparisons | ... |
  | syntheses | ... |
  | raw_files | N |
  | last_log_entry | YYYY-MM-DD (kind) |
  | tags | [...] |
  | memory_files | N |

  ### <another-wiki>

  ... (同上)
  ```

- **生成流程**：同 §5，但输出格式更结构化（表格）
- **skill 写入场景**：`scan`（与 INDEX.md 同一次刷新）
- **CLI 写入场景**：**无**

## §7 cross_queries/（skill 维护，可选）

> **维护方**：CLI 不创建。skill 在 `query` 输出适合归档为 cross-wiki synthesis 时
> 创建 + 写入。是 workspace 级的"synthesis 类比"——`yzr-llm-wiki-management` 把好的
> 单 wiki query 答案归档为 `<wiki>/wiki/syntheses/<slug>.md`，本 skill 把好的
> 跨 wiki query 答案归档为 `<workspace>/cross_queries/<slug>.md`。

- 路径：`<workspace-root>/cross_queries/`
- 文件命名：`<slug>.md`，kebab-case，约束见 §15
- frontmatter（**5 必填** + 推荐 `description`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 人类可读标题 |
| `type` | enum | 是 | `cross-query`（reserved，见 §13） |
| `tags` | array | 是 | 推荐 `[workspace, cross-query, <涉及 wiki 的 tag>...]` |
| `created` | date | 是 | skill 写入日期 |
| `updated` | date | 是 | skill 写入日期（首次创建时同 `created`） |
| `description` | string | 否 | 一句话 |
| `sources` | array | 是 | 引用的 wiki 内页路径数组（相对 workspace 根，如 `huawei_storage_wiki/wiki/sources/foo.md`） |
| `wikis` | array | 是 | 涉及的 wiki 名列表 |

- **skill 写入场景**：`query` 输出用户确认归档时
- **CLI 写入场景**：**无**

## §8 LINT.md（skill 维护，可选）

> **维护方**：CLI 不创建。skill 在 `lint` 时写最近一次报告。属于"快照"——历史上多次
> lint 报告不累积，被新一次覆盖。

- 路径：`<workspace-root>/LINT.md`
- frontmatter：同 §5（`type: workspace-lint`）
- **正文骨架**：

  ```markdown
  # <Workspace Display Name> — Lint Report (<YYYY-MM-DD>)

  > 最近一次 workspace lint 结果。skill `lint` 时刷新；CLI 不参与。

  ## Per-wiki Issues

  ### <wiki-name>

  - **跨 wiki 重复实体**: <list>
  - **跨 wiki 失效链接**: <list>
  - **孤立 wiki**: <yes/no + 说明>
  - **本 wiki 内 lint**: 走 wiki-spec §3 / §4 lint 流程——本 skill 不重复

  ## Workspace-level Issues

  - **重复 entity 跨 wiki**: <wiki-a>::<entity-x> ↔ <wiki-b>::<entity-y>
  - **未注册的 wiki 子目录**: <list>（workspace.toml 中没有但磁盘上存在的 wiki 目录）
  - **STATS.md 过期**: <yes/no>（与最近一次 scan 的时间差）
  - **MEMORY 索引一致性**: <list of `memory-not-indexed`>（MEMORY/*.md 未在 MEMORY.md 索引列出）
  - **其他**: ...
  ```

- **skill 写入场景**：`lint`（每次覆盖）
- **CLI 写入场景**：**无**

## §9 workspace MEMORY/（skill 维护）

> **维护方**：CLI 在 init 时刻创建**空目录**并按 §9.1 写入 `MEMORY/MEMORY.md`（索引占位）；
> 后续 `MEMORY/*.md` 经验条目由 **skill** 写入，并**同步追加 MEMORY.md 索引一行**。
> skill 是 LLM agent 的**跨 wiki** 私有记忆——人类**不写** MEMORY 内容。CLI 不参与 MEMORY
> 的后续写入（仅 init 写骨架）。
>
> **scope 严格区分**（**核心不变量**，避免变成 junk drawer）：
>
> - ✅ `<workspace>/MEMORY/` 写**跨 wiki** 的 LLM 经验（用户对 workspace 组织的偏好 /
>   跨 wiki 关联 / lint recurring pattern / 跨 wiki 综合经验）
> - ❌ **不**写单 wiki 观察——单 wiki 的踩坑 / 偏好 / 关联归 `<wiki>/MEMORY/`
>   （由 `yzr-llm-wiki-management` 维护）
> - ❌ **不**写跨 wiki 综合答案本身——归 `<workspace>/cross_queries/`
> - ❌ **不**写一次性观察——直接 chat，不写 MEMORY
>
> **纪律正文唯一副本（canonical）**：MEMORY 的"何时写 / 不写 / 条目形式 / 判别尺度"纪律正文
> 唯一维护点在 [`workspace-agents-md-template.md`](workspace-agents-md-template.md) §五——模板随
> init 拷进 workspace（workspace 侧读者可达），故它就是副本宿主。本节只保留**机制契约**
> （路径 / frontmatter 字段 / lint 语义 / CLI init 行为）；凡与模板重复的逐字纪律句以
> 「纪律正文见模板 §五」指针代替。**改纪律只改模板 §五 + bump `workspace_spec_version`**。
> 引用方向**单向**：spec / SKILL.md → 模板；模板**不**含任何指向 skill 仓的引用
> （由 `template-no-outbound-refs` check 机械强制）。

- 路径：`<workspace-root>/MEMORY/`
- 目录名 `MEMORY` **大写**，区别于小写 `raw` / `wiki` / `cross_queries` 等目录
- **MEMORY 不在 `INDEX.md` 中强制列出**——它是 agent 私有入口，不需要 workspace 单一入口约束
- **条目形式按事实颗粒度选**——完整 / 短两条写法的纪律正文见
  [模板 §五](workspace-agents-md-template.md)（**canonical 副本**）；本节只留机制事实：
  短条目与完整条目可在同一 `MEMORY/MEMORY.md` 共存；lint `memory-not-indexed` 只兜底
  "有 .md 但未索引"，不强制反向（短条目无 .md，不进该检查）
- 命名约束：详见 §15

### §9.1 MEMORY/MEMORY.md（索引）

> **维护方**：CLI 在 init 时刻写一次（idempotent：已存在则跳过）。与 wiki-spec §5.1
> `MEMORY/MEMORY.md` 同构——本目录的索引文件。

- 路径：`<workspace-root>/MEMORY/MEMORY.md`
- **无 frontmatter**——它是被 `<workspace>/AGENTS.md` 用 `@MEMORY/MEMORY.md` import 内联的
  索引片段，不是 workspace 内容页（对齐仓库根 `MEMORY/MEMORY.md` / wiki-spec §5.1 形态）。
  lint / scan 把它当索引跳过 frontmatter / type 校验
- **加载机制（agent 中立）**：agent 在 workspace 根目录工作时——经薄壳 `CLAUDE.md` → `@AGENTS.md`
  递归展开自动加载 SSOT，`@MEMORY/MEMORY.md` 随之展开 → 索引常驻；原生读 `AGENTS.md` 的其他 agent
  直读 SSOT；agent 在别处工作（skill 经 workspace 路径定位并读 AGENTS.md；具体定位途径——环境变量 /
  默认路径 / 显式传参——归 CLI session 设置，spec 不钉）时，`@` 不自动展开，
  由 AGENTS.md 顶部强制 Read 指令 + SKILL §0 启动检查显式 Read MEMORY.md 补齐
- 正文骨架：顶部 1 段说明（本目录用途 + 何时写 / 命名 / 纪律指向 SKILL §5，**不**重复以免
  口径分裂）+ `## 索引` 段。索引行两种格式共存：
  - **完整条目**：`- <slug> — <一句话摘要> → [正文](<slug>.md)`（指向 §9.2 的 `MEMORY/<slug>.md`）
  - **短条目**：`- <一句话事实>`（无链接，对应无 `.md` 文件的索引行 reminder）
  - 判别尺度见[模板 §五](workspace-agents-md-template.md)「条目形式按事实颗粒度选」（canonical 副本）
- lint `memory-not-indexed` 兜底——`MEMORY/*.md`（排除 `MEMORY.md`）未在索引列出时报该项；
  短条目无 `.md` 不进该检查
- **内容来源 / 字面量**：[`references/fixtures/memory-index.txt`](fixtures/memory-index.txt)
  （与 [`references/canonical/memory-index.md`](canonical/memory-index.md) 一致——MEMORY.md 无占位符，
  fixtures 与 canonical 内容相同）。CLI init **逐字拷贝**生成 `<workspace>/MEMORY/MEMORY.md`——与
  wiki-spec §5.1 走相同的 fixtures/canonical 字节金标准模式（无占位符字面量文件进 fixtures/canonical；
  有占位符的 `AGENTS.md` / `CLAUDE.md` 模板仍在 references/ 根，走 §4 内容级验证）。初始索引为空，注释用纯文字
  描述格式，不含真实 `[](...)` 链接以免被未来 lint 当死链

### §9.2 MEMORY/*.md（非 MEMORY.md）

- 路径：`<workspace-root>/MEMORY/<slug>.md`
- 命名约束：kebab-case `^[a-z0-9][a-z0-9-]*$`，见 §15
- frontmatter：**5 必填**（`title` / `type` / `created` / `updated` / `tags`）+ 推荐
  `description` + 推荐 `wikis` 字段（涉及 wiki 名数组）

| `type` 取值 | 含义 |
| --- | --- |
| `entity` / `concept` / `source` / `comparison` / `synthesis` | 复用 wiki-spec §9 的 5 类内容页 enum（按记忆内容性质选） |
| `workspace-memory` | 跨 wiki 关联 / 用户偏好 / lint 模式（**新增 reserved**，见 §13） |

- `wikis` 字段：数组，列涉及的 wiki 名；若该条记忆涉及全 workspace 而非特定 wiki，可省略
- lint 校验：走与 wiki 内容页一致的 5 必填校验（`title` / `type` / `created` / `updated` / `tags`）
- 与 wiki 内容页的区别：
  - **不**强制在 INDEX.md 列出
  - **不**要求有 inbound 链接
  - 正文无长度上限（agent 经验沉淀可以很长）
  - LLM agent **必须**创建（user 不写）
  - **必须**在 `MEMORY/MEMORY.md` 索引列出一行（skill 写 memory 时同步追加；
    lint `memory-not-indexed` 兜底漏列——severity = info，不阻断但提示）
  - 短条目无对应 `.md` 文件，frontmatter 5 必填仅约束完整条目；判别尺度见
    [模板 §五](workspace-agents-md-template.md)（canonical 副本）

### §9.3 何时写 / 不写

**写**（按 [`SKILL.md` §5 memory](../SKILL.md) 触发）——何时写 / 不写的完整清单
（跨 wiki 关联 / 用户偏好 / lint 模式 / 综合经验 vs 单 wiki 观察 / 综合答案 / 一次性观察）
见[模板 §五](workspace-agents-md-template.md)（**canonical 副本**），本节不重复正文。

### §9.4 创建时机

`MEMORY/` 目录 + `MEMORY.md` 索引由 **CLI init 时刻**创建（见 §1 / §9.1）；skill **不重建**
（已存在即跳过）。这与 `INDEX.md` / `STATS.md`（skill scan 时建）区分——MEMORY 骨架是出生
形态的一部分，由 CLI 负责。

skill 在 `lint` / `query` / `link` / `scan` 触发时**不创建** MEMORY 结构；只在真正需要写
跨 wiki 经验时才 Write `MEMORY/<slug>.md` + 同步 `MEMORY.md` 索引一行。

## §10 .gitignore

`.gitignore` **总是生成**——git 仓由用户外部创建（§11），无 git 时无害，便于后续补 git。
完整字节 SSOT 在 **CLI 代码**——CLI 落盘后由 `check_workspace_fixtures.py` 的
`gitignore-skeleton` check 做段结构比对（探测器 + fixtures 为权威）。本节只规定**设计不变量**，
`.gitignore` 必须排除**承载密钥 / 凭据的文件**——

- **敏感文件类**（强约束）：模型注册表（含 API key）+ 各 IDE / agent 的项目级 settings（可能含 token）。
  具体忽略哪些文件、用什么栅栏标记（托管块 / 段注释 / 其它）由 CLI 决定，spec 不钉——探测器硬要求的
  最小清单见 `gitignore-skeleton` check；CLI 可在此之上加自有扩展，扩展不进 spec
- **OS / 编辑器**、**Obsidian 配置**、**临时文件** 三类噪音段，各 ≥1 规则（段内具体规则用户可调）

**必须不忽略**：`workspace.toml`、`AGENTS.md`、`CLAUDE.md`、`INDEX.md`、`STATS.md`、
`cross_queries/`、`LINT.md`、`MEMORY/`、`<wiki-name>/`（wiki 仓内容由 wiki-spec §6 各自的
`.gitignore` 处理）。

## §11 Git 仓（用户外部创建，CLI 不碰）

> **立场**：workspace **不依赖 git 即可工作**——默认落盘为**纯目录树**。workspace 的 git 仓
> **由用户在外部自行 `git init` / `clone` 创建**，CLI **不碰 git**——不 `git init`、不 `add`、
> 不 `commit`、也不提供任何 git 操作入口；版本控制是用户在自己机器上决定的事。CLI 含密配置
> 在无 git 时靠文件系统权限保护，用户启用 git 后靠 `.gitignore`（§10）排除。

- **init 允许落在用户已建好的空 git 仓上**：若目标目录已是 git 空仓（仅含 `.git` 与/或
  `.gitignore`），CLI 的初始化操作照常在其上继续——CLI 不调 `git init`，只是不把"已有 .git"
  当成拒绝条件（`git init` 本身幂等，CLI 落盘不破坏用户已建的仓）。
- **`.gitignore` 无条件生成**（详见 §10）：与用户是否启用 git 无关——CLI 总是写 `.gitignore`，
  便于用户后续随时 `git init` 时敏感文件已被排除。

## §12 拒绝条件（强约束）

CLI 在以下情况必须拒绝并退出（**非零退出码**）：

| 触发条件 | 错误信息建议 |
| --- | --- |
| `workspace.toml` 已存在且非 CLI 自己写的 | `"workspace.toml 已存在；拒绝覆盖"` |
| `AGENTS.md` 已存在 | `"AGENTS.md 已存在；拒绝覆盖（schema 是用户所有）"` |
| `CLAUDE.md`（薄壳）已存在 | `"CLAUDE.md 已存在；拒绝覆盖（schema 是用户所有，若需更新请手动编辑）"` |
| 试图注册新 wiki 到已存在的子目录 | `"<wiki-name>/ 已存在；拒绝覆盖"` |
| 试图注册新 wiki 时 `wiki-name` 与现存 wiki 重复 | `"wiki <name> 已注册；拒绝重复"` |

**绝不允许覆盖**：workspace CLI 的 idempotency 原则——已存在 + 内容合法 = 跳过；已存在 + 内容非法 = 报错；用户想重新初始化必须先手动备份 + 删除。

> **注意**：CLI **不**触碰 `INDEX.md` / `STATS.md` / `LINT.md` / `cross_queries/` +
> `MEMORY/*.md` 经验条目——这些是 skill 的领地。CLI 仅在 init 时写 `MEMORY/MEMORY.md` 索引
> 占位（见 §9.1）；CLI 不检查 INDEX/STATS/LINT/cross_queries 是否存在，也不拒绝 init 时
> 这些文件已存在的情况（skill 会在首次 `scan` 时按需创建或跳过自己的产物，这是 skill 的
> 幂等约定）。

## §13 Frontmatter 字段约定（skill 写 §5–§9 时用）

### 通用必填字段（5 项）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | string | 人类可读标题，不含扩展名 |
| `type` | enum | 见下方 `type` 取值 |
| `tags` | array | 可空数组 |
| `created` | date | `YYYY-MM-DD` |
| `updated` | date | `YYYY-MM-DD` |

### `type` 取值（5 类 wiki 内容页 + 2 类 wiki reserved + 4 类 workspace reserved + 1 类 workspace-memory）

| `type` | 目录 | 备注 |
| --- | --- | --- |
| `entity` / `concept` / `source` / `comparison` / `synthesis` | 5 类 wiki 内容页 enum（**复用 wiki-spec §9**） | `<workspace>/MEMORY/*.md` 可按记忆内容性质选 |
| `index` / `log` | 2 类 wiki reserved（**复用 wiki-spec §9**） | wiki 内 `wiki/index.md` / `wiki/log.md`（workspace 不直接用） |
| `workspace-index` | `<workspace>/INDEX.md`（唯一） | workspace reserved |
| `workspace-stats` | `<workspace>/STATS.md`（唯一） | workspace reserved |
| `workspace-lint` | `<workspace>/LINT.md`（唯一） | workspace reserved |
| `cross-query` | `<workspace>/cross_queries/<slug>.md` | workspace reserved |
| `workspace-memory` | `<workspace>/MEMORY/*.md`（非 MEMORY.md） | workspace reserved |

> **与 wiki-spec §9 的关系**：workspace-spec 的 `workspace-memory`（`<workspace>/MEMORY/*.md`
> 经验条目）与 wiki 内容页 5 类 enum（`<wiki>/MEMORY/*.md` 可按记忆性质选）location 区分，
> 不冲突。两份 `MEMORY.md` 索引（workspace 与 wiki 各一份）均**无 frontmatter**——与 wiki-spec
> 的 `<wiki>/MEMORY/MEMORY.md` 无 frontmatter 形态对齐。lint 工具需要识别本
> spec 的 `workspace-memory`；若 lint 脚本只跑在 wiki 内，可忽略本节。

### 类型特化字段

| 字段 | 适用 type | 必填 | 含义 |
| --- | --- | --- | --- |
| `sources` | `cross-query` | 是 | 引用的 wiki 内页路径数组（相对 workspace 根） |
| `wikis` | `cross-query` / `workspace-memory` | 是（`cross-query`）/ 推荐（`workspace-memory`） | 涉及的 wiki 名列表 |
| `description` | 所有 5 必填类 | 否 | 一句话 |

## §14 版本钉死

**设计不变量**：workspace 必须记录它被创建时对齐的 spec 版本，使 skill `migrate` 能探测版本漂移。
具体承载形式——

- `workspace.toml` 的 `templates_version` 字段编码 workspace_spec + wiki_spec 双分量（可被
  `check_workspace_fixtures.py` 解析即可；具体编码串格式归 CLI，spec 不钉）
- AGENTS.md 的「当前配置」表记录 workspace_spec 版本 + CLI 版本（薄壳 CLAUDE.md 不持 spec 版本）

版本号的**来源**（CLI 内部机制）与**模板替换机制**（占位符语法 / 渲染引擎）都归 CLI，spec 不规定。
「CLI 记录的 spec 版本是否与 SKILL 当前版本对齐」
由 `check_workspace_fixtures.py` 的相关 check 校验（读取契约的可执行 gate）。

"当前 spec 版本"的 SSOT 是 [`yzr-llm-workspace-management`](../SKILL.md) SKILL.md
`metadata.workspace_spec_version`（本 spec 不重复钉号，避免双源漂移）。skill 在每次
`scan` 前比对 `workspace.toml.templates_version` 的 workspace_spec 分量与该版本——不一致时
**警告用户**走 §6 Migrate（不阻断；旧 spec 的产物仍可读）。完整检测走
`scripts/check_workspace_fixtures.py`（§17.3）。

## §15 命名约束

| 维度 | 规则 | 适用对象 |
| --- | --- | --- |
| Wiki name | `[a-z0-9][a-z0-9_-]*`，1–64 字符；推荐纯 kebab-case | `[wikis.<name>]` key + `<wiki-name>/` 子目录名 |
| cross_query slug | kebab-case `^[a-z0-9][a-z0-9-]*$` | `cross_queries/<slug>.md` |
| MEMORY 文件名 | kebab-case `^[a-z0-9][a-z0-9-]*$` | `<workspace>/MEMORY/*.md`（MEMORY.md 例外） |
| frontmatter 字段名 | 严格小写 + 下划线 | 所有 workspace 级 markdown |
| frontmatter `type` 值 | 严格小写 + 连字符（`workspace-index` / `workspace-memory` 等） | 所有 workspace 级 markdown |

> `model_id` 等 CLI 内部标识符（模型注册表等，见 §3）的命名规则归 CLI（skill 不读不写），
> 不在本 spec 范围。

## §16 不在本 spec 范围内

以下事项不由本 spec 定义（toml 字段 schema 归 CLI；运行时规则归 skill）：

- **toml 字段全集 schema**（`workspace.toml` / `wiki_metadata.toml` + CLI 内部配置 toml 的字段定义）——
  归 CLI 代码 SSOT，本 spec 只描述 skill 读取契约（见 §2 / §3）
- **cross-wiki Q&A 的工作流**——4 种模式（route / synthesis / compare / local）的
  算法与判定规则属 [`yzr-llm-workspace-management`](../SKILL.md) skill 范畴
- **跨 wiki 交叉引用（xref）建议逻辑**——同上
- **workspace lint 的工作流**——同上
- **workspace MEMORY 的工作流**（何时写 / 不写 / 怎样分类）——同上
- **frontmatter 字段的语义**（如 `description` 推荐写法）——LLM 写作视角，非 spec 视角
- **Obsidian / 编辑器偏好**——skill 假设通用 Markdown
- **INGEST / 单 wiki query / 单 wiki lint**——走 `yzr-llm-wiki-management` skill，
  本 spec 不重复

## §17 升级迁移（skill 维护）

> **维护方**：`yzr-llm-workspace-management` skill 的 migrate 工作流（SKILL.md §6）+
> `scripts/check_workspace_fixtures.py`（探测器）。CLI 不参与升级（§12 拒绝覆盖已存在文件）。

spec 演进时，已存在 workspace 的约定文件（AGENTS.md / CLAUDE.md / .gitignore /
MEMORY/MEMORY.md / workspace.toml `templates_version`）会有意识地保留旧格式——避免一刀切
破坏用户定制。本节定义检测 + 修复机制，让升级后 workspace 与最新模板保持**字节级**一致。

### §17.1 AGENTS.md / CLAUDE.md 模板同步

`AGENTS.md` 的 per-workspace 变量只有 4 个——Workspace 名 / 创建日期 / Workspace Spec
版本 / CLI 版本（全在固定承载位置：H1 + 「当前配置」表）；正文 §一~§五 是纪律文本，跨 workspace
逐字相同。因此一致性校验**不**做"存在性断言"，做**模板渲染字节比对**：

- `scripts/check_workspace_fixtures.py` 的 `agents-md-template-sync`（error）：从「当前配置」表
  提取 4 变量（无该表时 fallback H1 + 散文行），渲染
  `references/workspace-agents-md-template.md` 后与 workspace 实际 AGENTS.md 字节比对——
  任何不一致（旧版本残留 / 本地改动）都报错。`claude-md-template-sync` 同理（薄壳仅
  workspace display name 一个变量；缺失文件报 `workspace-fix-claude-md-create`）。
- 修复 = **全量重渲染**（fix `workspace-fix-agents-md-resync` /
  `workspace-fix-claude-md-resync`）：4 变量保留旧值（workspace spec 版本用
  迁移目标版本），其余以模板渲染稿为准——**不**做局部 Edit。旧文件中多出的本地定制
  行/段由 agent 逐条列给用户裁定：搬 `MEMORY/`（一行事实写 MEMORY.md 索引短条目；
  含 why 建 `MEMORY/<slug>.md` 完整条目 + 索引行）或丢弃。
- **纪律推论**：本 workspace 特有纪律 / 偏好一律沉淀到 `MEMORY/`（由 AGENTS.md 顶部
  `@MEMORY/MEMORY.md` `@import` 加载，会话常驻），不写进 AGENTS.md——否则下次升级
  重渲染时丢失。
- 与 `agents-version-is-current` 正交：版本行新旧由后者管；本 check 渲染时用
  workspace 自钉的 spec 版本替换版本变量，只比"正文与模板同步"。

### §17.2 迁移例外（所有权开口）

§1 / §4 的"skill 只读 / 不写"纪律在 migrate 工作流内有 4 条例外（前提都是**用户确认**
后在同一会话内执行）：

| 例外 | 范围 |
| --- | --- |
| agent 可 Write 覆盖 `AGENTS.md` | 仅 §17.1 全量重渲染；本地定制已逐条裁定 |
| agent 可 Write 覆盖 / 创建 `CLAUDE.md` | 仅按薄壳模板渲染 |
| agent 可 Edit `.gitignore` | 仅补 §10 敏感文件忽略段；不动用户自定义规则 |
| agent 可 Edit `workspace.toml` 的 `templates_version` 单字段 | migrate 收尾 bump 到目标版本；其余字段不动 |

### §17.3 检测与修复流程

探测器 `scripts/check_workspace_fixtures.py`（8 条 check：
`agents-version-is-current` / `agents-md-template-sync` / `claude-md-template-sync` /
`gitignore-skeleton` / `memory-index-skeleton` / `workspace-toml-templates-version-sync`（warn，
不阻断）/ `workspace-toml-reads-satisfied`（SKILL 读取契约自洽，error）/ `template-no-outbound-refs`
（skill 仓模板零出边自检，error）；退出码 0 全过 / 1 有 error / 2 运行错误；`--json` 机器可读）。修复由 agent 按
报告 `fix` 动作走 SKILL.md §6——**不落 plan 文件**（修复面恒定 ≤ 4 个结构文件，报告即
清单；检测幂等，中断重跑即可），零中间产物。

---

## 附录 A：CLI 实现自检建议

CLI 在生成完成后，可执行以下验证：

1. **字节级对比**：`AGENTS.md` 与 §4 SSOT 模板字面一致 + `CLAUDE.md` 与薄壳模板字面一致（占位符
   替换后）；`MEMORY/MEMORY.md` 与 `references/canonical/memory-index.md` 字节一致（无占位符，直接
   `cmp`，流程同 wiki fixtures）；`.gitignore` 段结构由 `gitignore-skeleton` check 比对（完整字节 SSOT
   在 CLI 代码，见 §10）。**`workspace.toml` + CLI 内部配置 toml 的字段 schema
   不由本 spec 比对**——归 CLI SSOT（见 §2 / §3），CLI 是唯一写方、字段演进自保；SKILL 只 gate 读取
   契约字段（`templates_version` / `[wikis].path/created_at`，由 `workspace-toml-reads-satisfied` check 校验）
2. **结构性自检**：`<workspace>/` 含 §1 列出的所有顶层项（含 `MEMORY/MEMORY.md`）；`<wiki-name>/` 子目录按
   wiki-spec §1 目录结构 落盘
3. **拒绝性自检**：对已存在 workspace 重新初始化、向已存在目录注册 wiki、`AGENTS.md` / `CLAUDE.md`
   已存在时初始化——都应非零退出（§12）
4. **gitignored 自检**：敏感文件（模型注册表 + 各 IDE/agent 项目级 settings）被 `.gitignore` 排除；
   具体清单与栅栏标记以 `gitignore-skeleton` check 为准（见 §10）
5. **不变量自检**：init 完成后 `<workspace>/INDEX.md` / `STATS.md` / `LINT.md` / `cross_queries/`
   **不存在**（CLI 不会创建它们；skill 在首次 `scan` 时按 §5–§8 约定建）；但 `<workspace>/MEMORY/`
   **存在**且含 `MEMORY.md` 索引、无 `*.md` 经验条目（CLI init 按 §9 建骨架）

> 版本演进历史见 git log（`git log --follow -- yzr-llm-workspace-management/references/workspace-spec.md`）——
> CLI 不读，agent 追"为什么这条规则存在"时按需看提交信息。
