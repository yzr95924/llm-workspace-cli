# MEMORY 索引

跨会话需要持久化的"为什么 + 边界"规则。完整条目各建一个 `<slug>.md`，短条目直接放本索引。

> **本文件是项目级规则的唯一真源（SSOT）。** agent 会话级 memory 只放指向本文件的指针，
> 禁止内容副本。

> **新建条目先读 [memory-entry-conventions](memory-entry-conventions.md)。** 索引区按"完整条目
> （带 `.md` 正文） / 短条目（裸行 reminder）"两类分区：建条目时先按颗粒度判别形式，再决定是否
> 单独建 `<slug>.md`。

## 项目规则

### 完整条目（带 .md 正文）

按主题分组：

**MEMORY 元规则**（管理本仓 `MEMORY/` 自身）

- [MEMORY 条目约定](memory-entry-conventions.md) — 判别两类条目 / 索引格式 / 写入纪律 / 持久化策略（仓库 MEMORY vs 个人 memory / 代码可查不写） / 与个人 memory 关系；建新条目必读

**CLI 参数与开发节奏**

- [CLI 参数传递约定](cli-ux-interactive-and-named-flags.md) — 配置类命令优先交互式；需用户指定的参数用命名 flag（`--xxx=`），不用裸位置参数
- [bash 补全 COMP_WORDBREAKS 坑](bash-completion-wordbreaks.md) — 调试须 pty 实测真实 readline（手动设 COMP_WORDS 不经分词，会假通过）；COMP_WORDBREAKS 含 = 拆 --flag=，补全函数须规范化 cur
- [completion 多段位置参数补全](completion-positional-stages.md) — 子命令有多段位置参数（如 `wiki config {get,set,unset} <key> <value>`）时，bash / fish / zsh 三套都需按 token 位置分阶段补全；漏段 Tab 断档

**AI agent 集成**

- [Agent settings env 优先级](agent-settings-env-precedence.md) — settings.json 的 `env` 块盖过
  subprocess env；`enter` 用 Local 层（`settings.local.json`）覆盖 user env 块；
  `ANTHROPIC_MODEL` 用 `name` 非 `model_id`
- [model 操作不走环境变量](model-ops-no-env-vars.md) — model 配置只从 `workspace_models.toml` 读（绝不读 `os.environ` 当真相源）；`enter` 通过 Local 层（`settings.local.json`）交付 `ANTHROPIC_*`（值来自 registry）
- [Overlay habit template](overlay-habit-template.md) — `llmw/models/overlay.py:_HABIT_TEMPLATE` 是代码内常量的"习惯级" env key（非用户可配），随 enter 一并写入 settings.local.json；加新 key = 改一行常量

**SKILL 与格式契约（2026-08-18 起两 SKILL 同仓）**

- [format 版本号 bump：包内常量 + CI gate](format-version-bump-single-repo.md) — SSOT = `llmw/__init__.py` 常量；bump 判别式：现有实例需要 reconcile 才 bump；文档/重构不 bump
- [三方边界关系图](boundary-map.md) — 四方（用户 / CLI / 两 skill）依赖方向 + 生命周期 + 产物归属 + 新能力判归测试；新增归属决策 / 改 skill 文档 / 模板 / CLI 指令文本时先查
- [raw/external/ anchor 写路径归 CLI](external-anchor-cli-owned.md) — 红线唯一例外：`llmw wiki external` 子命令持有 anchor + symlink；target 仓本体永不触碰；notes 走机械 scribe
- [agent 可见文本的引用白名单](agent-visible-text-reference-whitelist.md) — 只引命令名 / 输出自带字段 / 实例内可读路径；契约文档不重述 CLI 字段；面 9/10 守护
- [机械事实单源：代码注册表 + 自省](mechanical-truth-in-code.md) — finding 口径 = `lint --explain` 注册表、prose 禁镜像；语义进 AGENTS.md 模板；新增能力过下移试金石 + prose 预算制 + 定期语义审计

