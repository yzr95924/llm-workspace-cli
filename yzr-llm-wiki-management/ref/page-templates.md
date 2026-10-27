# 页面模板

内容页按 `type` 分 5 类，每类由共有 frontmatter 段、类型特定字段与自由正文组成。

本文件规定内容页的写作纪律：字段语义、建页阈值、认知质量信号、矛盾处理、图示指引。
页面字段与正文骨架不在 wiki 根 `AGENTS.md` 重复定义；lint 的校验口径以
`llmw wiki lint --explain=all` 为准，本文不镜像 severity 清单。

frontmatter 只支持三种写法：单行 `key: value`、inline 数组 `[a, b, c]`、`- item`
列表项。不要用多行折叠 `>` / `|`、YAML 锚点 `&` / `*`、嵌套 map：CLI 解析
frontmatter 时对这些形式静默丢弃或误解析且不报错；lint 走同一解析器，兜不住。

## 共有 frontmatter 段

- `title`：必填，人类可读标题，不带文件扩展名
- `description`：推荐，一句话摘要；非空时作为 `index.md` 条目摘要（建页用
  `--description` 传入）
- `type`：必填，取值 entity / concept / source / comparison / synthesis，决定
  子目录、index 分组与 lint 归类
- `tags`：必填（可空数组），取值必须在 `wiki/tags.md` 白名单内；白名单增删与取值
  规则见其头部说明块
