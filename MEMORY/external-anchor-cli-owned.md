---
name: external-anchor-cli-owned
description: 仓根红线唯一例外：raw/external/ 的 anchor + symlink 走 llmw wiki external 子命令落盘；target 仓本体永不触碰；notes 走机械 scribe
metadata:
  type: project
---

# raw/external/ anchor 写路径归 CLI

**Why:** anchor 写路径曾是仓内**唯一**一处"注册表但非 CLI 持有"的残留——schema SSOT
原来在两处散文（`AGENTS.md` raw/external 节 + skill `external-repo.md` 接入段），LLM 手写
TOML，事后靠 `external-anchor-corrupt` finding 兜底。这违反本仓其他所有注册表遵循的
"写入时代码强制 + schema SSOT 在码"模式（`workspace_models.toml` /
`wiki_metadata.toml` / `workspace.toml` 都走 store 层严格校验）。写路径入 CLI 后
消灭两处散文 schema 互相漂移的隐式风险 + 消灭 corrupt finding 的绝大部分来源
（只剩手改兜底）。

**Why 破例不破 I-1 精神：** I-1 真实底线是"代码永不创作**内容语义**"，anchor 无语义
（全是输入驱动的注册表变换 + 机械 scribe）；用"位置划线"代替"语义划线"是执行期的
可检查性优化（绝对形式便于 review/gate），anchor 例外恰是位置规则过宽的精确修正。

**How to apply:**

- **写路径入口唯一**：`llmw.content.external_anchor` 持有 `SOURCE_NAME_RE` /
  `EXTERNAL_SUBDIR` / `ANCHOR_FILENAME` / `SCHEMA_VERSION` 常量 + `load()`/`save()` +
  `cmd_add/remove/list/rebuild` + `build_subparsers`。任何新增 `raw/external/` 相关操作
  都从本模块出；不要绕开写 helper。
- **target 仓本体永不触碰**：`cmd_add` 只 read `git -C target`，`cmd_remove` 只 unlink
  wiki 侧 symlink；CLI 绝不 `git pull`/`git commit`/`rm` target。路径是普通文件/目录
  时 `cmd_remove` 拒绝（用户资产保护）。
- **notes 走机械 scribe**（不变量 I-1 第 3 类）：字节从 `--notes=...` 入参进来，与
  `ingest-diff`/`write` 同款。
- **`rebuild` 网络操作**：target 缺失 + 有 remote_url 时按 URL clone。TTY 单次确认
  或 `--yes`；非 TTY 无 `--yes` 只打计划 + exit 2 不动手（同 status 孤儿清理的确认模式）。跨 home
  布局用 `--target NAME=PATH` 覆盖，anchor 自动回写 `~/...` 形式。
- **wiki_lint 的 anchor parser** 已 1:1 平移至本模块的 `load()`；lint 用别名
  `load_anchor` 引用，**finding 名/文案零改变**（gate 面 3 + fixtures 守护；面 2 已改
  prose 镜像禁令，不再对账 finding 名）。
  改 parser 时只在本模块单点修改，lint 自动同步。

**关联**：

- AGENTS.md：开篇红线 + I-1 第 2/3 类 + 模块边界表 `llmw.content` 行 + 数据流图 external 分支
- 模板 `agents-md-template.md` raw/external 节：「LLM 可写」→「走 CLI 子命令」
- skill `external-repo.md`：接入 / 重建 shell 流程收编为 `llmw wiki external` 命令；
  §一 承接字段语义 SSOT（agent 排查损坏场景用）+ §三 保留跨主机重建原理
