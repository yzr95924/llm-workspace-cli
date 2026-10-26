# raw/external/：外部代码仓接入与跨主机重建

分工：接入决策归用户 + agent；接入物 = symlink + anchor。anchor 是外部仓元数据，
经 `llmw wiki external` 落盘，agent **不**手改；孤儿 symlink 等 CLI 无法直接接管的异常现场，
确认后只删该 symlink，再走 `external add` 重建；损坏 anchor 先备份，经用户确认后删除并逐项
重新 add。agent 对 target 仓的读写权限与命令细则以 wiki 根 `AGENTS.md` 的 `raw/external/`
节为准

## 首次接入

三项**取值**由 agent 与用户定（形态校验与归一化归 CLI，报错自明）：

- **命名**：短名（如 `linux-kernel` / `ray`）
- **target 路径**：建议 `~/src/<name>`（跨主机重建友好）
- **notes 文本**：可选，agent 自由写

## 消费 target 代码

- **分析代码**：围绕问题解释，不把复述实现细节当作分析；可引用关键函数和变量名
  支撑结论
- 把 target 内容落成 source 页走 ingest 流程，`sources` 字段的元素类型规则见
  [章节](page-templates.md#source资料页)

## 跨主机重建

命令与 `--target` / `--yes` 形式见 wiki 根 `AGENTS.md` 的 `raw/external/` 节；
完成后 `llmw wiki lint` 的 external-* findings 应为 0

## 漂移刷新

用户日常 `git pull` target 仓**不**触发任何自动检测：anchor 身份字段极少变化，
无需刷新。"摘要是否过期"由用户判断，需要时重 ingest 对应 source 页
（`target` 字段不动）
