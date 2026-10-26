# 页面模板

**5 类内容页**按 `type` 分，共有 frontmatter 段 + 类型特定字段 + 自由正文

本文件是内容页写作纪律的以…为准文本（字段语义、建页阈值、认知质量信号、
矛盾处理、图示指引；wiki 根 `AGENTS.md` 模板不承载写页规则）；lint 校验规则以
`llmw wiki lint --explain=all` 为准，不在此镜像

**frontmatter 写法约束**（约束对象 = 内容页）：仅支持单行 `key: value`、inline 数组
`[a, b, c]`、`- item` 列表项三种形式。**不要**用多行折叠 `>` / `|`、YAML 锚点
`&` / `*`、嵌套 map：CLI 解析 frontmatter 时**静默丢弃或误解析**这些形式且不报错；
lint 走同一解析器，兜不住

## 共有 frontmatter 段

- `title`：必填，人类可读标题，不带文件扩展名
- `description`：推荐，一句话摘要；`index.md` 条目摘要的唯一来源
- `type`：必填，取值 entity / concept / source / comparison / synthesis，驱动
  子目录 + index 分组 + lint
- `tags`：必填（可空数组），取值必须严格在 `wiki/tags.md` 白名单内；白名单增删与
  取值规则见其头部说明块
- `created` / `updated`：必填，写入用 `YYYY-MM-DD HH:MM`
- `reviewed` / `reviewed_at` / `contested` / `contradictions`：可选，认知质量
  信号，见「可信度与认知质量信号」节
- 类型特定字段（`sources` / `compared` / `threads` / `related` / `aliases` 等）：
  按类型见「各类型模板」节

`index.md` / `log.md` / `tags.md` 是 **reserved 文件**（index / log 自带 frontmatter，
`type: index` / `type: log` 仅作标记；tags 不带 frontmatter），lint 跳过

### 可信度与认知质量信号

LLM 写的页不标注，时间一长会被当成既成事实。`reviewed` 系 = 人工审核背书；
`contested` 系 = 矛盾未裁定告警；两组正交，可叠加

- `reviewed: true`：缺省 = 未审核；与 `reviewed_at: <YYYY-MM-DD>` 成对出现。
  lint 对 `reviewed_at` 与 `updated` 按字符串比较，同日复审会因 `updated` 带
  时刻而触发 `reviewed-stale`——复审落戳安排在最后一次正文改动之后
- `contested: true`：存在**尚未裁定**的矛盾主张，搭配 `contradictions` 指向对端
- `contradictions: [<路径>]`：与本页主张冲突的页数组，**双向标注**（A 标 B，
  B 也标 A）。路径按**本页所在目录**解析，与正文链接同基准（如
  `[../sources/x.md]`），**不**得指向本页自身——lint 按文件路径存在性校验，
  自指不会被报出，须自查。注意 `related` / `compared` 按 `wiki/` 内容根解析，
  与 `contradictions` 基准不同

### 生命周期规则

`reviewed: true` 是审核时点的背书快照，不是永久标签：LLM 对页面正文的任何修改
（重摄取、归档、手改）都让戳失效，删 `reviewed` + `reviewed_at` 回到未审核态，
正路 `llmw wiki write touch <page>`。落戳是人的主动作：读完正文 + 交叉引用 +
关键 raw 资料、确认主张站得住，才写 `reviewed: true` + `reviewed_at: <今天>`；
遇 `contested: true` 或 `contradictions` 非空，先裁定冲突再落戳

### 矛盾处理

ingest 或 query 中发现"新资料与已有页冲突"，**不**静默覆盖：

1. **先看日期**：更新的来源一般覆盖旧的；若旧来源更权威（如官方技术报告 vs
   博客），保留两者并进入第 2 步
2. **判定是否真矛盾**：版本差异（同一对象 v1 vs v2 的某属性）、上下文差异
   （不同评测条件）不算矛盾，加注明即可；确属矛盾进入第 3 步
3. **显式记录两种说法**：正文写出 A 说 X（来源 + 日期）、B 说 Y（来源 + 日期），
   不"和稀泥"挑一个；给承载该主张的页面（通常 concept / entity 页）
   设 `contested: true` + `contradictions` 互指，纯转述的 source 页不打标
