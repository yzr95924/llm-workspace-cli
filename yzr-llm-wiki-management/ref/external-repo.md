# raw/external/：外部代码仓接入

外部仓以 symlink + anchor 接入，不做仓库拷贝。anchor、symlink 与异常修法以
`llmw wiki external --help` 和 `llmw wiki lint --explain=all` 输出为准；删除动作先经
用户确认。target 仓的读写边界以 wiki 根 `AGENTS.md` 的 `raw/external/` 节为准。

## 接入

与用户确定短名（如 `linux-kernel`）、target 路径（建议 `~/src/<name>`）和可选 notes，
再按 `llmw wiki external add --help` 接入。接入后跑 `llmw wiki lint`，确认相关
external-* finding 已消除。

## 消费 target 代码

- 分析代码时围绕问题解释，可引用关键函数和变量名，不把复述实现细节当分析
- target 仓在 ingest / query / lint / upgrade 中只读；只有用户明确要求修改代码时才写入
- 把 target 内容落成资料页走 ingest 流程，source 页字段见
  [章节](page-templates.md#source资料页)

## 重建与刷新

- 换主机或 target 移动后，按 `llmw wiki external rebuild --help` 重建，再跑 lint 复核
- 用户对 target 仓 `git pull` 不触发自动刷新；摘要是否过期由用户判断，需要时对相关
  source 页重新 ingest，anchor target 不动
