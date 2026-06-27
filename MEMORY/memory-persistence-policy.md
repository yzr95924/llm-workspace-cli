---
name: memory-persistence-policy
description: 本项目相关记忆持久化到仓库内 MEMORY/ 目录，跟随代码仓演进；不写进 Claude 个人记忆目录
metadata:
  type: project
---

本项目（`llm_workspace_cli`）涉及到的"开发约定、设计风格、为什么这么设计、跨会话需要遵守的边界"等记忆，**持久化到仓库内 `MEMORY/` 目录**，**跟随代码仓演进**（提交、版本控制、可被同事看到）。

**Why:** 项目级记忆如果散落在 Claude 个人记忆目录（`~/.claude/projects/.../memory/`），无法随代码仓一同被协作方看见，也无法随代码历史回溯；丢失上下文=丢失设计意图。把记忆作为代码仓的一部分，让"为什么"和"代码"同步演化。

**How to apply:**

- 涉及本项目的开发约定 / 设计风格 / 子功能边界 / 持久化约束时，**写入 `MEMORY/`**（不是个人 memory 目录）
- 每条记忆一个独立 markdown 文件，frontmatter 含 `name` / `description` / `type`（project / feedback / reference / user）
- 在 `MEMORY/MEMORY.md` 索引里加一行指针（一句话 + 文件名 + 用途）；不放正文
- 同一事实已存在记忆文件 → 编辑更新，不创建重复
- 用户偏好 / 个人风格（如"我喜欢中文交流"）仍可放个人 memory 目录——项目内不放个人偏好
- 跟代码本身能查到的（命名约定、目录结构、git 历史）不写记忆——记忆只放"代码查不到的为什么"

关联 [[design-docs-organization]]。