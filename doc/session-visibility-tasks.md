# wiki session 可见性与并行支持 实施任务书

> 元信息：
>
> | 状态 | 关联设计文档 | 设计版本 | 创建日期 | 最近更新 |
> | --- | --- | --- | --- | --- |
> | 待验收（T1-T13 执行完成，§5 自测要点 1-16 已实测通过，待验收者复核；2.7 真机验证矩阵未跑，挂设计 §2.7-6） | `doc/session-visibility-design.md` | 草稿 2026-08-14（2026-08-15 修订 R2/R8/A3/R3/R5/R2 复用防护/R5 json 契约） | 2026-08-14 | 2026-08-15 |

> 本文件是**执行期活文档**：进度与问题只更新在这里；设计文档评审后保持稳定。
> 设计要改时先修订设计文档，再回本文件同步受影响任务（见 §3 循环纪律）。

## 执行者操作指引（拿到本文件先读）

你（执行者，人或 agent）按以下循环操作本文件：

1. **认领**：从 §1 挑一个状态"未开始"且依赖已完成的任务，状态改"进行中"，
   在 §2 对应小节写下开始记录（日期 + 执行者）。
2. **回读设计**：按任务行的"关联目标 / 设计落点 / 验收场景"指针读设计文档对应章节——
   本文件**不含**设计细节，不回读设计文档不许动手。
3. **执行 + 刷新**：每次有进展，在 §2 该任务小节追加一条执行记录（日期 / 内容 / 偏差 / 遗留）；
   状态变化时同步更新 §1 总表的"状态"列与元信息的"最近更新"。
4. **完成**：状态改"待验收"；验收者对照验收场景逐条验收、写结论，状态改"已验收"。
5. **遇到问题**：无法继续 → 状态"已阻塞"并在 §3 登记；发现**设计本身要改** →
   走 §3 循环纪律，不许绕过设计改实现。

你只能改三处：§1 的"状态"列、§2 的执行记录（只追加、不改历史）、§3 两张表。
任务定义（编号 / 内容 / 指针）由设计负责人维护——你觉得任务拆得不对，同样走 §3 登记。

## 1. 任务总表

> 指针适配说明：关联设计文档为 lite 档（无 full 档的 §3 功能点 / §5 场景表 / §7 详细设计），
> 三列指针改指："关联目标"= 设计文档 §1.2 的 G1-G3;"设计落点"= §2.x 章节与 R1-R7 规则；
> "验收场景"= §5 自测要点编号（正常 1-7 / 异常 8-14)。

