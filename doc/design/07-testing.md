# 07 · 测试策略（prototype 阶段延后）

> **状态**：本批设计阶段**不编写自动化测试**——先搭 prototype，prototype 跑通后再补 test case 保护。
> 本章仅记录**未来补测试时**的策略与边界，避免 prototype 阶段写出无法测的代码。

---

## 7.1 prototype 阶段验证方式

prototype 阶段每个命令**至少手动跑一遍 happy path**，记录在 README 的 "Manual Smoke Test" 段：

| 命令 | 手动 smoke 步骤 |
| --- | --- |
| `llmw init` | 在临时目录跑 init，验证 workspace.toml 生成 + git init |
| `llmw config` | 跑 set/get/unset 各一次；非 TTY 下验证不阻塞 |
| `llmw list` | 空 workspace 跑；add 几个 wiki 后再跑 |
| `llmw wiki --name=X add` | 跑一次 add（TTY 交互），验证子目录、metadata、workspace.toml 都对 |
| `llmw wiki --name=X remove` | 跑一次 remove（不带 --purge）；再跑一次带 --purge --yes |
| `llmw wiki --name=X show` | 跑一次表格输出；再跑一次 `--json` |
| `llmw wiki --name=X config` | 跑交互模式；跑一次 `set tags a,b,c`；跑一次 `unset display_name` |
| `llmw wiki --name=X enter` | 跑 `--dry-run` 验证命令构造；跑一次真启动（不进 Claude Code 即可，Ctrl-C 退出也行） |

手动 smoke 通过 = prototype 阶段验收门槛。

---

## 7.2 未来补测试时的分层

按依赖从轻到重：

### 单元测试（无 I/O）

- `llmw.workspace.store`：TOML 解析、字段校验
- `llmw.wiki.store`：TOML 解析、tags 校验、updated_at bump
- `llmw.errors`：异常构造与 exit_code 映射
- `llmw.config`：默认路径解析、`LLMW_WORKSPACE` env var 处理

### 集成测试（tmp dir + 真文件）

- `init` → 验证 workspace.toml 内容 + git 状态
- `wiki add` → 验证子目录、metadata、workspace.toml 三者一致
- `wiki remove` → 带/不带 `--purge` 两种
- `wiki config set/unset/get` 各路径
- 原子写：故意让 tmp 创建失败（如权限），验证 cleanup

### 端到端测试（CLI 调用）

- `python -m llmw init` 在 tmp dir 跑全流程
- `python -m llmw wiki --name=X add`（非 TTY 模式 + 全 flag 形式）跑全流程
- 验证 stdout 是 JSON / 表格格式

### subprocess mock 测试

- `enter`：用 `monkeypatch subprocess.run` 验证构造的 argv
- `wiki add`：mock `setup_wiki.py`，验证成功 / 失败两种路径的回滚

---

## 7.3 未来测试的 fixture 策略

### submodule 替代

- 不在测试中真跑 `setup_wiki.py`——mock 掉
- 提供 `tests/fixtures/fake_setup_wiki.py`：只创建空 `raw/`、`wiki/`、`CLAUDE.md`，跑得快

### tmp workspace

- 每个测试用 `tmp_path`（pytest fixture）建独立 workspace
- 测试结束自动清理

### TTY 模拟

- 用 `input()` patch 模拟 TTY 输入序列
- 不真起交互终端

---

## 7.4 不测什么

明确**不**写测试的部分：

- **手动 smoke 测试**：靠人
- **CLI 真实启动 Claude Code session**：CI 起不了交互进程
- **`raw/` / `wiki/` 内容**：CLI 不读不写，由 SKILL 自己测
- **submodule 网络拉取**：CI 网络环境不稳，submodule init 只在本地

---

## 7.5 prototype 阶段代码的可测性约束

为了让未来补测试时不重构，prototype 阶段遵守：

- **业务逻辑与 CLI 入口分离**：`llmw.cli` 只做 argparse + 分派，业务在 `llmw.wiki.manager` / `llmw.workspace.manager` 里
- **文件 I/O 走 `Path` 对象 + 显式参数**：不写死路径，便于 tmp_path 注入
- **subprocess 走单一函数包装**：未来用 `monkeypatch` 替换
- **异常用 `llmw.errors` 类**：便于 `pytest.raises` 断言
- **time / uuid 等副作用来源**：未来若需要可注入；prototype 阶段直接调用即可

---

## 7.6 与 CI 集成（未来）

- pytest + coverage
- coverage gate ≥ 85%（参考之前删除的 v1 设计里的 CI 配置）
- lint matrix：py3.7 / py3.11（与本仓 yzr-skill-creator 一致）
- Markdown lint：走全局 markdownlint-cli

---

## 7.7 占位说明

- 本章**不**给出具体的测试用例（`test_*.py` 内容）
- 本章**不**给出 pytest 配置（`pyproject.toml [tool.pytest.ini_options]`）
- 本章**不**给出 CI workflow（`.github/workflows/*.yml`）

以上三块在 prototype 跑通后单独立项设计。