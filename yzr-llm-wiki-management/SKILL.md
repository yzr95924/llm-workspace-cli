---
name: yzr-llm-wiki-management
description: |
  当用户和本地、单用户、复利型 Markdown 个人 wiki（Karpathy 'LLM owns wiki' 模式）打交道时
  使用本 skill——覆盖：初始搭建、批量摄取 raw/ 资料（论文 / 文章 / 剪藏 / 外部代码仓 symlink
  接入）、跨页综合 / 对比 / 矛盾协调 / 答案归档回 wiki、矛盾 / 孤儿 / 过期摘要 lint、format
  升级迁移。坚持 raw/ 用户掌控 + wiki/ LLM 拥有 + AGENTS.md 单一真源 四层纪律。
  触发："把这篇论文摄取进 wiki" / "总结 wiki 里关于 X 的内容" / "wiki 里 A 和 B 说法矛盾，
  帮我协调" / "扫一下 wiki 有没有孤儿页 / 过期摘要" / "升级 wiki / 迁移到最新 format / 检查
  wiki 版本" / "把 X 仓库（源码）纳入 wiki" / "想搭一个 wiki 管理 X"。
  不适用：云端 / 团队协作 wiki（Notion / Confluence / Outline / GitHub Wiki）。
metadata:
  author: Zuoru YANG
  category: knowledge-base
  wiki_format_version: 0.39.0
---

# LLM Wiki Management

