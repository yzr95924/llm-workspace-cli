# Lint 详细流程

Lint 查 wiki 结构健康。分两层：机械层 = `llmw wiki lint` 执行；半定性层 = agent
在其上人工判断，见[章节](#半定性检查agent-执行)

## 调用方式

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint
llmw wiki --path="$LLM_WIKI_ROOT" lint --explain=all    # finding 含义 / 修法查询
```

跑 lint 前先读 `AGENTS.md` + `wiki/index.md`；要定修复优先级时再补读 `wiki/log.md`。
log 义务按 wiki 根 `AGENTS.md` 写后必同步条（升级中的 `--check-version` 调用不记，见
[章节](upgrade-workflow.md#边界)）。

遇版本漂移 finding（`wiki-format-version-*`）→ `llmw wiki lint --check-version`
取报告，走[升级流程](upgrade-workflow.md)

## 半定性检查（agent 执行）

机械层跑完后，**仅 wiki < 200 页时逐项人工做**（经验阈值）；更大的 wiki 语义
矛盾 / 缺链不靠人工兜底，撞见了走[章节](page-templates.md#矛盾处理)：

- **矛盾主张**：同一概念 / 实体在 ≥ 2 页的描述互相矛盾且**未标** `contested`
  （已标注的归机械层）；grep 概念关键词 + 读上下文，发现后列入修复建议
- **缺失交叉引用**：概念 X 出现在正文但没链到对应 `concepts/` 页
- **缺失 entity / concept 页**：达到建页阈值仍无独立页，阈值见
  [章节](page-templates.md#建页--追加--归档阈值page-thresholds)；
  用 grep 统计候选词出现在几个 source 页
- **调查方向建议**：热门主题（多 source 涉及）还没有综合 / 对比页 = 新合成机会
- **待摄取堆积**：`raw/articles/` 有大量未摄取或已更新待重摄的文件（跑
  `llmw wiki ingest-diff --check-stale`，未摄取与 stale-raw 一并看），拖久会
  撑爆单次 ingest
- **index 体积**：单类别 / 总条目超过 `wiki/index.md` 头部"扩容护栏"建议值时，
  按该说明块处置
- **漂移点引用**：正文引用上游可变、且 wiki 机制感知不到变化的事实，按
  [章节](page-templates.md#正文引用的稳定性漂移点规避) 逐类扫描改写

## lint 之后

1. **询问用户先修哪些**（报告按 error > warn > info 排）：不要一次全修，易回退
   或引入新问题
2. **动手修前补读** `wiki/log.md`（`AGENTS.md` 与
   `wiki/index.md` 已在调用方式节读过）
3. 修完**重新跑 lint 验证**，不带未验证的 fix 前进
4. `llmw wiki lint --check-version` 报 fixtures 不合规 → 职责切分与 plan 消费
   流程见[章节](upgrade-workflow.md#职责切分关键三方分工)

## lint 的边界

- **不**自动修，只报告，修由用户 / agent 决定
- **不**评估内容质量（不核对事实），只看结构和纪律；也**不**判 frontmatter
  语义合理性（只查字段存在 + 类型合法）
- **不**取代 schema：wiki 根 `AGENTS.md` 是源头，lint 是其 CLI 实现
