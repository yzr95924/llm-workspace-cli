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

**外部调研 backlog**

- [cc-switch-cli 可借鉴功能](cc-switch-inspire.md) — doctor env 冲突检查 / model check / wiki sessions+resume / 临时配置启动；附源码出处与不借鉴清单

### 短条目（reminder，无需 why+how 展开）

无需独立文件（2026-08-12 中等清理：29→15 条，驳正链合并 + 过程细节压缩到结论 + 判别尺度）：

**协作偏好与节奏**

- **用中文交流** — 全程中文，含回答里的小标题；别英文标题配中文正文的混排（术语/命令保留英文，如 `pre-push`）
- **测试优先级低** — prototype 阶段不写自动化测试，跑通后补；agent 不主动加测试代码

**enter 后端选择**

- **enter_cli 选 agent CLI** — `workspace_local.toml#enter_cli` 白名单 3 值：`claude`（默认，resolve+overlay 写 `<wiki>/.claude/settings.local.json`）、`qodercli`（裸启动，不写 overlay、不解析 model）、`opencode`（resolve+overlay 写 `<wiki>/opencode.json`，见下条）。读取点 `enter.py`
- **opencode overlay 配置** — `overlay_opencode.py` 渲染 `<wiki>/opencode.json`（own `provider.llmw` 整对象 + 顶层 `model`；apiKey 明文 + chmod 600），与 claude 同族走 resolve+overlay。npm 包固定 `@ai-sdk/anthropic`（OpenAI 协议网关改 `_NPM_PACKAGE` 一行）。**baseURL 必须 +`/v1`**（`_ai_sdk_base_url`：Claude Code 约定 `{base}/v1/messages` vs AI SDK 约定 `{baseURL}/messages`，直填 404）。limit 块 context/output **成对必填**（只写 context 启动拒载）；context 直读 `model.context_window`，output `_MAX_OUTPUT=131_072` 习惯级（待 max_output 字段引入）。cmd `opencode <wiki_dir>` 自读 AGENTS.md；无 habit template（CLAUDE_CODE_* 为 claude 专属）。老文件靠 `_is_up_to_date` 整对象比对下次 enter 自动升级。workspace .gitignore 另加 `**/opencode.json`
- **enter 不传 --system-prompt** — claude/qodercli/opencode 都靠 `--add-dir` + cwd=wiki 让 agent 自读 `<wiki>/CLAUDE.md`/AGENTS.md；不显式注入避免双计入 + 多 backend 行为对齐
- **enter_byobu 走 byobu 窗口** — `workspace_local.toml#enter_byobu=true`（`_parse_bool` 严格小写，避 `bool("false")` 陷阱）后 `wiki enter` 在 byobu 固定 session `llm_workspace`（`byobu.py:_BYOBU_SESSION`）按 wiki 名开窗口，fire-and-forget（窗口建成返回 0，退出码不来自 agent），同名窗口 select 复用。一律 `byobu-tmux`（强制 tmux backend）；target 用 `#{window_id}`（防纯数字 wiki 名歧义）；agent argv[0] 先 `shutil.which`；`new-window -n` 锁名；`LLM_WIKI_ROOT` 走 `-e` 注入。引导三分支：同 session 切焦 / 异 session switch-client / 不在 tmux `byobu attach`。仅 tmux backend；remove 不清窗口。spawn 收口 `enter.py:_spawn`

**model registry**

- **registry.name 只存裸 wire，[1m] 由 backend 视图化** — `name` 字段只存裸网关名（k3 / MiniMax-M3 / qwen3.7-max / glm-5.2），不带客户端特定的 `[1m]` 后缀。`[1m]`（Claude Code 1M context hint）各 backend 自行生成：claude `_claude_anthropic_model(name, context_window)` 按 `context_window>=1_000_000` 自动追加（对旧 toml 已带 `[1m]` 幂等）；opencode 不写展示名（缺省用 key）、`_gateway_model_id` 内部 `name.split("[",1)[0]` 剥后缀做 wire 兜底（四网关实测 send 须裸名：qwen/glm 400 拒、kimi 401、minimax 收——小探针测不出，须真实 max_tokens）；qodercli 不读 overlay。用户 4 条 model 已全去 `[1m]`
- **model.context_window 必填字段** — `ModelEntry` 加 `context_window: int`（无 fallback，缺字段抛 `InvalidModelField`，校验 `1<=n<=10_000_000`）；`model add --context-window=N` 非 TTY 必填；list/show 增列；opencode overlay 直读渲染 `limit.context`。老仓库迁移：手动给每条 `[[models]]` 补真实上下文窗口值（minimax=1_000_000 等）。故意不做 fallback——schema 复杂度换用户可见性

**workspace / wiki 结构**

