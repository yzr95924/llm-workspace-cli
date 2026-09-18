# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

> **关键**：本文件里凡 `@path/to/file` 形式的引用（如 `@MEMORY/MEMORY.md`），都用 Read 工具按需
> 读取——它们与你**当前任务**直接相关。不自动展开 `@import` 的 agent 尤须手动执行，否则漏上下文。

@MEMORY/MEMORY.md

## 项目定位

`llmw`（命令同名）是一个轻量 AI agent 调起的 wrapper，管理 **一个 workspace（一个 git 仓）下的多个 wiki**：

- 一个 workspace = 一个目录 + `workspace.toml` + 多个 wiki 子目录
- 每个 wiki = 一个子目录，含 `raw/` + `wiki/` + `CLAUDE.md` + `wiki_metadata.toml`
- CLI **只**管元数据 + 启动 session；wiki 内部内容（ingest / lint / query）由
  [`yzr-llm-wiki-management`](https://github.com/yzr95924/llm-workspace-cli/tree/master/yzr-llm-wiki-management)
  skill 在 session 内负责（skill 与 CLI 同仓）
- CLI 包 `llmw/` 不写 `raw/` 与 `wiki/` 下任何文件，**唯一例外**：`raw/external/`
  下的 `.symlink-anchor.toml` 与对应 symlink，且仅经 `llmw wiki external` 子命令的
  注册表变换落盘；`notes` 字节由 agent 输入，机械 scribe

## 常用命令

### 安装 / 卸载

```bash
./scripts/install.sh        # 生成 ~/.local/bin/llmw（PYTHONPATH 指向本仓库），按需注册 PATH；注册两个 SKILL 的 symlink 到 ~/.agents/skills（~/.claude/skills 存在时补链）
./scripts/uninstall.sh      # 逆操作：删 wrapper + 清所有候选 rc 的 PATH marker 块 + 删 skill symlink
```

`install.sh` 不动 `llmw/` 包本身，不碰 pip；Python 3.11+ 零第三方依赖，<3.11 需
`pip install 'tomli>=1.1'`。

### 测试 / Lint

```bash
ruff format --check .        # 格式化校验（CI lint job）
ruff check .                 # 静态检查（CI lint job）
pytest -q                    # 单元/集成测试（CI test job，矩阵 py3.7 + py3.11）

python3 scripts/test/smoke_fixtures.py
                            # fixtures 字节一致性 gate（CI fixtures-smoke job）
python3 scripts/test/check_skill_cli_contract.py
                            # skill↔CLI 契约 gate（CI lint job）；改 CLI 子命令 / flag / finding / rule_ref 后必跑

bash scripts/test/test_install_uninstall.sh
                            # install/uninstall 集成测试（用临时 HOME 隔离）
```

> 当前阶段测试优先级低（详见 `MEMORY/MEMORY.md` 短条目区「测试优先级低」条）：
> 以手动 smoke + CI 冒烟为主，agent 不主动加测试代码。
> `llmw/models/` 子包已列入 `pyproject.toml` 的 `setuptools.packages`，editable 安装
> （`pip install -e .`，CI test job 用）含完整 4 子包。**功能完整安装只用 `./scripts/install.sh`**
> （PYTHONPATH 指向本仓）——运行期资源全部内建于 `llmw/content/templates/`，wheel 声明
> `package-data` 后独立可用（不再依赖同仓 `yzr-llm-*/references/` 或 repo 根文件）。

### 手动 smoke 验收

无固定脚本——按需对改动命令跑 happy path；session-visibility 相关自测点见
`doc/session-visibility-design.md` §5（正常 1-7 / 异常 8-16）。

## 架构

### 顶层数据流

```text
用户
  │
  ▼
llmw.cli (argparse + 分派)
  │
  ├──▶ llmw.workspace.manager  ──▶ llmw.workspace.store  ──▶ workspace.toml
  │            │
  │            └─(init)─▶ workspace/.gitignore (含 workspace_models.toml 行)
  │
  ├──▶ llmw.wiki.manager       ──▶ llmw.wiki.store       ──▶ <wiki>/wiki_metadata.toml
  │           │
  │           └─(add)──▶ llmw.wiki.init_wiki ──▶ <wiki>/raw/, <wiki>/wiki/, <wiki>/CLAUDE.md
   │                       (读 llmw/content/templates/{wiki,workspace}/ 下的模板与 fixtures；.gitkeep 无条件落盘
   │                        + 手动 git hint，CLI 绝不碰 git 不变量)
  │
  ├──▶ llmw.models.manager     ──▶ llmw.models.store     ──▶ workspace_models.toml
  │           │                          │
  │           └─(add)──▶ chmod 600       └─▶ redact.api_key (list/show 输出)
  │
  ├──▶ llmw.wiki.enter         ──▶ llmw.models.resolve (wiki → ModelEntry)  [仅 claude]
  │           │
  │           ├─▶ llmw.models.overlay (apply / inspect) → 写 wiki 启动配置（Local 层）  [仅 claude]
  │           │
  │           ├─▶ llmw.models.overlay_opencode (apply / inspect) → 写 opencode.json instructions 键  [仅 opencode]
  │           │
  │           └─▶ llmw.wiki.byobu.spawn_window（当前 tmux session 开窗/复用 + 打标；
  │               dead 残留自动收尸后新开；不在 tmux 内 → 恰一个可见 session 直接开入其中，否则兜底 llm_workspace + attach）──▶ tmux 窗口表
  │
  ├──▶ llmw.wiki.status        ──▶ llmw.wiki.byobu.list_windows（实时枚举带标窗口；workspace 缺失默认路径 → R8 孤儿清理模式）
  ├──▶ llmw.wiki.stop          ──▶ llmw.wiki.byobu.list_windows + kill_window
  │
  ├──▶ llmw.content.external_anchor（`llmw wiki external add/remove/list/rebuild`）
  │           └─▶ <wiki>/raw/external/{symlink, .symlink-anchor.toml}（注册表变换；target 仓永不触碰）
  │
  └──▶ llmw.wiki.show / llmw.workspace.list  ──▶ resolve_for_wiki  (展示 model 来源)
```

> 启动配置文件路径与 agent CLI 精确启动命令属于工具绑定内容——其它 agent 实现可能不同；详见
> `CLAUDE.md` 薄壳逃生舱。

### 关键不变量（核心 3 条）

此处列核心 3 条 + 指向 MEMORY 详述；其余不变量已在本文档各处承载：

1. **代码永不创作内容语义**——CLI 写路径仅限三类字节：① 骨架渲染（字节来自包内
   `llmw/content/templates/` 模板 + metadata 变量，单一入口 `llmw.content.render`）；② 注册表
   声明的纯函数变换（`workspace_models.toml` CRUD、`raw/external/.symlink-anchor.toml`
   + 对应 symlink CRUD（`llmw.content.external_anchor` 单入口）、overlay 启动配置、legacy 路径表
   移动）；③ 机械 scribe（字节来自 agent `ingest-diff` / `write` / `external add --notes` 输入，
   agent 决定内容，CLI 只负责 `log` 行追加 / `index` 条目挂载 / anchor entry 追加等无语义变换操作）。
   `raw/` / `wiki/` 内**任何**需要 LLM 判断的写入都由 skill 在 session 内执行，CLI 绝不创作
   ——这条红线由 `llmw.content` 包封装所有确定性操作（见模块边界表 `llmw.content` 一行）。
2. **CLI 内联实现 wiki 创建**：原 `setup_wiki.py` 已删除（skill 迁移时随之移除）；
    CLI 通过 `llmw.wiki.init_wiki` 读包内 `llmw/content/templates/wiki/` 的
    `agents-md-template.md` / `claude-md-template.md` / `fixtures/*.txt`
    作为字节金标准，占位符替换后落盘；
    不复制 SKILL 运行时纪律（ingest / lint），只承担"出生形态"。SKILL 升级时 CLI 自动获益
    （字节一致性 gate 走 `scripts/test/smoke_fixtures.py` 调 `llmw [wiki] check-fixtures` 探测器，
    CI fixtures-smoke job 执行）。
3. **overlay 交付走 Local 层文件（仅 claude 路径）**——model 真相源是 `workspace_models.toml`，
   不依赖环境变量（[[model-ops-no-env-vars]]）。claude 路径 `wiki enter` 用 `resolve_for_wiki`
   拿 ModelEntry（wiki `model` 字段优先、须在 registry 中否则阻断 enter；否则取 `is_default`），
   渲染进 Local 层 `settings.local.json` 的 `env` 块（优先级 > User 层）：
   `ANTHROPIC_MODEL`=网关模型名 `model.name`（如 `MiniMax-M3[1m]`，不是 `model_id` slug）/
   `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`。opencode 路径（默认）与 qodercli 跳过 model
   resolve，模型由 agent 内部自由切换；opencode 另写 `<wiki>/opencode.json` instructions 整文件
   overlay（gitignore 保留、每次 enter 幂等渲染，遗留 `provider.llmw` 明文 apiKey 自动剥除）。
   子进程 env 透传与优先级机制见 [[agent-settings-env-precedence]]，习惯级 env key 见
   [[overlay-habit-template]]。

其余不变量（包内资源统一于 `llmw/content/templates/` / api_key 永不明文出 stdout / CLI 内联 wiki 骨架的
字节一致性保证）已在本文档承载：资源位置见「架构」数据流与模块边界；
api_key redact 见「开发注意事项」；字节一致性 gate 见 `fixtures/README.md` +
`scripts/test/smoke_fixtures.py`（CI fixtures-smoke job）。

### 模块边界

| 子包 | 职责 | 不做什么 |
| --- | --- | --- |
| `llmw.cli` | argparse + 全局 flag + 分派 | 不含业务逻辑 |
| `llmw.backends` | backend 单一真源：`KNOWN_BACKENDS`（enter_cli 白名单 / 打标 / 校验共用）+ `STATE_PATTERNS`（status 的 STATE 模式注册表）+ `match_working`/`match_waiting`；加新 agent 只改此文件 | 不写盘、不做 tmux IO |
| `llmw.config` | workspace 路径解析、SKILL 脚本路径、模板目录定位 | 不解析 workspace.toml |
| `llmw.content` | **所有**确定性操作单仓收口：`render.py`（骨架渲染单一入口）/ `upgrade.py` + `upgrade_workspace.py`（升级引擎 + 3 终态）/ `wiki_fixtures.py` + `workspace_fixtures.py`（规则注册表 + 探测器，共享脚手架在 `_check_common.py`）/ 内容层命令 `wiki_lint.py` / `ingest_diff.py` / `wiki_write.py` / `external_anchor.py` / `log_format.py`（log 行正则 + 日期解析 SSOT）/ `legacy_paths.toml`（数据）。变量 SSOT = metadata toml + `__version__` 常量；不从旧文件反提取变量 | 不写 `raw/` / `wiki/` 语义内容（红线例外见项目定位）；不调用 LLM；不读用户 git 状态；不写元数据 toml（`store` 负责） |
| `llmw.errors` | 自定义异常（按 exit_code 1/2/3 分层） | — |
| `llmw.fsutil` | 原子写（tmp + fsync + rename）、ISO8601 时间 | — |
| `llmw._compat` | tomllib (3.11+) / tomli (<3.11) 兼容层 + 手写 toml dump | — |
| `llmw.workspace.store` | workspace.toml 读写 + schema 校验 (v2)；v1 已退役，load 直接拒（见「数据模型」） | 不做 wiki 操作、不做 init 业务 |
| `llmw.workspace.local_store` | workspace_local.toml 读写（主机相关运行时：enter_cli） | 无 secret 不 chmod；不读 workspace.toml 结构数据 |
| `llmw.workspace.manager` | init/config/list 业务；init 写 workspace `.gitignore`；config 路由 runtime key→local_store | 不写 wiki 文件；读 wiki_metadata.toml 仅限 list 聚合展示（走 wiki.store 唯一真源） |
| `llmw.wiki.store` | wiki_metadata.toml 读写 + schema v2 + 模板填充 | 不写 workspace.toml、不调 init_wiki |
| `llmw.wiki.init_wiki` | 渲染骨架（读 templates + .gitkeep 占位）；读 `llmw/content/templates/wiki/` → atomic_write；.gitkeep 无条件落盘（红线：不碰 git） | 不写 wiki_metadata.toml、不进 wiki 业务流 |
| `llmw.wiki.manager` | add/remove/show/config/stop 业务；add 调 init_wiki + 打印手动 git hint；校验 model_id；stop 枚举带标窗口 + kill-window（R6） | 不进 wiki 内部、不读 wiki/ 内容 |
| `llmw.wiki.enter` | 启动 session：resolve model → `overlay.apply` 写启动配置 → `byobu.spawn_window` 收口（当前 session 开窗/复用 + 打标；dead 残留自动收尸后新开；不在 tmux 内 → 兜底 session + attach） | 不写元数据 |
| `llmw.wiki.byobu` | byobu/tmux 薄封装 + 开窗编排原语：spawn/复用/打标/枚举 + `visible_sessions` 可见性查询（tmux 外 enter 的选路口径）；`spawn_window` 四条件复用（窗口名 + 打标 + backend + 非 dead，dead 命中收尸后新开）、`list_windows` 返回 `WindowRow`；enter/status/stop 共用 | 不写元数据、不读配置 |
| `llmw.wiki.status` | `llmw status`：枚举带标窗口 → WIKI/WINDOW/SESSION/BACKEND/STATE/UPTIME/IDLE 表 + `--json`（`state` 为 ASCII 稳定值 `dead/shell/working/waiting/unknown`）+ `--tmux`（`●N [✗M]`）；STATE 判定走 capture-pane 模式匹配；R8：workspace 缺失（默认路径）时降级孤儿清理模式——warning + 列表 + TTY 确认后逐窗 kill（`--json`/`--tmux`/非 TTY 只打 hint 不动手） | 主路径不写盘、不 kill 窗口（看归看，关归 stop；R8 孤儿清理是唯一经确认的破例） |
| `llmw.models.overlay` | `render`/`inspect`/`apply`：resolved ModelEntry → 启动配置 `env` 块；幂等合并 + chmod 600。仅 claude 路径使用（opencode 走 `overlay_opencode` 写 `instructions` 键） | — |
| `llmw.models.overlay_opencode` | `render`/`inspect`/`apply`：wiki 模板顶层 @import ∩ 实际存在文件 → `<wiki>/opencode.json` 整文件覆盖写（CLI 拥有；非 CLI 管理 key 覆盖前 stderr 逐名警告；遗留 `provider.llmw` 明文 apiKey 自动剥除；gitignore 保留，每次 enter 幂等渲染）。仅 opencode 路径使用 | — |
| `llmw.models.store` | workspace_models.toml 读写 + schema v2 + 字段校验 + chmod 600 | 不做 CRUD 业务、不做 resolve |
| `llmw.models.redact` | `redact_api_key` 单一脱敏出口 | — |
| `llmw.models.resolve` | `resolve_for_wiki` 单一查找入口：wiki.model 优先，否则 registry 默认 | 不做 CRUD |
| `llmw.models.manager` | CRUD + set/unset-default 业务；保证 `is_default` 全局唯一 | 不直接读 toml 文件（走 store.load） |

### 骨架所有权四分表（本仓视角）

本仓（llmw CLI）维护的"骨架文件"按所有权分 4 档；`llmw upgrade --apply` / `llmw wiki upgrade --apply`
的行为差异即按此分类。

| 档 | CLI 维护的文件 | `check-fixtures` 行为 | `upgrade --apply` 行为 |
| --- | --- | --- | --- |
| **byte-owned** | `<wiki>/AGENTS.md` / `<wiki>/CLAUDE.md` / `<workspace>/AGENTS.md` / `<workspace>/CLAUDE.md` | render-compare：必须与包内 `llmw/content/templates/*-template.md` 渲染稿字节一致 | 按模板全量重渲染 |
| **block-owned** | `<workspace>/.gitignore` 的 llmw managed 块 | 块内 3 规则必须齐全（`gitignore-skeleton` check） | 仅替换 managed 块，块外用户自定义规则不动 |
| **header-owned** | `wiki/index.md` / `wiki/log.md` / `wiki/tags.md` / `MEMORY/MEMORY.md` / `scripts/SCRIPTS.md` | frontmatter 必填键 + H1 + 说明块 + ## 段头（各 `*-skeleton` check） | 换头 + 段嫁接保留 growth 条目 |
| **content-owned** | wiki 内容页 + MEMORY 经验条目 + scripts 脚本正文 + 跨 wiki 综合产物 | 不查（归 agent / skill） | 不动 |

### 全局 flag 与退出码

全局 flag：`--workspace=PATH` / `--json` / `--debug` / `--quiet`/`-q`。

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 用户错误（参数非法、wiki 不存在、registry 字段错误等） |
| 2 | 环境错误（SKILL 目录缺失、agent CLI 不在 PATH 等） |
| 3 | 内部错误（未捕获异常） |

错误格式化统一走 `llmw.errors.format_error`，格式 `[llmw] error: ...` / `[llmw] hint: ...`；
`--debug` 加 traceback。

## 数据模型

四份元数据文件，都走原子写（`fsutil.atomic_write` = `tmp + fsync + os.replace`）：

- **`<workspace>/workspace.toml`**：schema v2；只承载结构数据 + `[wikis.<name>]` 注册表。老 v1
  schema 已硬退役（`load` 直接拒，2026-08 后无自愈路径）。
- **`<workspace>/workspace_local.toml`**：主机相关运行时配置（`enter_cli`，可 set/unset），
  跨主机共用 git 仓不互相 churn。**不入 git**（与 `workspace_models.toml` 同一 gitignore
  managed block），无 secret 不 chmod 600；`enter` / `config` 均从此读。
  （`enter_byobu` 已删——窗口路径全环境成立，直启无场景；残留键 load 静默忽略。）
- **`<workspace>/workspace_models.toml`**（model registry）：`[[models]]` 每条含 `model_id`
  （唯一，`^[a-z0-9_-]{1,64}$`）/ `name` / `base_url` / `api_key` / `context_window`（必填整数，
  无 fallback）/ 可选 `is_default`（全局至多 1 条）。**不入 git**——`init` 写 workspace
  `.gitignore` managed 块自动排除；chmod 600；api_key 只经 `redact` 出口。
- **`<wiki>/wiki_metadata.toml`**：schema v2；`model` 字段存 registry 中的 `model_id`，不是 url / key。

字段级规则（字段名 / 取值约束）见各 `store` 的 `validate` 函数——schema 校验全在 store 层。

## 项目规约（MEMORY/）

仓库内 `MEMORY/` 目录是项目级"为什么 + 边界"记忆的存放点（**不写个人 memory 目录**）。索引由顶部
`@MEMORY/MEMORY.md` 自动加载；每条规则一份独立 markdown，带 frontmatter。提交进代码仓以便协作方看见
并跟随代码历史回溯。

**`@MEMORY/MEMORY.md` 是项目级规则的唯一真源（SSOT）**——agent 会话级 memory 只放指向
本仓 `MEMORY/MEMORY.md` 的指针。条目两类形态（完整 / 短）与写入纪律以
[[memory-entry-conventions]] 为 canonical，索引头部说明块有速览，此处不重抄。

## 开发注意事项

- **不要写 wiki 内容**：除「项目定位」声明的红线例外（`raw/external/` anchor + symlink，
  仅经 `llmw wiki external` 命令）外，任何对 `raw/` 或 `wiki/` 的写入都违反不变量 1。
- **不要复活 setup_wiki.py**：wiki 骨架由 CLI 内联生成（详不变量 2），别把渲染拆回脚本。
- **不要在 `llmw.content` 之外做骨架渲染**：所有确定性操作（render / checker
  fixture 字节比对 / upgrade resync / legacy paths / 内容层命令）统一入口
  `llmw.content` 包——外部模块不要"为了复用"自己写 `_substitute` 或重读
  `llmw/content/templates/*-template.md`；直接调 `llmw.content.render` 的 API。
- **不要让 model 走环境变量被读出来**：`os.environ.get("ANTHROPIC_*")` 这类读取一律禁止；
  model 配置完全由 `workspace_models.toml` 掌控，enter 的 overlay 交付是 CLI 主动行为
  （写启动配置）。详 [[model-ops-no-env-vars]]。
- **api_key 走 redact 出口**：所有 list / show / dry-run 打印前必须过 `redact_api_key`；
  不要自己写 `key[:3] + "..." + key[-4:]`。
- **编辑模板 / fixtures 先读其「规则分层」**：每条纪律恰有一个 canonical 家（跨文件同步
  触发判定 → wiki AGENTS.md「写入纪律」；单文件格式契约 → 该 fixture 头部；工作流步骤 →
  skill references），其余位置只写裸指针、不夹带规则正文；判定规则用 catch-all 兜底行，
  **禁止逐例豁免句**——细则见 `llmw/content/templates/wiki/fixtures/README.md`「规则分层」。
- **schema 校验全在 store 层**：manager / resolve 不重新校验字段；想加新字段就改对应 store
  的 dataclass + validate 函数。
- **NFS 不安全**：原子写走 POSIX `rename`，本地 ext4 / APFS 安全；**不要在 NFS 挂载的 workspace
  上跑 `llmw`**。`workspace_models.toml` 在 NFS 上 `chmod 600` 会 silently 失败，权限安全是
  best-effort。
- **Markdown 行宽 ≤120**：`.markdownlint.jsonc` MD013（表格 / 代码块豁免）；改模板与仓根
  文档同样适用。
- **CI 矩阵**：lint job 跑 ruff（py3.11）；test job 跑 pytest，矩阵 py3.7 + py3.11，用官方
  python 容器（不受 runner 镜像变动影响）；3.7 上不装 ruff、不装 pytest-cov
  （`pip install -e . "pytest>=7,<8"`）。
