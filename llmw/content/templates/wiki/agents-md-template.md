# {{TOPIC_NAME}} Wiki：LLM 维护守则

这是本 wiki 的**纪律配置**，即给维护本 wiki 的 LLM 看的"工作守则"。你（即 LLM）必须在每次
操作前先读这份文件；任何对 wiki 的写入都必须符合这里规定的边界。

**本文件（`AGENTS.md`）规定跨操作边界与骨架所有权；内容页写法、index / log / tags / scripts
细则以各自文档或说明块为准。渲染所有权与升级重渲染规则见"本文件本身的纪律"节。

<!-- 下方 @引用若未被自动展开（看不到正文），用 Read 工具读取 -->
@MEMORY/MEMORY.md
@scripts/SCRIPTS.md

## 一、本 wiki 的边界

### `raw/`：真相之源（**LLM 只读，用户可改**）

- 路径：`<wiki-root>/raw/{articles,assets,...}/`（子目录可自由扩展，见下文 `external/`）
- 性质：用户策划的原始资料（论文、剪藏、PDF、图片、播客转写、手写笔记等）
- 纪律：
  - **LLM 不写 / 删除 / 移动 raw/ 下文件**，只读；**两处写权限例外**：`raw/external/`
    （symlink + anchor，见下文）+ `raw/discussions/`（协作草稿，见下文）。**这两处例外
    不得外推到 raw/ 其他子树**（papers / articles / clippings 等仍只读）
  - **用户可随时新增 / 更新 raw/**（重新剪藏、重存 PDF 都算）；这是用户的权限，
    不是违反纪律。启用 git 后，未提交的 raw 变更会被 lint 报 `raw-modified`，含义是
    确认改动来源，不是禁止用户更新；agent 不代还原或代提交，由用户决定
  - raw 文件一旦被更新（同路径新内容），**由 ingest 重新消化**（`llmw wiki ingest-diff --check-stale`
    可发现待重摄文件）
  - raw 文件路径是 wiki 内 source 页的 `sources` 字段的"永久引用"（改名会断链）
  - raw/ 的内容是真相之源；wiki 摘要如与 raw 矛盾，**以 raw 为准**
  - raw/ 进 git（本 wiki 的 `.gitignore` 不排除 `raw/`）
- **所有 git 操作由用户触发**（红线）：LLM agent **不**主动 `git init` /
  `git add` / `git commit` / `git config` / `git symbolic-ref`；用户看到 wiki 落盘后自行决定是否 init git

#### `raw/external/`：外部代码仓接入（symlink）

- 用途：把本地已有的外部代码仓（Linux kernel、Ray 源码、TensorFlow、NumPy 等）
  作语料纳入 wiki；**不**内嵌拷贝，走 symlink + 锚定元数据
- **扁平布局**：symlink + anchor 直接在 `raw/external/` 顶层，不要开
  `<source-name>/` 子目录；外部仓由单个 `.symlink-anchor.toml` 记录
- **写路径收编（`raw/` 写权限例外之一）**：symlink 与 anchor 的创建 / 删除 / 重建
  **一律**走 `llmw wiki external` 子命令（add / remove / list / rebuild，签名与行为见
  `llmw wiki external --help`）；add / remove 不修改已有 target 仓，`rebuild` 可在 target
  缺失且 anchor 记有 remote 时 clone；LLM **不**手改 `.symlink-anchor.toml`。孤儿 symlink
  等 CLI 无法直接接管的异常现场，经用户确认后只清理该 symlink，再走 `external add` 重建
- anchor / symlink 漂移由 `llmw wiki lint` 机械探测，check 名以 lint 输出为准
- **target 仓 agent 可读写**：`raw/external/` symlink 指向的外部仓**不**受 raw/ 只读约束；
  target 在 wiki 仓外、有其自身 git、由用户全权处置
- **语料场景以读为主**：ingest / query / lint / upgrade 等语料消费操作中 target 以读
  为主，写操作要有明确语境（用户要求 / 具体修改任务），不在纯摄取流程中顺手改代码。
  代码改动后的 wiki 同步走**既有通道**（用户确认 → 受影响 source 页重 ingest）

#### `raw/discussions/`：协作草稿层（用户 + LLM 双方可写）

- 路径：`<wiki-root>/raw/discussions/`（协作草稿层，与 wiki 内容维护解耦；存在时适用本节纪律）
- 用途：用户 + LLM 协作的临时草稿（讨论稿、设计草稿、待整理笔记）。**不是**"用户掌控的
  真相源"，**不是**待摄取资料，不参与复利结构
- 纪律：
  - **用户 + LLM 双方可写**：创建 / 编辑 / 删除都行；这是 `raw/` 总纪律的**第二处写权限
    例外**（第一处是 `raw/external/` 的 symlink + anchor）
  - **不**要求 frontmatter（草稿不是内容页）
  - **`sources:` 不得指向** `raw/discussions/`（lint 会报 `source-in-discussions`）
- **转正式**（草稿纳入 wiki 的唯一路径）：仅当用户明确要求时，LLM 才把草稿 `mv` 到
  `raw/articles/`（或合适的其他子树），此后按正式 raw 走标准 ingest；这是 raw/ 只读的
  **mv 例外**（迁入正式子树后 LLM 不可再改）。未经用户要求，agent **不**主动读本区
  内容往 `wiki/` 落页

### `wiki/`：LLM 拥有的复利资产

- 路径：`<wiki-root>/wiki/{{WIKI_SUBDIRS_GLOB}}/`
- 性质：LLM 生成的相互链接的 Markdown 文件
- 纪律：
  - 用户**不写** wiki 页面
  - 内容页**必须**含 YAML frontmatter；`index.md` / `log.md` / `tags.md` 按骨架文件
    各自说明块维护
  - 未归档内容页**必须**在 `wiki/index.md` 中有对应条目；归档页保留文件但退出 index
    与日常 lint 检查
- **内容页写页规则不在本文件**：页面类型 / frontmatter 字段全集 / 建页与追加阈值 /
  认知质量字段（`reviewed` / `contested` 等）由维护本 wiki 的 skill 的页面模板文档承载
  （ingest / 写页操作时按需读取）；环境中没有该 skill 时，向用户索取该文档

### `wiki/log.md`：近期活动速览（滚动窗口）

- 纪律：追加触发判定见"写入纪律""写后必同步"条；正路命令、条目格式与 retention
  细则见 [`wiki/log.md`](wiki/log.md) 头部说明块，带外手改前先读它

### `wiki/index.md`：wiki 单一入口

- 纪律：同步触发判定见"写入纪律""写后必同步"条；页面覆盖不变量见"wiki/"节；
  分组 / 条目格式 / 扩容护栏见 [`wiki/index.md`](wiki/index.md) 头部说明块

### `wiki/tags.md`：tag 白名单字典

- 纪律：追加时机 / 取值规则 / lint 解析约束见
  [`wiki/tags.md`](wiki/tags.md) 头部说明块

### `scripts/`：本 wiki 仓的自维护脚本目录

- 性质：**用户 + LLM agent 共有**的项目级脚本目录；用途 / 登记形态 / 调用纪律见
  [`scripts/SCRIPTS.md`](scripts/SCRIPTS.md) 头部说明块

## 二、写入纪律

1. **写前必搜**：创建新页面前先 grep / search `wiki/` 确认是否已有同主题或近义页；
   有则编辑它，不建新的副本
2. **写后必同步**：按同步对象判，不按动作名称判：
   - `index.md`：页面新增 / 删除 / 改名，或 `title` / `description` / `type` /
     `reviewed` 等 index 派生字段变化时，用 `llmw wiki write index add|remove` 同步
   - 相关页交叉引用：新增或取消页面关系时，在相关 entity / concept 页按需追加 / 修正，
     **不重写**整页
   - `log.md`：仅下列 op 痕迹各记一条，**ingest**＝raw 消化落盘；**query**＝结论
     归档（未归档的纯问答不记）；**lint**＝常规 `llmw wiki lint` 体检（干净运行也记，
     兼任"上次巡检时间"信号；format 升级中的 `--check-version` 不记）。条目写法细则见
     `wiki/log.md` 头部说明块
   - **此外一律不动 `index.md` / `log.md`**：纯读取、只改正文且不触发上述 index
     字段的微小编辑（git 承载）、`wiki/` 之外的任何写入（raw/ 各子树含 discussions/
     草稿与 external target 仓、scripts/、仓外路径）
3. **重写时保留 frontmatter**：不要因为改写丢失 `type` / `tags` / `sources` 字段
4. **交叉引用走相对路径**：`[link](../concepts/transformer.md)`，**不要**用 wikilink
   `[[transformer]]`（Obsidian 等工具的专用语法，换渲染器即失效）、**不要**用绝对路径
   （换机 / 分发即断）
5. **路径稳定**：文件名一旦确定就是永久 ID；想改名时重命名文件 + 更新所有引用，并同步
   `wiki/index.md`（启用 git 时用 `git mv` 保留 history；未启用 git 时用普通 `mv` +
   全量更新引用）

## 三、Query 纪律

细则由维护本 wiki 的 skill 的 query-workflow 文档承载；执行 query 前读全文。
环境中没有该 skill 时，向用户索取该文档

## 四、Lint 纪律

1. **`llmw wiki lint` 检查 deterministic 部分**：检查集与 finding 口径以 `llmw wiki lint`
   输出 / `--explain` 为准（本文件不枚举）
2. **agent 检查半定性部分**：清单与方法见维护本 wiki 的 skill 的 lint-workflow"半定性检查"节
3. **修 lint 不要回退 schema**：若 lint 报告与本文件冲突，**先讨论用户**再决定
4. **版本漂移响应**：lint / write / check-fixtures 报版本漂移类 finding 时，
   **不回退 schema、不手改对齐**；告知用户，升级流程细则见维护本 wiki 的 skill 的
   upgrade-workflow 文档

## 五、本文件本身的纪律

- **本文件由 llmw CLI 渲染拥有（byte-owned），禁手改**：手改会被 `agents-md-template-sync`
  check 判 drift、`llmw wiki upgrade --apply` 按最新模板**全量重渲染**覆盖："当前配置"表是
  仅有的本地内容（主题 / 创建日期来自 wiki metadata，Wiki Format 版本取升级目标）；
  自定义纪律沉淀去 `MEMORY/`
- 本文件是 schema，**不是 wiki 内容**：不要往里塞 wiki 主题相关的笔记

### 骨架所有权四分表（wiki 侧文件归属）

本表约束维护本 wiki 的 agent：哪些文件可改、哪些只能由 llmw CLI 渲染。

| 文件 | 所有权 | agent 权限 |
| --- | --- | --- |
| `AGENTS.md` | byte-owned（整个文件 = 模板渲染） | 禁改；自定义纪律沉淀到 `MEMORY/` |
| `.gitignore` | block-owned（llmw managed 块内禁改） | 块外自由添加用户忽略规则 |
| `wiki/index.md` / `wiki/log.md` / `wiki/tags.md` / `scripts/SCRIPTS.md` | header-owned（文件头禁改） | growth 段（`##` 段体 / 条目 / tags）日常写 |
| wiki `wiki/` 各内容页 + scripts 脚本 | content-owned | agent 拥有；`llmw wiki upgrade` 不动 |

## 六、当前配置

| 字段 | 值 |
| --- | --- |
| 主题 | {{TOPIC_NAME}} |
| 创建日期 | {{SETUP_DATE}} |
| Wiki Format 版本 | {{WIKI_FORMAT_VERSION}} |
