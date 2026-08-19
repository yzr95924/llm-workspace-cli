# 骨架统一引擎设计文档（skeleton-engine）

> 元信息（评审流转的跟踪字段，全部必填；无评审人写"待定"）：
>
> | 状态 | 作者 | 评审人 | 创建日期 | 更新日期 | 关联需求 / 链接 |
> | --- | --- | --- | --- | --- | --- |
> | 草稿 | yzr95924 | 待定 | 2026-08-19 | 2026-08-19 | 责任重划计划（Task 3-5） |
>
> **评审决策记录**（评审后回填）：
>
> - 撤版本下限护栏：无远古版本，`blocked_too_old` 终态删除，终态集 3 个
> - `blocked_drift` 语义：dry-run 输出 diff，不写盘，需人工将自定义搬 MEMORY 后重跑
> - `--list-rules` 生成稿内嵌 `lint-checklist.md` §二，CI 新鲜度断言保 SSOT
>
> **章节分层**：§1–5 **需求层**（不依赖实现）→ §6–10 **方案层**（怎么做）→ §11–14 **落地层**。
> 本文档覆盖 Task 3（render 统一 + checker 派生化）、Task 4（upgrade 引擎）、Task 5（纪律层）；
> Task 1（脚本搬移 + 命令面）已完成、Task 6（固化）不在本文档方案范围内。

## 1. 背景与现状

### 1.1 现状（Task 1 完成后）

确定性脚本已全量迁入 `llmw/content/`，命令面为 `llmw wiki lint / check-fixtures /
ingest-diff / write` + `llmw check-fixtures`；skill 目录零代码（CI 断言守护）。
但**一致性仍靠"查"维持**，不靠"构造"：

| 现状耦合点 | 位置 | 形态 |
| --- | --- | --- |
| 模板 ↔ checker 提取正则 | `wiki_fixtures._extract_agents_row` × 4（`AGENTS_TOPIC_ROW_RE` 等）+ 自拼渲染 | checker 从 wiki 文件**反提取**变量再渲染比对；模板变量换位置 → checker 代码要改 |
| 模板 ↔ 渲染 mapping | `init_wiki.render_and_write` 硬编码变量集合 | 加模板变量需改 mapping；fail-fast assert 兜底但仍是双点 |
| fixtures ↔ 骨架描述符 | `wiki_fixtures.SKELETON_SPECS` 硬编码 6 文件骨架信号 | 改 fixture 需手工同步描述符（docstring 原话）；唯 `.gitignore` 走 fixture 自动跟随（先例） |
| 规则代码 ↔ lint-checklist 散文 | `wiki_lint` 各 check 函数 + `references/lint-checklist.md` | 规则 id/severity/why 两份，改规则改两处 |
| wiki-spec §9 type ↔ workspace-spec §13 | 两 spec 各自陈述 type 分类 | 改动须双向同步（MEMORY 条目 [[wiki-workspace-spec-type-coupling]]） |
| 版本钉 | `SKILL.md` frontmatter 单点（已单源） | —（已解决） |
| 渲染逻辑副本 | `init_wiki`、checker 提取+拼渲染、`test_*._render_agents_md` 迷你渲染器 | 同一"渲染 AGENTS.md"事实三份实现 |

### 1.2 痛点

1. **"升级"仍是 agent 概率执行**：`llmw wiki lint --check-version --apply` 输出 plan JSON，
   agent 按 migrate-workflow.md 逐条手改（机械修复也在走 LLM 概率执行）。
2. **改模板/fixture 会触发多处手工同步**：模板措辞改动可能连带 checker 提取正则、测试
   迷你渲染器、SKELETON_SPECS——每处都是人肉对账点。
3. **检查器自身是维护负担**：checker 存在的理由是"防漂移"，但 checker 自身也要维护
   （描述符、提取正则、count 钉）。

### 1.3 假设清单（评审确认）

- A1：**存量 wiki 全为近世代**（wiki spec ≥ 0.11 / workspace spec ≥ 0.7），远古版本不存在
  → 引擎无需版本下限护栏，终态集不含 `blocked_too_old`。
