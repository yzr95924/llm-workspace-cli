---
name: format-version-bump-single-repo
description: format 版本号 SSOT = llmw 包内常量；bump 仅当现有实例需要 reconcile（模板/fixture/schema 漂移），纯文档变化不 bump
metadata:
  type: project
---

# format 版本号 bump：包内常量 + CI gate（2026-08-20 起）

SSOT = `llmw/__init__.py` 的两条硬编码常量：`WIKI_FORMAT_VERSION` / `WORKSPACE_FORMAT_VERSION`。
两 SKILL.md frontmatter 的 `wiki_format_version` / `workspace_format_version` 必须与常量一致，
CI fixtures-smoke job（`scripts/test/smoke_fixtures.py` 的 `_check_format_version_alignment`）
机械比对——任何不一致即挂 job。

**Why:** 运行时读 SKILL.md frontmatter 会让 `import llmw` 依赖 L2 skill 目录存在（违反 [[boundary-map]] 包内资源内建原则——wheel 装完依旧残）。改为包内常量后 `import llmw` 零依赖 L2，wheel 完整。CI gate 把"同 commit 改多处"的纪律升级为机械 gate。

**何时 bump**：版本号 = 实例契约版本。bump 仅当**现有实例需要 reconcile**：

**应该 bump（实例需要 reconcile 的变化）：
1. byte-owned 模板字节变化（AGENTS.md / CLAUDE.md 模板）
2. header-owned fixture 头部字节变化（index / log / tags / MEMORY / SCRIPTS 头部说明块）
3. block-owned `.gitignore` managed 块规则变化
4. lint / legacy-scan 强制的内容 schema 变化（frontmatter 必填集 / type 枚举 / 命名约束 /
   anchor schema / log 格式）——注意内容页规则的 canonical 在 skill 的 page-templates.md
5. 新增会让旧实例 fail 的 check

**不应该 bump（实例无需任何动作）：
- skill 工作流 prose（ingest / query / upgrade 流程、examples.md）
- page-templates.md 的 rationale / 示例 / 措辞（不动字段契约时）
- format 结构 / 指针 / canonical 声明调整
- CLI 内部重构（不改渲染字节）/ README / MEMORY 条目

**判别式**：`llmw upgrade --apply` 会不会对现有实例产生超出版本行的 diff，或 lint
会不会对旧实例产生新的 error/warn？会 → bump；不会 → 不 bump。

**How to apply:** bump 流程——① 改 `llmw/__init__.py` 常量 + ② 改对应 `SKILL.md`
frontmatter 的 `*_format_version`（同 commit，顺序任意）；③ 演进叙事写进 commit message。
单仓 CI 的 fixtures-smoke 直接挂。patch/minor 选型：reconcile 必需但向后相容
（模板字节增行但字段集稳定）→ patch；实例出生形态变化或新增会让旧实例 fail 的 check
→ minor/breaking（迁移指令落 `references/upgrade-workflow.md` §六）。

关联 [[boundary-map]] 单向约束（包内资源内建原则）。
