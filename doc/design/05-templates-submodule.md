# 05 · Templates 目录与 SKILL Submodule 集成

本章规范 CLI 仓库的两个外部依赖：`templates/` 目录（CLI 自己维护的元数据模板）与
`my_SKILL/llm-wiki-management`（作为 git submodule 引入的 wiki 管理 skill）。

---

## 5.1 `templates/` 目录

**位置**：CLI 仓库根目录（`templates/`）

**性质**：git 入库；CLI 自己维护

### 文件清单

```
templates/
├── wiki_metadata.toml.template    # wiki add 时拷出实例的源
└── CLAUDE.md.template             # 预留, Phase 1 不消费
```

详见 `04-data-model.md` 的 4.3 节。

### 维护规则

- 模板文件由 CLI 维护者修改，**不**自动同步到已存在的 wiki 实例
- 已存在的 `wiki_metadata.toml` 是 wiki 自有的副本——模板改了不影响已存在的实例
- 升级路径：CLI 升级 + 用户手动重新跑 `llmw wiki --name=<name> config ...` 把字段填入新模板
- **不做自动迁移**（Phase 1 简化版）

---

## 5.2 SKILL Submodule 集成

**位置**：`my_SKILL/llm-wiki-management/`（CLI 仓库根目录下的 submodule）

**性质**：git submodule，指向 `@my_SKILL/llm-wiki-management` 的某个 tag 或 commit

### 为什么用 submodule

- **版本固定**：CLI 与 SKILL 的版本可以独立演进，但运行时锁住当前 commit
- **零打包成本**：CLI 不打包 SKILL 内容；用户 clone CLI 仓后跑 `git submodule update --init` 拉取
- **API 稳定**：CLI 只调用 `setup_wiki.py` 一个入口，SKILL 内部重构不影响 CLI
- **离线友好**：submodule 一旦初始化，setup_wiki.py 不需要重新下载

### `.gitmodules` 引用

```ini
[submodule "my_SKILL/llm-wiki-management"]
    path = my_SKILL/llm-wiki-management
    url = https://github.com/yzr95924/my_SKILL.git
    branch = main
```

### 用户拉取 CLI 时

```bash
git clone https://github.com/yzr95924/llmw.git
cd llmw
git submodule update --init --recursive    # 必须, 否则 SkillMissing
```

README 必须明确写出 submodule 初始化步骤；否则 `wiki add` 报 `SkillMissing`。

---

## 5.3 SKILL 脚本路径解析

`llmw.wiki.manager` 调用 `setup_wiki.py` 时的查找顺序：

| 优先级 | 来源 | 说明 |
| --- | --- | --- |
| 1 | `$LLMW_SKILL_SETUP_SCRIPT` | 用户手动覆盖（CI / 自定义路径场景） |
| 2 | 相对 CLI 包内位置固定路径 | `<llmw-package>/../../my_SKILL/llm-wiki-management/scripts/setup_wiki.py` |
| 3 | — | 找不到 → 报错 `SkillMissing` |

### 相对路径解析逻辑

```python
import llmw  # 包
skill_setup = (
    Path(llmw.__file__).parent.parent.parent
    / "my_SKILL"
    / "llm-wiki-management"
    / "scripts"
    / "setup_wiki.py"
)
```

`llmw.__file__` 是 `llmw/__init__.py` 的路径：

- `parent` → `<repo>/llmw/`
- `parent.parent` → `<repo>/`
- `parent.parent.parent` → `<repo>/..`  （不对，是 `<repo>/` 才对）

修正：实际是 `parent.parent`：

- `llmw/__init__.py` → `parent` = `<repo>/llmw/`
- `parent.parent` = `<repo>/`
- `+ /my_SKILL/llm-wiki-management/scripts/setup_wiki.py` = `<repo>/my_SKILL/llm-wiki-management/scripts/setup_wiki.py`

### 子进程调用

```python
subprocess.run(
    [sys.executable, str(skill_setup), topic],
    cwd=wiki_abs_path,
    check=False,  # 失败由 returncode 处理
)
```

