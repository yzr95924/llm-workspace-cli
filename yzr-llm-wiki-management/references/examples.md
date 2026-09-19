# 完整样例

> 本文件是参考样例的"按需 Read"指针——SKILL.md「参考样例」段仅留一行引用到此，
> 完整样例一律写在本文件。

## 样例一：ingest 一份原始资料

**用户指令**："raw/articles/ 里有一份 'distributed-systems-overview.md'，把它摄取到 wiki"

**执行**：

```text
1. llmw wiki ingest-diff 确认这是未摄取文件
2. Read raw/articles/distributed-systems-overview.md 全文
3. llmw wiki write new --type=source --slug=distributed-systems-overview --title="Distributed Systems Overview" --sources=raw/articles/...md --tags=distributed-systems,consensus
   → Edit 写正文：摘要 + 关键概念 + 主要权衡 + 与同类工作的关系
4. 检查 concepts/distributed-systems.md, concepts/consensus.md 是否已存在
   - 不存在：创建并把本次贡献写进
   - 存在：追加"参考来源"段
5. llmw wiki write index add wiki/sources/distributed-systems-overview.md
6. llmw wiki write log --op=ingest --title="Distributed Systems Overview"
7. 若启用 git，建议 commit；裸目录树 wiki 跳过此步
```

## 样例二：query 一个跨实体问题

**用户指令**："wiki 里 `<Concept A>` 和 `<Concept B>` 的对比是什么样的？"

**执行**：

```text
1. 读 wiki/index.md，找到 concepts/<concept-a>.md 和 concepts/<concept-b>.md
2. 读两个 concept 页
3. 综合答案，引用形式：
   "<Concept A> 强调 <特点 1>（来源 sources/<source-a>.md）；
   <Concept B> 强调 <特点 2>（来源 sources/<source-b>.md）..."
4. 询问用户："这段对比适合归档为 wiki/comparisons/<concept-a>-vs-<concept-b>.md 吗？"
5. 用户同意后：
   - `llmw wiki write new --type=comparison --slug=<concept-a>-vs-<concept-b> --title=...`
     脚手架 + 按 references/page-templates.md「comparison（对比页）」模板写正文
   - `llmw wiki write index add wiki/comparisons/<concept-a>-vs-<concept-b>.md`
   - `llmw wiki write log --op=query --title="<Concept A> vs <Concept B>"`
```

## 样例三：lint 发现腐烂迹象

**用户指令**："lint 一下这个 wiki"

**执行**：

```text
1. llmw wiki --path=~/wiki/llm-systems lint
2. CLI 报告：
   - raw/ 干净（启用 git 时 git status clean；未启用时此项自动跳过 + 输出顶部 `[NOTES]` 提示跳过原因）
   - 3 个页面缺 updated 字段
   - 1 个失效引用：concepts/transformer.md 链到 sources/bigtable.md 但后者不存在
   - 5 个 source 页 updated 超过 stale 阈值（阈值见 [`lint-checklist.md「过期摘要」`](lint-checklist.md)），建议复查
   - 1 个孤儿页：concepts/<orphan-concept>.md 没有任何 inbound link
   - 1 个 `contested-page`：sources/<entity-v2>.md 与 sources/<entity-v1>.md 对某核心属性
     说法冲突、已双向标注 `contested: true`——需与用户裁定后移除标记
   - 7 个 `pending-review`：默认未审核页面（新常态，info）
   - 1 个 `reviewed-stale`：sources/<reviewed-page>.md reviewed=true reviewed_at=2026-06-01 但
     updated=2026-06-25——LLM 修改后漏清 reviewed 戳，建议重新审核
3. agent 补充半定性观察：
   - sources/<entity-v2>.md 与 sources/<entity-v1>.md 对某核心属性的描述不一致
4. 整理成结构化报告，问用户先修哪些
```

## 样例四：检查 wiki 是否需要升级到最新 format

**用户指令**："我这个 wiki 是去年搭的，老格式了，能不能升级到最新 format"

**执行**：

```text
1. 跑操作前置：读 ~/wiki/llm-systems/AGENTS.md 末尾「当前配置」表的 `Wiki Format 版本` 行
   （老 wiki 会落后于当前版本）+ wiki/index.md + wiki/log.md
2. 跑升级 dry-run 看骨架计划：
    llmw wiki --path=~/wiki/llm-systems upgrade
    CLI 输出 plan（每个文件一个 action + diff 行数）
3. 若 plan 含 `render` / `gitignore-block` 的 diff → 触发 blocked_drift，与用户裁定本地定制：
   - AGENTS.md / CLAUDE.md 中多出模板渲染稿的行/段 = 用户本地定制
   - 逐条决定搬到 MEMORY/ 还是丢弃
   - 裁定完 → 重跑 `llmw wiki --path=... upgrade --apply --yes` 落地
4. 查内容页 legacy + 跑修复（lint 侧）：
    llmw wiki --path=~/wiki/llm-systems lint --check-version --apply --json
    → needs_upgrade: true；legacy 组（如有）：
          - N 处老格式 → agent 按 plan 自带规则（`agent_rules[]` + 各 action 说明）用 Edit 落
5. 验证：重跑 `llmw wiki --path=... upgrade` + `lint --check-version`
    → needs_upgrade: false ✓ 完成；upgrade 终态 done；无残留冲突
```
