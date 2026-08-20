---
name: yzr-llm-workspace-management
description: |
  当用户要管理由 yzr-llm-wiki-management 维护的多个本地 wiki 时使用本 skill：在 workspace
  层级扫描所有 wiki、生成与维护全局 INDEX.md / STATS.md / LINT.md，做跨 wiki 综合问答
  （路由 / 合成 / 对比 / 局部），维护跨 wiki 交叉引用，做 workspace 级 lint，沉淀跨 wiki
  agent 私有记忆到 MEMORY/。弥补 workspace CLI 只能管元数据不能感知内容的缺陷——CLI 负责
  确定性元数据操作，本 skill 负责需要 LLM 判断的跨 wiki 决策。
  触发："总结我所有 wiki 中关于 X 的内容" / "对比 wiki A 和 wiki B 对 Y 的看法" / "这个问题
  该查哪个 wiki" / "扫一下我的 workspace" / "workspace 整体 lint" / "记一下：用户偏好按
  时间线分 wiki" / "wiki A 的 X 在 wiki B 也有，加个链接" / "升级 workspace / 迁移到最新
  spec / 检查 workspace 版本"。
  不适用：单 wiki 的 ingest / query / lint（走 yzr-llm-wiki-management）；workspace / wiki
  元数据 CRUD（走 workspace CLI）；云端协作 wiki（走 yzr-outline-wiki）；一次性文档生成
  （直接用普通文件写入流程）。
metadata:
  author: Zuoru YANG
  category: knowledge-base
  workspace_spec_version: 0.8.0
---

# LLM Workspace Management

维护一个**本地**、**多 wiki**
工作区的"全局视图"和跨 wiki 编排能力——单个 wiki 的 ingest / query / lint 仍走
`yzr-llm-wiki-management` SKILL.md skill。本 skill 站在所有 wiki
之上，做需要跨 wiki 判断的事情。

本 skill 提供三块交付物：

- **SKILL.md（本文）**——工作流 + 边界的"宪法"

  （toml 完整 schema 由 CLI 代码 SSOT，spec 不做权威定义）
- **确定性执行（归 llmw CLI）**——本 skill **零代码**。一致性检查 + 升级都收敛为两条 CLI 命令：
  - `llmw check-fixtures`：只探测（输出 drift 报告，不写盘）
  - `llmw upgrade`：workspace 骨架 + 逐 wiki 聚合确定性升级（默认 dry-run）
  不一致时以探测器为准；spec 文档仅说明设计意图

## 输入 / 输出

### 启动时需具备的信息

| 信息 | 来源 | 备注 |
| --- | --- | --- |
| Workspace 路径 | `$LLMW_WORKSPACE` 环境变量，或默认 `~/yzr-llm-wiki-workspace`，或交互时问 | workspace CLI 通常在 `enter` 时设好本变量 |
| 操作类型 | 用户自然语言 | `scan` / `query` / `link` / `lint` / `upgrade` |
| Query 范围（仅 query） | 用户自然语言或显式指定 wiki 名 | 不指定走全局 INDEX 路由 |

### 操作产物

- **scan** → 写 `<workspace>/INDEX.md`（人类可读概览）+ `<workspace>/STATS.md`（结构化统计），
  按 SKILL.md 附录 A2 / A3 格式落盘
- **query** → 对话中给出答案（带每 wiki 引用）；可选落 `<workspace>/cross_queries/<slug>.md`
  （需用户确认后归档；格式见附录 A4 cross_queries）
- **link** → 在涉及跨 wiki 引用的 wiki 各自的 source / entity 页追加跨 wiki 链接（走
  `yzr-llm-wiki-management` 的 ingest 流程，不直接写 wiki 文件）
- **lint** → 写 `<workspace>/LINT.md`（最近一次报告，每次 lint 覆盖；格式见
  附录 A5 LINT.md 格式）+ 对话中总结
- **upgrade** → 跑 `llmw upgrade`（默认 dry-run，加 `--apply [--yes]` 落盘）；3 终态 JSON
  由 CLI 输出；详见 §6 Upgrade