- A2：**骨架文件所有权收紧可接受**——agent 禁改骨架，自定义纪律沉淀去 `MEMORY/`（用户已拍板）。
- A3：**未来 spec bump 的 content-growth 格式变更（如 log 条目格式）极罕见**——历史上 36 个
  版本未发生（log_format.py 是稳定 SSOT）。

## 2. 目标与非目标

### 目标（可验证）

| # | 目标 | 判定方法 |
| --- | --- | --- |
| G1 | 改模板/夹具**结构上无事可改 CLI 侧** | 改 `agents-md-template.md` 措辞后，checker/测试/upgrade 全绿（fixtures-smoke + pytest） |
| G2 | 升级主体由 CLI 确定性执行 | `llmw wiki upgrade` 对近世代 wiki 跑通：0 error 自验证 + 无残留时 exit 0 |
| G3 | agent 只处理判断残留 | upgrade 输出 3 终态 JSON，agent 只 switch 分支，不解读 plan 手改机械项 |
| G4 | 检查器从"查"变"构造" | checker 无 SKELETON_SPECS / 无 4 条提取正则 / 无 count 钉；fixtures-smoke 仍全绿 |
| G5 | 每个事实单一真源 | 渲染=render.py 一处；规则 what=代码一处；type=wiki-spec 一处 |

### 非目标

- **不**做 STATS.md / LINT.md 生成器（workspace skill 的 agent 内联工作流，另行任务）。
- **不**做内容页 frontmatter 变换的自动化（type-memory-value 等语义类 → upgrade 残留，agent 处理）。
- **不**回写远古版本迁移代码（无远古版本，引擎无需处理）。
- **不**删除 migrate-workflow.md（Task 5 缩减并改名 upgrade-workflow.md，保留 agent fallback 路径）。

## 3. 功能点拆解

| # | 功能点 | 优先级 | 设计落点 |
| --- | --- | --- | --- |
| FP1 | render.py 单一渲染入口（wiki AGENTS/CLAUDE/index/log + workspace AGENTS/CLAUDE） | P0 | §7.2 |
| FP2 | 变量 SSOT 从"文件"改为"metadata toml + 版本常量" | P0 | §7.2 |
| FP3 | checker 从 fixture 字节解析 oracle（删 SKELETON_SPECS + 4 提取正则） | P0 | §7.3 |
| FP4 | 测试改调生产 render（删迷你渲染器） | P0 | §7.3 |
| FP5 | upgrade 引擎：resync（渲染 + growth 按段嫁接 + 缺失创建） | P0 | §7.4 |
| FP6 | upgrade 两护栏：drift 预警 --yes（预检 diff 非空时拒绝静默覆盖）/ 空 transform 插槽（未来 growth 格式变更的扩展位） | P0 | §7.4 / §8 |
| FP7 | legacy 路径表（声明式数据，路径存在性触发） | P1 | §7.5 |
| FP8 | 3 终态 JSON 输出契约 + 自验证闭环 | P0 | §7.6 |
| FP9 | 规则 metadata 入代码 + `--list-rules` 生成 checklist + CI 新鲜度断言 | P1 | §7.7 |
| FP10 | type taxonomy 单源化（wiki-spec 拥有，workspace-spec 引用） | P1 | §7.8 |
| FP11 | 纪律层：模板禁改段 + spec 所有权四分表 | P1 | §7.9 |
| FP12 | spec 复述审计（先报告后改写） | P2 | §13 开放问题 Q4 |

## 4. 功能规格与约束

### 4.1 渲染（FP1/FP2）

- **变量来源 SSOT**：渲染输入变量全部来自 `wiki_metadata.toml`（`name`/`topic`/`created_at`）、
  `workspace.toml`（`display_name`）或 `llmw/__init__.py` 版本常量（`WIKI_SPEC_VERSION` /
  `WORKSPACE_SPEC_VERSION` / `__version__`）。**不从旧文件反提取**。
- **占位符语法**：`{{KEY}}`；渲染后 assert 无残留（沿用 init_wiki `_substitute` 语义）。
- **消费方**：`wiki add`（init_wiki）、upgrade/resync、`wiki_fixtures.agents-md-template-sync`
  （render-compare）、测试。五个消费方调同一 `render_*()`。

