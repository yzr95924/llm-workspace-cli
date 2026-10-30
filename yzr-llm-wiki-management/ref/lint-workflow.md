# Lint workflow

Lint 不自动修复，只报告，修由用户 / agent 决定；机械检查走 `llmw wiki lint`，事实与
内容质量不在范围内。

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint
llmw wiki --path="$LLM_WIKI_ROOT" lint --explain=all
```

## 流程

1. 读 wiki 根 `AGENTS.md` 与 `wiki/index.md`，跑 lint
2. 遇 `wiki-format-version-stale` / `wiki-format-version-unparsed` 时跑
   `llmw wiki lint --check-version` 并走[章节](upgrade-workflow.md#流程)；
   `wiki-format-version-ahead` 不升级，告知用户更新 llmw
3. wiki 少于 200 页时补语义巡检，更大 wiki 只在发现线索时处理：
   - 同一对象多处描述矛盾且未标 `contested`，按
     [章节](page-templates.md#矛盾处理)处理
   - 正文提到已有概念但缺交叉引用，或对象达到建页阈值仍无独立页，阈值见
     [章节](page-templates.md#生命周期与归档)
   - 多个 source 页的热门主题还没有 comparison / synthesis，可建议建页
   - 引用上游可变事实时按[章节](page-templates.md#写作规则)查漂移点
4. 报告按 error > warn > info 排列；问用户先修哪些，确认后补读 `wiki/log.md` 近 30 行
   再动手
5. 修完重跑 lint，未通过复验不交付；按 wiki 根 `AGENTS.md` 的写后同步条记
   `llmw wiki write log --op=lint --title="<巡检摘要>"`。`--check-version` 的 fixtures
   修复走[章节](upgrade-workflow.md#流程)
