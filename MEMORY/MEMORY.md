# MEMORY 索引

跨会话需要持久化的"为什么 + 边界"规则，正文与索引同级。

## 项目规则

- [设计文档组织](design-docs-organization.md) — 设计文档统一放 `doc/`，按子功能拆成多份 markdown（不是单篇长文）
- [记忆持久化策略](memory-persistence-policy.md) — 项目级记忆写仓库内 `MEMORY/`，跟随代码仓演进，不写个人 memory 目录
- [model 操作不走环境变量](model-ops-no-env-vars.md) — model 配置完全由 `workspace_models.toml` + `llmw model` 命令管理，wiki 用 ID 引用，**不依赖任何环境变量**
- [测试优先级低](test-priority-low.md) — 当前阶段不写自动化测试，先跑通 prototype + 设计复核，prototype 跑通后再补 test