### 4.2 fixture 派生 oracle（FP3）

- **oracle 数据源** = `references/fixtures/*.txt` 字节 + 现有占位符 + 约定的 growth 边界。
- **growth 边界约定**（写入 fixtures/README.md，唯一新契约）：
  - `_（暂无内容）_` 行 = 该段 growth 为空占位（index.md 的 `##` 段）；
  - HTML 注释行 = 条目格式说明（tags.md / memory-index.txt 已有），解析时跳过；
  - `## 索引` 段（memory-index.txt）之后 = growth。
- **checker 解析逻辑**：frontmatter 键（`---` 间解析）、H1、说明块（`>` 行）、`##` 段头、
  growth 边界——全部从 fixture 字节导出，**无独立描述符文件、无硬编码信号**。

### 4.3 upgrade（FP5-FP8）

- **命令**：`llmw wiki upgrade [--path=DIR | --name=NAME] [--dry-run] [--yes] [--json]`；
  `llmw upgrade [--dry-run] [--yes] [--json]`（workspace 级）。
- **drift 预警**：dry-run 用 render-compare 输出将被覆盖的骨架 diff；apply 前必须 `--yes`，
  输出提示"自定义内容先搬 MEMORY/"（仅当 diff 非空）。
- **3 终态 JSON 契约**（`--json` 恒可用，agent 判定依据）：

  ```json
  {
    "status": "done | done_with_residue | blocked_drift",
    "current_spec": "0.36.0", "target_spec": "0.36.0",
    "changed": [{"file": "AGENTS.md", "action": "render"}],
    "residue": [{"type": "content-page-transform", "note": "..."}],
    "verified": {"error": 0, "warn": 0, "pass": 21, "skip": 0}
  }
  ```

  - `done`：全部骨架重渲染 + 自验证 0 error + 无残留。
  - `done_with_residue`：骨架完成，残留清单需 agent。
  - `blocked_drift`：pre-constraint 自定义将被覆盖，dry-run 输出 diff 停住，需先人工裁决
    （搬 MEMORY）后重跑（重跑时 diff 已空 → 正常走）。
- **自验证**：apply 后内联重跑 fixtures checker，0 error 才算 `done`/`done_with_residue`；
  失败 → 报错 exit 2，不改版本钉。
- **版本钉写回**：AGENTS.md §八 版本行（经重渲染自动）、`wiki_metadata.toml` 的
  `templates_version` 或等效字段、workspace.toml `templates_version`。

### 4.4 规则清单生成（FP9）

- 规则事实（id / severity / rule_ref / desc / 修复指引）在代码 CHECK_REGISTRY（wiki 侧
  `wiki_fixtures`）与 check 函数 docstring/常量（wiki_lint 侧）——**单一真源在代码**。
- `llmw wiki lint --list-rules` 输出 markdown 清单（含 CHECK_REGISTRY + lint 规则）。
- `references/lint-checklist.md` 缩减为：使用说明 + 半定性检查（§三）+ 修复指引（§五）的
  **散文 why**；机械清单部分由生成器产出，CI 断言"生成稿与已检入稿一致"（新鲜度 gate）。

### 4.5 type 单源（FP10）

- wiki-spec §9 的 type 分类为 SSOT；workspace-spec §13 只写一行指针
  （"type 分类见 yzr-llm-wiki-management references/wiki-spec.md §9"，不重抄清单）。
- 删除 MEMORY 条目 [[wiki-workspace-spec-type-coupling]]（单源化后不再双向同步）。

### 4.6 纪律层（FP11）

- **所有权四分表**（写入两 spec + 4 份模板正文）：

  | 文件 | 所有权 |
  | --- | --- |
  | AGENTS.md / CLAUDE.md | byte-owned（整个文件 = 模板渲染，agent 禁改） |
  | .gitignore | block-owned（llmw managed 块禁改，块外用户自由） |
  | index.md / log.md / tags.md / MEMORY.md | header-owned（文件头禁改，growth 段 agent 日常写） |
  | 内容页 + growth 条目 | content-owned（agent 拥有） |