## 执行原则 / 边界

### 与 workspace CLI 的边界

**本 skill 不调 workspace CLI**。原因：

1. workspace CLI 只读 / 写三份元数据 + 启动 session——本 skill 读 workspace.toml /
   wiki_metadata.toml **直接读**比解析 CLI 输出更可靠（CLI 输出是给人看的，文本可能改）
2. 本 skill 不修改 workspace.toml / wiki_metadata.toml——告诉用户跑 `llmw wiki ...`，
   人类执行。CLI 的元数据写入是用户驱动的决策，skill 不越权
3. workspace CLI 已通过 `wiki enter` 把 session 启动好（包含 model overlay）；
   本 skill 在 session 内只做内容层决策，不需要再 `enter`
4. **依赖单向 DAG（无环）**：本 skill 与 workspace CLI 都只依赖 spec 文件对齐契约
   workspace 文件契约见本 SKILL.md 附录；wiki 文件契约束见 yzr-llm-wiki-management SKILL.md 与 references/；本 skill
   **不**直接依赖 workspace CLI 的代码或二进制，运行时只委托 `yzr-llm-wiki-management`（下节）

### 与 yzr-llm-wiki-management 的边界

**本 skill 委托单 wiki 操作给 `yzr-llm-wiki-management`**：单 wiki 的 ingest / query / lint /
写跨 wiki 链接到某 wiki 的 source 页，一律转交其对应流程——本 skill **不直接**编辑
`<wiki>/wiki/**`（保持 wiki 内 log.md 同步、frontmatter 必填等不变量）。本 skill 自己做
**workspace 层**的事：scan 聚合 / route 路由 / 跨 wiki 综合与对比 / 跨 wiki 链接建议 /
workspace lint / 跨 wiki memory。

### 文件归属（不变量，强制）

### 本 skill 可写的产物（其他文件一律只读或委托）

| 文件 / 目录 | 谁写 | 边界 |
| --- | --- | --- |
| `<workspace>/INDEX.md` | 本 skill | scan 时聚合写 |
| `<workspace>/STATS.md` | 本 skill | scan 时聚合写 |
| `<workspace>/cross_queries/` | 本 skill | 跨 wiki 综合问答归档 |
| `<workspace>/LINT.md` | 本 skill | workspace 级 lint 报告 |
| `<workspace>/MEMORY/` 中的 `*.md` + 同步 `MEMORY.md` 索引 | 本 skill | 仅跨 wiki 经验（单 wiki 经验归 `<wiki>/MEMORY/`） |

**完整归属表 + 四分表见本仓 AGENTS.md「顶层数据流」+「骨架所有权四分表」**。

**违反归属 = bug**：
- 本 skill 写 `workspace.toml` / `.gitignore` / `AGENTS.md` / `CLAUDE.md` 均越权
  （前两类由 `llmw upgrade` 接管；后两类是用户宪法）
- CLI 写 `INDEX.md` / `STATS.md` / `LINT.md` / `cross_queries/` / `<workspace>/MEMORY/*.md` 均越权

**MEMORY 跨边界混淆**：本 skill **禁止**写
`<wiki>/MEMORY/`（单 wiki 记忆归 `yzr-llm-wiki-management`）；同样禁止把跨 wiki 观察
写到单 wiki MEMORY——按附录 A6 scope 严格区分。

## 工作流 / 步骤

### 0. 启动检查

每次进入本 skill 时：

1. 定位 workspace 路径：`$LLMW_WORKSPACE` → 默认 `~/yzr-llm-wiki-workspace` → 交互问
   （同「启动时需具备的信息」表）
2. 验证 `<workspace>/workspace.toml` 存在——不存在提示用户 "workspace 还没 init，
   跑 `llmw init` 初始化"（**不**替用户跑）
