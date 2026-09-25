---
name: yzr-llm-workspace-management
description: |
  当用户要对多个本地 LLM wiki（yzr-llm-wiki-management 体系）的知识内容做跨 wiki 操作时
  使用本 skill——从 workspace 全局视角：跨 wiki 扫描与索引（INDEX/STATS）、跨 wiki 问答
  （路由/综合/对比）、跨 wiki 交叉引用与重复 entity 治理、workspace 级健康检查（LINT）、
  跨 wiki 记忆（MEMORY/）、workspace format 升级。
  触发："总结我所有 wiki 中关于 X" / "对比 wiki A 和 B 对 Y" / "这问题该查哪个 wiki" /
  "扫一下我的 workspace" / "统计所有 wiki 的页面数" / "workspace 健康检查" /
  "wiki A 的 X 在 B 也有，加个链接" / "升级 workspace"。只要要读、汇总、对比或治理多个
  wiki 里的内容——即使没明说 workspace 或 skill 名，也务必使用本 skill。
  不适用：单 wiki 内操作（走 yzr-llm-wiki-management）；workspace / wiki 元数据配置、
  加删 wiki、session 启停等单条 llmw 命令操作（直接跑 llmw 即可，见 llmw --help，无需
  加载本 skill）；云端协作 wiki（Notion / Confluence / Outline 等）
metadata:
  author: Zuoru YANG
  category: knowledge-base
  workspace_format_version: 0.10.1
---

# LLM Workspace Management

维护一个**本地多 wiki** 工作区的"全局视图"和跨 wiki 编排——单 wiki 的 ingest / query / lint 走
`yzr-llm-wiki-management` skill

写盘产物的格式契约集中在 [`references/formats.md`](references/formats.md)（A1-A8）——正文
「格式 Ax」均指该文件，各流程写盘前必读对应 A 节

## 输入 / 输出

### 启动时需具备的信息

| 信息 | 来源 | 备注 |
| --- | --- | --- |
| Workspace 路径 | `$LLMW_WORKSPACE`，或默认 `~/yzr-llm-wiki-workspace`，或交互问 | 环境变量未设时 CLI 走默认路径 |
| 操作类型 | 用户自然语言 | scan / query / link / lint / upgrade |
| Query 范围（仅 query） | 用户自然语言或显式指定 wiki 名 | 不指定走全局 INDEX 路由 |

## 执行原则 / 边界

### 与 workspace CLI 的边界

本 skill 在场时可调 `llmw`——读 / 探测 / 升级类命令直接执行（子命令与参数见
`llmw --help`，不枚举）；会改 workspace / wiki 元数据或影响运行中 session 的命令，
先把完整命令给用户确认后再执行

**不手写 toml**——元数据写必须经 CLI（schema 校验 / 原子写 / 唯一性约束由 CLI
保证）。**涉及 api_key 的命令始终由用户亲自执行**（secret 不过 agent）

### 与 yzr-llm-wiki-management 的边界

单 wiki 操作（ingest / query / lint / 写 wiki 内文件）一律委托 `yzr-llm-wiki-management`——
本 skill **不直接**编辑 `<wiki>/wiki/**`（保持 log.md 同步、frontmatter 等不变量）。本 skill
只做 workspace 层的事：scan 聚合 / 路由 / 跨 wiki 综合与对比 / 跨 wiki 链接建议 / workspace lint /
跨 wiki memory

### 本 skill 可写的产物（不变量，强制）

| 文件 / 目录 | 谁写 | 边界 |
| --- | --- | --- |
| `<workspace>/INDEX.md` | 本 skill | scan 时聚合写 |
| `<workspace>/STATS.md` | 本 skill | scan 时聚合写 |
| `<workspace>/cross_queries/` | 本 skill | 跨 wiki 综合问答归档 |
| `<workspace>/LINT.md` | 本 skill | workspace 级 lint 报告 |
| `<workspace>/MEMORY/` 中的 `*.md` + 同步 `MEMORY.md` 索引 | 本 skill | 仅跨 wiki 经验（单 wiki 经验归 `<wiki>/MEMORY/`） |

