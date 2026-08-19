# Fixtures

CLI 实现 wiki 仓时落盘的 `wiki/index.md` / `wiki/log.md` / `wiki/tags.md`
/ `MEMORY/MEMORY.md` / `scripts/SCRIPTS.md` / `.gitignore` 六个文件的**字面量金标准**。

## 用法

CLI 实现时,把 fixtures 视为**带占位符的字节模板**,把 `references/canonical/` 视为
**字节金标准**——CLI 用自己的 render 函数生成产物,写盘后做字节级比对（`cmp -s`）：

```bash
# 假设 CLI 把产物写到 $TMP/wiki/
# canonical 路径 = yzr-llm-wiki-management/references/canonical/
# fixture 路径  = yzr-llm-wiki-management/references/fixtures/

cmp -s $TMP/wiki/index.md         canonical/index.md
cmp -s $TMP/wiki/log.md            canonical/log.md
cmp -s $TMP/wiki/tags.md           canonical/tags.md          # 裸 bullet 列表,无 frontmatter / 无占位符
cmp -s $TMP/MEMORY/MEMORY.md       canonical/memory-index.md
cmp -s $TMP/scripts/SCRIPTS.md     canonical/scripts.md       # 无 frontmatter / 无占位符,Markdown 结构走 canonical 留演化空间
cmp -s $TMP/.gitignore             <fixture>/gitignore.txt    # .gitignore 纯文本常量,fixture 比对足够
```

> **注**：`scripts.md.txt` 与 `memory-index.txt` 是**无占位符**（直接落盘，与 canonical 字节相同）；
> `index.md.txt` / `log.md.txt` 带占位符（渲染后 ≠ canonical）。不要从"fixture 都带占位符"推导。
> 分组见 §fixture 取值约定。

任何一个不一致 → CLI 实现有 bug,应 fail 退出。

> **术语**：fixtures 是**模板**(带 `{{TOPIC_NAME}}` / `{{SETUP_DATE}}` 占位符),
> canonical 是**渲染后字面量**(用锚点 mapping `{TOPIC_NAME: "Test", SETUP_DATE: "2026-06-28 14:30"}`
> 把 fixtures 跑一遍的产物,作为本 skill 字节金标准)。CLI 升级 / fixture 变更时,重新生成 canonical/。

## fixture 与 spec 的关系

| | spec | fixture |
|---|---|---|
| **形态** | 人类阅读的契约文档（`wiki-spec.md`） | 机器读取的字节模板（`*.txt`） |
| **作用** | 告诉 CLI "应该长什么样" | 给 CLI "字面量比对" 的金标准 |
| **变更** | spec 改 → fixture 改 | fixture 改 → spec 也要跟着改 |
| **权威性** | spec 是概念权威 | fixture 是字节权威 |

两者必须**同步**：spec §3 描述 index.md 的 frontmatter 字段时，fixture/index.md.txt 的实际 frontmatter 必须与之匹配。任一不一致 → review 时立即暴露。

## 六个 fixture 对应的"角色"

| fixture | CLI 何时生成 | 后续谁维护 |
|---|---|---|
| `index.md.txt` | init 时刻 | **LLM agent**（每次 ingest / 重写 / 归档同步） |
| `log.md.txt` | init 时刻（首条 setup 条目） | **LLM agent**（追加 ingest/query/lint 条目 + 滚动窗口截断） |
| `tags.md.txt` | init 时刻 | **LLM agent**（按需追加 tag bullet；用户可删误判 bullet 触发 lint `tag-not-in-taxonomy` 审计循环） |
| `memory-index.txt` | init 时刻 | **LLM agent**（追加经验条目到 MEMORY/ 下 + 同步 MEMORY.md 索引） |
| `scripts.md.txt` | init 时刻 | **用户 + LLM agent**（添加 / 修改脚本与同步 SCRIPTS.md 段是原子动作；与 MEMORY/tags.md 同形态——无 frontmatter） |
| `gitignore.txt` | init 时刻 | **不动**（除非用户手动调） |

详细归属见 `wiki-spec.md` 顶部声明。

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

wiki 根有两份模板产物：**`AGENTS.md`（SSOT）** 由 CLI 拷 `references/agents-md-template.md`、
**`CLAUDE.md`（薄壳）** 由 CLI 拷 `references/claude-md-template.md`。两者都**不在**本目录 fixture 覆盖范围
（fixture 只覆盖 CLI init 时刻的"成品"，AGENTS.md / CLAUDE.md 是模板替换产物）。

> **注**：AGENTS.md 虽不进 fixtures/canonical 字节比对，但**有独立的运行时同步检查**——
> `check_wiki_fixtures.py` 的 `agents-md-template-sync` 从 wiki §八 提取 4 个变量值反向渲染
> `references/agents-md-template.md`，与 wiki 实际 AGENTS.md 字节比对（spec §10.1）。机制同源：
> 都建立在"AGENTS.md = 模板 + 4 个占位符替换"这一事实上；区别只在本目录管 **init 时刻**、
> template-sync 管 **init 之后的整个生命周期**（含 spec 升级重渲染）。

CLI 必须替换的占位符：

| 占位符 | 替换为 | 出现在 |
|---|---|---|
| `{{TOPIC_NAME}}` | 用户传入的主题名 | AGENTS.md + CLAUDE.md（薄壳） |
| `{{SETUP_DATE}}` | 当天日期 `YYYY-MM-DD HH:MM` | AGENTS.md |
| `{{WIKI_SPEC_VERSION}}` | CLI 当前兼容的 wiki spec 版本 | AGENTS.md §八（薄壳不持版本） |
| `{{CLI_VERSION}}` | CLI 自身版本号 | AGENTS.md |

CLI 替换后做内容级验证（不能用 fixture 字节比对）：

1. AGENTS.md 的 4 个 `{{...}}` 占位符 + 薄壳 CLAUDE.md 的 `{{TOPIC_NAME}}` **全部被替换**——`grep -c '{{' AGENTS.md CLAUDE.md` 应为 0
2. 生成的 AGENTS.md §八 "Wiki Spec 版本" 与本 skill `metadata.wiki_spec_version` 一致

## 字节级一致性证据(渲染后)

fixtures 是**模板**;CLI 渲染后产物与 `references/canonical/` 下的字面量文件**字节级一致**。
canonical/ 下的字面量文件是把 mapping 喂 `{TOPIC_NAME: "Test", SETUP_DATE: "2026-06-28 14:30"}` 后
渲染产物的副本,作为本 skill 字节金标准。

CLI 升级 / fixture 变更时,跑附录 A 自检:用锚点 mapping render → cmp canonical → 不一致 = CLI / fixture 有 bug。

## 清理时机

`canonical/` 下的字面量文件是本 skill 的**字节金标准**,`fixtures/` 是**带占位符的字节模板**。
**不要删除**任一目录——前者是字节防线的最后一道,后者是占位符替换的源材料。