- **模板禁改段**：4 份模板正文加一段"本文件由 CLI 渲染拥有，禁手改；自定义纪律沉淀去
  MEMORY/；改动会被 checker 判 drift、`llmw wiki upgrade` 重渲染覆盖"。
- **I-1 新措辞**（写入本仓 AGENTS.md）："代码永不创作内容语义——CLI 写路径仅限骨架渲染
  （字节来自 skill 模板）+ 机械 scribe（字节来自 agent 输入）+ 注册表声明的纯函数变换"。

### 4.7 约束

- 不引入第三方依赖（llmw 保持零依赖，py3.7+）。
- 不动 skill 侧模板/fixtures 之外的内容散文（spec 复述审计先报告后改写，FP12）。
- 不破坏 `--path` 直传模式（测试与未注册 wiki 硬需求，Task 1 已建）。
- 不改变 `llmw wiki lint --check-version --apply` 的既有 plan JSON 输出（存量 agent 消费方）。

## 5. 场景拆解

| # | 场景 | 类型 | 触发条件 | 期望行为 | 设计落点 |
| --- | --- | --- | --- | --- | --- |
| S1 | 近世代 clean wiki upgrade | 主流程 | 版本落后或同版本漂移 | render 全骨架 + 自验证 0 error，`done` | §7.4 |
| S2 | 近世代 + pre-constraint 自定义 | 分支 | dry-run 检出 AGENTS.md 有模板外内容 | 输出 diff + 提示搬 MEMORY，apply 需 `--yes`，不写盘 | §7.4 / §8.1 |
| S3 | 结构变化（新增/删除/改名文件） | 分支 | legacy 路径表命中 | 创建/删除/移动，进 `changed[]` | §7.5 |
| S4 | 内容页变换残留 | 异常 | registry 判定需语义判断 | `done_with_residue` + 残留清单 | §8.2 |
| S5 | 未来 growth 格式变更 | 分支 | transform 插槽被填充（当前空） | 注册表函数执行；未填充则残留 | §8.3 |
| S6 | upgrade 后自验证失败 | 异常 | 重渲染产物不过 checker | exit 2，不 bump 版本钉，保留 dry-run diff | §8.4 |
| S7 | 改模板措辞 | 主流程 | 编辑 agents-md-template.md | 只动 skill 侧；checker/测试/upgrade 自动跟随 | §7.2/§7.3 |
| S8 | 加 lint 规则 | 主流程 | 新增 check 函数 | 只动代码 + checklist 生成稿自动更新 | §7.7 |

## 6. 方案总览

核心思路：**一致性由构造保证，升级由 CLI 重新出生**。

```
         ┌────────────────────────── skill（纯文本）──────────────────────────┐
         │  templates/*.md + fixtures/*.txt + SKILL.md(版本钉) + spec 散文      │
         └───────────────▲───────────────────────────────────────────────────┘
                         │ 读取（唯一依赖方向）
┌────────────────────────┴────────────────────────────────────────────────────┐
│ llmw.content                                                                 │
│  render.py ──单一渲染入口（变量 SSOT = metadata + 版本常量）                   │
│     ▲            ▲            ▲            ▲                                 │
│  init_wiki    upgrade      checkers      tests            （五个消费方）      │
│  (add)       (resync)   (render-compare) (production render)                 │
│                                                                              │
│  checkers: 从 fixtures 字节解析 oracle（无 SKELETON_SPECS / 无提取正则）       │
│  upgrade:  resync + 两护栏 + legacy 路径表 + 3 终态 JSON + 自验证             │
└──────────────────────────────────────────────────────────────────────────────┘
```

关键决策速览（细节见 §7/§10）：
1. **渲染单一入口**——五个消费方调同一 `render_*()`，模板事实一个家（§7.2）。
2. **oracle 派生化**——checker 从 fixture 字节解析，改 fixture 只动 1 文件（§7.3）。
3. **upgrade = 重新出生**——resync 幂等版本无关；迁移注册表不建，换成 legacy 路径表 +
   两护栏（§7.4-7.5）。
