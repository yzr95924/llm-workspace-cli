---
name: model-ops-no-env-vars
description: model 相关的所有操作不依赖环境变量；model 配置完全由 workspace_models.toml + llmw model 命令管理，wiki 元数据用 ID 引用
metadata:
  type: project
---

本仓库 wiki-workspace-cli 涉及 model 的所有操作（配置 / 解析 / 传递给 Claude Code）**完全不能依赖环境变量**——既不从 `os.environ` 读取，也不向 Claude Code 注入 `ANTHROPIC_MODEL` 等 env。

**Why:** 环境变量是进程级的、易被外部覆盖、且用户 shell 环境不可控；model 配置应该由 CLI 100% 掌控，确保审计可追、跨环境一致。这是用户 2026-06-28 在 wiki workspace CLI 设计阶段确立的硬约束。

**How to apply:**

- **Phase 2**：`workspace_models.toml` 是 model 的唯一真相源；`llmw model` 系列命令管理该文件；wiki_metadata.toml 用 model id 字段引用
- **Phase 1**：model 字段（`workspace.default_model` 与 `wiki.model`）保留为元数据/审计字段，**不主动传递给 Claude Code**——Claude Code 用自己的默认 model
- 不在任何代码路径中读取 `os.environ.get("ANTHROPIC_MODEL")` 或类似 pattern
- 不在 subprocess 启动 claude 时注入 model 相关 env
- 若将来需要把 model 通知给 Claude Code，走配置文件（如 `.claude/settings.json`），不走 env

关联 [[memory-persistence-policy]] [[design-docs-organization]]。