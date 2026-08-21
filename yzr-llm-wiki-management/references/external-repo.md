# raw/external/——外部代码仓接入与跨主机重建

> **维护方**：**用户**。CLI 不管理其内容；目录何时创建是 CLI 的自由。本文件只定义
> 它存在时的语义与操作契约。用户通过 LLM agent 协助或自行用 `ln -s` + 手写/追加
> `.symlink-anchor.toml` 接入。

外部代码仓（如 Linux kernel、Ray 源码）作为原始语料纳入 wiki 时，**不**做仓库内嵌
拷贝（避免占用空间），而是走 **symlink + 锚定元数据**：

## 一、首次接入（LLM 主导）

> **本文件的角色**：承载操作流程与 schema 示例；wiki 根的纪律约束由 `AGENTS.md` 承载（会话常驻）。

### §1.1 schema 完整示例

```toml
schema_version = 1

# linux-kernel 仓
[[entry]]
symlink = "linux-kernel"           # 对应 raw/external/linux-kernel symlink
target = "~/src/linux-kernel"      # 推荐 ~/... home-relative
captured_at = "2026-07-07"         # 接入当天
kind = "external-repo"             # 当前唯一支持的 kind
remote_url = "https://github.com/torvalds/linux.git"  # git 身份字段（可选）
branch = "master"                  # git 身份字段（可选）

# ray 仓
[[entry]]
symlink = "ray"
target = "~/src/ray"
captured_at = "2026-07-05"
kind = "external-repo"
remote_url = "https://github.com/ray-project/ray.git"
branch = "master"

# notes 字段可选
[[entry]]
symlink = "my-til"
target = "~/src/my-til"
captured_at = "2026-07-01"
kind = "external-repo"
notes = "个人 TIL 仓库，按需重 ingest"
```

> 每 entry 最小必填 4 字段（`symlink` / `target` / `captured_at` / `kind`）+
> 可选 git 身份字段（`remote_url` / `branch`）；`target` 推荐 `~/...` 形式以跨主机可移植，
> 也接受绝对路径（lint 一律 `Path(target).expanduser()` 展开）。**不**记 `commit`。
> `notes` 任何场景都不强制。

### §1.2 操作 5 步（LLM 主导首次接入）

1. 与用户确认 symlink 名（如 `linux-kernel`）+ target 路径
2. 验证 target 是 git 仓（`git -C <target> rev-parse --is-inside-work-tree`）
3. 读 `remote_url` / `branch` 两个值（git 命令）
4. `mkdir -p raw/external && ln -s <target> raw/external/<symlink>`（**扁平**，
   不要在 `external/<source-name>/` 下再开子目录）
5. **读**现有 `.symlink-anchor.toml`（如有）；**追加**新 `[[entry]]` 块；
   **写回**整个文件；首次创建则写完整文件含 `schema_version = 1` 顶层字段

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
  任何机器上的 LLM 读 anchor 都可还原"接入意图"（远端 + 分支）
- anchor 的 `target` 字段（推荐 `~/...` 形式，兼容绝对路径）——同 home
  布局的新机器直接可用；跨 home 布局的机器 LLM 重写。这正是
  `.symlink-anchor.toml` 与 symlink 解耦的价值：**anchor 描述意图、
  symlink 描述当前主机的具体绑定**
- anchor 是单文件 `[[entry]]` 数组——多仓共用一份 anchor，跨主机重建
  也是扫这一个文件
- **不**记 `commit`——wiki 跟随活跃仓的 live 状态而非历史快照

### §2.2 触发场景

| 触发场景 | 用户感知 |
| --- | --- |
| 在新机器 `git clone` wiki 仓后，symlink 不存在 | `ls raw/external/` 看到 `.symlink-anchor.toml` 但没 symlink 文件 |
| 跑 `llmw wiki lint` 时大量 `external-target-dead` | target 路径在新机器不存在 |
| 用户主动在新机器重建（"我换了电脑 / 加了一台机器"） | 同上 |

### §2.3 重建步骤（agent 驱动）

新机器的 LLM agent 跑下列流程：

#### Step 1 — 读 anchor

```bash
# 找到 anchor
test -f raw/external/.symlink-anchor.toml && echo "anchor 存在"
```

每个 entry 的 `remote_url` / `branch` 身份字段（§1.2）是重建的凭据；
若缺了它们，跨 home 布局时只能与用户确认远端与分支（字段可选）。

#### Step 2 — 决定目标路径