3. **加载跨 wiki MEMORY 索引**：在 workspace 根工作时经 `<workspace>/AGENTS.md` 的
   `@MEMORY/MEMORY.md` import 自动加载；非根目录工作 / 原生读 AGENTS.md 不展开 `@` 的 agent →
   显式 `Read <$LLMW_WORKSPACE>/MEMORY/MEMORY.md` 补齐（加载机制见
   附录 A6.1 MEMORY.md 索引格式）
4. **加载作用域边界**：`<workspace>/AGENTS.md` / `CLAUDE.md` 只约束**跨 wiki 工作**——当
   agent cwd 在 `<wiki>/` 子目录内、改跑 `yzr-llm-wiki-management` 时，本 skill 纪律
   （含跨 wiki MEMORY）**不**接管，由 `<wiki>/AGENTS.md` 单 wiki 纪律生效（模板顶部有
   scope 声明；警惕 MEMORY scope 混淆：workspace `MEMORY/` = 跨 wiki，`<wiki>/MEMORY/` =
   单 wiki；log 写入归属：wiki 内 ingest 写 `<wiki>/wiki/`，非 workspace 级 INDEX / STATS）
5. **不**自动跑 `scan`——等用户给操作意图

### 1. Scan / refresh-index

**触发**："扫一下 workspace" / "更新 INDEX.md" / 用户说"workspace 该刷新了"。

**流程**：

1. 读 `<workspace>/workspace.toml` 拿 `[wikis]` 注册表
2. 对每个 wiki：
   - 读 `<wiki>/wiki_metadata.toml`（CLI 维护）
   - 读 `<wiki>/AGENTS.md` §0（拿主题名）+ §一（拿边界）
   - 读 `<wiki>/wiki/index.md`（已有内容 + 段落骨架）
   - 扫 `<wiki>/wiki/{entities,concepts,sources,comparisons,syntheses}/` 拿 page counts
   - 扫 `<wiki>/raw/` 递归拿原始资料数（仅 `find` + 计数，不读内容）
   - 读 `<wiki>/wiki/log.md` 末条拿 last activity
   - 读 `<wiki>/MEMORY/` 拿 memory files 数（仅文件名）
3. 读 `<workspace>/MEMORY/MEMORY.md` 索引（知晓已有跨 wiki 记忆，供 query 路由 / scan 报告
   引用）；按 wiki name 字母序聚合，写 `<workspace>/INDEX.md`（格式见
   附录 A2 INDEX.md）+ `<workspace>/STATS.md`
   （格式见附录 A3 STATS.md）
4. 原子写（POSIX `tmp + fsync + rename`）
5. 对话中报告："已刷新 INDEX.md / STATS.md，X 个 wiki，Y 个 page，Z 个原始资料"

**何时不做 scan**：用户只想做 query → 先用现有 INDEX.md；INDEX.md 缺失或明显过期
（覆盖不到新增 wiki）再提示先 scan。

### 2. Query（跨 wiki Q&A）

**触发**："总结我所有 wiki 中关于 X 的内容" / "对比 A 和 B 对 Y" / "X 该查哪个 wiki"。

**4 种模式**（按用户意图 + 是否指定 wiki 范围自动判定）：

| 模式 | 触发关键词 | 流程 |
| --- | --- | --- |
| **route** | "应该查哪个 wiki" / "属于哪个 wiki" | 读 INDEX.md → 按 topic / tag / description 匹配 → 返回 1–3 个候选 wiki 名 + 理由 |
| **synthesis** | "总结所有" / "综合所有 wiki" / "跨 wiki 总结" | route → 每候选 wiki query → 合并 + 标注每 wiki 来源 |
| **compare** | "对比 A 和 B" / "A 和 B 的区别" | 读 wiki-A 与 wiki-B 的 `wiki/index.md` → query 双侧 → diff 风格对比 |
| **local** | "只看 wiki X" / "在 X 里查 Y" | 走 `yzr-llm-wiki-management` query（单 wiki） |

**判定规则**：

- 用户显式指定 1 个 wiki → **local**
- 用户显式指定 2 个 wiki 且带"对比 / 区别 / 异同" → **compare**
- 用户说"哪个 / 属于哪里 / 应该放哪" → **route**
- 其余 → **synthesis**