**违反归属 = bug**。完整归属表 + 四分表见 `<workspace>/AGENTS.md` 的「本 workspace 的边界」+「本文件本身的纪律」（含骨架所有权四分表）节（byte-owned 模板渲染）

### 反合理化三件套（硬禁令的护栏）

> 本 skill 的硬禁令集中在上面两节：不手写 toml / api_key 命令用户亲自执行 / 不直接编辑
> wiki 文件 / 归属表「违反 = bug」。三件套只堵**已被合理化的违反**

#### Rationalization Table

> **收录纪律**：只从实跑 transcript 收录（预写借口 = 噪声 + 信号干扰）。本表尚无实跑记录
> ——未来 RED / 实跑中出现的借口逐行补入（列头即收录格式）

| 常见借口 | 为什么是错的 | 应改做什么 |
| --- | --- | --- |

#### 违反字面 = 违反精神

任何对硬禁令的"看起来不同但效果一致"的绕法都算违反。判定锚点：`workspace*.toml` /
`wiki_metadata.toml` 的字节是否由 agent 直接产生、api_key 是否经过 agent、`<wiki>/wiki/**`
是否被本 skill 改写——任一被触碰即违反。**禁止**用"严格按字面 / 严格按精神"二选一措辞给
agent 留退路

#### Red Flags（念头清单 — 出现即停）

念头出现 ≠ 已违反；念头 = 警告 = 重读上面两节

- "用户催得急，直接改 toml 更快"
- "只是补两行，等价于 CLI 会写的内容，不算手写"
- "api_key 反正我也要用到，顺手帮用户配上"
- "这处 wiki 文件改动很小，不走 wiki skill 也等价"
- "先写了再说，CLI / lint 能兜底"
- "约定没禁这一种改法"

> 条目来源：标「实跑观察」者为 RED transcript 实录；未标注者为通用合理化模式（红旗是低成本预警网、广撒无害；实跑捕获新借口时追加并标注）

## 工作流 / 步骤

### 启动检查

每次进入本 skill 时：

1. 定位 workspace 路径（来源链见「输入 / 输出」表）
2. 验证 `<workspace>/workspace.toml` 存在——不存在提示用户 "workspace 还没 init，跑 `llmw init` 初始化"（**不**替用户跑）
3. **加载跨 wiki MEMORY 索引**：在 workspace 根工作时经 `<workspace>/AGENTS.md` 的
   `@MEMORY/MEMORY.md` import 自动加载；非根目录工作 / 原生读 AGENTS.md 不展开 `@` 的 agent →
   显式 `Read <$LLMW_WORKSPACE>/MEMORY/MEMORY.md` 补齐
4. **加载作用域边界**：当 agent cwd 在 `<wiki>/` 子目录内、改跑 `yzr-llm-wiki-management`
   时，本 skill 纪律不接管，由 `<wiki>/AGENTS.md` 单 wiki 纪律生效
5. **不**自动跑 `scan`——等用户给操作意图

### Scan / refresh-index

**触发**："扫一下 workspace" / "更新 INDEX.md" / 用户说"workspace 该刷新了"

**流程**：

1. 读 `<workspace>/workspace.toml` 拿 `[wikis]` 注册表
2. 对每个 wiki 收集：`wiki_metadata.toml`（CLI 维护）+ `AGENTS.md`「本 wiki 的边界」节 +
   `wiki/index.md` + 内容页子目录 page counts + `raw/` 递归计数（不读内容）+
   `wiki/log.md` 末条（last activity）+ `MEMORY/` 文件数（仅文件名）
3. 读 `<workspace>/MEMORY/MEMORY.md` 索引，按 A2 排序规则聚合，写 INDEX.md + STATS.md（格式 A2/A3）
4. 对话中报告："已刷新 INDEX.md / STATS.md，X 个 wiki，Y 个 page，Z 个原始资料"

