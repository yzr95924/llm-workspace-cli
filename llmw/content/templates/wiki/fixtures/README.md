# Fixtures

CLI 实现 wiki 仓时落盘的 `wiki/index.md` / `wiki/log.md` / `wiki/tags.md`
/ `MEMORY/MEMORY.md` / `scripts/SCRIPTS.md` / `.gitignore` 六个文件的**字节金标准**。
同仓后 fixtures 是唯一字节金标准（跨仓时代的 `references/canonical/` 双份已删）。
0.37.0 起各 fixture 头部说明块承载该文件的**操作纪律 canonical**（原在 AGENTS.md 模板
§一各段与 skill spec——规则跟着维护者走，落盘进实例 agent 直接读）。

## 用法

CLI 把 fixtures 视为**带占位符的字节模板**：用用户传入的 mapping
（`TOPIC_NAME` / `SETUP_DATE`）替换占位符后落盘。CLI 自身不做字节比对——完整 gate 走
`scripts/test/smoke_fixtures.py`（CI 跑 real `llmw init` + `llmw wiki add` 后用
`llmw wiki check-fixtures` 探测器断言 0 error）。

> **注**：`scripts.md.txt` / `memory-index.txt` / `tags.md.txt` 是**无占位符**（直接落盘，
> fixture 即字面量）；`index.md.txt` / `log.md.txt` 带占位符（渲染后 ≠ fixture）。
> 不要从"fixture 都带占位符"推导。

## fixture 与模板的关系

| | 模板（`*-template.md`） | fixture（`*.txt`） |
|---|---|---|
| **形态** | 带 `{{占位符}}` 的完整文档（`AGENTS.md` / `CLAUDE.md`） | 带占位符的字节模板（header-owned 文件的出生形态） |
| **作用** | CLI init / upgrade 时渲染完整文件 | byte-owned + header-owned 文件的字节级比对金标准 |
| **变更** | 改模板 → bump `wiki_spec_version`（实例需 upgrade reconcile） | 同左（字节变化即 bump） |
| **权威性** | 模板是字节权威（CLI 包内 SSOT） | fixture 是字节权威（CLI 包内 SSOT） |

模板与 fixture 共同承载 CLI 的骨架所有权（byte-owned + header-owned）；block-owned + content-owned 由其他机制承载（`.gitignore` managed block 在 gitignore 模块；content-owned 由 skill 的 page-templates.md 承载）。

## 六个 fixture 对应的"角色"

| fixture | CLI 何时生成 | 后续谁维护 |
|---|---|---|
| `index.md.txt` | init 时刻 | **LLM agent**（每次 ingest / 重写 / 归档同步） |
| `log.md.txt` | init 时刻（首条 setup 条目） | **LLM agent**（追加 ingest/query/lint 条目 + 滚动窗口截断） |
| `tags.md.txt` | init 时刻 | **LLM agent**（按需追加 tag bullet；用户可删误判 bullet 触发 lint `tag-not-in-taxonomy` 审计循环） |
| `memory-index.txt` | init 时刻 | **LLM agent**（追加经验条目到 MEMORY/ 下 + 同步 MEMORY.md 索引） |
| `scripts.md.txt` | init 时刻 | **用户 + LLM agent**（添加 / 修改脚本与同步 SCRIPTS.md 段是原子动作；与 MEMORY/tags.md 同形态——无 frontmatter） |
| `gitignore.txt` | init 时刻 | **不动**（除非用户手动调） |

## fixture 取值约定

fixtures 是**带占位符的字节模板**(而非渲染后的字面量)：

- 主题名占位符：`{{TOPIC_NAME}}`
- 日期占位符：`{{SETUP_DATE}}`
- `.gitignore` / `wiki/tags.md` / `scripts.md.txt` / `memory-index.txt` 无占位符，直接落盘
  （形态一致——无 frontmatter、纯 Markdown；`tags.md.txt` 与 `memory-index.txt` 属于
  wiki 根级文件，不带 wiki 名占位）

CLI 必须按 `mapping = {"TOPIC_NAME": <用户传入>, "SETUP_DATE": <today YYYY-MM-DD HH:MM>}` 做替换，
**不**做替换的占位符会在落盘后被 lint 立即报错(spec §11)。

