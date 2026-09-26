# MEMORY/

跨会话"为什么 + 边界规则"的索引；正文在同级 `<slug>.md`，按需 Read。
AGENTS.md 用单行 `@MEMORY/MEMORY.md` 引入本文件（host 自动展开则索引常驻上下文，
不展开的 agent 靠引用段内的 Read 指令注释兜底）。

## 规则

- 根级指令文件保持极简：2026-09-26 删 251 行旧 AGENTS.md 与全部 MEMORY/ 后重建紧凑版；扩写 AGENTS.md / 新增长记忆前先向用户提议
- 测试优先级低：手动 smoke + CI 冒烟为主，agent 不主动加测试代码（用户 2026-09-26 确认仍有效）