4. **检查器从"查"变"构造"**——fixtures-smoke CI 三角自检模板/fixture/render/checker（§7.7）。

## 7. 详细设计

### 7.1 流程与状态机

**upgrade 主流程**（`llmw wiki upgrade`）：

```
输入 --path/--name
  → 读 metadata toml + 版本常量（变量 SSOT）
  → render-compare 预检：diff 将被覆盖的自定义（骨架 vs 模板渲染稿）
      ├─ diff 非空 → 非 dry-run 需 --yes；dry-run 打印 diff 后停（blocked_drift 语义，不写盘）
  → resync 执行：
      ├─ byte-owned（AGENTS/CLAUDE）→ 全量重渲染 Write
      ├─ growth 文件（index/log/tags/MEMORY）→ 换头保条目（按段嫁接）
      ├─ .gitignore → managed block 替换
      ├─ 缺失骨架文件 → 从 fixture 创建
      └─ legacy 路径表 → 移动/删除
  → [transform 插槽]（当前空）→ 若注册表命中执行；未命中项进残留
  → 版本钉写回（AGENTS §八 经重渲染 + metadata templates_version）
  → 自验证：内联重跑 fixtures checker → 0 error?
      ├─ 是 → done / done_with_residue（按残留是否为空）
      └─ 否 → 报错 exit 2，版本钉不落
```

**resync 的 growth 按段嫁接算法**（唯一核心算法）：

```
输入：旧文件 text + 目标 fixture（渲染后）
1. 解析旧文件 → {frontmatter?, 骨架头(H1/说明块), 段表 {## 段头: [条目行]}}
2. 渲染目标 fixture（变量从 metadata 取）
3. 对目标文件逐 ## 段：若有同名旧段 → 填旧段条目；无 → 留占位符
4. 拼回：新 frontmatter/骨架头 + 各段（含 growth）
失败（解析不出旧段结构）→ 走 blocked_drift / 残留（不静默丢条目）
```

**状态机**（upgrade 命令生命周期）：

```
idle → preflight（drift diff）→ resync → verifying → done
                          ↘ blocked_drift（apply 前需 --yes，或搬 MEMORY 后重跑）
                          ↘ verifying fail → error（版本钉不落，可重跑）
```

### 7.2 render.py 设计（FP1/FP2）

- 新模块 `llmw/content/render.py`，暴露（例）：
  - `render_wiki_agents_md(meta: WikiMeta, cli_version, spec_version) -> str`
  - `render_wiki_claude_md(topic) -> str`
  - `render_wiki_index_md(meta, setup_date) / render_wiki_log_md(...)`（growth 文件骨架头）
  - `render_workspace_agents_md(ws_meta, cli_version, spec_version) / render_workspace_claude_md(name)`
- `WikiMeta` 从 `wiki_metadata.toml`（store 层已有 dataclass）取 `name`/`topic`/`created_at`；
  workspace 取 `workspace.toml#display_name`。
- `init_wiki.render_and_write` / `workspace.manager` 的模板渲染改为调 render.py（编排逻辑
  ——目录树/gitkeep/落盘——留在原处）。
- 占位符 assert 无残留逻辑收进 render.py 内部（`_substitute` 迁移至此）。

### 7.3 checker 派生化（FP3/FP4）

- **wiki_fixtures**：
  - 删 `AGENTS_TOPIC_ROW_RE` / `AGENTS_SETUP_DATE_ROW_RE` / `AGENTS_CLI_VERSION_ROW_RE` /
    `AGENTS_VERSION_ROW_RE` 4 条提取正则与自拼渲染 → `agents-md-template-sync` 改为
    `render_wiki_agents_md(meta_from_metadata, ...) == file`（diff 即报告）。
  - 删 `SKELETON_SPECS` 硬编码 → 新增 `_derive_oracle_from_fixture(name)`：
    解析 fixture 字节得 frontmatter 键 / H1 / 说明块 / `##` 段头 / growth 占位。
    各骨架 check（memory-index-skeleton / index-md-skeleton / log-md-skeleton /
    tags-md-skeleton / scripts-md-skeleton / gitignore 段）改从 oracle 取期望。
  - growth 边界约定写入 `references/fixtures/README.md`（§4.2）。
