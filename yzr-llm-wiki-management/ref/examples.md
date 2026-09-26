# 完整样例

四个流程各一条实跑 trace——只录「工作流文件里看不到的增量」：真实命令行的完整参数形态、
CLI 输出与报告的实际样子。步骤序列本身不重述，见各 workflow 文件

## 样例一：ingest 一份原始资料

**用户指令**："raw/articles/ 里有一份 'distributed-systems-overview.md'，把它摄取到 wiki"

命令序列（完整参数形态照此抄）：

```bash
llmw wiki ingest-diff                                  # 确认为未摄取文件
llmw wiki write new --type=source --slug=distributed-systems-overview \
  --title="Distributed Systems Overview" \
  --sources=raw/articles/distributed-systems-overview.md \
  --tags=distributed-systems,consensus                 # 脚手架落必填 frontmatter
# Edit 写正文：摘要 + 关键概念 + 主要权衡 + 与同类工作的关系
llmw wiki write index add wiki/sources/distributed-systems-overview.md
llmw wiki write log --op=ingest --title="Distributed Systems Overview" \
  --raw=raw/articles/distributed-systems-overview.md
```

entity / concept 同步：`concepts/distributed-systems.md`、`concepts/consensus.md` 不存在则
新建（贡献写进正文），已存在则只追加"参考来源"段

## 样例二：query 一个跨实体问题

**用户指令**："wiki 里 `<Concept A>` 和 `<Concept B>` 的对比是什么样的？"

答案形态（每条事实带来源，这就是可归档性的判据）：

```text
<Concept A> 强调 <特点 1>（来源：sources/<source-a>.md）；
<Concept B> 强调 <特点 2>（来源：sources/<source-b>.md）...
```

询问归档 → 用户同意后：

```bash
llmw wiki write new --type=comparison --slug=<concept-a>-vs-<concept-b> --title=...
# Edit 按 page-templates comparison 模板补 compared 字段与正文
llmw wiki write index add wiki/comparisons/<concept-a>-vs-<concept-b>.md
llmw wiki write log --op=query --title="<Concept A> vs <Concept B>"
```

## 样例三：lint 发现腐烂迹象

**用户指令**："lint 一下这个 wiki"——`llmw wiki --path=~/wiki/llm-systems lint`，CLI 输出的
真实形态（报告即按此整理给用户）：

```text
[SKIP] raw/ 干净检查自动跳过（未启用 git，[NOTES] 顶部提示原因）
[WARN] 3 个页面缺 updated 字段
[ERROR] 失效引用：concepts/transformer.md 链到 sources/bigtable.md 但后者不存在
[INFO] 5 个 source 页 updated 超过 stale 阈值（阈值随 finding 文本输出）
[ERROR] orphan-page：concepts/<orphan-concept>.md 未被 wiki/index.md 列出
[WARN] contested-page：sources/<entity-v2>.md 与 sources/<entity-v1>.md 对某核心属性
       说法冲突、已双向标注 contested: true——需与用户裁定后移除标记
[INFO] 7 个 pending-review：默认未审核页面
[WARN] reviewed-stale：sources/<reviewed-page>.md reviewed=true reviewed_at=2026-06-01
       但 updated=2026-06-25——LLM 修改后漏清 reviewed 戳，建议重新审核
```

随后 agent 补半定性观察：`concepts/<concept-x>.md` 与 `sources/<source-z>.md` 对某定义说法
不一致（上例已标 contested 的那对不重复报——半定性只抓未标注矛盾）→ 建议双方补
`contested: true` + `contradictions` 互指。整理成报告，问用户先修哪些

## 样例四：检查 wiki 是否需要升级到最新 format

**用户指令**："我这个 wiki 是去年搭的，老格式了，能不能升级到最新 format"

与 upgrade-workflow 5 步的对应只有一处增量——**终态出现的时机**：

- 第 2 步 dry-run 列出 `dropped_sections`（`--apply` 前唯一可见时机）
- 第 3 步裁定后 `upgrade --apply --yes` 的**这次运行**才产出骨架终态（`done` /
  `done_with_residue`）
- 第 4 步 `lint --check-version --apply --json` 产 `upgrade_plan`（`needs_upgrade: true` +
  legacy 组），agent 按 plan 自带 `agent_rules[]` 用 Edit 落
- 第 5 步重跑 2、4：plan 为空（骨架已对齐）且 `needs_upgrade: false` → 完成
