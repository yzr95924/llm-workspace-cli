# llmw — Wiki Workspace CLI

管理一个 workspace（一个 git 仓，含多个 wiki 子目录）下的多个 wiki。wiki 由 CLI 创建（spec 0.2.0 起），内容的 ingest / lint / query 由 [`yzr-llm-wiki-management`](https://github.com/yzr95924/llm-workspace-cli/tree/master/yzr-llm-wiki-management) skill 在 session 内负责。CLI 只管元数据与 session 启动。两 skill（`yzr-llm-wiki-management` / `yzr-llm-workspace-management`）与 CLI **同仓**（2026-08-18 起）。

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/yzr95924/llm-workspace-cli.git
cd llm-workspace-cli
```

### 2. 安装命令（推荐）

```bash
./scripts/install.sh
```

生成 `~/.local/bin/llmw`（wrapper 内嵌本仓库路径，用 `PYTHONPATH` 解析 `llmw` 包，**无需 pip/venv**），并在 `~/.local/bin` 不在 `PATH` 时自动往 shell rc 注册一个 marker 块。装完按提示 source 对应 shell rc（或重开终端）即可。

> 全程不动 `llmw/` 包本身、不碰 pip。Python 3.11+ 零第三方依赖；<3.11 运行时需 `pip install 'tomli>=1.1'`。

卸载（删 wrapper + PATH marker + 已装 completion + skill symlink，**不删仓库、不删 workspace 数据**）：

```bash
./scripts/uninstall.sh
```

### 3. 备选：pip editable（仅开发 / CI）

`pip install -e .` 只服务开发与 CI（test job 的 import smoke + entry point）。CLI 运行期依赖
本仓库的 `yzr-llm-*/references/` 与 `templates/`（同仓素材，不在 wheel 内），因此**功能完整安装
只用 §2 的 `install.sh`**；非 editable 的 wheel 安装只对不依赖这些素材的命令（`model` / `status` 等）
可用，`llmw init` / `llmw wiki add` 会失败。

### Shell Completion

`./scripts/install.sh` 装全部三套 completion（bash → `~/.local/share/bash-completion/completions/llmw`；fish → `~/.config/fish/completions/llmw.fish`；zsh → `~/.local/share/zsh/site-functions/_llmw` + 自动 prepend fpath，需 `source ~/.zshrc` 或重开终端）。覆盖全部子命令与 flag；`--name=` / `--model-id=` 动态补全当前 workspace 的 wiki / model 名（未初始化 workspace 时静默仅补静态）。卸载由 `uninstall.sh` 一并处理。

## 快速上手

> 参数风格约定：**带值 flag 一律用 `--flag=VALUE`**（`=` 连接，严谨无歧义；空格分隔的 `--flag VALUE` 会被拒绝并提示 `SpaceFormNotAllowed`）；前缀缩写（`--pref`）也已禁用，请用完整 flag 名。bool flag（无值，如 `--json` `--purge` `--yes` `--git` `--dry-run`）与位置参数（`config KEY VALUE`）不受影响。

```bash
# 初始化 workspace（默认 ~/yzr-llm-wiki-workspace；init 不碰 git）
llmw init
cd ~/yzr-llm-wiki-workspace

# 先把要用的 model 注册到 workspace（--default 设默认 model）
llmw model add \
  --model-id=minimax-m3-1m \
  --name="MiniMax-M3[1m]" \
  --base-url="https://api.example.com" \
  --api-key="sk-xxxxxxxx" \
  --default

# 新建一个 wiki（非 TTY 需全 flag；--model 必须是 registry 里的 model_id）
llmw wiki --name=llm-systems add \
  --topic="LLM Systems" \
  --display-name="LLM 系统研究" \
  --description="跟踪 LLM 系统相关论文与博客" \
  --tag=research --tag=llm \
  --model=minimax-m3-1m

# 查看
llmw list
llmw wiki --name=llm-systems show

# 编辑 metadata（交互模式）
llmw wiki --name=llm-systems config

# 启动 AI agent session（核心命令；默认 claude 走 overlay 写 <wiki>/.claude/settings.local.json；workspace_local.toml#enter_cli 可切 qodercli/opencode；当前 tmux session 开窗，不在 tmux 内 → 兜底 attach）
llmw wiki --name=llm-systems enter
# 先看命令再跑:
llmw wiki --name=llm-systems enter --dry-run
# 看运行中的 agent session + 关窗口:
llmw status
llmw wiki --name=llm-systems stop

# 移除 wiki
llmw wiki --name=llm-systems remove                   # 仅取消注册
llmw wiki --name=llm-systems remove --purge --yes     # 默认先备份到 .llmw-trash/
llmw wiki --name=llm-systems remove --purge --no-backup --yes  # 跳过备份，直接 rmtree
```

## 命令清单

### 全局 flag

`--workspace=PATH` / `--json` / `--debug` / `--quiet` / `-q`（可写子命令前，也可写子命令后）。

### workspace 级

| 命令 | 作用 |
| --- | --- |
| `llmw init [--path=PATH] [--display-name=NAME]` | 初始化 workspace；默认 PATH `~/yzr-llm-wiki-workspace`，不碰 git（允许在已有 git 空仓上 init） |
| `llmw config [get\|set\|unset] [KEY] [VALUE]` | 读写 `workspace.toml`（结构数据）与 `workspace_local.toml`（运行时 key）；无参数 + TTY 进交互模式，非 TTY 打印字段列表退出 0 |
| `llmw list [--tag=TAG]...` | 列出 wiki（`--tag` 可重复，AND 关系） |
| `llmw status [--json] [--tmux]` | 一屏查看所有运行中的 wiki agent session（tmux 窗口实时枚举；`--tmux` 输出 `●N [✗M]` 供状态条集成）；workspace 目录被删后降级孤儿清理模式。列：WIKI / WINDOW / SESSION / BACKEND / STATE / UPTIME / IDLE。详见 [窗口模式](#窗口模式) |

`llmw config` 合法 KEY（写于 `llmw/workspace/manager.py:CONFIG_KEYS`）：

| KEY | set | unset | 说明 |
| --- | :-: | :-: | --- |
| `enter_cli` | ✓ | ✓ | 选 `wiki enter` 启动的 agent CLI；`claude` (默认) \| `qodercli` \| `opencode`。存 `workspace_local.toml`（gitignored、主机相关，跨主机共用 git 仓不 churn）。详见 [切换 agent CLI](#切换-agent-cli) |
| `templates_version` | ✗ | ✗ | 只读，编码双 spec 版本 |
| `created_at` | ✗ | ✗ | 只读 |
| `schema_version` | ✗ | ✗ | 只读 |

### 切换 agent CLI

`wiki enter` 默认走 Claude Code（`claude`），可通过 `enter_cli` 切换为 `qodercli` / `opencode`（workspace 级开关，存 `workspace_local.toml`，gitignored / 主机相关）：

```bash
# 切到 qodercli（不再走 Claude Code；不解析 model、不写 overlay）
llmw config set enter_cli qodercli
llmw config get enter_cli
# qodercli

# 之后所有 wiki enter 都走 qodercli：
llmw wiki --name=<wiki> enter --dry-run   # 看到 backend: qodercli / qodercli --add-dir <wiki>
llmw wiki --name=<wiki> enter

# 切到 opencode（仍解析 model；overlay 写 <wiki>/opencode.json）
llmw config set enter_cli opencode
llmw wiki --name=<wiki> enter --dry-run   # 看到 backend: opencode / opencode <wiki>
llmw wiki --name=<wiki> enter

# 回退默认
llmw config unset enter_cli
```

| `enter_cli` | 命令 | model 解析 | overlay 交付 |
| --- | --- | --- | --- |
| `claude`（默认） | `claude --add-dir <wiki>` | ✓ resolve_for_wiki | `<wiki>/.claude/settings.local.json`（Local 层，env 块含 `ANTHROPIC_*` + habit template） |
| `opencode` | `opencode <wiki>` | ✓ resolve_for_wiki | `<wiki>/opencode.json`（项目级，`provider.llmw` + 顶层 `model`；无 habit template） |
| `qodercli` | `qodercli --add-dir <wiki>` | ✗ 跳过 | ✗ |

三个 backend 均从 cwd=wiki 自读上下文（claude 读 `<wiki>/CLAUDE.md`，opencode / qodercli 读 `<wiki>/AGENTS.md`），不显式注入 system prompt；opencode 的 overlay 写明文 apiKey，经 workspace `.gitignore` 的 `**/opencode.json` 行排除出 git。实现细节见 `AGENTS.md` / `MEMORY/`。合法取值：`claude` / `qodercli` / `opencode`，其它值 `config set` 时被挡（exit 1）。

### 窗口模式（wiki enter / llmw status / wiki stop）

`wiki enter` 把 agent 开成**当前 tmux session 的一个窗口**——tmux 内发起 → 自动聚焦
新窗口；不在 tmux 内（如 SSH 后直跑）→ 自动落到兜底 session `llm_workspace` 并
attach。fire-and-forget：窗口建成 llmw 即返回 0，不等 agent 退出、退出码不来自 agent。
byobu-tmux 是 enter 的**硬依赖**（缺 → exit 2 + 安装 hint）。与 `enter_cli` 正交：
claude / qodercli / opencode 三 backend 通用（model resolve + overlay 落盘逻辑不变，
只换最终 spawn 方式）。

```bash
llmw wiki --name=<wiki> enter --dry-run   # 看全部决策（backend / model / overlay / 窗口名 / 命令）
llmw wiki --name=<wiki> enter             # 在当前 tmux session 开/复用窗口并聚焦
llmw wiki --name=<wiki> enter --window-suffix=ingest   # 并行窗口 <wiki>-ingest（不传恒为复用跳转）
llmw status                               # 一屏：哪些 wiki 在跑、跑了多久、是否已退出
llmw status --tmux                        # ●2 ✗1（供 byobu 状态条集成）
llmw wiki --name=<wiki> stop --yes        # 关窗口（多窗口时需 --window-suffix 消歧）
```

窗口归属与生命周期（tmux 窗口表即注册表，llmw 不维护自建账本）：

- **窗口名一律 `<wiki>-<suffix>`**：suffix 缺省 `main`（第一窗口即 `db-main`），并行
  窗口经 `--window-suffix` 只传后缀（`ingest` → `db-ingest`）。suffix 校验
  `^[a-z0-9_-]{1,16}$`，拼接后总长 ≤40。**不传 flag 恒为复用跳转、传 flag 才是新开**
  ——默认动作绝不会意外开出第二个付费 agent session。
- **复用判定 = 窗口名精确匹配 AND `@llmw_wiki` == 当前 wiki AND `@llmw_backend` ==
  当前 backend AND pane 非 dead 四条件**：用户自开的同名非 llmw 窗口不会被误选
  （归属判定恒以 `@llmw_wiki` 为准，从不从名字反解）。命中已退出残留窗口
  （remain-on-exit=on 下 agent 退出的死 pane）→ **自动收尸后新开**：enter 的语义是
  "开 agent"，不留同名一死一活（那会让 `stop` 的 `--window-suffix` 消歧失效）。
  **backend 不符（切换 agent 时）→ 拒绝 enter**（exit 1 + hint）——复用会吞掉
  "切换 backend"的意图；切换须先 `stop` 再 enter，或 `--window-suffix` 开第二窗口并行。
- **打标**：新开窗口时写三个 tmux 窗口选项——`@llmw_wiki`（归属）+ `@llmw_started`
  （起算时间戳）+ `@llmw_backend`（agent CLI 名）；复用**不刷新**起算时间。agent 是
  窗口主命令，进程退出 → 窗口消亡 → 标记随之消亡，无僵尸记录。
- 复用时 overlay 文件照常刷新落盘，但**运行中的 agent 不会重读**——改了 model
  想生效，先 stop 该窗口再 re-enter。
- 窗口环境：`cwd = <wiki>`（`new-window -c`），`LLM_WIKI_ROOT` 以**命令前缀注入**
  （`K=V cmd` 拼进命令串，不依赖 tmux server 环境继承，兼容 tmux ≥2.7）；agent
  二进制先解析为绝对路径再下窗（tmux server 的 PATH 可能不含 `~/.local/bin`）。
- 兜底路径：不在 tmux 内时 `llm_workspace` session 不存在则自动创建（与首个窗口
  一步建成，不留裸 shell 窗口）；stdout 是 TTY → 直接 attach（落点即新窗口），
  非 TTY（脚本）→ 打印 `byobu attach -t llm_workspace` hint。
- `remain-on-exit` 两路免疫：off（默认）→ agent 退出窗口自动消失，status 枚举不到；
  on → 窗口残留为 dead pane，status 显示 `✗ exited <Nd> ago`、UPTIME 停表，`stop`
  可收尸，`enter` 再次进入该 wiki 时自动收尸后新开。
- **workspace 目录被删后 `llmw status` 进入孤儿模式**：tmux server 生命周期独立于
  文件系统——workspace 没了 agent 窗口可能还在跑。此时 status 不报错退出，而是
  warning + 残留窗口列表 + TTY 下确认后一次性清理（`--json` / `--tmux` / 非 TTY
  只给数据 + hint 不动手）。仅**不带 `--workspace` 的默认路径**解析失败才触发——
  显式指定路径大概率是手滑，保持硬报错（hint 会告知如何进入清理）。

**BACKEND / STATE 列**（status 的 actionable 信息）：

- **BACKEND**：spawn 时打标 `@llmw_backend`（claude / qodercli / opencode）；老窗口
  无此标 → 回退 `pane_current_command` 进程名。
- **STATE**（判定优先级短路）：`✗` 已退出（dead pane）→ `⚠ shell` **假活**（带标但
  前台进程已是 shell = agent 退出/崩溃后窗口残留）→ `⚙ working` / `⏳ waiting`
  （`capture-pane` 读屏幕尾部 + 按 backend 的模式匹配；opencode 已支持——工作态含
  `esc interrupt` + spinner，空闲态为输入行 `ctrl+p commands`；claude / qodercli
  占位未配置）→ `?` 未知。模式随 CLI 版本漂移时优雅降级 unknown，表不坏。
- **排序**：表格 **actionable first**——`⏳ waiting` / `⚠ shell` 最前，`⚙ working`
  次之，`✗` 最后。`--json` 保持 wiki 字典序；`state` 字段输出 **ASCII 稳定值**
  （`dead`/`shell`/`working`/`waiting`/`unknown`，脚本可判等），`backend` 字段同前。

已知限制：

- 仅支持 byobu 的 tmux backend（调用走 `byobu-tmux`，经 argv[0] 强制
  `BYOBU_BACKEND=tmux`）；screen backend 不支持。
- 窗口间切换不归 llmw 管（byobu 原生键 F3/F4、`prefix w/s` 已覆盖）——llmw 只做
  开 / 跳 / 看 / 关。
- `wiki remove` 不清对应窗口——被删 wiki 的窗口里 agent 若还在跑，用
  `wiki stop` 或手动关。
- 并发 double-enter 竞争不上锁：极端情况会产生同名双窗口（tmux 允许共存，下次
  enter 复用第一个），属良性。
- 用户在 agent 窗口内手动 split pane 会破坏"窗口=agent"1:1 假设，status 将继续
  显示存活——已知限制，用法上不给 agent 窗口拆 pane。

### model registry（源数据 `workspace_models.toml`，不入 git）

| 命令 | 作用 |
| --- | --- |
| `llmw model add --model-id=ID --name=NAME --base-url=URL --api-key=KEY [--default]` | 新增 model；`--default` 同时标记为默认（全局唯一） |
| `llmw model list [--json]` | 列出所有 model（api_key 自动 redact） |
| `llmw model show --model-id=ID [--json]` | 查看单条 model |
| `llmw model set-default --model-id=ID` | 把已有条目标记为默认 |
| `llmw model unset-default` | 清空默认标记 |
| `llmw model remove --model-id=ID [--yes\|-y]` | 删除 model 条目 |

### wiki 级

| 命令 | 作用 |
| --- | --- |
| `llmw wiki --name=NAME add [--topic=TOPIC] [--display-name=DISPLAY_NAME] [--description=DESC] [--tag=TAG]... [--model=MODEL_ID] [--git]` | 新建 wiki；非 TTY 下 metadata flag 全必填；`--model` 必须在 registry 中；`--git` 为 vestigial flag（spec §7 0.16.0+：git 操作全部由用户手动，CLI 不碰 git；落盘后打印手动 hint） |
| `llmw wiki --name=NAME remove [--purge] [--no-backup] [--yes\|-y]` | 移除 wiki；`--purge` 同时删子目录（默认先备份到 `.llmw-trash/<name>-<ISO8601>/`）；`--no-backup` 跳过备份直接 rmtree |
| `llmw wiki rename --old=OLD --new=NEW [--json] [--quiet]` | 重命名 wiki：3 处同步（`workspace.toml [wikis.<old>]`→`[wikis.<new>]`、`<workspace>/<old>/`→`<workspace>/<new>/`、`wiki_metadata.toml#name`）；若 `topic == OLD`（add 默认值）则同步改 `topic`；4 阶段原子，原目录直至切换前不动；冲突硬阻挡（`WikiExists` / `InvalidWikiName`） |
| `llmw wiki --name=NAME show [--json]` | 查看 wiki 详情（resolved model 来源 + api_key redact） |
| `llmw wiki --name=NAME config [get\|set\|unset] [KEY] [VALUE]` | 读写 `wiki_metadata.toml`；无参数 + TTY 进交互模式 |
| `llmw wiki --name=NAME enter [--dry-run] [--window-suffix=SUFFIX]` | 按 `workspace_local.toml#enter_cli` 选 agent CLI 启动 session；`claude`（默认）走 overlay + Local 层 settings.local.json 交付 model；`opencode` 走 overlay + 项目级 opencode.json 交付 model；`qodercli` 不读 `.claude/`，不交付 model（详见 [切换 agent CLI](#切换-agent-cli)）。窗口模式：当前 tmux session 开窗（不在 tmux 内 → 兜底 `llm_workspace` + attach）；`--window-suffix` 拼接为 `<wiki>-<suffix>` 开并行窗口，不传恒为复用跳转（详见 [窗口模式](#窗口模式)） |
| `llmw wiki --name=NAME stop [--window-suffix=SUFFIX] [--yes\|-y]` | 终止该 wiki 的 agent 窗口（kill-window）；0 候选 / 多候选未消歧 → exit 1 + 提示；TTY 下确认 `[y/N]`（`--yes` 跳过）。详见 [窗口模式](#窗口模式) |

`llmw wiki --name=X config` 合法 KEY（`llmw/wiki/manager.py:WIKI_CONFIG_KEYS`）：

| KEY | set | unset | 说明 |
| --- | :-: | :-: | --- |
| `display_name` | ✓ | ✓ | 显示名 |
| `description` | ✓ | ✓ | 描述 |
| `tags` | ✓ | ✓ | tag 列表（`set` 走逗号分隔字符串或重复 `--tag`） |
| `model` | ✓ | ✓ | 指向 registry 中的 `model_id`（必须存在） |
| `name` / `topic` / `schema_version` / `created_at` / `updated_at` | ✗ | ✗ | 全部只读 |

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在等） |
| 2 | 环境错误（byobu-tmux / agent CLI 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

## 注意事项

- 需 byobu（tmux backend）且 **tmux ≥ 2.7**（软性下限——实现只走保守原语，无版本分叉；本机实测 3.4）。
- 原子写走 `tmp + fsync + rename`（POSIX 原子），本地文件系统（ext4 / APFS）安全。
  **NFS 不安全**——不要在 NFS 挂载的 workspace 上跑 `llmw`（`workspace_models.toml` 的
  chmod 600 会静默失败）。

## 仓库结构

- `llmw/` — Python 包：`cli.py` / `config.py` + `workspace/` / `wiki/` / `models/` 子包（可执行入口 = install.sh 生成的 `~/.local/bin/llmw` wrapper，或 `python -m llmw`）
- `scripts/` — install / uninstall 脚本及其集成测试
- `templates/` — 仅 `wiki_metadata.toml.template`（`wiki add` 实例化用）
- `yzr-llm-wiki-management/` — wiki 维护 skill（模板 + 探测器 + lint 脚本的字节金标准，随仓分发）
- `yzr-llm-workspace-management/` — workspace 维护 skill（模板 + 探测器，随仓分发）
- `MEMORY/` / `doc/` / `tests/` — 项目记忆 / 设计文档 / pytest（CI 跑 ruff + pytest，py3.7 / py3.11）
