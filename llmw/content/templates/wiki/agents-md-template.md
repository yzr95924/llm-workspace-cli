# {{TOPIC_NAME}} Wiki — LLM 维护守则

> 这是本 wiki 的**纪律配置**——给维护本 wiki 的 LLM 看的"工作守则"。你（即 LLM）
> 必须在每次操作前先读这份文件；任何对 wiki 的写入都必须符合这里规定的边界。
>
> **本文件（`AGENTS.md`）是本 wiki 纪律的单一真源（SSOT）**——工具无关。由 llmw CLI 在初始化时
> 按其包内官方模板渲染生成（模板随 CLI 分发，不在本 wiki 内）；后续可由用户编辑，**但**
> 任何与本 skill 的核心原则冲突的修改都视为"非标准配置"，skill 行为不再保证一致。
> **本 wiki 特有的纪律 / 偏好请沉淀到 `MEMORY/`**（由下方 `@import` 加载，会话常驻），不要写进本文件——
> 模板升级时本文件按 CLI 最新模板**全量重渲染**，本地修改一律不保留。
>
> **关键**：本文件里凡 `@path/to/file` 形式的引用（如 `@MEMORY/MEMORY.md`、`@scripts/SCRIPTS.md`），
> 都用 Read 工具**必须**读取（不是"按需"）——它们与你**当前任务**直接相关。不自动展开 `@import` 的 agent 尤须手动执行，
> 否则漏上下文。

@MEMORY/MEMORY.md

@scripts/SCRIPTS.md

## 一、本 wiki 的边界

### `raw/` —— 真相之源（**LLM 只读，用户可改**）

