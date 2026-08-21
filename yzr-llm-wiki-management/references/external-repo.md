# raw/external/——外部代码仓接入与跨主机重建

> **维护方**：接入决策归用户 + agent；**symlink + anchor 写路径**统一走
> `llmw wiki external` 子命令；target 仓本体永不触碰。命令面细节在
> `AGENTS.md` `raw/external/` 节（会话常驻）；字段语义与失败兜底在本文件。

## 一、首次接入

agent 主导两项判断（CLI 帮不上）：

- **命名协商**：symlink `--name` 必须 kebab-case（`^[a-z0-9][a-z0-9-]*$`），
  由 agent 与用户共同决定（如 `linux-kernel` / `ray`）；CLI 校验
- **target 路径**：推荐 `~/src/<name>` home-relative 形式（跨主机重建友好；CLI
  rebuild 自动回写此形式）
- **notes 文本**：可选，agent 自由写（机械 scribe 入 anchor）

命令：`llmw wiki external add <target> --name=<n> [--notes=...]`（CLI 自动建 symlink +
读 git 身份字段 + 原子写 anchor；target 必须已存在、永不触碰 target 仓本体）。
命令面细节（4 个子命令 + flag 用法）见 AGENTS.md `raw/external/` 节；本文件不再列举。

### 字段语义（agent 只在排查损坏时需要读；写入全由 CLI 完成）

- **必填 4 字段**：`symlink`（kebab-case）/ `target`（见上）/ `captured_at`（YYYY-MM-DD）/
  `kind: "external-repo"`（未来可加新 kind，当前唯一）
- **git 身份字段（可选）**：`remote_url` + `branch`——跨主机 clone 重建时用；**不**
  记 commit（anchor 记录"接入意图"，commit 是机器快照会腐坏）
- **`notes`（可选）**：agent 自由文本

（schema SSOT = CLI `llmw.content.external_anchor._REQUIRED_FIELDS`；本文件仅列
agent 判断侧所需的语义要点。）

## 二、`sources:` 元素类型（external 特化）

`raw/external/<symlink>/...` 形式的 sources 可指向**文件或目录**：symlink 目标本身
是 git 仓（即目录），可用作整仓语料（`raw/external/<symlink>`）；也可指向仓内子路径
（文件或子目录）。lint 仅校验可访问性（`sp.exists()`），不做 file-only 约束。
普通 raw 路径（非 `raw/external/`）的 sources 仍要求指向**文件**（lint 用
`is_file()` 校验）——raw 子树语义是"已 ingest 的文档"，目录型 raw 来源暂无用例。

## 三、跨主机重建

### 原理：为什么 anchor 进 git、symlink 不进 git

```gitignore
raw/external/*                    # symlink 不进 git（跨主机无意义：target 在新机器不存在）
!raw/external/.symlink-anchor.toml  # anchor 进 git（记录接入意图，TOML 单文件）
```

anchor 文件**进 git** 是这一机制的根：

- symlink 本身是机器相关的——即使是 `~/src/linux-kernel` 在新机器也要重建
  （home-relative 仅指同 home 布局的逻辑路径，跟机器绑定的文件系统不是一回事）
- anchor 的 `remote_url` / `branch` 身份字段是**跨主机稳定**的——
  任何机器上读 anchor 都可还原"接入意图"（远端 + 分支）
- **anchor 描述意图、symlink 描述当前主机绑定**——这是 `.symlink-anchor.toml`
  与 symlink 解耦的价值
- anchor 是单文件 `[[entry]]` 数组——多仓共用一份，跨主机重建也是扫这一个文件

### 触发场景

| 触发场景 | 用户感知 |
| --- | --- |
| 在新机器 `git clone` wiki 仓后，symlink 不存在 | `ls raw/external/` 看到 `.symlink-anchor.toml` 但没 symlink |
| 跑 `llmw wiki lint` 时大量 `external-target-dead` | target 路径在新机器不存在 |
| 用户主动在新机器重建（"我换了电脑 / 加了一台机器"） | 同上 |

### 命令 + 验证

```bash
# 同 home 布局直接重建；TTY 单次确认，--yes 跳过
llmw wiki external rebuild --yes

# 跨 home 布局（新主机路径与 anchor target 不一致）：
# --target=NAME=PATH 覆盖（可重复），anchor 自动回写 ~/... 形式
llmw wiki external rebuild --target=linux=/home/new/src/linux --yes
```

rebuild 自动处理：ok → skip；target 在 → relink；target 不在 + 有 remote_url → clone +
checkout branch + 建 symlink；target 不在且无 remote_url → 报 `unrebuildable`（用
`--target=NAME=PATH` 覆盖或 remove 后重新 add）。验证：

```bash
llmw wiki lint                     # external-* findings 应为 0
```

## 四、与日常接入的关系 / 漂移

- **首次接入**（用户说"把 X 仓纳入 wiki"）：§一；LLM 在原机器跑 add（命名协商 +
  可能 notes 文本由 LLM 决策）
- **跨主机重建**（在新机器复现）：§三
- **漂移刷新**（用户日常 `git pull` 触发）：**不做**自动漂移检测——
  `remote_url` / `branch` 身份字段极少变化，无需刷新；"摘要是否过期"由用户判断，
  需要时重 ingest 对应 source 页（`target` 字段不动）

## 五、反模式

> 通用外部仓反模式见 SKILL.md §反模式段；本节只收**本流程特有**的：

- **不要用 `llmw wiki external remove` 删"孤儿 symlink"**（anchor 无对应 entry 的
  symlink）——CLI 只删注册表声明的东西；孤儿请手工 `rm` + 排查漏录原因
- **损坏的 anchor 不要手改**——CLI add 遇到"文件存在但解析失败"会拒绝覆盖
  （保护修复现场）；正确流程：备份 → 手工修或删除，再用 `external add` 重建

---

**失败兜底原则**：`llmw wiki external` 命令报错与 lint to_action 均为
actionable-first 设计——消息自带修复路径，按 stderr / lint 输出行动即可；本节不留
静态对照表，避免与 runtime 文案产生回声耦合。
