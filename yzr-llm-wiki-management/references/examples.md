# 5 个完整样例

> 本文件作为参考样例的"按需 Read"指针——SKILL.md §参考样例 段仅留一行引用到此。
> 来源：早期作为 `references/examples.md` 存在；2026-07-12 误并入 SKILL.md §参考样例
> （commit 36e0391），二次膨胀后回收独立文件 + SKILL.md 留一行指针。

## 样例一：setup 一个 LLM Systems 主题的 wiki

**用户指令**："我想搭一个 wiki 用来跟踪 LLM Systems 主题的研究资料"

**执行**：

```text
1. 告知用户：本 skill 不直接创建 wiki 仓；wiki 创建由 workspace CLI 负责
   → 推荐路径建议在 ~/wiki/llm-systems
2. 用户调 workspace CLI（具体命令以 CLI 文档为准）：
   workspace wiki init "LLM Systems" --root ~/wiki/llm-systems
   → CLI 按 wiki-spec.md 落盘目录 + AGENTS.md（SSOT）+ CLAUDE.md（薄壳）+ index.md + log.md + .gitignore
   → CLI 默认不建 git（用户 --git opt-in 时才 init + commit）
3. LLM agent 接管后：
   → 读 ~/wiki/llm-systems/AGENTS.md 确认主题名替换正确（CLAUDE.md 是薄壳，行数 ≤ 30）
   → 验证 wiki/index.md / wiki/log.md 存在且 frontmatter 完整
   → 提示用户：raw/articles/ 作为"资料投放口"，可放剪藏 / PDF / 笔记
4. 提示用户：wiki 根目录内的 AGENTS.md 经薄壳 CLAUDE.md 自动加载（经薄壳加载的 agent），
   或被原生读 AGENTS.md 的 agent 直读；别处工作时 skill 经 $LLM_WIKI_ROOT 按需读取，不必 symlink
```

## 样例二：ingest 一份原始资料

**用户指令**："raw/articles/ 里有一份 'distributed-systems-overview.md'，把它摄取到 wiki"

**执行**：

```text
1. ingest_diff.py 确认这是未摄取文件
2. Read raw/articles/distributed-systems-overview.md 全文
3. wiki_write.py new --type source --slug distributed-systems-overview --title "Distributed Systems Overview" --sources raw/articles/...md --tags distributed-systems,consensus
   → Edit 写正文：摘要 + 关键概念 + 主要权衡 + 与同类工作的关系
4. 检查 concepts/distributed-systems.md, concepts/consensus.md 是否已存在
   - 不存在：创建并把本次贡献写进
   - 存在：追加"参考来源"段
5. wiki_write.py index add wiki/sources/distributed-systems-overview.md
6. wiki_write.py log --op ingest --title "Distributed Systems Overview"
7. 若启用 git，建议 commit；裸目录树 wiki 跳过此步
```

## 样例三：query 一个跨实体问题

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
   - `wiki_write.py new --type comparison --slug <concept-a>-vs-<concept-b> --title ...`
     脚手架 + 按 references/page-templates.md §二 comparison 模板写正文
   - `wiki_write.py index add wiki/comparisons/<concept-a>-vs-<concept-b>.md`
   - `wiki_write.py log --op query --title "<Concept A> vs <Concept B>"`
```

## 样例四：lint 发现腐烂迹象

**用户指令**："lint 一下这个 wiki"

**执行**：

```text
1. python3 yzr-llm-wiki-management/scripts/lint_wiki.py ~/wiki/llm-systems
2. 脚本报告：
   - raw/ 干净（启用 git 时 git status clean；未启用时此项自动跳过 + 输出顶部
     `[NOTES] raw-immutable-skipped: 未启用 git（无 .git/）` 提示）
   - 3 个页面缺 updated 字段
   - 1 个失效引用：concepts/transformer.md 链到 sources/bigtable.md 但后者不存在
   - 5 个 source 页 updated 超过 stale 阈值（阈值见 [lint-checklist.md §二.7](lint-checklist.md#7-过期摘要)），建议复查
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

## 样例五：检查 wiki 是否需要升级到最新 spec

**用户指令**："我这个 wiki 是去年搭的，老格式了，能不能升级到最新 spec"

**执行**：

```text
1. 跑操作前置：Read ~/wiki/llm-systems/AGENTS.md (看到 §八 Wiki Spec 版本 = 0.5.0；老 wiki 版本在 CLAUDE.md §八) +
   wiki/index.md + wiki/log.md 最近 30 行
2. 跑探测：
   python3 yzr-llm-wiki-management/scripts/lint_wiki.py ~/wiki/llm-systems --check-version
   脚本报告：
     current_spec : 0.5.0
     skill_spec   : 0.7.0
     comparison   : older
     needs_migration: true
     [LEGACY] 共 12 处老格式现场（示意输出）
       - confidence-field (12) → migrate-workflow.md §6.1（依据 plan.actions[]）
           wiki/sources/<legacy-page>.md  [CONFLICT] ← 同时有 reviewed，需人工裁定
           wiki/sources/<another-legacy>.md
           ...
     [CONFLICTS] 1 处冲突页——agent 不自动覆盖
       - wiki/sources/<legacy-page>.md: 同时含 legacy confidence 字段与 reviewed 字段
     [HINT] 加 --apply 输出 migration plan（stdout JSON）供 agent 走 Edit/Write 修复
3. agent 把报告转成对话式清单 + 询问用户:
   "应用全部（除 1 处冲突转人工）/ 部分应用 / 仅看清单?"
   用户: "应用全部"
4. 生成 plan（stdout 输出，不落盘）：
   python3 yzr-llm-wiki-management/scripts/lint_wiki.py ~/wiki/llm-systems --check-version --apply --json
   → report.migration_plan 随 stdout JSON 返回（agent 内存持有，wiki 根无文件）
5. agent 从 stdout JSON 读 plan.actions[] 逐项 Edit/Write 修复:
   - 12 处 frontmatter-rename（其中 11 处直接改，1 处冲突跳过转人工）
   - 0 处其它（`type-memory-value` 已退役，老 wiki 中 `type: memory` 由 lint `invalid-type` 单独报）
6. Edit 改 ~/wiki/llm-systems/AGENTS.md §八 "Wiki Spec 版本" 0.5.0 → 0.7.0
7. 重跑 lint_wiki.py --check-version 验证:
     needs_migration: false ✓ 完成
     报告残留: wiki/sources/<legacy-page>.md [CONFLICT] 等待用户裁定
8. 告诉用户完成 + 1 处冲突转人工
```
