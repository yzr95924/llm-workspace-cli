---
name: cli-ux-interactive-and-named-flags
description: CLI 参数传递约定——配置类命令优先做成交互式；需用户指定的参数用命名 flag（--xxx=<value>）而非裸位置参数；带值 flag 强制 = 连接
metadata:
  type: project
---

`llmw` CLI 的参数传递遵循两条 UX 约定（用户 2026-06-28 确立）：

1. **配置类命令优先做成交互式**：`config` 这类需要用户逐项填值的命令，应提供交互模式（TTY 下无子动作即进入），让用户逐项输入，而不是逼用户记住一堆 flag。
2. **需用户指定的参数，用命名 flag 传递**：`--flag=<value>`（= 连接，严谨无歧义），不要用裸位置参数 `<value>`。命名 flag 自明、顺序无关、可读；位置参数的含义靠位置隐式推断，易错。

**Why:** 交互式降低用户记忆负担（配置项多时尤甚）；命名 flag 让命令行自文档化（`--model-id=m2` 比 `m2` 清晰）、顺序无关、便于脚本化与可读。

**形式统一（2026-07-03 修订）**：带值 flag 一律 `--flag=<value>`（= 连接），**拒绝**空格分隔的 `--flag value`——以保证严谨性（用户 2026-07-03 确立）。理由：`=` 把 flag 与值在同一 token 内绑定，不靠相邻位置隐式推断，避免"下一个 token 到底是值还是另一个 flag / 子命令"的歧义；配合禁用前缀缩写（`allow_abbrev=False`），堵住 `--pref value` 缩写绕过。实现见 `llmw/cli.py:_enforce_equals_form`：动态遍历 parser 树收集带值 flag（`_StoreAction`/`_AppendAction` 的 `--` 长选项），预扫描 argv 遇裸 `--flag`（不带 `=`）即抛 `SpaceFormNotAllowed`——判定走 action 类型，**无白名单**，新增带值 flag 无需同步维护。bool flag（`store_true`/`store_false`/`count`，无值）与位置参数（`config KEY VALUE` 等）不套用 = 约束。

> 历史脉络：本项目形式方向几经反复——早期有 `_normalize_argv` 归一化层（白名单 + stderr hint），后删除回归 argparse 原生两种形式，再一度强制空格分隔（`_reject_equals_form` + `EqualsFormNotAllowed`）；2026-07-03 最终定为强制 `=` 连接（反转前述空格强制）。结论：以 `=` 为准。

**How to apply:**

- 新增配置类子命令时，默认带交互模式（无子动作 + TTY → 进入交互逐项填）
- 命令行传值一律 `--flag=<value>`（= 连接）；项目惯例 flag 名用 kebab-case（`--model-id`，`dest=model_id`），与现有 `llmw model add --model-id=...` 一致
- **新增 bool flag 时**：直接 `add_argument(..., action="store_true"/"store_false")` 即可——bool flag 不带值，不受 = 约束，无需任何特殊处理
- **新增带值 flag 时**：直接 `add_argument("--flag", metavar="VALUE")`——`_enforce_equals_form` 自动把它纳入带值 flag 集合（靠 action 类型判定），强制 `=` 形式，无需手动注册
- 历史遗留的位置参数传值（如 `config set <key> <value>` 的 value）暂保留，改造时优先转交互式或命名 flag
- `get` / `unset` 等只需 KEY、不需要用户填自由值的操作不受此约束
- **新增带值 flag 时必须同步 `completions/`**：`cli.py:_enforce_equals_form` 靠 action 类型自动纳入新 flag（无需注册），但 `completions/{llmw.bash, llmw.fish, _llmw}` 是**手写静态脚本**——新带值 flag 要手动加到三处：bash 的 `§5` VALUE_FLAGS 列表（裸→补 `=`）+ `§4` 值补全分支；fish 的 for 循环 VALUE_FLAGS + 对应子命令 `-l flag` 补全（带值加 `-f`，动态值加 `-r -f -a`）；zsh 的 optspec `'--flag=[desc]:msg:action'`（带 `=`）。漏改 completion 不影响 CLI 校验，但 Tab 不会补 `=`

关联 [[memory-persistence-policy]]。
