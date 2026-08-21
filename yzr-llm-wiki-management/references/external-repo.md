# raw/external/——外部代码仓接入与跨主机重建

> **维护方**：**用户**掌握接入决策（接哪台仓、叫什么名、何时 re-ingest）；
> **symlink + anchor 的创建/删除/重建**一律走 `llmw wiki external` 子命令（CLI 持有
> 写路径；schema SSOT 在 `llmw.content.external_anchor`）。CLI target 仓本体永不触碰。

外部代码仓（如 Linux kernel、Ray 源码）作为原始语料纳入 wiki 时，**不**做仓库内嵌
拷贝（避免占用空间），而是走 **symlink + 锚定元数据**：

## 一、首次接入

> **本文件的角色**：承载操作流程 + schema 示例；wiki 根的纪律约束由 `AGENTS.md` 承载（会话常驻）。

接入流程（LLM 主导命名协商 + notes 文本；机械操作交 CLI）：

1. 与用户确认 symlink `--name`（kebab-case）+ target 路径
2. `llmw wiki external add <target> --name=<n> [--notes=<...>]`

CLI 自动完成：验证 target 存在 → git 仓则读 `remote_url`/`branch`（非 git 也允许，
身份字段省略 + warn）→ 建 symlink → 原子追加 anchor entry（`captured_at` 自动
填当天、target 在 `$HOME` 下存 `~/...` 形式）。

### §1.1 schema 示例（CLI 生成字节，本文档仅作快速参考）

```toml
schema_version = 1

[[entry]]
symlink = "linux-kernel"           # 对应 raw/external/linux-kernel 同名 symlink
target = "~/src/linux-kernel"      # 推荐 ~/... home-relative
captured_at = "2026-08-22"         # 接入当天 YYYY-MM-DD
kind = "external-repo"             # 当前唯一支持的 kind
remote_url = "https://github.com/torvalds/linux.git"  # 可选，git 仓自动读
branch = "master"                  # 可选，git 仓自动读

[[entry]]
symlink = "my-til"
target = "~/src/my-til"
captured_at = "2026-07-01"
kind = "external-repo"
notes = "个人 TIL 仓库，按需重 ingest"
```

> **字段语义 SSOT** = `llmw.content.external_anchor.save()`；`AGENTS.md`
> `raw/external/` 节（会话常驻）作参考。最小必填 4 字段（`symlink` / `target` /
> `captured_at` / `kind="external-repo"`）+ 可选 git 身份字段（`remote_url` /
> `branch`）+ 可选 `notes`；`target` 推荐 `~/...` 形式以跨主机可移植；**不**记
> `commit`（anchor 记录"接入意图"，commit 是机器快照会腐坏）。

### §1.2 检视 / 移除

- `llmw wiki external list [--json]`：NAME/TARGET/REMOTE/BRANCH/STATUS（ok/missing/dead/drift）
- `llmw wiki external remove <name>`：删 entry + 删 symlink（路径是普通文件/目录会被拒——用户资产保护；target 仓本体永不触碰）

### §1.3 `sources:` 元素类型（external 特化）

`raw/external/<symlink>/...` 形式的 sources 可指向**文件或目录**：symlink 目标本身
是 git 仓（即目录），可用作整仓语料（`raw/external/<symlink>`）；也可指向仓内子路径
（文件或子目录）。lint 仅校验可访问性（`sp.exists()`），不做 file-only 约束。
普通 raw 路径（非 `raw/external/`）的 sources 仍要求指向**文件**（lint 用
`is_file()` 校验）——raw 子树语义是"已 ingest 的文档"，目录型 raw 来源暂无用例。

---

## 二、跨主机重建（漂移刷新）

适用：当 wiki 仓被 `git clone` 到一台新机器，但 `raw/external/`
下的 symlink 不在 git 里（`.gitignore` 排除），需要从 anchor
重建外部源代码的链接。

### §2.1 原理：为什么 anchor 进 git、symlink 不进 git

```gitignore
raw/external/*                    # symlink 不进 git（跨主机无意义：target 在新机器不存在）
!raw/external/.symlink-anchor.toml  # anchor 进 git（记录接入意图，TOML 单文件）
```

anchor 文件**进 git** 是这一机制的根：

- symlink 本身是机器相关的——即使是 `~/src/linux-kernel` 在新机器也要重建
  （home-relative 仅指同 home 布局的逻辑路径，跟机器绑定的文件系统不是一回事）
- anchor 的 `remote_url` / `branch` 身份字段是**跨主机稳定**的——
  任何机器上读 anchor 都可还原"接入意图"（远端 + 分支）
- anchor 的 `target` 字段（推荐 `~/...` 形式，兼容绝对路径）——同 home
  布局的新机器直接可用；跨 home 布局的机器用 `--target=NAME=PATH` 覆盖
