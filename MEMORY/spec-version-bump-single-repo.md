---
name: spec-version-bump-single-repo
description: 两 SKILL（wiki/workspace）与 CLI 同仓后，spec 版本 bump 收敛为单仓操作，但 SKILL.md frontmatter / lint_wiki.py CURRENT_WIKI_SPEC / llmw/__init__.py 三处仍须同 commit 对齐
metadata:
  type: project
---

# spec 版本号 bump：单仓三方对齐（2026-08-18 迁移后形态）

2026-08-18 把 `yzr-llm-wiki-management` + `yzr-llm-workspace-management` 从 yzr-SKILL 迁入本仓（斩断历史），
submodule 删除。`*_spec_version` bump 从"my_SKILL ↔ CLI 跨仓原子操作"收敛为**单仓内三方对齐**：

1. 对应 `SKILL.md` frontmatter `*_spec_version`
2. `scripts/lint_wiki.py` `CURRENT_WIKI_SPEC`（`_assert_spec_version_sync` 在 import 时对照 frontmatter，失同步 warn）
3. `llmw/__init__.py` 的 `WORKSPACE_SPEC_VERSION` / `WIKI_SPEC_VERSION` 常量

**Why:** 迁移前的跨仓形态（submodule 指针 + pre-push hook + "同窗口 push"）是 2026-07-20 与
2026-08-17 两次版本漂移的根源——submodule 指针推进这个跨仓步骤屡被遗忘。单仓后漂移变成一次
commit 内可见、单仓 CI 可检的问题，被遗忘的步骤在物理上消失。

**How to apply:** bump 流程——① 改 `SKILL.md` frontmatter + `lint_wiki.py` + `llmw/__init__.py`
三处同 commit；② 演进叙事写进 commit message（spec 仓已无 changelog 文件）；③ 单仓 CI 的
fixtures-smoke 已取消对 `agents-version-is-current` 的免疫，漂移直接红。patch/minor 选型：
非破坏性（新 check 在现有产物 pass / prose 不改字节）→ patch；引入字节级出生形态变更 → minor/breaking。
breaking 的迁移指令必须落 `references/migrate-workflow.md` §六。

关联 [[wiki-workspace-spec-type-coupling]]（另一条跨 spec 耦合）。