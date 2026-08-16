# wiki session 可见性与并行支持 设计说明

> 状态：草稿 / 作者：yzr95924 / 日期：2026-08-14 / 最近修订：2026-08-15（R2/R8/A3/R3/R5 + status 状态可见性 + R2 backend 复用防护 + R5 json 契约，缘起任务书 I1/I2/I4/I5/I6） / 评审人：待定

## 1. 背景与目标

### 1.1 现状与痛点

llmw 是管理"一个 git 仓下多个 wiki"的 CLI(argparse 分派，`llmw/cli.py:255`)。`wiki enter`
启动 agent session，现有 byobu 模式把窗口开在**固定 session `llm_workspace`** 里，
fire-and-forget(`llmw/wiki/enter.py:143-177`，读码)。三个痛点：

| # | 痛点 | 依据 |
| --- | --- | --- |
| P1 | 看不到哪些 wiki 的 agent 正在跑、跑了多久——`llmw list` 的 LAST_ACTIVITY 由 `wiki/log.md` mtime 派生，是内容活动时间，不含运行态 | `llmw/workspace/manager.py:566-573`，读码；查运行态只能手动 `byobu-tmux list-windows` |
| P2 | 同一 wiki 开不出第二个并行 session——窗口名恒等于 wiki 名，`spawn_window` 同名即复用跳转 | `llmw/wiki/byobu.py:68-82, 114-142`，读码 |
| P3 | enter 是 fire-and-forget，启动后需手动 attach，且落点是 session 当时的 current window，不确定 | `llmw/wiki/enter.py:164-176`，读码 |

### 1.2 目标(均可判定)

- **G1**:`llmw status` 一屏回答——哪些 wiki 有运行中的 session(含并行)、在哪个 tmux
  session、已运行多久、是否还在输出 / 已退出。判定：输出与 `byobu-tmux list-windows -a`
  实测逐行一致，无僵尸条目。
- **G2**:`llmw wiki --name=X enter` 一步进入 agent:tmux 内发起 → 自动聚焦新窗口；
  tmux 外发起(TTY)→ 兜底 session + attach。判定：命令结束时用户视野内是该 wiki 的
  agent 界面。
- **G3**:同一 wiki 可开多个并行 session 且归属可辨。判定：`enter --name=db --window-suffix=ingest`
  后 `llmw status` 显示 `db-main` / `db-ingest` 两行，WIKI 列均为 `db`。

### 1.3 非目标

- 不做 TUI / 常驻界面(否决理由见 §2.6)
- 不管窗口/会话**切换**——归 byobu 原生键(F3/F4、`prefix w/s`),llmw 只做"开/跳/看/关"
- 不做纯 tmux(无 byobu)入口可配化；不做跨主机；不做 agent 退出的推送通知(均见 §2.7 开放项)

### 1.4 假设

- A1:单用户本机场景，无并发多用户(与 CLI 既有定位一致，用户口述确认)
- A2:日常主路径在 byobu 内——用户口述"SSH 后第一件事起 byobu，之后所有操作在 byobu 内";
  单 session 多窗口结构；单终端为主
- A3:目标主机 tmux ≥ 2.7(**软性下限**，2026-08-15 修订——实现只走 2.7 时代已稳定存在的
  保守原语，无版本分叉、无运行时版本检测；本机实测 3.4。原 3.2 硬约束的唯一来源
  `-e` 注入已改命令前缀注入（§2.2 步 8），约束随之消失)。2.7 真机验证矩阵未跑——
  作为开放问题登记（§2.7-6），出现 2.7 目标机时先跑清单再放行。

## 2. 方案设计

### 2.1 核心思路

三句话：

