# Lint 详细流程

Lint 让 wiki **不腐烂**，簿记自动化。分两层：

1. **Deterministic**（可程序化）：`llmw wiki lint` 执行，兜底带外手改（`llmw wiki write`
   正路的产物天然合规，见 wiki 根 `AGENTS.md` / SKILL 核心原则）
2. **Semi-qualitative**（需理解语义）：agent 执行，见 [章节](#半定性检查agent-执行)

## 调用方式

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint
llmw wiki --path="$LLM_WIKI_ROOT" lint --severity=error    # 严重性过滤
llmw wiki --path="$LLM_WIKI_ROOT" lint --explain=all       # finding 全清单（不跑检查）
```

退出码（常规）：0 = 干净；1 = 有问题；2 = 运行错误；未捕获异常 = 3。
`--check-version` 模式恒 0，是否需迁移看报告字段 `needs_upgrade`

finding 的含义 / severity / 修法是 CLI 注册表 SSOT，现场查：

```bash
llmw wiki lint --explain=all            # 全部
llmw wiki lint --explain=orphan-page    # 单条
```

### 子命令 `--check-version`

互斥模式：比对 `<wiki-root>/AGENTS.md` 末尾"当前配置"表的 `Wiki Format 版本` 与 CLI
常量 + 自动跑 fixtures 检查，不跑常规 lint；默认 dry-run，`--apply` 另把 upgrade plan
输出到 stdout（不落盘）：

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version --json
llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version --apply --json
```

agent 修复路径见 [章节](../SKILL.md#upgrade升级-wiki-format)；迁移依据 = plan 自带
`agent_rules[]` + [章节](upgrade-workflow.md#语义合并规则)

## 半定性检查（agent 执行）

跑完 deterministic 后 agent 再做以下检查（**仅 wiki < 200 页时人工做**，经验阈值）：

- **矛盾主张**（warning）：同一概念 / 实体在 ≥ 2 页被矛盾方式描述且**未标** `contested`
  （已标注的归 deterministic）；grep 概念关键词 + 读上下文，发现后建议双方补
  `contested: true` + `contradictions` 互指
- **缺失交叉引用**（info）：概念 X 出现在正文但没链到 `concepts/x.md`
- **缺失 entity / concept 页**（info）：重要概念（≥ 3 个 source 页出现）无独立页；
  grep 候选词统计出现次数
- **调查方向建议**（info）：热门主题（多 source 涉及）无综合 / 对比页 = 新合成机会
- **投放口堆积**（info）：`raw/articles/` 大量未摄取文件（跑 `llmw wiki ingest-diff` 即知），
  拖久会撑爆单次 ingest
- **漂移点引用**（info，不阻断）：正文引用上游可变且无机制可感知其变化的事实，按
  [章节](ingest-workflow.md#正文引用的稳定性漂移点规避) 逐类扫描，命中按该节改写规则修

## lint 之后

1. 整理报告（error > warn > info）
2. **询问用户先修哪些**：不要一次全修（易回退或引入新问题）
3. 修完**重新跑 lint 验证**，不带未验的 fix 前进；重跑同样按 wiki 根 `AGENTS.md`
   "写后必同步"记 log
4. 启用 git 时重大修复建议 `lint: <summary>` 前缀 commit；裸目录树 wiki 跳过
5. 若跑了 fixtures-check：骨架 vs 语义的分工见
   [章节](upgrade-workflow.md#职责切分关键三方分工)；anchor 类修复走 `llmw wiki external`
   命令，其余按 plan 的 `to_action` 字段 + schema 指针用 Edit 落

## lint 频率

- 小 wiki（< 50 页）每月 1 次；中（50-200）每 2 周；大（> 200）每周，可写 cron（经验建议阈值）
- 重大 ingest 后跑一次（可能引入新 entity / 断链）
- 跨 format 升级后首跑 fixtures-check，验证约定文件已切到新字节形态

## lint 的边界

- **不**自动修，只报告，修由用户 / agent 决定
- **不**评估内容质量（不是 fact-checker），只看结构和纪律；也**不**判 frontmatter
  语义合理性（只查字段存在 + 类型合法）
- **不**取代 schema：`AGENTS.md` 是源头，lint 是其 CLI 实现