- **运行时配置拆出 workspace_local.toml（schema v2）** — 主机相关字段（`enter_cli`/`enter_byobu`）从 git 跟踪的 workspace.toml 迁到 gitignored `workspace_local.toml`（无 secret 不 chmod）；动机是跨主机共用 git 仓不互相覆盖 churn。workspace.toml **v1→v2**（只剩结构数据），`store.load()` 自愈迁移（`_migrate_v1_to_v2` 幂等：抽 key 写 local merge 不覆盖 → 确保 gitignore 含新行 → 重写 v2）。config 据 `LOCAL_KEYS` 路由 runtime key→local_store。`default_model` **已彻底删除**（搬地方只是换处误导——resolve 路径从不读它；"默认 model" 只由 registry `is_default` 单一表达）。延续 [[model-ops-no-env-vars]]「配置走 toml 不走 env」纪律
- **CLI 实现 vs spec 字面的合理偏差** — (a) `init` 对非空目录一律 `WorkspaceExists`（超集覆盖 §12）；(b) `wiki add` 走 `check_not_initialized` 校验 6 文件（§8 字面仅 3，主动加严）；(c) `yzr-SKILL/.../SKILL.md` 5 处沿用 `<wiki>/wiki/MEMORY/>` 旧路径（应 `<wiki>/MEMORY/>`），llmw 落盘不受影响但 workspace scan 会扫空目录——待 SKILL 维护方修
- **workspace .gitignore managed block** — `_ensure_workspace_gitignore`（`workspace/manager.py`）现写 4 行：spec §10 v0.6.1 的 3 行（`workspace_models.toml` + `**/.claude/settings*.json` + `**/.qoder/settings*.json`）+ llmw 自有 `.llmw-trash/`（wiki remove --purge 备份目录）。老 workspace 升级：函数比对 block 不等就替换。演进史（多 1 行 → 0.5.0 漏 .qoder → 0.6.0/0.6.1 加宽 settings*.json）见 git log
- **wiki-spec §6 vs §13.4 已一致** — 两节现均为 `!raw/external/.symlink-anchor.toml`（TOML 形态），fixture 一致。`.json` 仅残留 §13 废弃声明历史语境。另：spec 侧仍有 prose 陈旧（§1 .gitkeep 矛盾 / §3§4 字段数不符等）不影响 CLI 产物（fixture 是金标准），待 SKILL owner 修
- **workspace-spec 0.7.0 对齐** — CLI 唯一动作 `WORKSPACE_SPEC_VERSION` bump 0.6.2→0.7.0（§17 升级迁移机制 + AGENTS.md 模板机读表；§17 明文 CLI 不参与升级，全在 skill 侧）。模板无新占位符，渲染字节兼容。老 workspace 走 SKILL.md §6 Migrate，CLI 永不提供迁移命令
- **raw/ 默认子目录 + spec↔CLI 解耦** — CLI fresh init 现预建 `raw/{articles,assets,discussions}/`（用户要求，spec §15 协作草稿层高频用）；discussions/.gitkeep 不被 .gitignore 排除。**raw/external/ 不预建**：.gitignore 的 `raw/external/*` 吃掉 external/.gitkeep（`git check-ignore` 实测 IGNORED），预建对 clone 不可见——调试手段：预建 raw 子目录前先 `git check-ignore -v raw/<sub>/.gitkeep` 验证。借这次做 **spec↔CLI 解耦**：yzr-SKILL `wiki-spec.md` 改 5 处（§1/§7 step1+step3/§15），把"预建哪些 raw 子目录 + .gitkeep 策略"改为「实现自由」，只留正确性约束（raw/ 至少有 tracked 内容否则 raw-modified lint 0 命中）+ discussions 语义。**版本号不 bump**（语义未变）。判别尺度（[[spec-semantics-vs-implementation-boundary]]）：spec 管语义层（目录含义/纪律/provenance），不管实现层（预建哪些/怎么进 git）

**submodule 纪律**

- **yzr-SKILL 改动去 /root/yzr-SKILL** — yzr-SKILL 是 submodule，本仓 `yzr-SKILL/` checkout 的改动不 commit 会被 `git submodule update` 覆盖。用户的独立 working repo 在 `/root/yzr-SKILL`（同 remote 同 HEAD）——改 yzr-SKILL 内容一律去那里，不在本仓 submodule checkout 里改（曾误改 spec，已 `git checkout` 撤回 + 迁移纠正）

## 维护规则

- **追加末尾**——新条目按 git 时间序追加
- **定期收敛**——驳正链合并到最终结论（删"原条目说 X 实际 Y"中间叙事）；过程细节（curl 实测 / 调试二分 / 逐行行号）压缩到结论 + 判别尺度；短条目回归"一句话 reminder"，超长的抽完整 `.md` 或精简。2026-08-12 中等清理：短条目 29→15 条、27KB→~11KB
- **不删既有**——踩坑沉淀；内容有误用追加驳正方式（定期收敛时可合并驳正链，与"不删"的张力由收敛规则调和）
- **frontmatter 三项必填**：`name` / `description` / `metadata.type`（值 ∈ `project | feedback | reference | user`）
- **条目之间用 `[[slug]]` 互链**——读一条可跟随关联链接定位相关记忆

完整约定见 [memory-entry-conventions](memory-entry-conventions.md)；持久化策略见 [memory-persistence-policy](memory-persistence-policy.md)。

---

## CI 实战沉淀

- **push 前必跑 CI 三件套** — `ruff check .` + `ruff format --check .` + `python3 scripts/test/smoke_fixtures.py`，本地等价 CI 4 job（lint / test py3.7 / test py3.11 / fixtures-smoke），跑过再 push。yzr-SKILL submodule 代码由该仓维护、llmw 仅消费，lint 误伤（F401/UP032）用 `pyproject.toml:[tool.ruff] extend-exclude=["yzr-SKILL"]` 全局排除（不放进 workflow 命令行）
