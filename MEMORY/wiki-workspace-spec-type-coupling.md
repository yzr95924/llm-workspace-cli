---
name: wiki-workspace-spec-type-coupling
description: wiki-spec 与 workspace-spec 的 frontmatter type enum 耦合——改 wiki-spec §9 type 时必须同步查 workspace-spec §13，否则"复用"引用悬空
metadata:
  type: project
---

`yzr-llm-workspace-management/references/workspace-spec.md` §13 的 type 表"复用 wiki-spec §9"
（index/log reserved + 5 类内容页 enum），形成跨 spec 耦合：改 wiki-spec 的 type enum
（增 / 删 / 改 reserved 类型）时，workspace-spec §13 及 §9 的"复用"引用会悬空。

**Why:** 2026-07-01 wiki-spec 0.6.0 删 `type: memory` reserved（`MEMORY/README.md` → 无
frontmatter 的 `MEMORY.md` 索引），连带让 workspace-spec §13（"3 类 wiki reserved 复用
wiki-spec §9"）/ §9.1（"复用 wiki-spec §5.1 的 type:memory reserved"）引用悬空——这是改
wiki 时漏查 workspace 的一致性 bug，workspace-spec 0.3.0 才补修。2026-08-18 两 skill 迁入
CLI 仓后同仓更应一并检查。

**How to apply:** 改 `yzr-llm-wiki-management/references/wiki-spec.md` §9 type enum 或 §5 MEMORY
结构时，立刻 grep `yzr-llm-workspace-management/references/workspace-spec.md` 里的
"复用 wiki-spec / wiki-spec §9 / wiki-spec §5"，确认引用仍有效；反之亦然（改 workspace-spec
type 时也查 wiki-spec 是否被反向依赖）。关联 [[wiki-spec-0-11-agents-md-ssot]]（两 spec 对称同步）。