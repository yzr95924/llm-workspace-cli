# {{TOPIC_NAME}} Wiki

内容页写法见维护本 wiki 的 skill 的页面模板文档；index / log / tags / scripts 细则见
各自文件头说明块。没有维护本 wiki 的 skill 时向用户索取。

<!-- 下方 @引用若未被自动展开（看不到正文），用 Read 工具读取 -->
@MEMORY/MEMORY.md
@scripts/SCRIPTS.md

## 本 wiki 的边界

| 目录 | 写权限 | 关键约束 |
| --- | --- | --- |
| `raw/` | agent 只读，用户可改 | 同路径更新后重新 ingest；路径被 `sources` 引用，改名断链；与摘要矛盾以 raw 为准 |
| `raw/external/` | 只经 `llmw wiki external` 维护 | 顶层 symlink + 同一 anchor；target 仓只读，用户明确要求才写，改后确认重摄 |
| `discussions/` | 用户与 agent 均可写 | 临时草稿；不得作 `sources`；转正须用户明确要求；未经用户要求不读取生成 wiki 页 |
| `wiki/` | agent 维护 | 内容页带 frontmatter；未归档页必须入 index；归档页退 index、保留文件 |

## 写入纪律

- 写前：新页先搜索 `wiki/`，已有同主题 / 近义页则编辑该页
- 写页：保留 frontmatter 与 `type` / `tags` / `sources`；交叉引用用相对路径
- 文件名是永久 ID；改名时更新引用与 index（启用 git 时用 `git mv`）
- 写后必同步：按受影响对象判断，不按动作名称判断
  - `index.md`：页面新增、删除、改名，或 `title` / `description` / `type` / `reviewed`
    等 index 字段变化时，用 `llmw wiki write index add|remove`
  - 相关页：新增或取消页面关系时，在 entity / concept 页追加或修正链接
  - `log.md`：仅记三类操作：`ingest` = raw 消化落盘；`query` = 结论归档，未归档
    问答不记；`lint` = 常规 lint 运行，无 finding 也记，升级中的 `--check-version`
    不记；格式见文件头说明块
  - `tags.md`：新页选 tag 或新增 tag 时，同步更新 `wiki/tags.md` 白名单
  - 其余写入不更新 index / log / tags
- git 写操作只在用户要求后执行；只读命令可直接执行，是否用 git 管理 wiki 由用户决定

## 模板与升级

- 本文件由 llmw 按包内模板渲染，禁手改；漂移用 `llmw wiki upgrade --apply` 重渲染
- 版本漂移 / 模板不一致 finding 不手改对齐，走维护本 wiki 的 skill 的 format 升级流程；
  finding 与本文件冲突时先确认再改
- 当前配置只记录 Wiki Format 版本；实例数据归 `wiki_metadata.toml`，wiki 特有纪律归
  `MEMORY/`

## 骨架所有权

| 文件 | 所有权 | 日常可改范围 |
| --- | --- | --- |
| `AGENTS.md` | byte-owned | 禁改，整文件由模板渲染 |
| `.gitignore` | block-owned | llmw managed 块内禁改；块外可加用户忽略规则 |
| `wiki/index.md` / `wiki/log.md` / `wiki/tags.md` / `scripts/SCRIPTS.md` | header-owned | 文件头说明块禁改；其余条目日常维护 |
| `wiki/` 内容页与 `scripts/` 脚本 | content-owned | agent 维护，`llmw wiki upgrade` 不动 |

## 当前配置

| 字段 | 值 |
| --- | --- |
| Wiki Format 版本 | {{WIKI_FORMAT_VERSION}} |