- **workspace_fixtures**：`workspace-agents-md-template-sync` / `claude-md-template-sync`
  改为 `render_workspace_*()` render-compare；`gitignore-skeleton` / `memory-index-skeleton`
  的期望从 fixture 字节推导（memory-index.txt / gitignore 先例已有）。
- **测试**：`test_content_wiki_fixtures._render_agents_md` 等迷你渲染器 → 调生产 render
  （用 scratch metadata）；clean/drift 断言不变。
- **行为保持约束**：本次为 refactor——全部既有 check id / severity / 通过/失败语义不变；
  fixtures-smoke + pytest 全绿才算完。

### 7.4 upgrade 引擎（FP5/FP6/FP8）

- 新模块 `llmw/content/upgrade.py`（wiki）+ `llmw/content/upgrade_workspace.py`（workspace，
  或单模块双入口）。核心：

  ```
  run_upgrade(root, *, dry_run, yes, as_json) -> int
    ├─ _plan_resync(root) → [{file, action, diff?}]      # dry-run 输出
    ├─ _apply_resync(plan) → 写盘
    ├─ _apply_legacy_paths(legacy_table, root) → changed[]
    ├─ _run_transforms()（空插槽，注册表函数）
    ├─ _bump_version_pins(root)
    └─ _self_verify(root) → fixtures checker 0 error?
  ```

- **幂等**：任意版本、任意中间态可重跑；重复跑结果相同（重渲染到同一终态）。
- **`--dry-run`** = 输出 plan（不写盘）；`--json` 恒可用（3 终态契约，§4.3）。
- **命令接线**：`llmw wiki upgrade` 走 `_resolve_content_root`（复用 Task 1 的
  `--path`/`--name` 逻辑）；`llmw upgrade`（workspace 级）走 `--workspace` 解析。
- **CLI flag**：`--dry-run` / `--yes` / `--json`（全局已有）。非 TTY 且非 dry-run 无
  `--yes` 时默认 blocked_drift 语义（不写盘），防误覆盖。

### 7.5 legacy 路径表（FP7）

- 数据文件 `llmw/content/legacy_paths.toml`（或随 upgrade.py 内联数据；倾向独立数据文件，
  便于 accumulate）：

  ```toml
  # 路径存在性触发（非版本号触发）——老路径在且新路径不在 → 移动/删除
  [[legacy]]
  kind = "move"
  old = "MEMORY"          # 示例：某历史版本 MEMORY/ 换位
  new = "wiki/MEMORY"
  note = "0.10.0 路径变更（待盘点确认）"
  ```

- 触发语义：`old` 存在 且 `new` 不存在 → 执行 move；`kind = "remove"` → 老骨架路径存在即删。
- 初始行：Task 4 时从 migrate-workflow.md / spec 历史条款盘点（**不臆造**）；当前已知候选：
  MEMORY 位置变更（0.10.0）、scripts/ 相关、老 CLAUDE.md 拆分（该类属内容抽取 → 归残留
  fallback，不进路径表）。

### 7.6 3 终态 JSON 契约（FP8）

见 §4.3 契约全文。补充：
- `blocked_drift` 的 `changed[]` 带 `diff` 预览（供 agent 提示用户搬 MEMORY）。
- `done_with_residue` 的 `residue[]` 每项带 `type` + 一句 `note`（agent 的下一步指令）。
- 契约在 `doc/skeleton-engine-design.md` + `llmw/content/upgrade.py` 模块 docstring 双写
  （代码为真源，本文档为说明）。

### 7.7 规则清单生成（FP9）

- `wiki_fixtures` 的 CHECK_REGISTRY 已是代码单一真源；`wiki_lint` 侧为各 check 函数补充
  机器可读规则元（`_RULES` 常量或 docstring 约定，Task 4 定细节）。
