# eval 夹具：语义覆盖 + 骨架现生成

用例目录不是沙箱。5 个可构建夹具只存语义文件（raw / 内容页 / 少量配置），
wiki 骨架由脚本现生成；纯骨架的版本变化不需要动语义夹具，内容页契约变化仍要
同步夹具。

```bash
python3 scripts/test/build_wiki_eval.py <case-id> <sandbox>
# agent 工作目录 = <sandbox>/<根名>
```

布局：

- `_bases/ml-notes/`：共享语义基底（mamba/attention raw、source/concept 页、
  tags 生长段）；基底取各用例相同的 plain 版本
- `<case-id>/<根>/build.conf`：该根的 `llmw wiki add` 参数 + `base` + `orphans`
  （wiki/ 相对路径，逗号分隔，跳过 index add，用于造 orphan-page）
- `<case-id>/<根>/` 其余文件：按路径覆盖基底
- `query-scope-current-wiki` 有两个根：`current`（任务 wiki）与同级诱饵
  `finetune-notes`（含 LoRA 结论 + 复现标记），判据依赖 agent 不读取同级根

构建顺序：

1. 生成骨架
2. 拷基底，再拷本用例覆盖文件
3. `write index add`（orphans 跳过；reviewed 页的 `✓ reviewed` 标识由该命令按
   frontmatter 派生）
4. `write log --op=ingest`（按 source 页 `created` 排序）
5. 追加 tags 生长段，并统一刷新 raw 文件 mtime

stale 信号是日期比较产物：页 frontmatter `updated` 固定在过去，构建收尾统一
刷新 raw mtime，恒晚于页，`ingest-diff --check-stale` 恒可复现。

行为实跑前提（其余按 skill 维护流程的定性测试循环执行）：

- 行为 agent 的工作目录与 `LLM_WIKI_ROOT` 都指向被测根（双根用例为 `current/`）
- 判据要求的命令与工具调用轨迹、前后 diff 存进本例 outputs；只读用例中
  outputs 是唯一写入例外
