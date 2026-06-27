---
name: test-priority-low
description: 测试当前优先级低，先确保设计和 prototype 功能符合预期；prototype 跑通后再补 test
metadata:
  type: project
---

本项目（llmw wiki-workspace-cli）当前阶段**测试优先级低**：先确保设计与 prototype 功能符合预期，prototype 跑通后再补 test case 保护。

**Why:** 用户 2026-06-28 在 wiki workspace CLI 设计阶段明确：prototype 阶段以"快速验证设计"为核心目标；测试用例是事后保护层，不是设计阶段的拦路虎。过早写测试会拖慢设计反馈循环，过晚写测试则会让代码在 prototype 阶段漂移。

**How to apply:**

- **设计阶段 / prototype 阶段**：不写自动化测试；用手动 smoke 验证（每个命令至少跑一遍 happy path，记在 README）
- **prototype 跑通后**：开始补 test，按 `doc/design/07-testing.md` 的分层（单元 → 集成 → 端到端 → subprocess mock）
- 代码层面遵守可测性约束（业务与入口分离、Path 显式参数、subprocess 包装、异常类化），但**不**为"便于测试"而重构
- CI 矩阵 / coverage gate / pytest 配置等**不**在 prototype 阶段搭——prototype 验收靠人工
- 用户**没有明确要求补测试**前，agent 不要主动加测试代码

关联 [[model-ops-no-env-vars]] [[design-docs-organization]]。