### 短条目（reminder，无需 why+how 展开）

**协作偏好与节奏**

- **用中文交流** — 全程中文，含回答里的小标题；别英文标题配中文正文的混排（术语/命令保留英文，如 `pre-push`）
- **测试优先级低** — prototype 阶段不写自动化测试，跑通后补；agent 不主动加测试代码
- **commit 直接在 master** — 不为每次 commit 开 feature 分支（单开发者无 PR 流，分支易忘合回 master）；override harness「默认分支先开分支」默认。仅用户明确要求 PR/分支隔离/多人协作时才开

**enter 后端选择**

- **enter_cli 选 agent CLI** — `workspace_local.toml#enter_cli` 白名单 3 值：`opencode`（默认，不解析模型 + instructions overlay 写 `<wiki>/opencode.json` 的 `instructions` 键）、`claude`（resolve+overlay 写 `<wiki>/.claude/settings.local.json`）、`qodercli`（裸启动，不写 overlay、不解析模型）。读取点 `enter.py`
- **opencode instructions overlay** — opencode 不解析 AGENTS.md 的 `@path` 引用（官方明确），用 `opencode.json` 的 `instructions` 字段替代（config.mdx "Instructions" 小节）。`overlay_opencode.py` **整文件 CLI 拥有**（byte-owned 配置，与 AGENTS.md byte-owned 模板同模型）：render 产 `{"$schema": ..., "instructions": effective_instructions(wiki_dir)}`，existing == expected → 幂等短路；existing 含 `{$schema, instructions}` 之外 key → stderr 逐名警告将被覆盖（可见性原则：不静默吞用户内容）；损坏 JSON → `OverlayFileUnparseable` 绝不 clobber。用户自定义 opencode 配置（permission/mcp/custom provider 等）走全局 `~/.config/opencode/opencode.json`，opencode 官方 config 合并机制保证项目级 > 全局、非冲突 key 合并。**遗留 secret 自动剥除**：旧 overlay_opencode 写过的含明文 apiKey 的 `provider.llmw` 块与悬空 `model: "llmw/..."` 键在下次 enter 随整文件覆盖消失（CLI 清理自有内容，非 clobber 用户配置），磁盘 secret 渐进消失。**gitignore 保留 `**/opencode.json` 行**——与 `.claude/settings*.json` 同模型：机器本地生成、每次 enter 幂等重建，不入 git；保留行同时兜底遗留含 secret 的老文件在剥除前被排除。**P1 防御过滤**：`effective_instructions(wiki_dir)` 把 `INSTRUCTION_FILES` 与 wiki 内实际存在的文件取交集——缺文件（破坏的 wiki）自动剔除，文件恢复后下次 enter 自动补回；`INSTRUCTION_FILES` 仍是 SSOT（与模板顶层 @import 一一对应，`wiki_fixtures.py:opencode-instructions-sync` 规则强制同步）。**@import 展开官方实测矩阵**：claude 原生 4 跳递归展开（docs.claude.com）；qodercli 原生递归展开（docs.qoder.com/cli/memory）；仅 opencode 不支持 → instructions 兜底。wiki 模板顶部"**必须 Read 兜底**" note 已删——改为机制中立一行描述（随文件自动加载，会话常驻）；workspace 模板同款 note 保留（workspace 层无 instructions 交付，opencode 裸跑 workspace 根仍需兜底）。**P2 定性**：fresh clone 后裸跑 opencode 缺 MEMORY/SCRIPTS 上下文的缝隙是"生成产物不入 git + enter 幂等物化"架构的自然推论——`llmw wiki enter` 是 session 唯一入口（tmux 开窗/打标/status 都依赖它），绕开 llmw 徒手裸跑本就反工作流，缝隙窗口极窄、现实中不发生，无需机制修补
- **enter 不传 --system-prompt** — claude/qodercli/opencode 都靠 `--add-dir` + cwd=wiki 让 agent 自读 `<wiki>/CLAUDE.md`/AGENTS.md；不显式注入避免双计入 + 多 backend 行为对齐
- **enter 走 tmux 窗口** — agent 开成当前 tmux session 的窗口，fire-and-forget；窗口名/四条件复用/tmux 外选路（恰一可见 session 直接开入，兜底名禁 `-`/`_` 头）/打标/status 判定链/孤儿清理/实施坑 → [enter-tmux-window-model](enter-tmux-window-model.md)

