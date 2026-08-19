---
name: spec-version-bump-single-repo
description: 两 SKILL（wiki/workspace）与 CLI 同仓后，spec 版本 bump 收敛为单仓操作，SSOT = SKILL.md frontmatter 一处
metadata:
  type: project
---

# spec 版本号 bump：单仓单一真源（2026-08-18 迁移后形态）

2026-08-18 把 `yzr-llm-wiki-management` + `yzr-llm-workspace-management` 从 yzr-SKILL 迁入本仓（斩断历史），
submodule 删除。`*_spec_version` bump 从"my_SKILL ↔ CLI 跨仓原子操作"收敛为单仓操作；
2026-08-19 进一步单一化——**SSOT 只有 `SKILL.md` frontmatter 的 `*_spec_version` 一处**：

1. `scripts/lint_wiki.py` 的 `CURRENT_WIKI_SPEC` 在模块加载时**直接读** SKILL.md frontmatter（`_load_current_spec()`），
   不再维护常量副本
2. `llmw/__init__.py` 的 `WORKSPACE_SPEC_VERSION` / `WIKI_SPEC_VERSION` 经 `llmw.config.skill_spec_version()`
   读同仓 SKILL.md frontmatter（lru_cache），不再硬编码

**Why:** 迁移前的跨仓形态（submodule 指针 + pre-push hook + "同窗口 push"）是 2026-07-20 与
2026-08-17 两次版本漂移的根源——submodule 指针推进这个跨仓步骤屡被遗忘。单仓后漂移变成一次
commit 内可见、单仓 CI 可检的问题；三处手写副本的同 commit 纪律进一步收敛为"只改一处"，
被遗忘的步骤在物理上消失。

**How to apply:** bump 流程——① 只改对应 `SKILL.md` frontmatter 的 `*_spec_version` 一处；
② 演进叙事写进 commit message（spec 仓已无 changelog 文件）；③ 单仓 CI 的 fixtures-smoke
已取消对 `agents-version-is-current` 的免疫，漂移直接红。patch/minor 选型：
非破坏性（新 check 在现有产物 pass / prose 不改字节）→ patch；引入字节级出生形态变更 → minor/breaking。
breaking 的迁移指令必须落 `references/upgrade-workflow.md` §六。

关联 [[wiki-workspace-spec-type-coupling]]（另一条跨 spec 耦合）。