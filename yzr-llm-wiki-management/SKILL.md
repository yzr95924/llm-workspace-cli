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
  wiki、session 启停（单条 llmw 命令，直接跑即可）；跨 wiki / workspace 层操作（无专门
  skill，按用户指示处理）；MEMORY/ 的写入与治理（归 yzr-memory-management skill）；cwd 不是
  wiki 根（无 `wiki_metadata.toml` + AGENTS.md 骨架）
metadata:
  author: Zuoru YANG
  category: knowledge-base
  wiki_format_version: 0.43.8
---

# LLM Wiki Management

## 输入与输出

| 方向 | 内容 |
| --- | --- |
| 输入 | wiki 根（session cwd；否则 `$LLM_WIKI_ROOT` 或问用户） |
| 输出 | `wiki/` 内容页（entity / concept / source / comparison / synthesis）+ `wiki/log.md` / `wiki/index.md` / `wiki/tags.md` 条目 |

## 执行原则

### 核心原则

> **操作前置（orient ritual，所有操作通用）**：每次 ingest / query / lint 启动前，按以下
> 顺序读完四件套再动手：
>
> 1. **确认 `<wiki-root>/AGENTS.md` 已在上下文**——拿主题名与「当前配置」表
>    （`Wiki Format 版本` 行）；MEMORY 全文随其自动加载
> 2. `Read <$LLM_WIKI_ROOT>/wiki/index.md`——有哪些页、分布在哪些类别，避免重复创建 / 漏交叉引用
> 3. `Read <$LLM_WIKI_ROOT>/wiki/log.md`（最近 ~30 行）——看清最近活动，避免重复 ingest / 漏归档
> 4. **`scripts/SCRIPTS.md`**（已随 AGENTS.md 自动加载；wiki 可无 scripts/）——**要跑
>    `scripts/` 下自定义脚本前**（即操作不在 `llmw wiki` 命令与本文各工作流的覆盖面内）必须先查
>    其分节契约（使用场景 / 调用约定 / 前置依赖）
>
> 四件套任一未读完不写任何 wiki 内容。100+ 页的 wiki 还应在 `wiki/` 全域
> `Grep "<topic>"` 补一次——单看 index.md 可能漏掉 entity/concept 页之间的引用关系

1. **写操作正路 = `llmw wiki write` 系列**——log 追加走 `write log`、新建页走 `write new`、
   清 `reviewed` 戳走 `write touch`、MEMORY 新条目走 `write memory add`、index 条目走
   `write index add`；格式 + 滚动窗口截断由 `write` 保证，lint 只兜底带外手改。
   **逃生舱**：命令不支持的形态手写 Edit/Write 合法——write 是默认路径不是闸门

### 边界

- **不**绕过 `AGENTS.md` 自创约定——若 AGENTS.md 没说的，**先问用户**再写
- **不擅自建跨 wiki xref**——确有需要先报用户裁决