- 路径：`<wiki-root>/raw/{articles,assets,...}/`（子目录可自由扩展，见下文 `external/`）
- 性质：用户策划的原始资料（论文、剪藏、PDF、图片、播客转写、手写笔记等）
- 纪律：
  - **LLM 不写 / 删除 / 移动 raw/ 下文件**——只读；**两处写权限例外**：`raw/external/`
    （symlink + anchor，见下文）+ `raw/discussions/`（协作草稿，见下文）。**这两处例外
    不得外推到 raw/ 其他子树**（papers / articles / clippings 等仍只读）
  - **用户可随时新增 / 更新 raw/**（重新剪藏、重存 PDF 都算）；这是用户的权限，
    不是违反纪律
  - raw 文件一旦被更新（同路径新内容），**由 ingest 重新消化**：更新对应 source
    页的正文 + `updated` 字段，并在 `log.md` 追加一条 ingest。`llmw wiki ingest-diff
    --check-stale` 会按 mtime vs source 页 `updated` 标记这类待重新摄取的文件
  - raw 文件路径是 wiki 内 source 页的 `sources` 字段的"永久引用"——改名会断链
  - raw/ 的内容是真相之源；wiki 摘要如与 raw 矛盾，**以 raw 为准**
  - raw/ 进 git（本 wiki 的 `.gitignore` 不排除 `raw/`）；空目录在 init 时由 CLI 放 `.gitkeep` 占位（
    `raw/articles/` + `raw/assets/`），后续真实文件由用户 `git add`（与 wiki/ 行为一致）
- **所有 git 操作由用户触发**（红线）——LLM agent **不**主动 `git init` /
  `git add` / `git commit` / `git config` / `git symbolic-ref`；用户看到 wiki 落盘后自行决定是否 init git

#### `raw/external/` —— 外部代码仓接入（symlink）

- 路径：`<wiki-root>/raw/external/`
- 用途：把本地已有的外部代码仓（Linux kernel、Ray 源码、TensorFlow、NumPy 等）
  作语料纳入 wiki；**不**内嵌拷贝（占空间），走 symlink + 锚定元数据
- **扁平布局**——symlink + anchor 直接在 `raw/external/` 顶层，不要开
  `<source-name>/` 子目录；anchor 单文件记录所有外部仓：

  ```text
  raw/external/
  ├── .symlink-anchor.toml         # TOML: schema_version=1 + [[entry]] 数组
  │                                 # 每 entry: symlink / target / captured_at /
  │                                 # kind='external-repo' 必填 + git 身份字段（可选）
  ├── linux-kernel                  # symlink → ~/src/linux-kernel
  └── ray                          # symlink → ~/src/ray
  ```

- **纪律（用户 + LLM 共有）**：
  - **每 entry 最小必填 4 字段**：`symlink`（kebab-case，对应 `raw/external/`
    同名 symlink）+ `target`（**推荐 `~/src/<name>` home-relative 形式**；
    也接受绝对路径，lint 端 `Path(target).expanduser()` 统一展开判定）+
    `captured_at`（接入当天）+ `kind: "external-repo"`
  - **git 身份字段（可选）**：target 在 git 仓内时推荐记 `remote_url` + `branch`
    ——跨机器重建软链接时用；不记 commit
  - anchor / symlink 的漂移（缺 anchor、解析失败、孤儿 symlink、target 失效、
    子目录布局等）由 `llmw wiki lint` 机械探测，check 名以 lint 输出为准
  - LLM agent **可写** symlink + anchor（首次接入 + 漂移刷新）——这是 `raw/`
    总纪律的**写权限例外之一**；首次接入走标准 ingest 流程（建 symlink + anchor →
    建 source 页 → 追加 log 条目 → 同步 index）
  - **target 仓内文件按角色分**：**wiki 维护操作**（ingest / query / lint /
    upgrade）中 target 只读（librarian 角色，不在仓内跑 `git pull` 之类）；**用户明确要求
    的开发协作**（修 bug / 重构 / 仓内 git 操作）**不**属 wiki 操作、**不**受 raw/ 只读约束
    ——target 在 wiki 仓外、有其自身 git、由用户全权处置。代码改动后的 wiki 同步走**既有通道**
    （用户确认 → 受影响 source 页重 ingest）。
    **禁止**以"开发协作"为借口在 wiki 维护操作中顺手改 target
  - LLM **不**编辑 `raw/external/` 之外的 `raw/` 子树（articles / papers / assets /
    clippings 等仍"LLM 只读"；`discussions/` 是另一处写权限例外——见下节）
- `.gitignore` 配置：已排好 `raw/external/*` 排除但保留 `.symlink-anchor.toml`——
  跨机器 clone 时通过 anchor 立即知道"这本来指着哪"；anchor 的
  `remote_url` + `branch` 让新主机 LLM 可重建（重建 = 按 anchor 重建
  symlink → 重 ingest 受影响 source 页）

#### `raw/discussions/` —— 协作草稿层（用户 + LLM 双方可写）

- 路径：`<wiki-root>/raw/discussions/`（协作草稿层；存在时适用本节纪律）
- 用途：用户 + LLM 协作的临时草稿——讨论稿、设计草稿、待整理笔记。**不是**"用户掌控的
  真相源"，不参与复利结构
- 纪律：
  - **用户 + LLM 双方可写**——创建 / 编辑 / 删除都行；这是 `raw/` 总纪律的**第二处写权限
    例外**（第一处是 `raw/external/` 的 symlink + anchor）
  - **不**要求 frontmatter（草稿不是内容页）
  - **不**进 `wiki/index.md`；写 discussions/ **不**追加 `log.md` 条目（非 wiki 操作，
    显式豁免"每次写入必更 log"）
  - **`llmw wiki ingest-diff` 跳过** discussions/ 子树——草稿不会被当 untracked 素材列出
    （避免 LLM 把自己写的草稿当 raw 真相 ingest 回 wiki = provenance 后门）
  - **`raw-modified` lint 排除** discussions/——草稿的未提交 git 改动**不**触发"raw 被违规改"
  - **`sources:` 不得指向** `raw/discussions/`——`type: source` 页引用草稿会被 lint 报
    `source-in-discussions`（error）；要引用先走归档路径转正式
  - git 默认跟踪（与 raw/ 其余子树一致）
- **归档路径**（草稿 → wiki 真相，两条都需用户确认）：
  - **消化式**：LLM 把结论写进 `wiki/` 对应页（走标准 ingest 纪律：log / index / 清
    `reviewed` 戳），原稿留删自便，不进 `sources:`
  - **转正式**：用户确认后 LLM `mv raw/discussions/<x>.md raw/articles/<x>.md`（或合适
    子树），此后回归只读真相源、走标准 ingest；这是 raw/ 只读的**第二处 mv 例外**
    （迁入正式子树后 LLM 不可再改）
- **滑坡防线**：discussions/ 的可写性**不得**外推到 raw/ 其他子树（papers /
  articles / clippings 等仍只读）；上节 target 开发协作切分**不得**外推为"raw/ 也能改"；
  不得用 discussions/ 规避 ingest 纪律（绕归档路径漏 log / index / reviewed 戳）

### `wiki/` —— LLM 拥有的复利资产

- 路径：`<wiki-root>/wiki/{entities,concepts,sources,comparisons,syntheses}/`
- 性质：LLM 生成的相互链接的 Markdown 文件
- 纪律：
  - 用户**不写** wiki 页面（编辑 AGENTS.md 除外）
  - 任何 wiki 页面**必须**含 YAML frontmatter
  - 任何 wiki 页面**必须**在 `wiki/index.md` 中有对应条目
  - 任何 wiki 页面**必须**有 ≥ 1 条 inbound 链接（index 或其它页）
- **内容页写页规则不在本文件**——页面类型 / frontmatter 字段全集 / 建页与追加阈值 /
  认知质量字段（`reviewed` / `contested` 等）由维护本 wiki 的 skill 的页面模板文档承载
  （ingest / 写页操作时按需读取）；环境中没有该 skill 时，向用户索取该文档

### `wiki/log.md` —— 近期活动速览（滚动窗口）

- 路径：`<wiki-root>/wiki/log.md`
- 纪律：每次 ingest / query / lint 后**必须**追加一条——正路走 `llmw wiki write log`
  （格式 + 滚动窗口截断自动保证）；条目格式与 retention 细则见
  [`wiki/log.md`](wiki/log.md) 头部说明块，带外手改前先读它

### `wiki/index.md` —— wiki 单一入口

- 路径：`<wiki-root>/wiki/index.md`
- 纪律：任何 wiki 页面必须在 index.md 有对应条目；每次 wiki 内容变更后**必须**同步
  （宁可多改）。分组 / 条目格式 / 扩容护栏见 [`wiki/index.md`](wiki/index.md) 头部说明块

### `MEMORY/` —— LLM agent 的持久化记忆

- 路径：`<wiki-root>/MEMORY/`
- 性质：LLM agent 在 ingest / query / lint 过程中沉淀的**经验、踩坑、用户偏好**——
  不是 wiki 内容、不是操作时间线，而是 agent 私有记忆（内容页、操作时间线、agent
  记忆三者的分层中的第 3 层）
- 纪律：用户**不**直接编辑 MEMORY/（这是 agent 私有记录）；条目形式（完整 / 短条目）、
  frontmatter 豁免、索引维护规则见 [`MEMORY/MEMORY.md`](MEMORY/MEMORY.md) 头部说明块；
  写每条**只改 `MEMORY/MEMORY.md`** 这一份

### `scripts/` —— 本 wiki 仓的自维护脚本目录

- 路径：`<wiki-root>/scripts/`
- 性质：**用户 + LLM agent 共有**的项目级脚本目录——放置项目专属的 ingest 扩展（批量 PDF prep、
  主题模板预处理等）、外部 CLI 胶水（pdf 抽图 / obsidian 同步等）、自动化 hook（pre-commit 校验、
  ingest 前清洗等）。**不**放置 CLI 自带的 lint / ingest-diff / write 工具（随 llmw 分发，复制进来
  会版本漂移）
- 纪律：添加 / 修改 / 删除脚本只登记 [`scripts/SCRIPTS.md`](scripts/SCRIPTS.md) 一处（顶部
  `@import` 自动加载）；登记形态 / 每脚本契约 / 执行纪律见其头部说明块。agent **不自动遍历**
  `scripts/` 跑任何东西——先看 SCRIPTS.md 再按"调用约定"显式执行

## 二、写入纪律

1. **写前必搜**——创建新页面前先 grep / search `wiki/` 确认是否已有同名或近义页
2. **写后必同步**——新增 / 改 / 删页面后必须同步：
   - `index.md`（条目增减）
   - 相关的 entity / concept 页（追加"参考来源"段，**不重写**）
   - `log.md`（追加操作条目）
3. **改写而非新建**——若已有同类页，**编辑它**而不是建新的副本
4. **重写时保留 frontmatter**——不要因为改写丢失 `type` / `tags` / `sources` 字段
5. **交叉引用走相对路径**——`[link](../concepts/transformer.md)`，**不要**用 wikilink
   `[[transformer]]`、**不要**用绝对路径
6. **路径稳定**——文件名一旦确定就是永久 ID；想改名时重命名文件 + 更新所有引用（启用
   git 时用 `git mv` 保留 history；未启用 git 时用普通 `mv` + 全量更新引用）

## 三、阅读纪律

1. **读 raw 优先**——source 页的引用若与 raw 矛盾，回到 raw 复核
2. **读 index 起手**——找相关页面前先看 `index.md` 分类
3. **不读 log 内容**做证据——log 是时间线，证据在源页里
4. **跨页综合走 query 操作**——读多页 + 综合 + 给引用，不要拼接

## 四、Query 纪律

1. **先看 index，再读相关页**——不要直接全量 grep
2. **答案带引用**——每条事实带 `(来源: <page path>)`
3. **矛盾显式标注**——不要"和稀泥"
4. **好答案问归档**——对比 / 综合 / 发现新联系 → 询问用户是否写回 wiki

## 五、Lint 纪律

1. **`llmw wiki lint` 检查 deterministic 部分**——raw/ 不可变性、frontmatter、index 覆盖、断链、log 格式
2. **agent 检查半定性部分**——矛盾、缺失交叉引用、过期主张
3. **修 lint 不要回退 schema**——若 lint 报告与本文件冲突，**先讨论用户**再决定
4. **版本漂移响应**——lint / write / check-fixtures 报版本漂移
   （`wiki-format-version-stale` / `agents-md-template-sync` drift / legacy warn）时，
   **不回退 schema、不手改对齐**；告知用户并走升级流程：`llmw check-fixtures` 取
   plan → 按 upgrade-workflow 走 Edit/Write 修复 → 改本文件 §七 版本行（其余由模板
   重渲染）

## 六、本文件本身的纪律

- **本文件由 llmw CLI 渲染拥有（byte-owned）——禁手改**。自定义纪律沉淀去 `MEMORY/`
  （由顶部 `@MEMORY/MEMORY.md` 自动加载，会话常驻）；手改会被
  `agents-md-template-sync` check 判 drift、`llmw upgrade --apply`
  重渲染覆盖（§七 表里 4 个 per-wiki 字段由 upgrade 自动保留现值）。
- 本文件是 schema，**不是 wiki 内容**——不要往里塞 wiki 主题相关的笔记
- 改本文件 = 改 skill 行为 = 大事；先和用户确认
- **模板升级时本文件按 CLI 最新模板全量重渲染**（本 wiki 的健康检查强制这一条；本地定制先沉淀 `MEMORY/`，
  详见顶部说明）——§七 四行变量
  （主题 / 创建日期 / CLI 版本 / Wiki Format 版本）是仅有的 per-wiki 内容，升级时保留
- 若 wiki 启用 git，每次改建议 commit 并加清晰的 commit message；未启用 git 跳过此步

### 骨架所有权四分表（wiki 侧文件归属）

本表约束维护本 wiki 的 agent —— 哪些文件可改、哪些只能由 llmw CLI 渲染。

| 文件 | 所有权 | agent 权限 |
| --- | --- | --- |
| `AGENTS.md` / `CLAUDE.md` | byte-owned（整个文件 = 模板渲染） | 禁改；自定义纪律沉淀到 `MEMORY/` |
| `.gitignore` | block-owned（llmw managed 块内禁改） | 块外自由添加用户忽略规则 |
| `wiki/index.md` / `wiki/log.md` / `wiki/tags.md` / `MEMORY/MEMORY.md` / `scripts/SCRIPTS.md` | header-owned（文件头禁改） | growth 段（`##` 段体 / 条目 / tags）日常写 |
| wiki `wiki/` 各内容页 + MEMORY 经验条目 + scripts 脚本 | content-owned | agent 拥有；`llmw wiki upgrade` 不动 |

## 七、当前配置

| 字段 | 值 |
| --- | --- |
| 主题 | {{TOPIC_NAME}} |
| 创建日期 | {{SETUP_DATE}} |
| Wiki 根 | <由 LLM_WIKI_ROOT 环境变量或 init 时确定> |
| Wiki Format 版本 | {{WIKI_FORMAT_VERSION}} |
| CLI 版本 | {{CLI_VERSION}} |