- anchor 是单文件 `[[entry]]` 数组——多仓共用一份 anchor，跨主机重建
  也是扫这一个文件
- **不**记 `commit`——wiki 跟随活跃仓的 live 状态而非历史快照

### §2.2 触发场景

| 触发场景 | 用户感知 |
| --- | --- |
| 在新机器 `git clone` wiki 仓后，symlink 不存在 | `ls raw/external/` 看到 `.symlink-anchor.toml` 但没 symlink 文件 |
| 跑 `llmw wiki lint` 时大量 `external-target-dead` | target 路径在新机器不存在 |
| 用户主动在新机器重建（"我换了电脑 / 加了一台机器"） | 同上 |

### §2.3 重建：一条命令 + 一次确认

```bash
# 同 home 布局：直接重建
llmw wiki external rebuild --yes

# 跨 home 布局（新主机路径与 anchor target 不一致）：
# 用 --target=NAME=PATH 覆盖（可重复），anchor 自动回写 ~/... 形式
llmw wiki external rebuild --target=linux=/home/new-user/src/linux --yes

# 不带 --yes：TTY 单次确认；非 TTY 无 --yes 只打计划 + exit 2 不动手
llmw wiki external rebuild
```

rebuild 自动处理：symlink ok → skip；symlink 缺/dead/drift 但 target 存在 → relink；
target 不存在且有 `remote_url` → `git clone <remote_url> <path>` + `checkout <branch>`
+ 创建 symlink；target 不存在且无 `remote_url` → 报 `unrebuildable`（用 `--target`
覆盖或手工处理）。

### §2.4 验证

```bash
llmw wiki external list            # STATUS 应全 ok
llmw wiki lint                     # external-* findings 应为 0
```

---

## 三、与日常接入的关系 / 漂移

- **首次接入**（用户说"把 X 仓纳入 wiki"）：§一；LLM 在**原机器**跑
  `llmw wiki external add`（命名协商 + 可能 notes 文本由 LLM 决策）
- **跨主机重建**（在新机器复现）：§2.3；新主机 `llmw wiki external rebuild`
- **漂移刷新**（用户日常 `git pull` 触发）：**不做**自动漂移检测——
  `remote_url` / `branch` 身份字段极少变化，无需刷新；"摘要是否过期"由用户判断，
  需要时重 ingest 对应 source 页（`target` 字段不动）

## 四、反模式

> 通用外部仓反模式见 SKILL.md §反模式段；本节只收**本流程特有**的：

- **不要把 symlink 文件本身 commit 进 git**——已由 `.gitignore` 排除，强行 `--force`
  add 会污染仓
- **不要手改 `.symlink-anchor.toml`**——CLI 持有 schema SSOT；手写违反
  `_validate_entry` 校验；lint 会报 `external-anchor-corrupt`。要改走 `external add/remove`
- **不要用 `llmw wiki external remove` 删"孤儿 symlink"**——CLI 只删注册表声明
  的东西；孤儿（anchor 无对应 entry）请手工 `rm` + 排查原因

## 五、失败兜底

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `llmw wiki external add` 报"target 不存在" | target 路径拼错 / 未创建 | 核对路径；非本机路径先 clone / mkdir |
| `llmw wiki external add` warn "target 不是 git 仓" | target 不在 git 内 | 可继续 add（`remote_url`/`branch` 省略）；若 target 应是 git 仓则检查 target |
| `llmw wiki external remove` 报"路径是普通文件/目录，拒绝删除" | 路径被覆盖成真实文件，可能是用户资产 | 手工核对后决定：若是资产用 `mv` 保留；若真是要删的 symlink 先排查 |
| `llmw wiki external rebuild` 报 "clone ... failed" | remote_url 失效 / 私有 repo 缺凭据 / 网络问题 | git 配 SSH key 或 token；网络修复后重跑 |
| `llmw wiki external rebuild` 报"unrebuildable" | target 不存在且 anchor 无 remote_url | 用 `--target=NAME=PATH` 指定本地路径；或手工 `llmw wiki external remove <name>` 后再 `add` |
| `llmw wiki lint` 报 `external-symlink-missing` | anchor 有 entry 但 symlink 未建（重建漏跑 / 失败） | `llmw wiki external rebuild --yes` |
| `llmw wiki lint` 报 `external-target-drift` | target 被迁移（`mv` 过）但 anchor target 字段没更新 | 手工编辑 anchor（罕见场景；CLI 不提供 edit 子命令）或 remove + add 到正确路径 |
| `llmw wiki external ...` 报 "git 不在 PATH" | 新机器没装 git | 装 git 后重跑；add 时身份字段会省略，rebuild 无法 clone |
