---
name: yzr-llm-wiki-management
description: |
  当用户在本地、复利型 Markdown 个人 wiki（Karpathy 'LLM owns wiki' 模式）内工作时
  使用本 skill——覆盖：摄取 raw/ 资料（论文 / 剪藏 / 外部代码仓）、查询与跨页
  综合 / 矛盾协调、结论归档回 wiki、孤儿 / 过期摘要 lint、format 升级。
  触发："把这篇论文摄取进 wiki" / "wiki 里有没有 / 总结一下关于 X 的内容" / "wiki 里 A 和
  B 说法矛盾" / "把刚才的结论记进 wiki" / "扫一下 wiki 有没有孤儿页 / 过期摘要" /
  "升级 wiki / 检查 wiki 版本" / "把 X 仓库纳入 wiki"。只要用户要消化资料 / 查 wiki 沉淀 /
  归档新结论——即使没提 skill 名，也务必使用本 skill。
  不适用：云端 / 团队 wiki（Notion / Confluence / Outline 等）；wiki 元数据配置、增删
  wiki、session 启停（单条 llmw 命令，直接跑即可）；跨 wiki / workspace 层操作（归
  workspace 层 skill）；MEMORY/ 的写入与治理（归 yzr-memory-management skill）；cwd 不是
  wiki 根（无 `wiki_metadata.toml` + AGENTS.md 骨架）
metadata:
  author: Zuoru YANG
  category: knowledge-base
  wiki_format_version: 0.43.5
---

# LLM Wiki Management

## 输入与输出

| 方向 | 内容 |
| --- | --- |
| 输入 | wiki 根（session cwd；否则 `$LLM_WIKI_ROOT` 或问用户） |
| 输出 | `wiki/` 内容页（entity / concept / source / comparison / synthesis）+ `wiki/log.md` / `wiki/index.md` / `wiki/tags.md` 条目 + `MEMORY/` 条目 |

## 执行原则

### 核心原则

> **操作前置（orient ritual，所有操作通用）**：每次 ingest / query / lint 启动前，按以下
> 顺序读完四件套再动手：
>
> 1. **确认 `<wiki-root>/AGENTS.md` 已在上下文**（薄壳 `CLAUDE.md` 或原生加载，会话常驻）——
>    拿主题名与「当前配置」表（`Wiki Format 版本` 行）；MEMORY 全文随其自动加载
> 2. `Read <$LLM_WIKI_ROOT>/wiki/index.md`——有哪些页、分布在哪些类别，避免重复创建 / 漏交叉引用
> 3. `Read <$LLM_WIKI_ROOT>/wiki/log.md`（最近 ~30 行）——看清最近活动，避免重复 ingest / 漏归档
> 4. **`scripts/SCRIPTS.md`**（已随 AGENTS.md 自动加载；wiki 可无 scripts/）——**要跑
>    `scripts/` 下自定义脚本前**（即操作不在 `llmw wiki` 命令与本文各工作流的覆盖面内）必须先查
>    其分节契约（使用场景 / 调用约定 / 前置依赖）
>
> 四件套任一未读完不写任何 wiki 内容。100+ 页的 wiki 还应在 `wiki/` 全域
> `Grep "<topic>"` 补一次——单看 index.md 可能漏掉 entity/concept 页之间的引用关系

1. **raw/ 由用户掌控，LLM 只读**——例外以 wiki 根 `AGENTS.md`「本 wiki 的边界」为准
   （自动加载，不得外推）；接入外部仓见 [`ref/external-repo.md`](ref/external-repo.md)，
   草稿消化见 [`ref/ingest-workflow.md「raw/discussions/ 草稿消化」`](ref/ingest-workflow.md)
2. **写操作正路 = `llmw wiki write` 系列**——log 追加走 `write log`、新建页走 `write new`、
   清 `reviewed` 戳走 `write touch`、MEMORY 新条目走 `write memory add`、index 条目走
   `write index add`；格式 + 滚动窗口截断由 `write` 保证（上限见 `wiki/log.md` 头部），lint
   只兜底带外手改。**逃生舱**：命令不支持的形态手写 Edit/Write 合法——write 是默认路径不是闸门
3. **每页必带 YAML frontmatter**（必填字段 + 推荐 `description`）；权威定义与例外清单见
   [`ref/page-templates.md「共有 frontmatter 段」`](ref/page-templates.md)
