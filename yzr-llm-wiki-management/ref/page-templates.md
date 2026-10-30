# 页面模板

内容页 `type` 取 `entity / concept / source / comparison / synthesis`。建页骨架走
`llmw wiki write new`；本文约束字段语义、正文节名、写作规则与页面生命周期。

## 字段

frontmatter 只支持单行 `key: value`、inline 数组 `[a, b]`、`- item` 列表。不用多行
折叠 `>` / `|`、YAML 锚点、嵌套 map：CLI 解析这些形式会静默丢弃或误解析，lint 走同一
解析器，兜不住。

- `title` / `type` / `created` / `updated` / `tags`：必填；由 `write new` 生成，日期用
  `YYYY-MM-DD HH:MM`
- `description`：推荐，一句话摘要；非空时进入 index 条目
- `reviewed` / `reviewed_at`：人工审核信号；改正文后审核失效，见
  [章节](#生命周期与归档)
- `contested` / `contradictions`：未裁定矛盾信号；字段语义见[章节](#矛盾处理)
- `related` / `compared`：按 `wiki/` 内容根解析（如 `concepts/a.md`）
- `contradictions`：按本页所在目录解析，与正文链接同基准

## 页面规格

固定节保留节名，可按内容拆分；按需节没有内容时省略；参考来源统一放在
`## 参考来源 / Sources`。

### entity（实体页）

- 路径：`wiki/entities/<slug>.md`
- 字段：`aliases` 可选
- 固定节：简述、关键属性、参考来源
- 按需节：已知变体

### concept（概念页）

- 路径：`wiki/concepts/<slug>.md`
- 字段：`related` 可选
- 固定节：定义、关键性质、变体、相关概念、参考来源
- 按需节：数学形式 / 形式化

### source（资料页）

- 路径：`wiki/sources/<slug>.md`
- 字段：`sources` 必填，指向 `raw/` 现存文件；`raw/external/<source-name>/` 可指目录；
  `authors` / `published` / `url` / `venue` 可选
- 固定节：摘要、关键贡献、与本 wiki 其它资料的关系、参考来源
- 按需节：关键数字 / 实验结果、引文

### comparison（对比页）

- 路径：`wiki/comparisons/<slug>.md`
- 字段：`compared` 必填，列出被对比的 wiki 页
- 固定节：对比对象、维度对比、适用场景、参考来源
- 按需节：其它能突出决策差异的材料

### synthesis（综合页）

- 路径：`wiki/syntheses/<slug>.md`
- 字段：`threads` 与 `sources` 必填；`sources` 只列 wiki 内页，不指 raw/ 或
  discussions/
- 固定节：主线、交叉与综合、观察 / 待研究、参考来源
- 按需节：按 `threads` 拆分的线索节

## 写作规则

- `type: source` 消化 raw 内容，不复制原文；正文给出摘要、关键贡献和与其他页的关系
- `type: synthesis` 与多源 comparison 逐段溯源：来源可分的断言用脚注 `[^n]` 指向
  source 页；不用 pandoc 行内脚注
- 图用于交互流程、结构关系或 3 句话仍说不清的过程；默认 mermaid，节点标签短小，
  超过约 12 个节点先拆图。静态定义、简单枚举和单点结论不配图
- 改主张必同步改图；关键结论在图外保留文字，页面不靠图也能读
- 引用可变上游时不锚易漂移位置：代码用符号名或 commit SHA，PDF 用章节标题，网页内容
  记值并写 `截至 YYYY-MM-DD`
- 瞬态数值记值加日期，或不录值只引来源；“最新版支持 X”写死起始版本
- 完整枚举不复制进 wiki，给代表性例子并指向来源

### 矛盾处理

发现新资料与既有页冲突时不静默覆盖：

1. 先判断是否真矛盾；版本差异、评测条件差异不算矛盾，正文注明差异即可
2. 版本演进按新旧版本记录；日期只识别版本演进，不裁决同一条件下的冲突
3. 真矛盾时并列写出双方主张、来源和日期；需取舍时交用户裁定。承载主张的页设
   `contested: true`，双方用 `contradictions` 互指；纯转述的 source 页不打标
4. 用户裁定后移除 `contested`；改过正文的生命周期同[章节](#生命周期与归档)

## 生命周期与归档

- 改 `type`、`sources`、页面路径等关键字段前先经用户确认；普通正文修改不走这条确认
- 改过正文就跑 `llmw wiki write touch <page>`；这会更新 `updated` 并清除过期的
  `reviewed` 信号
- 人工复审在最后一次正文修改之后：用户通读页面、核对关键 raw 与交叉引用后，才写
  `reviewed: true` 与当天 `reviewed_at`
- 新建 entity / concept 页：同一对象在 ≥ 2 个 source 页出现，或是某 source 页的中心
  主题；路过提及不建页
- 追加已有页：source 提到已覆盖对象时，只往参考来源段追加条目，不重写该页
- 单页超过 lint 的 oversized-page 提示时拆子主题页并交叉链接
- 内容被完全取代或离开本 wiki 主题时加 `archived: true` 并移出 index；文件保留，
  页面不物理删除