## AGENTS.md / CLAUDE.md 占位符（不在 fixture 范围）

wiki 根有两份模板产物：**`AGENTS.md`（SSOT）** 由 CLI 拷本目录上层的 `agents-md-template.md`、
**`CLAUDE.md`（薄壳）** 由 CLI 拷同层的 `claude-md-template.md`。两者都**不在**本目录 fixture 覆盖范围
（fixture 只覆盖 CLI init 时刻的"成品"，AGENTS.md / CLAUDE.md 是模板替换产物）。

> **注**：AGENTS.md 虽不进 fixtures 字节比对，但**有独立的运行时同步检查**——
> `llmw wiki check-fixtures` 的 `agents-md-template-sync` 从 wiki §七 提取 4 个变量值反向渲染
> 包内 `agents-md-template.md`，与 wiki 实际 AGENTS.md 字节比对（spec §10.1）。机制同源：
> 都建立在"AGENTS.md = 模板 + 4 个占位符替换"这一事实上；区别只在本目录管 **init 时刻**、
> template-sync 管 **init 之后的整个生命周期**（含 spec 升级重渲染）。

CLI 必须替换的占位符：

| 占位符 | 替换为 | 出现在 |
|---|---|---|
| `{{TOPIC_NAME}}` | 用户传入的主题名 | AGENTS.md + CLAUDE.md（薄壳） |
| `{{SETUP_DATE}}` | 当天日期 `YYYY-MM-DD HH:MM` | AGENTS.md |
| `{{WIKI_SPEC_VERSION}}` | CLI 当前兼容的 wiki spec 版本 | AGENTS.md §七（薄壳不持版本） |
| `{{CLI_VERSION}}` | CLI 自身版本号 | AGENTS.md |

CLI 替换后做内容级验证（不能用 fixture 字节比对）：

1. AGENTS.md 的 4 个 `{{...}}` 占位符 + 薄壳 CLAUDE.md 的 `{{TOPIC_NAME}}` **全部被替换**——`grep -c '{{' AGENTS.md CLAUDE.md` 应为 0
2. 生成的 AGENTS.md §七 "Wiki Spec 版本" 与 `llmw.WIKI_SPEC_VERSION` 常量一致（SKILL.md frontmatter 由 CI gate 与常量比对）

## 字节级一致性证据

用固定测试 mapping `{TOPIC_NAME: "Test", SETUP_DATE: "2026-06-28 14:30"}` 渲染 fixtures 即得
原 canonical/ 字面量——`tests/test_content_wiki_fixtures.py` 与
`scripts/test/smoke_fixtures.py` 的探测器断言共同保证：CLI 或 fixture 任一改坏，
CI 立即红。

## Growth 约定（CLI 拥有 vs agent 成长）

fixtures 只承载 **CLI init 时刻的骨架字节**；内容在 init 之后由 agent / skill
按 ingest / query / lint / memory 工作流成长——成长部分**不**回写到 fixture：

| 文件 | fixture 覆盖（骨架） | 成长内容（fixture 外） |
|---|---|---|
| `wiki/index.md` | frontmatter + H1 + 说明块 + 5 类别 H2 标题 | 类别下每篇 ingest 产出的 page bullet / 链接 |
| `wiki/log.md` | frontmatter + 说明块 + 第一条 setup 条目 | 之后每次 ingest / query / lint 追加的条目 |
| `wiki/tags.md` | H1 + 说明块（空 bullet 列表） | agent 按需追加的 tag bullet |
| `MEMORY/MEMORY.md` | H1 + 说明块 + `## 索引` 段标题 | 索引下每条经验条目 |
| `scripts/SCRIPTS.md` | H1 + 说明块 + `## 索引` 段标题 | 用户 / agent 追加的脚本条目 |
| `.gitignore` | llmw 托管块 + OS / Obsidian / 临时文件段 | 用户自定义排除规则（CLI 不动） |

**原则**：fixture 改 = spec 改；fixture 加新骨架字段 = spec 改；
fixture 加具体 page / tag / 经验 / 脚本 = 错误（那是 agent 工作流产物，不是骨架）。