4. **LLM 修改已审核页必须清 `reviewed` 戳**——每次编辑后跑 `llmw wiki write touch`；
   生命周期规则 canonical 见 [`page-templates.md「生命周期规则」`](ref/page-templates.md)；
   lint 用 `reviewed-stale` 兜底
5. **tag 白名单唯一真源在 `wiki/tags.md`**——agent 遇新 tag **直接追加、不询问用户**，
   用户审计直接删；取值规则 / 解析约束详见该文件头部说明块（入口：wiki 根 `AGENTS.md`
   「tag 白名单字典」节）；finding 含义 / 修法用 `llmw wiki lint --explain=tag-not-in-taxonomy`

### 边界

- **不**绕过 `AGENTS.md` 自创约定——若 AGENTS.md 没说的，**先问用户**再写

> 其余边界纪律以 wiki 根 `AGENTS.md` 为准（自动加载，会话常驻）

### 反模式（绝对禁止）

- 跨 wiki 互引但不更新对端 index（对端同步经 workspace 层 link 工作流、用户确认后执行）

> 其余反模式以 wiki 根 `AGENTS.md` + [`ref/external-repo.md「反模式」`](ref/external-repo.md)为准

### 反合理化三件套（纪律型 skill 必带）

> 本 skill 是纪律型 skill（含多条"必须 / 禁止 / 不"+"**不**" 起始段）。纪律型禁令在
> LLM 压力下会被以各种合理化借口绕开——三件套只堵一类：**已被合理化的违反**

#### Rationalization Table

> **baseline 实跑记录**：3 次 RED 运行（带纪律 / 无纪律 / 带纪律 + 用户施压）仅产出
> 真实借口一条（下表第 1 行）+ 一处静默遗漏（缺必填 `tags`）

| 常见借口 | 为什么是错的 | 应改做什么 |
| --- | --- | --- |
| "剪藏只有一句话，按'克制建页'原则和你说的小事轻办，一个资料页够了"（实跑 transcript） | 用户的"随便 / 赶时间"是态度不是豁免——写 wiki 页即触发必填字段 / 建页阈值 / log 纪律；"轻办"是拿用户情绪当省略纪律的挡箭牌（同轮还静默漏了必填 `tags` 字段） | 流程不缩水；建页阈值判断如实执行（canonical 见 [`page-templates.md「建页 / 追加 / 归档阈值」`](ref/page-templates.md)）但**向用户说明**（"本文只有一个中心主题，暂不建概念页，出现第二篇同主题再补"），字段与 log 纪律照走 |

> **收录纪律**：条目**只**从实跑 transcript 收录（预写借口 = 噪声）；实跑出现新借口
> 才补入，未出现不新增

#### 违反字面 = 违反精神

任何对「核心原则 / 边界 / 反模式」三段禁令的"看起来不同但效果一致"绕法都算违反——最常见的三种：

- 把 `llmw wiki write` 能做的写操作改用手写 `Edit` / `Write` 完成，再声称走了逃生舱——**不算**：
  逃生舱只覆盖命令不支持的形态，默认路径只有 `llmw wiki write` 系列
- 把"不删除 wiki 页"解释为"先把内容拷出去再 `rm` 然后写回"——**不算**绕开不删禁令，状态效果完全等同
- 把"raw/ 由用户掌控，LLM 只读"解释为"我 `cp` 进 raw/ 后立即 `rm`，读取发生在删除前所以等于只读"——**不算**：写入发生在第一步

**禁止**用"按字面 / 按精神"二选一措辞留退路

#### Red Flags（念头清单 — 出现即停）

念头出现 ≠ 已违反；念头 = 警告 = 重读「核心原则 / 边界 / 反模式」三段。
条目来源：标「实跑观察」者为 RED transcript 实录；未标注者为通用合理化模式（红旗是低成本预警网、广撒无害；实跑捕获新借口时追加并标注）

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

> 念头是**信号**不是违反；但**念头后仍继续** = 默认承担违反精神的责任

## 工作流

### 一次性 setup（首次使用）—— 由 workspace CLI 完成

> **职责边界**：本 skill 只管 wiki 的**成长阶段**（ingest / query / lint）；创建与删除归
> workspace CLI（`llmw`，与本 skill 同仓），"出生形态"由 CLI 包内模板决定
> （`llmw wiki check-fixtures` 探测）

**LLM agent 接管后做什么**：

