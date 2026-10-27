# Lint 详细流程

Lint 检查 wiki 结构健康，分两层：机械层由 `llmw wiki lint` 执行；半定性层由 agent
在其上人工判断，见[章节](#半定性检查agent-执行)。

## 调用方式

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint
llmw wiki --path="$LLM_WIKI_ROOT" lint --explain=all    # finding 含义 / 修法查询
```

跑 lint 前先读 `AGENTS.md` 与 `wiki/index.md`。log 义务按 wiki 根 `AGENTS.md` 写后必
同步条（升级中的 `--check-version` 调用不记，见[章节](upgrade-workflow.md#边界)）。

遇 `wiki-format-version-stale` / `wiki-format-version-unparsed` 先跑
`llmw wiki lint --check-version` 取报告，再走[升级流程](upgrade-workflow.md)；遇
`wiki-format-version-ahead` 不升级，转告用户更新 llmw。

## 半定性检查（agent 执行）

机械层跑完后，仅在 wiki 少于 200 页时逐项人工做（经验阈值）；更大的 wiki 不靠人工兜底
语义矛盾与缺链，发现时按[章节](page-templates.md#矛盾处理)处理：

- **矛盾主张**：同一概念 / 实体在 2 页及以上的描述互相矛盾且未标 `contested`（已标注
  的归机械层）；grep 概念关键词并读上下文，发现后列入修复建议
- **缺失交叉引用**：概念 X 出现在正文但没有链到对应 `concepts/` 页
- **缺失 entity / concept 页**：达到建页阈值仍无独立页，阈值见
  [章节](page-templates.md#建页--追加--归档阈值page-thresholds)；用 grep 统计候选词
  出现在几个 source 页
- **调查方向建议**：多个 source 页涉及的热门主题还没有综合 / 对比页，可建议新建
- **待摄取堆积**：`raw/articles/` 有大量未摄取或已更新待重摄的文件（跑
  `llmw wiki ingest-diff --check-stale`，未摄取与 stale-raw 一并看），积压过多会让
  单次 ingest 负载过大
- **index 体积**：单类别或总条目超过 `wiki/index.md` 头部的规模建议值时，按该说明块
  处置
- **漂移点引用**：正文引用上游可变、且 wiki 机制感知不到变化的事实时，按
  [章节](page-templates.md#正文引用的稳定性漂移点规避) 逐类扫描，列入修复建议

## lint 之后

1. 询问用户先修哪些（报告按 error > warn > info 排）：一次修太多难回退，也容易引入
   新问题
2. 动手修前补读 `wiki/log.md`（近 30 行，确认近期动作；`AGENTS.md` 与
   `wiki/index.md` 已在调用方式节读过）
3. 修完重新跑 lint 验证，未通过复验的修复不交付
4. `llmw wiki lint --check-version` 报 fixtures 不合规时，职责分工与 plan 消费流程见
   [章节](upgrade-workflow.md#职责切分关键三方分工)

## lint 的边界

- lint 不自动修复，只报告，修由用户 / agent 决定
- lint 不核对事实、不评估内容质量，只看结构与纪律；检查清单以
  `llmw wiki lint --explain=all` 为准
- lint 不取代格式定义：格式以 wiki 根 `AGENTS.md`、内容页写作纪律文档与各文件头
  说明块为准