**good query 必有"是否归档"环节**——参考 `yzr-llm-wiki-management` query 流程 SKILL.md
的"是否归档"原则。归档位置：

- 答案涉及**单 wiki** → 归档到 `<wiki>/wiki/syntheses/<slug>.md`（走 `yzr-llm-wiki-management`）
- 答案涉及**多 wiki** → 归档到 `<workspace>/cross_queries/<slug>.md`（本 skill 直接写，
  格式见附录 A4 cross_queries）

归档正文引用上游易变事实时过感知测试（漂移点规避）——规则 SSOT 见
`yzr-llm-wiki-management` 的 `references/ingest-workflow.md`「正文引用的稳定性」节。

### 3. Link（跨 wiki 交叉引用）

**触发**："wiki A 里的 entity X 在 wiki B 也存在，加链接" / "扫一下跨 wiki 重复 entity"。

**流程**：

1. **扫描**：对每个 wiki 的 `wiki/entities/` + `wiki/concepts/`，提取所有 entity name
   （frontmatter `title` 或文件名 slug）
2. **去重聚合**：跨 wiki 同名 / 近义（用 description 比对）的 entity 收集为候选对
3. **建议**：对话中列出候选对，让用户选哪些要加跨 wiki 链接
4. **写入**：用户确认后，对每个涉及的 wiki，调用 `yzr-llm-wiki-management` 的 ingest
   流程更新对应 entity / concept 页——追加"跨 wiki 引用"段，引用路径用相对 workspace
   根（例 `[huawei_storage wiki 的 storage-architecture](../huawei_storage_wiki/wiki/concepts/storage-architecture.md)`）

**不变量**：本 skill **不直接**编辑 `<wiki>/wiki/**`——一律通过 `yzr-llm-wiki-management`
的 ingest 流程（保持 wiki 内的 log.md 同步、frontmatter 5 必填、不变量等）。

### 4. Lint（workspace 级）

**触发**："workspace lint" / "workspace 健康检查" / 定期（如每次 scan 时顺带）。

**流程**：