- `llmw wiki lint --list-rules [--format=md|json]`：聚合两处规则 → 输出 markdown。
- `references/lint-checklist.md` §二（deterministic 清单）改为**生成稿**：CI 新增 step
  校验"生成稿 == 检入稿"（新鲜度 gate），检入稿放 `references/lint-checklist.md` 对应段。
- checklist 散文（§三半定性 / §五修复指引 / §七频率）保留人工维护。

### 7.8 type 单源（FP10）

- wiki-spec §9 是 type 分类唯一陈述；workspace-spec §13 改为一行指针。
- 删 MEMORY 条目 [[wiki-workspace-spec-type-coupling]]（git 可恢复）。

### 7.9 纪律层（FP11）

- 4 份模板（wiki agents/claude + workspace agents/claude）正文加"CLI 渲染拥有 / 禁手改 /
  自定义去 MEMORY"段（措辞进 Task 5，落点即这 4 文件 + fixtures/README.md 说明）。
- 两 spec 立"骨架所有权四分表"（§4.6）条款，引用本设计文档 §4.6 表格（同仓不重抄）。
- 本仓 AGENTS.md：I-1 新措辞 + 模块边界表加 `llmw.content` + 触动面表（Task 6 落，引用本文档）。

### 7.10 兼容与影响面

| 维度 | 影响 |
| --- | --- |
| 现有命令 | `llmw wiki lint/check-fixtures` 行为不变（refactor 保持）；新增 `wiki upgrade`/`upgrade` |
| `--check-version --apply` plan JSON | **不破坏**（存量 agent 消费方）；upgrade 是新路径，plan 机制保留为探测/兼容 |
| SKILL.md 工作流 | migrate 节改为 upgrade 命令（Task 5）；ingest/lint 已 Task 1 改完 |
| references/ | lint-checklist §二生成稿化、migrate-workflow 改名 upgrade-workflow（Task 5）、fixtures/README 增 growth 约定 |
| 测试 | 迷你渲染器删、count 钉断言已改、新增 upgrade 端到端 + --list-rules 新鲜度 |
| CI | 新增 --list-rules 新鲜度 gate；skill 零 .py 断言已有 |
| py3.7 | render/upgrade 保持 py37 语法（CI 矩阵守护） |

## 8. 异常与边界处置

### 8.1 pre-constraint 自定义覆盖（S2）

dry-run render-compare 出 diff → apply 前必须 `--yes`；提示先搬 MEMORY。这是唯一
"可能丢内容"路径——diff 预览 + 显式确认 + 不写盘兜住，不静默覆盖。重跑时 diff 已空 → 正常走。

### 8.2 内容页变换残留（S4）

type-memory-value 等语义裁定 → 残留清单（带精确指令），agent 用 `llmw wiki write` 或
Edit 处理。**不**做自动化——CLI 写权限保持"只写骨架"（§4.6 I-1 新措辞）。

### 8.3 未来 growth 格式变更（S5）

transform 插槽为空注册表。若未来 bump 需要（如 log 条目格式换代），届时加一个注册表
函数（版本注册表只在**需要时**建，不预建空壳机制）。未填充而 lint 满屏报错时 → 残留
清单提示 agent。

### 8.4 自验证失败（S6）

resync 后 checker 非 0 error → **版本钉不落**、exit 2、保留 dry-run diff 供排查。重跑
幂等（失败态可再跑）。

### 8.5 growth 切分解析失败

旧文件结构解析不出（用户大改骨架）→ 不静默丢条目：该项进残留 + 提示 agent 人工合并
（不属"机械可解"）。

## 9. DFX 设计

### 9.1 性能与容量

量级低（单 wiki 数十文件、upgrade 低频触发）；resync 为 O(文件数) 一次扫描。性能非主要
矛盾。

### 9.2 可靠性

resync 幂等 + 原子写（fsutil.atomic_write 复用）；upgrade 失败不落版本钉，可重跑。
fixtures-smoke CI 每次 commit 守护 render↔fixture↔checker 三角一致。

### 9.3 安全与合规

不适用（本地单用户文件工具，无鉴权/敏感数据路径；不触碰 `workspace_models.toml` api_key）。

### 9.4 可服务性

