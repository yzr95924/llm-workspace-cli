---
name: bash-completion-wordbreaks
description: bash 补全调试须 pty 实测真实 readline；COMP_WORDBREAKS 默认含 = 会把 --flag= 拆成 --flag + =，补全函数须规范化 cur
metadata:
  type: feedback
---

bash 补全（`completions/llmw.bash`）调试方法 + `COMP_WORDBREAKS` 坑。

**Why:** 手动设 `COMP_WORDS` 不经过 readline 的 `COMP_WORDBREAKS` 分词，会得到与真实 tab 不同的结果——假通过。`--flag=` 形式触发 `COMP_WORDBREAKS` 含 `=`，readline 把 `--name=` 拆成 `[--name =]`，补全函数必须规范化 cur。

**How to apply:**
- **调试 bash 补全必须用 pty 实测真实 readline**：`pty.fork()` 起 `bash --rcfile ~/.bashrc -i`，`os.write(fd, b'llmw wiki --name=\t')`，读回显看补全结果。隔离变量用对照函数（`_fake(){ COMPREPLY=("x"); }; complete -F _fake fake`）区分"readline 机制问题" vs "函数逻辑问题"。**绝不**只调函数看 `COMPREPLY` 就下结论。
- **`COMP_WORDBREAKS` 默认含 `=`**：`--flag=value` 被拆成 `--flag` + `=`（+ `value`）。`cur=${COMP_WORDS[COMP_CWORD]}` 拿到 `=` 或值片段，不是整体；`prev=${COMP_WORDS[COMP_CWORD-1]}` 是 `--flag`。
- **规范化 cur**（`completions/llmw.bash` 现状）：若 `prev` 是带值 flag 且 `cur` 是 `=`/`=xxx`，合并回 `--flag=` 形式；返回**裸 value**（readline 自动附加到 `=` 后）。**不要**给候选加 `--flag=` 前缀（pty 实测：会补成 `--name=--name=x`）。
- fish / zsh **不受影响**：fish 的 `-l flag -a vals`、zsh 的 `_arguments '--flag=[...]'` 都自动把值附加到 `=` 后，候选返回裸 value 即可。

关联 [[cli-ux-interactive-and-named-flags]]（带值 flag 统一用 `--xxx=` 形式的约定——正是这个形式触发 `COMP_WORDBREAKS` 的 `=` 拆词）。