**何时不做 scan**：用户只想做 query → 先用现有 INDEX.md；INDEX.md 缺失或明显过期（覆盖不到新增 wiki）再提示先 scan

### Query（跨 wiki Q&A）

**触发**："总结我所有 wiki 中关于 X 的内容" / "对比 A 和 B 对 Y" / "X 该查哪个 wiki"

**4 种模式 + 判定优先级 local > compare > route > synthesis**：

| 模式 | 触发关键词 | 流程 |
| --- | --- | --- |
| **local** | "只看 wiki X" / "在 X 里查 Y" | 委托 `yzr-llm-wiki-management` query |
| **compare** | "对比 A 和 B" / "A 和 B 的区别" | 读双侧 wiki/index.md → query → diff 风格对比 |
| **route** | "应该查哪个 wiki" / "属于哪个 wiki" | 读 INDEX.md → 按 topic / tag / description 匹配 → 返回 1-3 个候选 wiki |
| **synthesis** | "总结所有" / "综合所有 wiki" / 兜底 | route → 每候选 wiki query → 合并 + 标注每 wiki 来源 |

**good query 必有"是否归档"环节**——归档落点与两级归属的纪律见 `<workspace>/AGENTS.md`
「查询 / 综合纪律」；workspace 级归档由本 skill 直接写（格式 A4），wiki 级部分转交 `yzr-llm-wiki-management`

归档正文引用上游易变事实时过感知测试——规则 SSOT 见 `yzr-llm-wiki-management` 的 ingest-workflow.md「正文引用的稳定性」节

### Link（跨 wiki 交叉引用）

**触发**："wiki A 里的 entity X 在 wiki B 也存在，加链接" / "扫一下跨 wiki 重复 entity"

**流程**：

1. **扫描**：对每个 wiki 的 `wiki/entities/` + `wiki/concepts/`，提取所有 entity name（frontmatter `title` 或文件名 slug）
2. **去重聚合**：跨 wiki 同名 / 近义（用 description 比对）的 entity 收集为候选对
3. **建议**：对话中列出候选对，让用户选哪些要加跨 wiki 链接
4. **写入**：用户确认后，对每个涉及的 wiki，调用 `yzr-llm-wiki-management` 的 ingest
   流程更新对应 entity / concept 页——追加"跨 wiki 引用"段（xref 格式见
   `<workspace>/AGENTS.md` 的「跨 wiki 约定」节）

### Lint（workspace 级）

**触发**："workspace lint" / "workspace 健康检查" / 定期（如每次 scan 时顺带）

**流程**：