4. **等 lint 复审**：下次 lint 会把 `contested` 页拎出来；与用户一起裁定后移除
   `contested`；裁定过程改了正文的，按生命周期规则重审

## 各类型模板

每类只列**路径 + 类型特定字段 + 正文骨架**（不适用的节可省略；写到的节沿用模板
节名，可按内容拆分；5 个必填 frontmatter 字段由 `llmw wiki write new` 生成）

### entity（实体页）

路径：`wiki/entities/<slug>.md`；类型字段：`aliases: [<别名>]`（可选，自由文本）

```markdown
# <Title>

## 简述

<一段话：本 entity 是谁/什么，附 primary source 链接>

## 关键属性

- <客观属性 bullet>

## 已知变体

- <变体（版本 / 型号 / 形态）>

## 参考来源 / Sources

* [<source page>](<relative-path>) — <说明>
```

### concept（概念页）

路径：`wiki/concepts/<slug>.md`；类型字段：`related: [<concepts/x.md>, ...]`（相关概念，wiki 根相对）

```markdown
# <Title>

## 定义

<形式化定义 + primary source>

## 数学形式 / 形式化

<若适用：LaTeX / mermaid / 表格>

## 关键性质

- <区别于相邻概念的关键属性>

## 变体

- <变体>（来源：[<source>](<path>)）

## 相关概念

- [<concept>](<path>) — <关系说明>

## 参考来源 / Sources

* [<source page>](<relative-path>) — <说明>
```

### source（资料页）

路径：`wiki/sources/<slug>.md`；类型字段：`sources`（必填，raw/ 现存路径）、
`authors` / `published` / `url` / `venue`（可选）

`sources` 元素指向文件或目录的限制：`raw/external/<symlink>/...` 可指向**文件或
目录**（symlink 目标是 git 仓目录时可整仓作语料）；普通 raw 路径（非
`raw/external/`）仍要求指向**文件**。lint 只校验可访问性，细则见
`llmw wiki lint --explain=external-target-dead` 等 external-* 条目

```markdown
# <Title>

**作者**：<authors>
**来源**：[<raw path>](../../raw/<...>)

## 摘要

<一段话（建议 200-500 字）：核心主张 + 在本 wiki 主题域里的位置>

## 关键贡献

1. <贡献>

## 关键数字 / 实验结果

- <关键数据 / 性能 / 复杂度>

## 与本 wiki 其它资料的关系

- 启发了 [<other source>](<path>)
- 核心概念见 [<concept>](../concepts/<slug>.md)

## 引文（可独立成段）

> "<原文 quote>" —— <出处>
```

### comparison（对比页）

路径：`wiki/comparisons/<slug>.md`；类型字段：`compared: [<concepts/a.md>, ...]`（必填，wiki 根相对）

```markdown
# <Title>

## 对比对象

- [<A>](../concepts/<a>.md) — <路线 1 一句话>
- [<B>](../concepts/<b>.md) — <路线 2 一句话>

## 维度对比

| 维度 | <A> | <B> |
| --- | --- | --- |
| <维度> | <A 属性> | <B 属性> |

## 适用场景

- <场景> → <选 A / B / 视情况>

## 参考来源 / Sources

* [<source page>](<relative-path>)
```

### synthesis（综合页）