> 其余边界纪律以 wiki 根 `AGENTS.md` 为准（自动加载，会话常驻）；流程特有反模式见
> [章节](ref/external-repo.md#反模式)

### 反合理化三件套（纪律型 skill 必带）

> 纪律型禁令在 LLM 压力下会被合理化绕开——三件套只堵一类：**已被合理化的违反**

#### Rationalization Table

| 常见借口 | 为什么是错的 | 应改做什么 |
| --- | --- | --- |
| "剪藏只有一句话，按'克制建页'原则和你说的小事轻办，一个资料页够了"（实跑 transcript） | 用户的"随便 / 赶时间"是态度不是豁免——写 wiki 页即触发必填字段 / 建页阈值 / log 纪律；"轻办"是拿用户情绪当省略纪律的挡箭牌（同轮还静默漏了必填 `tags` 字段） | 流程不缩水；建页阈值判断如实执行（canonical 见 [章节](ref/page-templates.md#建页--追加--归档阈值page-thresholds)）但**向用户说明**（"本文只有一个中心主题，暂不建概念页，出现第二篇同主题再补"），字段与 log 纪律照走 |

> **收录纪律**：条目**只**从实跑 transcript 收录（预写借口 = 噪声），实跑出现新借口才补入——
> 3 次 RED baseline（带纪律 / 无纪律 / 带纪律 + 用户施压）仅产出下表 1 条真实借口 +
> 1 处静默遗漏（缺必填 `tags`）

#### 违反字面 = 违反精神

任何对「核心原则 / 边界」两段禁令的"看起来不同但效果一致"绕法都算违反——最常见的三种：

- 把 `llmw wiki write` 能做的写操作改用手写 `Edit` / `Write` 完成，再声称走了逃生舱——**不算**：
  逃生舱只覆盖命令不支持的形态，默认路径只有 `llmw wiki write` 系列
- 把"不删除 wiki 页"解释为"先把内容拷出去再 `rm` 然后写回"——**不算**绕开不删禁令，状态效果完全等同
- 把"raw/ 由用户掌控，LLM 只读"解释为"我 `cp` 进 raw/ 后立即 `rm`，读取发生在删除前所以等于只读"——**不算**：写入发生在第一步

**禁止**用"按字面 / 按精神"二选一措辞留退路

#### Red Flags（念头清单 — 出现即停）

念头出现 ≠ 已违反；念头 = 警告 = 重读「核心原则 / 边界」两段。
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

### Ingest（摄取新资料）

**触发**："把这篇摄取到 wiki" / `raw/` 有新文件 / 跑 `llmw wiki ingest-diff` 发现未摄取项

**流程预告**：识别 → 对齐要点 → source 页 → entity / concept 同步 → index / log 簿记 →
commit，全文见 [`ref/ingest-workflow.md`](ref/ingest-workflow.md)（执行前必读）；外部代码仓
接入 / 漂移刷新 / 跨主机重建见 [`ref/external-repo.md`](ref/external-repo.md)（相应操作前必读）

### 批处理摄取（≥ 3 份 raw 同时摄入）

走批处理路径而非逐份——理由与步骤见
[章节](ref/ingest-workflow.md#批处理摄取-3-份-raw-同时摄入)

**外部代码仓作为语料**——"把 X 仓库纳入 wiki"：**不**内嵌拷仓，走 symlink 路径：
`llmw wiki external add <target> --name=<n> [--notes=...]`（symlink + anchor 一律经 CLI 落盘）；
随后 `llmw wiki ingest-diff` 扫描。漂移刷新 / 跨主机重建见
[`ref/external-repo.md`](ref/external-repo.md)

### Query（跨页综合）

**触发**："wiki 里有 X 吗" / "总结 wiki 中关于 Y 的内容" / "对比 A 和 B"

**流程预告**：`index.md` 定位 → 只读相关页（不读 raw）→ `reviewed` / `contested` 采信分级
→ 综合 → 符合条件时询问归档，全文见 [`ref/query-workflow.md`](ref/query-workflow.md)（执行前必读）

### Lint（健康检查）

**触发**："lint wiki" / 定期（频率阈值见 [章节](ref/lint-workflow.md#lint-频率)）/ 大型 wiki 主动建议

**流程预告**：`llmw wiki lint`（deterministic）→ agent 半定性 → 报告 + 询问用户先修哪些，
全文见 [`ref/lint-workflow.md`](ref/lint-workflow.md)（执行前必读）；finding 口径（含义 /
severity / 修法）= `llmw wiki lint --explain=all`；fixtures 一致性归
`llmw wiki check-fixtures`（常规 lint 只在 `--check-version` 时附带）

### Upgrade（升级 wiki format）

**触发**：用户说"升级 wiki / 迁移 / 检查 wiki 版本 / 老格式 / format 升级 / 是否需要
reformat"；或 `llmw wiki lint` 报告 `wiki-format-version-stale` / legacy warn

**红线**：迁移期不走 `llmw wiki write`；**不**追加 log 条目。三方职责、流程与裁定细则见
[`ref/upgrade-workflow.md`](ref/upgrade-workflow.md)（执行前必读）

## 参考样例

完整样例（ingest / query / lint / upgrade）见 [`ref/examples.md`](ref/examples.md)——按需 Read
