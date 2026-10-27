# raw/external/：外部代码仓接入与跨主机重建

接入决策由用户与 agent 共同确定；接入物是 symlink + anchor。anchor 记录外部仓元数据，
经 `llmw wiki external` 落盘，agent 不手改。孤儿 symlink、损坏 anchor 等 CLI 无法直接
接管的异常，按 `llmw wiki lint --explain=all` 对应 finding 的修法处理，其中删除动作先经
用户确认。agent 对 target 仓的读写权限与命令细则以 wiki 根 `AGENTS.md` 的
`raw/external/` 节为准。

## 首次接入

三项取值由 agent 与用户确定（形态校验与归一化由 CLI 负责，报错说明自明）：

- 命名：短名（如 `linux-kernel` / `ray`）
- target 路径：建议 `~/src/<name>`（跨主机重建友好）
- notes 文本：可选，agent 自由写

## 消费 target 代码

- 分析代码：围绕问题解释，可引用关键函数和变量名支撑结论，不把复述实现细节当分析
- 把 target 内容落成 source 页走 ingest 流程，`sources` 字段的元素类型规则见
  [章节](page-templates.md#source资料页)

## 跨主机重建

命令与 `--target` / `--yes` 用法见 `llmw wiki external rebuild --help`；完成后跑
`llmw wiki lint`，确认与本次重建相关的 external-* finding 已消除。

## 漂移刷新

用户日常对 target 仓 `git pull` 不触发任何自动检测：anchor 身份字段极少变化，无需刷新。
摘要是否过期由用户判断，需要时对对应 source 页重新执行 ingest（`target` 字段不动）。