| 编号 | 任务 | 关联目标 | 设计落点 | 验收场景 | 依赖 | 状态 | 预估 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | `llmw/wiki/byobu.py` 重构：spawn/复用/打标/枚举四原语 | G1,G2,G3 | §2.2 第8步分路；§2.3 状态机；§2.4 R2,R3,R4 | §5-1,2,5 | 无 | 待验收 | 0.5d |
| T2 | enter 新语义 + 删 `enter_byobu` + `--window-suffix`(enter.py / cli.py / local_store.py / workspace manager.py) | G2,G3 | §2.2 全表；§2.4 R1,R2,R4；§2.5 删除/修改项 | §5-1,2,3,5,8,9,10,12 | T1 | 待验收 | 1d |
| T3 | `llmw status` 子命令（新模块 `llmw/wiki/status.py` + cli.py 接线) | G1 | §2.4 R5,R7；§2.5 新增项 | §5-4,7,11 | T1 | 待验收 | 0.5d |
| T4 | `llmw wiki stop` 子命令(wiki/manager.py + cli.py) | G1 | §2.4 R6 | §5-6,11 | T1 | 待验收 | 0.5d |
| T5 | 配套文档 + 全量回归 + smoke(README / AGENTS.md / completions;ruff + pytest;§5 全清单) | G1,G2,G3 | §3 影响面(上下游/测试行);§4 回滚 | §5-1~12 全量 | T2,T3,T4 | 待验收 | 0.5d |
| T6 | enter 命中 dead 窗口收尸后新开（byobu.find_tagged_window 加 pane_dead 条件 + spawn_window 收尸分支 + enter 文案） | G2,G3 | §2.4 R2（2026-08-15 修订）;§2.3 状态机;§2.2 第8步分路 | §5-13 | T1 | 待验收 | 0.5d |
| T7 | status 孤儿清理模式（cli.py 捕 WorkspaceNotFound 降级 + status.py 列表/确认/清理流 + 仅默认路径触发护栏） | G1 | §2.4 R8 | §5-14 | T3 | 待验收 | 0.5d |
| T8 | tmux ≥2.7 兼容改造（byobu.py env 命令前缀注入 + list_windows 逐 session 枚举 + status.py dead 停表 activity 回退 + dry-run 打印同步） | G1,G2,G3 | §1.4 A3（2026-08-15 修订）;§2.2 第8步分路;§2.4 R5;§2.5 tmux 兼容改造;§2.7-6 | §5 全量（3.4 行为保真复跑） | T1,T3 | 待验收 | 0.5d |
| T9 | status 状态可见性增强（R3 第三标 @llmw_backend + R5 枚举 10 字段 + BACKEND/STATE 列 + capture-pane 模式注册表 + actionable-first 排序 + json 字段） | G1 | §2.4 R3（2026-08-15 修订）;§2.4 R5（2026-08-15 修订）;§2.5 status 状态可见性增强 | §5-15 | T1,T3 | 待验收 | 0.5d |
| T10 | backend 复用防护（R2 第四条件 @llmw_backend 匹配，不符拒绝 enter + hint；find_tagged_window 返回带标 backend + enter 拒绝路径 + dry-run 同步） | G2,G3 | §2.4 R2（2026-08-15 修订）;§2.2 第 8 步分路（拒绝分支） | §5-16 | T1 | 待验收 | 0.25d |
| T11 | 行结构/真源/契约重构（巡检 #2/#3/#7/#8/#9：`llmw/backends.py` 单一真源 + `WindowRow` NamedTuple 取代 _W_* 手抄索引 + state ASCII json 契约 + enter_cli 非法值 warning） | G1 | §2.4 R5（--json ASCII 契约）;§2.5 status 状态可见性增强 | §5-15,16 | T3,T9 | 待验收 | 0.5d |
| T12 | 纯重构（巡检 #4/#5/#6：enter()/_print_dry_run_model_backends/_enter_qodercli 拆分 + SpawnSpec 参数对象 + show/_show_collect + _confirm_stop） | G1,G2,G3 | 无设计变更（行为零变化） | §5 相关场景复跑 | T1,T2,T3 | 待验收 | 0.25d |
| T13 | STATE 判定纯函数最小单测（tests/test_status_state.py：模式匹配/分类短路/排序，18 条；用户拍板覆盖"不主动加测试"默认纪律） | G1 | 无设计变更（测试层） | pytest 回归 | T9,T11 | 待验收 | 0.25d |

纪律：

- **只做指针，不复制设计**——"关联目标 / 设计落点 / 验收场景"三列只写设计文档章节号；
  任务行复制设计内容 = 与设计文档必然漂移。
- **状态机**：未开始 → 进行中 → 待验收 → 已验收；异常状态：已阻塞（写明被什么卡住）/ 有偏差。
- **任务粒度**：一个任务 ≈ 一个执行者一个会话能闭环（半天到两天）；先后关系写进"依赖"列。
- 执行中拆出的新任务追加编号（T6、T7…），不重排已有编号。
- 每个代码任务收尾必须跑 `ruff format --check .`、`ruff check .`、`pytest -q`（仓内既有纪律，
  见 AGENTS.md）；存量引用 `enter_byobu` / 老 `spawn_window` 语义的测试用例在对应任务内同步修正。

## 2. 任务执行记录

每个任务一小节，**只追加、不改历史**。

