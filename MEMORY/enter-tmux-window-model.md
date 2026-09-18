---
name: enter-tmux-window-model
description: llmw wiki enter 的窗口启动模型——agent 开成当前 tmux session 的窗口（W'），复用/打标/status 判定/孤儿清理的规则与坑
metadata:
  type: project
---

# enter 走 tmux 窗口（W' 模型）

`llmw wiki enter` 把 agent 开成**当前 tmux session 的一个窗口**：tmux 内发起 → `new-window`
自动聚焦；不在 tmux 内 → 按可见 session 数选路（恰 1 → 直接在其中开窗；0 / ≥2 → 兜底
session `llm_workspace` + TTY attach / 非 TTY hint）。
fire-and-forget（窗口建成返回 0，退出码不来自 agent）。

**Why:** 以"窗口"而非"进程"为生命周期单元，agent 退出 → 窗口消亡 → 标记随亡，天然无僵尸账本；
`llmw status` 实时枚举即可，不需要自建注册表。

**How to apply:**

- **窗口名**一律 `<wiki>-<suffix>`（缺省 `main`）；`--window-suffix` 只传后缀，不传恒为
  **复用跳转**——防误开第二个付费 session。
- **tmux 外选路**（`byobu.visible_sessions`）：恰 1 个可见 session → 直接在其中开窗
  （保持单 session 结构，裸 `byobu` 唯一可见 → 自动选中直达 agent）；0 → 建
  `llm_workspace`；≥2 → 兜底 `llm_workspace`（有歧义不猜）。可见性口径对齐
  byobu-select-session 菜单过滤（隐藏 `_` 开头与含 `-` 的名字——分组残影
  `llm_workspace-N` 在此列）；**兜底 session 名因此禁含 `-`、禁 `_` 开头**（违规名被
  byobu 菜单隐藏，直达永久失效）。动因：原"无条件建 llm_workspace"在已有 session 的
  主机上造出第二个 session，把裸 byobu 直达变成菜单（2026-09-05，假设 A2 被实际
  用法绕过——用户在 tmux 外跑了 enter）。
- **复用四条件**：窗口名精确匹配 AND `@llmw_wiki`==wiki AND `@llmw_backend`==当前 backend AND
  pane 非 dead。命中 dead 尸体 → kill-window 收尸后新开；**backend 不符 → 拒绝 enter + hint 先
  stop 或 --window-suffix**（复用会吞掉"切换 agent"意图，2026-08-15 I6）；防劫持同名非 llmw 窗口，
  归属从不从名字反解。
- **打标**：新开时打 `@llmw_wiki`/`@llmw_started`/`@llmw_backend`（复用不刷新起算；backend 标供
  status 的 BACKEND 列与 STATE 模式路由）。
- **tmux 窗口表即注册表**——不维护自建账本；status 实时枚举（dead pane 显式 `✗ exited` 防僵尸）。
- **status 判定链**（R5）：BACKEND=`@llmw_backend`（老窗口 fallback `pane_current_command`）；
  STATE 短路 = dead `✗` → 假活 `⚠ shell`（带标但 pcmd ∈ fish/bash/zsh/sh，agent 崩了窗口残留）
  → capture-pane 尾部按 backend 模式匹配（opencode：`esc interrupt`/braille spinner=working、
  `ctrl+p commands` 输入行=waiting；claude/qodercli 占位 unknown）→ `?`。**内部值 ASCII**
  （dead/shell/working/waiting/unknown——`--json` 可判等；显示值 `✗/⚠/⚙/⏳/?` 只活在表格层）；
  表格 actionable first 排序（waiting/⚠ 最前、dead 最后）。模式随 CLI 版本漂移 → 优雅降级 unknown。
- **backend 注册表 = `llmw/backends.py`**（结构与判据见 AGENTS.md 模块边界「`llmw.backends`」行）。
- **R8 孤儿清理**：workspace 目录被删后 status 降级孤儿清理模式——仅默认路径触发，warning + 列表 +
  TTY 确认后逐窗 kill；`--json`/`--tmux`/非 TTY 只打 hint（tmux server 生命周期独立于文件系统，
  agent 可能还在烧 token）。
- **实施坑**：一律 `byobu-tmux`（强制 tmux backend），缺 → exit 2（硬依赖）；target 用
  `#{window_id}`；**session target 用 `<name>:` 显式冒号段**（target-window 无冒号时整串按窗口
  index 解析，数字 session 名如 byobu 默认 "1" 会被窗口 index 匹配抢先报 `index N in use`，
  2026-08-15 实机踩坑）；agent argv[0] 先 `shutil.which`；`new-window -n` 锁名；`LLM_WIKI_ROOT`
  走命令前缀注入（`K=V cmd` 拼进命令串，取代 tmux 3.2+ 的 `-e`；只允许非敏感变量，api_key 恒走
  overlay）。**tmux 版本口径：软性 ≥2.7**（保守原语零分叉：`-e`→前缀、`list-windows -a`(2.9+)→
  逐 session 枚举、`#{pane_dead_time}` 缺失→status dead 行 activity 回退停表；实测 3.4）。
- **边界**：仅 tmux backend；`stop` 枚举带标窗口 + kill-window（多候选需 `--window-suffix` 消歧）；
  `remove` 不清窗口；spawn 收口 `enter.py:_spawn` → `byobu.spawn_window`；`enter_byobu` 配置已删除。

关联 [[cli-ux-interactive-and-named-flags]]（--window-suffix 带值 flag 形式）。
