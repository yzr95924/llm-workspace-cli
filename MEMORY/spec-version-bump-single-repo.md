---
name: spec-version-bump-single-repo
description: spec 版本号 SSOT = llmw 包内常量（llmw/__init__.py），SKILL.md frontmatter 由 CI gate 比对
metadata:
  type: project
---

# spec 版本号 bump：包内常量 + CI gate（2026-08-20 起）

SSOT = `llmw/__init__.py` 的两条硬编码常量：`WIKI_SPEC_VERSION` / `WORKSPACE_SPEC_VERSION`。
两 SKILL.md frontmatter 的 `wiki_spec_version` / `workspace_spec_version` 必须与常量一致，
CI fixtures-smoke job（`scripts/test/smoke_fixtures.py` 的 `_check_spec_version_alignment`）
机械比对——任何不一致即挂 job。

**Why:** 2026-08-20 把 spec 版本从运行时读 SKILL.md frontmatter 改为包内常量（公理 2 / 3：
代码绝不读 L2 skill 目录；跨层一致性由 gate 而非运行时读文件守护）。之前 `import llmw` 依赖
skill 目录存在——wheel 装完依旧残——是 [[boundary-map]] 三层划界原则的违规点。改为常量后
`import llmw` 零依赖 L2，wheel 完整。CI gate 把"同 commit 改多处"的纪律升级为机械 gate。

**How to apply:** bump 流程——① 改 `llmw/__init__.py` 常量 + ② 改对应 `SKILL.md` frontmatter
的 `*_spec_version`（同 commit，顺序任意）；③ 演进叙事写进 commit message。
单仓 CI 的 fixtures-smoke 直接挂。patch/minor 选型：
非破坏性（新 check 在现有产物 pass / prose 不改字节）→ patch；引入字节级出生形态变更 → minor/breaking。
breaking 的迁移指令必须落 `references/upgrade-workflow.md` §六。

历史形态：
- 2026-08-18：三处副本（SKILL.md frontmatter + lint_wiki.py CURRENT_WIKI_SPEC + llmw/__init__.py）同仓同 commit
- 2026-08-20 前：`llmw.config.skill_spec_version()` 运行时读 SKILL.md，常量消失
- 2026-08-20 起：回到硬编码常量 + CI gate（当前形态）

关联 [[wiki-workspace-spec-type-coupling]]（另一条跨 spec 耦合）、[[boundary-map]] 公理 2/3（包内资源内建原则）。
