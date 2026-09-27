# Lint 详细流程

Lint 让 wiki **不腐烂**。分两层：deterministic = `llmw wiki lint` 执行，semi-qualitative =
agent 执行，见 [章节](#半定性检查agent-执行)

## 调用方式

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint
llmw wiki --path="$LLM_WIKI_ROOT" lint --explain=all    # finding 含义 / 修法查询
```

遇到版本漂移 finding（`wiki-format-version-*`）→ `lint --check-version` 取报告，走
[章节](../SKILL.md#upgrade升级-wiki-format)

## 半定性检查（agent 执行）

跑完 deterministic 后 agent 再做以下检查，**仅 wiki < 200 页时人工做**（经验阈值）；> 200 页后语义矛盾 / 缺链无人工兜底，靠 ingest 时撞见走矛盾处置：

- **矛盾主张**（warning）：同一概念 / 实体在 ≥ 2 页的描述互相矛盾且**未标** `contested`
  （已标注的归 deterministic）；grep 概念关键词 + 读上下文，发现后列入修复建议，
  处置按 [章节](page-templates.md#矛盾处理-update-policy)
- **缺失交叉引用**（info）：概念 X 出现在正文但没链到 `concepts/x.md`
- **缺失 entity / concept 页**（info）：达到建页阈值（canonical 见
  [章节](page-templates.md#建页--追加--归档阈值page-thresholds)）仍无独立页；
  grep 候选词统计出现在几个 source 页
- **调查方向建议**（info）：热门主题（多 source 涉及）无综合 / 对比页 = 新合成机会
- **投放口堆积**（info）：`raw/articles/` 大量未摄取文件（跑 `llmw wiki ingest-diff` 即知），
  拖久会撑爆单次 ingest
- **index 体积**（info）：单类别 / 总条目超 `wiki/index.md` 头部"扩容护栏"时，
  按该说明块处置（拆段 / 建 topic-map）
- **漂移点引用**（info，不阻断）：正文引用上游可变且无机制可感知其变化的事实，按
  [章节](ingest-workflow.md#正文引用的稳定性漂移点规避) 逐类扫描，命中按该节改写规则修

## lint 之后

1. **询问用户先修哪些**（报告按 error > warn > info 排）：不要一次全修（易回退或引入新问题）
2. 修完**重新跑 lint 验证**，不带未验的 fix 前进；重跑同样按 wiki 根 `AGENTS.md`
   "写后必同步"记 log
3. 启用 git 时重大修复建议 `lint: <summary>` 前缀 commit；裸目录树 wiki 跳过
4. 若跑了 fixtures-check：职责切分与 plan 消费流程见
   [章节](upgrade-workflow.md#职责切分关键三方分工)

## lint 频率

- 小 wiki（< 50 页）每月 1 次；中（50-200）每 2 周；大（> 200）每周，可写 cron（经验阈值）
- 重大 ingest 后跑一次（可能引入新 entity / 断链）

## lint 的边界

- **不**自动修，只报告，修由用户 / agent 决定
- **不**评估内容质量（不是 fact-checker），只看结构和纪律；也**不**判 frontmatter
  语义合理性（只查字段存在 + 类型合法）
- **不**取代 schema：`AGENTS.md` 是源头，lint 是其 CLI 实现