- **必须**用 `sys.executable`（用户当前 Python 解释器），不能用裸 `python`/`python3`
- `cwd` 设为 `<workspace>/<name>`——让 `setup_wiki.py` 在 wiki 子目录内运行
- 返回 0 视为成功；非 0 抛 `SetupFailed`

---

## 5.4 错误场景

| 场景 | 异常 | 提示 |
| --- | --- | --- |
| submodule 未初始化（目录为空 / 缺失） | `SkillMissing` | "请运行 `git submodule update --init` 初始化 SKILL" |
| `setup_wiki.py` 文件不存在但目录在 | `SkillScriptMissing` | "SKILL submodule 损坏，请 `git submodule update --force`" |
| `setup_wiki.py` 退出码非 0 | `SetupFailed` | 透传 stderr，给"setup_wiki.py 失败，已回滚"提示 |
| `sys.executable` 不可执行 | `PythonUnavailable` | 极少见——CLI 自身都在跑 |

### CLI 不捕获的 SKILL 内部错误

`setup_wiki.py` 内部错误（如模板缺失、权限问题）由 SKILL 自己处理；CLI 只看 returncode + 透传 stderr。

---

## 5.5 SKILL 版本管理

### 锁定策略

- CLI 仓 `.gitmodules` 锁定 SKILL 的 branch / commit
- 推荐：CLI 仓库根 commit 把 submodule 锁到 SKILL 的某个 tag（如 `v0.1.0`）
- 这样 CLI 的每个 release 对应固定的 SKILL 版本

### 升级流程

1. CLI 仓库所有者 bump `.gitmodules` 的 submodule 引用
2. 测试新 SKILL 版本与现有 CLI 的兼容性（主要是 `setup_wiki.py` 的命令行接口）
3. 通过后 commit + push CLI 仓库
4. 用户 `git pull` 后 `git submodule update` 拉新 SKILL

### 兼容性约束

CLI 调用 `setup_wiki.py` 的方式**仅一行**：

```python
subprocess.run([sys.executable, setup_wiki_path, topic])
```

只要 SKILL 维持：

- `python setup_wiki.py <topic>` 调用方式
- 在 cwd 下创建 `raw/` + `wiki/` 子目录
- 在 cwd 下创建 `CLAUDE.md`

CLI 与 SKILL 即兼容。SKILL 内部任意重构不破坏 CLI。

---

## 5.6 文件依赖图

```
CLI 仓库根
├── bin/llmw                          # CLI 可执行入口
├── llmw/                             # CLI Python 包
│   └── wiki/manager.py               # 调用 setup_wiki.py
├── templates/                        # CLI 自己维护的元数据模板
│   ├── wiki_metadata.toml.template
│   └── CLAUDE.md.template            # 预留
├── my_SKILL/                         # git submodule (来自 my_SKILL 仓)
│   └── llm-wiki-management/
│       ├── SKILL.md
│       ├── scripts/
│       │   ├── setup_wiki.py         # ← CLI 唯一调用入口
│       │   ├── ingest_diff.py        # CLI 不调用 (留 SKILL session 内)
│       │   └── lint_wiki.py          # CLI 不调用 (留 SKILL session 内)
│       └── references/
│           └── ...
├── tests/
├── doc/
├── MEMORY/
└── pyproject.toml
```

| 文件 / 目录 | 由谁提供 | 何时更新 |
| --- | --- | --- |
| `bin/llmw` | CLI 仓 | 跟随 CLI release |
| `llmw/` | CLI 仓 | 跟随 CLI release |
| `templates/wiki_metadata.toml.template` | CLI 仓 | 跟随 CLI release |
| `my_SKILL/...` | SKILL 仓（submodule） | 用户 `git submodule update` 拉新 |

---

## 5.7 与 build / install 的关系

CLI 安装脚本（Phase 2/3 设计）只关心 `bin/llmw` + Python 包，不涉及 submodule 与 templates：

- `bin/llmw` 复制到 `~/.local/bin/llmw`
- `llmw` Python 包安装到目标 site-packages（或以可编辑模式安装）
- `templates/` 跟随 Python 包一起安装（数据文件）
- `my_SKILL/` submodule **不**被打包——用户使用时由 CLI 自己从本地路径读（submodule 已经初始化了）