**model registry**

- **registry.name 只存裸 wire，[1m] 由 claude 路径视图化** — `name` 字段只存裸网关名（k3 / MiniMax-M3 / qwen3.7-max / glm-5.2），不带客户端特定的 `[1m]` 后缀。`[1m]`（Claude Code 1M context hint）由 `_claude_anthropic_model(name, context_window)` 按 `context_window>=1_000_000` 自动追加（对旧 toml 已带 `[1m]` 幂等）；opencode / qodercli 不经本路径（模型由后端内部自由切换）。
- **model.context_window 必填字段** — `ModelEntry` 加 `context_window: int`（无 fallback，缺字段抛 `InvalidModelField`，校验 `1<=n<=10_000_000`）；`model add --context-window=N` 非 TTY 必填；list/show 增列；claude overlay 按此推断 `[1m]` 视图。老仓库迁移：手动给每条 `[[models]]` 补真实上下文窗口值（minimax=1_000_000 等）。故意不做 fallback——schema 复杂度换用户可见性

**workspace / wiki 结构**

- **运行时配置拆出 workspace_local.toml（schema v2）** — 主机相关字段（`enter_cli`）放 gitignored `workspace_local.toml`（动机：跨主机共用 git 仓不互相覆盖 churn；无 secret 不 chmod）；workspace.toml 只剩结构数据，config 据 `LOCAL_KEYS` 路由 runtime key→local_store。**勿复活 `default_model`**（resolve 从不读它，"默认 model" 只由 registry `is_default` 单一表达）与 `enter_byobu`（删除理由见 AGENTS.md 数据模型节）。延续 [[model-ops-no-env-vars]]「配置走 toml 不走 env」纪律
- **CLI 有意比格式契约字面严** — `init` 对非空目录一律 `WorkspaceExists`（超集覆盖契约要求）；`wiki add` 走 `check_not_initialized` 校验 6 文件（契约字面仅 3，主动加严）
- **raw/ 默认子目录 + 格式契约↔CLI 解耦** — CLI fresh init 预建 `raw/{articles,assets,discussions}/`（用户要求，协作草稿层高频用），`raw/external/` 不预建（.gitignore 的 `raw/external/*` 吃掉 external/.gitkeep，`git check-ignore` 实测 IGNORED，预建对 clone 不可见）。判别尺度：格式契约定语义层（目录含义/纪律/provenance），不管实现层（预建哪些/怎么进 git）
- **external target 仓 agent 可读写（0.43.0 起）** — `raw/external/` symlink 指向的外部仓不受 raw/ 只读约束：agent 有读写权限，语料消费（ingest/query/lint/upgrade）以读为主、写需明确语境（用户要求 / 具体修改任务）；代码改动后走既有同步通道（用户确认 → 受影响 source 页重 ingest）。CLI 侧"永不触碰 target"边界不变（仅指 `llmw wiki external` 命令自身行为）

**SKILL 维护（2026-08-18 起同仓）**

- **两 SKILL 结构已对齐 yzr-skill-creator 模板（2026-09-26）** — skill 细节目录 `references/` → `ref/`（contract gate 路径构造 + fixtures 模式 + lint rule_ref 字符串同步）；节名用规范体 `输入与输出 / 执行原则 / 工作流`（变体后缀退役）；此后 verify 基线 = 0 ERROR / 0 WARN，再出红即真问题