### T1 `llmw/wiki/byobu.py` 重构

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：重写为四原语 + R1/R2/R3 规则。新 API：`window_name_for`（R1 拼接校验，新增 `InvalidWindowSuffix`）、`new_session`/`new_window`（`-P -F '#{window_id}'` 返回 @N）、`find_tagged_window`（R2 窗口名+`@llmw_wiki` 双条件）、`tag_window`（R3 打标，复用不刷新）、`list_windows`（R5 枚举格式 8 字段）、`kill_window`、`attach_session`、`spawn_window`（ensure 一步建 session+首窗口 / 双条件复用 / 新开+打标，线性降级 ≤3 步）。删旧 `find_window`/`has_session(name=固定)`/`_new_session` 固定 session 版。偏差：`ByobuCommandFailed` hint 从"两条命令 stderr 摘要"简化为诊断指引（helper 只返 @N，stderr 不再上抛）。
  - 2026-08-15（agent）：实测（tmux 3.4，fake agent）：复用不新建 ✓、并行窗口 ✓、打标后 status 可枚举 ✓、ensure 一步建 session 不留裸窗口 ✓。
  - 2026-08-15（agent）：**真实使用返工（I3 类，设计没错，实现 bug）**——用户在 byobu 数字名 session（"1"）内 enter 报 `byobu 开窗失败`。根因：`new-window -t <session>` 无冒号时 target-window 整串按**窗口 index/name** 解析（man 规则：special token → 窗口 index → 窗口名），数字 session 名 "1" 被窗口 index 匹配抢先 → `create window failed: index 1 in use`（实机 stderr 确认；`has-session -t 1` / `list-windows -t 1` 等 target-session 类命令不受影响——解析规则含精确名匹配）。修复：session target 一律显式冒号段 `<name>:`（`new_window` 的 `-t f"{session}:"`），强制走 session 段解析，数字名无歧义（实测 `-t 1:` / `-t $1` 两种形态均过）。连带：`_run` 记录最近失败 stderr（`_LAST_STDERR`），`ByobuCommandFailed` 消息带上真实 tmux 报错（此前 `capture_output` 吞 stderr，关键失败全靠猜——T1 早期简化 hint 的代价）。验证：数字 session 内端到端 `enter` 开窗成功（fake claude，exit 0，打标正确）；ruff + pytest 59 passed。
- 验收：（待填，验收者对照 §5-1,2,5）

### T2 enter 新语义 + 删 `enter_byobu` + `--window-suffix`

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：enter.py 重写为 §2.2 八步流程：step5 环境检查（byobu-tmux + agent 二进制，缺 → exit 2，dry-run 跳过）、step7 `_window_name`（R1 拼接，缺省 `-main`）、step8 `_spawn` 新语义（当前 session 开窗/复用 + 自动聚焦；不在 tmux → 兜底 `llm_workspace` + TTY attach / 非 TTY hint）。删 `enter_byobu` 全链路：local_store 字段、workspace manager `CONFIG_KEYS`/`LOCAL_KEYS`/config dump、v1→v2 迁移（静默丢弃）、cli.py enter help + `--window-suffix`。新增错误类 `InvalidWindowSuffix`/`NoRunningSession`/`MultipleRunningSessions`/`StopRequiresConfirmation`。
  - 2026-08-15（agent）：实测 §5-1（tmux 内 enter 自动聚焦窗口）、§5-2（复用 + "运行中 agent 不会重读"提示）、§5-3（`db-main`/`db-ingest` 并行两行同 WIKI）、§5-5（非 TTY 兜底 + hint、TTY 下 attach 阻塞落点正确）、§5-8（byobu 不在 PATH → exit 2 + hint）、§5-9（resolve 失败 → exit 1 且无窗口落盘）、§5-10（未注册/目录缺失 → exit 1）、§5-12（老 local 文件含 `enter_byobu` load 不报错、config 不显示、下次 save 抹除）。
- 验收：（待填，验收者对照 §5-1,2,3,5,8,9,10,12）

### T3 `llmw status` 子命令

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：新建 `llmw/wiki/status.py` + cli.py 接线。R5 表格（WIKI/WINDOW/SESSION/UPTIME/IDLE，时间格式 `now/Nm/Nh/Nd`，dead 行 `✗ exited <Nd> ago` + UPTIME 停表）+ `--json`（原始时间戳秒数）+ `--tmux`（`●N` 仅计运行中，dead 后缀 ` ✗M`）。byobu-tmux 缺失 → exit 2。无 server/无窗口 → `# (no running sessions)` / `●0`。
  - 2026-08-15（agent）：实测 §5-4（UPTIME 增长、IDLE now/Nm 变化）、§5-7（`--tmux` `●2 ✗1`、`--json` 结构合法）、§5-11（remain-on-exit on 下 agent 退出 → `✗ exited now ago` + `uptime_seconds` 停表于 dead_at；stop 收尸后消失）。
- 验收：（待填，验收者对照 §5-4,7,11）

