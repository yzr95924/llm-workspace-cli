---
name: cc-switch-inspire
description: 调研 ~/cc-switch-cli 归档的可借鉴功能 backlog——doctor env 冲突检查 / model check 连通性 / wiki sessions（按 wiki 过滤 + resume）/ start 式临时配置启动；附 cc-switch 源码 file:line 出处与明确不借鉴清单
metadata:
  type: project
---

# cc-switch-cli 可借鉴功能归档

调研对象：`~/cc-switch-cli`（Rust 实现的 AI CLI 多供应商管理器，TUI + CLI 双模式，
管理 Claude/Codex/Gemini/OpenCode/Hermes/OpenClaw 的供应商、会话、MCP、skills 等）。
定位差异：cc-switch 是单用户多供应商切换器；llmw 是 workspace + wiki + model registry。
以下只收录**值得借鉴且不破 llmw 边界**（只管元数据 + 启动 session）的机制，按优先级排序。

## 高价值

### 1. `start` 式临时配置启动（并行 session 各用不同 model）

- cc-switch `start claude <id>`：把 effective settings 写进
  `$TMPDIR/cc-switch-claude-settings-<pid>-<ts>.json`（0600），用
  `claude --settings <临时文件>` 启动，shell 包装脚本 trap INT/TERM/HUP 退出后自动
  `rm -f` 临时文件。完全不碰用户配置目录。
  （`src-tauri/src/cli/claude_temp_launch.rs:59-77,141`）
- llmw 现状：overlay 写 `<wiki>/.claude/settings.local.json`，是"最后一次 enter 覆盖"
  语义，同 wiki 不能并行跑不同 model 的 session。
- 借鉴方向：`llmw wiki enter <name> --model <id> --temp`（或独立子命令），用临时
  settings 文件启动，实现同 wiki 多 session 并行不同模型。
- 注意：需评估是否与"overlay 交付走 Local 层文件"不变量冲突；临时文件方案反而是
  更弱的侵入（不写 wiki 内任何文件），可能更干净。

### 2. wiki 级会话管理（sessions list/show/resume/delete）

- cc-switch 按应用扫会话文件：Claude `~/.claude/projects/**.jsonl`、Codex
  `~/.codex/sessions/**.jsonl`、Gemini `~/.gemini/tmp/<project>/chats/session-*.json`；
  提取 title（custom-title > 首条 user 消息 > 目录名）、时间、project_dir；
  resume 时把子进程 cwd 设为会话记录的 `project_dir`。
  （`src-tauri/src/session_manager/providers/claude.rs:22-27`，
  `src-tauri/src/cli/commands/sessions.rs:338-344`）
- llmw 借鉴方向：`llmw wiki sessions <name>`——Claude 的 projects 目录名就是 cwd
  路径编码，天然可按 wiki 路径过滤，做出"该 wiki 的历史 session 列表 + 一键 resume"，
  比 cc-switch 的全局列表更贴合"wiki = 工作单元"定位。
- selector 设计可抄：精确 id → 唯一前缀 → 歧义报错并列候选（上限 8 个）。
  （`cli/commands/sessions.rs:640`）
- 不搬：token/cost 统计（sync-usage 依赖其定价表 + proxy 日志体系，对 llmw 价值低）。

### 3. 环境变量冲突检查（doctor）

- cc-switch `env check`：扫进程 env + `~/.bashrc ~/.bash_profile ~/.zshrc ~/.zprofile
  ~/.profile /etc/profile /etc/bashrc` 中的 `export ANTHROPIC_*` / `OPENAI_*` /
  `GEMINI_*`，逐行报告 `文件:行号`；顺带做应用级体检（live 文件存在性、token 非空、
  base_url 合法 URL）。（`src-tauri/src/services/env_checker.rs:103-154`，
  `src-tauri/src/cli/commands/env.rs:91-307`）
- llmw 借鉴方向：`llmw doctor`——model 真相源是 `workspace_models.toml`，纪律就是
  "禁止 env 读取 model"（[[model-ops-no-env-vars]]）；检测用户 shell 残留的
  `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY`，能直接解释
  "overlay 为什么不生效"这类问题。成本低价值高。