1. **workspace 级 deterministic 检查**（agent 内联 / 后续拆脚本）：
   - 重复 entity 跨 wiki（同名 + 不同 slug 的对）
   - 失效跨 wiki 链接（cross_queries/*.md 的 `sources` 路径不存在；`<wiki>/wiki/**`
     中的 `../<another-wiki>/...` 路径不存在）
   - 未注册的 wiki 子目录（磁盘上有 `<wiki>/AGENTS.md` 但 workspace.toml 没有注册）
   - workspace.toml 注册但磁盘上不存在的 wiki（孤儿注册）
   - STATS.md 与 INDEX.md 的 wiki 列表是否一致
   - MEMORY 索引一致性：扫 `<workspace>/MEMORY/*.md`（排除 `MEMORY.md`），任一文件未在
     `MEMORY/MEMORY.md` 索引列出 → 报 `memory-not-indexed`（severity = info，与 wiki 侧
      lint-checklist 对应条目对齐）
2. **本 skill 做的半定性检查**：
   - 主题重叠的 wiki 是否需要合并
   - tag 体系是否混乱（同名 tag 含义不同 / 同含义 tag 命名不一）
3. **本 skill 不做的**：单 wiki 内部 lint（重复 entity / 缺 frontmatter / 矛盾主张等）
   ——转交 `yzr-llm-wiki-management`
4. **输出**：写 `<workspace>/LINT.md`（格式见
   附录 A5 LINT.md 格式）+ 对话中报告

**何时不做 lint**：用户只问 query → 不 lint；用户说"扫一下" → scan 而非 lint。

### 5. Memory（跨 wiki agent 私有记忆）

**触发**：在 scan / query / link / lint 过程中识别到**跨 wiki**值得沉淀的信息时主动写。

**写**：跨 wiki 视角的组织偏好 / lint 模式 / 经验关联；**不写**：单 wiki 踩坑、跨 wiki 综合
答案本身、一次性观察。完整写 / 不写清单与 scope 边界见
附录 A6 workspace MEMORY（含"何时写/不写"）。

**流程**：

1. 识别值得沉淀的观察 → **scope 自检**确认跨 wiki（不只是单个 wiki 的事）
2. 判别条目形式（完整 / 短条目），判别尺度 + frontmatter / 索引格式 + 命名约束见
   附录 A6.2 MEMORY/*.md + A8 命名约束
3. 写入 `MEMORY/<slug>.md`（完整条目）或直接在 `MEMORY/MEMORY.md` 索引追加短条目一句话
4. **同步 `MEMORY.md` 索引一行**（漏写 = 下次读不到，lint `memory-not-indexed` 兜底）

**不动** `<workspace>/INDEX.md` / `STATS.md` / `LINT.md` / 任何 `<wiki>/MEMORY/`——
MEMORY 是 agent 私有入口；`<workspace>/MEMORY/` 目录 + `MEMORY.md` 索引由 CLI init
建（附录 A6.1 MEMORY.md 索引格式），skill 不重建。

**MEMORY 与单 wiki MEMORY 的清晰边界**：

| 场景 | 写哪 |
| --- | --- |
| "wiki A 的 ingest 总是失败，因为 raw/ 里有特殊字符" | `<A>/MEMORY/ingest-special-char-pitfall.md`（单 wiki 经验） |
| "用户偏好把所有 storage 相关放 A wiki，把 LLM 相关放 B wiki" | `<workspace>/MEMORY/user-storage-vs-llm-preference.md`（跨 wiki 偏好） |

### 6. Upgrade（升级 workspace 骨架）

**触发**："升级 workspace / 检查 workspace 版本 / spec 升级"。

**职责切分**：`llmw upgrade`（CLI 命令）= **全部确定性操作**——workspace 骨架 + 逐 wiki
聚合两段式，按本仓 AGENTS.md 骨架所有权四分表
分类处理（详见 `llmw upgrade` 命令文档 + `llmw/content/workspace_fixtures.py` 升级引擎）。
`llmw check-fixtures` 仅探测（不写盘）。agent = **跑命令 + 解读输出**。

**流程**：

1. `llmw upgrade` 默认 dry-run → 输出 workspace + 各 wiki 的处理计划 + 3 终态 JSON
   （加 `--json` 机器可读）
2. **解读 3 终态**：
   - `done` → 收尾，提示用户"workspace 升级完成，X 个 wiki 已升"
   - `blocked_drift` → 按 `hint` 字段把自定义内容搬 `MEMORY/`，再 `llmw upgrade
     --apply --yes` 重跑
   - `verify_failed` → 报告用户，转人工
3. 各 wiki 的后续内容迁移（如有 `content-page-transform` 残留）走
   `yzr-llm-wiki-management` 的工作流——本 skill 不代跑

**不**写 `INDEX.md` / `STATS.md` / `LINT.md`（升级不是 scan / lint 事件）。

**边界**：CLI 不碰 `workspace-models.toml` 等含密配置，升级只动 byte/block/header-owned 类
文件。跨 skill 委托（某个 wiki 版本落后）由 `llmw upgrade` 输出提示，本 skill 不代跑兄弟
skill 的 upgrade 工作流（按工作流名引用：走 `yzr-llm-wiki-management` 的 upgrade
工作流）。

## 参考样例

### 样例 1：跨 wiki 综合问答

> 用户："我所有 wiki 中关于 RAID 有什么记录？"

1. skill 读 `<workspace>/INDEX.md` → 找到 `huawei_storage_wiki` 的描述含"存储"
2. mode = **synthesis**（用户说"所有 wiki 中"）
3. 转交 `yzr-llm-wiki-management` 给 `huawei_storage_wiki` 做 query："RAID"
4. 拿到答案（带 source 页引用），对话中给用户，附"只涉及 1 个 wiki，是否归档到
   `huawei_storage_wiki/wiki/syntheses/raid-overview.md`？"
5. 用户确认 → 走 `yzr-llm-wiki-management` 写 synthesis 页 + log 条目

### 样例 2：路由

> 用户："我刚下了一篇 LLM inference 论文，应该放哪个 wiki？"

1. skill 读 INDEX.md + 读每个 wiki 的 description / tags
2. mode = **route**
3. 返回："`huawei_storage_wiki` 主题是存储，不相关；`test` wiki 主题是 test，也不相关；
   建议新建一个 wiki（`llmw wiki --name=llm-inference add ...`）"
4. **不**自动跑 `llmw wiki add`——告诉用户跑 CLI 命令

## 参考文件

- **必读**：`workspace-agents-md-template.md`（CLI 包内 `llmw/content/templates/workspace/`）——
  `<workspace>/AGENTS.md`（SSOT）的 canonical 模板字节金标准（内建 `llmw/content/templates/workspace/`，
  CLI init 时按此拷）；薄壳 `<workspace>/CLAUDE.md`
  见 CLI 包内 `workspace-claude-md-template.md`
- **必读**：`yzr-llm-wiki-management` SKILL.md 与 references/ 下各 workflow + page-templates.md——
  单 wiki 内的目录 / frontmatter / 命名约束（本 skill 操作 wiki 时遵循）
- **委托目标**：`yzr-llm-wiki-management` SKILL.md——
  单 wiki ingest / query / lint / memory 工作流（本 skill 的单 wiki 操作委托给它）
- **CLI 文档**：workspace CLI（命令 `llmw`，与本 skill 同仓维护）——本 skill
  **不直接调**，但用户的 `init / add / remove / config / enter / model ...` 命令参考此处

## 附录：产物格式契约与读取契约

> 本节合并原 `references/workspace-spec.md` ——workspace 文件的**归属 + skill 读取契约
> + 产物格式**。spec 文档已删除（2026-08-20：CLI 实现参考职能已被同仓代码吸收；
> 残量并入本 SKILL.md）。

### A1. workspace.toml 读取契约（SKILL 的读方视角）

- 路径：`<workspace-root>/workspace.toml`
- 完整字段 schema 权威在 CLI 代码（CLI 是唯一写方；具体文件路径 / 符号名归 CLI，
  `workspace-toml-reads-satisfied` check 校验读取契约完整性）

**skill 实际读取的字段**（`scan` / `upgrade` 用）：

| 字段 | 用途 |
| --- | --- |
| `templates_version` | `llmw upgrade` 版本比对 + 自动 bump（含 `workspace_spec` / `wiki_spec` 双分量） |
| `[wikis.<name>].path` | skill `scan` 遍历 wiki 子目录 |
| `[wikis.<name>].created_at` | INDEX 内 wiki 排序 |

### A2. INDEX.md（`<workspace-root>/INDEX.md`）

- 维护方：**skill** 在 `scan` / `refresh-index` 时创建 + 维护；CLI 不创建、不写
- frontmatter 5 必填（A7）+ `type: workspace-index`（reserved）；`title` 推荐 `"Workspace Index"`；
  `tags` 推荐 `[workspace, index]`
- 正文骨架：

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
  - **page counts**: 0 entities / 0 concepts / ...
  - **key entities**: [...]
  - **one-line summary**: ...

  ## Cross-wiki Links
  ...（短描述）
  ## Recent Activity (across all wikis)
  ...
  ```

- skill 写入场景：`scan` / `refresh-index`（原子写 `tmp + fsync + rename`）
- CLI 写入场景：**无**

### A3. STATS.md（`<workspace-root>/STATS.md`）

- 维护方：**skill** 在 `scan` 时一并创建 + 维护；与 INDEX.md 区别：结构化（表格）
- frontmatter 5 必填 + `type: workspace-stats`
- 正文骨架：`# <Workspace> — Workspace Stats` + `## Overview` 总表 +
  `## Per-wiki` 每 wiki 一节分表（pages / entities / concepts / sources / comparisons /
  syntheses / raw_files / last_log_entry / tags / memory_files）
- skill 写入场景：`scan`（与 INDEX.md 同一次刷新）
- CLI 写入场景：**无**

### A4. cross_queries/（`<workspace-root>/cross_queries/`，可选）

- 维护方：**skill** 在 `query` 输出适合归档为 cross-wiki synthesis 时 `Write`
- 是 workspace 级的 synthesis 类比——`yzr-llm-wiki-management` 把好的单 wiki query
  答案归到 `<wiki>/wiki/syntheses/<slug>.md`，本 skill 把好的跨 wiki query 答案归到
  `<workspace>/cross_queries/<slug>.md`
- 文件命名：`<slug>.md`，kebab-case `^[a-z0-9][a-z0-9-]*$`（A8）
- frontmatter 5 必填 + `type: cross-query`；`tags` 推荐 `[workspace, cross-query, <涉及 wiki 的 tag>...]`；
  必填 `sources`（引用 wiki 内页路径数组）+ `wikis`（涉及 wiki 名数组）
- skill 写入场景：`query` 输出用户确认归档时
- CLI 写入场景：**无**

### A5. LINT.md（`<workspace-root>/LINT.md`，可选）

- 维护方：**skill** 在 `lint` 时写最近一次报告（历史报告**不**累积，被新一次覆盖，是快照）
- frontmatter 5 必填 + `type: workspace-lint`
- 正文骨架：`# <Workspace> — Lint Report (<YYYY-MM-DD>)` +
  `## Per-wiki Issues`（每 wiki 一段，本 wiki 内 lint 走 yzr-llm-wiki-management）+
  `## Workspace-level Issues`（跨 wiki 重复 entity / 未注册子目录 / STATS 过期 /
  MEMORY 索引一致 / ...）
- skill 写入场景：`lint`（每次覆盖）
- CLI 写入场景：**无**

### A6. workspace MEMORY/（`<workspace-root>/MEMORY/`）

- 维护方：CLI init 时刻创建空目录 + 写 `MEMORY/MEMORY.md` 索引占位；后续条目由 **skill**
  写入 + 同步追加 MEMORY.md 索引一行。人类不写 MEMORY；CLI 不参与后续
- 目录名 `MEMORY` **大写**，区别于小写 `raw` / `wiki` / `cross_queries`
- MEMORY 不在 INDEX.md 中强制列出（agent 私有入口）
- 条目形式按事实颗粒度选（完整 / 短两条）——完整清单与判别尺度见包内
  `workspace-agents-md-template.md` §五（**canonical 副本**，本 SKILL 不重复）
  - 完整条目：`MEMORY/<slug>.md` + 索引行 `- slug — 摘要 → [正文](slug.md)`
  - 短条目：仅索引行 `- 一句话事实`，无对应 `.md`
  - 两种格式可在同一 `MEMORY.md` 共存；lint `memory-not-indexed` 兜底"有 .md 未索引"
- **scope 严格区分**（核心不变量，避免变成 junk drawer）：
  - ✅ `<workspace>/MEMORY/` 写**跨 wiki** 的 LLM 经验（用户偏好 / 跨 wiki 关联 / lint 模式 / 综合经验）
  - ❌ 不写单 wiki 观察（归 `<wiki>/MEMORY/`，由 `yzr-llm-wiki-management` 维护）
  - ❌ 不写跨 wiki 综合答案本身（归 `<workspace>/cross_queries/`）
  - ❌ 不写一次性观察（直接 chat）

#### A6.1 MEMORY/MEMORY.md（索引）

- 无 frontmatter（被 `<workspace>/AGENTS.md` 用 `@MEMORY/MEMORY.md` `@import` 内联加载；
  对齐仓库根 `MEMORY/MEMORY.md` / wiki MEMORY.md 形态）
- 正文：顶部 1 段说明 + `## 索引` 段（完整/短两条格式共存）

#### A6.2 MEMORY/*.md（非 MEMORY.md）

- 命名：kebab-case `^[a-z0-9][a-z0-9-]*$`
- frontmatter 5 必填 + `type` = 5 类 wiki 内容页 enum 或 `workspace-memory`（按记忆内容性质选）
- 推荐 `description` / `wikis` 字段
- lint 校验：5 必填 + `memory-not-indexed` 兜底；与 wiki 内容页一致但不强制 inbound 链接 /
  不在 INDEX.md 列出

### A7. Frontmatter 字段通用规则

**通用必填 5 项**（所有 workspace 级 markdown 共享）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | string | 不含扩展名 |
| `type` | enum | 见下表 |
| `tags` | array | 可空 |
| `created` | date | `YYYY-MM-DD` |
| `updated` | date | `YYYY-MM-DD` |

**`type` 取值**：

| `type` | 备注 |
| --- | --- |
| `entity` / `concept` / `source` / `comparison` / `synthesis` | 5 类 wiki 内容页 enum——`<workspace>/MEMORY/*.md` 按记忆内容性质选 |
| `index` / `log` | 2 类 wiki reserved（`<wiki>/wiki/index.md` / `<wiki>/wiki/log.md`，workspace 不直接用） |
| `workspace-index` | `<workspace>/INDEX.md`（唯一） |
| `workspace-stats` | `<workspace>/STATS.md`（唯一） |
| `workspace-lint` | `<workspace>/LINT.md`（唯一） |
| `cross-query` | `<workspace>/cross_queries/<slug>.md` |
| `workspace-memory` | `<workspace>/MEMORY/*.md`（非 MEMORY.md） |

**与 wiki page-templates.md 的关系**：workspace 的 `workspace-memory` 与 wiki 内容页 5 类 enum
（`<wiki>/MEMORY/*.md` 可按记忆性质选）是 location 区分而非冲突；两份 `MEMORY.md` 索引
（workspace 与 wiki 各一份）均无 frontmatter 形态对齐。

**类型特化字段**：

| 字段 | 适用 type | 必填 | 含义 |
| --- | --- | --- | --- |
| `sources` | `cross-query` | 是 | 引用的 wiki 内页路径数组（相对 workspace 根） |
| `wikis` | `cross-query` / `workspace-memory` | `cross-query` 是 / `workspace-memory` 推荐 | 涉及的 wiki 名列表 |
| `description` | 所有 5 必填类 | 推荐 | 一句话 |

### A8. 命名约束

| 维度 | 规则 | 适用对象 |
| --- | --- | --- |
| Wiki name | `[a-z0-9][a-z0-9_-]*`，1–64 字符；推荐纯 kebab-case | `[wikis.<name>]` key + `<wiki-name>/` 子目录名 |
| cross_query slug | kebab-case `^[a-z0-9][a-z0-9-]*$` | `cross_queries/<slug>.md` |
| MEMORY 文件名 | kebab-case `^[a-z0-9][a-z0-9-]*$` | `<workspace>/MEMORY/*.md`（MEMORY.md 例外） |
| frontmatter 字段名 | 严格小写 + 下划线 | 所有 workspace 级 markdown |
| frontmatter `type` 值 | 严格小写 + 连字符（`workspace-index` / `workspace-memory` 等） | 所有 workspace 级 markdown |

> `model_id` 等 CLI 内部标识符（模型注册表等）的命名规则归 CLI（skill 不读不写）。

### A9. 不在本节范围内

- toml 字段全集 schema（`workspace.toml` / `wiki_metadata.toml` + CLI 内部配置——归 CLI 代码 SSOT）
- cross-wiki Q&A / 交叉引用 / lint / MEMORY 的**工作流**（归本 SKILL.md 主体各节）
- frontmatter 字段的**语义**写法（归 LLM 写作视角，参照 yzr-llm-wiki-management page-templates.md §一）
- Obsidian / 编辑器偏好
- INGEST / 单 wiki query / 单 wiki lint（走 `yzr-llm-wiki-management`）
