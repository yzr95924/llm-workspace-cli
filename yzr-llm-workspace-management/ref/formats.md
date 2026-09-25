# 产物格式契约与读取契约

> 本文件承载 skill 写盘文件的格式契约（A1-A8）；运行期读取契约与实例归属见 `<workspace>/AGENTS.md`。
> scan / query 归档 / lint / memory 各流程写盘前读对应 A 节

## A1. workspace.toml 读取契约

- 路径：`<workspace-root>/workspace.toml`
- 完整 schema 权威在 CLI 代码；`workspace-toml-reads-satisfied` check 校验读取契约完整性

**skill 实际读取的字段**（`scan` / `upgrade` 用）：

| 字段 | 用途 |
| --- | --- |
| `templates_version` | `llmw upgrade` 版本比对 + 自动 bump（含 `workspace_format` / `wiki_format` 双分量） |
| `[wikis.<name>].path` | skill `scan` 遍历 wiki 子目录 |
| `[wikis.<name>].created_at` | INDEX 条目的 `created` 字段展示 |

## A2. INDEX.md

- 维护方：**skill** 在 `scan` 时写；CLI 不写
- frontmatter 必填（A7） + `type: workspace-index`；`title` 推荐 `"Workspace Index"`；`tags` 推荐 `[workspace, index]`
- 正文骨架：

  ```markdown
  # <Workspace Display Name> — Workspace Index

  > workspace 入口文档。每个 wiki 一节，按 wiki name 字母序。

  ## Wikis

  ### <wiki-name>

  - **display_name**: ...
  - **topic**: ...
  - **description**: ...
  - **tags**: [...]
  - **created**: YYYY-MM-DD
  - **last activity**: YYYY-MM-DD (log entry kind)
  - **page counts**: 0 entities / 0 concepts / ...
  - **key entities**: [...]
  - **one-line summary**: ...

  ## Cross-wiki Links
  ...（短描述）
  ## Recent Activity (across all wikis)
  ...
  ```

## A3. STATS.md

- 维护方：**skill** 在 `scan` 时一并写；与 INDEX.md 区别：结构化（表格）
- frontmatter 必填（A7） + `type: workspace-stats`
- 正文骨架：`# <Workspace> — Workspace Stats` + `## Overview` 总表 + `## Per-wiki` 每 wiki
  一节分表（pages / entities / concepts / sources / comparisons / syntheses / raw_files /
  last_log_entry / tags / memory_files）
- skill 写入场景：`scan`（与 INDEX.md 同一次刷新）

## A4. cross_queries/

- 维护方：**skill** 在 `query` 输出适合归档时 `Write`
- 文件命名：`<slug>.md`，kebab-case（精确 pattern 见 A8 表）
- frontmatter 必填（A7） + `type: cross-query`；`tags` 推荐
  `[workspace, cross-query, <涉及 wiki 的 tag>...]`；必填 `sources`（引用 wiki 内页路径数组）+
  `wikis`（涉及 wiki 名数组）
- skill 写入场景：`query` 输出用户确认归档时

## A5. LINT.md

- frontmatter 必填（A7） + `type: workspace-lint`
- 正文骨架：`# <Workspace> — Lint Report (<YYYY-MM-DD>)` + `## Per-wiki Issues`（每 wiki
  一段，本 wiki 内 lint 走 yzr-llm-wiki-management）+ `## Workspace-level Issues`
  （跨 wiki 重复 entity / 未注册子目录 / STATS 过期 / MEMORY 索引一致 / ...)
- skill 写入场景：`lint`（每次覆盖）

## A6. workspace MEMORY/

- 维护方：CLI init 时创建空目录 + 写 `MEMORY/MEMORY.md` 索引占位；后续条目由 `yzr-memory-management` skill
  写入 + 同步追加 MEMORY.md 索引一行。人类不写；CLI 不写
- MEMORY 不在 INDEX.md 中强制列出（agent 私有入口）
- **条目形式（完整 / 短）+ 何时写/不写 + 索引行格式** canonical = `<workspace>/AGENTS.md` 的「Memory 纪律」节（byte-owned 模板渲染），本文件不重复

### A6.1 MEMORY/MEMORY.md（索引）

无 frontmatter（被 `<workspace>/AGENTS.md` 用 `@MEMORY/MEMORY.md` `@import` 内联加载）；正文：顶部 1 段说明 + `## 索引` 段（完整/短两条格式共存）

### A6.2 MEMORY/*.md（非 MEMORY.md）

frontmatter 口径 canonical = `<workspace>/AGENTS.md` 的「Memory 纪律」节（byte-owned 模板渲染），
本文件不重复。lint `memory-not-indexed` 兜底；不强制 inbound 链接，不在 INDEX.md 列出

## A7. Frontmatter 字段通用规则

**通用必填 5 项**（workspace 级 markdown，**MEMORY/*.md 例外——见 A6.2**）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | string | 不含扩展名 |
| `type` | enum | 见下表 |
| `tags` | array | 可空 |
| `created` | date | `YYYY-MM-DD` |
| `updated` | date | `YYYY-MM-DD` |

**`type` 取值**（workspace 级 markdown）：

| `type` | 备注 |
| --- | --- |
| `workspace-index` | `<workspace>/INDEX.md`（唯一） |
| `workspace-stats` | `<workspace>/STATS.md`（唯一） |
| `workspace-lint` | `<workspace>/LINT.md`（唯一） |
| `cross-query` | `<workspace>/cross_queries/<slug>.md` |
| `workspace-memory` | `<workspace>/MEMORY/*.md`（若写 type；optional） |

**类型特化字段**：

| 字段 | 适用 type | 必填 | 含义 |
| --- | --- | --- | --- |
| `sources` | `cross-query` | 是 | 引用的 wiki 内页路径数组（相对 workspace 根） |
| `wikis` | `cross-query` / `workspace-memory` | `cross-query` 是 / `workspace-memory` 推荐 | 涉及的 wiki 名列表 |
| `description` | 所有 | 推荐 | 一句话 |

字段**语义**写法（怎么写好 `title` / `description` / `tags`）SSOT = `yzr-llm-wiki-management` page-templates.md#共有-frontmatter-段

## A8. 命名约束

本表只承载 **skill 写盘文件**的命名约束（这些文件 CLI 不读写、无机械 gate，约束唯一承载点
= 本节）。wiki name（`llmw wiki add` 创建时校验）与 CLI 内部标识符归 CLI；wiki 命名推荐
风格见 `<workspace>/AGENTS.md` 的「跨 wiki 约定」节

| 维度 | 规则 | 适用对象 |
| --- | --- | --- |
| cross_query slug | kebab-case `^[a-z0-9][a-z0-9-]*$` | `cross_queries/<slug>.md` |
| MEMORY 文件名 | kebab-case `^[a-z0-9][a-z0-9-]*$` | `<workspace>/MEMORY/*.md`（MEMORY.md 例外） |
| frontmatter 字段名 | 严格小写 + 下划线 | 所有 workspace 级 markdown |
| frontmatter `type` 值 | 严格小写 + 连字符（`workspace-index` / `workspace-memory` 等） | 所有 workspace 级 markdown |
