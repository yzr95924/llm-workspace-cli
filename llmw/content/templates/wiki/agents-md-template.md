# {{TOPIC_NAME}} Wiki

内容页写法、index / log / tags / scripts 细则见各自文档或文件头说明块；没有维护本 wiki 的 skill 时向用户索取。

<!-- 下方 @引用若未被自动展开（看不到正文），用 Read 工具读取 -->
@MEMORY/MEMORY.md
@scripts/SCRIPTS.md

## 本 wiki 的边界

### `raw/`（agent 只读，用户可改）

- agent 不在 `raw/` 下创建、修改、删除或移动文件；例外只有 `raw/external/` 与
  `raw/discussions/` 两处，不适用于 `raw/` 其他子树
- 用户可随时新增或更新 `raw/` 文件（重新剪藏、重存 PDF 都算），agent 不视之为违规
- raw 文件更新（同路径新内容）后重新执行 ingest；待重摄文件用
  `llmw wiki ingest-diff --check-stale` 发现
- raw 文件路径被 source 页 `sources` 字段长期引用，改名会断链
- wiki 摘要与 raw 内容矛盾时，以 raw 为准
- git 写操作（init / add / commit / mv / config / symbolic-ref 等）只在用户要求后执行；
  只读命令（status / diff / log）可直接执行；是否用 git 管理 wiki 由用户决定

### `raw/external/`（外部代码仓，symlink + anchor）

- 外部代码仓以 symlink + anchor 接入，不拷贝仓库内容进 wiki
- symlink 与 anchor 只用 `llmw wiki external`（add / remove / list / rebuild，用法见
  `llmw wiki external --help`）创建、删除或重建；agent 不手改 `.symlink-anchor.toml`
- symlink 与 anchor 直接放在 `raw/external/` 顶层，不建子目录；全部外部仓记录在同一个
  `.symlink-anchor.toml`
- symlink 指向的 target 仓在 wiki 之外，不受 `raw/` 只读约束，由其自身 git 仓库与用户管理
- ingest / query / lint / upgrade 等语料操作中 target 仓只读；只有用户明确要求修改代码时
  才写入，不在摄取流程中顺带改代码
- 改过 target 代码后，经用户确认再对受影响的 source 页重新执行 ingest

### `raw/discussions/`（协作草稿，用户与 agent 均可写）

- 本目录存放用户与 agent 的临时草稿（讨论稿、设计草稿、待整理笔记），可创建、编辑、删除，
  不要求 frontmatter
- source 页的 `sources:` 不得指向 `raw/discussions/`
- 草稿只有经用户明确要求时才 `mv` 到 `raw/articles/` 或其他正式子树，之后按标准 ingest
  处理；迁入后 agent 不再修改
- 未经用户要求，agent 不读取本目录内容来生成 `wiki/` 页面

### `wiki/`（agent 维护）

- 用户不直接编辑 wiki 页面
- 内容页必须含 YAML frontmatter；`index.md` / `log.md` / `tags.md` 按各自文件头说明块维护
- 未归档内容页必须在 `wiki/index.md` 有条目；归档页保留文件，退出 index 与日常 lint 检查
- 写页细则见维护本 wiki 的 skill 的页面模板文档，ingest / 写页时读取

## 写入纪律

- 新建页面前先搜索 `wiki/`，确认没有同主题或近义页；已有则编辑该页，不建重复页
- 写后必同步：按受影响的对象判断，不按动作名称判断
  - `index.md`：页面新增、删除、改名，或 `title` / `description` / `type` / `reviewed`
    等 index 收录字段变化时，用 `llmw wiki write index add|remove` 同步
  - 相关页交叉引用：新增或取消页面关系时，在相关 entity / concept 页追加或修正链接，
    不重写整页
  - `log.md`：只有下列三类操作各记一条。`ingest` = raw 消化落盘；`query` = 结论归档
    （未归档的问答不记）；`lint` = 常规 `llmw wiki lint` 运行（无 finding 也记，用于
    表示最近巡检时间；format 升级中的 `--check-version` 不记）。条目写法见
    `wiki/log.md` 头部说明块
  - 除此之外不更新 `index.md` / `log.md`：纯读取、只改正文且不涉及上述 index 字段的
    编辑、`wiki/` 之外的任何写入（`raw/` 各子树含 `raw/discussions/` 草稿与 external
    target 仓、`scripts/`、仓外路径）
- 重写页面时保留 frontmatter，不丢失 `type` / `tags` / `sources` 字段
- 交叉引用用相对路径（如 `[link](../concepts/transformer.md)`），不用 wikilink
  `[[transformer]]`，不用绝对路径
- 文件名确定后作为永久 ID；改名时重命名文件、更新所有引用并同步 `wiki/index.md`
  （启用 git 时用 `git mv` 保留历史，否则用普通 `mv`）

## Lint 纪律

- 修 lint 不回退格式定义：finding 与本文件冲突时，先和用户确认再改
- lint / write / check-fixtures 报版本漂移类 finding 时，不回退格式定义、不手改对齐；
  告知用户，升级流程见维护本 wiki 的 skill 的 upgrade-workflow 文档

## 本文件本身的纪律

- 本文件由 llmw 按包内模板渲染，手改会被 `agents-md-template-sync` 判为模板不一致；
  `llmw wiki upgrade --apply` 按最新模板全量重渲染
- 当前配置表只记录 Wiki Format 版本（升级目标值）；主题等其余实例数据以
  `wiki_metadata.toml` 为准；wiki 特有的纪律沉淀到 `MEMORY/`
- 各骨架文件的可改范围见下一节

## 骨架所有权

- `AGENTS.md`：byte-owned，整个文件由模板渲染，禁改
- `.gitignore`：block-owned，llmw managed 块内禁改；块外可自由添加用户忽略规则
- `wiki/index.md` / `wiki/log.md` / `wiki/tags.md` / `scripts/SCRIPTS.md`：header-owned，
  文件头说明块禁改；头部之外的条目、tags、登记内容日常维护
- `wiki/` 内容页与 scripts 脚本：content-owned，agent 维护，`llmw wiki upgrade` 不动

## 当前配置

| 字段 | 值 |
| --- | --- |
| Wiki Format 版本 | {{WIKI_FORMAT_VERSION}} |