1. 验证 CLI 落盘——读 `<wiki-root>/AGENTS.md` 确认主题名 + 日期替换正确；
   `wiki/index.md` / `wiki/log.md` 存在且 frontmatter 完整；`<wiki-root>/CLAUDE.md` 是薄壳
2. 跑 orient ritual（见「执行原则」顶部引用块）
3. 询问用户是否做首次 ingest——若是，把第一份资料路径给 agent

### Ingest（摄取新资料）

**触发**："把这篇摄取到 wiki" / `raw/` 有新文件 / 跑 `llmw wiki ingest-diff` 发现未摄取项

**流程摘要**（agent 驱动；详细 7 步 + 批处理见
[`ref/ingest-workflow.md`](ref/ingest-workflow.md)（执行前必读）；外部代码仓接入 /
漂移刷新 / 跨主机重建见 [`ref/external-repo.md`](ref/external-repo.md)（相应操作前必读））：

1. 跑 `llmw wiki ingest-diff`（日常加 `--check-stale`）找出未摄取 / 待重摄文件清单
2. 逐份走细节文件 7 步：对齐要点（单篇时）→ 写 source 页 → 同步 entity / concept →
   index / log / touch 簿记 →（启用 git 时）建议 commit

### 批处理摄取（≥ 3 份 raw 同时摄入）

走批处理路径而非逐份，5 步流程 + 理由 + log 标题前缀 `Bulk:` 的细节见
[`ref/ingest-workflow.md`](ref/ingest-workflow.md)「批处理」节

**外部代码仓作为语料**——"把 X 仓库纳入 wiki"：**不**内嵌拷仓，走 symlink 路径：
`llmw wiki external add <target> --name=<n> [--notes=...]`（symlink + anchor 一律经 CLI 落盘）；
随后 `llmw wiki ingest-diff` 扫描。漂移刷新 / 跨主机重建见
[`ref/external-repo.md`](ref/external-repo.md)

### Query（跨页综合）

**触发**："wiki 里有 X 吗" / "总结 wiki 中关于 Y 的内容" / "对比 A 和 B"

**流程骨架**：`index.md` 定位候选 → 只读相关页（不读 raw）→ 按 `reviewed` / `contested`
标采信等级 → 综合 → 符合条件时询问归档为 comparison / synthesis 页。详细 6 步 + 采信判定表 +
归档条件与脚手架见 [`ref/query-workflow.md`](ref/query-workflow.md)（执行前必读）

### Lint（健康检查）

**触发**："lint wiki" / 定期（频率阈值见 [`lint-workflow.md「lint 频率」`](ref/lint-workflow.md)）/ 大型 wiki 主动建议

**流程骨架**：`llmw wiki lint`（deterministic 层）→ agent 半定性检查 → 报告 + 询问用户先修
哪些。finding 口径（含义 / severity / 修法）=
`llmw wiki lint --explain=all`；半定性检查与频率见
[`ref/lint-workflow.md`](ref/lint-workflow.md)（执行前必读）；fixtures 一致性归
`llmw wiki check-fixtures`（常规 lint 只在 `--check-version` 时附带）

### Memory（写入 LLM agent 持久化记忆）

沉淀判断与治理（何时写 / 体检清理 / 删除确认）归 `yzr-memory-management` skill；wiki 侧只出
机械面：完整条目 `llmw wiki write memory add --slug=... --title=...` 建文件 + 索引行、再
Edit 正文；短条目直接往 `MEMORY/MEMORY.md` 挂一行索引。格式契约 canonical =
wiki 根 `AGENTS.md` 的 `MEMORY/` 节 + fixture `memory-index.txt` 头部说明块（自动加载）

### Upgrade（升级 wiki format）

**触发**：用户说"升级 wiki / 迁移 / 检查 wiki 版本 / 老格式 / format 升级 / 是否需要
reformat"；或 `llmw wiki lint` 报告 `wiki-format-version-stale` / legacy warn

**职责**：`llmw wiki upgrade` 修骨架、`lint --check-version --apply --json` 出升级 plan、
agent 按 plan 落内容页修复 + drift 裁定 + 语义合并。迁移期不走 `llmw wiki write`；**不**追加
log 条目。分工细节、5 步流程与裁定细则见
[`ref/upgrade-workflow.md`](ref/upgrade-workflow.md)（执行前必读）

## 参考样例

完整样例（ingest / query / lint / upgrade）见 [`ref/examples.md`](ref/examples.md)——按需 Read
