# Lint 详细 Checklist

Lint 让 wiki **不腐烂**。Karpathy 原话："The tedious part of maintaining a knowledge
base is not the reading or the thinking — it's the bookkeeping." Lint 把 bookkeeping
的一部分自动化。

## 目录

- [一、调用方式](#一调用方式)
- [二、Deterministic 检查清单（脚本执行）](#二deterministic-检查清单脚本执行)
- [三、半定性检查（agent 执行）](#三半定性检查agent-执行)
- [四、报告格式](#四报告格式)
- [五、Semantic-merge 规则](#五semantic-merge-规则)
- [六、lint 之后](#六lint-之后)
- [七、lint 频率](#七lint-频率)
- [八、lint 的边界](#八lint-的边界)

Lint 分**两层**：

1. **Deterministic**（脚本检查，可程序化）——`scripts/lint_wiki.py`
2. **Semi-qualitative**（agent 检查，需理解语义）——本文件"半定性检查"段

**与 `wiki_write.py` 的分工**：log / index / touch / new / memory 的**正路**是
`wiki_write.py`（产物天然合规，见 SKILL.md §设计决策「机械 vs 判断」准入规则）；
lint 的 deterministic 检查兜底**带外手改**（用户 / agent 手工 Edit 的场景）。

## 一、调用方式

```bash
python3 yzr-llm-wiki-management/scripts/lint_wiki.py "$LLM_WIKI_ROOT"
# 或带严重性过滤
python3 yzr-llm-wiki-management/scripts/lint_wiki.py "$LLM_WIKI_ROOT" --severity error
```

退出码：0 = 干净；1 = 有问题（看输出）；2 = 运行错误。

### 子命令 `--migrate-confidence`（仅供旧用法兼容）

老 wiki 中 `confidence: high/medium/low` 字段（已退役）一次性迁移到新
`reviewed` + `reviewed_at`。行为：`high` → `reviewed: true` + `reviewed_at`（今天）；
`medium` / `low` → 仅移除；遇冲突 → `migration-conflict` 跳过该页。输出
`<N> migrated, <M> removed, <K> skipped (conflicts)`。**互斥模式**，不写 log 条目。
新流程一律走 `--check-version --apply`；保留仅供旧脚本/CI 调用兼容。

### 子命令 `--check-version`

扫当前 wiki 的 spec 版本（解析 `<wiki-root>/AGENTS.md` §八；老 wiki fallback
`<wiki-root>/CLAUDE.md`）与 SKILL 仓 `metadata.wiki_spec_version`（脚本常量
`CURRENT_WIKI_SPEC`）比对 + 扫已知 legacy 现场（`confidence-field` /
`type-memory-value`）+ 自动调 fixtures 检查：

```bash
python3 yzr-llm-wiki-management/scripts/lint_wiki.py "$LLM_WIKI_ROOT" --check-version --json
# 加 --apply 输出 migration plan（stdout JSON，不落盘）供 agent 按 [`migrate-workflow.md`](migrate-workflow.md) 走 Edit/Write 修复
python3 yzr-llm-wiki-management/scripts/lint_wiki.py "$LLM_WIKI_ROOT" --check-version --apply --json
```

行为：默认 dry-run（只打印报告，不动文件）；`--apply` 以 stdout JSON 输出 migration
plan（含 `actions[]` / `skipped_conflicts[]` / `agent_rules[]` / `fixtures_actions[]`）；
标记冲突页 → agent 跳过 + 转人工；**互斥模式**，不写 log 条目。
完整 agent 修复路径见 [SKILL.md §5 Migrate](../SKILL.md#5-migrate升级-wiki-spec)；
迁移依据 SSOT = plan `actions[]`（remove/add_or_modify/to_action 自含）+
[`migrate-workflow.md` §六](migrate-workflow.md#六语义合并规则)。

## 二、Deterministic 检查清单（脚本执行）

> 机制细节（实现用的正则 / 函数 / 分支条件）在 `lint_wiki.py` docstring——本节只给
> 口径：**finding 名 / 严重性 / 触发 / 修法**。

### 前置：wiki 版本一致性

每次常规 lint 都查 `<wiki-root>/AGENTS.md` §八 与 `CURRENT_WIKI_SPEC` 一致性（实现：
`check_spec_version()`，与 `--check-version` 同源）——日常 lint 就能感知版本漂移：

- `wiki-spec-version-stale`（warn）：版本**落后** SKILL → 跑 `--check-version --apply`
  走升级流程（SKILL.md §5 Migrate）
- `wiki-spec-version-ahead`（warn）：版本**领先** SKILL → 升级 SKILL 仓对齐
- `wiki-spec-version-unparsed`（warn）：§八 行无法解析 → 跑 `--check-version` 诊断
- 一致（equal）→ 无 finding

### 1. `raw/` 不可变性

- `raw-modified`（**error**）——git 仓内 + raw/ tracked 文件有未提交改动 = 违反纪律。
  修法：问用户，还原或确认后提交
- 跳过（不报错不提示）：无 `.git/`（默认状态，CLI 不自动 git init）/ raw/ 未纳入
  git 跟踪 / 传 `--no-git` 静默跳过
- `raw/discussions/`（spec §15）未提交改动属预期，从 `git status` 结果中排除

### 2. frontmatter 完整性

- 扫 `wiki/` 5 个内容子目录 + `<wiki-root>/MEMORY/*.md`（排除 `MEMORY.md` 本身）
- 口径两类（spec §5.2 vs §9）：**wiki 5 类内容页** 5 必填（`title` / `type` /
  `created` / `updated` / `tags`，字段定义见 [page-templates.md §一](page-templates.md#一共有-frontmatter-段)）；
  **MEMORY/*.md** 仅 `title` 必填（其余全 optional）
- `type` 取值：5 类内容页；MEMORY 桶额外 `memory` / `memory-entry`
- `type-memory-value`（error，legacy）：仅对 wiki 内容页误用 reserved `type: memory`
  报错；MEMORY/*.md 上合法，不触发
- findings：`missing-frontmatter`（error）/ `invalid-type`（error）

### 3. frontmatter 来源（source / synthesis 页）

- `sources-missing`（**error**）：`type: source` 的 `sources:` 非空 + 每个值是 raw/
  现存路径；`type: synthesis` 的 `sources:` 非空（可指 wiki 内页）
- `sources-absolute-path`（error，仅 source 页）：任一元素以绝对路径形式出现（Unix /
  Windows 盘符 / UNC 三种）——破坏跨机器可移植性。修法：改 wiki 根相对 raw/ 路径
- **`raw/external/<symlink>/...` 例外**（spec §13.3）：以 `raw/external/` 起始时走
  关联校验链——`sources-malformed`（段数 < 3）/ `sources-external-anchor-missing`
  （缺 anchor）/ `sources-external-symlink-missing`（symlink 不存在）/
  `sources-missing`（跟随 symlink 后不可访问；external repo 是 git 仓即目录，可指向整仓）
- `source-in-discussions`（error，仅 source 页）：指向 `raw/discussions/` = provenance
  后门。修法：走 spec §15.3 归档路径（消化式 / 转正式 `mv` 后再 ingest）

### 4. 路径引用完整性

- `broken-link`（**error**）：`wiki/**/*.md` 的 Markdown 链接 / 图片相对路径解析后
  不指向现存文件（外部 URL 跳过）。修法：修正链接或补文件

### 5. index.md 覆盖

- `index-missing`（error）：`wiki/index.md` 不存在
- `orphan-page`（error）：非 index / log 页未被 index 引用。正路：
  `wiki_write.py index add`；修法：补条目或按 archive 流程从 index 移除

### 6. log.md 格式

- `log-missing`（error）：`wiki/log.md` 不存在
- `log-format`（warn）：行不匹配正则（见 [page-templates.md §7](page-templates.md#7-logmdlog)）——
  破坏 `grep "^## \[" log.md` 可用性。正路：`wiki_write.py log`；修法：改行

### 7. 过期摘要

- `stale-summary`（warn）：`type: source` 且 `updated` 距今 > `STALE_SUMMARY_DAYS`
  （lint_wiki.py 常量）。修法：复查源文件是否有更新，重摄取

### 8. 文件名规范

- 文件名非 kebab-case（小写 + `-`）→ warn。修法：改名 + 更新引用

### 9. 重复标题

- 同一 `title` 出现在多个 wiki 页 → warn。修法：合并候选

### 10. log.md 条目数（log-truncation）

- `log-truncation-recommended`（warn）：条目数 > `LOG_RETENTION_LIMIT`（lint_wiki.py
  常量，默认 50）——完整历史靠 git（`git log -p -- wiki/log.md`）。正路：
  `wiki_write.py log` 写入时自动截断；带外手改超限才由 agent Edit 删最旧保最近 N

### 11. Tag Taxonomy 校验

- 解析 `<wiki-root>/wiki/tags.md`（**主流位置**）裸 bullet 列表；不存在则 fallback
  AGENTS.md `### Tag Taxonomy` 段（老 wiki 过渡期，spec §9.1）。文件必须是**裸 bullet**
  （包在 code block / HTML comment 里 = 解析 0 tag 静默跳过）；支持
  `- category：tag1 / tag2` 中英文分隔
- 仅对 5 类内容页做包含校验；**MEMORY agent 私有**不共享 taxonomy；tags.md 自身不参与
- 找不到任何 tag 源 → 静默跳过（新 setup 不报错）
- `tag-not-in-taxonomy`（**info**）——审计循环：用户删 tags.md bullet → 下次 lint 报
  所有残留引用页，由用户裁定二选一（重新加回 / 从页面删 tag）
- 严格 tag 名 = 小写 kebab-case（`^[a-z0-9][a-z0-9-]*$`）

### 12. 页面体量

- `oversized-page`（warn）：5 类内容页正文**非空行数** > `PAGE_SIZE_THRESHOLD`
  （lint_wiki.py 常量，与 AGENTS.md「Page Thresholds」对齐；MEMORY 无上限——spec §5.2）
- 修法：拆成子主题页 + cross-link

### 13. 可信度与认知质量信号（reviewed / contested / contradictions）

为什么是 deterministic：只读作者**已写**的 frontmatter 信号并拎出来；"是否真的经过
认真审核 / 到底是否矛盾"是 §三 半定性工作。字段语义见
[page-templates.md §一「可选：可信度与认知质量信号」](page-templates.md#可选可信度与认知质量信号)。
全部可选（省略 = 不评，不报）；MEMORY/*.md 不进 reviewed 校验（无人工 review 语义角色）。

- `pending-review`（info）：非 log/index 页未含 `reviewed: true`——新常态，仅提示
- `reviewed-stale`（warn）：`reviewed: true` 存在但 `updated > reviewed_at`——LLM 修改后
  漏清戳。正路：编辑后 `wiki_write.py touch`；修法：删两字段回未审核态
- `invalid-reviewed-value`（warn）：取值非严格 `true`（`"true"` / `yes` / `1` / `false`）
- `reviewed-at-missing`（warn）：`reviewed: true` 但缺 `reviewed_at`
- `reviewed-at-orphan`（warn）：`reviewed_at` 存在但缺 `reviewed: true`
- `index-review-badge-drift`（warn）：index.md 条目 ✓/✗ 标识与被链页 frontmatter 不一致
- `contested-page`（warn）：`contested: true` 的页——未解决矛盾，裁定后移除标记
- `contradiction-target-missing`（warn）：`contradictions` 指向不存在的页
- `contradiction-asymmetric`（warn）：A 列 B 但 B 未反向标注 A（字段要求**双向标注**）
- `legacy-confidence-field`（warn）：出现已退役 `confidence:` 字段 → 跑
  `--migrate-confidence`（建议保留 ≥ 1 个迁移周期，未触发可移除）

### 14. MEMORY.md 索引一致性

- `memory-not-indexed`（info）：`MEMORY/*.md`（非 `MEMORY.md`）未在 MEMORY.md
  `## 索引` 段列出——下次 `@import` 加载后该条目不可见。正路：
  `wiki_write.py memory add`（原子追加索引行）；修法：追加一行 `- [Title](<slug>.md) — 一句话`
- `memory-index-dangling`（warn）：索引指向的 `<slug>.md` 不存在（索引与磁盘脱节；
  短条目 `- 一句话事实` 无链接、不算）
- MEMORY.md 不存在 → 静默跳过（老 wiki 迁移期）
- `agents-md-template-sync`（error，fixtures）：AGENTS.md 与模板渲染字节不一致 →
  按 wiki-spec §10.1 全量重渲染 + 本地定制逐条搬 MEMORY/ 或丢弃

### 15. related / compared 路径引用完整性

- `related-broken-link`（warn）：frontmatter `related`（concept 页）/ `compared`
  （comparison 页）每条元素按**内容根 `wiki/` 相对**解析（`concepts/X.md`，不带
  `./` / `../` / `wiki/` 前缀）不存在
- 两层路径约定（spec §9）：frontmatter 路径字段（机器消费为主）→ wiki 根相对；
  正文 markdown 链接（人读为主）→ 文件相对。`contradictions` 字段按既有约定走文件
  相对（§二.13 处理），不在本检查范围

## 三、半定性检查（agent 执行）

跑完 deterministic 检查后，agent 应当再做以下检查（**仅在 wiki 规模 < 200 页
时人工做**——更大规模需 LLM-based 自动检查）：

### 17. 矛盾主张

- 同一概念 / 实体在 ≥ 2 个页里被以**矛盾方式**描述（**内容层**矛盾，区别于 §二.13 的
  frontmatter `contested` 信号——后者是作者已标注、本项是 agent 主动发现未标注的）
- 例：`concepts/<attribute>.md` 说 "`<value A>`"，`sources/<other>.md` 说 "`<value B>`"
  （可能是不同版本，但未注明）
- 检查方法：grep 概念关键词 + 读周围上下文；发现后建议双方补 `contested: true` +
  `contradictions` 互指（让 §二.13 后续能持续追踪）
- **严重性：warning**——可能需要更深入调研

### 18. 缺失交叉引用

- 概念 X 出现在页面 A 的正文里，但 A 没有链接到 `concepts/x.md`
- 例：`sources/foo.md` 提到 "self-attention" 但没链到 `concepts/self-attention.md`
- 检查方法：grep 概念名 + 看是否生成了 link
- **严重性：info**——是 lint 的最高频 finding

### 19. 缺失 entity / concept 页

- 重要概念（出现在 ≥ 3 个 source 页）但没有独立 entity / concept 页
- 检查方法：grep 候选关键词 + 统计出现次数
- **严重性：info**

### 20. 调查方向建议

- 哪些主题"很热门"（多个 source 涉及）但 wiki 内的综合 / 对比页没有
- 例：5 篇 source 提到 RAG，但 `syntheses/rag-evolution.md` 不存在
- **严重性：info**——这是"建议新摄取 / 新合成"的机会

### 21. 资料投放口是否堆积

- `raw/articles/` 是否有大量未摄取文件（跑 `ingest_diff.py` 即可知）
- **严重性：info**——堆积太久会让 ingest 时信息过载

### 22. 漂移点引用

- 正文引用上游可变、且无机制能感知其变化的事实——按
  [ingest-workflow.md §七](ingest-workflow.md#七正文引用的稳定性漂移点规避)
  五类扫描（位置引用 / 瞬态数值 / 版本绑定 / 完整枚举 / 归属信息）
- 典型命中：`foo.py:812` 式行号、裸"最新 / 目前"、无"截至"日期的数值快照
- 命中 → 建议按该节改写规则修（锚点 / 快照 / 退到 `sources:` 字段），不回退 schema
- **严重性：info**——写作质量项，agent 判断，不阻断

## 四、报告格式

脚本 + agent 一起输出统一格式，每条带：**严重性** + **类别** + **文件:行** + **描述**。

```text
[ERROR] raw-modified: raw/articles/foo.md has uncommitted changes
[ERROR] orphan-page: wiki/concepts/qux.md is not listed in wiki/index.md
[WARN] reviewed-stale: wiki/concepts/<concept>.md reviewed=true reviewed_at=2026-06-15 但 updated=2026-07-01 — LLM 修改后未清 reviewed，建议重新审核
[WARN] external-target-drift: raw/external/linux-kernel 当前 symlink 解析为 '/home/foo/src/linux-kernel'，但 anchor 记录 '/apsarapangu/disk10/src/linux-kernel'
[INFO] memory-not-indexed: MEMORY/ocr-tips.md 未在 MEMORY.md 索引中列出
```

（external symlink ↔ anchor 关联的 finding 全家：`external-anchor-missing` /
`external-anchor-corrupt` / `external-source-name-invalid` / `external-symlink-missing` /
`external-anchor-orphan` / `external-target-drift`——
spec §13 相关，详见 lint_wiki.py `check_external_symlinks` docstring。）

## 五、Semantic-merge 规则

> 语义合并规则（agent 走 migration plan 时的合并依据）已并入
> [`references/migrate-workflow.md` §六](migrate-workflow.md#六语义合并规则)——
> 含 frontmatter 字段合并 / index 条目合并 / anchor TOML 迁移 5 步 / MEMORY 经验合并 /
> log 严格保留 / 决策树。本节只留指针。

## 六、lint 之后

跑完 lint 后，agent 应当：

1. 整理报告（按严重性排序：error > warn > info）
2. **询问用户先修哪些**——不要一次全修（容易回退或引入新问题）
3. 修完后**重新跑 lint 验证**——不要带着 fix 没验过的状态前进
4. 若启用 git，重大修复 commit 时建议加 `lint: <summary>` 前缀；裸目录树 wiki 跳过 commit 步骤
5. **若跑 fixtures-check**——按 §五 Decision tree 区分脚本 vs LLM 修；
   `fixtures-fix-*` 系列可通过 Edit 落，`fixtures-fix-anchor-merge/-schema/-symlink-matches`
   三条要走 [`migrate-workflow.md`](migrate-workflow.md) §6.3 五步迁移（不是单 Edit）

## 七、lint 频率

- **小 wiki（< 50 页）**——每月 1 次足够
- **中 wiki（50-200 页）**——每 2 周 1 次
- **大 wiki（> 200 页）**——每周 1 次；可考虑写 cron
- **重大 ingest 后**——建议跑一次（可能引入新 entity / 断链）
- **跨 spec 升级后**——首次跑 fixtures-check 验证约定文件已切到新 spec 字节形态

## 八、lint 的边界

- **不**自动修——只报告；修由用户 / agent 决定（机械字节操作的"正路"是
  `wiki_write.py`，lint 不兼任 writer）
- **不**评估内容质量（不是 fact-checker）——只看结构和纪律
- **不**评估 frontmatter 的语义是否合理（只检查字段存在性 + 类型合法）
- **不**取代 schema（`AGENTS.md`）——schema 是源头，lint 是脚本化检查
- **fixtures 边界**——`check_wiki_fixtures.py` 扫「约定文件」
  （AGENTS.md §八 / .gitignore / wiki/index.md / wiki/log.md / wiki/tags.md /
  MEMORY/MEMORY.md / MEMORY/*.md 条目 / scripts/SCRIPTS.md / raw/external/.symlink-anchor.toml /
  wiki_metadata.toml）的合规性：
  **`metadata.fixtures_check_count`** 条 check（13 条结构探测 + 7 条骨架字段比对，后者读
  `references/canonical/` + `references/fixtures/gitignore.txt` 作 SSOT）；语义合并走 §五
  由 LLM 判断——脚本不替代人。常规 lint 另跑 `check_spec_version`（§二前置）报版本漂移 warn