路径：`wiki/syntheses/<slug>.md`；类型字段：`threads: [<线索标题>]`（必填）、
`sources: [<wiki 内页路径>]`（必填，**不是 raw/**）

```markdown
# <Title>

## 主线

<要回答的核心问题 + 多线索概览>

## 线索一：<thread 1>

- <要点>（来源：[<source>](<path>)）

## 交叉与综合

- <跨线索的连接 / 共性>

## 观察 / 待研究

1. <观察 / 待研究问题>

## 参考来源 / Sources

* 列在 frontmatter `sources` 字段
```

**逐段溯源（synthesis / 多源 comparison 专属）**：frontmatter `sources` 只能定位
"引了哪些来源"，追溯不了"某句主张来自哪篇"。对**来源可分的断言**用标准 Markdown
脚注 `[^n]`（文末 `[^n]: ...` 指向 source 页；**不要**用 pandoc 行内 `^[...]`，
那是 pandoc 方言，GitHub 等标准渲染器不识别）；纯推论无需脚注

### index（index.md）

路径：`wiki/index.md`（**唯一一份**，`type: index` reserved）。条目纪律与扩容护栏
见其头部说明块；正路走 `llmw wiki write index add|remove`

### log.md（log）

路径：`wiki/log.md`（**唯一一份**，`type: log` reserved）。每行格式 / op 取值 /
滚动窗口截断见其头部说明块；正路走 `llmw wiki write log`

## 模板使用规则

1. **新建**：走 `llmw wiki write new`；正文按上节骨架写
2. **修改 / 重写**：改过正文按[章节](#生命周期规则)处理 `updated` / `reviewed` 戳；
   `type` / `sources` 等关键字段要变，**先和用户确认**；`title` / `description` /
   `type` 变更后 `llmw wiki write index add <page>` 同步条目，页面换路径另
   `llmw wiki write index remove <旧路径>`

### 建页 / 追加 / 归档阈值（Page Thresholds）

**宁可错过一个 entity 也不堆十个空页**：空页让 lint 报告被噪声淹没

- **新建 entity / concept 页**：该 entity / concept 在 ≥ 2 个 source 页中被提到
  （经验阈值），或是某 source 页的中心主题
- **追加到已有页**：source 页提到一个已被覆盖的 entity / concept，追加
  「参考来源」段即可，不重写
- **不创建页**：路过提及（脚注 / 一次出现的名字）、领域外的细节、与本 wiki
  主题无关
- **拆分页**：单页正文超过 lint `oversized-page` 阈值（拆分建议随触发输出自带），
  拆成子主题 + 交叉链接
- **归档页**：内容被完全取代或主题域变化，加 `archived: true`、从 `index.md` 移除；
  页文件保留，lint 与 `ingest-diff --check-stale` 不再按活跃页维护它

**页不物理删除**（`rm` 会断 inbound 链接与 index 溯源），生命周期终点是「归档页」

## 图示使用指引

建议式规则，不强制：图是过程性 / 结构性内容的压缩，不是装饰；密度优先

- **优先配图**：交互流程 / pipeline / 状态机 / 组件-模块关系 / 层级结构；散文写
  这类内容超过 2-3 句仍绕不清时，换一张图
- **不配图**：静态定义、简单枚举、单点结论；一页一般 ≤ 2 图，超了先自问是否该
  拆页，阈值见[章节](#建页--追加--归档阈值page-thresholds)
- **mermaid 为默认**（`flowchart` / `sequenceDiagram`）：中文标签无碍，GitHub 网页 /
  md-to-html 均可渲染；**源码本身保持可读**：短标签、线性流、节点 ≤ ~12，超了就
  拆图或退回文字
- **ASCII 图仅限**目录树 / 纯英文短标签结构（围栏用 `text`），**禁止中文标签进
  ASCII 框**：中英混排显示宽度数不准，对齐必崩
- **表格仍是对比类内容首选**；LaTeX 公式照旧；**不用二进制图片**——检索 / diff /
  可移植性三损，wiki 的文本性是一等约束
- **维护**：图是主张的一部分，改主张必同步改图（stale / `reviewed` 判定对图与
  文字一视同仁）；**关键结论在图外保留文字**——图里的信息对靠 grep 检索的
  agent 等于不存在

## 正文引用的稳定性（漂移点规避）

正文或对话作答引用上游可变事实时，先过一遍机械判定：上游事实变了，wiki 有任何
机制（lint / anchor / stale 检查）能发现吗？发现不了的引用就是漂移点，按下列
类别改写

- **位置引用**（`foo.py:812`、PDF 第 34 页）：引符号名 / 章节标题；git 仓引
  commit SHA
- **瞬态数值**（"star 数 1.2w"、跑分）：值 + "截至 YYYY-MM-DD"；或只引来源不录值
- **版本绑定**（"最新版支持 X"）：写死版本号（"v2.3 起"）；禁裸"最新 / 目前"
- **完整枚举**（全参数清单）：代表性例子 + "完整清单见来源"；清单属来源不属 wiki
- **归属信息**（“由张三维护”）：引角色不引人名

日期只标上游事实的有效时点；本次核对 / 回查 / 修订不写进页面标题、节名或正文，
既有这种写法不跟随复制
