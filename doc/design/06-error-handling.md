# 06 · 错误处理与可靠性

本章规范 CLI 的异常分类、退出码、错误输出格式与可靠性约束。

---

## 6.1 异常层次（`llmw.errors`）

所有自定义异常继承自 `LlmwError`（统一基类）：

```python
class LlmwError(Exception):
    """所有 CLI 异常的基类，含 exit_code 与 user_message。"""
    exit_code: int = 1
    user_message: str = ""

# ===== 用户错误（exit_code = 1） =====

class WorkspaceNotFound(LlmwError):
    """workspace 根解析失败"""
    exit_code = 1

class WorkspaceExists(LlmwError):
    """init 时目标路径已存在且非空"""
    exit_code = 1

class WikiNotFound(LlmwError):
    """wiki 名不在 workspace.toml [wikis] 中"""
    exit_code = 1

class WikiExists(LlmwError):
    """wiki 名重复"""
    exit_code = 1

class WikiDirMissing(LlmwError):
    """wiki 子目录被外部 rm"""
    exit_code = 1

class PurgeRequiresConfirmation(LlmwError):
    """非 TTY 下 --purge 需要 --yes"""
    exit_code = 1

class InvalidConfigKey(LlmwError):
    """config 命令 KEY 不在白名单"""
    exit_code = 1

class KeyNotUnsettable(LlmwError):
    """config unset 命令 KEY 不可 unset"""
    exit_code = 1

class ConfigKeyMissing(LlmwError):
    """config get 命令 KEY 不存在"""
    exit_code = 1

class MissingRequiredFlag(LlmwError):
    """非 TTY 下 metadata 字段缺 flag"""
    exit_code = 1

class SchemaVersionUnsupported(LlmwError):
    """workspace.toml / wiki_metadata.toml 的 schema_version 不被当前 CLI 支持"""
    exit_code = 1

class InvalidWikiName(LlmwError):
    """wiki 名格式非法"""
    exit_code = 1

class InvalidTagValue(LlmwError):
    """tags 元素格式非法"""
    exit_code = 1

# ===== 环境错误（exit_code = 2） =====

class SkillMissing(LlmwError):
    """SKILL submodule 未初始化"""
    exit_code = 2

class SkillScriptMissing(LlmwError):
    """submodule 在但 setup_wiki.py 文件缺失"""
    exit_code = 2

class SetupFailed(LlmwError):
    """setup_wiki.py 退出码非 0"""
    exit_code = 2

class ClaudeNotFound(LlmwError):
    """claude 不在 PATH"""
    exit_code = 2

class GitUnavailable(LlmwError):
    """git 命令不可用 / 失败"""
    exit_code = 2

class PythonUnavailable(LlmwError):
    """sys.executable 不可执行（极少见）"""
    exit_code = 2

# ===== 内部错误（exit_code = 3） =====

class InternalError(LlmwError):
    """未预期的内部异常"""
    exit_code = 3
```

### 异常 → 退出码映射

| 异常类别 | 退出码 |
| --- | --- |
| 用户错误 | 1 |
| 环境错误 | 2 |
| 内部错误 | 3 |

---

## 6.2 退出码总表

| 退出码 | 含义 | 触发场景示例 |
| --- | --- | --- |
| 0 | 成功 | 所有正常命令路径 |
| 1 | 用户错误 | 参数非法、wiki 不存在、KEY 不在白名单、缺必填 flag |
| 2 | 环境错误 | SKILL submodule 未初始化、setup_wiki.py 失败、claude 不在 PATH、git 不可用 |
| 3 | 内部错误 | 未捕获的 Python 异常、TOML 损坏不可读、os.replace 失败等 |

脚本用户（如 `set -e` 的 shell）可通过退出码做粗粒度判断：

- `0`：成功
- `1`：输入问题，修了能重试
- `2`：环境问题，需用户介入
- `3`：CLI bug，需报 issue

---

## 6.3 错误输出格式

### stdout vs stderr 分工