### T4 `llmw wiki stop` 子命令

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：wiki/manager.py 新增 `stop`（R6）+ cli.py 接线。候选 = `@llmw_wiki == X`（再按 `<X>-<S>` 过滤）：0 候选 → `NoRunningSession` exit 1；N 候选未给 `--window-suffix` → `MultipleRunningSessions` exit 1 + 候选清单 + hint（不做交互选择器）；恰 1 → TTY `[y/N]` 确认（`--yes` 跳过，非 TTY 无 `--yes` → `StopRequiresConfirmation` exit 1）→ `kill-window -t @N`。不查 workspace 注册表（窗口枚举是现实，被删 wiki 的残留窗口也能收）。
  - 2026-08-15（agent）：实测 §5-6（单候选 TTY 确认；2 候选报错消歧列出 `foo-main`/`foo-ingest`；`--yes` 跳过；kill 后 status 行消失）、§5-11（dead 残留 `（已退出残留）` 提示 + 收尸）。
- 验收：（待填，验收者对照 §5-6,11）

### T5 配套文档 + 全量回归 + smoke

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：README（config 表删 enter_byobu、命令清单加 status/stop、`enter` 行更新、byobu 章节重写为「窗口模式」、smoke 段重写为 status/stop/并行断言、退出码表）、AGENTS.md（顶层数据流图 + 模块边界表加 `llmw.wiki.status`/更新 byobu/enter/manager/local_store 行 + 数据模型 workspace_local 描述）、MEMORY/MEMORY.md 两条短条目（enter 窗口模型 / 运行时配置拆出）+ cc-switch-inspire 引用措辞、completions 三件套（status + `--window-suffix` + stop + 删 enter_byobu）。
  - 2026-08-15（agent）：回归——`ruff format --check .` ✓、`ruff check .` ✓、`pytest -q` 59 passed ✓。§5 自测 1-12 全清单实测通过（见 T1-T4 记录）。遗留：任务书元信息「设计版本」未动（设计未修订）；本仓 `yzr-SKILL` submodule 有脏改动（既有，非本次引入）。
- 验收：（待填，验收者对照 §5-1~12 全量复核）

### T6 enter 命中 dead 窗口收尸后新开

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：byobu.py `find_tagged_window` 枚举加 `#{pane_dead}`，返回 `(wid, dead)`；`spawn_window` 返回值扩为 `(created, wid, collected)`——dead 命中 → `kill_window` 收尸 → 走新开路径（保持"1 个 `<wiki>-<suffix>` 至多 1 个窗口"，防 stop 消歧失效）；enter.py `_spawn` 消费 collected 打印"同名已退出残留窗口已清理"。文档同步：byobu/enter 模块 docstring、README 窗口模式、AGENTS.md 边界表、MEMORY 短条目。实测（tmux 3.4）：`true` 立即退出 + remain-on-exit=on 构造 dead 窗口 → 二次 spawn 收尸+新开（collected=True）、枚举只剩 1 个活窗口、活窗口复用不新建 ✓。
- 验收：（待填，验收者对照 §5-13）

### T7 status 孤儿清理模式

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：cli.py status 分派提前到 `resolve_workspace_root` 之前——默认路径失败且 `--workspace`/`$LLMW_WORKSPACE` 均未显式指定 → `status_orphan`（显式路径失败保持硬报错，路径不存在时 hint 附加"不带 --workspace 运行 status 可清理"）；status.py 重构出 `_enumerate`/`_render_tmux_line` 供两条路径共用，新增 `status_orphan`（warning + 列表 + TTY `[y/N]` 确认逐窗 kill；非 TTY / `--json` / `--tmux` 只打 hint 不动手；无带标窗口 → 抛回原 WorkspaceNotFound）。文档同步：README、AGENTS.md（status 边界行补 R8 破例）、MEMORY 短条目。实测：非 TTY 表/`--tmux`/`--json` 三形态只输出不动手 ✓、TTY 回 n 取消 / 回 y 全清（2/2，session 整体消失）✓、无孤儿 → WorkspaceNotFound exit 1 ✓、`--workspace=/nope` 硬报错 + 附加 hint ✓、workspace 正常 → 原路径不受影响 ✓。踩坑记录：byobu 包装器要求 HOME 目录存在且归当前用户，测试须先 mkdir fake HOME。
- 验收：（待填，验收者对照 §5-14）

