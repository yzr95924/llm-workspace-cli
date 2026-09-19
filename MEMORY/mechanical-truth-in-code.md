---
name: mechanical-truth-in-code
description: 机械事实单源架构——finding 注册表 + lint --explain 自省、AGENTS.md 模板承载语义、prose 只载方法论；配套下移试金石 / prose 预算制 / 定期语义审计
metadata:
  type: project
---

# 机械事实单源：代码注册表 + 自省，prose 只载方法论（2026-09-20）

**架构**：每条事实恰好一个家——

| 事实类型 | 家 | 消费方式 |
| --- | --- | --- |
| finding 名 / severity / 含义 / 修法 | `llmw/content/findings.py` 注册表 | `llmw wiki lint --explain=NAME\|all` 现场打印 |
| 格式字节（骨架 / 条目 / frontmatter 生成） | 包内模板 + CLI（render / `write new` / fixtures 金标准） | agent 读实例文件 / 跑命令 |
| 语义纪律（边界 / 生命周期 / 矛盾策略 / 阈值） | AGENTS.md 模板 + fixture 头部（byte-owned，会话自动加载） | 每会话常驻 |
| 方法论（猎矛盾 / 摘要质量条 / 引用稳定性 / 反理性化） | skill prose（SKILL.md + references） | 触发加载 + 按需 Read |

**Why:** 2026-09 审计实证——真 drift（severity 静默落 info、rebuild 回写承诺落空、索引行格式三处不一致）全是"同一事实的第二份手抄本错了"，没有一例代码错。冗余副本 + 865 行 gate 盯副本 = 结构性维护成本；删副本后 gate 只守结构（命令存在性 / 指针有效性）。

**How to apply:**

1. **新增能力先过下移试金石**：纯机械（可判定、无判断）→ 进 CLI + 注册表 + 测试；需语义 → 留 skill 但 CLI 打包证据（finding 文本带数值 / `--explain` 带修法）；需用户拍板 → CLI 停住给选项。默认路径**不是**"新增一条规则 → 改六个面"
2. **prose 预算制**：skill 只为**观测到的失败模式**写字（红旗表只从 transcript 收录）；失败模式被机械化或消失后，对应 prose 要删。文档曾经膨胀是因为每轮"agent 做错了 → 加一段"，没人做减法
3. **引名不引值**：prose 只引分支 / 定位所需的名字；阈值与字面量归 CLI 输出。**计数词**（「5 类」/「5 必填」）只允许出现在 canonical 文档（page-templates）/ byte-owned 模板 / SSOT 文件自身注释；skill prose 与 agent 可见文案（--explain / 错误信息）一律去计数（2026-09-20 清剿，gate 不为此建闸——成本 > 收益，靠本条纪律）
4. **finding 口径零镜像**：skill prose 禁 finding 清单（`` `name`（severity`` 格式，gate 面 2 判红）；裸 kebab token 须命中注册表 / CLI 源码字面量（面 2b 单向存在性，防 rename 静默陈旧）；finding 名可现于分支判定（如 upgrade 触发），但含义 / 修法一律走 `--explain`
5. **定期语义审计**：gate 管语法面（名字 / 指针 / 布局），"行为描述是否仍真实"只能审——大功能收尾或攒批改动后，逐条把文档 claim 钉到代码（本仓 2026-09-19 三轮审计实证抓到 4 处真错）

**已验证承载**：type 枚举四编码收口 `page_types.py` 单源（wiki_lint / wiki_write / findings / wiki_fixtures / init_wiki 全派生，2026-09-20）；lint-checklist 284→145（改名 lint-workflow——deterministic 清单删、agent 半定性方法论留）；page-templates 476→282（删 YAML / lint 校验镜像，判断内容留）；severity 漏配类 bug 由 `tests/test_findings_registry.py` 双向穷举结构性消灭。

**关联**：[[agent-visible-text-reference-whitelist]]（agent 可见文本引用面）、[[boundary-map]]（归属判定）、[[format-version-bump-single-repo]]（page-templates 仍是内容页规则 canonical）