| 信息 | 输出到 | 理由 |
| --- | --- | --- |
| 正常结果（表格 / JSON / 提示"已创建"） | stdout | 可被管道 / 重定向消费 |
| 错误信息 | stderr | 不污染 stdout 数据流 |
| 警告（⚠ 前缀的软提示） | stderr | 不阻断但需用户看到 |
| `--json` 模式错误 | stderr | 仍输出人类可读错误；stdout 不输出 |

### 错误格式

```
[llmw] error: <user_message>
[llmw] hint: <optional remediation>
```

示例：

```
$ llmw wiki --name=foo show
[llmw] error: wiki 'foo' 不在当前 workspace 中
[llmw] hint: 运行 `llmw list` 查看已注册的 wiki
[llmw] exit code: 1
```

### 警告格式

```
[llmw] warning: <message>
```

示例：

```
[llmw] warning: wiki 'foo' 缺少 CLAUDE.md, session 启动后将没有 schema 上下文
```

---

## 6.4 错误场景汇总

### 通用（所有命令）

| 场景 | 行为 |
| --- | --- |
| 当前 cwd 不在 workspace 内 | `WorkspaceNotFound`，提示设 `LLMW_WORKSPACE` 或 `cd` 进默认 |
| `workspace.toml` 缺失 | `WorkspaceNotFound` |
| `workspace.toml` 存在但 TOML 解析失败 | `InternalError`，给出解析错误位置（来自 tomllib） |
| `workspace.toml` 的 schema_version 不被支持 | `SchemaVersionUnsupported`，提示用户升级 CLI |

### `llmw init`

| 场景 | 行为 |
| --- | --- |
| `--path` 已存在且非空 | `WorkspaceExists`，保留现场 |
| `git init` 失败 | `GitUnavailable`，提示安装 git |
| 父目录无写权限 | `WorkspaceExists`（mkdir 失败抛 OSError），转为 CLI 异常 |

### `llmw config`

| 场景 | 行为 |
| --- | --- |
| KEY 不在白名单 | `InvalidConfigKey` |
| `set` 时原子写失败 | `InternalError`，清理 tmp 文件 |
| `unset` KEY 不可 unset | `KeyNotUnsettable` |
| `get` KEY 不存在 | `ConfigKeyMissing` |
| 非 TTY 无参数运行 | 打印字段列表 + 用法，**不**报错；退出码 0 |

### `llmw list`

| 场景 | 行为 |
| --- | --- |
| `[wikis]` 表为空 | 表格只打表头，JSON 输出 `[]`；无错 |
| 某些 wiki 路径缺失（被外部 rm） | 标 ⚠；不阻断 |

### `llmw wiki --name=<name> add`

| 场景 | 行为 |
| --- | --- |
| `--name` 格式非法 | `InvalidWikiName` |
| `--name` 已注册 | `WikiExists` |
| SKILL submodule 缺失 | `SkillMissing` |
| `setup_wiki.py` 失败 | `SetupFailed`，**完整回滚**（子目录、wiki_metadata.toml、workspace.toml 都恢复原状） |
| 非 TTY 下缺 metadata flag | `MissingRequiredFlag`，列出哪些 flag 缺失 |
| 交互中 Ctrl-C | 视为"跳过剩余 metadata"，已收集的写入文件 |

### `llmw wiki --name=<name> remove`

| 场景 | 行为 |
| --- | --- |
| `--name` 不存在 | `WikiNotFound` |
| `--purge` + 非 TTY + 无 `--yes` | `PurgeRequiresConfirmation` |
| `rm -rf` 失败 | `InternalError`（权限问题等） |

### `llmw wiki --name=<name> show`

| 场景 | 行为 |
| --- | --- |
| `--name` 不存在 | `WikiNotFound` |
| wiki 目录缺失 | 显示 `existence.*` 全 false；不阻断 |
| `wiki_metadata.toml` 缺失 | 字段显示 `-`；不阻断 |
| `CLAUDE.md` 缺失 | 同上 |

### `llmw wiki --name=<name> config`