### T8 tmux ≥2.7 兼容改造
- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：按设计 A3 修订（软性 ≥2.7，方案甲保守原语零分叉）实现——byobu.py：删 `_env_args`、`new_session`/`new_window` 去 env 参数，`spawn_window` 拼 `K=V cmd` 前缀（值过 shlex.quote，只允许非敏感变量；取代 tmux 3.2+ 的 `-e`）；`list_windows()` 改逐 session 枚举（`list-sessions` + 每 session `list-windows -t`，session 中途消失跳过不报错，返回结构不变）；模块 docstring 补版本口径与两处机制说明。enter.py：dry-run 打印同步（前缀命令形态 + 三条件文案）。status.py：`_row_to_dict` dead 行停表回退——`pane_dead_time` 缺失（2.7 疑无）→ `window_activity` 近似（agent 死后 activity 冻结），`dead_at` 同步取回退值。文档：README（窗口环境前缀注入 + 注意事项版本行）、MEMORY 短条目（`-e`→前缀 + 版本口径）。实测（tmux 3.4）：env 前缀注入生效（窗口内 `echo $LLM_WIKI_ROOT` 正确）✓、逐 session 枚举跨 session 正确 ✓、dead 回退构造行（无 `pane_dead_time` → dead_at=activity / 有 → 用 dead_time）✓、数字 session 端到端 enter → status → dry-run 形态 → stop 全链 ✓、ruff + pytest 59 passed ✓。遗留：2.7 真机验证矩阵（本小节下方清单）未跑——设计 §2.7-6 登记，出现 2.7 目标机时先跑。
- 验收：（待填，验收者对照 §5 全量 3.4 复跑 + 2.7 验证清单见下）

2.7 真机验证清单（设计 §2.7-6；出现 2.7 目标机时先跑，结果记本小节）：

```bash
# 隔离：PATH 前置 2.7 编译目录 + TMUX_TMPDIR 独立目录（勿与 3.4 server 共用 socket）
# ① new-session/new-window 的 -P -F / -c 组合
tmux new-session -d -s 2 -P -F '#{window_id}' -n w0 -c /tmp sleep 1
tmux new-window -t '2:' -P -F '#{window_id}' -n w1 -c /tmp sleep 1     # 数字名 + 空窗口段
# ② 8 字段格式变量（重点 pane_dead_time 是否渲染为空）
tmux list-windows -t 2 -F '#{session_name}\t#{window_id}\t#{window_name}\t#{window_activity}\t#{pane_dead}\t#{pane_dead_time}\t#{@llmw_wiki}\t#{@llmw_started}'
# ③ @ 用户窗口选项写入/读出
tmux set-option -w -t 2:0 @llmw_wiki db && tmux list-windows -t 2 -F '#{@llmw_wiki}'
# ④ 命令前缀 env 注入
tmux new-window -t '2:' -n w2 'LLM_WIKI_ROOT=/tmp sleep 1'
# ⑤ 逐 session 枚举链路（list-sessions + list-windows -t）
tmux list-sessions -F '#{session_name}'
```

### T9 status 状态可见性增强

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：按设计 I5 修订实现——byobu.py：`_LIST_FORMAT` 8→10 字段（+`#{@llmw_backend}`+`#{pane_current_command}`，常量注释锚定唯一真源）、`tag_window` 加 backend 参数（第三标 `@llmw_backend`，复用不刷新）、`spawn_window` 签名 +backend 透传、新增 `capture_pane_tail`（只读，失败空串）、`_SHELL_CMDS` 假活判定集。enter.py：`_spawn` 加 backend 参数（三调用点 + dry-run 打标打印同步）。status.py：`_W_*` 索引 10、`_row_to_dict` 加 backend（标优先，fallback pcmd basename）/pcmd、STATE 判定 `_classify_state`（dead→✗ → 假活 shell→⚠ → capture 尾部 opencode 模式匹配 working/waiting → ?；短路省调用）、表格 7 列 + `_state_sorted` actionable-first 排序（`--json` 保持 wiki 序 + state/backend 字段）。manager.py：`_W_*` 索引同步 10。文档：README（status 行 + BACKEND/STATE 小节）、MEMORY 短条目、AGENTS.md status 行。实测：**真实 opencode 屏幕**（用户 session 1 window 1，工作中）喂 `_match_working` → working ✓、waiting 互斥 ✓；fake 构造四态（python3 假 agent working/waiting、remain-on-exit dead、pcmd=fish 假活）全判对 ✓；排序 waiting→working→dead ✓；端到端（enter_cli=opencode 真实配置）enter → status 显示 `opencode`/`⏳ waiting` → stop 清理 ✓；ruff + pytest 59 passed ✓。遗留：claude/qodercli STATE 模式占位（扩展点）；opencode waiting 模式为结构推断（空闲态样本待校准）；`sh` 在假活集——sh-wrapper agent 罕见误报可接受。
- 验收：（待填，验收者对照 §5-15）