按 Karpathy [LLM Wiki 设计哲学](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
维护一个**本地**、**复利累积**的知识库：用户只管读 + 提供资料 + 提问题，LLM 负责摘要、
交叉引用、归档、簿记这些"无聊的部分"。和各类云端 wiki skill 的关键区别是
**本地文件 + 三层纪律**——vs 云端 MCP 单层文档。

本 skill 提供三块交付物：

- **SKILL.md（本文）**——工作流 + 纪律的"宪法"
- **确定性执行（归 llmw CLI，`llmw.content`）**——本 skill **零代码**。原 scripts/ 的
  deterministic 工具（lint / fixtures 检查 / ingest 探测 / 机械写）全部收敛为
  `llmw` 子命令：`llmw wiki lint / check-fixtures / ingest-diff / write`（详见
  §工作流各节）。高频确定性任务固化在 CLI，agent 只负责需要判断的部分。
- **references/**——按需加载：各操作详细流程（ingest / query / lint / upgrade）、页面模板
  （page-templates.md）、lint-checklist、external-repo（接入 + 跨主机重建）。骨架模板 + fixtures（CLI 字节级比对金标准）内建于
  `llmw/content/templates/wiki/`（CLI 包资产，`llmw wiki check-fixtures` 探测）、
  upgrade-workflow.md §六 (语义合并规则，agent 走 upgrade plan 时的合并依据)

## 何时不使用

"何时使用 / 不适用"已在 frontmatter description（含触发词），正文不重抄。本节只补**出路**与
正文独有负例：

- **云端协作 wiki**（Notion / Confluence / Outline Wiki / GitHub Wiki）——走对应的云端 wiki skill
- **一次性文档生成**（不是累积型）——直接用普通文件写入流程
- **没有 raw/ 资料 + 没有累积需求**——skill 的价值在"复利"，一次性整理用不上
- **需强结构化数据库**（带 schema / SQL / 全文检索后端）——wiki 规模 ≤ 数百页时
  index.md 足够；超过该规模再考虑迁移到专用工具
- **多人实时协作**——本 skill 假设单人使用（多账号实时协同走云端 wiki）
- **系统设计文档写作**（单篇正式设计文档）——走专门的系统文档 skill

## 输入 / 输出

### 启动时需具备的信息

| 信息 | 来源 | 备注 |
| --- | --- | --- |
| Wiki 根目录 | `LLM_WIKI_ROOT` 环境变量，或交互时问 | 例 `~/wiki/llm-systems` |
| 主题名 | setup 时一次性指定，写入 `AGENTS.md` | 例 "LLM Systems" |
| 操作类型 | 用户自然语言 | ingest / query / lint / upgrade / setup |
| 触发资料 | ingest 时给文件路径或目录 | 必须在 `raw/` 内 |

### 操作产物

- **setup** → 由 workspace CLI 完成（按 CLI 包内模板落盘），
  本 skill 不实现创建逻辑；产物形态为目录结构 + AGENTS.md（SSOT）+ CLAUDE.md（薄壳）+
  wiki/index.md + wiki/log.md + MEMORY/MEMORY.md + .gitignore
- **ingest** → 新增 / 更新 `wiki/sources/<slug>.md` + 同步实体 / 概念页 + 追加
  `log.md` 条目 + 更新 `index.md`
- **query** → 对话中给出答案（带引用），**可选**把答案归档为 `wiki/comparisons/`
  或 `wiki/syntheses/<slug>.md`
- **lint** → `log` 中报告：raw/ 是否被改、孤儿页、断裂交叉引用、过期摘要、缺
  frontmatter、log.md 格式
- **upgrade** → 跑 `llmw wiki lint --check-version` 输出 format 版本 + legacy 现场
  报告；`--apply` 把 upgrade plan 以 JSON 输出到 stdout（不落盘）供 agent 按
  `references/upgrade-workflow.md` 走 Edit/Write 修复；详见 §5 Upgrade

## 执行原则 / 边界

### 核心原则

> **操作前置（orient ritual，所有操作通用）**：每次 ingest / query / lint 启动前，**不依赖 symlink**
> ——按以下顺序读完四件套再动手：
>
> 1. `Read <$LLM_WIKI_ROOT>/AGENTS.md`——拿到本 wiki 的主题名、边界配置、
>    Page Thresholds（纪律 SSOT 是 `AGENTS.md`；`CLAUDE.md` 是 `@AGENTS.md` 薄壳，不持纪律）。
>    AGENTS.md 不含 tag 白名单（在 `wiki/tags.md`——见本节 §核心原则 §11）。AGENTS.md
>    顶部一行 `@MEMORY/MEMORY.md` + 一行 `@scripts/SCRIPTS.md` `@import`——自动展开 `@import`
>    的 agent 透明拿到 MEMORY / scripts 全文，不展开的由 AGENTS.md 顶部强制 Read 指令兜底
>    （详见 `llmw/content/templates/wiki/agents-md-template.md`（CLI 包内） 顶部）。**别处由 skill
>    按需读 AGENTS.md 时** 也走相同的 `@import` 链路，
>    **不**需要单独 `Read MEMORY.md` 补齐索引（除非要看各 `<slug>.md` 正文）。
> 2. `Read <$LLM_WIKI_ROOT>/wiki/index.md`——知道有哪些页、分布在哪些类别，避免重复创建 / 漏交叉引用
> 3. `Read <$LLM_WIKI_ROOT>/wiki/log.md`（最近 ~30 行即可）——看清最近活动，避免重复
>    ingest / 漏归档旧工作
> 4. **`Read <$LLM_WIKI_ROOT>/scripts/SCRIPTS.md`**（按需）——确认本 wiki 是否有
>    项目级扩展脚本的**完整分节契约**（使用场景 / 调用约定 / 作用 / 前置依赖）；不强制（wiki 可无
>    scripts/），但**触发非标工作流前**必须先查（AGENTS.md 顶部的 `@scripts/SCRIPTS.md` import
>    已加载全文，详细契约随读出）
>
> 四件套任一未读完不写任何 wiki 内容。100+ 页的 wiki 还应在 `wiki/` 全域
> `Grep "<topic>"` 补一次——单看 index.md 可能漏掉 entity/concept 页之间的引用关系。

1. **raw/ 由用户掌控，LLM 只读**——完整纪律（含两处写权限例外 + 滑坡防线 + target 角色切分）见 `<wiki-root>/AGENTS.md` §一 + [`references/external-repo.md`](references/external-repo.md) / [`references/ingest-workflow.md §10`](references/ingest-workflow.md#十rawdiscussions-草稿消化可选入口)
2. **wiki/ 由 LLM 撰写**——用户不写 wiki 页（编辑 AGENTS.md 除外）；纪律见 `AGENTS.md` §一 `wiki/` 节
3. **AGENTS.md 是本 wiki 纪律的 SSOT，不是文档**——禁手改（byte-owned by CLI）；自定义纪律沉淀去 MEMORY/（详见 `AGENTS.md` §六）
4. **每次写入必更 log.md——追加走 `llmw wiki write log`**（格式 + `LOG_RETENTION_LIMIT` 截断由脚本保证）；lint 只兜底带外手改。**逃生舱**：脚本不支持的形态手写 Edit/Write 合法、lint 兜底——脚本是默认路径不是闸门
5. **每页必带 YAML frontmatter——新建页走 `llmw wiki write new`**（5 必填 + 推荐 `description`）。权威定义（`type` 取值 / reserved / `sources` 特化 / 可信度信号）见 [`references/page-templates.md`](references/page-templates.md) §一；例外清单（index / log / MEMORY / MEMORY*）同节
6. **交叉引用走相对路径**——`[link](sources/foo.md)`，禁用 wikilink / 绝对路径；详见 `AGENTS.md` §二.5
7. **index.md 是 wiki 内容页的单一入口**——所有非 log / 非 MEMORY 页必须在 index.md 出现；详见 `AGENTS.md` §一 `wiki/index.md`
8. **query 的好答案必问"是否归档"**——能写回 wiki 的不浪费在对话里；详见 `AGENTS.md` §四 + 工作流 §2
9. **MEMORY/ 是 LLM agent 的私有记忆**——新条目走 `llmw wiki write memory add`；只改 `MEMORY/MEMORY.md` 这一份（无副本漂移）。物理位置在 `<wiki-root>/` 而非 `wiki/` 内 = publish 时自然留作私有层不外传；写入流程见工作流 §4
10. **LLM 修改已审核页必须清 `reviewed` 戳**——每次编辑后跑 `llmw wiki write touch`；生命周期规则 canonical 见 [`page-templates.md`](references/page-templates.md#可选可信度与认知质量信号) "可信度与认知质量信号"段；lint 用 `reviewed-stale` 兜底
11. **tag 白名单在 `wiki/tags.md`**——取值 / 解析 / 审计循环 canonical 在 fixture 头部说明块（落盘即读）；lint 语义见 [`lint-checklist.md §11`](references/lint-checklist.md#11-tag-taxonomy-校验)
12. **scripts/ 由 `SCRIPTS.md` 索引承载**——`@import` 自动加载；agent 先看索引行再按需 Read，不自动遍历；详见 `AGENTS.md` §一 `scripts/` + fixture 头部说明块

### 边界

- **不**绕过 `AGENTS.md` 自创约定——若 AGENTS.md 没说的，**先问用户**再写
- **不**在 query 时偷偷归档——必须先展示答案 + 询问用户
- **不**忽略 lint 报告——长期不 lint 的 wiki 一定会腐烂

> 其余纪律（raw 只读、wiki 拥有、log/index/MEMORY/scripts、交叉引用、git 操作、编辑工具）
> 与 `AGENTS.md` §一 §二 完全重合，详见该文件；不在此重抄。

### 反模式（绝对禁止）

- 在 wiki 页面里手写"先写一段话再贴图"等散文式总结（散弹式散落口径冲突的根源）
- 把同一个概念分散在多个 entities/ 文件里（必须先 search 是否已有同名页）
- 改 wiki 不追加 log 条目就收工——失去操作语义记录（正路 `llmw wiki write log`，见 §核心原则 §4）
- 跨 wiki 互引但不更新对端 index（同步是用户责任）

> 其余反模式（raw 操作违规、wikilink、复制 llmw 源码、anchor 字段修改、external 子目录布局、
> discussions 外推、source-in-discussions 等）与 `AGENTS.md` §一 §二 /
> [`references/external-repo.md`](references/external-repo.md) §二 完全重合，详见该文件。

### 反合理化三件套（纪律型 skill 必带）

> 本 skill 含 14+ 行"必须 / 禁止 / 不"+"**不**" 起始段 = 纪律型。纪律型禁令在
> LLM 压力下会被以各种合理化借口绕开——三件套只堵一类：**已被合理化的违反**。
> 未被合理化的违反（直接忽略规则）= 缺 §反模式 清单本身，与三件套无关。

#### Rationalization Table

> **baseline 实跑记录**：3 次 RED 运行——① 带纪律 ingest
> 任务：全程合规零借口；② 无纪律 ingest 任务（Iron Law 创建场景）：仍合规（模型自带该
> 规范知识）；③ 带纪律 + 用户施压任务（"随便记一下 / 赶时间"）：产出真实借口一条（下表
> 第 1 行）+ 一处静默遗漏（frontmatter 缺必填 `tags` 字段，无借口直接漏掉）。

| 常见借口 | 为什么是错的 | 应改做什么 |
| --- | --- | --- |
| "剪藏只有一句话，按'克制建页'原则和你说的小事轻办，一个资料页够了"（实跑 transcript） | 用户的"随便 / 赶时间"是态度不是豁免——写 wiki 页即触发 5 必填 / 建页阈值 / log 纪律；"轻办"是拿用户情绪当省略纪律的挡箭牌（同轮还静默漏了必填 `tags` 字段） | 流程不缩水；"克制建页"判断如实执行但**向用户说明**（"本文只有一个中心主题，暂不建概念页，出现第二篇同主题再补"），字段与 log 纪律照走 |
| "用户没明说要我做这一步" | 本 skill 的纪律点（log / lint / reviewed 戳 / 等）触发条件是**事**而非**人**——写了 wiki 页就是触发 lint，写了 source 就是清 reviewed 戳——用户没说 = 沉默 ≠ 豁免 | 先按 §执行原则走完纪律，再决定是否省略；省略要写明理由进 log 条目 |
| "这次是单页 ingest，跳过 entity/concept 同步更快" | 知识孤岛 = wiki 复利亏空——单页也一样要 cross-link；"更快"是把当前 case 凌驾于复利结构之上 | 哪怕只挂 1 个 entity 页也要同步；交叉引用是 wiki 的 ROI 核心 |
| "我把 source `cp` 进 raw/ 比走 `Write` + 创建 page 更直接" | raw/ 不可变 + raw/external/ 例外是 symlink 不是 cp——`cp` 进 raw/ 触发 `raw-external-anchor-mismatch` 一连串 finding | 用 `Edit/Write` 写 wiki/sources/`<slug>`.md；raw 是用户私有 |
| "`reviewed: true` 是一周前人标的，我没改多少内容，留着就行" | `reviewed: true` 是"这一刻内容背书"快照，**任何** LLM 对正文的修改都让它失效（包括 typos / 字段补全）——留戳 = 假装审过 | 任何 Edit/Write 后**必须**删 `reviewed` + `reviewed_at` 两字段，回到默认未审核态 |
| "外部代码仓我 cp -r 进 raw/ 也算接入，symlink 没必要" | cp -r 占用 wiki 仓磁盘 + 违反 external-repo.md §1——"也算"是把"接入意图"和"接入手段"混淆 | 走 `ln -s` 创建 symlink + 写 `.symlink-anchor.toml` 的 `[[entry]]` 块 |
| "这个 wiki 没 git，不写 log 也行" | log.md 记的是**操作语义**（ingest/query/lint）+ 近期活动速览（orient ritual 读它避免重复工作）——这是 git diff 不直接体现的；完整文件历史才靠 git | 任何 wiki 改动**必须**追加 log 条目（哪怕 wiki 无 git） |

> **表内条目两类**：第 1 行 = 实跑 transcript 逐字摘录；其余 6 条 = 从 §反模式 / §边界
> 反推的**嫌疑清单**（多次 baseline 未复现）——保留为未来实跑验证 / 替换的候补。保持
> "只收录 agent 实际说过的"原则：实跑复现即替换 / 未复现不新增（预写 = 噪声 + 信号干扰）。

#### 违反字面 = 违反精神

任何对 §核心原则 / §边界 / §反模式 三段禁令的"看起来不同但效果一致"绕法都算违反——本 skill 常见绕法前三：

- 把 `Edit` / `Write` 改为 `Read` + 手动生成新内容再 `Write`——**不算**绕开"用 Read 之外工具做自动修改"禁令，操作工具是 Write 一样算
- 把"不删除 wiki 页"解释为"先把内容拷出去再 `rm` 然后写回"——**不算**绕开不删禁令，状态效果完全等同
- 把"raw/ 由用户掌控，LLM 只读"解释为"我`cp` 进 raw/ 后立即再`rm`，窗口里我读到了内容 = 等价于只读"——**不算**，写入发生在第一步

**禁止**用"严格按字面 / 严格按精神"二选一措辞给 agent 留退路——任何"看起来不同但效果等价"都是违反。

#### Red Flags（念头清单 — 出现即停）

念头出现 ≠ 已违反；念头 = 警告 = 重读 §核心原则 / §边界 / §反模式 三段。

- "用户说'随便记一下 / 赶时间 / 别太正式'——纪律可以打折了"（实跑观察）
- "我觉得这一步对当前 case 不必要"
- "用户没明说要我做这步"
- "这样更快 / 更省 token / 更高效"
- "约定没禁止"
- "我已经做了等价的事" / "效果一样不算违反"
- "先这样留着，回头再补"
- "我自己生成字段比 frontmatter 严格写更灵活"
- "log 条目这次先跳过，反正是 wiki 不是 git"
- "raw 反正用户也天天改，我帮一下忙"
- "lint 报了一堆，反正都是 warn 不算错"

> 没有"念头清单 = 已违反"的递进——念头出现是**信号**，再走下去才成**行动**。
> 但**念头后仍继续** = 默认承担违反精神的责任。

## 工作流 / 步骤

### 0. 一次性 setup（首次使用）—— 由 workspace CLI 完成

> **职责边界**：本 skill 只负责 wiki 的**成长阶段**（ingest / query / lint）。
> wiki 仓的**创建与删除**由 workspace CLI 负责——命令是 `llmw`（**与本 skill 同仓维护**，
> 命令名与参数见其自带文档，本节只给形态示例）。
> wiki 仓的"出生形态"由 CLI 包内模板渲染决定——`llmw wiki check-fixtures` 探测。

**基本流程**：

```bash
# 1. 调 workspace CLI 创建 wiki 仓（`--topic` 可选，缺省 = name；`--model` 若给必须是 registry 里的 model_id）
llmw wiki --name=llm-systems add --topic="LLM Systems" --model=minimax-m3-1m
# CLI 按包内模板落盘：目录结构 + AGENTS.md（SSOT）+ CLAUDE.md（薄壳）+
# wiki/index.md + wiki/log.md + .gitignore + scripts/SCRIPTS.md +
# git 默认跳过（CLI 不碰 git，仓库由用户自己托管）。

# 2. 把原始资料放进 raw/（用户手动 / Obsidian Web Clipper / 浏览器下载）
cp ~/Downloads/some-article.md ~/wiki/<topic-name>/raw/articles/
```

**LLM agent 接管后做什么**：

1. 验证 CLI 落盘——读 `<wiki-root>/AGENTS.md` 确认主题名 + 日期替换正确；
   `wiki/index.md` / `wiki/log.md` 存在且 frontmatter 完整；`<wiki-root>/CLAUDE.md` 是薄壳
2. 跑 orient ritual（见 §执行原则 / 边界 顶部引用块）
3. 询问用户是否做首次 ingest——若是，把第一份资料路径给 agent

**为什么 setup 与日常分两层**：CLI = 出生/死亡（一次性，结构稳定），LLM = 成长（高频交互）。
最大收益是 **wiki schema 与 LLM 工作流解耦**——CLI 可独立升级实现（Python → Rust），
SKILL 不动。

### 1. Ingest（摄取新资料）

**触发**："把这篇摄取到 wiki" / `raw/` 有新文件 / 跑 `llmw wiki ingest-diff` 发现未摄取项。

**流程摘要**（agent 驱动；详细 7 步 + 批处理见
[`references/ingest-workflow.md`](references/ingest-workflow.md)；外部代码仓 5 步接入 /
漂移刷新 / 跨主机重建见 [`references/external-repo.md`](references/external-repo.md)）：

1. 跑 `llmw wiki ingest-diff`（日常加 `--check-stale`）找出未摄取/待重摄文件清单
2. **单篇对一下要点**——仅交互式单篇或少量场景：确认主题方向 / 重点交叉的 entity / 用户判断要保留
3. 对每个文件：Read 全文 → 提取元数据 → `llmw wiki write new --type source ...` 建骨架 →
   写正文（stale-raw 走 **Edit**,**不** Write 覆盖）→ 同步 entity/concept(只 append
   "Sources" 段) → `llmw wiki write index add` → `llmw wiki write log --op ingest` →
   **编辑过的页跑 `llmw wiki write touch`**
4. **commit**（仅启用 git 时）：节奏由用户/agent 决定，**不**自动 commit

### 批处理摄取（≥ 3 份 raw 同时摄入）

走批处理路径而非逐份。**一次聚合、一次写入、一次索引**——避免 N 次重复 search / N 次
index 更新 / N 条 log。5 步流程 + 为什么批处理 + log 标题前缀 `Bulk:` 的细节见
[`references/ingest-workflow.md`](references/ingest-workflow.md)「批处理」节。

**外部代码仓作为语料**——若用户说"把 X 仓库纳入 wiki"：**不**内嵌拷仓，走
[`external-repo.md`](references/external-repo.md) 的 symlink 路径
（`raw/` 总纪律的**写权限例外之一**——LLM 主导接入；另一处例外是 `raw/discussions/`
协作草稿，见 ingest-workflow.md §10）。
5 步接入（确认 symlink/target → LLM 验证 → 读
git 身份字段 → 创建 symlink + 写 anchor → 后续 `llmw wiki ingest-diff` 扫描）+ 漂移刷新 + 跨主机
重建见 [`references/external-repo.md`](references/external-repo.md)。

### 2. Query（跨页综合）

**触发**："wiki 里有 X 吗" / "总结 wiki 中关于 Y 的内容" / "对比 A 和 B"。

**流程**：

1. **先看 index.md**——按关键词 / 类别找候选页
2. **读相关页**（不读 raw——raw 已经在 source 页里消化过）
3. **跨页综合**——用引用形式带 source 链接；矛盾处显式标注："A 说 X（来源：...），
   B 说 Y（来源：...），需要更深入调研"
4. **展示答案 + 询问归档**——如果答案有"对比 / 综合 / 发现联系"的性质，询问用户：
   "这段答案适合归档回 wiki 作为 comparisons/`<slug>`.md 吗？"
5. **用户同意后归档**——走 references/page-templates.md 的 `comparison` 或
   `synthesis` 模板 + 追加 log 条目

详细 query 流程与判定规则见 [`references/query-workflow.md`](references/query-workflow.md)。

### 3. Lint（健康检查）

**触发**："lint wiki" / 定期（频率阈值见 [lint-checklist.md §七](references/lint-checklist.md#七lint-频率)）/ 大型 wiki 主动建议。

**流程**：

1. 跑 `llmw wiki lint` 做 deterministic 检查
2. 脚本覆盖（大类如下，权威清单见 [`references/lint-checklist.md`](references/lint-checklist.md)）：
   raw 不可变性 / frontmatter 字段 / 孤儿页 / 断链 / log.md 格式 / 过期摘要 / 页面体量
   / 认知质量与可信度信号（`reviewed` / `contested` / `contradictions`）/ `raw/external/`
   symlink ↔ anchor 关联（external-repo.md）/ fixtures 一致性（见下文「fixtures 一致性检查」段）
3. 脚本输出后 **agent 还要做半定性检查**：矛盾主张 / 缺失交叉引用 / 建议新摄取方向
4. 报告 + 询问用户哪些修

详细 checklist 见 [`references/lint-checklist.md`](references/lint-checklist.md)。

### 4. Memory（写入 LLM agent 持久化记忆）

**触发**：在 ingest / query / lint 过程中识别到值得沉淀的信息——踩坑、用户偏好、跨文档关联。

**何时写**：

- 遇到踩坑（例：raw/ PDF 频繁 OCR 错误，下次让用户先转格式）
- 发现用户偏好（例：用户偏好表格化对比、不喜散文式总结）
- 跨 ingest 关联（两 source 页指向同一论文不同章节）
- lint 报告的 recurring pattern（每次 lint 都报某 type 缺字段）

**流程摘要**（agent 主动；frontmatter 字段 / 索引同步 / 完整 vs 短条目判定的权威定义在
AGENTS.md 模板 §一「MEMORY/」节 + 仓库根 `MEMORY/MEMORY.md` 索引自身的写法 — fixture `memory-index.txt` 头部说明块 canonical）：

1. 决定是否值得写——能否让未来 agent 工作更顺？
2. 判别条目形式：**完整**（含 why+how 上下文）→ `llmw wiki write memory add --slug ... --title ...`
   建文件 + 索引行，再 Edit 写正文；**短**（纯 reminder）→ 直接 `MEMORY/MEMORY.md` 加一行索引
3. 写正文——记录具体经验，含上下文 / 解决步骤 / 未来如何避免
4. **不**追加 log 条目 / **不**在 wiki/index.md 列出（MEMORY 不走单一入口约束）

**纪律**：

- 不删除任何 MEMORY 文件——踩坑记录沉淀下来
- 写新文件时保留原 `created` 字段；只更新 `updated`
- 用户**不**直接编辑 MEMORY/——若用户想补充，先转告 agent 由 agent 写入

### 5. Upgrade（升级 wiki format）

**触发**：用户说"升级 wiki / 迁移 / 检查 wiki 版本 / 老格式 / format 升级 / 是否需要
reformat"；或 `llmw wiki lint` 报告 legacy warn。

**职责：** CLI（`llmw wiki lint --check-version`）是探测器，只扫不修；agent 按 stdout JSON 返回的 upgrade plan + `fixtures_actions[]` 用 Edit/Write 修复。迁移期不走 `llmw wiki write`（脚本只认识当前形态——迁移 = 格式流动期，硬编码会破坏）；迁移依据 SSOT = plan actions[] + upgrade-workflow.md §六；**不**追加 log 条目。

**完整步骤**（含 fixtures 一致性检查 10 类约定文件 / `agents-md-template-sync` 处理 /
语义合并规则 / 脚本 vs LLM 合并决策树 / 清理临时文件）见
[`references/upgrade-workflow.md`](references/upgrade-workflow.md)。

## 参考样例

5 个完整样例（setup / ingest / query / lint / upgrade）见 [`references/examples.md`](references/examples.md)——按需 Read。
