# raw/external/——外部代码仓接入与跨主机重建

> **维护方**：接入决策归用户 + agent；**symlink + anchor 写路径**统一走
> `llmw wiki external` 子命令；target 仓本体永不触碰（此处仅指 **CLI 命令**自身行为——
> **agent** 对 target 的读写权限以 wiki 根 `AGENTS.md` `raw/external/` 节为准）。命令面
> 细节在 `AGENTS.md`（会话常驻）；anchor 字段 schema 归 CLI 持有——本文件只留 agent
> 判断与不宜从命令输出直接得知的语义

## 首次接入

agent 主导三项判断（CLI 帮不上）：

- **命名协商**：`--name` 必须 kebab-case 短名，由 agent 与用户共同决定（如
  `linux-kernel` / `ray`）；格式校验归 CLI——非法即拒，报错自带格式要求
- **target 路径**：推荐 `~/src/<name>` home-relative 形式（跨主机重建友好；CLI rebuild
  自动回写此形式）
- **notes 文本**：可选，agent 自由写（机械 scribe 入 anchor）

命令：`llmw wiki external add <target> --name=<n> [--notes=...]`（CLI 自动建 symlink +
读 git 身份字段 + 原子写 anchor；target 必须已存在）

## sources: 元素类型（external 特化）

`raw/external/<symlink>/...` 可指向**文件或目录**：symlink 目标本身是 git 仓（即目录），
可用作整仓语料；普通 raw 路径（非 `raw/external/`）的 sources 仍要求指向**文件**。
lint 只校验可访问性——细则见 `llmw wiki lint --explain=external-target-dead` 等
external-* 条目

## 跨主机重建

**原理**：symlink 机器相关**不进 git**；anchor（`.symlink-anchor.toml`）**进 git**，记录
接入意图——`remote_url` / `branch` 跨主机稳定，任何机器可还原；**不**记 commit（anchor
记录意图，commit 是机器快照会腐坏）。gitignore 块字节 canonical = 实例 `.gitignore`

```bash
llmw wiki external rebuild --yes                                  # 同 home 布局直接重建
llmw wiki external rebuild --target=linux=/home/new/src/linux --yes  # 跨 home 布局（可重复）
```

rebuild 自动处理 skip / relink / clone + checkout + 建 symlink / `unrebuildable`（无
remote_url 时用 `--target=NAME=PATH` 覆盖，或 remove 后重新 add）——按输出行动。
验证：`llmw wiki lint` 的 external-* findings 应为 0

## 漂移刷新

用户日常 `git pull` target 仓**不**触发任何自动检测——身份字段极少变化，无需刷新；
"摘要是否过期"由用户判断，需要时重 ingest 对应 source 页（`target` 字段不动）

## 反模式

> 本节只收**本流程特有**的反模式；通用纪律见 wiki 根 `AGENTS.md`

- **不要用 `llmw wiki external remove` 删"孤儿 symlink"**（anchor 无对应 entry 的
  symlink）——remove 只处理注册表声明；按报错提示手工 `rm` + 排查漏录原因
- **损坏的 anchor 不要手改**——CLI 拒绝覆盖（保护修复现场）；按 stderr 提示备份 /
  修复 / 重建

---

**失败兜底原则**：`llmw wiki external` 命令报错与 lint to_action 均为
actionable-first 设计——消息自带修复路径，按 stderr / lint 输出行动即可；本节不留
静态对照表，避免与 runtime 文案产生回声耦合