### T10 backend 复用防护

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：按设计 I6 修订实现——byobu.py：`find_tagged_window` 加 backend 参数 + 枚举加 `#{@llmw_backend}`，返回 `(wid, dead, backend_ok)`；`spawn_window` 消费新形态——非 dead 且 backend 匹配 → select-window 复用；非 dead 但 backend 不符（含老窗口无标）→ 抛新异常 `WindowBackendMismatch`（errors.py，exit 1，hint"先 stop 或 --window-suffix"）；dead 仍收尸新开（backend 无关）。enter.py：dry-run 复用文案改四条件 + 拒绝分支。文档：设计 §2.4 R2 四条件 + §2.2 步 8 拒绝分支 + §5 自测 16 + 元信息；任务书 I6 登记 + 设计修订同步记录；byobu/enter 模块 docstring。实测（tmux 3.4，独立 session）：① claude 活窗换 backend → 拒绝 ✓ ② 同 backend 复用 ✓ ③ `--window-suffix` 旁路新开 ✓ ④ stop 后换 backend enter 成功 ✓ ⑤ 老窗口无 `@llmw_backend` 标 → 拒绝 ✓ ⑥ dead 窗口换 backend → 收尸新开（不拒绝）✓；CLI 端到端（真实 llmw enter/status）：claude enter → status backend=claude → 切 opencode enter → `[llmw] error` + hint + EXIT=1 ✓ → stop → opencode enter 成功 backend=opencode ✓。ruff + pytest 59 passed ✓。
- 验收：（待填，验收者对照 §5-16）

### T11 行结构/真源/契约重构

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：巡检 #2/#3/#7/#8/#9 一次性收口——**新模块 `llmw/backends.py`**（backend 知识单一真源：`KNOWN_BACKENDS` + `STATE_PATTERNS` 注册表 + `match_working`/`match_waiting`，dict 取代 status.py 的 if 链；属于 `llmw` 顶层包，wheel 自动含）。**byobu.py**：`WindowRow` NamedTuple（10 字段）+ `list_windows() -> List[WindowRow]`，`_LIST_FORMAT` 仍是唯一真源（解析长度锚定 `WindowRow._fields`）；消费端 status.py / manager.py **删除 `_W_*` 手抄索引常量**，改属性访问（错位静默失败风险根治——T9 曾漏改 `[:8]` 实证）。**status.py**：state 内部值改 ASCII（`dead`/`shell`/`working`/`waiting`/`unknown`），显示值（`✗`/`⚠ shell`/`⚙ working`/`⏳ waiting`/`?`）下沉 `_STATE_DISPLAY` 表格层——`--json` 输出 ASCII 契约（设计 R5 补记）。**enter.py**：白名单 import `KNOWN_BACKENDS`；手改非法 `enter_cli` 值 → **stderr warning**（不再静默降级，巡检 #7）。**workspace/manager.py**：`_check_enter_cli` 白名单 import `KNOWN_BACKENDS`（删本地 frozenset）。文档：设计 §2.4 R5（--json ASCII 契约）+ 元信息；README（四条件 + BACKEND/STATE 小节 ASCII 说明）；MEMORY 短条目（四条件 + ASCII + backends.py 真源）；AGENTS.md（模块表加 `llmw.backends` 行 + byobu/status 行更新）。实测：四态枚举 ASCII ✓（working/waiting/dead/unknown + 老窗口 fallback backend=sleep）✓、显示映射 + actionable 排序 ✓、`--json` ASCII ✓、`stop` 全链路（WindowRow 消费 + 真实 kill）✓、非法 enter_cli warning ✓、用户配置 `enter_cli=opencode` 已恢复 ✓。ruff + pytest 59 passed ✓。
- 验收：（待填，验收者对照 §5-15 复跑 + §5-16）

