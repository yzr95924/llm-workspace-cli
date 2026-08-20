---
name: completion-positional-stages
description: CLI 子命令有多段位置参数（action → key → value）时，bash / fish / zsh 三套 completion 都需按 token 位置分多阶段补全；漏任一段则 Tab 断档
metadata:
  type: project
---

`llmw` CLI 有多段位置参数子命令（典型：`wiki config {get,set,unset} <key> <value>`），
completion **必须按 token 位置分多阶段补全**——漏任一段则 Tab 断档。

**Why:** `--flag=` 形式的 completion 有现成模式（见 [[cli-ux-interactive-and-named-flags]]
末尾「新增带值 flag 同步」段）。但**多段位置参数**更复杂——用户依次输入
`wiki config get display_name foo` 时，需要：
- `wiki config` 后 → 候选 `get / set / unset`（cfg_action 位置）
- `wiki config get` 后 → 候选 `display_name / description / tags / model`（cfg_key 位置）
- `wiki config get display_name` 后 → **不补**（cfg_value 自由文本）

**实现模板**（三套 shell 当前形态以 `completions/` 脚本为活参考）：

- **bash**：`wiki_pos` 数组收集非 flag token → 按下标分支。关键：`[ -z "${wiki_pos[N]:-}" ]` 判未选。
- **fish**：`__fish_seen_subcommand_from a b c` 是 **OR**（任一见即真）。"未选 action" 须链式中追加 `; and not __fish_seen_subcommand_from get set unset`——易漏。
- **zsh**：`_describe` 必须在 `_arguments` **之前**调用，否则 describe 被 arguments 的默认分支吞掉。

**验证**（`--flag=` 的验证方法详见 [[bash-completion-wordbreaks]]）：

- bash：mock `COMP_WORDS` 调用 `_llmw` 看 `COMPREPLY` 可验证分支覆盖（**不能**验证 wordbreaks，须 pty 实测）
- fish：`fish -n` + `complete -c llmw` 内省（看 `-n` 条件和 `-a` 候选注册）
- zsh：`zsh -n` 语法检查 + 对照 bash 已通过的算法（pty 难拿回显）

关联 [[cli-ux-interactive-and-named-flags]]（带值 flag 的 completion 同步），
[[bash-completion-wordbreaks]]（pty 验证方法与 wordbreaks 坑）。
