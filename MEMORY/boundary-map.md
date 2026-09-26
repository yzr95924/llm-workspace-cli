---
name: boundary-map
description: 三方（用户 / CLI / wiki skill）依赖方向 + 生命周期 + 产物归属 + 新能力判归测试；新增归属决策 / 改 skill 文档 / 模板 / CLI 指令文本时先查
metadata:
  type: project
---

三方（用户 / CLI / 按 skill 纪律行事的 agent）的**关系边界** SSOT——回答"新能力放哪、为什么"。本图只承载**关系层**（边与判归），各方内部事实（模块职责 / schema / 工作流）以各自原位为准；本图里的任何行与本位事实冲突时，**本位事实优先**。

> **本图 vs 既有边界文档的分工**：本仓 AGENTS.md「顶层数据流」「模块边界表」「四分表」都是**事实层**（节点内部职责 / 文件字段）；本图是**关系层**（跨方协作的线）。重叠点在本图用"指针归本位"代替复制——改事实时只动本位，图不动。

> **跨 wiki / workspace 内容操作已退役（2026-09-26）**：workspace 仅为 wiki 的 git 仓容器（workspace.toml 注册表 + models / local toml + .gitignore），根级宪法（AGENTS.md / CLAUDE.md / MEMORY/）与 workspace skill 均已删除；跨 wiki 的 scan / INDEX / STATS / link / workspace lint 不在体系内，用户临时需要时逐项裁定，不预建机制。

## V1 三方定位

| 方 | mandate | 反 mandate（不做的事） |
| --- | --- | --- |
| **用户（owner）** | 拥有 `raw/` 内容、`<wiki>/AGENTS.md` / `CLAUDE.md`（宪法）、git、元数据 CRUD 决策 | 不执行字节级骨架渲染 |
| **llmw CLI** | 确定性操作唯一执行者（零 LLM 判断）：元数据 toml CRUD、骨架渲染（字节来自模板）、`llmw wiki check-fixtures` 探测、`llmw wiki upgrade` 引擎、session 启动（tmux/byobu）、model registry/overlay | 不写 `raw/` / `wiki/` 语义内容（机械 scribe 协作边除外，见 V2）；不读 `os.environ` 当 model 真相源 |
| **agent（按 wiki skill 纪律行事）** | 单 wiki 判断（零代码）：ingest、query、单 wiki lint；**在场时可代跑 llmw**（读类直接执行、写类经用户确认后执行、api_key 类恒用户亲自执行） | 不做跨 wiki 内容操作（场景已退役）；不写 `raw/`（用户所有）；不手写元数据 toml（写类操作必须经 CLI，schema / 原子写 / 唯一性约束由 CLI 保证） |

> **"skill"与"agent"的区分**——skill = 规则文本（被加载的 SKILL.md + ref/）；agent = 按这份规则行事的执行者。行为者永远是 agent；skill 只是哪份规则书。V2 行为者标注用 agent 而非 skill。

## V2 依赖方向 DAG

```
            ┌───── SKILL 仓（纯文本）─────┐          ┌─── llmw CLI 包（代码+资源自包含）
            │   wiki skill                │          │   llmw/content/templates/ 内建
            │   （单 wiki 世界；不知        │          │   全部模板+fixtures 字节金标准
            │    workspace 容器层存在）     │          │   （init / upgrade / check-fixtures /
            └─────▲─▲─────────────────────┘          │    scribe / session spawn / model）
                  │ │                                │
     agent ───────┘ └─────── 跑 ──────────────────────┘
     （按 skill          llmw wiki upgrade /
      纪律行事）          wiki check-fixtures

     agent ──提供字节──▶ CLI scribe【协作边】
                        （wiki_write / ingest_diff：
                         agent 决定字节，CLI 纯函数落盘）

     用户 ──跑──▶ llmw init / wiki add / remove / enter / config / model（元数据 CRUD）
     用户 ──改──▶ <wiki>/AGENTS.md / CLAUDE.md（宪法）
     用户 ──写──▶ <wiki>/raw/（原始资料）
     用户 ──建──▶ git 仓（CLI 不碰 git）
```

**单向约束（反向依赖全禁）**：

- **CLI 代码不读 skill 文件**——运行期资源全部内建 `llmw/content/templates/`（2026-08-20 收敛；format 版本号 SSOT = `llmw/__init__.py` 常量，SKILL.md frontmatter 由 CI gate 比对）
- skill 文本**不**读 CLI 代码（CLI 重构不能让 skill 失效）；格式契约指向 CLI 资产只用命令名
  （`llmw wiki check-fixtures`）不用包内路径。**反向同理**：CLI 输出的 agent 指令文本
  （`to_action` / `agent_rules` / `note` / `rule_ref` / `expected` / `actual`）不引包内实现
  ——只引命令名 / 输出自带字段 / 实例内可读路径（agent 读不到 = 不可执行指令）。
  两侧机械守护：gate 面 9（skill→CLI）+ 面 10（CLI→agent 文本）