1. **workspace 级 deterministic 检查**（agent 内联）：
   - 重复 entity 跨 wiki（同名 + 不同 slug 的对）
   - 失效跨 wiki 链接（cross_queries/*.md 的 `sources` 路径不存在；`<wiki>/wiki/**` 中的 `../<another-wiki>/...` 路径不存在）
   - 未注册的 wiki 子目录（磁盘上有 `<wiki>/AGENTS.md` 但 workspace.toml 没有注册）
   - workspace.toml 注册但磁盘上不存在的 wiki（孤儿注册）
   - STATS.md 与 INDEX.md 的 wiki 列表是否一致
   - MEMORY 索引一致性：扫 `<workspace>/MEMORY/*.md`（排除 `MEMORY.md`），任一文件未在
     `MEMORY/MEMORY.md` 索引列出 → 报 `memory-not-indexed`（severity = info；名字沿用
     wiki 侧 finding 名——workspace 级由 agent 内联报告，CLI 不发射）
2. **半定性检查**：
   - 主题重叠的 wiki 是否需要合并
   - tag 体系是否混乱（同名 tag 含义不同 / 同含义 tag 命名不一）
3. **本 skill 不做的**：单 wiki 内部 lint——转交 `yzr-llm-wiki-management`
4. **输出**：写 `<workspace>/LINT.md`（格式 A5）+ 对话中报告

> **为什么这些检查 agent 内联**：脚本化准入针对写路径；本节为只读诊断，无写路径，
> 且这些文件 CLI 不读写（A8）——检查随 skill 格式契约同侧演进

**何时不做 lint**：用户只问 query → 不 lint；用户说"扫一下" → scan 而非 lint

### Memory（跨 wiki agent 私有记忆）

**触发**：在 scan / query / link / lint 过程中识别到**跨 wiki**值得沉淀的信息时主动写

完整"何时写/不写" + 判别尺度 canonical = `<workspace>/AGENTS.md` 的「Memory 纪律」节（byte-owned 模板渲染），本 skill 不重复

**流程**：

1. 识别值得沉淀的观察 → scope 自检确认跨 wiki
2. 判别条目形式（完整 / 短）
3. 写入 `MEMORY/<slug>.md`（完整条目）或直接在 `MEMORY/MEMORY.md` 追加短条目一行
4. **同步 `MEMORY.md` 索引一行**（漏写 = 下次读不到，lint `memory-not-indexed` 兜底）

**不动** `<workspace>/INDEX.md` / `STATS.md` / `LINT.md` / 任何 `<wiki>/MEMORY/`

### Upgrade（升级 workspace 骨架）

**触发**："升级 workspace / 检查 workspace 版本 / format 升级"

`llmw upgrade`（CLI）= 全部确定性操作——workspace 骨架 + 逐 wiki 聚合两段式，按
`<workspace>/AGENTS.md` 的「本文件本身的纪律」节（含骨架所有权四分表）分类处理。
`llmw check-fixtures` 仅探测（不写盘）。agent = 跑命令 + 解读输出

**流程**：

1. `llmw upgrade` 默认 dry-run → 输出 workspace + 各 wiki 的处理计划 + 终态 JSON（加 `--json` 机器可读）
2. **解读终态**：按 JSON 字段行动——`status` 定终态；`hint` / `residue[]`（旧自定义段被丢弃项）/
   `verified.failures[]` 自带处理指引，`verify_failed` 修完重跑（幂等）。`dry_run` 是默认模式
   的正常输出、非失败。agent 侧补充：收尾时向用户报"X 个 wiki 已升"；逐 wiki 聚合段内异常
   条目按段内 hint 转人工，**不阻断**其它 wiki
3. 各 wiki 的后续内容迁移走 `yzr-llm-wiki-management` 工作流——本 skill 不代跑

**不**写 `INDEX.md` / `STATS.md` / `LINT.md`（升级不是 scan / lint 事件）。升级只动
byte/block/header-owned 骨架 + `workspace.toml` 的 `templates_version` 分量；不碰含密配置

## 参考样例

### 样例 1：跨 wiki 综合问答

> 用户："我所有 wiki 中关于 RAID 有什么记录？"

1. skill 读 `<workspace>/INDEX.md` → 找到 `huawei_storage_wiki` 的描述含"存储"
2. mode = **synthesis**
3. 转交 `yzr-llm-wiki-management` 给 `huawei_storage_wiki` 做 query："RAID"
4. 拿到答案（带 source 页引用），对话中给用户，附"只涉及 1 个 wiki，是否归档到 `huawei_storage_wiki/wiki/syntheses/raid-overview.md`？"
5. 用户确认 → 走 `yzr-llm-wiki-management` 写 synthesis 页 + log 条目

### 样例 2：路由

> 用户："我刚下了一篇 LLM inference 论文，应该放哪个 wiki？"

1. skill 读 INDEX.md + 读每个 wiki 的 description / tags
2. mode = **route**
3. 返回："`huawei_storage_wiki` 主题是存储，不相关；`test` wiki 主题是 test，也不相关；建议新建一个 wiki（`llmw wiki --name=llm-inference add ...`）"
4. 提议代跑 `llmw wiki --name=llm-inference add`——用户确认后执行（skill 在场做 route，顺手闭环）
