# Wiki Spec（wiki 仓出生形态 + skill 读取契约）

> 本文档约定 wiki 仓的**出生形态骨架** + 各文件的**归属关系**（谁写谁读）+
> **skill 读取契约** + `wiki_metadata.toml` 的 schema 边界（schema 归 CLI，见 §1.1）。
>
> **依赖方向（单向）**：`workspace CLI → SKILL`（CLI 运行时读 SKILL 的 fixtures / 模板落盘骨架）。
> SKILL **不反向依赖** CLI 实现——`wiki_metadata.toml` 的**字段全集 schema 归 CLI 代码 SSOT**
>（见 CLI 仓）。本 spec 只描述 SKILL 读取所需的字段子集。
>
> **spec 只承载设计不变量**：CLI 的具体实现形式——命令名、占位符语法 / 渲染机制、版本戳编码格式、
> `.gitignore` 栅栏标记、CLI 源码路径等——一律**不进 spec**（实现方法多样，spec 钉死只会反向限制
> CLI 开发）。这些细节的唯一权威是 [`check_wiki_fixtures.py`](../scripts/check_wiki_fixtures.py)
> （可执行契约）+ [`references/fixtures/`](fixtures/)（字节金标准）+ CLI 代码；本 spec 提及时只描述
> 设计意图 + 指向探测器，不复制字节。
>
> **结构合规的可执行真源**是 [`scripts/check_wiki_fixtures.py`](../scripts/check_wiki_fixtures.py)——
> 本 spec 是它的人类可读说明；两者不一致时**以探测器为准**（spec 滞后不构成 CLI 违规；
> 探测器 pass 即合规）。
>
> **生命周期归属**：本 spec 只规定 wiki 仓的"出生形态"。
> wiki 出生后的所有成长（ingest / query / lint / 重写）由 **LLM agent** 维护，遵循
> SKILL 仓的 SKILL.md / references/ 规则。CLI 在 wiki 生命周期的两个边界点被调用：
>
> - **init**：创建（按本 spec 落盘）
> - **delete**：删除（带备份）
>
> 其他时刻调 CLI 属"误用"，CLI 应拒绝。
>
> **AGENTS.md / CLAUDE.md（薄壳） / index.md / log.md / MEMORY/ 的归属**：
>
> | 文件 / 目录 | init 时刻（CLI） | 后续所有变更 |
> | --- | --- | --- |
> | `<wiki-root>/AGENTS.md` | CLI 按 §2 拷贝 SSOT 模板 | 用户（schema 是用户宪法，工具无关 SSOT） |
>
| `<wiki-root>/CLAUDE.md`（薄壳） | CLI 按 §2 拷贝薄壳模板（`@AGENTS.md`） | 用户（仅供经薄壳自动加载的 agent） |
> | `wiki/index.md` | CLI 按 §3 写入初始骨架 | **LLM agent**（ingest / 重写 / 归档时同步） |
> | `wiki/log.md` | CLI 按 §4 写入首条 setup 条目 | **LLM agent**（追加 + 维护滚动窗口，见 §4.1） |
> | `MEMORY/` | CLI 按 §5 创建空目录 + 写 MEMORY.md（索引） | **LLM agent**（append 经验条目 + 同步 MEMORY.md 索引） |
> | `scripts/` | CLI 按 §14 创建空目录 + 写 SCRIPTS.md（索引） | **用户 + LLM agent**（添加 / 修改脚本与同步 SCRIPTS.md 段是原子动作） |
>
> CLI **不**参与 index.md / log.md / MEMORY / scripts 的后续追加；无 "add log entry" /
> "add memory" / "add script" / "sync index" 类命令。

## 目录

