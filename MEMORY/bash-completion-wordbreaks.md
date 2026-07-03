---
name: bash-completion-wordbreaks
description: bash 补全调试须 pty 实测真实 readline；COMP_WORDBREAKS 默认含 = 会把 --flag= 拆成 --flag + =，补全函数须规范化 cur
metadata:
  type: feedback
---

bash 补全（`completions/llmw.bash`）调试方法 + `COMP_WORDBREAKS` 坑。

**Why:** bash 补全**不能**用"手动设 `COMP_WORDS` 调 `_llmw` 看 `COMPREPLY`"验证——手动设的 `COMP_WORDS` 不经过 readline 的 `COMP_WORDBREAKS` 分词，和真实 tab 时的 `COMP_WORDS` 不同，会得到**虚假的"通过"**。`llmw` 的 `--name=` 补全曾连错 3 轮（spawn llmw → toml 直读 → 加 `-P` 前缀），全是这个假验证导致：每轮手动调都显示 `COMPREPLY` 有值就报"修复"，但用户实测仍补不出。真实 readline 把 `llmw wiki --name=` 拆成 `[llmw wiki --name =]`（`COMP_WORDBREAKS` 默认含 `=><&|;:(:` 等），`COMP_WORDS[COMP_CWORD]` 是 `=` 而非 `--name=`，§4 的 `case --name=*` 永远不匹配 → 走分派分支 → `cur=="="` 匹配不到任何候选 → 空补全。

**How to apply:**
- **调试 bash 补全必须用 pty 实测真实 readline**：`pty.fork()` 起 `bash --rcfile ~/.bashrc -i`，`os.write(fd, b'llmw wiki --name=\t')`，读回显看补全结果（见本仓历次诊断脚本）。隔离变量用对照函数（`_fake(){ COMPREPLY=("x"); }; complete -F _fake fake`）区分"readline 机制问题" vs "函数逻辑问题"。**绝不**只调函数看 `COMPREPLY` 就下结论。
- **`COMP_WORDBREAKS` 默认含 `=`**：readline 在 tab 时按这些字符拆 word，`--flag=value` 被拆成 `--flag` + `=`（+ `value`）。补全函数里 `cur=${COMP_WORDS[COMP_CWORD]}` 拿到的是 `=` 或值片段，**不是** `--flag=value` 整体；`prev=${COMP_WORDS[COMP_CWORD-1]}` 是 `--flag`。
- **规范化 cur**（`completions/llmw.bash` 现状）：在 cur/prev 提取后，若 `prev` 是带值 flag 且 `cur` 是 `=`/`=xxx`，合并回 `--flag=` 形式以复用 `--flag=*` 分支；返回**裸 value**（readline 自动附加到 `=` 后）。**不要**给候选加 `--flag=` 前缀（pty 实测：会补成 `--name=--name=x`）。
- fish / zsh **不受影响**：fish 的 `-l flag -a vals`、zsh 的 `_arguments '--flag=[...]'` 都自动把值附加到 `=` 后，候选返回裸 value 即可。三套候选都返回裸 value，只有 bash 需在函数里处理 `COMP_WORDBREAKS` 拆词。

关联 [[cli-ux-interactive-and-named-flags]]（带值 flag 统一用 `--xxx=` 形式的约定——正是这个形式触发 `COMP_WORDBREAKS` 的 `=` 拆词）。
