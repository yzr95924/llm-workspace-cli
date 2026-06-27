# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库工作时提供指引。

## 这是什么

`llmw` 是一个 CLI，管理一个**由 wiki 组成的 workspace**；每个 wiki 由外部的 `llm-wiki-management` skill（独立仓库）创建。CLI 本身**不做任何 LLM 推理**——`llmw enter` 以子进程方式 spawn `claude`（Claude Code），由后者完成 LLM 驱动的工作。workspace 根目录下的 `.workspace.toml` 是 wiki 元数据的唯一来源（SSOT）；CLI 不维护平行数据库。

`doc/design.md` 是权威设计规格（§1–§5 + 附录）。遇到行为层面的问题时先查它——退出码、校验规则、写盘时机、模块边界都在里面。

## 常用命令

```bash
pip install -e .          # 安装 `llmw` console script
pip install -e .[dev]     # + pytest、pytest-cov、ruff（本地开发）
llmw <command>            # 或：python -m wiki_workspace <command>

ruff format --check .     # 行宽交给 formatter 管（E501 已忽略）
ruff check .              # py37 target、line-length 100，启用 E/F/W/I

pytest -q                 # 注意：pyproject addopts 强制 --cov=wiki_workspace --cov-fail-under=85
pytest tests/test_add_cmd.py -q                                  # 单个文件
pytest tests/test_add_cmd.py::test_function -q                   # 单个测试
pytest -o addopts="" tests/test_add_cmd.py -q                    # 绕过覆盖率门槛
```

CI（`.github/workflows/test.yml`）在 **3.11** 上跑 lint，在 **3.7 + 3.11** 矩阵上跑测试。

## 架构：分层模块边界

这套分层是**刻意的设计约束**（spec §1.5），不是随手约定——加代码时务必遵守：

| 模块 | 职责 | 不可 |
| --- | --- | --- |
| `cli.py` | argparse 顶层 + 分派 + 全局 flag 接线 + 顶层错误捕获 | 放业务逻辑 |
| `commands/*_cmd.py` | 每个子命令一个文件；统一签名 `def run(args) -> int` | 直接调 argparse |
| `workspace.py` | workspace 根解析、`.workspace.toml` 读写、**原子持久化** | 调外部脚本；感知具体命令 |
| `manifest.py` | 内存模型 `Manifest`/`WikiEntry`、parse/serialize、字段**校验** | 碰文件系统（写盘走 `workspace.py`） |
| `_compat.py` | 从 skill 软导入 `slugify` / `parse_frontmatter_simple`，失败回退内置 stub | 修改 skill 的文件 |
| `errors.py` | 退出码、分类错误发射器、`CommandError` | |

**控制流：** `cli.main()` → `build_parser()` → `_dispatch()`（惰性 import 命令模块，故某模块坏了不影响 `--help`）→ `command.run(args)`。命令抛 `CommandError`，在 `main` 顶层**只捕获一次**，emit 到 stderr，并映射为退出码。

**`manifest.py` 是纯模块**，刻意保持无 import 环：它**不** import `errors`，`serialize()` 惰性 import `workspace.dump_toml`（后者只 import `errors`）。保持这一点。

## 跨切面约定

- **stdout vs stderr。** stdout 只承载机器可解析的结果；所有诊断（`[ERROR]`/`[WARN]`/`[INFO]`/`[DEBUG]`）都打到 stderr。`--json` 调用方用 `errors.render_json_result()`。绝不要把诊断 `print` 到 stdout。
- **退出码：** `0` OK · `1` 用户错误（改输入即可）· `2` 环境错误（得装东西 / 改环境）· `3` 内部 bug。由 `CommandError(exit_code, category, message, hint=...)` 承载。
- **原子写盘。** 任何对 `.workspace.toml` 的改动都走 `workspace.atomic_write`（tmp + fsync + `os.replace`），随后 `save_manifest` 重解析刚写下的文本，若重解析失败则抛 `EXIT_INTERNAL`/`internal-state-corruption`。读命令（`enter`/`list`/`show`）绝不写盘。
- **subprocess，不是 import。** 跨包/跨仓调用一律 `subprocess.run`——`add_cmd` 经它调 skill 的 `setup_wiki.py`；`enter_cmd` 经它调 `claude`。绝不 `import` skill 的包（避免 lock-step 升级）。
- **全局 flag 可放在子命令前或后**（`llmw -w X init` 与 `llmw init -w X` 都可用）。做法：把共享的 `common` parent parser 同时挂到主 parser 与每个子 parser，并用 `default=argparse.SUPPRESS`，使子 parser 的默认值不会覆盖主 parser 已解析到的值。新增全局 flag 都挂到 `common` 上。
- **校验在每个命令启动时都跑**（不止 `add`），经 `_common.load_manifest`。`error` 级阻断；`warn` 级不阻断。
- **`errors.QUIET`/`DEBUG` 是模块级全局量**，由 `cli.main` → `errors.configure()` 每次运行设一次。测试经 `conftest.py` 的 autouse `reset_errors_globals` fixture 复位。

## `llm-wiki-management` 软依赖

`_compat.find_skill_root()` 按优先级探测 4 处：`$LLM_WIKI_MANAGEMENT_PATH` → `../llm-wiki-management/SKILL.md` → `~/.claude/skills/llm-wiki-management/SKILL.md` → None。
依赖**按命令分级**（spec §1.4）：`add` 必需它（硬错误，退出码 2），`enter` 强烈推荐（warn 但仍启动 `claude`），其余命令不需要。测试用 `conftest.py` 里的 `fake_skill` fixture 搭起来。

## Python 兼容性

- `requires-python = ">=3.6"`，但按 **py37 语法**写（PEP 604/585、海象、`capture_output+text`）。3.6 本身已从 CI 移除（EOL、不在现代 runner 镜像里）。
- TOML：≥3.11 用 `tomllib`，否则 `tomli`。**没有 `tomli_w`**——`workspace.dump_toml` 是手写的、schema 专属的序列化器（安全仅因 schema 完全受控：只有带引号字符串 / `list[str]` / 裸 key）。换通用 TOML writer 前务必重审转义。
- 在 3.7 上特别地：钉 `pytest>=7,<8`（pytest 8 需 ≥3.8），且**不要**装 `[dev]`（ruff 在 3.7 上装不干净；格式化由 3.11 上的 lint job 覆盖）。

## 语言约定

代码标识符用英文；**docstring、代码注释、用户可见的 CLI 消息一律用简体中文**，以匹配现有代码。编辑时遵循此约定——例如错误 category（如 `workspace-not-initialized`）保持英文（稳定的机器契约），但其 `message`/`hint` 文本与周边 docstring 用中文。

## 记忆（仓内）

本仓的持久化记忆放在仓库根目录的 **`MEMORY/`**（纳入 git、跨 clone 共享）——**而非** Claude Code 默认的 per-project 记忆路径（`~/.claude/projects/.../memory/`）。被要求"记住"某事或要写关于本项目的任何持久笔记时，写到 `MEMORY/` 下的一个文件，并在那里的 `MEMORY.md` 索引留一行指针。一条事实一个文件。