- **两 SKILL 与 CLI 同仓（随 install.sh 一起分发）** — `yzr-llm-wiki-management` / `yzr-llm-workspace-management` 在本仓；install.sh 注册 `~/.agents/skills` 的 symlink 直接指向本仓、`~/.claude/skills`（存在时）建**链式 symlink 指向 `~/.agents/skills/<name>`**（uninstall.sh 的安全检查依赖这个链式形态），uninstall.sh 对称清理。
- **规范体只陈述现状规则** — AGENTS.md 模板 / SKILL.md 正文 / 本仓 AGENTS.md 写"记什么 / 不记什么"的规则本身；历史与辩护（"旧版必填…已废止""0.x.0 起取消""schema v2 起字段迁出 X"）归 commit message + upgrade-workflow「语义合并规则」，不进规范体。逐条辩护句会让每处维护都承担同步改写的成本（2026-08-17 清理 external anchor commit 字段时踩过）
- **改 skill 不手改 wiki/workspace 实例** — 模板变更经升级重渲染全量传播，实例 AGENTS.md 不手改（改了会与模板漂移 + 被下次重渲染覆盖）；`agents-md-template-sync` 报漂移属预期，等统一升级
- **skill / .py 引用 AGENTS.md 只用稳定锚点，禁节号 + bare shorthand** — wiki / workspace 两个 SKILL + llmw/**/*.py 都按此约束：模板内重组不应让引用侧断链，引用改用节名 / 字段名 / landmark 字符串。gate 面 7a 守护：扫 CONTRACT_MDS + llmw/**/*.py，抓 `AGENTS.md[^\w\n]{0,6}§N`（字面模式，禁节号引用）+ `(wiki|workspace)\s+§N`（bare shorthand，排除 wiki 名后缀如 `huawei_storage_wiki/wiki/`）；零误报：排除 `AGENTS.md + [`ref.md`](...) §二` 形式（§ 实指 ref.md）+ 模板自身"本文件 §N"自引用用"本文件"字面量不触发。gate 面 7b 断言 LANDMARKS 列表——数量与条目以 gate `LANDMARKS = [...]` 为准，本文不引具体数。**保证机制**：模板内部重组不动 landmark → skill/.py 零修改零感知；动 landmark → CI 红，同 commit 同步 skill 引用 + .py 字符串 + LANDMARKS 列表
- **目录结构变化走"单点改 + 漏改即红"** — 目录结构是 wiki format 本身（CLI 代码 + 模板 + fixtures + page-templates 共同定义），skill 教的是这些路径上的操作，零修改不可能也不该追求；追求漏改即红。gate 面 8 守护布局 token：扫 skill md 中 `wiki/<dir>/` token（regex `(?:^|[\s<>/])wiki/([a-z][a-z0-9]*)/`，前置分隔符排除 wiki 名后缀如 `storage_wiki/`，纯字母排除 wiki 名含分隔符如 `llm-systems`），`<dir>` 必须在 `llmw.content.wiki_lint.WIKI_SUBDIRS`（CLI SSOT）。改目录名时残留旧路径被当场点名。配合已有 gate：smoke_fixtures.py:46 强制 SKILL frontmatter == `llmw.WIKI_FORMAT_VERSION` 同 commit bump
- **改 CLI 外部契约必同步 skill + 模板 + 仓根文档** — 子命令 / flag / JSON 字段 / 终态词变更的 commit，必须同 commit grep `yzr-llm-wiki-management/` + `yzr-llm-workspace-management/` + `llmw/content/templates/**/*.md|*.txt` + 仓根 `AGENTS.md`/`CLAUDE.md`/`README.md` + `llmw/**/*.py` rule_ref/to_action 字符串并同步。**finding 名不再绑 skill prose**——口径唯一入口 = `llmw wiki lint --explain`（注册表 `llmw/content/findings.py`）；改 finding = 注册表加条目 + wiki_lint.py 发射同名（`tests/test_findings_registry.py` 双向穷举），prose 出现 severity 镜像格式由 gate 面 2 判红（2026-09-20 架构收口，见 [[mechanical-truth-in-code]]）。**绑定面清单与数量（命令 / finding / 终态字段 / rule_ref / landmark / 布局 token / rule_ref_fmt）以 gate `scripts/test/check_skill_cli_contract.py` 输出首行统计为准**，本文不引具体数字（一次 72→67→118 的变更证明活数字必腐坏）。skill / 模板 / 仓文档 / .py 与 CLI 同仓共演进，不建抽象间接层（skill 的存在理由是给 agent 精确可执行命令，间接层降执行质量）；只绑 CLI 外部契约。`.py` rule_ref 值指向 skill 文档必须带 `.md` 扩展名（gate 面 8 守护）；「节名」引用经 gate 面 3 名称锚点校验——须唯一命中一个标题，0 命中 = 死指针、>1 = 歧义（节号引用已于 2026-09-19 全仓退役，见下条）。gate 全量检查面兜底语法面 + 模板依赖 + 布局 token + rule_ref 格式（README 风格的 `[--X\|-Y]` OR 写法也识别；裸 semver 面豁免 `wiki_format_version:` / `workspace_format_version:` 键行 + `upgrade-workflow.md` 整文件）；语义面（行为描述如"只扫不修"）gate 管不到，靠本纪律人工保证。有意不扫 `MEMORY/`（历史命令 + 反例必误报）与 `tests/`（可执行测试自带 loud failure）
- **全仓模板节号指针已清剿（2026-08-20）** — workspace_fixtures.py ~12 处 "§六「当前配置」" 全部错指（workspace 模板当前配置实为 §七），证明节号引用是脆弱隐式依赖；同步清剿 wiki_fixtures.py / wiki_write.py / wiki_lint.py / upgrade_workspace.py / wiki/enter.py / workspace/manager.py / models/*.py / cli.py / templates / fixtures README 的 §六/§七 引用→名称锚点，外加模板自引用 8 处。悬空设计文档指针（doc/skeleton-engine-design.md + doc/design/* 已删，指针全是死引用）删除，保留内联实质文字；session-visibility-design.md 的 §2.x 引用当时保留（该 doc 2026-09-19 删除，R 编号与 § 指针同批清剿）。WIKI_FORMAT_VERSION 0.39→0.40 / WORKSPACE_FORMAT_VERSION 0.9→0.10（模板字节变更按 309b9e8 惯例 bump）
- **skill 域引用统一「节名」锚点、标题去编号（2026-09-19）** — 把既有纪律"引用 AGENTS.md 禁节号"推广到 skill 域全部引用：7 个 wiki skill 文档 + workspace SKILL 标题去掉一/二/三与 6.1 式编号，跨文件引用一律 `<file>.md「节名」`（三种邻接形式：名在链接内 / 链接闭合后 / 裸文本；名须唯一命中标题，gate 面 3 校验），py rule_ref / 注释 / tests docstring 同步。动因：节号插入即整体漂移（同日删 lint-checklist §五、加 page-templates §四、清 query-workflow 残留 §六 均实证代价）。gate 面 7c 禁 §N 防回潮（OKF §9 等外部规范引用豁免）；面 7d 兜底裸「」残留节号（`「5. Upgrade」` 类无 basename 前缀形态迁移漏网 2 处，7a/7c/RULE_REF_RE 均扫不到——已证盲区）。指针语义记在引用处而非图例：强制读随行内标记落在工作流指针（如「（执行前必读）」，同 yzr-skill-creator "先 Read X 再动手"式）；裸 `见` = 背景参考；`canonical 见` 是 SSOT 标记、不表读层级。原 wiki SKILL.md「文档引用约定」图例节已删（2026-09-25）：图例离它保护的决策点太远，行内标记在决策点直接生效。官方 >100 行参考文件加 TOC 的建议评估后**不采纳**：引用带节名锚点已解决定位，TOC 反成新的无守护漂移源（与刚退役的节号同类）；待观察到实际迷路信号再加。标题不再编号——加节随便加、引用零改
- **reference / SKILL 文档不维护手工 TOC / `#fragment`** — agent 靠节名 grep 导航，GitHub 自带大纲按钮；手工 TOC 与 fragment 是漂移成本而非文档价值（`ingest-workflow.md` 旧版的 `#生命周期规则llm-必读` fragment 是活证据，2026-08 修复为文件级链接；CI 也无 anchor_health 闸——裸奔）。跨文件引用只到文件级链接 + 文字节名（`[文字](file.md)` 或纯文本 `file.md「节名」`），CLI 输出字符串一律纯文本（终端里 url 是噪音且 `ref/` 从 wiki cwd 不可解析）
- **只理解当前格式，不保留旧版本自愈路径** — 系统（lint / upgrade / fixtures / skill）只服务当前 format；历史布局（0.16 之前 anchor JSON / 老 CLAUDE.md 正文 / 老 §六 散文行 / 0.19 之前 type: memory 迁移等）一律不提供迁移路径。历史布局从 git 考古挖出 → 用户人工处理或走统一升级。理由：2026-08 后 v1 schema 已硬退役（load v1 直接拒）作为先例；单用户使用无需对考古场景兜底；保留迁移 machinery 的维护成本 > 实际命中概率
- **命令表面 SSOT = llmw.cli.build_parser() 单一 argparse 树** — 模块 standalone 入口（`python -m llmw.content.*` + 各模块 main/__main__）已全部退役：内容模块是纯业务库（`run(wiki_root, **params)` 显式参数入口，run_upgrade 模式推广）；`wiki write` 子树经 `wiki_write.build_subparsers` 组合进 cli 树（无 REMAINDER 透传）。加 flag 只改 cli.py 一处（write 改 build_subparsers 一处）；`LLM_WIKI_ROOT` env fallback 移入 `_resolve_content_root`。**带值 flag 全局强制等号形式**（`--flag=VALUE`，SpaceFormNotAllowed）——skill 文档命令一律等号写法，gate 有风格检查兜底
- **两 SKILL 触发域不对称（设计使然）** — wiki skill 仅在 cwd 为 wiki 根（含 `wiki_metadata.toml`）时触发（description gating 软约束；"初始搭建"覆盖 / "想搭一个 wiki"触发词已移除——`llmw wiki add` 接管，skill 无 bootstrap 职责）；workspace skill 相反，全局安装且**必须**全局可达（跨 wiki 问答可从任意目录发起，甚至可从某个 wiki 内目录发起，属合法路径；其 不适用段已写明单 wiki 操作走 wiki skill）。非对称是两 skill 的本质差异，不是疏漏；per-wiki symlink 物理隔离方案已备过但判复杂（qodercli 项目级 skill 约定未证实 + 安装矩阵变大），软约束够用，观察到误触发再升级
- **真实 workspace 由用户统一升级，agent 不碰** — `~/yzr-llm-wiki-workspace` 的 wiki 实例 upgrade / enter / drift 清理一律不主动执行（模板变更报 `agents-md-template-sync` drift 属预期）；验证一律走隔离沙盒 + `--workspace=.`；用户声明稳定后自行统一升级

## 维护规则

追加末尾 / 定期收敛 / 不删既有（被代码吸收可删，git 可恢复）/ frontmatter 必填 / `[[slug]]`
互链——canonical 见 [memory-entry-conventions](memory-entry-conventions.md)。

---

## CI 实战沉淀

- **push 前必跑 CI 三件套** — `ruff check .` + `ruff format --check .` + `python3 scripts/test/smoke_fixtures.py`，本地等价 CI 4 job（lint / test py3.7 / test py3.11 / fixtures-smoke），跑过再 push。两 SKILL 目录均已不含脚本（全部迁入 `llmw/content/`，其 ruff.toml 是仓内唯一一份）