### T12 纯重构（长函数拆分 + SpawnSpec）

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：巡检 #4/#5/#6 纯机械拆分，零行为变化——**enter.py**：`enter()` 190 → 137 行（抽 `_enter_qodercli`（qodercli 早退分支 + 专属 dry-run）+ `_print_dry_run_model_backends`（claude/opencode dry-run 打印块，含 redact/habit template））。**byobu.py**：`SpawnSpec` NamedTuple 收 `spawn_window` 8 平铺参数簇（调用方仅 enter._spawn，拆对象为读法清晰）。**wiki/manager.py**：`show` 拆 `_show_collect`（收集）+ `show`（渲染，json/表格两分支）；`stop` 拆 `_confirm_stop`（TTY [y/N] / 非 TTY StopRequiresConfirmation）。add 保持不动（TTY/非 TTY 分支微妙，拆它收益低风险高，巡检在案）。验证：dry-run 输出 20 行与重构前形态逐项核对 ✓、show 表格 ✓、SpawnSpec spawn/reuse 回归 ✓、ruff + pytest 59 passed ✓。
- 验收：（待填，验收者对照 §5 相关场景复跑）

### T13 STATE 判定纯函数最小单测

- 状态：待验收
- 执行记录：
  - 2026-08-15（agent）：巡检 #11——用户拍板加最小单测（覆盖 AGENTS.md"不主动加测试"的默认纪律，一次例外批准，纪律本身不动）。`tests/test_status_state.py` 18 条：`match_working`/`match_waiting`（opencode esc-interrupt/spinner/ctrl+p-commands 判据 + 互斥 + 未注册 backend 一律 False）；`_classify_state`（**dead/shell 短路零 capture 断言**——monkeypatch 后 calls==[]，+ window_id 透传验证）；`_state_sorted`（actionable-first + 组内稳定 + 未知 state 值降级 1 档不崩）。只测纯函数，capture-pane 全 monkeypatch，CI 无 tmux 可跑。pytest 59 → 77 passed ✓。
- 验收：（待填，验收者对照 §5-15 复跑）

## 3. 问题反馈与设计变更

执行中遇到的问题登记在这里——**尤其是"设计本身要改"的问题**：

| 编号 | 发现于 | 问题描述 | 影响 | 处置（改设计 / 绕过 / 挂起） | 状态 |
| --- | --- | --- | --- | --- | --- |
| I1 | 代码 review（2026-08-15） | R2 复用不排除 dead 窗口：remain-on-exit=on 下 enter 复用尸体，用户落在无 agent 的死 pane 且误报"agent 已在运行"；同名一死一活共存还会使 stop --window-suffix 消歧失效（两候选同名无法区分） | enter 语义正确性 + stop 可用性 | 改设计（R2 加"非 dead"第三条件、dead 命中收尸后新开；§2.3 状态机补转移；§5 加自测 13）→ 新增 T6 | 已闭环 |
| I2 | 代码 review（2026-08-15） | workspace 目录缺失（rm/mv）时 status/stop 被 cli.py resolve_workspace_root 前置阻断，tmux 里残留 agent 窗口无法经 llmw 发现/清理（tmux server 生命周期独立于文件系统） | G1 在 workspace 缺失场景失效 | 改设计（新增 R8 status 孤儿清理模式 + 仅默认路径触发的护栏；§5 加自测 14）→ 新增 T7 | 已闭环 |
| I3 | 真实使用（2026-08-15，用户在 byobu 数字名 session "1" 内 enter 失败） | `new-window -t <session>` 无冒号时 target-window 整串按窗口 index/name 解析，数字 session 名被窗口 index 匹配抢先 → `create window failed: index 1 in use`；且 `capture_output` 吞 stderr，失败不可诊断 | enter 在 byobu 默认数字命名 session 下不可用（P2/G2 场景） | 不改设计（实现 bug）：`-t <name>:` 显式冒号段 + `_LAST_STDERR` 上抛真实报错；记 T1 执行记录返工 | 已闭环 |
| I4 | 设计评审（2026-08-15，目标主机 tmux 版本下限讨论） | 版本下限 3.2 由 `-e` 注入（3.2+）与 `list-windows -a`（2.9+）钉死，无必要地排除 2.7 时代目标机；`pane_dead_time`（疑 2.9+）缺失时 dead 行停表无数据源 | 兼容面收窄，老机器无法使用 | 改设计（A3 软性 ≥2.7：env 改命令前缀注入、枚举改逐 session、dead 停表加 activity 回退；§2.7-6 登记 2.7 验证矩阵）→ 新增 T8 | 已闭环 |
| I5 | 设计评审（2026-08-15，status 字段价值讨论） | status 缺两个 actionable 维度：哪些真在跑（BACKEND/假活——带标但 pane 已是 shell 的残留窗口）与哪些在等我回复（STATE：working/waiting；opencode 屏幕模式已实测可辨） | G1 回答"在跑/多久"但不回答"要不要去看" | 改设计（R3 加第三标 `@llmw_backend`；R5 枚举 8→10 字段 + BACKEND/STATE 列 + actionable-first 排序 + capture-pane 模式注册表；§5 加自测 15）→ 新增 T9 | 已闭环 |
| I6 | 代码 review（2026-08-15，backend 复用歧义） | R2 复用条件（窗口名+@llmw_wiki+非 dead）不含 backend：enter_cli=opencode 开 `wiki-main` 后切 claude 再 enter 同 suffix → 静默复用 opencode 窗口，"切换 backend"意图被吞（用户以为在跑 claude 实际复用 opencode）；窗口名无 backend 维度，强新开必致同名共存 → stop/status 消歧失效 | enter 意图正确性 + 窗口唯一性不变量 | 改设计（R2 加"@llmw_backend == 当前 backend"第四条件，不符 → 拒绝 enter + hint 先 stop 或 --window-suffix；不自动开同名第二窗口；§2.2 步 8 分路同步；§5 加自测 16）→ 新增 T10 | 已闭环 |

