# llmw — Wiki Workspace CLI

管理一个 workspace（一个 git 仓，含多个 wiki 子目录）下的多个 wiki。wiki 由 CLI 创建（spec 0.2.0 起），内容的 ingest / lint / query 由 [`yzr-llm-wiki-management`](https://github.com/yzr95924/llm-workspace-cli/tree/master/yzr-llm-wiki-management) skill 在 session 内负责。CLI 只管元数据与 session 启动。两 skill（`yzr-llm-wiki-management` / `yzr-llm-workspace-management`）与 CLI **同仓**（2026-08-18 起）。

## 安装

```bash
git clone https://github.com/yzr95924/llm-workspace-cli.git
cd llm-workspace-cli
./scripts/install.sh
```

生成 `~/.local/bin/llmw`（wrapper 内嵌本仓库路径，用 `PYTHONPATH` 解析 `llmw` 包，**无需 pip/venv**），并注册 PATH / completion（bash/fish/zsh 三套）/ 两个 skill 的 symlink。装完 source 对应 shell rc 即可。Python 3.11+ 零第三方依赖；<3.11 需 `pip install 'tomli>=1.1'`。

卸载（删 wrapper + PATH marker + completion + skill symlink，**不删仓库、不删 workspace 数据**）：

```bash
./scripts/uninstall.sh
```

> `pip install -e .` 只服务开发 / CI；功能完整安装只用 `install.sh`（运行期依赖同仓 `yzr-llm-*/references/` 与 `templates/`，非 editable wheel 不支持）。

## 快速上手

> 带值 flag 一律用 `--flag=VALUE`（空格分隔会被拒）；前缀缩写已禁用。bool flag 与位置参数不受影响。

```bash
llmw init                                    # 初始化 workspace（默认 ~/yzr-llm-wiki-workspace；不碰 git）
llmw model add --model-id=minimax-m3-1m \
  --name="MiniMax-M3[1m]" --base-url="https://api.example.com" \
  --api-key="sk-xxxxxxxx" --default
llmw wiki --name=llm-systems add --topic="LLM Systems" \
  --display-name="LLM 系统研究" --description="跟踪 LLM 系统论文与博客" \
  --tag=research --tag=llm --model=minimax-m3-1m
llmw wiki --name=llm-systems enter          # 启动 agent session（默认 claude；当前 tmux session 开窗）
llmw wiki --name=llm-systems enter --dry-run  # 先看决策（backend / model / overlay / 窗口名 / 命令）
llmw status                                 # 一屏看所有运行中的 session
llmw wiki --name=llm-systems stop           # 关窗口
llmw wiki --name=llm-systems remove --purge --yes   # 移除并删除目录（默认备份到 .llmw-trash/）
```

## 命令一览

全局 flag：`--workspace=PATH` / `--json` / `--debug` / `--quiet`/`-q`（子命令前后均可）。

### workspace 级

| 命令 | 作用 |
| --- | --- |
| `llmw init [--path=PATH] [--display-name=NAME]` | 初始化 workspace；默认 `~/yzr-llm-wiki-workspace` |
| `llmw config [get\|set\|unset] [KEY] [VALUE]` | 读写 `workspace.toml` / `workspace_local.toml`；无参数 + TTY 进交互模式，非 TTY 打印字段列表 |
| `llmw list [--tag=TAG]...` | 列出 wiki（`--tag` 可重复，AND 关系） |
| `llmw status [--json] [--tmux]` | 一屏查看所有运行中的 session（STATE/UPTIME/IDLE 列；workspace 被删 → 孤儿清理模式） |

### model registry（源数据 `workspace_models.toml`，不入 git）

| 命令 | 作用 |
| --- | --- |
| `llmw model add --model-id=ID --name=NAME --base-url=URL --api-key=KEY [--default]` | 新增 model；`--default` 标记为默认（全局唯一） |
| `llmw model list [--json]` / `show --model-id=ID [--json]` | 列出 / 查看（api_key 自动 redact） |
| `llmw model set-default --model-id=ID` / `unset-default` | 设 / 清默认标记 |
| `llmw model remove --model-id=ID [--yes\|-y]` | 删除 model 条目 |

### wiki 级

| 命令 | 作用 |
| --- | --- |
| `llmw wiki --name=NAME add [--topic=...] [--display-name=...] [--description=...] [--tag=TAG]... [--model=MODEL_ID] [--git]` | 新建 wiki；非 TTY 下 metadata flag 全必填；`--model` 必须在 registry 中；`--git` 为 vestigial flag（CLI 不碰 git，落盘后打印手动 hint） |
| `llmw wiki --name=NAME remove [--purge] [--no-backup] [--yes\|-y]` | 移除 wiki；`--purge` 删子目录（默认备份到 `.llmw-trash/`）；`--no-backup` 跳过备份 |
| `llmw wiki rename --old=OLD --new=NEW [--json] [--quiet]` | 重命名 wiki（3 处同步 + 冲突硬阻挡） |
| `llmw wiki --name=NAME show [--json]` | 查看 wiki 详情（resolved model 来源 + api_key redact） |
| `llmw wiki --name=NAME config [get\|set\|unset] [KEY] [VALUE]` | 读写 `wiki_metadata.toml`；无参数 + TTY 进交互模式 |
| `llmw wiki --name=NAME enter [--dry-run] [--window-suffix=SUFFIX]` | 启动 agent session（backend 见下；当前 tmux session 开窗，不在 tmux 内 → 兜底 attach） |
| `llmw wiki --name=NAME stop [--window-suffix=SUFFIX] [--yes\|-y]` | 终止该 wiki 的 agent 窗口 |

`config` 的合法 KEY 列表由命令本身输出（非 TTY 打印字段清单），此处不重复。

### agent CLI 切换（`wiki enter` 的 backend）

`enter_cli`（`llmw config` 设置，存 `workspace_local.toml`，gitignored / 主机相关）决定 `wiki enter` 用哪个 agent CLI：

| `enter_cli` | 命令 | model 解析 | overlay 交付 |
| --- | --- | --- | --- |
| `claude`（默认） | `claude --add-dir <wiki>` | ✓ | `<wiki>/.claude/settings.local.json`（Local 层 env 块） |
| `opencode` | `opencode <wiki>` | ✓ | `<wiki>/opencode.json`（项目级，明文 apiKey 经 gitignore 排除） |
| `qodercli` | `qodercli --add-dir <wiki>` | ✗ | ✗ |

```bash
llmw config set enter_cli opencode   # 切换；llmw config unset enter_cli 回退默认
```

### 窗口模式（enter / status / stop）

`wiki enter` 把 agent 开成**当前 tmux session 的一个窗口**（不在 tmux 内 → 兜底 `llm_workspace` session + attach）。窗口名 `<wiki>-<suffix>`（suffix 默认 `main`）；**不传 `--window-suffix` 恒为复用跳转，传了才是新开并行窗口**。enter 是 fire-and-forget（窗口建成即返回 0）。设计细节（复用四条件 / 打标 / remain-on-exit / 孤儿模式 / STATE 判定）见 `doc/session-visibility-design.md`。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在等） |
| 2 | 环境错误（byobu-tmux / agent CLI 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

## 注意事项

- 需 byobu（tmux backend）且 **tmux ≥ 2.7**（软性下限，本机实测 3.4）。
- **NFS 不安全**——原子写走 `tmp + fsync + rename`，本地文件系统（ext4 / APFS）安全；`workspace_models.toml` 的 chmod 600 在 NFS 上会静默失败。

## 仓库结构

- `llmw/` — Python 包：`cli.py` / `config.py` + `workspace/` / `wiki/` / `models/` 子包（可执行入口 = install.sh 生成的 `~/.local/bin/llmw` wrapper，或 `python -m llmw`）
- `scripts/` — install / uninstall 脚本及其集成测试
- `templates/` — 仅 `wiki_metadata.toml.template`（`wiki add` 实例化用）
- `yzr-llm-wiki-management/` / `yzr-llm-workspace-management/` — 两 skill（模板 + 探测器 + lint 脚本，随仓分发）
- `MEMORY/` / `doc/` / `tests/` — 项目记忆 / 设计文档 / pytest（CI 跑 ruff + pytest，py3.7 / py3.11）