- skill **不**解析 CLI 输出做元数据读取（直读 toml 更可靠；CLI 输出是人类的，文本可能改）
- **agent 代跑 llmw 的边界**——读 / 探测 / 升级类命令直接执行；写类（改 workspace / wiki 元数据、影响运行中 session）先给用户确认后再执行；**api_key 类命令始终由用户亲自执行**（secret 不过 agent）。不手写 toml——元数据写必须经 CLI（schema 校验 / 原子写 / 唯一性约束由 CLI 保证）。历史："让 CLI 写"曾被解读为"只告诉用户"（2026-08-21 前）；修订为"skill 在场时可代跑以闭环 UX，同时保留不手写 toml 的防线"

**唯一例外（协作边）**：agent 提供字节 → CLI 机械落盘（`wiki_write.py` / `ingest_diff.py`）。CLI 不审内容语义，只做 log 追加 / index 挂载 / frontmatter 校验等纯函数。字节来自 agent 即 I-1（"CLI 永不创作语义内容"）不违反。

## V3 生命周期

| 阶段 | 主导方 | CLI 角色 |
| --- | --- | --- |
| **init** | CLI | 建目录、写骨架（字节来自包内 `llmw/content/templates/` 模板 + fixtures） |
| **成长** | agent（wiki skill 下） | 仅按需被 agent 跑 `llmw wiki check-fixtures` 探测一致性 |
| **upgrade** | agent 跑 `llmw wiki upgrade` | CLI 引擎执行：每 wiki 骨架（4 类）；3 终态 JSON 输出；agent 解读并处理 `blocked_drift` |
| **delete** | CLI | 带备份删 |
| **元数据 CRUD** | 用户（agent 可代跑经确认的写类命令；api_key 类恒用户执行） | skill 建议 → 用户确认后代跑 / 用户直接跑 llmw；CLI 负责 schema 校验 + schema_version 自愈 |

版本号 SSOT = `llmw/__init__.py` 常量（SKILL.md frontmatter 与常量由 CI gate 比对，同 commit 改两处）。workspace.toml 的 `templates_version` 字段已随 workspace 骨架退役（load 对老文件残键静默忽略）。

## V4 产物归属（指针）

**本图不复制归属矩阵**——权威表在本位：

- 骨架所有权四分表 / 本仓模块边界：`AGENTS.md`（本仓）

图只承载**跨方写入原则**：CLI 绝不写 wiki 内容页 / `MEMORY/*.md` 经验条目（agent 领地）；CLI 绝不写 `raw/` / `wiki/` 语义内容（用户 + agent 领地）；skill 绝不写 `workspace.toml` / `.gitignore` / `AGENTS.md` / `CLAUDE.md`（前三 CLI / CLI 引擎升级；后两用户宪法）。

## V5 判归测试（6 步有序，新增能力按序问）

**0. 碰谁的领地？**（文件归属红线绝对，先于确定性判据）
要写/改的文件是 skill 领地 还是 user/CLI 领地？红线硬禁：CLI 绝不写 wiki 内容页 / MEMORY 经验条目 / raw 语义；skill 绝不写 workspace.toml/.gitignore/用户宪法。红线冲突则该设计不成立。

**1. 输出是输入的纯函数？**（零 LLM 判断）
字节级纯函数（骨架渲染、字节比对、重渲染、纯函数落盘、元数据 CRUD）→ **CLI**（`llmw.content` 包收口所有骨架操作）。

**2. 需要 LLM 判断 + 跨 wiki？**
场景已退役（见顶部声明）——默认**不接**；用户临时需要时逐项人工裁定，不预建机制 / 不进 skill / 不进 CLI。

**3. 需要 LLM 判断 + 单 wiki？**
单 wiki 的 ingest（摘要、冲突协调、页面综合）、query、lint → **wiki skill**。

MEMORY/ 条目的沉淀判断与治理 → `yzr-memory-management` skill（外部通用）；
skill 正文不承载记忆工作流——落盘机制自承载于实例：`MEMORY/MEMORY.md` 头部说明块
（fixture 声明 `write memory add`）；判归时不再走 2 / 3。

**4. 迁移/升级路径上的写操作？**
格式流动期（新旧形态并存时）的写操作 → **agent**（脚本只认识当前形态，硬编码 = 探测器要同时理解新旧）。格式稳定后进 CLI。

**5. 元数据变更？**
`workspace.toml` / `wiki_metadata.toml` / `workspace_models.toml` 结构变更 → **CLI**（skill 在场时 agent 经用户确认代跑；api_key 类恒用户亲自执行；agent 不手写 toml）。

### 历史实例（作为判据参照）

| 实例 | 判归 | 步骤 | 理由 |
| --- | --- | --- |---|
| `<wiki>/wiki/log.md` 的 `ingest-diff` 追加 | CLI scribe + agent | 协作边 | agent 出日志字节（diff 摘要），CLI 纯函数追加 + 时间戳规范化，I-1 不违反 |
| `<wiki>/wiki/syntheses/<slug>.md` 写入 | wiki skill | 步骤 3 | 单 wiki 综合答案，需判断综合内容 |
| `workspace_models.toml` 字段加 `is_default` | 用户跑 CLI | 步骤 5 | schema 变更，用户决策；CLI 校验唯一性约束 |
| `<wiki>/AGENTS.md` 改纪律 | 用户 | 宪法所有权 | 用户宪法；agent 改前必须与用户确认 |