设计修订同步记录（设计文档每次因问题修订后在此留痕）：

| 日期 | 设计文档变更（章节 + 摘要） | 同步更新的任务 | 操作人 |
| --- | --- | --- | --- |
| 2026-08-15 | §2.4 R2 修订（复用加"非 dead"第三条件，dead 命中收尸后新开）+ §2.3 状态机补"已退出 --enter 收尸--> 无窗口"转移 + §2.2 第 8 步分路同步 + §5 加自测 13 | T6（新增） | agent |
| 2026-08-15 | §2.4 新增 R8（status 孤儿清理模式：触发条件 / 仅默认路径触发护栏 / 非 TTY 行为）+ §2.5 行为补充 + §5 加自测 14 | T7（新增） | agent |
| 2026-08-15 | §1.4 A3 修订（tmux ≥3.2 硬约束 → 软性 ≥2.7：env 改命令前缀注入、枚举改逐 session、dead 停表加 activity 回退）+ §2.2 第 8 步分路命令形态 + §2.4 R5 枚举/停表数据源 + §2.5 tmux 兼容改造 + §2.7 开放问题 6（2.7 验证矩阵）+ §4 回滚表述 | T8（新增） | agent |
| 2026-08-15 | §2.4 R3 修订（打标加第三标 @llmw_backend）+ §2.4 R5 修订（枚举 8→10 字段 + BACKEND/STATE 列 + actionable-first 排序 + capture-pane 模式注册表 + unknown 降级）+ §2.5 status 状态可见性增强 + §5 加自测 15 | T9（新增） | agent |
| 2026-08-15 | §2.4 R2 修订（复用加"@llmw_backend == 当前 backend"第四条件，不符 → 拒绝 enter + hint，不自动开同名第二窗口）+ §2.2 第 8 步分路同步（拒绝分支）+ §5 加自测 16 | T10（新增） | agent |

循环纪律（偏差回流）：

1. 执行中发现设计要改 → 在问题表登记（状态：待处理），**先停该方向的实现**。
2. 修订设计文档相关章节并更新其元信息日期；改动大时挂进设计文档"开放问题"，走二次评审。
3. 回本文件：受影响任务行的"设计落点 / 验收场景"指针同步更新，填"设计修订同步记录"，
   问题状态置"已闭环"。
4. 继续执行。

**不许绕过设计直接改实现**——实现与设计悄悄分叉 = 设计文档和任务书同时失效。
反过来，实现走样但设计没错：不走本表，属于该任务的返工，记在执行记录里。