| 场景 | 行为 |
| --- | --- |
| `--name` 不存在 | `WikiNotFound` |
| KEY 不在白名单 | `InvalidConfigKey` |
| `set tags` 值含非法字符 | `InvalidTagValue` |
| 原子写失败 | `InternalError` |

### `llmw wiki --name=<name> enter`

| 场景 | 行为 |
| --- | --- |
| `--name` 不存在 | `WikiNotFound` |
| wiki 子目录缺失 | `WikiDirMissing` |
| CLAUDE.md 缺失 | ⚠ 警告（stderr），不阻断 |
| `wiki_metadata.toml` 缺失 | ⚠ 警告（stderr），不阻断 |
| `claude` 不在 PATH | `ClaudeNotFound`（除非 `--dry-run`） |
| `claude` 子进程非 0 退出 | CLI 透传子进程退出码 |

---

## 6.5 原子写策略（汇总）

所有 CLI 写入的元数据文件（workspace.toml / wiki_metadata.toml）走**统一原子写**：

```python
def atomic_write(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
```

要点：

- `os.replace` 是 POSIX 原子操作（同一文件系统下）
- tmp 文件用 pid 后缀避免并发冲突
- 失败时清理 tmp，不留垃圾
- fsync 确保断电也不丢

详见 `04-data-model.md` 的 4.5 节。

---

## 6.6 add 命令的回滚策略

`wiki add` 涉及多个文件写入，任何一步失败都要回滚：

```
步骤 3:  mkdir <workspace>/<name>      ─┐
步骤 4:  setup_wiki.py                 ─┤ 全部回滚 = 删除子目录
步骤 5:  wiki_metadata.toml            ─┤
步骤 7:  workspace.toml                ─┘
```

### 回滚伪代码

```python
def add(name, ...):
    created_files = []
    try:
        workspace_root = ensure_workspace()
        check_unique(workspace_root, name)        # 失败 → WikiExists, 无副作用
        wiki_path = workspace_root / name
        wiki_path.mkdir()                         # 失败 → OSError
        if not no_setup:
            run_setup_wiki(wiki_path, topic)      # 失败 → SetupFailed, 回滚
        write_metadata(wiki_path, ...)            # 失败 → InternalError, 回滚
        update_workspace_toml(workspace_root, ...) # 失败 → InternalError, 回滚
    except LlmwError:
        rollback(wiki_path, created_files)
        raise
```

### 回滚顺序（反向）

1. 从 `workspace.toml [wikis]` 删条目（若已加）
2. 删 `wiki_metadata.toml`（若已写）
3. （`--no-setup` 不删 raw/ wiki/ CLAUDE.md，因为是用户自己建的）
4. （非 `--no-setup`）删整个 `<workspace>/<name>` 子目录

### `--no-setup` 回滚差异

- 不删子目录（用户自己建的，可能有内容）
- 仅删 CLI 自己写的 `wiki_metadata.toml` 与 `workspace.toml` 条目
- 若子目录里有非 CLI 写的 `wiki_metadata.toml`（用户手工写的同名文件），保留——CLI 不覆盖用户文件

---

## 6.7 调试支持

### `--debug` 全局 flag

开启后：

- 异常 traceback 完整打印（stderr）
- 执行的子进程命令完整打印（before run）
- 解析的中间值（model 解析链、最终 model、workspace 解析路径）打印

### `--quiet` / `-q` 全局 flag

开启后：

- 抑制 INFO 级别输出（如 "已写入" 提示）
- ⚠ WARNING 仍打印
- 错误信息仍打印

### 默认级别

- INFO：默认打印
- WARNING：默认打印
- ERROR：默认打印

详见 `01-workspace-management.md` 提及的全局 flag 设计。

---

## 6.8 不可恢复错误

以下情况 CLI **不**尝试自动恢复，**必须**用户介入：

- workspace.toml 损坏无法解析
- wiki_metadata.toml 损坏无法解析
- SKILL submodule 目录存在但内部结构损坏
- git 命令本身不可用

行为：报错 + 给出修复建议（人工编辑文件、重新初始化 submodule 等），**不**做任何写操作以免覆盖用户数据。