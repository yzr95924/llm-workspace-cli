# MEMORY 索引

跨会话需要持久化的"为什么 + 边界"规则。本目录每个文件承载一条独立记忆。

> **本文件是项目级规则的唯一真源。** Claude 会话级 memory（`~/.claude/projects/.../memory/`）
> 只放指向本文件的指针，不再持有内容副本——避免随代码仓迁移 / 协作时失同步。

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
- [三方边界关系图](boundary-map.md) — 用户 + CLI + workspace skill + wiki skill 四方依赖方向 + 生命周期 + 产物归属指针 + 新能力判归 6 步有序测试；新增归属决策时先查

### 短条目（reminder，无需 why+how 展开）

无需独立文件：

**协作偏好与节奏**

- **用中文交流** — 全程中文，含回答里的小标题；别英文标题配中文正文的混排（术语/命令保留英文，如 `pre-push`）
- **测试优先级低** — prototype 阶段不写自动化测试，跑通后补；agent 不主动加测试代码
- **commit 直接在 master** — 不为每次 commit 开 feature 分支（单开发者无 PR 流，分支易忘合回 master）；override harness「默认分支先开分支」默认。仅用户明确要求 PR/分支隔离/多人协作时才开

**enter 后端选择**

- **enter_cli 选 agent CLI** — `workspace_local.toml#enter_cli` 白名单 3 值：`claude`（默认，resolve+overlay 写 `<wiki>/.claude/settings.local.json`）、`qodercli`（裸启动，不写 overlay、不解析 model）、`opencode`（resolve+overlay 写 `<wiki>/opencode.json`，见下条）。读取点 `enter.py`
- **opencode overlay 配置** — `overlay_opencode.py` 渲染 `<wiki>/opencode.json`（own `provider.llmw` 整对象 + 顶层 `model`；apiKey 明文 + chmod 600），与 claude 同族走 resolve+overlay。npm 包固定 `@ai-sdk/anthropic`（OpenAI 协议网关改 `_NPM_PACKAGE` 一行）。**baseURL 必须 +`/v1`**（`_ai_sdk_base_url`：Claude Code 约定 `{base}/v1/messages` vs AI SDK 约定 `{baseURL}/messages`，直填 404）。limit 块 context/output **成对必填**（只写 context 启动拒载）；context 直读 `model.context_window`，output `_MAX_OUTPUT=131_072` 习惯级（待 max_output 字段引入）。cmd `opencode <wiki_dir>` 自读 AGENTS.md；无 habit template（CLAUDE_CODE_* 为 claude 专属）。老文件靠 `_is_up_to_date` 整对象比对下次 enter 自动升级。workspace .gitignore 另加 `**/opencode.json`
- **enter 不传 --system-prompt** — claude/qodercli/opencode 都靠 `--add-dir` + cwd=wiki 让 agent 自读 `<wiki>/CLAUDE.md`/AGENTS.md；不显式注入避免双计入 + 多 backend 行为对齐
- **enter 走 tmux 窗口（W' 模型）** — agent 开成当前 tmux session 的窗口，fire-and-forget；窗口名/四条件复用/打标/status 判定链/R8 孤儿清理/实施坑 → [enter-tmux-window-model](enter-tmux-window-model.md)

**model registry**

- **registry.name 只存裸 wire，[1m] 由 backend 视图化** — `name` 字段只存裸网关名（k3 / MiniMax-M3 / qwen3.7-max / glm-5.2），不带客户端特定的 `[1m]` 后缀。`[1m]`（Claude Code 1M context hint）各 backend 自行生成：claude `_claude_anthropic_model(name, context_window)` 按 `context_window>=1_000_000` 自动追加（对旧 toml 已带 `[1m]` 幂等）；opencode 不写展示名（缺省用 key）、`_gateway_model_id` 内部 `name.split("[",1)[0]` 剥后缀做 wire 兜底（四网关实测 send 须裸名：qwen/glm 400 拒、kimi 401、minimax 收——小探针测不出，须真实 max_tokens）；qodercli 不读 overlay。
- **model.context_window 必填字段** — `ModelEntry` 加 `context_window: int`（无 fallback，缺字段抛 `InvalidModelField`，校验 `1<=n<=10_000_000`）；`model add --context-window=N` 非 TTY 必填；list/show 增列；opencode overlay 直读渲染 `limit.context`。老仓库迁移：手动给每条 `[[models]]` 补真实上下文窗口值（minimax=1_000_000 等）。故意不做 fallback——schema 复杂度换用户可见性

