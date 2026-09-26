# raw/external/：外部代码仓接入与跨主机重建

**分工**：接入决策归用户 + agent；agent 对 target 的读写权限与命令细则以 wiki 根
`AGENTS.md` `raw/external/` 节为准

## 首次接入

agent 主导三项判断（CLI 帮不上）：

- **命名**：`--name` 必须 kebab-case 短名，agent 与用户共同决定（如 `linux-kernel` /
  `ray`）
- **target 路径**：推荐 `~/src/<name>` home-relative 形式（跨主机重建友好，rebuild 自动回写
  此形式）
- **notes 文本**：可选，agent 自由写（机械 scribe 入 anchor）

命令：`llmw wiki external add <target> --name=<n> [--notes=...]`（target 必须已存在）

## sources: 元素类型

`raw/external/<symlink>/...` 可指向**文件或目录**：symlink 目标是 git 仓目录，可整仓作
语料；普通 raw 路径（非 `raw/external/`）的 sources 仍要求指向**文件**。lint 只校验可
访问性；细则见 `llmw wiki lint --explain=external-target-dead` 等 external-* 条目

## 跨主机重建

```bash
llmw wiki external rebuild --yes                                  # 同 home 布局直接重建
llmw wiki external rebuild --target=linux=/home/new/src/linux --yes  # 跨 home 布局（可重复）
```

rebuild 会按 entry 状态自动选动作并打印计划，按打印出的计划执行；完成后 `llmw wiki lint`
的 external-* findings 应为 0

## 漂移刷新

用户日常 `git pull` target 仓**不**触发任何自动检测，身份字段极少变化，无需刷新；"摘要是否
过期"由用户判断，需要时重 ingest 对应 source 页（`target` 字段不动）

## 反模式

命令报错与 lint `to_action` 均自带修复路径，按 stderr / 输出行动即可