约定每个 entry 的 symlink 名 `<symlink>`（kebab-case，与 anchor entry 的
`symlink` 字段对应）的 target 落在新机器的 `~/src/<symlink>/`（可与用户协商改其他路径）。
本字段会写入 anchor entry 的 `target`（推荐 `~/...` 形式，让同 home 布局的同 wiki
仓的其它机器共享）：

```bash
SYMLINK_NAME="linux-kernel"            # 对应 anchor entry 的 symlink 字段
TARGET_ABS="$HOME/src/${SYMLINK_NAME}"  # git clone 的真实落地路径
TARGET_ANCHOR="~/src/${SYMLINK_NAME}"   # 写回 anchor 的 target 字段
```

#### Step 3 — clone + checkout

```bash
git clone "$remote_url" "$TARGET_ABS"
cd "$TARGET_ABS"
git checkout "$branch"  # 切到 anchor 记录的分支（缺 branch 时默认远端默认分支）
```

#### Step 4 — 创建 symlink + 更新 anchor（**扁平布局**）

```bash
# symlink 直接放在 raw/external/ 顶层，不要开 <source-name>/ 子目录
mkdir -p raw/external
ln -s "$TARGET_ABS" "raw/external/${SYMLINK_NAME}"
```

最后**用 `~/...` 形式覆盖 anchor entry 的 `target` 字段**（推荐形式；老
anchor 写绝对路径也兼容）。anchor 是 TOML 单文件，**只改本 entry 的 target**，
不要触碰其他 entry + 不改 `remote_url` / `branch` 身份字段：

```bash
# 用 regex 单行替换 target 字段（保留 entry 顺序 / 注释 / 字段顺序，跨机器 diff 干净）
python3 -c "import re, pathlib; p=pathlib.Path('raw/external/.symlink-anchor.toml'); \
t=p.read_text(); \
q=re.compile(r'(\\[\\[entry\\]\\][\\s\\S]*?symlink\\s*=\\s*\"linux-kernel\"[\\s\\S]*?target\\s*=\\s*)\"[^\"]*\"'); \
p.write_text(q.sub(r'\\1\"~/src/linux-kernel\"', t, count=1))"
```

> **为什么不全量重写（`tomllib.dump`）**：会丢注释、丢字段顺序、跨机器 diff 噪音。
> anchor 是跨主机重建凭据，必须 byte-stable 的局部改写。

`remote_url` / `branch` 身份字段**保持原值不动**——它们是接入意图，不是机器状态。

#### Step 5 — 验证

```bash
# symlink 是否能解析到 target
readlink -f "raw/external/${SYMLINK_NAME}"

# lint 跑通（不应再报 external-target-dead / external-symlink-missing）
# 注意 lint 端会做 Path(target).expanduser()，所以 '~/src/...' 形式 + 同 home 布局下不报 dead
llmw wiki --path=. lint
```

---

## 三、与日常接入的关系 / 漂移

- **首次接入**（用户说"把 X 仓纳入 wiki"）：§一；LLM 在**原机器**跑 5 步接入（读
  现有 anchor → 追加 `[[entry]]` 块）
- **跨主机重建**（在新机器复现）：§二；LLM 在**新机器**跑 5 步重建
  （每个 anchor entry 各自 Step 3-4 一遍）
- **漂移刷新**（用户日常 `git pull` 触发）：**不做**自动漂移检测——
  `remote_url` / `branch` 身份字段极少变化，无需刷新；"摘要是否过期"由用户判断，
  需要时重 ingest 对应 source 页（`target` 字段不动）

## 四、反模式

> 通用外部仓反模式见 SKILL.md §反模式段；本节只收**本流程特有**的：

- **不要把 symlink 文件本身 commit 进 git**——已由 `.gitignore` 排除，强行 `--force`
  add 会污染仓

## 五、失败兜底

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `git clone` 失败：remote not found | `remote_url` 拼错 / 已删除 / 私有 repo 缺凭据 | 检查 remote_url；私有 repo 配 SSH key 或 token |
| `readlink -f` 显示 anchor 路径不存在 | symlink 写错 / target 未建好 | 检查 step 3 4 路径字面量 |
| `llmw wiki lint` 报 `external-symlink-missing` | anchor entry 有但 symlink 未建（Step 4 漏跑 / 失败） | 回到 Step 4 补建 symlink |
| 找不到 `git` CLI | 新机器没装 git | 装 git 后重跑；`git clone` 依赖 git CLI |