**workspace / wiki 结构**

- **运行时配置拆出 workspace_local.toml（schema v2）** — 主机相关字段（`enter_cli`）放 gitignored `workspace_local.toml`（动机：跨主机共用 git 仓不互相覆盖 churn；无 secret 不 chmod）；workspace.toml 只剩结构数据，`store.load()` v1→v2 自愈迁移幂等，config 据 `LOCAL_KEYS` 路由 runtime key→local_store。**勿复活 `default_model`**（resolve 从不读它，"默认 model" 只由 registry `is_default` 单一表达）与 `enter_byobu`（删除理由见 AGENTS.md 数据模型节）。延续 [[model-ops-no-env-vars]]「配置走 toml 不走 env」纪律
- **CLI 有意比格式契约字面严** — `init` 对非空目录一律 `WorkspaceExists`（超集覆盖契约要求）；`wiki add` 走 `check_not_initialized` 校验 6 文件（契约字面仅 3，主动加严）
- **raw/ 默认子目录 + 格式契约↔CLI 解耦** — CLI fresh init 预建 `raw/{articles,assets,discussions}/`（用户要求，协作草稿层高频用），`raw/external/` 不预建（.gitignore 的 `raw/external/*` 吃掉 external/.gitkeep，`git check-ignore` 实测 IGNORED，预建对 clone 不可见）。判别尺度：格式契约定语义层（目录含义/纪律/provenance），不管实现层（预建哪些/怎么进 git）

**SKILL 维护（2026-08-18 起同仓）**