1. **enter 把 agent 开成"当前 tmux session 的一个窗口"**(W' 模型)——不再使用固定
   session 收纳所有窗口；不在 tmux 内时，用兜底 session `llm_workspace` 并在 TTY 下直接
   attach。由此 G2 的"一步进入"无需任何新机制：`new-window` 从 client 内发起天然自动聚焦。
2. **不维护任何自建 session 账本**。spawn 时在窗口上打两个 tmux 用户选项
   (`@llmw_wiki` 归属 / `@llmw_started` 起算时间戳);agent 是窗口主命令，进程退出 →
   pane 销毁 → 窗口消亡 → 标记随之消亡。**tmux 窗口表即注册表，枚举即现实**——无心跳、
   无轮询、无僵尸记录。
3. **管理动作集 = 看(`llmw status`)/ 开+跳(`wiki enter`)/ 关(`wiki stop`)**;
   窗口间切换不归 llmw 管(byobu 原生键已覆盖，且 tmux 是焦点状态的 SSOT，外部工具抢不过来)。

### 2.2 enter 流程(新语义)

`llmw wiki --name=db enter [--window-suffix=S] [--dry-run]`,按序执行：

| 步 | 动作 | 失败出口 |
| --- | --- | --- |
| 1 | 查 `workspace.toml` 注册表得 wiki 目录 | 未注册 → `WikiNotFound`,exit 1 |
| 2 | wiki 目录存在性检查 | 缺失 → `WikiDirMissing`,exit 1 |
| 3 | CLAUDE.md / wiki_metadata.toml 缺失 → stderr 软警告，不阻断 | — |
| 4 | 选 backend:`workspace_local.toml#enter_cli`(claude 默认 / qodercli / opencode),非法值兜回 claude | — |
| 5 | 环境检查：byobu-tmux 在 PATH;agent 二进制在 PATH | 缺一 → exit 2 + 安装 hint(dry-run 跳过) |
| 6 | qodercli：跳过 6a/6b。claude/opencode:6a `resolve_for_wiki`(失败 exit 1，**此时未写任何盘**);6b `overlay.apply` 落盘启动配置(opencode 先确保 gitignore 排除行) | resolve 失败 → exit 1 |
| 7 | 定窗口名:`--window-suffix` 拼接为 `<wiki>-<suffix>`,缺省 `<wiki>-main`;按 R1 校验 | 非法 → exit 1 |
| 8 | spawn 分路(见下),成功后打印确认,exit 0 | byobu 命令失败 → `ByobuCommandFailed`,exit 2 |

第 8 步分路：

```text
$TMUX 存在(主路径,假设 A2)
  → find_window(当前 session, 窗口名)
      有且非 dead 且 backend 匹配 → select-window 复用;打印"overlay 已刷新落盘,运行中 agent 不会重读"
      有且非 dead 但 backend 不符 → 拒绝 enter(exit 1):"窗口 '<名>' 正在运行 <旧backend>;
          切换 backend 请先 stop 或 --window-suffix 开第二窗口"
      有但已 dead → kill-window 收尸(R2),落入"无"分支
      无 → new-window -P -F '#{window_id}' -n <名> -c <wiki目录> <env 前缀> <agent命令>
           （env 前缀 = `LLM_WIKI_ROOT=<目录>` 拼进命令串，`sh -c` 赋值前缀语义；
           值过 shlex.quote。2026-08-15 起取代 tmux 3.2+ 的 `-e` 注入——版本下限由
           3.2 降至 2.7；env 只允许非敏感变量，api_key 恒走 overlay 文件交付）
           → 按 R3 打标 → tmux 自动聚焦,用户落在 agent 窗口
$TMUX 不存在
  → ensure 兜底 session llm_workspace(has-session || new-session -d;并发竞争线性降级 ≤3 步)
  → 同上"复用/新开+打标",作用域为 llm_workspace
  → stdout 是 TTY → attach-session(落点 = 该窗口,select/new 已置其为 current)
  → stdout 非 TTY(脚本)→ 只建不 attach,打印"byobu attach -t llm_workspace",exit 0
```

`--dry-run`:打印第 1-8 步全部决策(backend / resolved model(redacted)/ overlay 文件
will-write 或 up-to-date / 窗口名 / 分路与将执行命令),零写盘零 spawn。

### 2.3 窗口生命周期状态机

```text
                 enter(spawn,打标)
  (无窗口) ──────────────────────▶ ┌─────────┐
    ▲                              │ 运行中   │── agent 进程退出,remain-on-exit=off ──▶ (无窗口)
    │                              │         │── agent 进程退出,remain-on-exit=on ───▶ ┌──────────┐
    │                              └─────────┘                                          │ 已退出    │
    │                                ▲     │ enter(同名复用,                            │(dead pane)│
    │                                │     │  select-window,不刷新 @llmw_started)       └──────────┘
    │                                │     ▼                                             │
    │                                │   (同一窗口)              stop / 手动 kill-window / enter 收尸
    │                              stop(kill-window) ◀───────────────────────────────────┘
    ▼
  (无窗口)

派生属性(非状态,不进状态机):
  active / idle —— 由 now - window_activity 派生(<60s 视为 active,status 显示 now)

已退出 窗口的第三条出路(stop / 手动 kill-window 之外):enter 命中 dead 候选 →
kill-window 收尸后按无窗口处理(新开 + 打标,R2)。收尸杀的是 dead pane(无活进程),
不属 R6 高危动作,无需确认。
```

退出感知两路免疫配置(本机实测:byobu profiles 不设 remain-on-exit,当前 server 为 off;
但设计不押注配置):off → 窗口消失,status 枚举不到;on → 窗口残留为 dead pane,status
按 R5 显式 `✗ exited`。

### 2.4 规则口径(每条附理由——设计点自检)

- **R1 窗口名**:一律 `<wiki>-<suffix>` 形态,suffix 默认 `main`(第一窗口即 `db-main`);
  并行窗口经 `--window-suffix` 只传后缀(如 `ingest` → 拼接为 `db-ingest`)。
  suffix 校验 `^[a-z0-9_-]{1,16}$`,拼接后总长 ≤40 字符。
  理由:① 防误开——不传 flag 恒为复用跳转、传 flag 才是新开,默认动作绝不能意外开出
  第二个付费 agent session(静默烧 token 是不可接受的失败模式);② 名字即用途——并行窗口
  几乎总有用途差异,`db-ingest` 在状态条扫一眼就懂,`db-2` 毫无信息;③ 形状恒定消歧——
  恒为 `<wiki>-<suffix>` 的窗口一眼可辨是 llmw agent,与用户自开的同名 shell 窗口
  (如数据库操作窗口也叫 `db`)区分开;④ 前缀拼接是构造保证,归属可读性不依赖用户自觉。
- **R2 复用语义**(2026-08-15 修订):作用域 session(tmux 内 = 当前 session;否则 =
  llm_workspace)内,**窗口名精确匹配 AND `@llmw_wiki` == 当前 wiki AND
  `@llmw_backend` == 当前 backend AND pane 非 dead** 四条件命中 → select-window;
  命中但 **backend 不符** → 拒绝 enter(exit 1 + hint"先 `stop` 或 `--window-suffix`
  开第二窗口",见下);命中但 pane 已 dead(remain-on-exit=on 残留) →
  kill-window 收尸后按无窗口处理(新开 + 打标);否则新开。
  理由:① 双条件防劫持——用户自开的非 llmw 同名窗口(如 shell 窗口恰叫 `db-main`)
  不被误选,而是正常新开一个带标窗口;② 归属判定恒以 `@llmw_wiki` 为准、窗口名只管
  复用,撞名歧义(如 wiki `db` 的窗口 `db-ingest` vs 真实 wiki `db-ingest`)彻底消解——
  归属从不从名字反解,前缀拼接是单向的、只做展示;③ dead 命中收尸而非复用——复用尸体
  会把用户落在无 agent 的死 pane 上且误报"agent 已在运行";收尸后新开同时保持
  "1 个 `<wiki>-<suffix>` 至多 1 个窗口"不变量,避免同名一死一活共存导致 stop 的
  `--window-suffix` 消歧失效(两候选同名无法区分)。收尸杀的是 dead pane(无活进程),
  不属 R6"关是低频高危"的高危动作,无需确认;代价是丢失尸体最后屏幕输出——想看的
  用户先 status(R5 尸体显式可见)再决定 stop,enter 语义是"开 agent",顺手收尸合理;
  ④ backend 是 spawn 语义的一部分(2026-08-15 增补,缘起任务书 I6)——复用 backend
  不符的活窗口 = 用户"切换 agent"的意图被静默吞掉(切 enter_cli 后 enter 以为换成了
  claude,实际复用着 opencode 窗口)。拒绝 + 可操作 hint 让切换必须显式:先 `stop`
  收掉旧窗口,或 `--window-suffix` 开第二窗口并行——**不自动开同名第二窗口**(窗口名
  无 backend 维度,强新开必致同名共存,stop/status 消歧失效)。
- **R3 打标**(2026-08-15 修订):仅新开窗口时 `set-option -w -t <wid> @llmw_wiki <wiki>` +
  `@llmw_started <unix_ts>` + **`@llmw_backend <backend>`**;复用**不刷新**三个标。
  理由:"session 起来多久"的语义是从最初 spawn 起算;窗口消亡标记随亡,账本零漂移。
  `@llmw_backend`(claude/qodercli/opencode)供 status 的 BACKEND 列与 STATE 模式路由——
  spawn 时已知 backend,比 `pane_current_command` 可靠(claude 走 node,进程名可能显示
  node);老窗口无此标 → status 回退 `pane_current_command`。
  不用 `pane_pid`+`ps` 推算启动时间:跨平台分叉、进程语义绕(pane 首进程 ≠ agent 本体),
  而 tmux 3.4 无 `window_start_time` 变量(本机 man 实测)。
- **R4 兜底 session**:名 `llm_workspace`(沿用既有常量);ensure 竞争只做线性降级(≤3 步,
  沿用老 `spawn_window` 精神,不上锁);TTY → attach,非 TTY → 打印 attach hint。
  理由:罕见路径(假设 A2),但让 enter 在任何环境成立,消灭"不在 tmux 就报错"的懒设计。
- **R5 status**(2026-08-15 修订):枚举走**逐 session**——`list-sessions -F '#{session_name}'`
  + 每 session `list-windows -t <name> -F '#{session_name} #{window_id} #{window_name}
  #{window_activity} #{pane_dead} #{pane_dead_time} #{@llmw_wiki} #{@llmw_started}
  #{@llmw_backend} #{pane_current_command}'`(10 字段;原 `list-windows -a` 是 2.9+,
  逐 session 用远古原语,行为全版本一致;session 在两次调用间消失 → 跳过不报错,
  快照语义)。过滤 `@llmw_wiki` 非空行。**linked/grouped session 去重**(2026-08-16):
  `new-session -t <base>` 不带 `-s` 时 tmux 自动建 `<base>-<n>` linked session,
  与 base 共享全部窗口——逐 session 枚举会把同一窗口重复返回(window_id 全局唯一,
  窗口是 tmux 唯一实体),导致 status 重复行 / stop 误报 MultipleRunningSessions。
  `list_windows()` 按 `window_id` 去重,保留首个枚举到的 session(list-sessions 按
  创建序)。llmw 自身不创建 linked session(`new-session -s <显式名>` / `new-window`
  `-t <session>:`),此为外部产物(用户手动 / 其它工具),防御性处理。
  列:WIKI / WINDOW / SESSION / BACKEND / STATE / UPTIME / IDLE。
  时间格式统一:<60s → `now`;<60min → `Nm`;<24h → `Nh`;否则 `Nd`。
  dead 行:IDLE 列显示 `✗ exited <Nd ago>`,UPTIME 停表——数据源 `pane_dead_time`,
  **缺失(2.7 疑无此格式变量)时回退 `window_activity`**(agent 死后无输出 → activity
  冻结 ≈ 死亡时刻，近似停表;多 pane 窗口下另一活 pane 会刷新 activity → 高估死亡
  时刻，并入 §2.7-4 已知限制)。
  **STATE 列**(2026-08-15 新增,缘起任务书 I5):判定优先级短路——① `✗ exited`(dead,
  已有)② **`⚠ shell` 假活**:带标窗口但 `pane_current_command` ∈ shell 集
  (fish/bash/zsh/sh)= agent 已退出/崩溃但窗口残留 ③ **`⚙ working` / `⏳ waiting`**:
  `capture-pane -p -S -15` 尾部 + 按 `@llmw_backend` 路由的模式注册表——opencode:
  `esc interrupt` / braille spinner(⠋⠙⠹…) 段 → working;无 working 标志但底部输入
  行(`ctrl+p commands`)存在 → waiting;claude/qodercli 注册表**占位未配置** → ④
  `? unknown`。排序:**actionable first**——waiting/`⚠ shell` 最前 → working/unknown →
  dead 最后(原 wiki 字典序 → state 优先级,有意行为变更;`--json` 保持 wiki 稳定排序,
  新增 `state`/`backend` 字段)。**`--json` 契约**(2026-08-15 修订):`state` 输出
  **ASCII 稳定值** `dead` / `shell` / `working` / `waiting` / `unknown`(脚本可判等),
  显示值(`✗`/`⚠ shell`/`⚙ working`/`⏳ waiting`/`?`)只存在于文本表层——显示值与
  机器契约分离,消费方不依赖 emoji。
  理由:dead 窗口显式显示而非隐藏——尸体可见才会被 stop 收掉;隐藏会让 remain-on-exit 用户
  积累不可见僵尸。STATE 仍是 pull 快照(R7 不变——屏幕尾部文本只是 pane 的另一个可拉取
  属性,无 hook 无轮询);模式随 CLI 版本漂移 → 优雅降级 unknown,表不坏。每带标窗口
  +1 次 capture-pane(~10ms 级),规模可忽略。claude/qodercli 模式为扩展点,本次不做。
- **R6 stop**:`llmw wiki --name=X stop [--window-suffix=S] [--yes]`。候选 = `@llmw_wiki == X`
  的带标窗口(再按拼接后窗口名 `<X>-<S>` 过滤)。0 候选 → exit 1"没有运行中的 session";
  N 候选且未给 `--window-suffix` → exit 1 + 列出候选 + hint 消歧(不做交互选择器);
  恰 1 候选 → TTY 确认 `[y/N]`(`--yes` 跳过,沿用 `remove` 惯例)→ `kill-window -t @N`。
  确认信息含窗口名 / 归属 wiki / 窗口状态(运行中 agent 将被终止,或清理已退出残留)。
  理由:关是低频高危动作,显式确认 + 消歧报错比交互选择器简单且脚本友好。
- **R7 感知模型**:无轮询、无账本、无 hook;每次 `status` 实时枚举。
  理由:tmux daemon 维护的窗口表是免费且永远正确的注册表——agent 退出由 daemon 收尸,
  免疫 PID 复用 / SSH 断线 / llmw 进程死亡;拉取精确对"看一眼哪些在跑"的场景是满分答案。
  推送式通知(pane-exited hook)需注入用户 tmux server,违反"不写用户配置"边界,入 §2.7。
- **R8 status 孤儿清理**(2026-08-15 新增,缘起任务书 I2):workspace 解析失败
  (WorkspaceNotFound)时,`llmw status` 不直接报错退出——若 tmux 里枚举到带标窗口
  (`@llmw_wiki` 非空),进入孤儿模式:stderr warning "workspace 未找到: <路径>" +
  照常渲染窗口表 + TTY 下交互确认"将清理全部 N 个窗口(M 个运行中 agent 将被终止 /
  K 个已退出残留),[y/N]" → 确认后逐窗 kill-window。非 TTY / `--json` / `--tmux`:
  不交互,照常输出数据 + hint(TTY 下运行 `llmw status` 交互清理,或
  `byobu-tmux kill-window -t @N`)。workspace 缺失且无任何带标窗口(新机器 / 路径写错)
  → 保持 WorkspaceNotFound 报错。**护栏:仅隐式默认路径解析失败才进孤儿模式**——显式
  `--workspace` / `$LLMW_WORKSPACE` 指向不存在路径大概率是手滑,保持硬报错(hint 告知
  不带 --workspace 运行 status 可清理),杜绝"typo 路径 + 习惯性回 y 误杀活窗口"。
  理由:tmux server 生命周期独立于文件系统——workspace 目录被 rm/mv 后 agent 窗口仍
  跑着烧 token,此时恰恰最需要 status 发现并引导清理;单 workspace 前提(假设 A1/A2)
  下枚举到的带标窗口必属该 workspace,无跨 workspace 误清风险。清理走"先列表、显式
  确认、区分运行中/已退出",与 R6 同级安全;"看归看、关归 stop"的边界在此破例——
  stop 被 cli 入口的 resolve_workspace_root 前置阻断,workspace 缺失时不可用,孤儿
  清理是该场景唯一的 llmw 内收尸通道。

### 2.5 接口与数据变更

- **删除**:config key `enter_byobu`(`workspace_local.toml`)——窗口路径已全环境成立,
  直启模式无存在场景,不为不存在的场景养代码路径。连带:byobu 从可选增强变为 enter
  **硬依赖**(缺 → exit 2;依据假设 A2 用户全覆盖)。
- **修改**:`wiki enter` 语义变更(显式标注):固定 session fire-and-forget → 当前 session
  开窗 / 兜底 attach;新增 `--window-suffix`。`enter_cli` 语义不变;qodercli 路径自动获得
  窗口化(本就走同一 `_spawn`)。
- **新增**:顶层 `llmw status [--json] [--tmux]`;wiki 子命令 `stop [--window-suffix] [--yes]`。
- **行为补充(2026-08-15 修订)**:`status` 增加 workspace 缺失时的孤儿清理模式(R8);
  `enter` 复用判定加"非 dead"第三条件,dead 命中收尸后新开(R2 修订)。
- **tmux 兼容改造(2026-08-15 修订,缘起任务书 I4)**:env 注入 `-e`(3.2+) → 命令前缀
  (全版本);status 枚举 `list-windows -a`(2.9+) → 逐 session(全版本);R5 dead 停表
  数据源加 `window_activity` 回退。版本下限 3.2 → **软性 2.7**。行为差异(3.4 上):
  dry-run 打印的命令形态变化;env 出现在 `pane_start_command` 观测中;`respawn` 后
  env 不再自动继承(`-e` 写 window 环境,前缀只作用初始进程——用户手动 respawn 边缘
  场景,可接受)。
- **status 状态可见性增强(2026-08-15 修订,缘起任务书 I5)**:R3 打标加第三标
  `@llmw_backend`;R5 枚举 8→10 字段 + BACKEND/STATE 两列 + actionable-first 排序;
  `--json` 新增 `state`/`backend` 字段;STATE 数据源 = capture-pane 尾部 + 按 backend
  模式注册表(opencode 先行,claude/qodercli 占位)。
- **数据变更**:无 schema 变更(三份 toml 结构不动);新增数据仅为 tmux 窗口级运行时选项
  (`@llmw_wiki` / `@llmw_started`),不落任何文件。
- **`--tmux` 输出**:`●N`(仅计运行中窗口);存在 dead 窗口时后缀 ` ✗M`。
  理由:status-right 要回答的是"几个在跑",dead 单独计数不混入。

### 2.6 备选方案与否决理由

| 方案 | 否决理由 |
| --- | --- |
| 全屏 TUI(launcher / 监控台) | 鸡肋检验:逐项功能有原生或廉价替代——byobu 状态条常驻列窗口(看)、`prefix &` 杀窗(关)、同名复用(跳);唯一不可替代的"元数据×运行态 join 视图"由 `llmw status` 以纯文本按需提供。且 enter 直启模式(os.chdir+阻塞 subprocess)与 TUI 事件循环互斥。多 session 同屏监控墙是其唯一真独有收益,进 §2.7 |
| session-per-wiki(每 wiki 独立 session) | attach 落点变稳定身份、多 client 焦点隔离是真实收益;但牺牲用户口述的"单 session 多窗口"桌面结构,F3/F4 同构切换与状态条 ambient 可见性丢失(状态条只列当前 session 窗口)。不匹配用户习惯 |
| 自建 session 账本(记录 spawn/退出) | 账本边界是"llmw 的事件",现实边界是"终端里的进程",必然漂移(手动重启 agent / PID 复用 / SSH 断线僵尸记录);tmux 窗口表是 daemon 维护的免费真账,且条目可寻址(attach/kill)。记一笔控不了的死账 |
| enter --attach 旗标(旧 window 模型下) | 落点是一次性状态,F3/F4 一键即破;W' 模型内 `new-window` 自动聚焦已内建吸收该诉求 |

### 2.7 开放问题

1. 纯 tmux(无 byobu)入口可配化——当前 byobu-tmux 写死为唯一入口,出现纯 tmux 使用场景再做
2. pane-exited hook 退出通知(如 ingest 跑完桌面通知)——需用户自行配置 hook,llmw 不注入
3. 多 session 同屏实时监控墙(TUI 形态)——若将来并行 session 常态化,另起评估
4. 用户在 agent 窗口内手动 split pane 会破坏"窗口=agent"1:1 假设,status 将继续显示存活——
   已知限制,不处理(用法上不给 agent 窗口拆 pane)
5. `--new` flag:并行常态化后的省写语法糖——自动取最低空闲序号后缀(如 `db-2`),仍保留
   "显式意图"前提(必须传 flag 才会新开);MVP 不做
6. **tmux 2.7 真机验证矩阵未跑**(A3 修订后)——代码只走保守原语，理论兼容 2.7，但以下
   项需在 2.7 目标机实证后再放行:① `new-window -t '<数字session名>:'` 空窗口段在旧版
   cmd-find 的接受度(不支持的备选:tmux 内路径省略 `-t`——client 上下文即当前 session;
   或 session-id `$N` 形式);② `#{pane_dead_time}` 是否渲染为空(空 → 走 R5 activity
   回退);③ `new-session/new-window` 的 `-P -F` / `-c` 组合;④ `@` 用户窗口选项写入/
   读出。验证清单全文见任务书 T8

## 3. 影响面

- **现有功能**:`enter_byobu` 删除——老 `workspace_local.toml` 含此键,load 忽略(实施时
  验证 local_store 对未知键的容忍),下次 save 自然抹除,不做主动迁移。enter 直启模式删除:
  无 byobu 环境 enter 不可用(exit 2)——依据假设 A2,可接受。存量
  `llm_workspace` 内未打标的历史窗口对新 status 不可见,自然消亡,不迁移。
- **上下游/调用方**:无外部调用方(个人 CLI);`completions/` 需加 `status` / `--window-suffix`
  / `stop`;README 的 byobu 模式描述与 smoke 清单重写;AGENTS.md 模块边界表加
  `llmw/wiki/status.py`,byobu/enter 职责行更新。
- **元数据**:无 schema 变更;api_key 仍只经 redact 出口;CLI 不写 wiki 内容不变量保持
  (overlay 落盘是 enter 既有行为)。
- **用户环境**:llmw 只发 tmux 运行时命令(new-window / set-option -w / kill-window /
  list-windows / attach-session),**永不写**用户 tmux.conf 与 ~/.byobu;状态条集成以
  README 建议片段形式给出。
- **依赖**:无新第三方 Python 依赖;byobu-tmux 从可选变为 enter 硬依赖。
- **测试**:`tests/` 中引用 `enter_byobu` / 老 `spawn_window` 语义的用例同步修正(实施时全搜)。

## 4. 回滚与预案

纯代码变更,无数据迁移:回滚 = git revert 本特性提交。已打标窗口的 `@llmw_wiki` /
`@llmw_started` 是无害 tmux 窗口选项,老代码不读,窗口消亡即清除,无需修复脚本。
若目标主机 tmux 版本过老(低于 2.7 时代的原语集合),表现为 enter exit 2 报错
(`_LAST_STDERR` 会带出真实原因,如 `unknown flag`),回滚版本即恢复。

## 5. 自测要点

正常路径:

1. byobu 内 `enter --name=X` → 新窗口 + 自动聚焦 + agent 启动;overlay 落盘与
   `--dry-run` 输出一致
2. 再次 `enter --name=X` → select-window 复用跳转 + "运行中 agent 不会重读"提示
3. `enter --name=X --window-suffix=ingest` → 并行窗口 `X-ingest`;`status` 显示
   `X-main` / `X-ingest` 两行同 WIKI,归属正确
4. `status`:列齐全;UPTIME 增长、IDLE 在 `now`/`Nm` 间变化;agent 退出后窗口消失、
   status 不再显示
5. byobu 外 TTY `enter --name=X` → 兜底 `llm_workspace` + attach 落点正确;
   非 TTY → 打印 attach hint,exit 0
6. `stop`:确认后 kill-window,status 行消失;N 候选报错消歧;`--yes` 跳确认
7. `status --tmux` 单行 `●N`;`--json` 结构合法

异常路径:

8. byobu-tmux 不在 PATH → exit 2 + hint
9. model resolve 失败 → exit 1,且 overlay / spawn 均未发生
10. wiki 未注册 / 目录缺失 → exit 1
11. `tmux set -g remain-on-exit on` 后 agent 退出 → status 显示 `✗ exited`,UPTIME 停表;
    `stop` 可收尸
12. 老 `workspace_local.toml` 含 `enter_byobu` → load 不报错,`llmw config` 不再显示该键
13. `tmux set -g remain-on-exit on` 后 agent 退出,`enter --name=X`(同 suffix) → dead 窗口
    被收尸 + 新开带标窗口;status 只显示新窗口一行,无同名一死一活共存
14. workspace 目录移走后 `llmw status` → stderr warning + 残留窗口表 + TTY 确认:y → 全部
    kill,n / 非 TTY → 不动只打 hint;workspace 缺失且无带标窗口 → WorkspaceNotFound;
    `--workspace=/不存在路径` → 硬报错,不进孤儿模式
15. `status` 新列:带标窗口 BACKEND 正确(`@llmw_backend` 优先,老窗口 fallback
    `pane_current_command`);带标窗口 pane 变 shell(fake agent 退出后手动开 shell)→
    `⚠ shell`;opencode 真实窗口工作中 → `⚙ working`、空闲 → `⏳ waiting`;排序
    waiting 最前、dead 最后;`--json` 含 `state`/`backend` 字段
16. `enter_cli=claude` 下已有活窗口 `X-main`(backend=claude),改 `enter_cli=opencode`
    再 `enter --name=X`(同 suffix)→ **拒绝**:exit 1 + hint"先 stop 或
    `--window-suffix`";`stop` 后 enter 成功(新窗口 backend=opencode);
    `--window-suffix=oc` 旁路成功(与 `X-main` 并行,互不干扰)
