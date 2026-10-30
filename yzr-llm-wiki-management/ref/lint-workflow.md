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
   `llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version` 并走
   [章节](upgrade-workflow.md#流程)；
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
5. 修复分支：用户选定的项修完重跑 `llmw wiki --path="$LLM_WIKI_ROOT" lint`，确认
   selected 项消失即通过（不要求全 zero；info 级 pending-review / tag-not-in-taxonomy
   是常态提示）。报告或修复均按 wiki 根 `AGENTS.md` 的写后同步条记
   `llmw wiki --path="$LLM_WIKI_ROOT" write log --op=lint --title="<巡检摘要>"`
6. report-only 分支（用户要求只报告）：报告后直接记 log（无 finding 也记），不修改
   任何内容页 / index / tags
7. `--check-version` 的 fixtures 修复走[章节](upgrade-workflow.md#流程）

## 完成口径

- error 级：选定的修复项必须消失，或有用户明确接受残留的记录
- warn 级：修或列为待办；不阻断交付
- info 级：常态提示，不要求清零
- 进程退出码 1 表示有 finding，不等同于本次巡检失败