- `created` / `updated`：必填，写入用 `YYYY-MM-DD HH:MM`
- `reviewed` / `reviewed_at` / `contested` / `contradictions`：可选，认知质量
  信号，见[章节](#可信度与认知质量信号)
- 类型特定字段（`sources` / `compared` / `threads` / `related` / `aliases` 等）：
  按类型见[章节](#各类型模板)

`index.md` / `log.md` / `tags.md` 是 reserved 文件：index 与 log 自带 frontmatter
（`type: index` / `type: log` 仅作标记），tags 不带 frontmatter；lint 不按普通内容页
校验这三个文件，另有专属检查。

### 可信度与认知质量信号

页面要区分审核与矛盾状态，否则未审内容日久会被当作既成事实引用。`reviewed` 系记录
人工审核，`contested` 系记录未裁定矛盾，两组独立、可叠加：

- `reviewed: true`：缺省为未审核；与 `reviewed_at: <YYYY-MM-DD>` 成对出现。lint 按
  日期比较 `updated` 与 `reviewed_at`，改正文与复审落在同一天不会触发
  `reviewed-stale`；复审落戳安排在最后一次正文改动之后
- `contested: true`：存在尚未裁定的矛盾主张，搭配 `contradictions` 指向对端
- `contradictions: [<路径>]`：与本页主张冲突的页数组，须双向标注（A 标 B，B 也标
  A）。路径按本页所在目录解析，与正文链接同基准（如 `[../sources/x.md]`），不得指向
  本页自身：lint 按文件路径存在性校验，自指不会被报出，须自查。注意 `related` /
  `compared` 按 `wiki/` 内容根解析，与 `contradictions` 基准不同

### 生命周期规则

`reviewed: true` 只代表审核时点的状态，不是永久标签：页面正文被再次修改（重摄取、
归档、手改）都使审核失效，删 `reviewed` 与 `reviewed_at` 回到未审核态；改正文后跑
`llmw wiki write touch <page>`。人工复审由用户完成：通读正文与交叉引用、
核对关键 raw 资料、确认主张成立后，才写 `reviewed: true` 加当天的 `reviewed_at`；
遇 `contested: true` 或 `contradictions` 非空，先裁定冲突再落戳。

### 矛盾处理

ingest 或 query 中发现新资料与已有页冲突时，不静默覆盖，按下列步骤：

1. 先看日期：更新的来源一般覆盖旧的；旧来源更权威时（如官方技术报告 vs 博客），
   两者都保留
2. 再判断是否真矛盾：版本差异（同一对象 v1 与 v2 属性不同）、上下文差异（不同评测
   条件）不算矛盾，正文注明即可
3. 确属矛盾时显式记录两种说法：正文写出 A 说 X（来源 + 日期）、B 说 Y（来源 + 日期），
   并列保留、不擅自取舍；给承载该主张的页面（通常 concept / entity 页）设
   `contested: true` 并用 `contradictions` 互指，纯转述的 source 页不打标
4. 下次 lint 会列出 `contested` 页；与用户一起裁定后移除 `contested`；裁定过程改了
   正文的，按生命周期规则重审

## 各类型模板

每类只列路径、类型特定字段与正文骨架。不适用的节可省略；写到的节沿用模板节名，可按
内容拆分；五个必填 frontmatter 字段由 `llmw wiki write new` 生成。

逐段溯源适用于 synthesis 与多源 comparison：frontmatter `sources` 只能列出引用了
哪些来源，定位不了某句主张出自哪篇。对来源可分的断言，用标准 Markdown 脚注
`[^n]`，文末 `[^n]: ...` 指向 source 页。不要用 pandoc 行内 `^[...]`：那是 pandoc
方言，GitHub 等标准渲染器不识别。纯推论无需脚注。

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

路径：`wiki/concepts/<slug>.md`；类型字段：`related: [<concepts/x.md>, ...]`（相关概念，按 `wiki/` 内容根相对）

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

`sources` 元素的指向限制：`raw/external/<symlink>/...` 可指向文件或目录（symlink
目标是 git 仓时可整仓作语料）；`raw/external/` 以外的 raw 路径仍要求指向文件。
目录源由 source 页整体覆盖：`ingest-diff` 不按子文件报待摄取，`write log --raw`
不接受目录。校验细则见 `llmw wiki lint --explain=external-target-dead` 等
external-* 条目。

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

路径：`wiki/comparisons/<slug>.md`；类型字段：`compared: [<concepts/a.md>, ...]`（必填，按 `wiki/` 内容根相对）

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
`sources: [<wiki 内页路径>]`（必填，不是 raw/）

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

### index（index.md）

路径 `wiki/index.md`。条目规则与规模建议见其头部说明块；维护用
`llmw wiki write index add|remove`。

### log.md（log）

路径 `wiki/log.md`。行格式、op 取值与滚动窗口截断见其头部说明块；维护用
`llmw wiki write log`。

## 模板使用规则

- **新建**：走 `llmw wiki write new`，正文按各类型骨架写
- **修改 / 重写**：改过正文按[章节](#生命周期规则)处理 `updated` / `reviewed` 戳；
  `type` / `sources` 等关键字段要变，先和用户确认；`title` / `description` /
  `type` 或页面路径变化后，按 wiki 根 `AGENTS.md` 写后必同步条同步 index 条目

### 建页 / 追加 / 归档阈值（Page Thresholds）

- **新建 entity / concept 页**：该 entity / concept 在 ≥ 2 个 source 页中被提到
  （经验阈值），或是某 source 页的中心主题
- **追加到已有页**：source 页提到已被覆盖的 entity / concept 时，往其 `参考来源`
  段追加条目，不重写
- **不创建页**：路过提及（脚注 / 一次出现的名字）、领域外细节、与本 wiki 主题无关的
  内容不建页
- **拆分页**：单页正文超过 lint `oversized-page` 阈值时，拆成子主题页 + 交叉链接
  （拆分建议随触发输出自带）
- **归档页**：内容被完全取代或主题域变化时，加 `archived: true` 并从 `index.md`
  移除；页文件保留，lint 与 `ingest-diff --check-stale` 不再按活跃页维护它

页面不物理删除：`rm` 会断 inbound 链接与 index 溯源，生命周期终点是归档页。

## 图示使用指引

以下为建议式规则，不强制：图用于压缩过程性 / 结构性内容，不是装饰。

- **优先配图**：交互流程 / pipeline / 状态机 / 组件-模块关系 / 层级结构；散文写
  2 至 3 句仍说不清时改用图
- **不配图**：静态定义、简单枚举、单点结论。一页一般不超过 2 图，超过时先考虑拆页，
  阈值见[章节](#建页--追加--归档阈值page-thresholds)
- **mermaid 为默认**（`flowchart` / `sequenceDiagram`）：中文标签可正常渲染，
  GitHub 网页与 md-to-html 均支持；源码保持可读：短标签、线性流、节点约 12 个以内，
  超过就拆图或退回文字
- **ASCII 图仅用于**目录树 / 纯英文短标签结构（围栏用 `text`）；中文标签不进 ASCII
  框：中英混排宽度不可控，对齐易错
- **表格仍是对比类内容首选**；LaTeX 公式照常。不用二进制图片：不可检索、不可 diff、
  不利移植
- **维护**：图是主张的一部分，改主张必同步改图；stale / `reviewed` 判定对图文
  一视同仁；关键结论在图外保留文字，页面不靠图也能读

## 正文引用的稳定性（漂移点规避）

正文或对话作答引用上游可变事实时，先判断：上游事实变了，wiki 的机制（lint / anchor /
stale 检查）能发现吗？发现不了的引用就是漂移点，按下列类别改写：

- **位置引用**（`foo.py:812`、PDF 第 34 页）：改引符号名 / 章节标题；git 仓引
  commit SHA
- **瞬态数值**（star 数、跑分）：记值并注明 `截至 YYYY-MM-DD`；或不录值，只引来源
- **版本绑定**（如 `最新版支持 X` 的说法）：写死起始版本（如 `v2.3 起`）；不单独
  使用 `最新 / 目前`
- **完整枚举**（全参数清单）：给代表性例子并注明完整清单见来源；清单留在来源侧，
  不复制进 wiki
- **归属信息**：维护者、负责人这类随人员变动的职责引角色不引人名；作者与历史署名
  照常记录

日期只标注上游事实的有效时点；本次核对、回查、修订不写进页面标题、节名或正文，
遇到既有这种写法不跟随复制。