- [§1 目录结构](#1-目录结构)
- [§2 AGENTS.md（SSOT）+ CLAUDE.md（薄壳）](#2-agentsmdssot-claudemd薄壳)
- [§3 wiki/index.md](#3-wikiindexmd)
- [§4 wiki/log.md](#4-wikilogmd)
- [§5 MEMORY/](#5-memory)
  - [§5.1 MEMORY/MEMORY.md（索引）](#51-memorymemorymd索引)
  - [§5.2 MEMORY/*.md（非 MEMORY.md）](#52-memorymd非-memorymd)
- [§6 .gitignore](#6-gitignore)
- [§7 Git 初始化（opt-in，默认跳过）](#7-git-初始化opt-in默认跳过)
- [§8 拒绝条件（强约束）](#8-拒绝条件强约束)
- [§9 Frontmatter 字段全集（CLI 引用，非生成内容页）](#9-frontmatter-字段全集cli-引用非生成内容页)
- [§10 版本钉死](#10-版本钉死)
- [§11 命名约束（影响 CLI 生成的产物）](#11-命名约束影响-cli-生成的产物)
- [§12 不在本 spec 范围内](#12-不在本-spec-范围内)
- [§13 raw/external/——外部代码仓接入](#13-rawexternal外部代码仓接入可选)
- [§14 scripts/——本 wiki 仓扩展脚本目录](#14-scripts本-wiki-仓扩展脚本目录)
- [§15 raw/discussions/——协作草稿层](#15-rawdiscussions协作草稿层可选)
- [附录 A：CLI 实现自检建议](#附录-acli-实现自检建议)

## §1 目录结构

```text
<wiki-root>/
├── .gitignore
├── AGENTS.md                  # 工具无关纪律 SSOT（详 §2）；顶部
│                              # @MEMORY/MEMORY.md + @scripts/SCRIPTS.md 双
│                              # @import 收口
├── CLAUDE.md                  # 薄壳（@AGENTS.md，供经薄壳加载的 agent）
├── wiki_metadata.toml         # CLI 维护的 wiki 元数据（schema 见 §1.1；skill 只读）
├── MEMORY/                    # agent 持久化记忆目录（详 §5）
│   └── MEMORY.md              # MEMORY 索引（无 frontmatter）；由 AGENTS.md 顶部
│                              # @MEMORY/MEMORY.md @import 自动加载（详见 §5.1）
├── raw/
│   ├── articles/
│   └── assets/
├── scripts/                   # 本 wiki 自维护脚本目录（详 §14）
│   └── SCRIPTS.md             # scripts/ 索引（无 frontmatter）；由 AGENTS.md 顶部
│                              # @scripts/SCRIPTS.md @import 自动加载（详见 §14.3）
└── wiki/
    ├── comparisons/
    ├── concepts/
    ├── entities/
    ├── index.md
    ├── log.md
    ├── sources/
    ├── syntheses/
    └── tags.md                # tag 白名单（LLM 拥有；详 §9）
```

- 5 个内容页子目录名固定，**字母序**（`comparisons` → `concepts` → `entities` → `sources` → `syntheses`），
  CLI 必须按此顺序创建（利于阅读、diff 稳定、跨工具兼容）
- **`MEMORY/` 是 wiki 仓的"agent 持久化记忆"目录**（与 `wiki/` **平级**，
  不嵌在 `wiki/` 下）——LLM agent 写入，用于沉淀跨 ingest / query / lint 的工作经验、
  踩坑记录、用户偏好；走 §5.2 的 frontmatter **1 必填（`title`）+ optional 字段**规则
  （MEMORY 是 agent 私有，不与 wiki 内容页共享 5 必填；详见 §5）。
  其中 `MEMORY.md` 是索引（**单一真源**），由 `<wiki-root>/AGENTS.md` 顶部
  `@MEMORY/MEMORY.md` `@import` 自动加载全文——自动展开 `@import` 的 agent 透明拿到索引；
  不展开 `@import` 的 agent 由 AGENTS.md 顶部强制 Read 指令兜底。AGENTS.md 只挂单行引用、
  不持有副本，**无**双写漂移 / L1 膨胀风险（详见 §5.1 加载机制段）。**为什么 MEMORY 位于
  `<wiki-root>/`（与 `wiki/` 平级）**：对应 §四层架构第 3 层（独立于 wiki/ 内容，物理位置跟逻辑分层对齐）；
  未来 publish 时 MEMORY 自然留作私有层不外传
- **`wiki/tags.md` 是 wiki 仓的"tag 白名单"**——LLM agent 拥有，存放本 wiki
  允许使用的 tag 集合；裸 bullet 列表，**无 frontmatter**（与 MEMORY.md 同——元数据不是
  wiki 内容页）；不在 `wiki/index.md` 强制列出；CLI init 时刻按 `references/fixtures/`
  生成空白模板，LLM 与用户共同确认主题分类后填充。详见 §9「§9.1 tag 白名单来源」
- `raw/` 下子树分两类：**通用分类占位**（`articles/` / `assets/` 等，用户自由组织原始资料，
  无强制语义）与**有专门语义的子树**——`external/`（§13，外部仓 symlink 接入）、
  `discussions/`（§15，协作草稿层）。后两者是 raw/ 总纪律（LLM 只读）的**两处写权限例外**，
  其余 raw/ 子树 LLM 仍只读。**fresh init 预建哪些 raw/ 子目录是实现的自由**（见 §7），
  不影响语义正确性
- `index.md` / `log.md` 是 `wiki/` 下的文件（不是子目录）；`MEMORY/MEMORY.md` 在 `<wiki-root>/MEMORY/`
  下（与 `wiki/` 平级），不是 `wiki/` 下的文件
- `comparisons/` 等 5 个内容页子目录在初始化时为空目录——空目录对纯目录树 wiki 无副作用；
  让空目录可被 git 跟踪的占位策略（`.gitkeep` / 别的方式）由实现自定（见 §7）
- **`scripts/` 是 wiki 仓的本机扩展脚本目录**——CLI init 时刻**始终创建**
  （与 `raw/articles/` 同：默认占位），用户 / agent 后续填入项目级 ingest 扩展、
  外部 CLI 胶水脚本、自动化钩子等。`scripts/SCRIPTS.md` 是这个目录的索引，由
  `<wiki-root>/AGENTS.md` 顶部 `@scripts/SCRIPTS.md` `@import` 自动加载全文
  （同 MEMORY 加载机制）。scripts/ **不**走 §9 5 必填、**不**参与 lint 内容页扫描
  （**代码而非内容页**）。详见 §14。

## §1.1 wiki_metadata.toml（CLI 维护）

> **维护方**：workspace CLI 在 wiki 注册时创建 + 后续 wiki 元数据 CRUD 命令维护。
> skill **只读**（workspace skill `scan` 时读取，见 workspace-spec §5）。

- 路径：`<wiki-root>/wiki_metadata.toml`
- 格式：TOML
- **完整字段 schema 由 CLI 代码 SSOT**（见 CLI 仓）——本 spec 不做权威定义。
  CLI 可自由演进运行时字段（簿记 / session 启动等），spec 不跟进。

> **authority**：下表是 **SKILL 的读取契约**，authority 在 SKILL（读方决定读什么）；
> toml 字段全集 authority 在 CLI。「SKILL 读的字段 CLI 是否仍提供」由
> `check_wiki_fixtures.py` 的 `wiki-metadata-reads-satisfied` check 校验（读取契约的可执行 gate）。

- **skill 读取的字段**（workspace skill `scan` 生成 INDEX / STATS 用）：
  `name` / `topic` / `display_name` / `description` / `tags` / `created_at`
- **skill 不读**（CLI 内部字段）：session 启动 / 簿记等运行时数据——具体字段名与用途归 CLI，spec 不跟进
- **CLI 写入场景**：wiki 元数据 CRUD——具体命令名归 CLI
- **skill 写入场景**：**无**——只读

## §2 AGENTS.md（SSOT）+ CLAUDE.md（薄壳）

> **agent 中立设计**：wiki 纪律的**单一真源是 `AGENTS.md`**——工具无关。`CLAUDE.md`
> 收敛为薄壳（`@AGENTS.md` + 声明），仅供经薄壳自动加载的 agent 读到 SSOT。原生读 `AGENTS.md` 的
> 其他 agent 直读 SSOT，不依赖薄壳。改纪律请改 `AGENTS.md`，不要改 `CLAUDE.md` 薄壳。
>
> **维护方**：CLI 在 init 时刻按本节模板拷贝两份；后续修改由 **用户** 完成（AGENTS.md 是 wiki 的
> schema，是用户的"宪法"）。LLM agent 不得编辑 AGENTS.md / CLAUDE.md；如需变更 schema，**先与用户确认**。
>
> **现行形态**：`AGENTS.md` 顶部含 `@MEMORY/MEMORY.md` + `@scripts/SCRIPTS.md` 两行 `@import` 收口 +
> 一条**强制 Read 指令** blockquote（凡 `@` 引用都用 Read 读）——自动展开 `@import` 的 agent
> 透明拿到 MEMORY / scripts 全文；不展开 `@import` 的 agent 由该顶部指令兜底直接 Read。
> **MEMORY / scripts 是单一真源**，AGENTS.md 单行 `@import` 引用同步指向全文——**不**在 AGENTS.md
> 持有副本，**无**双写漂移 / L1 膨胀风险。详见 §5.1 + §14.3 加载机制段。
>
> **Tag Taxonomy 段归属**：SSOT 模板含 `### Tag Taxonomy` 段——但只承载解析规则与格式
> 约束（权威定义见 §9.1）；**tag 白名单本体**归 [`wiki/tags.md`](#91-tag-白名单来源)
> 维护，CLI init 不向 AGENTS.md 写入 tag 字典。
>
> **scripts 索引**：SSOT 模板含 `### scripts/ —— 本 wiki 仓的自维护脚本目录` 段，引用
> [`scripts/SCRIPTS.md`](#14-scripts本-wiki-仓扩展脚本目录) 索引；CLI init 必须
> 同时在 AGENTS.md 顶部插入 `@scripts/SCRIPTS.md` import 行（`scripts/` 是 opt-in
> 扩展，不存在不算违规）。

### AGENTS.md（SSOT）

- 路径：`<wiki-root>/AGENTS.md`
- 内容来源：本仓 `references/agents-md-template.md`（**权威 canonical 模板**）
- CLI 按 canonical 模板生成，差异**仅限 4 个 per-wiki 值**（模板替换机制——占位符语法 / 渲染引擎——归 CLI，spec 不规定）：
  - 主题名（用户传入的人类可读字符串，如 `"LLM Systems"`、`"Distributed Systems"`）
  - 创建日期（当天，`YYYY-MM-DD HH:MM`；lint 也接受 `YYYY-MM-DD`，详见 §9 字段说明）
  - wiki spec 版本号（CLI 当前兼容版本）
  - CLI 自身版本号
- 模板顶部说明块的自述（"由 workspace CLI 在初始化时按本 skill 的官方模板拷贝生成"）为
  **自包含措辞**——模板是引用图汇点，**零出边**（不指向任何 skill 仓文件；由
  `check_wiki_fixtures.py` 的 `template-no-outbound-refs` check 强制），CLI **不得修改**

> **纪律正文唯一副本（canonical）**：模板与各 spec 节共享的纪律正文，**唯一维护点在
> [`agents-md-template.md`](agents-md-template.md)**——wiki 跨仓读不到 skill，模板必须
> 自包含，故它就是副本宿主。本 spec / page-templates.md / SKILL.md 只保留各自**独有**
> 内容（机制契约 / rationale / 骨架 / digest + 指针），凡与模板重复的逐字纪律句以
> 「纪律正文见模板 §X」指针代替。**改纪律只改模板对应段 + bump `wiki_spec_version`**；
> spec 侧仅在机制变化时才跟改。引用方向**单向**：spec / page-templates / SKILL.md →
> 模板；模板**不**含任何指向 skill 仓的引用（由 `check_wiki_fixtures.py` 的
> `template-no-outbound-refs` check 机械强制）。
>
> **新纪律归属判据**：写一条新规则前先判它属于哪一层——一句话判据：**它是「wiki 的
> 属性」还是「干活的方法」**（删掉本 skill、换一个维护工具后，这条规则还必须跟着 wiki
> 走吗？）。三个测试任一命中 → 进模板：
>
> 1. **在场测试**——skill 未加载、任何 agent 只打开 wiki 目录时，缺了这条会做错吗？
>    （「做错」限定为 wiki **状态不合法 / 腐烂**——lint 可判定或结构受损；「写得不够好」
>    的写作质量类方法不算，归 skill 侧工作流文件，不进模板）
> 2. **状态测试**——它约束的是 wiki 的**状态**（什么能写 / 什么格式 / 阈值 / 边界），
>    而非做一件工作的**过程**（先做什么 / 用什么命令 / 什么顺序）？
> 3. **人格测试**——它要求任何在这个 wiki 里干活的 agent 都是这类人（习惯 / 口径）？
>
> 偏「过程 / 工具 / 路由」（orient 流程、脚本命令、迁移与评估流程）→ 留 SKILL.md
> （digest + 指针）。灰色案例——log 格式：格式规范与滚动窗口是 wiki 合法状态 → 模板；
> 「正路走 `wiki_write.py log`」模板只留工具名一句，参数 / 源码 / 常量归 skill。

### CLAUDE.md（薄壳）

- 路径：`<wiki-root>/CLAUDE.md`
- 内容来源：本仓 `references/claude-md-template.md`（薄壳模板，`@AGENTS.md` + 声明，≤ 30 行）
- CLI 按薄壳模板生成，差异仅限主题名一个值（不持 spec 版本——版本在 AGENTS.md §八）
- 不含纪律正文；AGENTS.md 顶部 `@MEMORY/MEMORY.md` / `@scripts/SCRIPTS.md` `@import`
  由 AGENTS.md 自身携带，薄壳内**不**再额外挂 import；仅 `@AGENTS.md` 一行

## §3 wiki/index.md

> **维护方**：CLI 在 init 时刻按本节模板创建**初始骨架**；
> 后续所有条目变更由 **LLM agent** 在 ingest / 重写 / 归档时维护。
> CLI 不参与 index.md 的后续更新。

- 路径：`<wiki-root>/wiki/index.md`
- frontmatter（**6 字段必填**）：

| 字段 | 值 |
|---|---|
| `title` | `"<TOPIC_NAME> Index"`（带双引号） |
| `type` | `index`（无引号） |
| `okf_version` | `"0.1"`（OKF 规范版本） |
| `tags` | `[index]` |
| `created` | `YYYY-MM-DD HH:MM`（= today） |
| `updated` | `YYYY-MM-DD HH:MM`（= today） |

- 正文骨架：5 个空类别段（按字母序），各带一句"暂无内容"占位
- **字面量见 fixtures**：`references/fixtures/index.md.txt`

## §4 wiki/log.md

> **维护方**：CLI 在 init 时刻写入首条 setup 条目；
> 后续所有 ingest / query / lint 条目由 **LLM agent** 追加 + 维护滚动窗口（见 §4.1）。
> CLI 不参与 log.md 的后续追加。
>
> **agent 侧使用纪律见模板「log.md」段（canonical 副本）**——本节只留 CLI / 机制契约：
> frontmatter、首条字面量、权威正则、滚动窗口截断实现。

- 路径：`<wiki-root>/wiki/log.md`
- frontmatter（**5 字段必填**，同 §3 但 `type=log`、`okf_version` 不出现）：

| 字段 | 值 |
|---|---|
| `title` | `"<TOPIC_NAME> Log"`（带双引号） |
| `type` | `log` |
| `tags` | `[log]` |
| `created` | `YYYY-MM-DD HH:MM`（= today） |
| `updated` | `YYYY-MM-DD HH:MM`（= today） |

- 首条 log 条目（**CLI init 时刻写**）：

  ```text
  ## [<SETUP_DATE>] setup | Initial scaffold by yzr-llm-wiki-management
  ```

  例：setup 时间为 `2026-07-27 14:30` 时，log 条目为 `## [2026-07-27 14:30] setup | ...`

- **log 条目格式权威正则**（CLI 自检用，未来 lint 也用同一份）：

  ```regex
  ^## \[\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\] (ingest|query|lint|setup) \| .+$
  ```

  > `HH:MM`（`HH:MM:SS` 也合法）可选；`YYYY-MM-DD`（date-only）也合法——lint 按精度宽容解析三种格式。

- 后续条目由 LLM 在 ingest / query / lint 时按相同格式追加，CLI 不必写
- **字面量见 fixtures**：`references/fixtures/log.md.txt`

### §4.1 Log retention（滚动窗口）

> **维护方**：**LLM agent** 在每次写 log 后 + lint 兜底；**CLI 不参与**。log.md 不是
> 完整审计日志——它是**近期活动速览**；完整操作历史靠 git（`git log -p -- wiki/log.md`）。
> 本 skill 假设 wiki 纳入 git 仓（典型为 workspace 级 git）。

- **滚动窗口**：`log.md` 只保**最近 50 条**操作条目（滚动窗口阈值，lint 兜底见下）。按正则
  `^## \[\d{4}-\d{2}-\d{2}\]` 计，不含 frontmatter 与空白行
- **截断时机**（两层）：
  1. **写入时**——`wiki_write.py log` 追加后自动截断保最近 N 条（正路）；
     带外手改（直接 Edit）时由 agent 按本条规则手工截断
  2. **lint 兜底**——lint 在条目数超过上限时报 `log-truncation-recommended`
     （warning），agent 看到后截断
- **删条目规则**：删 frontmatter 之后、最旧的若干 `## [date] op | title` 行；**保留 frontmatter
  全部字段不变**（`created` 永远是首次创建日，不因截断改；`updated` 正常更新）
- **历史回溯**：被删的老条目在 git history 里——`git log -p -- wiki/log.md` 可查任意历史版本。
  未启用 git 的 wiki 老条目会丢失（本 skill 推荐将 wiki 纳入 git 仓）

## §5 MEMORY/

> **维护方**：CLI 在 init 时刻创建**空目录**并按 §5.1 写入 `MEMORY/MEMORY.md`（索引）；
> 后续 MEMORY 下的经验条目 `*.md` 由 **LLM agent** 写入，并**同步追加 MEMORY.md 索引一行**。
> 用户**不**直接编辑 MEMORY——它是 agent 私有记录。
> CLI 不参与 MEMORY 的后续写入。

- 路径：`<wiki-root>/MEMORY/`
- 目录名 `MEMORY` **大写**，区别于 `raw/` `wiki/` `wiki/index.md` 等小写目录/文件——这是为了
  在文件浏览器里一眼区分"agent 私有记忆"与"wiki 内容"
- **`MEMORY/MEMORY.md`（索引）——CLI init 时刻写入**（fixtures 字面量见
  `references/fixtures/memory-index.txt`）；由 `<wiki-root>/AGENTS.md` 顶部一行
  `@MEMORY/MEMORY.md` `@import` 加载到所有读 AGENTS.md 的 agent（加载机制详见 §5.1）
- 其余 `*.md` 经验条目由 LLM 在工作中追加，**文件命名与 wiki 内容页一致**；
  frontmatter 走 §5.2 的 **1 必填（`title`）+ optional 字段**规则（与 wiki 内容页 5 必填
  解耦——MEMORY 是 agent 私有，frontmatter 是可选 decoration）
  （lint 校验实现见 SKILL 仓 `scripts/lint_wiki.py`，不归本 spec）
- **MEMORY 不在 `wiki/index.md` 中强制列出**——它是 agent 私有入口，不需要 wiki 单一入口约束；
  但每条 `*.md` **必须**在 `MEMORY/MEMORY.md` 索引中列出一行（lint `memory-not-indexed` 兜底漏列）
- **条目形式按事实颗粒度选**——完整条目（`MEMORY/<slug>.md` + 索引行）/ 短条目（索引行
  直记）的判别尺度与格式纪律正文见模板「MEMORY/」段（canonical 副本）；本节只补 lint
  语义：`memory-not-indexed` 只兜底"有 .md 但未索引"，不强制反向（短条目无 .md，不进该检查）

### §5.1 MEMORY/MEMORY.md（索引）

- 路径：`<wiki-root>/MEMORY/MEMORY.md`
- **无 frontmatter**——它是**被 `<wiki-root>/AGENTS.md` 用 `@MEMORY/MEMORY.md` `@import` 加载**
  的索引片段，不是 wiki 内容页。lint 把它当 reserved 跳过 frontmatter / tag / 命名校验
- 正文骨架：顶部 1 段说明（本目录用途 + 何时写 / 命名 / 纪律指向 SKILL §4，**不**重复以免口径分裂）+
  `## 索引` 段。索引行两种格式共存：
  - **完整条目**：`- <slug> — <一句话摘要> → [正文](<slug>.md)`（指向 §5.2 的 `MEMORY/<slug>.md`）
  - **短条目**：`- <一句话事实>`（无链接，对应无 `.md` 文件的索引行 reminder）
  - 判别尺度见 §5 总段「条目形式按事实颗粒度选」
- **加载机制（agent 中立；`@import` 收口）**：`<wiki-root>/AGENTS.md` 顶部单行
  `@MEMORY/MEMORY.md` ——自动展开 `@import` 的 agent（经薄壳递归展开 / 原生支持 `@import`）
  透明加载 `MEMORY.md` 全文（SSOT）；不展开 `@import` 的 agent 由 AGENTS.md **顶部强制 Read
  指令**兜底（直接 `Read MEMORY/MEMORY.md`）。所有 agent 都见 L2 索引——AGENTS.md 不持有副本，
  **无**双写漂移 / L1 膨胀风险
- MEMORY 沉淀自由增长——索引活在 `MEMORY/MEMORY.md` 单一真源，AGENTS.md 单行 `@import` 引用不占 L1
  词数预算，无需条数护栏
- **字面量见 fixtures**：`references/fixtures/memory-index.txt`（与 `references/canonical/memory-index.md`
  一致——MEMORY.md 无占位符，fixtures 与 canonical 内容相同）

### §5.2 MEMORY/*.md（非 MEMORY.md）

- 路径：`<wiki-root>/MEMORY/<slug>.md`
- 命名约束：与 wiki 内容页一致，kebab-case `^[a-z0-9][a-z0-9-]*$`
- frontmatter：**1 必填**（`title`），其余 5 字段（`type` / `created` / `updated` / `tags` /
  `description`）全 optional
  - 理由：MEMORY 是 agent 私有记忆，frontmatter 是可选 decoration——短条目即索引行
    reminder、不单独建 `.md`；5 必填的 rationale（description 进 index 摘要、tags 走
    wiki taxonomy、updated 触发 stale 判定等）对 MEMORY 多半不成立（见 spec §5「agent
    私有」定位 + §5.2「与 wiki 内容页的区别」）
  - 若 frontmatter 含 `type`，取值需合法：5 类内容页枚举（`entity` / `concept` / `source` /
    `comparison` / `synthesis`），或 memory 扩展类型（`memory` / `memory-entry`，见下）
- `type` 取值另有 2 类 memory 扩展（与 spec §9 的「5 类内容页 + 2 类 reserved」并列）：
  - `memory`——MEMORY/*.md 自用语义，区别于 wiki 5 类内容页
  - `memory-entry`——`memory` 同义别名
- lint 校验（实现见 SKILL 仓 `scripts/lint_wiki.py`）：
  - **仅 `title` 必填**；其余 5 字段全 optional
  - `type` 若取则必须合法（含 `memory` / `memory-entry`）
  - `tags` 若取则必须是 list
  - **不**走 tag 白名单校验（§9.1 taxonomy 仅约束 wiki 内容页，不渗透到 agent 私有记忆）
  - **不**走 reviewed / pending-review 校验（MEMORY 无「人工 review」语义角色）
  - `MEMORY/MEMORY.md`（索引）**不**参与此校验——本身无 frontmatter，是被
    `AGENTS.md` 用 `@MEMORY/MEMORY.md` `@import` 加载的索引片段
- 与 wiki 内容页的区别：
  - **不**强制在 `wiki/index.md` 列出
  - **不**要求有 inbound 链接
  - 正文无长度上限（agent 经验沉淀可以很长）
  - LLM agent **必须**创建（user 不写）
  - **必须**在 `MEMORY/MEMORY.md` 索引列出一行（新增；lint `memory-not-indexed` 兜底）

## §6 .gitignore

`.gitignore` **无论是否 opt-in git 都生成**（无 git 时是无害空操作，便于后续补 git）。完整字节
SSOT 在 [`references/fixtures/gitignore.txt`](fixtures/gitignore.txt)——CLI 按该文件逐字
落盘，`scripts/check_wiki_fixtures.py` 的 `gitignore-init-rules-complete` check 做字段级
骨架比对。**必含 4 段**：OS / 编辑器忽略 / Obsidian 配置 / 临时文件 / 外部代码仓 symlink
（保留 `raw/external/.symlink-anchor.toml` 元数据）；**必不**忽略 `wiki/`、`raw/`
（除 `raw/external/*` 例外）、`CLAUDE.md`、`.gitignore` 自身。

## §7 Git 初始化（opt-in，默认跳过）

> **立场**：wiki **不依赖 git 即可工作**——默认落盘为**纯目录树**。git 是用户显式 opt-in 的事，
> 用于版本控制 / history / diff。即便不启用 git，后续所有 ingest / query / lint 仍正常运行
> （lint 的 raw/ 不可变性检查在无 git 时自动跳过——没有 git 就没有"未提交改动"概念）。

- **无论用户是否打算 opt-in git**：CLI **完全不碰 git**——不 init、不 add、不 commit、不提供任何 git
  操作入口。wiki 作为纯目录树落盘；即使用户想启用 git，CLI init 也只落盘文件结构 + 提示用户自行操作
  git（红线——CLI/agent 流程不主动操作 git；是否提供 opt-in 开关、开关叫什么，归 CLI，spec 不钉）。
- **CLI 必须做的工作（init 时刻）**：
  1. 落盘 wiki 骨架目录结构——至少含 `raw/{articles,assets}/`、5 个 wiki 内容子目录、`MEMORY/`、
     `scripts/`（见 §1）。`raw/` 下是否额外预建有专门语义的子树（如 `discussions/`）由实现自定，
     非语义要求
  2. 拷贝 SSOT 模板到 `<wiki-root>/AGENTS.md` / `CLAUDE.md` / `wiki/index.md` /
     `wiki/log.md` / `wiki/tags.md` / `MEMORY/MEMORY.md` / `scripts/SCRIPTS.md` / `.gitignore`
  3. **空目录占位策略由实现自定**（`.gitkeep` / 别的方式均可），但有一个正确性约束：
     git 跟踪的 wiki 里 `raw/` **至少要有 tracked 内容**，否则 `raw-modified` lint 永远 0 命中
     （检测不到 raw 被违规改）。`raw/articles/`、`raw/assets/` 等占位子目录的存在即可满足此约束；
     预建哪些子目录、是否为其放占位文件，都是实现自由，非语义要求

- **CLI 应提示用户如何自行 opt-in git**：init 后告知用户 wiki 已落盘为纯目录树、如需版本控制由用户
  手动 `git init` + 首次 commit、空目录占位策略（见下）。**具体提示文案与建议命令归 CLI**（红线不变——
  CLI 自身不执行这些 git 操作）；空目录占位策略也由实现自定（`.gitkeep` / 别的方式均可）

- **不得**对已存在的 git 仓误调 `git init`（反向边界——CLI 本就不主动 git init，正常流程无触发机会）。

## §8 拒绝条件（强约束）

CLI 在以下情况必须拒绝并退出（**非零退出码**）：

| 触发条件 | 错误信息建议 |
|---|---|
| `<wiki-root>/AGENTS.md` 已存在 | `"<wiki-root>/AGENTS.md 已存在；拒绝覆盖（schema 是用户所有）..."` |
| `<wiki-root>/CLAUDE.md`（薄壳）已存在 | `"<wiki-root>/CLAUDE.md 已存在；拒绝覆盖..."` |
| `<wiki-root>/wiki/index.md` 已存在 | `"<wiki-root>/wiki/index.md 已存在；拒绝覆盖。..."` |

**绝不允许覆盖已有 wiki**。用户想重新初始化必须先手动备份 + 删除。

## §9 Frontmatter 字段全集（CLI 引用，非生成内容页）

CLI **不**生成 `wiki/{entities,concepts,sources,comparisons,syntheses}/` 下的内容页（由 LLM 在 ingest 时写）。
但 spec 必须明确字段全集，CLI 在做合规性自检（如对初始化产物做校验）时引用：

> **为什么是这 5 个**：5 字段是 OKF §9「字段齐全性」与 lint 校验一致性的最小交集——
> `title`（人/grep 找页）、`type`（决定子目录 + lint 校验路径）、`created` / `updated`（stale / orphan 判定）、
> `tags`（taxonomy 过滤）。少于 5 字段会让"抓腐烂"判定失效；多于 5 字段 OK 但不强制。
> 推荐 `description`（一句话摘要，`index.md` 条目摘要从它来——OKF §4.1）。

### 通用必填字段（5 项）

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 人类可读标题，不含扩展名 |
| `type` | enum | 见下方 `type` 取值 |
| `tags` | array | 可空数组 |
| `created` | date | `YYYY-MM-DD HH:MM`；lint 也接受 `YYYY-MM-DD` |
| `updated` | date | `YYYY-MM-DD HH:MM`；lint 也接受 `YYYY-MM-DD` |

### `type` 取值（5 类内容页 + 2 类 reserved）

| `type` | 目录 | 备注 |
|---|---|---|
| `entity` | `entities/` | 实体页 |
| `concept` | `concepts/` | 概念页 |
| `source` | `sources/` | 资料页 |
| `comparison` | `comparisons/` | 对比页 |
| `synthesis` | `syntheses/` | 综合页 |
| `index` | `wiki/index.md`（唯一） | reserved，仅标记用，lint 跳过 |
| `log` | `wiki/log.md`（唯一） | reserved，仅标记用，lint 跳过 |

字母序约束与目录同：`comparison` → `concept` → `entity` → `source` → `synthesis`。

### §9.1 tag 白名单来源

`tags` 字段允许的取值集合**不在**本页规定的 type / sources 等字段里——它来自另一个非
内容页文件，避免 wiki 内容页 schema 与 tag 字典混在一起：

- **主流位置**：`<wiki-root>/wiki/tags.md`——LLM agent 拥有，**裸 bullet 列表，
  无 frontmatter**；CLI init 时刻按 `references/fixtures/` 生成空白模板，agent 在
  ingest / query 过程中自动追加新 tag
- **fallback**（`wiki/tags.md` 缺失时）：`<wiki-root>/AGENTS.md` 的 `### Tag Taxonomy`
  段——`lint_wiki.py --check-version --apply` 可把 tag 字典迁到 `wiki/tags.md`
- 解析规则、bullet 格式约束、`tag-not-in-taxonomy` lint 行为权威定义在
  [`agents-md-template.md`](agents-md-template.md)「Tag Taxonomy」段；
  SKILL 仓 `scripts/lint_wiki.py` 是实现 SSOT

**为什么 tag 白名单独立成 `wiki/tags.md`**：

1. 纪律 SSOT（`AGENTS.md`）是用户写的 schema "宪法"，LLM 不应编辑（见 `wiki-spec.md` §2）；tag 白名单
   是内容元数据，LLM 拥有 + 随 ingest 自动扩更合理
2. tag 字典漂移不应触发 schema 漂移告警；独立文件后 tag bullet 增减不误判 spec 版本漂移
3. 与 `MEMORY/MEMORY.md`（无 frontmatter、agent 私有记忆）形态对齐——元数据不归类到
   wiki 内容页

### 类型特化字段（LLM 写内容页时使用）

| 字段 | 适用 type | 必填 | 含义 |
|---|---|---|---|
| `sources` | `source` / `synthesis` | 是 | source 页是 `raw/` 下路径数组（**最外层 `<wiki>/` 相对**，如 `raw/articles/x.pdf`）；synthesis 页是 wiki 内其它页路径数组（**内容根 `wiki/` 相对**，如 `concepts/transformer.md`） |
| `aliases` | `entity` | 否 | 别名数组，方便搜索 |
| `related` | `concept` | 否 | 相关概念路径数组（**内容根 `wiki/` 相对**，见下方路径格式约定） |
| `compared` | `comparison` | 否 | 被对比对象路径数组（**内容根 `wiki/` 相对**，见下方路径格式约定） |
| `threads` | `synthesis` | 否 | 线索标题数组 |

#### 路径格式约定

frontmatter 内**指 wiki 内内容页的字段**（`related` / `compared`，以及 synthesis 页
`sources`）统一使用 **内容根 `wiki/` 相对路径**——以 `<wiki>/wiki/` 为基准（即去掉
最外层 `<wiki>/` 与其下 `wiki/` 两段）的 POSIX 风格路径，不带前导 `./`、不带 `../`
跨目录、**也不带 `wiki/` 前缀**。（注意：source 页 `sources` 指 `raw/` 资料时走**最外层
`<wiki>/` 相对**基准，形如 `raw/articles/x.pdf`——两类基准刻意区分，勿混用。）例：

```yaml
# wiki/concepts/self-attention.md frontmatter
related:
  - concepts/transformer.md
  - concepts/multi-head-attention.md
  - concepts/scaled-dot-product-attention.md
```

```yaml
# wiki/comparisons/transformer-vs-mamba.md frontmatter
compared:
  - concepts/transformer.md
  - concepts/mamba.md
```

裸文件名（`transformer.md`）、文件相对路径（`../concepts/transformer.md`）、以及误带
`wiki/` 前缀（`wiki/concepts/transformer.md`，会解析出双 `wiki/` 段）都**不**被 lint
接受——第一种跨目录引用时信息不完整；第二种与正文 Markdown 链接约定（`AGENTS.md`
§三.5，文件相对）混淆、跨目录改动易断裂；第三种与 source 页 `sources` 的最外层基准
歧义。

**为什么指 wiki 内页的字段用内容根 `wiki/` 相对、与正文链接形成两层约定**：

- **指 wiki 内页的 frontmatter 字段**（`related` / `compared` / synthesis `sources`）
  ——机器消费为主（lint 校验、cross-page 综合）；统一内容根 `wiki/` 相对，**LLM 写时
  一次声明、跨子目录生效**，移动页面不会因相对路径断裂
- **正文 Markdown 链接**（`[text](path)`）——人读为主，in-context 局部引用；保持
  文件相对，**让单页可视化阅读时不依赖 wiki 根位置**

**lint 兜底**：`related-broken-link`（warn 级）——校验 `related` /
`compared` 字段每条元素是否能在 wiki 根下解析到现存文件；详见
[`lint-checklist.md` §二.15](lint-checklist.md#15-related--compared-路径引用完整性)。

### 可选可信度与认知质量字段（LLM 按需写，全部可选）

> 字段语义权威定义在 [`agents-md-template.md`](agents-md-template.md) §二「认知质量信号」
> （canonical 副本）；本表只列 CLI 自检用的字段类型，不重复语义。CLI 自检不要求这些字段存在——
> `reviewed` / `reviewed_at` 是人工审核背书信号，`contested` / `contradictions` 是
> 认知冲突未裁定告警；两类正交。

| 字段 | 适用 type | 必填 | 含义 |
|---|---|---|---|
| `reviewed` | 任意内容页 | 否 | 仅 `true` 时写；人工已审核该页的可信度背书 |
| `reviewed_at` | 任意内容页 | 否 | `YYYY-MM-DD`；与 `reviewed: true` 成对出现 |
| `contested` | 任意内容页 | 否 | 仅 `true` 时写；本页含未解决的矛盾主张，需复审 |
| `contradictions` | 任意内容页 | 否 | wiki 页路径数组；与本页主张冲突的页面（双向标注） |

**生命周期规则**（LLM 必读，CLI 不强制但 CLI 合规自检可加 `reviewed-stale` 检查）：
纪律正文（背书快照非永久标签 / LLM 修改必删戳）见模板 §二「认知质量信号」（canonical
副本）；本节只留 lint 语义：`reviewed: true` 存在且 `updated > reviewed_at` 时给 warn。

完整 frontmatter 写法约束与 YAML 子集要求，**不在本 spec 范围内**——见 SKILL 仓的
[`page-templates.md`](page-templates.md)（LLM 写作视角，非 CLI 视角）。

## §10 版本钉死

**设计不变量**：AGENTS.md 必须记录本 wiki 创建时对齐的 wiki spec 版本 + CLI 版本（薄壳 CLAUDE.md 不持版本），
使 skill `migrate` 能探测版本漂移。具体承载形式（AGENTS.md §八 表）+ 模板替换机制（占位符语法 /
渲染引擎）+ 版本号来源（CLI 内部机制）都归 CLI，spec 不规定。「CLI 记录的 spec 版本是否与 SKILL
当前版本对齐」由 `check_wiki_fixtures.py` 校验（读取契约的可执行 gate）。

spec 版本号的 SSOT 是 SKILL 仓 `SKILL.md` 的 `metadata.wiki_spec_version` 字段（本 spec 不重复钉号，
避免双源漂移）。CLI 仓与 spec 版本对齐是 CLI 仓的责任；spec 变更时 SKILL 仓升 `wiki_spec_version`，
CLI 仓跟随升级。

**LLM 在每次操作前比对** AGENTS.md §八（无 AGENTS.md 时 fallback CLAUDE.md §八）的 "Wiki Spec 版本" 与 SKILL.md
`metadata.wiki_spec_version`；不一致时**警告用户**（不阻断——CLI 可能支持多个 spec 版本）。

### §10.1 AGENTS.md 模板同步

`AGENTS.md` 的 per-wiki 变量只有 4 个——主题 / 创建日期 / CLI 版本 / Wiki Spec 版本
（全在 H1 + §八 表格）；正文 §一~§七 + §九 是纪律文本，跨 wiki 逐字相同。因此一致性校验
**不**做"存在性断言"，做**模板渲染字节比对**：

- `check_wiki_fixtures.py` 的 `agents-md-template-sync`（error）：从 wiki §八 提取
  主题 / 创建日期 / CLI 版本（主题 fallback H1 `# <主题> Wiki — LLM 维护守则`）+
  wiki 自钉 spec 版本，渲染 `references/agents-md-template.md` 后与 wiki 实际 AGENTS.md
  字节比对——任何不一致（旧版本残留 / 本地改动）都报错。
- 修复 = **全量重渲染**（plan action `fixtures-fix-agents-md-resync`）：§八 变量保留旧值
  （wiki spec 版本用迁移目标版本），其余以模板渲染稿为准——**不**做局部 Edit。
  旧文件中多出的本地定制行/段由 agent 逐条列给用户裁定：搬 `MEMORY/`（一行事实写
  MEMORY.md 索引短条目；含 why 的建 `MEMORY/<slug>.md` 完整条目 + 索引行）或丢弃。
- **纪律推论**：本 wiki 特有纪律 / 偏好一律沉淀到 `MEMORY/`（由 AGENTS.md 顶部
  `@MEMORY/MEMORY.md` `@import` 加载，会话常驻），不写进 AGENTS.md——否则下次升级
  重渲染时丢失。
- 与 `agents-version-is-current` 正交：版本行新旧由后者管；本 check 渲染时用 wiki
  自钉的 spec 版本替换版本变量，只比"正文与模板同步"。

## §11 命名约束（影响 CLI 生成的产物）

| 维度 | 规则 | 适用对象 |
|---|---|---|
| 文件名 kebab-case | `^[a-z0-9][a-z0-9-]*$` | `wiki/{entities,concepts,sources,comparisons,syntheses}/*.md` + `MEMORY/*.md`（index/log/tags/MEMORY.md 除外） |
| 子目录名 | 固定字母序（§1） | 5 个内容页子目录 |
| 特殊目录名 `MEMORY` | **大写**（区别于小写 `raw` / `wiki` 等）；与 `wiki/` 平级（不再嵌在 `wiki/` 下） | `<wiki-root>/MEMORY/` |
| 元数据文件 tags.md | 与 index.md / log.md 同——**无** frontmatter，裸 Markdown；lint 不走 frontmatter 校验（按 `MEMORY.md` 同形态） | `wiki/tags.md` |
| 索引文件 SCRIPTS.md | 与 tags.md / MEMORY/MEMORY.md 同——**无** frontmatter，裸 Markdown；由 `<wiki-root>/AGENTS.md` 顶部 `@scripts/SCRIPTS.md` `@import` 加载 | `scripts/SCRIPTS.md` |
| frontmatter 字段名 | 严格小写 + 下划线（`okf_version`、`created`、`updated`） | 所有 frontmatter |
| frontmatter `type` 值 | 严格小写（5 类内容页 + 2 类 reserved：`index`/`log`） | 所有 wiki 页 |

CLI 生成的产物必须满足以上规则；否则后续 lint 会立即报错。

## §12 不在本 spec 范围内

以下事项不由本 spec 定义（`wiki_metadata.toml` 字段 schema 归 CLI；运行时规则归 SKILL 仓）：

- **`wiki_metadata.toml` 字段全集 schema**——归 CLI 代码 SSOT，本 spec 只描述 skill 读取契约（见 §1.1）
- raw/ 是否 LLM 只读、用户可改的纪律
- ingest / query / lint 的工作流
- frontmatter 字段的语义（如 `description` 推荐写法）
- 类型特化字段的内容（如 `aliases` 写什么）
- 跨页交叉引用的语义
- 半定性 lint（矛盾、缺失交叉引用等）
- 是否使用 Obsidian / 编辑器偏好

## §13 raw/external/——外部代码仓接入（可选）

> **维护方**：**用户**。CLI 不管理其内容；目录何时创建是实现的自由（见 §7），本节
> 只定义它存在时的语义。用户通过 LLM agent 协助或自行用 `ln -s` + 手写/追加
> `.symlink-anchor.toml` 接入。

外部代码仓（如 Linux kernel、Ray 源码）作为原始语料纳入 wiki 时，**不**做仓库内嵌
拷贝（避免占用空间），而是走 **symlink + 锚定元数据**：

### §13.1 路径约定

```text
<wiki-root>/raw/external/
├── .symlink-anchor.toml           # 必填：TOML，[[entry]] 数组描述所有外部仓
├── linux-kernel                     # symlink → ~/src/linux-kernel
├── ray                              # symlink → ~/src/ray
└── ...
```

- **扁平结构**：所有外部仓的 symlink 直接放在 `raw/external/` 下，**不再**用
  `<source-name>/` 子目录分组。anchor 文件**单文件**记录所有 entries。
- **symlink 命名**：必须 kebab-case `^[a-z0-9][a-z0-9-]*$`（与 wiki 内容页命名一致）
- **anchor 文件位置**：固定 `<wiki-root>/raw/external/.symlink-anchor.toml`
- **anchor ↔ symlink 关联**：每个 `[[entry]]` 的 `symlink` 字段对应 `raw/external/`
  下同名的 symlink 文件；该 symlink 缺失 → lint 报 `external-symlink-missing`；
  反之 anchor 中没记录该 symlink → lint 报 `external-anchor-orphan`
- 同一 target 的多个 subpath：直接创建多个 symlink（每个 symlink 一行 entry），
  无需 `subpath` 字段间接表达

### §13.2 `.symlink-anchor.toml` Schema（必填 + git 身份字段可选）

**顶层 `schema_version`（可选，推荐）**：`schema_version = 1`——为未来 schema 演进留口子。

**顶层 `[[entry]]` 数组**——每个元素描述一个外部仓：

```toml
schema_version = 1

# linux-kernel 仓
[[entry]]
symlink = "linux-kernel"           # 对应 raw/external/linux-kernel symlink
target = "~/src/linux-kernel"      # 推荐 ~/... home-relative
captured_at = "2026-07-07"         # 接入当天
kind = "external-repo"             # 当前唯一支持的 kind
remote_url = "https://github.com/torvalds/linux.git"  # git 身份字段（可选）
branch = "master"                  # git 身份字段（可选）

# ray 仓
[[entry]]
symlink = "ray"
target = "~/src/ray"
captured_at = "2026-07-05"
kind = "external-repo"
remote_url = "https://github.com/ray-project/ray.git"
branch = "master"

# notes 字段可选
[[entry]]
symlink = "my-til"
target = "~/src/my-til"
captured_at = "2026-07-01"
kind = "external-repo"
notes = "个人 TIL 仓库，按需重 ingest"
```

**每 entry 最小必填 4 字段**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `symlink` | kebab-case string | 是 | 对应 `raw/external/` 下同名的 symlink 文件名 |
| `target` | string（绝对路径 **或** `~/...` home-relative 形式） | 是 | 推荐 `~/src/<name>` 形式以跨主机可移植；**也接受** `readlink -f <symlink>` 输出的绝对路径。lint 在判定前统一 `Path(target).expanduser()` 展开——绝对路径展开后不变，`~/...` 展开为 `$HOME/...` |
| `captured_at` | date `YYYY-MM-DD` | 是 | 用户接入当天；用于提示"target 路径多久前定锚" |
| `kind` | enum | 是 | 当前仅支持 `"external-repo"`；预留给以后扩展（`"snapshot"` 等） |

**git 身份字段（可选，推荐）**（当 `target` 指向 git 仓时——跨机器重建软链接用）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `remote_url` | string | 可选（推荐） | `git -C <target> remote get-url origin` 输出；用于跨主机重建时 `git clone` |
| `branch` | string | 可选（推荐） | `git -C <target> rev-parse --abbrev-ref HEAD` 输出；辅助重建时选分支 |

**不**记 `commit`。

**可选字段**（任何场景都不强制）：`notes`（自由文本，记录接入原因）。

> **为什么 target 字段允许 `~/...` 而不是硬要求绝对路径**：`target` 字段
> 进 git，但**不**必须是机器相关绝对路径——推荐写 `~/src/<name>` 形式
> 让同 home 布局的多机共享同一 anchor；`~/...` 跨 home 布局失效时降级到
> `remote_url` + `branch` 重建（详见 `external-repo-rebuild.md`）。
> lint 端用 `Path(target).expanduser()` 统一展开，**不**关心 anchor 写哪种形式。
>
> **为什么选 TOML 而不是 JSON**：① 支持 `# ...` 注释——LLM / 用户
> 手写时易读、易解释每段含义；② `[[entry]]` array-of-tables 是表达「多 entry」的
> 原生 TOML 语法，比 JSON array + 每个 entry 重复字段名更紧凑；③ 与项目既有
> `workspace.toml` / `wiki_metadata.toml` 风格一致；④ 标准库即可解析，零运行时依赖。

### §13.3 责任切分（用户 + LLM 共有）

**用户责任**：

- 决定**接入哪些**外部代码仓（意图层面）
- symlink target 的存活——target 被删除 / 改名 / 移动后 anchor 仍记录
  旧路径，lint 报 `external-target-dead` 让用户感知
- 感知内容是否过期——外部仓活跃演进时，wiki 摘要是否重 ingest 由用户判断
  （anchor **不**记 commit，无自动漂移检测）

**LLM agent 责任**（首次接入 + 漂移刷新）：

- **创建 symlink + 追加 entry**——当用户说"把 X 仓纳入 wiki"时，LLM 主导：
  1. 与用户确认 symlink 名（如 `linux-kernel`）+ target 路径
  2. 验证 target 是 git 仓（`git -C <target> rev-parse --is-inside-work-tree`）
  3. 读 `remote_url` / `branch` 两个值（git 命令）
  4. `mkdir -p raw/external && ln -s <target> raw/external/<symlink>`（**扁平**，
     不要在 `external/<source-name>/` 下再开子目录）
  5. **读**现有 `.symlink-anchor.toml`（如有）；**追加**新 `[[entry]]` 块；
     **写回**整个文件；首次创建则写完整文件含 `schema_version = 1` 顶层字段
- **更新 entry 的 `target` 字段**（重建到新主机时——见 `external-repo-rebuild.md`）
- **不**在 wiki 维护操作（ingest / query / lint / migrate）中修改 target 本身——
  librarian 角色下 target 仓内文件只读（外部仓是用户所有；不在仓内跑 `git pull` 之类）。
  **用户明确要求的开发协作**（修 bug / 重构 / 仓内 git 操作）**不**属 wiki 操作、**不**受
  raw/ 只读约束——target 在 wiki 仓外、有其自身 git、由用户全权处置。代码改动后的 wiki
  同步走**既有通道**（用户确认 → 受影响 source 页重 ingest），**不**为此加新机制。
  **禁止**以"开发协作"为借口在 wiki 维护操作中顺手改 target——角色切分是放行真·开发任务，
  不是给 librarian 开后门
- **不**编辑 `raw/external/` 之外的 `raw/` 子树（articles / papers / assets /
  clippings 等仍走"LLM 只读"纪律；`discussions/` 是另一处写权限例外——见 §15）
- lint 报 `external-anchor-missing` / `external-anchor-corrupt` /
  `external-anchor-orphan` / `external-symlink-missing` 时由 LLM 引导用户重写
- **`sources:` 元素类型**——`raw/external/<symlink>/...` 形式的
  sources 可指向**文件或目录**：symlink 目标本身是 git 仓（即目录），可用作整仓
  语料（`raw/external/<symlink>`）；也可指向仓内子路径（文件或子目录）。lint
  仅校验可访问性（`sp.exists()`），不做 file-only 约束。普通 raw 路径（非
  `raw/external/`）的 sources 仍要求指向**文件**（lint 用 `is_file()` 校验）——
  raw 子树语义是"已 ingest 的文档"，目录型 raw 来源暂无用例

> **为什么改"LLM 不写"为"LLM 主导接入"**：外部代码仓接入是结构化操作
> （固定 schema + 固定 git 命令序列），由 LLM 主导可避免用户手动跑
> `ln -s` + 手写 anchor 时出错；范围**仅**限 `raw/external/`，其他
> `raw/` 子树仍只读。

### §13.4 .gitignore 增强

`.gitignore` 在 §6 的基础上追加以下规则（CLI init 时一并生成）：

```gitignore
# 外部代码仓 symlink 接入（不跟踪 symlink 本身，但保留 anchor 元数据）
raw/external/*
!raw/external/.symlink-anchor.toml
```

> **理由**：symlink 会被 git 当成 symlink 记录（指向一个不可解析的 target，跨机器
> clone 时毫无意义），而 `.symlink-anchor.toml` 是真实文件、记录"接入意图"——
> `!` 否定号让 anchor 文件被跟踪。跨机器 / 跨 home 布局的重建协议详见
> [`references/external-repo-rebuild.md`](external-repo-rebuild.md)。

### §13.5 git 身份字段（可选）

anchor 的 `remote_url` / `branch` 是**可选**的 git 身份字段——记录"接入意图"（这本来
指向哪个远端、哪个分支），供跨主机重建软链接时 `git clone`。**不**记 `commit`。

- lint **不**校验 git 身份字段
- `target` 不在 git 仓内（如手动下载的源码包、未初始化的目录）时，身份字段
  可整块省略；在 git 仓内时推荐记 `remote_url` + `branch`（重建靠它们）
- anchor 中遗留的旧字段（如 `commit`）解析时忽略、不报错
- "摘要是否过期"不做自动检测——由用户判断（用户知道自己的仓库何时有大改动，
  届时说"重新整理一下 X"即可）

> 重建协议详见 [`references/external-repo-rebuild.md`](external-repo-rebuild.md)——
> `remote_url` + `branch` 是跨机器 clone 后还原"接入意图"的身份信息；不还原到
> 精确 commit（wiki 跟随活跃仓的 live 状态，而非某个历史快照）。

### §13.6 anchor 结构迁移（手工）

`raw/external/` 采用扁平 + 单 TOML anchor 形态（§13.1）。非扁平布局 / JSON anchor 等
结构差异由 `lint_wiki.py --check-version --apply` **手工**迁移（差异大、自动迁移易出错）；
步骤见 [`migrate-workflow.md` §六](migrate-workflow.md#六语义合并规则)（§6.3）；
版本演进历史见 git log（`git log --follow -- yzr-llm-wiki-management/references/wiki-spec.md`）。

---

## §14 scripts/——本 wiki 仓扩展脚本目录

> **维护方**：CLI 在 init 时刻**始终创建** `scripts/` 目录 + 拷贝空 `SCRIPTS.md`
> 骨架（参考 `references/fixtures/scripts.md.txt`）；后续**用户 + LLM agent 共有**
> ——用户可手写 / LLM agent 可补——只要维持 `SCRIPTS.md` 索引同步。
>
> **agent 侧使用纪律见模板「scripts/」段（canonical 副本）**——本节只留机制契约与
> 实现细节（路径 / 索引骨架 / 4 要素 / 权限 / 原子更新）。

### §14.1 设计动机

- skill 自带脚本（`scripts/lint_wiki.py` / `ingest_diff.py` / `log_format.py`）
  满足**通用**wiki 工作流；本 wiki 个性化的扩展（批量 PDF prep、特定主题的
  ingest 模板、外部 CLI 胶水、自动 hook）**不**适合 ship 进 skill 仓
- 走**用户/项目级别**就地维护——既享受 git tracking 又不被 skill 版本约束

### §14.2 路径约定

```text
<wiki-root>/scripts/
├── SCRIPTS.md                  # 必填：索引；其 ## 索引 段 one-liner 列表
│                               # 由 AGENTS.md 顶部 @scripts/SCRIPTS.md @import
│                               # 加载（详见 §14.3）
└── <user scripts>              # 任意文件名 / 嵌套子目录（按工具性质自组织）
```

- **路径**:顶层 `<wiki-root>/scripts/`,与 `raw/` `wiki/` 同级
- **不**为 scripts/ 预创建空 `.gitkeep`——目录由 CLI 必须创建(避免"目录存在但空"
  的歧义;若用户 opt-in git,`SCRIPTS.md` 是真实文件足以让目录被 git 跟踪)
- 子目录 / 文件命名**不限**(`foo.py` / `pdf-prep.sh` / `hooks/pre-commit.sh`
  / `batch/N-papers/main.py` 都可)——scripts/ 不是 wiki 内容页,不走 §11 kebab-case 约束

### §14.3 索引 `SCRIPTS.md`（AGENTS.md 顶部 `@import` 加载）

- **文件名**:`SCRIPTS.md`(大写,镜像 `MEMORY/MEMORY.md` "目录专属索引" 命名模式)
- **路径**:`<wiki-root>/scripts/SCRIPTS.md`
- **形态**:**无 frontmatter**(与 `MEMORY/MEMORY.md` 同),纯 Markdown
- **加载机制（agent 中立；`@import` 收口）**：`<wiki-root>/AGENTS.md` 顶部单行
  `@scripts/SCRIPTS.md` ——自动展开 `@import` 的 agent 透明加载 `SCRIPTS.md` 全文；
  不展开 `@import` 的 agent 由 AGENTS.md 顶部强制 Read 指令兜底（同 §5.1）。所有 agent 都见
  scripts 索引——AGENTS.md 不持有副本，**无**双写漂移 / L1 膨胀风险
- **形态**：单段 `## 索引`（既是 AGENTS.md `@import` 加载源、又是 LLM agent Read 的入口），
  每脚本一段：`` - `<name>` — <一句话用途> `` one-liner 起头 + `### <name> — <label>` 子节
  含 4 要素（使用场景 / 调用约定 / 作用 / 可选前置依赖）——`@import` 加载后 agent 全文
  Read 即可，**不**需要在 AGENTS.md 单独投影 one-liner
- **更新纪律**：脚本增删时**只改这一份**（`scripts/SCRIPTS.md`）——AGENTS.md 单行
  `@import` 引用同步指向 `SCRIPTS.md` 全文，**不**需要再同步 AGENTS.md
- **骨架**（CLI init 时刻拷贝）——字面量模板进 `references/fixtures/scripts.md.txt`
  （字节权威，本 spec 不复制）；形态：无 frontmatter、`## 索引` 单段（one-liner +
  4 要素子节），见 §14.4
- **无**占位符——SCRIPTS.md 是 wiki 内的"脚本契约",与 `MEMORY/MEMORY.md` / `wiki/tags.md`
  同族(均无 frontmatter、wiki 名由 AGENTS.md §一承载,SCRIPTS.md 不重复)

### §14.4 每工具一段的契约(LLM / 用户共同维护)

SCRIPTS.md 内的"分节契约"采用 `### <name> — <label>` 子节(在 `## 索引` 段下)，
每条必含 4 个要素(顺序任意;lint 不解析但风格一致):

| 要素 | 例子 | 用途 |
| --- | --- | --- |
| **使用场景** | "用户给出 N 个 PDF 想一次摄取; 或 `ingest_diff.py` 返回 ≥ 3 个 untracked" | agent 触发条件(口吻匹配"何时该调") |
| **调用约定** | `python3 scripts/<name>.py "<wiki-root>" [args]` | 一行可粘贴;wiki-root 的传递方式（环境变量 / 位置参数 / cwd）按 SKILL/CLI 既有约定，spec 不钉 |
| **作用** | "本脚本做一次聚合 ingest:per-N 调一次 ingest,完成后用 `--bulk-rebuild-index` 一次性更新" | 解释做什么、产出什么、副作用范围 |
| **前置依赖**(可选) | "需 `pip install pypdf`;需环境变量 `PAPERS_DIR`" | 显式声明非标依赖,避免 agent 误跑 |

每脚本以 `` - `<name>` — <一句话用途> `` one-liner 起头（同时充当 AGENTS.md `@import` 投影、
agent Read 时第一眼看到的 hook），下面紧跟 4 要素段落——只活一份，单段形态（`@import`
加载后 agent 全文 Read 即可）。

### §14.5 纪律(硬化约束)

- **git**:默认跟踪(用户 opt-in git 时随 wiki 仓一起 commit;不 opt-in 时跟 wiki 同走纯目录树);
  §6 `.gitignore` 模板**不**额外排 `scripts/` ——不写例外规则
- **frontmatter**:**不**写——scripts/ 是代码,非 wiki 内容页(`scripts/*.py` 走 PEP 723
  inline metadata 或 shebang,不由本 spec 规定)
- **lint**:scripts/ **不**参与 `lint_wiki.py` 扫描（扫描自然不递归
  `scripts/`,且 §9 5 必填只对 `wiki/{entities,concepts,sources,comparisons,syntheses}/*.md`
  与 `<wiki-root>/MEMORY/*.md` 走）——脚本的代码质量由用户 / agent 自行负责,
  不在 SKILL 范围内
- **可执行权限**:`.sh` 必须 `chmod +x`(CLI 不批量 chmod,免得给用户跑陌生 binary
  留通道);`.py` 走 `python3 scripts/<name>.py` 不依赖 +x
- **不安全默认**:agent **不会自动遍历** `scripts/` 跑任何东西——必须先 `Read` SCRIPTS.md
  找到对应段,再显式调用。SCRIPTS.md 是唯一的"我知道有谁"通道,**防止意外执行**
- **SCRIPTS.md 更新纪律**:"添加 / 修改 / 删除脚本文件" 与 "同步更新 SCRIPTS.md" 是
  原子动作——stub 段先写还是脚本文件先写由维护者决定,但**完成时两者必须同时一致**

### §14.6 与已有索引模式对照

| | `MEMORY/MEMORY.md` | `wiki/tags.md` | `scripts/SCRIPTS.md` (本) |
| --- | --- | --- | --- |
| AGENTS.md 加载方式 | 顶部 `@MEMORY/MEMORY.md` `@import` 自动展开 | 不内联——LLM 不需要看完整 tag 字典；按需 `Read` | 顶部 `@scripts/SCRIPTS.md` `@import` 自动展开 |
| 形态 | 无 frontmatter | 无 frontmatter | 无 frontmatter |
| 维护方 | LLM agent | LLM agent(用户审计) | 用户 + LLM agent |
| 列举对象 | 一行一条 MEMORY 条目 | 一行一条 tag | 一段一条工具（4 要素契约） |
| 类别 | 知识 | 标签白名单 | 代码索引 |

---

## §15 raw/discussions/——协作草稿层（可选）

> **维护方**：**用户 + LLM 共有**。CLI 不管理其内容（草稿由双方按需填充）；目录何时创建
> 是实现的自由（见 §7），本节只定义它存在时的语义。
>
> raw/ 总纪律是"LLM 只读，用户掌控"（§四层架构第 1 层）。本节定义该纪律的**第二处**
> 写权限例外（第一处是 §13 `raw/external/` 的 symlink + anchor）：一个用户 + LLM
> **双方可写**的草稿层，承载临场讨论 / 设计草稿 / 待整理笔记。
>
> **agent 侧纪律（可写性 / 豁免 / 归档两路 / 滑坡防线的日常执行版）见模板
> 「raw/discussions/」段（canonical 副本）**——本节只留机制契约与 rationale（脚本豁免
> 实现 / 为什么放 raw/ 下 / 归档细则）。

### §15.1 动机与边界

| 维度 | 规则 |
| --- | --- |
| 路径 | `<wiki-root>/raw/discussions/`（存在时适用本节语义；fresh init 是否预建由实现定——见 §7） |
| 谁可写 | 用户 + LLM **双方**可创建 / 编辑 / 删除——raw/ 内除 §13.3 外唯一 LLM 可写子树 |
| 性质 | 协作草稿——不是"用户掌控的真相源"，不要求 frontmatter，不参与复利结构 |
| index / log | **不**进 `wiki/index.md`；写 discussions/ **不**追加 log（非 wiki 操作，显式豁免"每次写入必更 log"） |
| git 跟踪 | 默认跟踪（与 raw/ 其余子树一致）；草稿随 wiki 仓一起进 git history，未启用 git 时走纯目录树 |

**为什么是 raw/ 内的子树而不是新顶层目录**：草稿与 raw/ 资料同属"非 wiki 复利资产"的
原始层（区别于 `wiki/` 的 LLM 复利页 + `MEMORY/` 的 agent 私有记忆）；放 raw/ 下让
"raw/ = 原始层"的心智模型保持单一，再用显式纪律 + 脚本豁免守住"discussions/ 不是真相源"。

### §15.2 与 ingest / lint 的契约（脚本豁免）

discussions/ 的可写性靠三道脚本契约兜底，**不**靠自觉：

1. **`ingest_diff.py`**——扫描 `raw/` 时跳过 `raw/discussions/`
   （与 `assets/` 同机制）：草稿**不**被当 untracked 素材列出，避免诱导 LLM 把自己写的
   草稿当 raw 真相 ingest 回 wiki（provenance 后门）
2. **`lint_wiki.py` raw-modified**——raw 不可变性检查从 `git status` 改动里
   **排除** `raw/discussions/` 路径：草稿的未提交改动**不**触发"raw 被违规改"告警
   （`raw/external/` 的 symlink 本身被 §13.4 `.gitignore` 排除，不会进 git status，
   故本排除只针对 discussions/）
3. **`lint_wiki.py` source-in-discussions**（error）——`type: source` 页的
   `sources:` 字段**不得**指向 `raw/discussions/` 下任何路径：堵住"草稿直接被引用为真相源"
   的后门。要引用其内容，先走 §15.3 把草稿转正式

### §15.3 归档路径（草稿 → wiki 真相，两条都需用户确认）

草稿消化进 wiki 有两条路径，**都需用户明确确认**：

1. **消化式**（讨论结论型）——LLM 把结论写进 `wiki/` 对应页（syntheses / concepts /
   comparisons），原稿留 / 删自便；走标准 ingest / query 流程（含 log 条目、index 同步、
   清 `reviewed` 戳等）。原稿不进 `sources:`
2. **转正式**（草稿本身要被检索 / 引用）——用户确认后 LLM 把文件 `mv` 到
   `raw/articles/`（或 `papers/` / `clippings/` 等合适子树），此后它回归**只读**真相源、
   走标准 ingest（写 `wiki/sources/<slug>.md` + `sources:` 指向 mv 后的路径）。这是
   raw/ 只读的**第二处 mv 例外**（第一处是 §13.3 接入时的 symlink 创建）：表述为
   "**仅限** discussions/ 迁出 + 用户明确要求"，迁入正式子树后 LLM **不可**再改

### §15.4 滑坡防线（反模式）

discussions/ 是 raw/ 总纪律的第二处例外——纪律型 skill 最怕"同层双语义"被合理化外扩。
三条红线（可写性不外推 / target 开发协作切分不外推 / 不用 discussions/ 规避 provenance）
的纪律正文见模板「raw/discussions/」段「滑坡防线」条（canonical 副本），本节不重抄。

---

## 附录 A：CLI 实现自检建议

CLI 在生成完成后，可执行以下验证：

1. **字节级对比(渲染后)**:CLI 用一组固定测试值（主题名 / 创建日期等 per-wiki 变量取测试常量）渲染,
   产物与本仓 `references/canonical/` 下对应文件**逐字一致**。
   canonical/ 目录由本仓在每次 fixture 变更时手工生成(SKILL 仓 owner 操作)。
2. **正则自检**：生成的 `wiki/log.md` 首条条目匹配 §4 正则
3. **frontmatter 解析**：生成的 `wiki/index.md` / `wiki/log.md` 能被
   SKILL 的 frontmatter 解析器正确解析（MEMORY.md 无 frontmatter，不在此列）
4. **结构自检**：5 个内容页子目录 + `MEMORY/` 全部存在；MEMORY 目录含 MEMORY.md
5. **lint 跑通**：生成的 wiki 仓跑 `scripts/lint_wiki.py` 应返回 exit code 0