- **两 SKILL 与 CLI 同仓（随 install.sh 一起分发）** — `yzr-llm-wiki-management` / `yzr-llm-workspace-management` 在本仓；install.sh 注册 `~/.agents/skills` 的 symlink 直接指向本仓、`~/.claude/skills`（存在时）建**链式 symlink 指向 `~/.agents/skills/<name>`**（uninstall.sh 的安全检查依赖这个链式形态），uninstall.sh 对称清理。
- **规范体只陈述现状规则** — AGENTS.md 模板 / SKILL.md 正文 / 本仓 AGENTS.md 写"记什么 / 不记什么"的规则本身；历史与辩护（"旧版必填…已废止""0.x.0 起取消""schema v2 起字段迁出 X"）归 commit message + upgrade-workflow §六，不进规范体。逐条辩护句会让每处维护都承担同步改写的成本（2026-08-17 清理 external anchor commit 字段时踩过）
- **改 skill 不手改 wiki/workspace 实例** — 模板变更经升级重渲染全量传播，实例 AGENTS.md 不手改（改了会与模板漂移 + 被下次重渲染覆盖）；`agents-md-template-sync` 报漂移属预期，等统一升级
- **wiki skill 文本不节号引用 AGENTS.md 纪律** — 只在 wiki 目录触发，`CLAUDE.md` @import 自动加载，重抄 = 双源漂移面；skill 只按小节标题词（"`raw/external/` 节"）引用或完全不引。例外：§七（Wiki Format 版本）是 CLI 解析契约（`wiki_lint.py check_format_version` 按此行解析），属于代码级接口而非文档导航
- **改 CLI 外部契约必同步 skill + 模板 + 仓根文档** — 子命令 / flag / finding 名 / JSON 字段 / 终态词变更的 commit，必须同 commit grep `yzr-llm-wiki-management/` + `yzr-llm-workspace-management/` + `llmw/content/templates/**/*.md|*.txt` + 仓根 `AGENTS.md`/`CLAUDE.md`/`README.md` 并同步（当前绑定面：命令 157 处 + finding 36+42 + 终态字段 7 + rule_ref 60）。skill / 模板 / 仓文档与 CLI 同仓共演进，不建抽象间接层（skill 的存在理由是给 agent 精确可执行命令，间接层降执行质量）；只绑 CLI 外部契约，不绑模块内部路径（`llmw.content.*`），模块路径属实现布局、拆模块即静默失效。语法面（命令/flag/风格/跨行断命令）由 `scripts/test/check_skill_cli_contract.py` CI gate 兜底（扫描域含模板 + 仓文档；README 风格的 `[--X\|-Y]` OR 写法也识别）；语义面（行为描述如"只扫不修"）gate 管不到，靠本纪律人工保证。有意不扫 `MEMORY/`（历史命令 + 反例必误报）与 `tests/`（可执行测试自带 loud failure）
- **命令表面 SSOT = llmw.cli.build_parser() 单一 argparse 树** — 模块 standalone 入口（`python -m llmw.content.*` + 各模块 main/__main__）已全部退役：内容模块是纯业务库（`run(wiki_root, **params)` 显式参数入口，run_upgrade 模式推广）；`wiki write` 子树经 `wiki_write.build_subparsers` 组合进 cli 树（无 REMAINDER 透传）。加 flag 只改 cli.py 一处（write 改 build_subparsers 一处）；`LLM_WIKI_ROOT` env fallback 移入 `_resolve_content_root`。**带值 flag 全局强制等号形式**（`--flag=VALUE`，SpaceFormNotAllowed）——skill 文档命令一律等号写法，gate 有风格检查兜底
- **两 SKILL 触发域不对称（设计使然）** — wiki skill 仅在 cwd 为 wiki 根（含 `wiki_metadata.toml`）时触发（description gating 软约束；"初始搭建"覆盖 / "想搭一个 wiki"触发词已移除——`llmw wiki add` 接管，skill 无 bootstrap 职责）；workspace skill 相反，全局安装且**必须**全局可达（跨 wiki 问答可从任意目录发起，甚至可从某个 wiki 内目录发起，属合法路径；其 不适用段已写明单 wiki 操作走 wiki skill）。非对称是两 skill 的本质差异，不是疏漏；per-wiki symlink 物理隔离方案已备过但判复杂（qodercli 项目级 skill 约定未证实 + 安装矩阵变大），软约束够用，观察到误触发再升级
- **真实 workspace 由用户统一升级，agent 不碰** — `~/yzr-llm-wiki-workspace` 的 wiki 实例 upgrade / enter / drift 清理一律不主动执行（模板变更报 `agents-md-template-sync` drift 属预期）；验证一律走隔离沙盒 + `--workspace=.`；用户声明稳定后自行统一升级

## 维护规则

- **追加末尾**——新条目按 git 时间序追加
- **定期收敛**——驳正链合并到最终结论（删"原条目说 X 实际 Y"中间叙事）；过程细节（curl 实测 / 调试二分 / 逐行行号）压缩到结论 + 判别尺度；短条目回归"一句话 reminder"，超长的抽完整 `.md` 或精简
- **不删既有**——踩坑沉淀；内容有误用追加驳正方式（定期收敛时可合并驳正链，与"不删"的张力由收敛规则调和）；**例外**：已被代码/文档吸收或过时的事实条目可删（git 可恢复）
- **frontmatter 三项必填**：`name` / `description` / `metadata.type`（值 ∈ `project | feedback | reference | user`）
- **条目之间用 `[[slug]]` 互链**——读一条可跟随关联链接定位相关记忆

完整约定见 [memory-entry-conventions](memory-entry-conventions.md)。

---

## CI 实战沉淀

- **push 前必跑 CI 三件套** — `ruff check .` + `ruff format --check .` + `python3 scripts/test/smoke_fixtures.py`，本地等价 CI 4 job（lint / test py3.7 / test py3.11 / fixtures-smoke），跑过再 push。两 SKILL 目录均已不含脚本（全部迁入 `llmw/content/`，其 ruff.toml 是仓内唯一一份）
