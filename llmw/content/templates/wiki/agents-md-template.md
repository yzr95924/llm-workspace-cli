# {{TOPIC_NAME}} Wiki

内容页写法、index / log / tags / scripts 细则见各自文档或文件头说明块；没有维护本 wiki 的 skill 时向用户索取。

<!-- 下方 @引用若未被自动展开（看不到正文），用 Read 工具读取 -->
@MEMORY/MEMORY.md
@scripts/SCRIPTS.md

## 本 wiki 的边界

### `raw/`（agent 只读，用户可改）

- agent 不写 / 删除 / 移动 `raw/` 下文件；`raw/external/` 与 `raw/discussions/` 是仅有的两处例外，不得外推到 `raw/` 其他子树
- 用户可随时新增 / 更新 `raw/`（重新剪藏、重存 PDF 都算），agent 不视之为违规
- raw 文件更新（同路径新内容）后重新执行 ingest；`llmw wiki ingest-diff --check-stale` 可发现待重摄文件
- raw 文件路径是 source 页 `sources` 字段的永久引用，改名会断链
- wiki 摘要与 raw 矛盾时，以 raw 为准
- git 写操作（init / add / commit / mv / config / symbolic-ref 等）只在用户要求后执行；
  只读 git 命令（status / diff / log）可直接执行；wiki 落盘后是否启用 git 由用户决定

### `raw/external/`（外部代码仓，symlink + anchor）

- 外部仓走 symlink + anchor，不内嵌拷贝仓库内容
- symlink 和 anchor 只通过 `llmw wiki external`（add / remove / list / rebuild，签名与行为见
  `llmw wiki external --help`）创建、删除或重建；agent 不手改 `.symlink-anchor.toml`
- symlink 与 anchor 直接在 `raw/external/` 顶层，不开子目录；外部仓由单个 `.symlink-anchor.toml` 记录
- symlink 指向的 target 仓不受 `raw/` 只读约束；target 在 wiki 仓外，由其自身 git 和用户处置
- ingest / query / lint / upgrade 等语料操作中 target 以读为主；改代码须有明确语境（用户要求 /
  具体修改任务），不在纯摄取流程中顺手改
- 改过 target 代码后，经用户确认再对受影响的 source 页重新执行 ingest

### `raw/discussions/`（协作草稿，用户与 agent 双方可写）

- 本区存放用户与 agent 协作的临时草稿（讨论稿、设计草稿、待整理笔记），创建 / 编辑 / 删除均可，不要求 frontmatter
- source 页的 `sources:` 不得指向 `raw/discussions/`
- 草稿进 wiki 只能走 mv：用户明确要求时把草稿 `mv` 到 `raw/articles/`（或其他正式子树），
  之后按正式 raw 走标准 ingest；迁入后 agent 不再改
- 未经用户要求，agent 不读本区内容往 `wiki/` 落页

### `wiki/`（agent 拥有）

- 用户不写 wiki 页面
- 内容页必须含 YAML frontmatter；`index.md` / `log.md` / `tags.md` 按各自文件头说明块维护
- 未归档内容页必须在 `wiki/index.md` 中有条目；归档页保留文件但退出 index 与日常 lint 检查
- 写页细则由维护本 wiki 的 skill 的页面模板文档承载，ingest / 写页操作时按需读取

## 写入纪律

- 写前必搜：创建新页面前先 grep / search `wiki/`，确认是否已有同主题或近义页；有则编辑它，不建新的副本
- 写后必同步：按同步对象判，不按动作名称判
  - `index.md`：页面新增 / 删除 / 改名，或 `title` / `description` / `type` / `reviewed` 等
    index 派生字段变化时，用 `llmw wiki write index add|remove` 同步
  - 相关页交叉引用：新增或取消页面关系时，在相关 entity / concept 页按需追加 / 修正，不重写整页
  - `log.md`：仅下列 op 痕迹各记一条，`ingest` = raw 消化落盘；`query` = 结论归档（未归档的纯问答不记）；
    `lint` = 常规 `llmw wiki lint` 体检（干净运行也记，兼任上次巡检时间信号；format 升级中的
    `--check-version` 不记）。条目写法见 `wiki/log.md` 头部说明块
  - 此外一律不动 `index.md` / `log.md`：纯读取、只改正文且不触发上述 index 字段的微小编辑（由 git 承载）、
    `wiki/` 之外的任何写入（`raw/` 各子树含 `raw/discussions/` 草稿与 external target 仓、`scripts/`、仓外路径）
- 重写时保留 frontmatter，不要因为改写丢失 `type` / `tags` / `sources` 字段
- 交叉引用走相对路径（如 `[link](../concepts/transformer.md)`），不要用 wikilink `[[transformer]]`，也不要用绝对路径
- 路径稳定：文件名一旦确定就是永久 ID；改名时重命名文件、更新所有引用，并同步 `wiki/index.md`
  （启用 git 时用 `git mv` 保留历史；未启用 git 时用普通 `mv`）

## Lint 纪律

- 修 lint 不要回退格式定义：若 lint 报告与本文件冲突，先和用户讨论再决定
- 版本漂移响应：lint / write / check-fixtures 报版本漂移类 finding 时，不回退格式定义、不手改对齐；
  告知用户，升级流程细则见维护本 wiki 的 skill 的 upgrade-workflow 文档

## 本文件本身的纪律

- 本文件由 llmw CLI 渲染（byte-owned），禁手改；手改会被 `agents-md-template-sync` 判为模板不一致，
  `llmw wiki upgrade --apply` 按最新模板全量重渲染。当前配置表只存 Wiki Format 版本（取升级目标），
  其余实例值以 `wiki_metadata.toml` 为准；wiki 特有纪律写进 `MEMORY/`。编辑规则见骨架所有权一节

## 骨架所有权

- `AGENTS.md`：byte-owned，整个文件由模板渲染，禁改
- `.gitignore`：block-owned，llmw managed 块内禁改；块外可自由添加用户忽略规则
- `wiki/index.md` / `wiki/log.md` / `wiki/tags.md` / `scripts/SCRIPTS.md`：header-owned，文件头说明块禁改；
  头部之外的条目、tags、登记区日常维护
- `wiki/` 内容页与 scripts 脚本：content-owned，agent 拥有，`llmw wiki upgrade` 不动

## 当前配置

| 字段 | 值 |
| --- | --- |
| Wiki Format 版本 | {{WIKI_FORMAT_VERSION}} |
