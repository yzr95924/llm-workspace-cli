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

- [MEMORY 条目约定](memory-entry-conventions.md) — 判别两类条目 / 索引格式 / 写入纪律 / 与个人 memory 关系；建新条目必读
- [记忆持久化策略](memory-persistence-policy.md) — 项目级记忆写仓库内 `MEMORY/`，跟随代码仓演进，不写个人 memory 目录

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

**SKILL 与 spec（2026-08-18 起两 SKILL 同仓）**

- [spec 版本号 bump：单仓三方对齐](spec-version-bump-single-repo.md) — SKILL.md frontmatter / lint_wiki.py CURRENT_WIKI_SPEC / llmw/__init__.py 同 commit 对齐；submodule 指针跨仓步骤已随迁移消失
- [wiki-spec ↔ workspace-spec type enum 耦合](wiki-workspace-spec-type-coupling.md) — 改 wiki-spec §9 type 必须同步查 workspace-spec §13，否则"复用"引用悬空
- [wiki/workspace 纪律文件 AGENTS.md SSOT + CLAUDE.md 薄壳](wiki-spec-0-11-agents-md-ssot.md) — 0.11.0/0.4.0 起纪律 SSOT 改 AGENTS.md + 薄壳；两 spec 对称，改 SSOT 引用要同步两 skill

### 短条目（reminder，无需 why+how 展开）

无需独立文件（2026-08-12 中等清理：29→15 条，驳正链合并 + 过程细节压缩到结论 + 判别尺度；
2026-08-19：删 cc-switch-inspire 调研档 + 3 条已吸收/一次性记录短条目，死链 5 处清零）：

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

- **registry.name 只存裸 wire，[1m] 由 backend 视图化** — `name` 字段只存裸网关名（k3 / MiniMax-M3 / qwen3.7-max / glm-5.2），不带客户端特定的 `[1m]` 后缀。`[1m]`（Claude Code 1M context hint）各 backend 自行生成：claude `_claude_anthropic_model(name, context_window)` 按 `context_window>=1_000_000` 自动追加（对旧 toml 已带 `[1m]` 幂等）；opencode 不写展示名（缺省用 key）、`_gateway_model_id` 内部 `name.split("[",1)[0]` 剥后缀做 wire 兜底（四网关实测 send 须裸名：qwen/glm 400 拒、kimi 401、minimax 收——小探针测不出，须真实 max_tokens）；qodercli 不读 overlay。用户 4 条 model 已全去 `[1m]`
- **model.context_window 必填字段** — `ModelEntry` 加 `context_window: int`（无 fallback，缺字段抛 `InvalidModelField`，校验 `1<=n<=10_000_000`）；`model add --context-window=N` 非 TTY 必填；list/show 增列；opencode overlay 直读渲染 `limit.context`。老仓库迁移：手动给每条 `[[models]]` 补真实上下文窗口值（minimax=1_000_000 等）。故意不做 fallback——schema 复杂度换用户可见性

**workspace / wiki 结构**

- **运行时配置拆出 workspace_local.toml（schema v2）** — 主机相关字段（`enter_cli`）放 gitignored `workspace_local.toml`（动机：跨主机共用 git 仓不互相覆盖 churn；无 secret 不 chmod）；workspace.toml 只剩结构数据，`store.load()` v1→v2 自愈迁移幂等，config 据 `LOCAL_KEYS` 路由 runtime key→local_store。**勿复活 `default_model`**（resolve 从不读它，"默认 model" 只由 registry `is_default` 单一表达）与 `enter_byobu`（删除理由见 AGENTS.md 数据模型节）。延续 [[model-ops-no-env-vars]]「配置走 toml 不走 env」纪律
- **CLI 有意比 spec 字面严** — `init` 对非空目录一律 `WorkspaceExists`（超集覆盖 §12）；`wiki add` 走 `check_not_initialized` 校验 6 文件（§8 字面仅 3，主动加严）
- **raw/ 默认子目录 + spec↔CLI 解耦** — CLI fresh init 预建 `raw/{articles,assets,discussions}/`（用户要求，spec §15 协作草稿层高频用），`raw/external/` 不预建（.gitignore 的 `raw/external/*` 吃掉 external/.gitkeep，`git check-ignore` 实测 IGNORED，预建对 clone 不可见）。判别尺度：spec 管语义层（目录含义/纪律/provenance），不管实现层（预建哪些/怎么进 git）

**SKILL 维护（2026-08-18 起同仓）**

- **两 SKILL 与 CLI 同仓（随 install.sh 一起分发）** — `yzr-llm-wiki-management` / `yzr-llm-workspace-management` 自 yzr-SKILL 迁入（斩断历史），改 skill 直接在本仓改、commit 随 CLI 走；**npx 分发已退役（2026-08-19）**，install.sh 注册 `~/.agents/skills` 的 symlink 直接指向本仓、`~/.claude/skills`（存在时）建**链式 symlink 指向 `~/.agents/skills/<name>`**（uninstall.sh 的安全检查依赖这个链式形态），uninstall.sh 对称清理。submodule 已删除，原「yzr-SKILL 改动去 /root/yzr-SKILL」纪律废止
- **规范体只陈述现状规则** — spec / AGENTS.md 模板 / SKILL.md 正文 / 本仓 AGENTS.md 写"记什么 / 不记什么"的规则本身；历史与辩护（"旧版必填…已废止""0.x.0 起取消""schema v2 起字段迁出 X"）归 commit message + migrate-workflow §六，不进规范体。逐条辩护句会让每处维护都承担同步改写的成本（2026-08-17 清理 external anchor commit 字段时踩过）
- **改 skill 不手改 wiki/workspace 实例** — 模板变更经升级重渲染全量传播，实例 AGENTS.md 不手改（改了会与模板漂移 + 被下次重渲染覆盖）；`agents-md-template-sync` 报漂移属预期，等统一升级

## 维护规则

- **追加末尾**——新条目按 git 时间序追加
- **定期收敛**——驳正链合并到最终结论（删"原条目说 X 实际 Y"中间叙事）；过程细节（curl 实测 / 调试二分 / 逐行行号）压缩到结论 + 判别尺度；短条目回归"一句话 reminder"，超长的抽完整 `.md` 或精简。2026-08-12 中等清理：短条目 29→15 条、27KB→~11KB
- **不删既有**——踩坑沉淀；内容有误用追加驳正方式（定期收敛时可合并驳正链，与"不删"的张力由收敛规则调和）
- **frontmatter 三项必填**：`name` / `description` / `metadata.type`（值 ∈ `project | feedback | reference | user`）
- **条目之间用 `[[slug]]` 互链**——读一条可跟随关联链接定位相关记忆

完整约定见 [memory-entry-conventions](memory-entry-conventions.md)；持久化策略见 [memory-persistence-policy](memory-persistence-policy.md)。

---

## CI 实战沉淀

- **push 前必跑 CI 三件套** — `ruff check .` + `ruff format --check .` + `python3 scripts/test/smoke_fixtures.py`，本地等价 CI 4 job（lint / test py3.7 / test py3.11 / fixtures-smoke），跑过再 push。两 SKILL 脚本随仓纳入 ruff（各目录 `ruff.toml` 行宽 120 + E/W/F/I/B/UP 规则族）
