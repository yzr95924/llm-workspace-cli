# eval 夹具：语义覆盖 + 骨架现生成

用例目录不是沙箱。5 个行为夹具只存语义文件（raw / 内容页 / 少量配置），
wiki 骨架由脚本现生成，`WIKI_FORMAT_VERSION` 升级不需要动夹具：

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

构建顺序：生成骨架 → 拷基底 → 拷覆盖 → `write index add`（orphans 跳过；
reviewed 页补挂 `✓ reviewed` 标识）→ `write log --op=ingest`（按 source 页
`created` 排序）→ 追加 tags 生长段。

stale 信号是日期基准产物：页 frontmatter `updated` 固定在过去，raw 在构建/拷入
沙箱时刷新 mtime，恒晚于页 → `ingest-diff --check-stale` 恒复现。

已知 CLI 不一致（只报告，不在本仓修）：`write index add` 不生成
`✓ reviewed` 标识，lint `index-review-badge-drift` 却按标识校验；构建脚本在
index add 后按 frontmatter 补挂。
