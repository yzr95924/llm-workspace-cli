---
name: boundary-map
description: CLI / workspace skill / wiki skill 三方（加用户四方）的依赖方向 + 生命周期 + 产物归属指针 + 新能力判归测试；新增归属决策时先查
metadata:
  type: project
---

三方（实际四方，含用户）的**关系边界** SSOT——回答"新能力放哪两方、为什么"。本图只承载**关系层**（边与判归），各方内部事实（模块职责 / schema / 工作流）以各自原位为准；本图里的任何行与本位事实冲突时，**本位事实优先**。

> **本图 vs 既有边界文档的分工**：本仓 AGENTS.md「顶层数据流」「模块边界表」「四分表节」、模板 `§一` 都是**事实层**（节点内部职责 / 文件字段）；本图是**关系层**（跨方协作的线）。重叠点在本图用"指针归本位"代替复制——改事实时只动本位，图不动。

## V1 四方定位

| 方 | mandate | 反 mandate（不做的事） |
| --- | --- | --- |
| **用户（owner）** | 拥有 `raw/` 内容、`AGENTS.md` / `CLAUDE.md`（宪法）、git、元数据 CRUD 决策 | 不执行字节级骨架渲染 |
| **llmw CLI** | 确定性操作唯一执行者（零 LLM 判断）：元数据 toml CRUD、骨架渲染（字节来自模板）、`check-fixtures` 探测、`upgrade` 引擎、session 启动（tmux/byobu）、model registry/overlay | 不写 `raw/` / `wiki/` 语义内容（机械 scribe 协作边除外，见 V2）；不读 `os.environ` 当 model 真相源 |
| **agent（按 workspace skill 纪律行事）** | 跨 wiki 判断（零代码）：scan / INDEX / STATS、query 路由/合成/对比、link、workspace lint、跨 wiki MEMORY | 不写 wiki 内部（委托 wiki skill）；不跑元数据 CRUD（只告诉用户） |
| **agent（按 wiki skill 纪律行事）** | 单 wiki 判断（零代码）：ingest、query、单 wiki lint、单 wiki MEMORY | 不知 workspace skill 存在（DAG 单向）；不写 `raw/`（用户所有） |

> **"skill"与"agent"的区分**——skill = 规则文本（被加载的 SKILL.md + references/）；agent = 按这份规则行事的执行者。行为者永远是 agent；skill 只是哪份规则书。V2 行为者标注用 agent 而非 skill。

## V2 依赖方向 DAG

```
            ┌───────── 两 skill 仓（纯文本）─────────┐       ┌─── llmw CLI 包（代码+资源自包含）
            │   workspace skill                     │       │   llmw/content/templates/ 内建
            │       │                               │       │   全部模板+fixtures 字节金标准
            │       │ 委托单 wiki 操作              │       │   （init / upgrade / check-fixtures /
            │       ▼                               │       │    scribe / session spawn / model）
            │   wiki skill                          │       │
            └─────▲─▲───────────────────────────────┘       │
                  │ │                                      │
     agent ───────┘ └─────── 跑 ─────────────────────────────┘
     （按 skill         llmw upgrade /
      纪律行事）         check-fixtures

     agent ──提供字节──▶ CLI scribe【协作边】
                         （wiki_write / ingest-diff：
                          agent 决定字节，CLI 纯函数落盘）

     用户 ──跑──▶ llmw init / add / remove / enter / config / model（元数据 CRUD）
     用户 ──改──▶ AGENTS.md / CLAUDE.md（宪法）
     用户 ──写──▶ <wiki>/raw/（原始资料）
     用户 ──建──▶ git 仓（CLI 不碰 git）
```

**单向约束（反向依赖全禁）**：

- **CLI 代码不读 skill 文件**——运行期资源全部内建 `llmw/content/templates/`（2026-08-20 收敛；spec 版本号 SSOT = `llmw/__init__.py` 常量，SKILL.md frontmatter 由 CI gate 比对）
- skill 文本**不**读 CLI 代码（CLI 重构不能让 skill 失效）；spec 指向 CLI 资产只用命令名（`llmw check-fixtures`）不用包内路径
- skill **不**解析 CLI 输出做元数据读取（直读 toml 更可靠；CLI 输出是人类的，文本可能改）
- wiki skill **不知** workspace skill 存在（workspace → wiki 是单委托；反向会破坏 DAG）
- agent（workspace skill）**不**执行元数据写——"让 CLI 写"的语义是"告诉用户跑 CLI"，人类决策

**唯一例外（协作边）**：agent 提供字节 → CLI 机械落盘（`wiki_write.py` / `ingest_diff.py`）。CLI 不审内容语义，只做 log 追加 / index 挂载 / frontmatter 校验等纯函数。字节来自 agent 即 I-1（"CLI 永不创作语义内容"）不违反。