`--json` 3 终态契约即可观测性出口；dry-run diff 是变更审计；upgrade 全程无中间文件残留
（延续 plan 不落盘约定）。

### 9.5 可测试性

- render 纯函数（metadata + 版本 → 字符串）直接单测；
- oracle 派生纯函数（fixture 字节 → 期望结构）单测 + 端到端（clean/drift wiki 跑 checker）；
- upgrade 端到端：scratch wiki（clean / 自定义 / 远古 / 结构漂移）→ apply → 断言文件
  状态 + 自验证 0 error + JSON 终态；
- 时间依赖（setup_date）可注入（render 接受 date 参数）。

## 10. 备选方案与设计权衡

| 备选 | 否决理由 |
| --- | --- |
| alembic 式逐版本迁移注册表（链式函数） | 每条链式路径一生只走一次、最难测；resync 单路径每次 CI 都在测。链式正确性依赖起点状态做乘法，resync 终态 == render(当前) 一个等式。加上无远古版本，链式注册表完全无意义 |
| 纯 resync（无护栏） | pre-constraint 自定义静默覆盖 — drift 护栏把这条做成显式行为。版本下限护栏在确认无远古版本后撤掉 |
| 描述符数据文件（SKELETON_SPECS → fixtures 同目录 .toml） | fixture 字节本身已自描述（frontmatter/H1/段/growth 占位），再建描述符 = 第二份拷贝；直接派生化更彻底（gitignore 先例已验证） |
| checklist 双写（散文 + 代码） | 两份漂移；规则 what 入代码 + 生成稿内嵌 §二 + CI 新鲜度断言保 SSOT，散文只留 why |
| 保留 fixtures_check_count 钉 | 搬进 CLI 后跨侧计数同步点无意义；tests 断言 registry 自洽已覆盖 |
| wiki_write 留 skill（早期方案 C） | 全量搬入后 import 卫生更好（无跨包 bootstrap），且 skill 零代码目标更纯 |

## 11. 实施任务书（独立文件）

任务拆解沿用总体计划的 Task 3/4/5（本文档评审后作为其设计依据）：

- **Task 3（P2b）**：render.py + checker 派生化 + 规则 metadata + checklist 生成器
  ——对应 FP1/2/3/4/9。
- **Task 4（P2c）**：upgrade 引擎 + legacy 表 + 命令 + 3 终态契约——对应 FP5/6/7/8。
- **Task 5（P2d）**：纪律层（模板禁改段 + spec 四分表 + type 单源 + upgrade-workflow 改名
  + spec 复述审计）——对应 FP10/11/12。

当前完成度：Task 3-5 均未开始（评审 gate 在本文档）。

## 12. 上线与回滚

- **上线**：单仓原子提交；无灰度需求（本地工具）。Task 3 先行（refactor 保持行为，
  fixtures-smoke + pytest 全绿为门禁），Task 4 在其上加 upgrade，Task 5 收口纪律。
- **回滚**：git revert 对应 commit。旧路径保留（`--check-version --apply` plan 机制不删，
  作为 upgrade 兼容/fallback），故回滚无数据风险；upgrade 写盘前 dry-run diff + `--yes`
  是操作级回退闸。

## 13. 开放问题

| # | 问题 | 默认倾向 | 待确认 |
| --- | --- | --- | --- |
| Q1 | `LLM_WIKI_ROOT` 环境变量注入（enter 注入 agent pane）去留 | 保留（session 上下文零成本；脚本迁走后已非必需，但无害） | 用户 |
| Q2 | workspace `templates_version` 的 wiki_spec 分量——upgrade 时是否联动各 wiki | 不联动（各 wiki 版本归 wiki skill 管，跨 skill 委托提示） | 用户 |
| Q3 | `--list-rules` 生成稿放 lint-checklist.md 内嵌段还是独立文件 | **已锁定**：内嵌 §二（单文件可读），CI 新鲜度断言保 SSOT | — |
| Q4 | spec 复述审计（FP12）规模未知 | 先出报告后改写，不入本次核心 gate | 用户 |

## 14. 排期

不适用（内部重构，按 Task 3→5 顺序执行，无独立时间点要求）。
