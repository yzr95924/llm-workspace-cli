# Lint 详细流程

Lint 让 wiki **不腐烂**——把 bookkeeping 自动化。Lint 分**两层**：

1. **Deterministic**（CLI 检查，可程序化）——`llmw wiki lint` 执行
2. **Semi-qualitative**（agent 检查，需理解语义）——本文件「半定性检查」节

**与 `llmw wiki write` 的分工**：log / index / touch / new / memory 的**正路**是
`llmw wiki write`（产物天然合规：输出是输入的纯函数 + lint 可 round-trip 验证）；
lint 的 deterministic 检查兜底**带外手改**（用户 / agent 手工 Edit 的场景）。

## 调用方式

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint
llmw wiki --path="$LLM_WIKI_ROOT" lint --severity=error    # 严重性过滤
llmw wiki --path="$LLM_WIKI_ROOT" lint --explain=all       # finding 全清单（不跑检查）
```

退出码（常规）：0 = 干净；1 = 有问题（看输出）；2 = 运行错误；未捕获异常 = 3。
`--check-version` 模式恒 0——是否需迁移看报告字段 `needs_upgrade`。

### Deterministic 检查（CLI）

`llmw wiki lint` 跑全部 deterministic 检查，输出 `<finding>: <message>` 行。
**finding 的含义 / severity / 修法是 CLI 注册表 SSOT**——现场查：

```bash
llmw wiki lint --explain=all            # 全部 finding 清单
llmw wiki lint --explain=<finding 名>   # 单条（如 --explain=orphan-page）
```

覆盖族（改 CLI 自动生效，本文不镜像明细）：format 版本一致性 / `raw/` 不可变性 /
frontmatter 完整性 / sources 引用链 / 正文链接 / index 覆盖 / log 格式与条目数 /
tag taxonomy / 页面体量 / 可信度信号（reviewed / contested / contradictions）/
MEMORY 索引一致性 / external symlink ↔ anchor 关联。

### 子命令 `--check-version`

扫当前 wiki 的 format 版本（解析 `<wiki-root>/AGENTS.md` 末尾「当前配置」表的 `Wiki Format 版本` 行）
与 CLI 常量 `CURRENT_WIKI_FORMAT` 比对 + 扫当前格式 frontmatter 误用
（`type-memory-value`——内容页误用 reserved `type: memory`，常规 lint 不报，
后续修法由 `--apply` 输出的 plan 给出）+ 自动调 fixtures 检查：

```bash
llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version --json
# 加 --apply 输出 upgrade plan（stdout JSON，不落盘）供 agent 按 upgrade-workflow.md 走 Edit/Write 修复
llmw wiki --path="$LLM_WIKI_ROOT" lint --check-version --apply --json
```

行为：默认 dry-run（只打印报告，不动文件）；`--apply` 以 stdout JSON 输出 upgrade
plan（含 `actions[]` / `skipped_conflicts[]` / `agent_rules[]` / `fixtures_actions[]`）；
标记冲突页 → agent 跳过 + 转人工；**互斥模式**，不写 log 条目。
完整 agent 修复路径见 [SKILL.md「Upgrade」](../SKILL.md)；
迁移依据 SSOT = plan 自带的 `agent_rules[]` +
[`upgrade-workflow.md「语义合并规则」`](upgrade-workflow.md)。

## 半定性检查（agent 执行）

跑完 deterministic 检查后，agent 应当再做以下检查（**仅在 wiki 规模 < 200 页
时人工做**——更大规模需 LLM-based 自动检查）：

### 矛盾主张

- 同一概念 / 实体在 ≥ 2 个页里被**矛盾方式**描述（**内容层**矛盾——区别于 frontmatter
  `contested` 信号：后者是作者已标注、本项是 agent 主动发现未标注的）
- 检查方法：grep 概念关键词 + 读上下文；发现后建议双方补 `contested: true` + `contradictions` 互指
- **严重性：warning**

### 缺失交叉引用

- 概念 X 出现在页面 A 正文，但 A 没链接到 `concepts/x.md`；检查方法：grep 概念名 + 看是否生成了 link
- **严重性：info**——是 lint 的最高频 finding

### 缺失 entity / concept 页

- 重要概念（出现在 ≥ 3 个 source 页）但没有独立 entity / concept 页；检查方法：grep 候选关键词 + 统计出现次数
- **严重性：info**

### 调查方向建议

- 热门主题（多个 source 涉及）但没有对应综合 / 对比页——"建议新摄取 / 新合成"的机会
- **严重性：info**

### 资料投放口是否堆积

- `raw/articles/` 有大量未摄取文件（跑 `llmw wiki ingest-diff` 即可知）——堆积太久会让 ingest 时信息过载
- **严重性：info**

### 漂移点引用

- 正文引用上游可变、且无机制能感知其变化的事实——按
  [`ingest-workflow.md「正文引用的稳定性」`](ingest-workflow.md)
  五类扫描（位置引用 / 瞬态数值 / 版本绑定 / 完整枚举 / 归属信息）；命中 → 按该节改写规则修，
  不回退 schema
- **严重性：info**——写作质量项，agent 判断，不阻断

## 报告格式

CLI stdout 按严重性分组（组头 `[ERROR] (N)` / 缩进行为 finding 文本原文 / 末尾
`Total: N finding(s)`）。agent 整理给用户时沿用 finding 文本原文，每条给：
**严重性** + **类别** + **文件** + **描述**（下为整理稿示例，文本取自 CLI 输出）：

```text
[ERROR] orphan-page: wiki/concepts/qux.md 未在 wiki/index.md 中列出
[WARN] reviewed-stale: wiki/concepts/<concept>.md reviewed=true reviewed_at=2026-06-15 但 updated=2026-07-01 — LLM 修改后未清 reviewed，建议重新审核
[INFO] memory-not-indexed: MEMORY/ocr-tips.md 未在 MEMORY/MEMORY.md 索引中列出；该条目下次会话读不到（追加一行：…）
```

单个 finding 的含义 / 修法用 `llmw wiki lint --explain=<finding 名>` 现场查（注册表 SSOT，
含 external symlink ↔ anchor 关联的全家）。

## lint 之后

跑完 lint 后，agent 应当：

1. 整理报告（按严重性排序：error > warn > info）
2. **询问用户先修哪些**——不要一次全修（容易回退或引入新问题）
3. 修完后**重新跑 lint 验证**——不要带着 fix 没验过的状态前进
4. 若启用 git，重大修复 commit 时建议加 `lint: <summary>` 前缀；裸目录树 wiki 跳过 commit 步骤
5. **若跑 fixtures-check**——按 [`upgrade-workflow.md「职责切分」`](upgrade-workflow.md) 区分 CLI 骨架 vs agent 语义合并；
   `fixtures-fix-*` 系列（anchor-schema / symlink-matches / log-format 等当前格式维护）：anchor 类
   走 `llmw wiki external add/remove/rebuild` 命令（CLI 持有 schema SSOT，参考
   [`external-repo.md「sources: 元素类型」`](external-repo.md)）；
   log-format 等纯骨架字段按 `to_action` 字段 + schema 指针用 Edit 落

## lint 频率

- **小 wiki（< 50 页）**——每月 1 次足够
- **中 wiki（50-200 页）**——每 2 周 1 次
- **大 wiki（> 200 页）**——每周 1 次；可考虑写 cron
- **重大 ingest 后**——建议跑一次（可能引入新 entity / 断链）
- **跨 format 升级后**——首次跑 fixtures-check 验证约定文件已切到新 format 字节形态

## lint 的边界

- **不**自动修——只报告；修由用户 / agent 决定
- **不**评估内容质量（不是 fact-checker）——只看结构和纪律
- **不**评估 frontmatter 的语义是否合理（只检查字段存在性 + 类型合法）
- **不**取代 schema（`AGENTS.md`）——schema 是源头，lint 是 CLI 实现的检查
- **fixtures 边界**——`llmw wiki check-fixtures` 扫「约定文件」合规性；check 清单以
  `llmw wiki check-fixtures --json` 输出为准（CLI 注册表唯一真源；结构探测 + 骨架字段比对
  两类，后者读 llmw 包内字节金标准作 SSOT）。语义合并由 LLM 按
  [`upgrade-workflow.md「语义合并规则」`](upgrade-workflow.md) 判断——CLI 不替代人；骨架漂移
  修复走 `llmw wiki upgrade --apply`（本地定制先按 `blocked_drift` 裁定）