### 4. model 连通性检查（speedtest / stream-check）

- cc-switch `provider speedtest`：并发测各端点延迟（timeout 钳制 2-30s）；
  `stream-check`：发一条真实流式请求验证端到端可用性，仅对超时类失败重试。
  （`src-tauri/src/services/speedtest.rs`，`src-tauri/src/services/stream_check/service.rs`）
- llmw 借鉴方向：`llmw model check <id>`——探测 base_url 连通性 + 可选发一条最小
  请求验证 api_key 有效。registry 里 model 多起来之后排障必备；实现只需 urllib，
  零第三方依赖。

## 中低价值

### 5. 批量操作前自动备份

- cc-switch：restore 前自动建 pre-restore 备份；备份目录按 mtime 轮换保留 10 份。
  （`src-tauri/src/services/config.rs:39-72,183-210`）
- llmw 三份 toml 已走原子写防损坏；若将来加 `llmw model import` 之类批量操作，
  操作前自动备份 `workspace_models.toml` 一份（含时间戳），成本极低。

### 6. dry-run "零文件落地"验收

- cc-switch 有专门测试断言 `start --dry-run` 执行前后临时目录为空（连 normalize 都跑
  但不写盘）。（`src-tauri/src/cli/commands/start.rs:661-688`）
- llmw 已有 `enter --dry-run`；可把"不落盘"写成显式测试约束（当前阶段测试优先级低，
  记入 backlog 即可）。

### 7. fetch-models 辅助填写

- cc-switch `provider fetch-models`：GET `<base_url>/models` 拉远端模型列表，只打印
  不落库。（`src-tauri/src/cli/commands/provider_inspect.rs:267-369`）
- llmw 借鉴方向：`llmw model add` 时可选 `--fetch` 列出远端可用模型名，辅助填 `name`
  字段（网关模型名，如 `MiniMax-M3[1m]`），避免手抄错误。

## 明确不借鉴

- TUI、proxy daemon、MCP / skills / prompts 管理、WebDAV 同步——超出 llmw
  "只管元数据 + 启动 session"的边界。
- SQLite 存储——llmw 的 toml 方案与"元数据可 git 管理 / 人类可读"定位一致，不换。
- 用量统计（token/cost）——依赖 cc-switch 的 proxy 日志 + 定价表体系，llmw 无此
  数据源。

## 落地优先级建议

1. `llmw doctor`（env 冲突检查）
2. `llmw model check <id>`（连通性 / key 验证）
3. `llmw wiki sessions <name>`（按 wiki 过滤历史 session + resume）
4. start 式临时配置启动（`enter --temp` / `--model` 并行 session）

---

## 2026-07-26 二次调研增量（深化工程细节，原文结论不变）

三个子 agent 通读 cc-switch 源码后的增量，补强原文 §2/§3 的工程细节并新增 overlay snippet 点。原文方向与优先级不变。

### §3 doctor 深化

- **为什么必检 `ANTHROPIC_API_KEY`**：overlay 写的是 `ANTHROPIC_AUTH_TOKEN`，但 shell 残留的 `ANTHROPIC_API_KEY`（旧版兼容 key 名）在某些 Claude Code 版本里会被**优先当作 auth fallback**——这是"overlay 不生效"的真实而非理论成因（原文三个变量平列，未点出 API_KEY 的特殊 fallback 地位）。
- **"只检测不修复"哲学**：cc-switch 的 `services/env_manager.rs:25 delete_env_vars`（自动备份 + 删 rc 行 + restore 闭环）是**死代码**，全仓零 caller——CLI 路径只打印诊断让用户手动删。正好匹配 llmw 克制定位：doctor 不做一键清理。
- **精确名白名单替代 substring**：原文扫 `ANTHROPIC_*` 通配会误报 `MY_ANTHROPIC_NOTE`。改成精确名 4 变量：`{ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL}`（正好是 overlay 写的 3 个 + 兼容路径用的 API_KEY），零误报。
- **不违反 [[model-ops-no-env-vars]] 的边界**：那条禁"读 env 当 model 真相源"；doctor 检测 env 冲突是**反向**的（提醒用户清掉 env），二者方向相反、不冲突。
- **env 子命令不走 `--json`**：cc-switch 在 `cli/mod.rs:1698` 显式跳过（诊断给人看）。llmw doctor 同理，省一层格式化。