## V3 生命周期

| 阶段 | 主导方 | CLI 角色 |
| --- | --- | --- |
| **init** | CLI | 建目录、写骨架（字节来自包内 `llmw/content/templates/` 模板 + fixtures） |
| **成长** | agent（两 skill 下） | 仅按需被 agent 跑 `check-fixtures` 探测一致性 |
| **upgrade** | agent 跑 `llmw upgrade` | CLI 引擎执行：workspace 骨架（4 类）+ 每 wiki 聚合；3 终态 JSON 输出；agent 解读并处理 `blocked_drift` |
| **delete** | CLI | 带备份删 |
| **元数据 CRUD** | 用户 | skill 建议 → 用户跑 `llmw wiki ...` 命令，人类执行（agent 不代行） |

`templates_version` 跨仓语义：workspace.toml 里的 `workspace_spec=X; wiki_spec=Y` 双分量，归 CLI 写（`upgrade` 时 bump）；版本号 SSOT = `llmw/__init__.py` 常量（SKILL.md frontmatter 与常量由 CI gate 比对，同 commit 改两处）。

## V4 产物归属（指针）

**本图不复制归属矩阵**——权威表在本位：

- workspace 根文件归属 + 骨架所有权四分表：`AGENTS.md`（本仓）「顶层数据流」+「四分表」
- 本仓模块边界 + 四分表：`AGENTS.md`

图只承载**跨方写入原则**：CLI 绝不写 INDEX / STATS / LINT / cross_queries / `MEMORY/*.md`（skill 领地）；CLI 绝不写 `raw/` / `wiki/` 语义内容（用户 + agent 领地）；skill 绝不写 `workspace.toml` / `.gitignore` / `AGENTS.md` / `CLAUDE.md`（前三 CLI / CLI 引擎升级；后两用户宪法）。

## V5 判归测试（6 步有序，新增能力按序问）

**0. 碰谁的领地？**（文件归属红线绝对，先于确定性判据）
要写/改的文件是 skill 领地 还是 user/CLI 领地？红线硬禁：CLI 绝不写 INDEX/STATS/LINT/cross_queries/cross_wiki_MEMORY/raw 语义；skill 绝不写 workspace.toml/.gitignore/用户宪法。红线冲突则该设计不成立。

**1. 输出是输入的纯函数？**（零 LLM 判断）
字节级纯函数（骨架渲染、字节比对、重渲染、纯函数落盘、元数据 CRUD）→ **CLI**（`llmw.content` 包收口所有骨架操作）。

**2. 需要 LLM 判断 + 跨 wiki？**
跨 wiki 的 scan 聚合、路由/合成/对比、link 建议、workspace lint、跨 wiki MEMORY → **workspace skill**。

**3. 需要 LLM 判断 + 单 wiki？**
单 wiki 的 ingest（摘要、冲突协调、页面综合）、query、lint、单 wiki MEMORY → **wiki skill**。

**4. 迁移/升级路径上的写操作？**
格式流动期（新旧形态并存时）的写操作 → **agent**（脚本只认识当前形态，硬编码 = 探测器要同时理解新旧）。格式稳定后进 CLI。

**5. 元数据变更？**
`workspace.toml` / `wiki_metadata.toml` / `workspace_models.toml` 结构变更 → **用户跑 CLI**（agent 只建议、不代行；CLI 负责 schema 校验 + schema_version 自愈）。

### 历史实例（作为判据参照）

| 实例 | 判归 | 步骤 | 理由 |
| --- | --- | --- |---|
| `upgrade_workspace.py`（workspace 骨架升级） | CLI | 步骤 1 | render + 字节比对 + 重渲染 = 纯函数；CLI 引擎镜像 wiki 侧 `upgrade.py` |
| `<workspace>/cross_queries/<slug>.md` 写入 | workspace skill | 步骤 3 | 跨 wiki 合成答案归档，需判断"是否值得归档""跨几 wiki" |
| `<wiki>/wiki/log.md` 的 `ingest-diff` 追加 | CLI scribe + agent | 协作边 | agent 出日志字节（diff 摘要），CLI 纯函数追加 + 时间戳规范化，I-1 不违反 |
| `<wiki>/wiki/syntheses/<slug>.md` 写入 | wiki skill | 步骤 3 | 单 wiki 综合答案，需判断综合内容 |
| `workspace_models.toml` 字段加 `is_default` | 用户跑 CLI | 步骤 5 | schema 变更，用户决策；CLI 校验唯一性约束 |
| `<workspace>/AGENTS.md` 改纪律 | 用户 | 宪法所有权 | 用户宪法；agent 改前必须与用户确认 |