### §2 session 深化工程纪律

- **有界解析早停（必抄）**：cc-switch 在 `session_manager/mod.rs:87-90`（常量 200 条 / 1MiB 总 / 16KiB 单条）+ `:107-133`（`SessionMessageBatchBuilder::push` 在保留每条前检查，超限 `ControlFlow::Break` 让 reader 立刻停）。**绝不**"读完整文件再 truncate"——这是处理巨量历史的底线。Python 用计数器 + break + UTF-8 边界回退。
- **跨 backend 抽象用"约定式自由函数 + 中央 dict 分派"，非 trait/ABC**：cc-switch `session_manager/providers/mod.rs` 全文 7 行 `pub mod`，中央 `match provider_id`（`session_manager/mod.rs:238-248`）分派；每个 adapter 暴露同名函数集（`scan_sessions`/`load_messages`/`delete_session` 等）+ `PROVIDER_ID` 常量，无 trait。**与 llmw 现有 `overlay.py`/`overlay_opencode.py` 平行模块风格一致**，且适配 Python（无 trait；Protocol 偏静态）。新加 backend = 建 `session/providers/<name>.py` + 加一个 dict 臂，不碰继承链。
- **`resume_cmd` 下沉各 provider + 复用 `_spawn`**：各 adapter 自带 `resume_command` 字段（`SessionMeta`，claude=`claude --resume {id}` @ `providers/claude.rs:460`，opencode=`opencode session resume {id}`），上层不关心动词差异。llmw 落地时复用 `llmw/wiki/enter.py:_spawn` 的 byobu/直启收口 + backend 分派。
- **缓存策略**：cc-switch 旁路 SQLite（`session_manager/scan_cache_store.rs`，按 `(mtime_ns, size)` 指纹 memoize 解析结果）对 llmw **过重**。内核——"解析文件→meta"当纯函数、`(mtime_ns, size)` 为 key memoize、指纹不变复用——llmw 可用 `~/.cache/llmw/session-meta.json`（JSON dict）复刻；MVP **可不缓存**（claude 单 wiki session 文件数通常个位数，远小于 cc-switch 的 17000+）。**即便 Python 标准库自带 sqlite3 也不引入**（守零 DB 定位）。
- **delete 路径穿越护栏**：cc-switch `session_manager/mod.rs:717-722` 把 root 与 source 都 `canonicalize`，source 必须以 provider root 为前缀。llmw 若做 `session delete` 需同款护栏 + `--yes`。

### 新增借鉴点：overlay 用户可配 snippet（演进 [[overlay-habit-template]]）

- `_HABIT_TEMPLATE` 是代码常量、用户不可配；cc-switch 的 common snippet 是用户可配 + opt-in（`meta.apply_common_config`）+ 深合并（`services/common_config.rs:61-77 json_deep_merge`，snippet 在叶子冲突处覆盖 provider，`common_config.rs:406-418`）。
- 演进形态：`workspace.toml` 加 `[overlay_snippet]` 表，`overlay.render` 深合并进 env 块。幂等合并逻辑（`overlay.py:_is_up_to_date` / `_OWNED`）已就绪。
- **所有权分层（关键）**：snippet 用户拥有（不 reset），habit CLI 拥有（reset 回常量）——两者别混。

### "不借鉴"细化

- **enum dispatch 重构 overlay 暂缓**：现仅 2 个 backend，重构不划算。**等第三 backend（codex）出现时再做**；届时因 llmw 支持 py3.7，用 dict dispatch 而非 `match-case`（3.10+）。参考 cc-switch `services/provider/mod.rs:180-207` 的 `enum PreparedLiveWrite`（每 variant 自带 app 特定负载类型 + prepare/apply 两步派发）。
- **SQLite 旁路缓存**：即便标准库自带 sqlite3 也不引入，session 缓存走 JSON 文件或不缓存（见上）。

关联 [[agent-settings-env-precedence]] [[model-ops-no-env-vars]] [[overlay-habit-template]]。
