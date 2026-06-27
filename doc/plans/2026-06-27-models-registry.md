# llmw — 模型注册表（Models Registry）+ Per-Wiki Profile 绑定 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在 v1 上叠加 workspace 级 `models.toml`（profile 注册表，含 `model_id` / `base_url` / `api_key` 全字段）和 per-wiki `<wiki>/profile.toml`（profile 名绑定）。`llmw enter` 从字符串 ID 升级为 profile 解析；完全删除 v1 的 `workspace.default_model` / `wikis.<name>.model` 字段（无 migration）。

**架构：** 三个新纯叶子模块 `models.py` / `profile.py`（镜像 `manifest.py` 的 `parse`/`serialize`/`validate` 模式）—— 顶部仅 stdlib、`serialize` 惰性 import `workspace`。`workspace.py` 扩展 8 个新函数（`models_*` 与 `profile_*` 对称）。`commands/_common.py` 加 `load_models(args)` / `load_profile(wiki_root)`。新增 `commands/models_cmd.py`（4 actions）与 `commands/wiki_config_cmd.py`（交互式）。`enter_cmd.py` 重写为 profile 解析器（echo / warn / refuse 三路径）。`manifest.py` 与 CLI flags 同步清理（删 `--model` / `--default-model` / `--profile`）。两层 gitignore 屏蔽：workspace `.gitignore` 含 `models.toml`，wiki `.gitignore` 含 `profile.toml`。

**技术栈：** Python ≥ 3.6（target py37 语法）、`tomllib`/`tomli` 读 TOML、自写的 schema 专属 TOML writer（不引入 `tomli_w`）、`argparse`、`getpass`、`pytest` + `pytest-cov`、`ruff`。CI 矩阵 py3.7 + py3.11（沿用 v1）。

**规格来源：** `doc/2026-06-27-models-registry-design.md`（§1 数据模型、§2 命令、§3 模块边界、§4 错误、§5 测试、§6 安全）。开工前请先读它——本计划不复述设计理由。

---

## 待解决的设计缺口（开工前必读）

设计稿对大部分事项都已定调。有五处需在执行期确认或现场拍板，照做即可，无需重新讨论：

1. **Claude Code / Anthropic SDK 的环境变量名。** 设计稿 §2.7 写 `ANTHROPIC_BASE_URL` 与 `ANTHROPIC_AUTH_TOKEN` 作占位；实现期第一件事是跑 `claude --help` + 翻 Anthropic SDK 源码核对（若变量名错，`enter --dry-run` 会立刻暴露——dry-run 打印 `proc_env`）。`test_enter_cmd.py` 里的断言统一用 `enter_cmd.BASE_URL_ENV` / `enter_cmd.API_KEY_ENV` 常量，便于一处改处处一致。

2. **`wiki config clear` 的语义。** 设计稿 §6.4 推荐**删除 profile.toml**（vs 留空文件）。**裁决：删除文件**——避免空文件歧义，且 `enter` 已用"文件存在但 model 缺/空 → error vs 文件不存在 → fallback to default"区分两个状态。

3. **profile.toml 中 `model` 字段取值的特殊字面量 `clear`。** 设计稿 §2.6 把 `clear` 当 unbind 操作，但用户理论上可建一个 kebab-case 名为 `clear` 的 profile……实际不可能：`clear` 不是 kebab-case（kebab 限定 `[a-z0-9]+(-[a-z0-9]+)*`，单字 `clear` 是合法 kebab！）。**裁决：** profile 名 `clear` 一律被 `models validate` 拒（实现时 `models.py` 在 `validate()` 里把 `clear` 加进 reserved 名单），与 `wiki config` 输入 `clear` 当 unbind 永不会冲突。

4. **`atomic_write` 的文件权限。** v1 `workspace.atomic_write` 用 `tempfile.mkstemp` 默认 0600 + `os.replace` 保留源文件 mode——`models.toml` / `profile.toml` 创建后自动 0600。**裁决：沿用，不改 `atomic_write` 签名。** 不对既有非 0600 文件做 chmod（尊重用户调整）。任务 2/8 的 `save_models` / `save_profile` 测试用 `stat().st_mode & 0o777 == 0o600` 断言。

5. **`dump_models_toml` 中 `default=""` 的写法。** 空 default 是合法状态（"未设 default"），dump 时也得写 `default = ""`（不是省略——否则 `parse` 第二次走会拿默认 fallback，与首读不一致）。**裁决：** 始终 emit `default = "<escaped>"`，即便空串。`dump_profile_toml` 同理始终 emit `model = "<escaped>"`。

---

## 文件结构

锁定分解。每个文件单一职责；一起变更的文件放一起。

```
llm_workspace_cli/
├── pyproject.toml                      # 不改（已有 --cov-fail-under=85）
├── README.md                           # 任务 20 — 补充 models / wiki config / enter 用法
├── wiki_workspace/
│   ├── errors.py                       # 不改
│   ├── workspace.py                    # 任务 2, 8 — 加 8 个 models_*/profile_* 函数
│   ├── manifest.py                     # 任务 13 — 删 model/default_model/KNOWN_MODELS/SETTABLE
│   ├── models.py                       # 任务 1 — 纯叶子（镜像 manifest.py）
│   ├── profile.py                      # 任务 7 — 纯叶子（镜像 models.py）
│   ├── _compat.py                      # 不改
│   ├── cli.py                          # 任务 4, 10, 17 — 加 models/wiki 子 parser；删 --model/--default-model/--profile
│   └── commands/
│       ├── __init__.py                 # 不改
│       ├── _common.py                  # 任务 3, 9 — 加 load_models / load_profile
│       ├── init_cmd.py                 # 任务 6, 14 — 删 --default-model；append workspace .gitignore
│       ├── add_cmd.py                  # 任务 15 — 删 --model/--profile；append wiki .gitignore
│       ├── config_cmd.py               # 任务 16 — SETTABLE 不再含 "model"
│       ├── enter_cmd.py                # 任务 12 — 重写：profile 解析（echo/warn/refuse）
│       ├── models_cmd.py               # 任务 5 — NEW（add/list/remove/set-default）
│       ├── wiki_config_cmd.py          # 任务 11 — NEW（交互式）
│       └── （其余命令不动）
└── tests/
    ├── conftest.py                     # 不改
    ├── test_models.py                  # 任务 1 — NEW（100% 覆盖）
    ├── test_profile.py                 # 任务 7 — NEW（100% 覆盖）
    ├── test_workspace.py               # 任务 2, 8 — EXTEND（models/profile I/O）
    ├── test_common.py                  # 任务 3, 9 — EXTEND（load_models / load_profile helpers）
    ├── test_models_cmd.py              # 任务 5 — NEW
    ├── test_wiki_config_cmd.py         # 任务 11 — NEW（交互式 monkeypatch）
    ├── test_enter_cmd.py               # 任务 12 — REWRITE（profile 解析 + env 注入）
    ├── test_init_cmd.py                # 任务 6, 14 — EXTEND + 删 --default-model 测试
    ├── test_add_cmd.py                 # 任务 15 — EXTEND + 删 --model/--profile 测试
    ├── test_config_cmd.py              # 任务 16 — 删 model key 测试
    ├── test_manifest.py                # 任务 13 — 删 KNOWN_MODELS / WikiEntry.model / default_model 测试
    ├── test_cli.py                     # 任务 4, 10, 17 — EXTEND（parser help 断言）
    └── test_e2e_smoke.py               # 任务 19 — EXTEND（init → models add → wiki config → enter）
```

**依赖 DAG（无环）：**
```
errors ← workspace ← {commands, manifest.serialize, models.serialize, profile.serialize}
manifest.parse / manifest.validate ← commands（_common.load_manifest）
models.parse / models.validate ← commands（_common.load_models）
profile.parse / profile.validate ← commands（_common.load_profile / wiki_config_cmd）
profile.validate 函数体内惰性 import models（profile.py 顶部仍干净）
_compat ← commands（add / show / enter 软探测）
```

关键不变量：`models.py` / `profile.py` 都是纯叶子（顶部仅 stdlib），互不依赖；`workspace.py` 是中间层；`commands/*` 在顶层 import `errors` / `workspace` / `manifest` / `models` / `profile` / `_compat`。

---

## 每个任务的通用约定

- **TDD：** 先写失败的测试，运行，确认它因"正确的原因"失败，再写最小实现，确认通过，提交。
- **跑单个测试：** `python -m pytest tests/<file>.py::<test_name> -v`。
- **跑全量：** `python -m pytest -q`（注意 `--cov-fail-under=85`）。
- **提交信息风格：** `feat:` / `test:` / `chore:` / `fix:`——每次提交一个逻辑变更。
- 任何需要"今天日期"的测试都注入日期（monkeypatch `wiki_workspace.workspace.today_iso`）——**不要**断言真实时钟。
- 行宽 ≤ 100（ruff `line-length = 100`）。
- **TOML reader：** `tomllib` (≥3.11) / `tomli`（<3.11）——沿用 v1 顶部 try/except 模式。
- **TOML writer：** 自写 schema 专属（`dump_models_toml` / `dump_profile_toml`），不引入 `tomli_w`。
- **api_key 永远不打印明文：** 任何 `--debug` / `emit_*` / 测试断言里 profile dump 都用 `api_key=***`。
- **0600 文件权限：** `atomic_write` 默认即 0600；不要手工 chmod。

---

### 任务 1：`models.py` — workspace 级 profile 注册表（纯叶子）

**文件：**
- 创建：`wiki_workspace/models.py`、`tests/test_models.py`
**对应 spec：** §1.2–1.4。镜像 `manifest.py` 的结构与约定——纯模块、顶部仅 stdlib、`serialize` 惰性 import `workspace`。

- [ ] **第 1 步：写失败测试**

`tests/test_models.py`：
```python
from wiki_workspace import models

SAMPLE = """\
default = "anthropic-prod"

[[models]]
name = "anthropic-prod"
model_id = "claude-opus-4-8"
base_url = "https://api.anthropic.com"
api_key = "sk-ant-secret"

[[models]]
name = "thirdparty-vertex"
model_id = "claude-opus-4-8"
base_url = "https://custom.example.com"
api_key = "tp-secret"
"""


def test_parse_builds_registry():
    r = models.parse(SAMPLE)
    assert r.default == "anthropic-prod"
    assert len(r.models) == 2
    p = r.models["anthropic-prod"]
    assert p.model_id == "claude-opus-4-8"
    assert p.api_key == "sk-ant-secret"
    assert r.models["thirdparty-vertex"].base_url == "https://custom.example.com"


def test_parse_missing_default_means_unset():
    r = models.parse('[[models]]\nname = "x"\nmodel_id = "m"\nbase_url = "b"\napi_key = "k"\n')
    assert r.default == ""
    assert "x" in r.models


def test_parse_empty_models_array_legal():
    r = models.parse('default = ""\n')
    assert r.models == {}
    assert r.default == ""


def test_serialize_round_trips():
    r = models.parse(SAMPLE)
    text = models.serialize(r)
    r2 = models.parse(text)
    assert r2.default == r.default
    assert {n: (p.model_id, p.base_url, p.api_key) for n, p in r2.models.items()} == \
        {n: (p.model_id, p.base_url, p.api_key) for n, p in r.models.items()}


def test_serialize_empty_registry():
    r = models.ModelRegistry(default="", models={})
    text = models.serialize(r)
    assert 'default = ""' in text
    r2 = models.parse(text)
    assert r2.models == {}
    assert r2.default == ""


def test_validate_clean():
    r = models.parse(SAMPLE)
    issues = models.validate(r)
    assert [i for i in issues if i.severity == "error"] == []


def test_validate_missing_required_fields():
    r = models.ModelRegistry(default="x", models={"x": models.ModelEntry("x", "", "b", "k")})
    issues = models.validate(r)
    errs = [i for i in issues if i.severity == "error"]
    assert any("model_id" in i.message for i in errs)


def test_validate_duplicate_name_fails():
    text = '''default = "x"
[[models]]
name = "x"
model_id = "m"
base_url = "b"
api_key = "k"
[[models]]
name = "x"
model_id = "m2"
base_url = "b2"
api_key = "k2"
'''
    issues = models.validate(models.parse(text))
    errs = [i for i in issues if i.severity == "error"]
    assert any("重复" in i.message or "重复" in i.message.lower() or "重复" in i.message for i in errs)


def test_validate_default_must_exist():
    text = SAMPLE.replace('default = "anthropic-prod"', 'default = "ghost"')
    issues = models.validate(models.parse(text))
    errs = [i for i in issues if i.severity == "error"]
    assert any("default" in i.message and "ghost" in i.message for i in errs)


def test_validate_non_kebab_name_fails():
    r = models.ModelRegistry(
        default="",
        models={"Bad_Name": models.ModelEntry("Bad_Name", "m", "b", "k")},
    )
    issues = models.validate(r)
    assert any(i.severity == "error" and "kebab" in i.message for i in issues)


def test_validate_clear_name_is_reserved():
    """'clear' 是 wiki config 的 unbind 关键字；models.toml 不允许 profile 名 = clear"""
    r = models.ModelRegistry(
        default="",
        models={"clear": models.ModelEntry("clear", "m", "b", "k")},
    )
    issues = models.validate(r)
    assert any(i.severity == "error" and "clear" in i.message for i in issues)


def test_validate_unknown_top_level_warns_not_fails():
    text = SAMPLE + '\nunknown_top = "x"\n'
    issues = models.validate(models.parse(text))
    assert any(i.severity == "warn" for i in issues)
    assert not [i for i in issues if i.severity == "error"]


def test_validate_unknown_field_in_entry_warns():
    text = SAMPLE.replace(
        'api_key = "sk-ant-secret"',
        'api_key = "sk-ant-secret"\ntemperature = 0.5',
    )
    issues = models.validate(models.parse(text))
    assert any(i.severity == "warn" for i in issues)
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_models.py -v`
预期：FAIL——`ModuleNotFoundError: No module named 'wiki_workspace.models'`

- [ ] **第 3 步：写 `wiki_workspace/models.py`**

```python
"""workspace 级 profile 注册表内存模型 + parse/serialize/validate。纯模块：
不碰文件系统、不碰 errors。镜像 manifest.py 的约定（spec §3.2）。"""

import re
from typing import Dict, List

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED_NAMES = {"clear"}  # wiki config 的 unbind 关键字（spec §6.4 裁决 #3）


class ModelEntry:
    def __init__(self, name, model_id, base_url, api_key):
        self.name = name
        self.model_id = model_id
        self.base_url = base_url
        self.api_key = api_key

    def to_dict(self):
        return {
            "name": self.name,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "api_key": self.api_key,
        }


class ModelRegistry:
    """default + Dict[str, ModelEntry]。"""

    def __init__(self, default, models):
        self.default = default  # str；"" 表示"未设 default"
        self.models = models  # Dict[str, ModelEntry]（保持插入顺序）

    def to_data(self):
        """序列化中间态：default + 按数组形式给出 entries（spec §1.2 决定 [[models]] 而非 [models.<name>]）。"""
        return {
            "default": self.default,
            "models": [e.to_dict() for e in self.models.values()],
        }


class Issue:
    def __init__(self, severity, category, message, field=None):
        self.severity = severity  # "error" | "warn"
        self.category = category
        self.message = message
        self.field = field


def parse(text):
    """把 TOML 文本解析成 ModelRegistry。语法错误时抛 tomllib.TOMLDecodeError
    （调用方映射为 models-file-parse-failed）。未知顶层 / 未知 entry 字段在此不报错；
    语义校验放在 validate()。"""
    try:
        import tomllib  # py>=3.11
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    data = tomllib.loads(text)

    default = data.get("default", "")
    entries: Dict[str, ModelEntry] = {}
    for raw in data.get("models", []):
        name = raw.get("name", "")
        entries[name] = ModelEntry(
            name=name,
            model_id=raw.get("model_id", ""),
            base_url=raw.get("base_url", ""),
            api_key=raw.get("api_key", ""),
        )
    return ModelRegistry(default=default, models=entries)


def serialize(r):
    """经 workspace.dump_models_toml（惰性 import，保持 models 在 import 期为纯模块）。"""
    from wiki_workspace.workspace import dump_models_toml

    return dump_models_toml(r.to_data())


def validate(r):
    """返回 list[Issue]。'error' 阻断命令；'warn' 不阻断。"""
    issues: List[Issue] = []
    seen = set()

    known_entry_fields = {"name", "model_id", "base_url", "api_key"}

    for name, e in r.models.items():
        if not name:
            issues.append(Issue("error", "models-validation-failed", "profile 缺 name 字段"))
            continue
        if not KEBAB_RE.match(name):
            issues.append(
                Issue("error", "models-validation-failed", "profile 名 '{}' 必须 kebab-case".format(name))
            )
        if name in RESERVED_NAMES:
            issues.append(
                Issue(
                    "error",
                    "models-validation-failed",
                    "profile 名 '{}' 是保留字（wiki config 用作 unbind 关键字）".format(name),
                )
            )
        if name in seen:
            issues.append(Issue("error", "models-validation-failed", "profile 名 '{}' 重复".format(name)))
        seen.add(name)

        if not e.model_id:
            issues.append(
                Issue(
                    "error",
                    "models-validation-failed",
                    "profile '{}' 缺 model_id".format(name),
                )
            )
        if not e.base_url:
            issues.append(
                Issue(
                    "error",
                    "models-validation-failed",
                    "profile '{}' 缺 base_url".format(name),
                )
            )
        if not e.api_key:
            issues.append(
                Issue(
                    "error",
                    "models-validation-failed",
                    "profile '{}' 缺 api_key".format(name),
                )
            )

    if r.default and r.default not in r.models:
        issues.append(
            Issue(
                "error",
                "models-validation-failed",
                "default 指向不存在的 profile '{}'".format(r.default),
            )
        )

    return issues


def load_and_validate(text):
    """解析 + 校验。语法错误时抛 tomllib 解析异常（调用方映射为 models-file-parse-failed）。
    返回 (ModelRegistry, list[Issue])。"""
    r = parse(text)
    return r, validate(r)
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_models.py -v`
预期：PASS（12 passed）。`serialize` 路径会因 `workspace.dump_models_toml` 还不存在而失败——任务 2 完成后才全绿。**临时绕开：** 在任务 2 之前，跑 `pytest tests/test_models.py -v -k "not serialize and not round_trip"` 验证 parse/validate 已绿。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/models.py tests/test_models.py
git commit -m "feat(models): registry data model, parse, validate (serialize stubbed until task 2)"
```

---

### 任务 2：`workspace.py` 扩展 — models.toml I/O + 原子写 + 0600

**文件：**
- 修改：`wiki_workspace/workspace.py`（追加 4 个函数 + 1 个常量）
- 修改：`tests/test_workspace.py`（追加 models I/O 测试）
**对应 spec：** §1.5、§3.3。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_workspace.py`：
```python
from wiki_workspace import models


def test_models_file_path(tmp_path):
    from wiki_workspace.workspace import models_file_path, models_filename
    assert models_filename() == "models.toml"
    assert models_file_path(tmp_path) == tmp_path / "models.toml"


def test_dump_models_toml_round_trip():
    from wiki_workspace.workspace import dump_models_toml
    data = {
        "default": "anthropic-prod",
        "models": [
            {"name": "anthropic-prod", "model_id": "claude-opus-4-8",
             "base_url": "https://api.anthropic.com", "api_key": "sk-ant"},
            {"name": "tp", "model_id": "claude-opus-4-8",
             "base_url": "https://x.com", "api_key": "tp-secret"},
        ],
    }
    text = dump_models_toml(data)
    r = models.parse(text)
    assert r.default == "anthropic-prod"
    assert len(r.models) == 2
    assert r.models["tp"].base_url == "https://x.com"


def test_dump_models_toml_empty_registry():
    from wiki_workspace.workspace import dump_models_toml
    text = dump_models_toml({"default": "", "models": []})
    assert 'default = ""' in text
    r = models.parse(text)
    assert r.default == ""
    assert r.models == {}


def test_dump_models_toml_escapes_quotes_and_backslashes():
    from wiki_workspace.workspace import dump_models_toml
    text = dump_models_toml({
        "default": "",
        "models": [{
            "name": "x", "model_id": 'm"d',
            "base_url": "https://x.com/\\path", "api_key": "k\\k",
        }],
    })
    r = models.parse(text)
    assert r.models["x"].model_id == 'm"d'
    assert r.models["x"].base_url == "https://x.com/\\path"
    assert r.models["x"].api_key == "k\\k"


def test_load_models_missing_file_returns_empty_registry(tmp_path):
    from wiki_workspace.workspace import load_models
    r = load_models(tmp_path)
    assert r.default == ""
    assert r.models == {}


def test_save_models_creates_file_with_0600(tmp_path):
    from wiki_workspace.workspace import save_models, models_file_path
    r = models.ModelRegistry(default="p1", models={
        "p1": models.ModelEntry("p1", "m", "https://x", "k"),
    })
    save_models(tmp_path, r)
    path = models_file_path(tmp_path)
    assert path.is_file()
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_save_models_round_trip(tmp_path):
    from wiki_workspace.workspace import load_models, save_models
    r = models.ModelRegistry(default="p1", models={
        "p1": models.ModelEntry("p1", "claude-opus-4-8", "https://x", "k"),
        "p2": models.ModelEntry("p2", "claude-sonnet-4-6", "https://y", "k2"),
    })
    save_models(tmp_path, r)
    r2 = load_models(tmp_path)
    assert r2.default == "p1"
    assert {n: e.api_key for n, e in r2.models.items()} == {"p1": "k", "p2": "k2"}
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_workspace.py -v -k "models"`
预期：FAIL——`AttributeError: module 'wiki_workspace.workspace' has no attribute 'models_file_path'`（或类似）

- [ ] **第 3 步：扩展 `wiki_workspace/workspace.py`**

在文件末尾追加：
```python
# --- models.toml 接口（spec §3.3）---------------------------------------
def models_filename():
    return "models.toml"


def models_file_path(root):
    return Path(root) / models_filename()


def _models_toml_escape(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def dump_models_toml(data):
    """schema 专属序列化器（spec §1.5）。安全因 schema 受控：default 是带引号字符串；
    models 是数组，每条 entry 仅含 4 个带引号字符串字段。"""
    lines = []
    lines.append('default = "{}"'.format(_models_toml_escape(data.get("default", ""))))
    lines.append("")
    for e in data.get("models", []):
        lines.append("[[models]]")
        lines.append('name = "{}"'.format(_models_toml_escape(e.get("name", ""))))
        lines.append('model_id = "{}"'.format(_models_toml_escape(e.get("model_id", ""))))
        lines.append('base_url = "{}"'.format(_models_toml_escape(e.get("base_url", ""))))
        lines.append('api_key = "{}"'.format(_models_toml_escape(e.get("api_key", ""))))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_models(root):
    """读 + 解析 models.toml；文件缺失返回空 registry（合法状态，不报错）。
    文件存在但 TOML 语法错误抛 tomllib.TOMLDecodeError（调用方映射为 models-file-parse-failed）。"""
    p = models_file_path(root)
    if not p.is_file():
        return models.ModelRegistry(default="", models={})
    text = p.read_text(encoding="utf-8")
    return models.parse(text)


def save_models(root, registry):
    """原子写 + 重解析自检（spec §1.5）。失败抛 internal-state-corruption。"""
    text = dump_models_toml(registry.to_data())
    atomic_write(models_file_path(root), text)
    try:
        models.parse(text)
    except Exception as exc:
        raise errors.CommandError(
            errors.EXIT_INTERNAL,
            "internal-state-corruption",
            "写盘后重解析 models.toml 失败：{}".format(exc),
            hint="检查磁盘空间 / 权限",
        )
```

在 `workspace.py` 顶部 import 区追加一行（紧跟 `from wiki_workspace import errors`）：

```python
from wiki_workspace import errors, models  # models 无环：其顶部无 import workspace；serialize 内部惰性 import
```

上面的 `load_models` / `save_models` 函数体里直接用 `models.ModelRegistry` / `models.parse` —— 这一行 import 解决了名字查找。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_workspace.py tests/test_models.py -v`
预期：PASS（`test_models.py` 全部 12 + `test_workspace.py` models 7 = 19 通过）。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): models.toml I/O + atomic write + 0600 permissions"
```

---

### 任务 3：`commands/_common.py` 扩展 — `load_models(args)` helper

**文件：**
- 修改：`wiki_workspace/commands/_common.py`（追加 1 个函数）
- 修改：`tests/test_common.py`（追加测试）
**对应 spec：** §3.3、§3.5。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_common.py`：
```python
from wiki_workspace import models


def test_load_models_missing_file_returns_empty(tmp_path):
    from wiki_workspace.commands import _common
    args = type("A", (), {"workspace": str(tmp_path)})()
    r = _common.load_models(args)
    assert r.default == ""
    assert r.models == {}


def test_load_models_returns_registry(tmp_path):
    from wiki_workspace.commands import _common
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1",
        models={"p1": models.ModelEntry("p1", "m", "https://x", "k")},
    ))
    args = type("A", (), {"workspace": str(tmp_path)})()
    r = _common.load_models(args)
    assert r.default == "p1"
    assert "p1" in r.models
```

> **注意：** `test_load_models_returns_registry` 用了 `workspace.save_models`——确认 `tests/test_common.py` 顶部有 `from wiki_workspace import workspace`。若没有就追加。

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_common.py -v -k "load_models"`
预期：FAIL——`AttributeError: module 'wiki_workspace.commands._common' has no attribute 'load_models'`

- [ ] **第 3 步：扩展 `wiki_workspace/commands/_common.py`**

在文件末尾追加：
```python
def load_models(args):
    """解析 workspace 根、读 + 解析 models.toml。文件缺失返回空 registry（合法）；
    TOML 语法错误抛 CommandError(models-file-parse-failed)。"""
    root = resolve_root(args)
    try:
        return workspace.load_models(root)
    except Exception as exc:  # tomllib.TOMLDecodeError
        raise errors.CommandError(
            errors.EXIT_ENV_ERROR, "models-file-parse-failed", str(exc)
        )
```

并在文件顶部 `from wiki_workspace import errors, manifest, workspace` 追加 `, models`：
```python
from wiki_workspace import errors, manifest, models, workspace
```

> **import 顺序无环：** `models.py` 顶部不 import `commands._common`；`_common.py` 反向 import `models` 安全。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_common.py -v`
预期：PASS。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/_common.py tests/test_common.py
git commit -m "feat(commands): _common.load_models helper"
```

---

### 任务 4：`cli.py` 扩展 — `models` 子 parser

**文件：**
- 修改：`wiki_workspace/cli.py`
- 修改：`tests/test_cli.py`
**对应 spec：** §2.1。本任务只接子 parser 与分派表，命令实现留给任务 5。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_cli.py`：
```python
def test_models_subparser_help(capsys):
    from wiki_workspace import cli
    p = cli.build_parser()
    with pytest.raises(SystemExit) as ei:
        p.parse_args(["models", "--help"])
    assert ei.value.code == 0


def test_models_list_invokes_list_action(monkeypatch):
    from wiki_workspace import cli
    captured = {}
    monkeypatch.setattr(cli, "_dispatch", lambda f, a: captured.update(f=f, a=a) or 0)
    cli.main(["models", "list"])
    assert captured["f"] == "models_list"


def test_models_add_invokes_add_action(monkeypatch):
    from wiki_workspace import cli
    captured = {}
    monkeypatch.setattr(cli, "_dispatch", lambda f, a: captured.update(f=f, a=a) or 0)
    cli.main(["models", "add", "--name", "x"])
    assert captured["f"] == "models_add"
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_cli.py -v -k "models_"`
预期：FAIL（无 `models` 子 parser）。

- [ ] **第 3 步：扩展 `wiki_workspace/cli.py`**

在 `sub = p.add_subparsers(...)` 后插入（参考 v1 init/list 写法）：
```python
    # models 子命令组（spec §2.1）
    sp_models = sub.add_parser("models", help="管理 workspace 级 model profiles", parents=[common])
    sp_models_sub = sp_models.add_subparsers(dest="models_action", metavar="<action>")

    # models add
    sp_ma = sp_models_sub.add_parser("add", help="新增 profile")
    sp_ma.add_argument("--name")
    sp_ma.add_argument("--model-id")
    sp_ma.add_argument("--base-url")
    sp_ma.add_argument("--set-default", action="store_true")
    sp_ma.set_defaults(func="models_add")

    # models list
    sp_ml = sp_models_sub.add_parser("list", help="列出 profile")
    sp_ml.set_defaults(func="models_list")

    # models remove
    sp_mr = sp_models_sub.add_parser("remove", help="删除 profile")
    sp_mr.add_argument("name")
    sp_mr.add_argument("--yes", "-y", action="store_true")
    sp_mr.set_defaults(func="models_remove")

    # models set-default
    sp_ms = sp_models_sub.add_parser("set-default", help="设置/清空 default profile")
    sp_ms.add_argument("name", nargs="?")
    sp_ms.add_argument("--clear", action="store_true")
    sp_ms.set_defaults(func="models_set_default")
```

并在 `_dispatch` 函数内的 `from wiki_workspace.commands import (...)` 与 `table = {...}` 同步追加：
```python
    from wiki_workspace.commands import (
        add_cmd,
        config_cmd,
        enter_cmd,
        init_cmd,
        list_cmd,
        models_cmd,        # NEW
        remove_cmd,
        show_cmd,
    )

    table = {
        ...
        "models_add": models_cmd.run_add,
        "models_list": models_cmd.run_list,
        "models_remove": models_cmd.run_remove,
        "models_set_default": models_cmd.run_set_default,
    }
```

> **提前暴露的 import：** 任务 5 之前 `models_cmd` 模块还不存在——`_dispatch` 是惰性 import（仅在分派时触发），`_dispatch` 未被调用的测试（如 `models_subparser_help`）不受影响。被调用的测试（`models_list_invokes_list_action`）会用 monkeypatch 替换 `_dispatch`，根本走不到 import。任务 5 完成后即绿。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_cli.py -v -k "models_"`
预期：PASS（3 passed）。其它 cli 测试维持现状。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/cli.py tests/test_cli.py
git commit -m "feat(cli): models subparser + dispatch wiring"
```

---

### 任务 5：`commands/models_cmd.py` — 4 actions

**文件：**
- 创建：`wiki_workspace/commands/models_cmd.py`、`tests/test_models_cmd.py`
**对应 spec：** §2.2–2.5。

- [ ] **第 1 步：写失败测试**

`tests/test_models_cmd.py`：
```python
from wiki_workspace import errors, models, workspace
from wiki_workspace.commands import models_cmd


def _args(**kw):
    base = dict(
        workspace=None, json=False, quiet=False, debug=False,
        name=None, model_id=None, base_url=None, set_default=False,
    )
    base.update(kw)
    return type("A", (), base)()


def _args_remove(name, **kw):
    base = dict(workspace=None, json=False, quiet=False, debug=False, name=name, yes=False)
    base.update(kw)
    return type("A", (), base)()


def _args_set_default(name=None, clear=False, **kw):
    base = dict(workspace=None, json=False, quiet=False, debug=False, name=name, clear=clear)
    base.update(kw)
    return type("A", (), base)()


def _seed_ws(tmp_path):
    workspace.save_manifest(tmp_path, __import__("wiki_workspace").manifest.empty_manifest("2026-06-26"))


def _patch_getpass(monkeypatch, value="sk-test"):
    import getpass as _gp
    monkeypatch.setattr(models_cmd.getpass, "getpass", lambda prompt="": value)


def test_add_creates_profile(tmp_path, monkeypatch):
    _seed_ws(tmp_path)
    _patch_getpass(monkeypatch)
    code = models_cmd.run_add(_args(
        workspace=str(tmp_path), name="p1", model_id="claude-opus-4-8",
        base_url="https://x", set_default=True,
    ))
    assert code == 0
    r = workspace.load_models(tmp_path)
    assert "p1" in r.models
    assert r.default == "p1"


def test_add_duplicate_name_fails(tmp_path, monkeypatch):
    _seed_ws(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="", models={"p1": models.ModelEntry("p1", "m", "b", "k")},
    ))
    _patch_getpass(monkeypatch)
    code = models_cmd.run_add(_args(
        workspace=str(tmp_path), name="p1", model_id="m", base_url="b",
    ))
    assert code == errors.EXIT_USER_ERROR


def test_add_workspace_not_initialized(tmp_path):
    code = models_cmd.run_add(_args(
        workspace=str(tmp_path), name="p1", model_id="m", base_url="b",
    ))
    assert code == errors.EXIT_USER_ERROR


def test_add_redacts_api_key_in_debug(monkeypatch, capsys):
    _seed_ws(monkeypatch)
    # 简单做法：注入 secret 到 env，触发 emit_debug，断言不在 capsys 里
    import os
    os.environ["_TEST_SECRET_DO_NOT_LEAK"] = "sk-leak-me"
    try:
        errors.emit_debug("api_key=sk-leak-me")
        assert "sk-leak-me" not in capsys.readouterr().err
    finally:
        del os.environ["_TEST_SECRET_DO_NOT_LEAK"]


def test_list_table_redacts_api_key(tmp_path, capsys):
    _seed_ws(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1",
        models={"p1": models.ModelEntry("p1", "claude-opus-4-8", "https://x", "sk-secret-LEAK")},
    ))
    code = models_cmd.run_list(_args(workspace=str(tmp_path)))
    assert code == 0
    captured = capsys.readouterr()
    assert "sk-secret-LEAK" not in captured.out
    assert "sk-secret-LEAK" not in captured.err
    assert "p1" in captured.out


def test_list_json_omits_api_key(tmp_path, capsys):
    import json as _json
    _seed_ws(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1",
        models={"p1": models.ModelEntry("p1", "claude-opus-4-8", "https://x", "sk-LEAK")},
    ))
    code = models_cmd.run_list(_args(workspace=str(tmp_path), json=True))
    assert code == 0
    obj = _json.loads(capsys.readouterr().out)
    assert obj["default"] == "p1"
    assert "api_key" not in obj["result"]["models"][0]


def test_list_empty_registry(tmp_path, capsys):
    _seed_ws(tmp_path)
    code = models_cmd.run_list(_args(workspace=str(tmp_path)))
    assert code == 0
    out = capsys.readouterr().out
    assert "(unset)" in out or "default:" in out


def test_remove_existing_profile(tmp_path):
    _seed_ws(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1",
        models={"p1": models.ModelEntry("p1", "m", "b", "k")},
    ))
    code = models_cmd.run_remove(_args_remove("p1", workspace=str(tmp_path), yes=True))
    assert code == 0
    r = workspace.load_models(tmp_path)
    assert "p1" not in r.models
    assert r.default == ""  # default 自动清空


def test_remove_nonexistent_fails(tmp_path):
    _seed_ws(tmp_path)
    code = models_cmd.run_remove(_args_remove("ghost", workspace=str(tmp_path), yes=True))
    assert code == errors.EXIT_USER_ERROR


def test_set_default_existing(tmp_path):
    _seed_ws(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="",
        models={
            "p1": models.ModelEntry("p1", "m", "b", "k"),
            "p2": models.ModelEntry("p2", "m", "b", "k"),
        },
    ))
    code = models_cmd.run_set_default(_args_set_default("p1", workspace=str(tmp_path)))
    assert code == 0
    assert workspace.load_models(tmp_path).default == "p1"


def test_set_default_clear(tmp_path):
    _seed_ws(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1", models={"p1": models.ModelEntry("p1", "m", "b", "k")},
    ))
    code = models_cmd.run_set_default(_args_set_default(clear=True, workspace=str(tmp_path)))
    assert code == 0
    assert workspace.load_models(tmp_path).default == ""


def test_set_default_nonexistent_fails(tmp_path):
    _seed_ws(tmp_path)
    code = models_cmd.run_set_default(_args_set_default("ghost", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_models_cmd.py -v`
预期：FAIL——`ModuleNotFoundError: ...models_cmd`

- [ ] **第 3 步：写 `wiki_workspace/commands/models_cmd.py`**

```python
"""llmw models add|list|remove|set-default — workspace 级 profile 管理（spec §2.2–2.5）。"""

import getpass

from wiki_workspace import errors, models, workspace
from wiki_workspace.commands import _common


def _emit_debug_profile(p):
    """api_key 一律 redact（spec §4.3）。"""
    errors.emit_debug(
        "profile name={} model_id={} base_url={} api_key=***".format(
            p.name, p.model_id, p.base_url
        )
    )


def run_add(args):
    try:
        root = _common.resolve_root(args)
        _common.require_initialized(root)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    if not name:
        errors.emit_error("models-validation-failed", "--name 必填（profile 名）")
        return errors.EXIT_USER_ERROR

    model_id = args.model_id
    base_url = args.base_url
    api_key = getpass.getpass("api_key: ")

    existing = workspace.load_models(root)
    if name in existing.models:
        errors.emit_error("model-already-exists", "profile '{}' 已存在".format(name))
        return errors.EXIT_USER_ERROR

    entry = models.ModelEntry(name=name, model_id=model_id, base_url=base_url, api_key=api_key)
    new_models = dict(existing.models)
    new_models[name] = entry
    new_default = name if args.set_default else existing.default
    new_registry = models.ModelRegistry(default=new_default, models=new_models)

    issues = models.validate(new_registry)
    errs = [i for i in issues if i.severity == "error"]
    for i in issues:
        if i.severity == "warn":
            errors.emit_warn(i.message)
    if errs:
        for i in errs:
            errors.emit_error(i.category, i.message)
        return errors.EXIT_USER_ERROR

    try:
        workspace.save_models(root, new_registry)
    except errors.CommandError as exc:
        errors.emit_error(exc.category, exc.message, exc.hint)
        return exc.exit_code

    _emit_debug_profile(entry)
    errors.emit_info("已添加 profile '{}'".format(name))
    return errors.EXIT_OK


def run_list(args):
    try:
        registry = _common.load_models(args)
    except errors.CommandError as exc:
        return exc.exit_code

    if getattr(args, "json", False):
        out = {
            "default": registry.default,
            "models": [
                {"name": e.name, "model_id": e.model_id, "base_url": e.base_url}
                for e in registry.models.values()
            ],
        }
        print(errors.render_json_result(errors.EXIT_OK, result=out))
        return errors.EXIT_OK

    if not registry.models:
        print("(无 profile)")
        print("default: {}".format(registry.default or "(unset)"))
        return errors.EXIT_OK

    print("{:<24} {:<24} {}".format("NAME", "MODEL_ID", "BASE_URL"))
    for e in registry.models.values():
        print("{:<24} {:<24} {}".format(e.name, e.model_id, e.base_url))
    print("")
    print("default: {}".format(registry.default or "(unset)"))
    return errors.EXIT_OK


def run_remove(args):
    try:
        root = _common.resolve_root(args)
        _common.require_initialized(root)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    registry = workspace.load_models(root)
    if name not in registry.models:
        errors.emit_error("model-not-found", "profile '{}' 不存在".format(name))
        return errors.EXIT_USER_ERROR

    if not args.yes:
        errors.emit_error(
            "confirm-required",
            "删除 profile '{}' 需 --yes".format(name),
            hint="llmw models remove {} --yes".format(name),
        )
        return errors.EXIT_USER_ERROR

    new_models = {n: e for n, e in registry.models.items() if n != name}
    new_default = "" if registry.default == name else registry.default
    new_registry = models.ModelRegistry(default=new_default, models=new_models)

    try:
        workspace.save_models(root, new_registry)
    except errors.CommandError as exc:
        errors.emit_error(exc.category, exc.message, exc.hint)
        return exc.exit_code

    errors.emit_info("已删除 profile '{}'".format(name))
    return errors.EXIT_OK


def run_set_default(args):
    try:
        root = _common.resolve_root(args)
        _common.require_initialized(root)
    except errors.CommandError as exc:
        return exc.exit_code

    registry = workspace.load_models(root)

    if args.clear:
        new_default = ""
    elif args.name:
        if args.name not in registry.models:
            errors.emit_error("model-not-found", "profile '{}' 不存在".format(args.name))
            return errors.EXIT_USER_ERROR
        new_default = args.name
    else:
        errors.emit_error("usage", "需传 <name> 或 --clear")
        return errors.EXIT_USER_ERROR

    new_registry = models.ModelRegistry(default=new_default, models=registry.models)
    try:
        workspace.save_models(root, new_registry)
    except errors.CommandError as exc:
        errors.emit_error(exc.category, exc.message, exc.hint)
        return exc.exit_code

    if new_default:
        errors.emit_info("default 已指向 '{}'".format(new_default))
    else:
        errors.emit_info("default 已清空")
    return errors.EXIT_OK
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_models_cmd.py -v`
预期：PASS（12 passed）。

- [ ] **第 5 步：跑全量，确保现有测试未受 import 影响**

运行：`python -m pytest -q`
预期：PASS。**注意：** `test_cli.py` 里 `models_list_invokes_list_action` 这类 monkeypatch `_dispatch` 的测试已在任务 4 通过；未被 monkeypatch 的 `cli.main([...])` 真实路径仍可能在任务 14 之前因 `--default-model` 等 flag 已删而报错——任务 17 之后再跑全量。

- [ ] **第 6 步：提交**

```bash
git add wiki_workspace/commands/models_cmd.py tests/test_models_cmd.py
git commit -m "feat(models): add/list/remove/set-default with secret redaction"
```

---

### 任务 6：`init_cmd.py` 扩展 — workspace `.gitignore` append

**文件：**
- 修改：`wiki_workspace/commands/init_cmd.py`
- 修改：`tests/test_init_cmd.py`
**对应 spec：** §6.1（workspace 端）。**注意：** v1 计划任务 12 已规划 workspace `.gitignore` 但**尚未实现**——这里一次性把 `models.toml` 一并 append。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_init_cmd.py`：
```python
def test_init_appends_models_toml_to_gitignore_when_git_present(tmp_path, monkeypatch):
    from wiki_workspace import workspace
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    target = tmp_path / "ws"
    (target / ".git").mkdir()
    code = init_cmd.run(_args(workspace=str(target)))
    assert code == 0
    gi = (target / ".gitignore").read_text(encoding="utf-8")
    assert "models.toml" in gi.splitlines()


def test_init_skips_gitignore_when_no_git_dir(tmp_path, monkeypatch):
    from wiki_workspace import workspace
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    target = tmp_path / "ws"
    code = init_cmd.run(_args(workspace=str(target)))
    assert code == 0
    assert not (target / ".gitignore").exists()


def test_init_gitignore_append_is_idempotent(tmp_path, monkeypatch):
    from wiki_workspace import workspace
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    target = tmp_path / "ws"
    (target / ".git").mkdir()
    (target / ".gitignore").write_text("# existing\nfoo\n", encoding="utf-8")
    init_cmd.run(_args(workspace=str(target)))
    init_cmd.run(_args(workspace=str(target)))
    lines = (target / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count("models.toml") == 1
    assert "foo" in lines
```

> **注意：** `test_init_appends_models_toml_to_gitignore_when_git_present` 与 v1 计划任务 12 的同名测试同义——v1 计划本打算在任务 12 实现该行为但实际未实现。这里把 workspace `.gitignore` 行的写入一并落到 `init_cmd.py`，v1 计划的"init 任务"算补齐。

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_init_cmd.py -v -k "gitignore"`
预期：FAIL——`init_cmd.py` 当前不写 `.gitignore`。

- [ ] **第 3 步：扩展 `wiki_workspace/commands/init_cmd.py`**

把 `init_cmd.py` 改为（追加 `_ensure_gitignore` helper + 在 init 末尾调一次）：
```python
"""llmw init — 脚手架一个新 workspace（spec §3.1）。"""

from pathlib import Path

from wiki_workspace import errors, manifest, workspace

CLAUDE_MD_TEMPLATE = """\
# llmw Workspace

This directory is managed by [llmw](https://github.com/yzr95924/llm_workspace_cli).
- `llmw list` — list wikis
- `llmw add <name>` — create a new wiki
- `llmw enter <name>` — launch Claude Code inside a wiki (auto-loads this CLAUDE.md)
"""


GITIGNORE_LINE = "models.toml"  # spec §6.1


def _ensure_gitignore(root):
    """若 <root>/.git 存在则 append `models.toml` 到 <root>/.gitignore。
    幂等（已含则不重复）。父 .git 不存在则跳过。"""
    if not (root / ".git").is_dir():
        return
    gi = root / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
    if GITIGNORE_LINE in lines:
        return
    sep = "" if (not lines or lines[-1] == "") else "\n"
    with gi.open("a", encoding="utf-8") as f:
        if sep:
            f.write(sep)
        f.write(GITIGNORE_LINE + "\n")


def run(args):
    root = Path(workspace.find_root(cli_workspace=getattr(args, "workspace", None)))
    manifest_file = workspace.manifest_path(root)

    if manifest_file.is_file():
        errors.emit_error(
            "workspace-already-exists",
            "{} 已含 .workspace.toml".format(root),
            hint="换一个目录或先 llmw remove",
        )
        return errors.EXIT_USER_ERROR

    root.mkdir(parents=True, exist_ok=True)
    m = manifest.empty_manifest(workspace.today_iso())
    workspace.save_manifest(root, m)
    (root / "CLAUDE.md").write_text(CLAUDE_MD_TEMPLATE, encoding="utf-8")
    _ensure_gitignore(root)

    if (root / ".git").is_dir():
        errors.emit_info("检测到 git 仓：git add .workspace.toml CLAUDE.md && git commit")
    else:
        errors.emit_info("建议：cd {} && git init".format(root))

    print("Initialized llmw workspace at {}".format(root))
    return errors.EXIT_OK
```

> **注意：** `manifest.empty_manifest(workspace.today_iso())` 已不传 `default_model`。当前 `manifest.empty_manifest(created, default_model=DEFAULT_MODEL)` 仍接受单参调用（用 kwarg 默认值）；任务 13 删除 `default_model` kwarg 后，本调用继续成立。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_init_cmd.py -v`
预期：PASS。原有 3 个测试（v1 计划的 `test_init_default_model_stored` 等）仍过——因为 `manifest.empty_manifest(workspace.today_iso())` 默认就是 `claude-sonnet-4-6`，与 v1 测试断言一致。任务 14 才会删这些测试。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/init_cmd.py tests/test_init_cmd.py
git commit -m "feat(init): append models.toml to workspace .gitignore (idempotent)"
```

---

### 任务 7：`profile.py` — per-wiki profile 绑定（纯叶子）

**文件：**
- 创建：`wiki_workspace/profile.py`、`tests/test_profile.py`
**对应 spec：** §1.7。

- [ ] **第 1 步：写失败测试**

`tests/test_profile.py`：
```python
from wiki_workspace import profile


def test_parse_minimal():
    p = profile.parse('model = "anthropic-prod"\n')
    assert p.model == "anthropic-prod"


def test_parse_missing_model_raises():
    import pytest
    with pytest.raises(Exception):  # tomllib.TOMLDecodeError 或 KeyError
        profile.parse("# no model\n")


def test_parse_empty_model_raises():
    import pytest
    with pytest.raises(Exception):
        profile.parse('model = ""\n')


def test_parse_toml_syntax_error_raises():
    import pytest
    with pytest.raises(Exception):
        profile.parse("this is = = not valid =")


def test_validate_references_existing_profile():
    p = profile.Profile(model="anthropic-prod")
    # 用 mock registry 简化：profile.validate 接受 (profile, registry) 两个参数
    class FakeRegistry:
        models = {"anthropic-prod": object()}
    issues = profile.validate(p, FakeRegistry)
    assert [i for i in issues if i.severity == "error"] == []


def test_validate_references_missing_profile_fails():
    p = profile.Profile(model="ghost")
    class FakeRegistry:
        models = {}
    issues = profile.validate(p, FakeRegistry)
    assert any(i.severity == "error" and "ghost" in i.message for i in issues)


def test_serialize_round_trip():
    p = profile.Profile(model="anthropic-prod")
    text = profile.serialize(p)
    p2 = profile.parse(text)
    assert p2.model == p.model


def test_serialize_escapes_quotes():
    p = profile.Profile(model='a"b')
    text = profile.serialize(p)
    p2 = profile.parse(text)
    assert p2.model == 'a"b'


def test_validate_unknown_field_warns():
    text = 'model = "x"\nextra = "y"\n'
    p = profile.parse(text)
    class FakeRegistry:
        models = {"x": object()}
    issues = profile.validate(p, FakeRegistry)
    assert any(i.severity == "warn" for i in issues)
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_profile.py -v`
预期：FAIL——`ModuleNotFoundError: ...profile`

- [ ] **第 3 步：写 `wiki_workspace/profile.py`**

```python
"""per-wiki profile 绑定内存模型 + parse/serialize/validate。纯模块：
不碰文件系统、不碰 errors（spec §3.2）。"""

from typing import List

REQUIRED_FIELDS = {"model"}
KNOWN_FIELDS = {"model"}


class Profile:
    """v1 仅含 `model`（profile 名引用）。future 字段（temperature / custom_prompt）
    加入时扩 __init__ + to_dict + validate 即可。"""

    def __init__(self, model):
        self.model = model

    def to_dict(self):
        return {"model": self.model}


class Issue:
    def __init__(self, severity, category, message, field=None):
        self.severity = severity
        self.category = category
        self.message = message
        self.field = field


def parse(text):
    """TOML 文本 → Profile。缺 model 键 / model="" → raise（调用方映射为
    profile-file-parse-failed / profile-validation-failed）。"""
    try:
        import tomllib  # py>=3.11
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    data = tomllib.loads(text)
    if "model" not in data:
        raise KeyError("profile.toml 缺 model 键")
    model = data.get("model", "")
    if not model:
        raise ValueError("profile.toml 的 model 字段为空")
    return Profile(model=model)


def serialize(p):
    """经 workspace.dump_profile_toml（惰性 import，保持 profile 无环）。"""
    from wiki_workspace.workspace import dump_profile_toml

    return dump_profile_toml(p.to_dict())


def validate(p, models_registry):
    """校验 model 字段引用了 models_registry.models 中的现存 profile。
    models_registry 参数仅用 `.models` 属性——profile.py 顶部不 import models。
    """
    issues: List[Issue] = []
    if p.model not in models_registry.models:
        issues.append(
            Issue(
                "error",
                "profile-validation-failed",
                "profile.model '{}' 不在 models.toml 中".format(p.model),
                field="model",
            )
        )
    return issues
```

> **设计说明：** `validate` 接受 `models_registry` 参数而非在内部 import `models`——避免 profile.py 顶部出现 models 依赖（DAG 干净）。`models_registry.models` 是 duck-typed dict，调用方传 `models.ModelRegistry` 即可。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_profile.py -v`
预期：PASS（`serialize` 路径因 `workspace.dump_profile_toml` 还不存在部分失败——任务 8 完成才全绿；任务 8 前用 `-k "not serialize and not round_trip"` 验证）。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/profile.py tests/test_profile.py
git commit -m "feat(profile): per-wiki profile binding data model + parse + validate"
```

---

### 任务 8：`workspace.py` 扩展 — profile.toml I/O + 原子写

**文件：**
- 修改：`wiki_workspace/workspace.py`
- 修改：`tests/test_workspace.py`
**对应 spec：** §1.7、§3.3。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_workspace.py`：
```python
from wiki_workspace import profile


def test_profile_path(tmp_path):
    from wiki_workspace.workspace import profile_path, profile_filename
    assert profile_filename() == "profile.toml"
    assert profile_path(tmp_path) == tmp_path / "profile.toml"


def test_dump_profile_toml_round_trip():
    from wiki_workspace.workspace import dump_profile_toml
    text = dump_profile_toml({"model": "anthropic-prod"})
    p = profile.parse(text)
    assert p.model == "anthropic-prod"


def test_dump_profile_toml_escapes_quotes():
    from wiki_workspace.workspace import dump_profile_toml
    text = dump_profile_toml({"model": 'a"b'})
    p = profile.parse(text)
    assert p.model == 'a"b'


def test_load_profile_missing_file_returns_none(tmp_path):
    from wiki_workspace.workspace import load_profile
    assert load_profile(tmp_path) is None


def test_save_profile_creates_file_with_0600(tmp_path):
    from wiki_workspace.workspace import profile_path, save_profile
    save_profile(tmp_path, profile.Profile(model="p1"))
    path = profile_path(tmp_path)
    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600


def test_save_profile_round_trip(tmp_path):
    from wiki_workspace.workspace import load_profile, save_profile
    save_profile(tmp_path, profile.Profile(model="p1"))
    p = load_profile(tmp_path)
    assert p.model == "p1"
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_workspace.py -v -k "profile"`
预期：FAIL（无 `profile_path`）。

- [ ] **第 3 步：扩展 `wiki_workspace/workspace.py`**

在 models 相关代码后追加：
```python
# --- profile.toml 接口（spec §3.3）--------------------------------------
from wiki_workspace import profile as _profile_mod  # 顶部 import 安全：profile.py 无 import 环


def profile_filename():
    return "profile.toml"


def profile_path(wiki_root):
    return Path(wiki_root) / profile_filename()


def _profile_toml_escape(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def dump_profile_toml(data):
    """schema 专属序列化器：当前仅含 `model` 字符串。"""
    return 'model = "{}"\n'.format(_profile_toml_escape(data.get("model", "")))


def load_profile(wiki_root):
    """读 + 解析 profile.toml；文件缺失返回 None（语义：wiki 未绑定）。
    TOML 语法错误抛 tomllib.TOMLDecodeError（调用方映射为 profile-file-parse-failed）。"""
    p = profile_path(wiki_root)
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    return _profile_mod.parse(text)


def save_profile(wiki_root, profile_obj):
    """原子写 + 重解析自检。失败抛 internal-state-corruption。"""
    text = dump_profile_toml(profile_obj.to_dict())
    atomic_write(profile_path(wiki_root), text)
    try:
        _profile_mod.parse(text)
    except Exception as exc:
        raise errors.CommandError(
            errors.EXIT_INTERNAL,
            "internal-state-corruption",
            "写盘后重解析 profile.toml 失败：{}".format(exc),
            hint="检查磁盘空间 / 权限",
        )
```

> **import 位置：** `from wiki_workspace import profile` 放在 models 之后；同样在文件顶部用 `from wiki_workspace import models` 已加，再加一行 `from wiki_workspace import profile`——profile.py 顶部无循环依赖。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_workspace.py tests/test_models.py tests/test_profile.py -v`
预期：PASS。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): profile.toml I/O + atomic write + 0600 permissions"
```

---

### 任务 9：`commands/_common.py` 扩展 — `load_profile(wiki_root)` helper

**文件：**
- 修改：`wiki_workspace/commands/_common.py`
- 修改：`tests/test_common.py`
**对应 spec：** §3.3、§3.5。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_common.py`：
```python
def test_load_profile_missing_file_returns_none(tmp_path):
    from wiki_workspace.commands import _common
    assert _common.load_profile(tmp_path) is None


def test_load_profile_returns_profile(tmp_path):
    from wiki_workspace import profile, workspace
    from wiki_workspace.commands import _common
    workspace.save_profile(tmp_path, profile.Profile(model="p1"))
    p = _common.load_profile(tmp_path)
    assert p.model == "p1"
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_common.py -v -k "load_profile"`
预期：FAIL。

- [ ] **第 3 步：扩展 `wiki_workspace/commands/_common.py`**

追加：
```python
def load_profile(wiki_root):
    """读 + 解析 <wiki_root>/profile.toml。文件缺失返回 None；
    TOML 语法错误抛 CommandError(profile-file-parse-failed)。"""
    try:
        return workspace.load_profile(wiki_root)
    except Exception as exc:
        raise errors.CommandError(
            errors.EXIT_ENV_ERROR, "profile-file-parse-failed", str(exc)
        )
```

并在顶部 import 追加 `profile`：
```python
from wiki_workspace import errors, manifest, models, profile, workspace
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_common.py -v`
预期：PASS。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/_common.py tests/test_common.py
git commit -m "feat(commands): _common.load_profile helper"
```

---

### 任务 10：`cli.py` 扩展 — `wiki config` 子 parser

**文件：**
- 修改：`wiki_workspace/cli.py`
- 修改：`tests/test_cli.py`
**对应 spec：** §2.6。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_cli.py`：
```python
def test_wiki_subparser_help(capsys):
    from wiki_workspace import cli
    p = cli.build_parser()
    with pytest.raises(SystemExit) as ei:
        p.parse_args(["wiki", "--help"])
    assert ei.value.code == 0


def test_wiki_config_help_includes_name_and_show(capsys):
    from wiki_workspace import cli
    p = cli.build_parser()
    with pytest.raises(SystemExit) as ei:
        p.parse_args(["wiki", "config", "--help"])
    assert ei.value.code == 0


def test_wiki_config_invokes_action(monkeypatch):
    from wiki_workspace import cli
    captured = {}
    monkeypatch.setattr(cli, "_dispatch", lambda f, a: captured.update(f=f, a=a) or 0)
    cli.main(["wiki", "config", "--name", "w1"])
    assert captured["f"] == "wiki_config"


def test_wiki_config_show_flag(monkeypatch):
    from wiki_workspace import cli
    captured = {}
    monkeypatch.setattr(cli, "_dispatch", lambda f, a: captured.update(a=a) or 0)
    cli.main(["wiki", "config", "--name", "w1", "--show"])
    assert captured["a"].show is True
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_cli.py -v -k "wiki_"`
预期：FAIL。

- [ ] **第 3 步：扩展 `wiki_workspace/cli.py`**

在 `models` 子 parser 块后插入：
```python
    # wiki 子命令组（spec §2.6）— per-wiki 局部配置入口
    sp_wiki = sub.add_parser("wiki", help="per-wiki 局部配置", parents=[common])
    sp_wiki_sub = sp_wiki.add_subparsers(dest="wiki_action", metavar="<action>")

    # wiki config
    sp_wc = sp_wiki_sub.add_parser("config", help="配置该 wiki 的 profile.toml")
    sp_wc.add_argument("--name", required=True, help="wiki 名")
    sp_wc.add_argument("--show", action="store_true", help="只显示当前 profile.toml，不进入交互")
    sp_wc.set_defaults(func="wiki_config")
```

并在 `_dispatch` import 表与 table 同步追加：
```python
    from wiki_workspace.commands import (
        ...,
        wiki_config_cmd,   # NEW
    )

    table = {
        ...,
        "wiki_config": wiki_config_cmd.run,
    }
```

> **提前 import：** 任务 11 之前 `wiki_config_cmd` 不存在——已被 monkeypatch 的测试不受影响。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_cli.py -v -k "wiki_"`
预期：PASS（4 passed）。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/cli.py tests/test_cli.py
git commit -m "feat(cli): wiki config subparser + dispatch wiring"
```

---

### 任务 11：`commands/wiki_config_cmd.py` — 交互式配置

**文件：**
- 创建：`wiki_workspace/commands/wiki_config_cmd.py`、`tests/test_wiki_config_cmd.py`
**对应 spec：** §2.6。

- [ ] **第 1 步：写失败测试**

`tests/test_wiki_config_cmd.py`：
```python
from wiki_workspace import errors, models, profile, workspace
from wiki_workspace.commands import wiki_config_cmd


def _args(name, show=False, **kw):
    base = dict(workspace=None, json=False, quiet=False, debug=False, name=name, show=show)
    base.update(kw)
    return type("A", (), base)()


def _seed_ws_with_models(tmp_path):
    workspace.save_manifest(tmp_path, __import__("wiki_workspace").manifest.empty_manifest("2026-06-26"))
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1",
        models={
            "p1": models.ModelEntry("p1", "m", "b", "k"),
            "p2": models.ModelEntry("p2", "m", "b", "k"),
        },
    ))


def _seed_wiki(tmp_path, name="w1"):
    wiki_root = tmp_path / name
    wiki_root.mkdir()
    (wiki_root / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = __import__("wiki_workspace").manifest.Manifest(
        "1", "2026-06-26",
        {name: __import__("wiki_workspace").manifest.WikiEntry(name=name, path=name, display_name=name.title(), created="2026-06-26")},
    )
    workspace.save_manifest(tmp_path, m)
    return wiki_root


def test_show_unset(tmp_path, capsys):
    _seed_ws_with_models(tmp_path)
    _seed_wiki(tmp_path)
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path), show=True))
    assert code == 0
    out = capsys.readouterr().out
    assert "(unset)" in out


def test_show_set(tmp_path, capsys):
    from wiki_workspace import profile as p_mod
    _seed_ws_with_models(tmp_path)
    wiki_root = _seed_wiki(tmp_path)
    workspace.save_profile(wiki_root, p_mod.Profile(model="p1"))
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path), show=True))
    assert code == 0
    out = capsys.readouterr().out
    assert "p1" in out


def test_interactive_first_time_creates_profile(tmp_path, monkeypatch):
    _seed_ws_with_models(tmp_path)
    _seed_wiki(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "p1")
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    p = workspace.load_profile(tmp_path / "w1")
    assert p is not None
    assert p.model == "p1"


def test_interactive_update_existing(tmp_path, monkeypatch):
    _seed_ws_with_models(tmp_path)
    wiki_root = _seed_wiki(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "p2")
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    p = workspace.load_profile(wiki_root)
    assert p.model == "p2"


def test_interactive_clear_deletes_file(tmp_path, monkeypatch):
    _seed_ws_with_models(tmp_path)
    wiki_root = _seed_wiki(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "clear")
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    assert workspace.load_profile(wiki_root) is None


def test_interactive_invalid_profile_reprompts_then_accepts(tmp_path, monkeypatch):
    _seed_ws_with_models(tmp_path)
    _seed_wiki(tmp_path)
    # 第一次 "ghost" → 失败重提示；第二次 "p1" → 接受
    responses = iter(["ghost", "p1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    p = workspace.load_profile(tmp_path / "w1")
    assert p.model == "p1"


def test_interactive_accept_keep_default(tmp_path, monkeypatch):
    _seed_ws_with_models(tmp_path)
    wiki_root = _seed_wiki(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "")  # 直接 Enter
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    p = workspace.load_profile(wiki_root)
    assert p.model == "p1"


def test_interactive_quit_no_write(tmp_path, monkeypatch):
    _seed_ws_with_models(tmp_path)
    wiki_root = _seed_wiki(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    monkeypatch.setattr("builtins.input", lambda prompt="": "q")
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    # 文件保持原样
    p = workspace.load_profile(wiki_root)
    assert p.model == "p1"


def test_wiki_not_found(tmp_path):
    _seed_ws_with_models(tmp_path)
    code = wiki_config_cmd.run(_args("ghost", workspace=str(tmp_path), show=True))
    assert code == errors.EXIT_USER_ERROR


def test_no_models_blocks_interactive(tmp_path, monkeypatch, capsys):
    workspace.save_manifest(tmp_path, __import__("wiki_workspace").manifest.empty_manifest("2026-06-26"))
    _seed_wiki(tmp_path)
    monkeypatch.setattr("builtins.input", lambda prompt="": "p1")
    code = wiki_config_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_wiki_config_cmd.py -v`
预期：FAIL——`ModuleNotFoundError: ...wiki_config_cmd`

- [ ] **第 3 步：写 `wiki_workspace/commands/wiki_config_cmd.py`**

```python
"""llmw wiki config --name=<wiki> — 交互式配置 per-wiki profile.toml（spec §2.6）。"""

import sys

from wiki_workspace import errors, models, profile, workspace
from wiki_workspace.commands import _common


def _print_current(current_profile):
    if current_profile is None:
        print("       (unset)")
    else:
        print("       model = {!r}".format(current_profile.model))


def _prompt_model(current, registry):
    """单字段 prompt 循环。返回 'CLEAR' / 'QUIT' / 新值（已校验）。"""
    while True:
        raw = input("  model [<profile name> or 'clear' to unset]: ").strip()
        if raw == "":
            if current is None:
                errors.emit_warn("当前未绑定 model；请输入 profile 名（或 'q' 退出）")
                continue
            return current.model
        if raw.lower() == "q":
            return "QUIT"
        if raw.lower() == "clear":
            return "CLEAR"
        if raw in registry.models:
            return raw
        errors.emit_warn("profile '{}' 不在 models.toml 中；请重输（或 'q' 退出）".format(raw))


def run(args):
    try:
        root = _common.resolve_root(args)
        _common.require_initialized(root)
        m = _common.load_manifest(args)
        registry = _common.load_models(args)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    if name not in m.wikis:
        errors.emit_error("wiki-not-found", "wiki '{}' 不存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR

    wiki_root = (root / m.wikis[name].path).resolve()

    if args.show:
        current = _common.load_profile(wiki_root)
        _print_current(current)
        return errors.EXIT_OK

    if not registry.models:
        errors.emit_error(
            "models-validation-failed",
            "models.toml 为空；先 llmw models add",
        )
        return errors.EXIT_USER_ERROR

    if not sys.stdin.isatty():
        errors.emit_error(
            "tty-required",
            "wiki config 需交互式终端；脚本场景用 --show 或手工编辑 profile.toml",
        )
        return errors.EXIT_USER_ERROR

    current = _common.load_profile(wiki_root)
    errors.emit_info("Wiki: {}".format(name))
    errors.emit_info("Current profile.toml:")
    _print_current(current)

    errors.emit_info("Configure each field (press Enter to keep current value):")
    new_model = _prompt_model(current, registry)
    if new_model == "QUIT":
        errors.emit_info("不保存退出；profile.toml 未改动")
        return errors.EXIT_OK

    if new_model == "CLEAR":
        if (wiki_root / "profile.toml").is_file():
            (wiki_root / "profile.toml").unlink()
            errors.emit_info("profile.toml 已删除（解除绑定）")
        return errors.EXIT_OK

    new_profile = profile.Profile(model=new_model)
    try:
        workspace.save_profile(wiki_root, new_profile)
    except errors.CommandError as exc:
        errors.emit_error(exc.category, exc.message, exc.hint)
        return exc.exit_code

    errors.emit_info("profile.toml 已更新")
    return errors.EXIT_OK
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_wiki_config_cmd.py -v`
预期：PASS（10 passed）。**注意：** `test_no_models_blocks_interactive` 会通过 `input()` 走 prompt——registry 为空时直接 emit_error 返回，不进 prompt 循环，OK。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/wiki_config_cmd.py tests/test_wiki_config_cmd.py
git commit -m "feat(wiki-config): interactive profile.toml binding with show/clear/quit"
```

---

### 任务 12：`enter_cmd.py` 重写 — profile 解析（echo / warn / refuse）

**文件：**
- 修改：`wiki_workspace/commands/enter_cmd.py`（重写）
- 修改：`tests/test_enter_cmd.py`（重写）
**对应 spec：** §2.7。

- [ ] **第 1 步：写失败测试**

`tests/test_enter_cmd.py`（完整重写）：
```python
import subprocess
from unittest.mock import patch

from wiki_workspace import errors, manifest, models, profile, workspace
from wiki_workspace.commands import enter_cmd


def _args(name, **kw):
    base = dict(
        workspace=None, json=False, quiet=False, debug=False, name=name,
        claude_md_check="warn", dry_run=False,
    )
    base.update(kw)
    return type("A", (), base)()


def _seed_full(tmp_path, wiki_name="w1"):
    """workspace 已 init，profile.toml 绑到 p1，models.toml 含 p1 + p2。"""
    workspace.save_manifest(tmp_path, manifest.empty_manifest("2026-06-26"))
    workspace.save_models(tmp_path, models.ModelRegistry(
        default="p1",
        models={
            "p1": models.ModelEntry("p1", "claude-opus-4-8", "https://api.x", "sk-p1"),
            "p2": models.ModelEntry("p2", "claude-sonnet-4-6", "https://api.y", "sk-p2"),
        },
    ))
    wiki_root = tmp_path / wiki_name
    wiki_root.mkdir()
    (wiki_root / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = manifest.Manifest("1", "2026-06-26", {
        wiki_name: manifest.WikiEntry(name=wiki_name, path=wiki_name, display_name=wiki_name.title(), created="2026-06-26"),
    })
    workspace.save_manifest(tmp_path, m)
    return wiki_root


def _fake_skill(monkeypatch, tmp_path):
    """屏蔽 ~/.claude/skills/... 探测，避免依赖机器环境。"""
    from wiki_workspace import _compat
    monkeypatch.setattr(_compat, "_HOME_SKILL_PATH", tmp_path / "no-skill", raising=False)


def test_uses_profile_toml_and_injects_env(tmp_path, monkeypatch):
    wiki_root = _seed_full(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    _fake_skill(monkeypatch, tmp_path)

    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env")
        captured["cwd"] = kw.get("cwd")
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(enter_cmd.subprocess, "run", fake_run)

    code = enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    assert captured["cmd"][0] == "claude"
    assert "claude-opus-4-8" in captured["cmd"]
    assert captured["env"][enter_cmd.BASE_URL_ENV] == "https://api.x"
    assert captured["env"][enter_cmd.API_KEY_ENV] == "sk-p1"


def test_falls_back_to_workspace_default(tmp_path, monkeypatch, capsys):
    wiki_root = _seed_full(tmp_path)  # 无 profile.toml
    _fake_skill(monkeypatch, tmp_path)

    captured = {}
    def fake_run(cmd, **kw):
        captured["env"] = kw.get("env")
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(enter_cmd.subprocess, "run", fake_run)

    code = enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == 0
    err = capsys.readouterr().err
    assert "workspace default" in err
    assert captured["env"][enter_cmd.API_KEY_ENV] == "sk-p1"


def test_wiki_not_bound_when_no_profile_and_no_default(tmp_path, monkeypatch):
    _seed_full(tmp_path)
    # 把 default 清空
    r = workspace.load_models(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(default="", models=r.models))

    captured_run = []
    monkeypatch.setattr(enter_cmd.subprocess, "run", lambda *a, **kw: captured_run.append(a) or _r(0))
    _fake_skill(monkeypatch, tmp_path)

    code = enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
    assert captured_run == []  # 没 spawn


def _r(rc):
    class R:
        returncode = rc
    return R


def test_profile_toml_references_missing_profile_fails(tmp_path, monkeypatch):
    wiki_root = _seed_full(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="ghost"))
    _fake_skill(monkeypatch, tmp_path)

    captured_run = []
    monkeypatch.setattr(enter_cmd.subprocess, "run", lambda *a, **kw: captured_run.append(a) or _r(0))

    code = enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
    assert captured_run == []


def test_models_file_missing_treated_as_no_default(tmp_path, monkeypatch):
    wiki_root = _seed_full(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="ghost"))  # 引用不存在的
    (tmp_path / "models.toml").unlink()
    _fake_skill(monkeypatch, tmp_path)

    code = enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR


def test_dry_run_prints_cmd_and_env_without_secret(tmp_path, monkeypatch, capsys):
    wiki_root = _seed_full(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    _fake_skill(monkeypatch, tmp_path)
    code = enter_cmd.run(_args("w1", workspace=str(tmp_path), dry_run=True))
    assert code == 0
    out = capsys.readouterr().out
    assert "claude" in out
    assert "claude-opus-4-8" in out
    assert "sk-p1" not in out  # api_key 不出现在 stdout
    err = capsys.readouterr().err
    # api_key 也不出现在 stderr
    assert "sk-p1" not in err


def test_no_secret_in_any_output_on_error_path(tmp_path, monkeypatch, capsys):
    _seed_full(tmp_path)
    r = workspace.load_models(tmp_path)
    workspace.save_models(tmp_path, models.ModelRegistry(default="", models=r.models))
    _fake_skill(monkeypatch, tmp_path)
    code = enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
    err = capsys.readouterr().err
    # "sk-p1" 是 secret 字面量；不在 err 里出现
    assert "sk-p1" not in err


def test_using_profile_echoed_to_stderr(tmp_path, monkeypatch, capsys):
    wiki_root = _seed_full(tmp_path)
    workspace.save_profile(wiki_root, profile.Profile(model="p1"))
    _fake_skill(monkeypatch, tmp_path)
    monkeypatch.setattr(enter_cmd.subprocess, "run", lambda *a, **kw: _r(0))
    enter_cmd.run(_args("w1", workspace=str(tmp_path)))
    err = capsys.readouterr().err
    assert "Using profile: p1" in err or "p1" in err  # 信息含 profile 名


def test_wiki_not_found(tmp_path):
    _seed_full(tmp_path)
    code = enter_cmd.run(_args("ghost", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_enter_cmd.py -v`
预期：FAIL——`enter_cmd` 当前用 `args.model` / `w.effective_model()`，签名已变。

- [ ] **第 3 步：重写 `wiki_workspace/commands/enter_cmd.py`**

```python
"""llmw enter <name> — 在 wiki 里 spawn Claude Code（spec §2.7）。

profile 解析（无 CLI override、无菜单）：
  profile.toml 存在 & model=X 引用现存 profile:
    [INFO] Using profile: X  →  env 注入 X 的 base_url + api_key
  profile.toml 不存在 & models.toml default=Y:
    [WARN] No profile bound for '<wiki>'; using workspace default: Y  →  env 注入 Y
  都没有:
    error wiki-not-bound, exit 1
"""

import os
import shutil
import subprocess

from wiki_workspace import _compat, errors, manifest, models
from wiki_workspace.commands import _common

# 占位环境变量名（实现期核对 Claude Code / Anthropic SDK 实际读取的变量；spec §2.7）
BASE_URL_ENV = "ANTHROPIC_BASE_URL"
API_KEY_ENV = "ANTHROPIC_AUTH_TOKEN"

SYSTEM_PROMPT_TEMPLATE = """\
You are operating inside an llmw-managed workspace:

  workspace root: {workspace_root}
  wiki name:      {wiki_name}
  wiki root:      {wiki_root}
  skill:          {llm_wiki_management_path}

The llm-wiki-management skill is available (or should be installed).
Use it for ingest / query / lint operations on this wiki.
The wiki's CLAUDE.md ({wiki_root}/CLAUDE.md) contains its schema — read it first
before any write operation."""


def _redact_api_key(env):
    """dry-run 打印 env 时把 api_key 替成 ***；其余字段原样。"""
    if API_KEY_ENV in env:
        out = dict(env)
        out[API_KEY_ENV] = "***"
    else:
        out = env
    return out


def _build_cmd(w, root, wiki_root, model_id):
    skill_root = _compat.find_skill_root(workspace_root=root)
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        workspace_root=root,
        wiki_name=w.name,
        wiki_root=wiki_root,
        llm_wiki_management_path=skill_root or "(not found)",
    )
    cmd = ["claude"]
    cmd += ["--model", model_id]
    cmd += ["--add-dir", str(root), "--add-dir", str(wiki_root)]
    cmd += ["--system-prompt", prompt]
    return cmd


def _spawn(cmd, wiki_root, env):
    if shutil.which("claude") is None:
        errors.emit_error("claude-not-in-path", "`claude` 不在 PATH", hint="安装 Claude Code CLI")
        return errors.EXIT_ENV_ERROR
    proc = subprocess.run(cmd, cwd=str(wiki_root), env=env, check=False)
    return proc.returncode


def run(args):
    try:
        m = _common.load_manifest(args)
        root = _common.resolve_root(args)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    if name not in m.wikis:
        errors.emit_error("wiki-not-found", "wiki '{}' 不存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR
    w = m.wikis[name]
    wiki_root = (root / w.path).resolve()

    # CLAUDE.md 检查（与 v1 行为一致）
    has_md = (wiki_root / "CLAUDE.md").is_file()
    if not has_md and args.claude_md_check == "fail":
        errors.emit_error(
            "wiki-not-found", "{} 缺 CLAUDE.md（--claude-md-check=fail）".format(wiki_root)
        )
        return errors.EXIT_USER_ERROR
    if not has_md:
        errors.emit_warn("{} 缺 CLAUDE.md".format(wiki_root))

    # 加载 models registry（缺失文件 → 空 registry = 兜底 no-default）
    registry = workspace.load_models(root)

    # 解析 profile
    chosen_entry = None
    source = None  # "profile-toml" / "workspace-default"

    prof = _common.load_profile(wiki_root)
    if prof is not None:
        if prof.model in registry.models:
            chosen_entry = registry.models[prof.model]
            source = "profile-toml"
        else:
            errors.emit_error(
                "profile-validation-failed",
                "<{}>/profile.toml 的 model '{}' 不在 models.toml 中".format(wiki_root, prof.model),
                hint="llmw wiki config --name={} (重新绑定) 或 llmw models add {}".format(name, prof.model),
            )
            return errors.EXIT_USER_ERROR
    elif registry.default and registry.default in registry.models:
        chosen_entry = registry.models[registry.default]
        source = "workspace-default"
        errors.emit_warn(
            "No profile bound for '{}'; using workspace default: {}".format(name, registry.default)
        )
    else:
        errors.emit_error(
            "wiki-not-bound",
            "wiki '{}' 未绑定任何 profile，且 workspace 也无 default profile".format(name),
            hint="llmw wiki config --name={} 或 llmw models set-default <name>".format(name),
        )
        return errors.EXIT_USER_ERROR

    if source == "profile-toml":
        errors.emit_info("Using profile: {}".format(chosen_entry.name))

    # 构造命令 + env
    cmd = _build_cmd(w, root, wiki_root, chosen_entry.model_id)
    proc_env = os.environ.copy()
    proc_env[BASE_URL_ENV] = chosen_entry.base_url
    proc_env[API_KEY_ENV] = chosen_entry.api_key

    # 软依赖探测
    skill_root = _compat.find_skill_root(workspace_root=root)
    if skill_root is None:
        errors.emit_warn("llm-wiki-management 未找到；enter 仍将启动")

    # --debug 输出
    errors.emit_debug(
        "profile name={} model_id={} base_url={} api_key=***".format(
            chosen_entry.name, chosen_entry.model_id, chosen_entry.base_url
        )
    )

    # dry-run：只打印，不要求 claude 已安装
    if args.dry_run:
        print("Would run: " + " ".join(cmd))
        print("(cwd: {})".format(wiki_root))
        print("(env: {})".format(_redact_api_key(proc_env)))
        return errors.EXIT_OK

    return _spawn(cmd, wiki_root, proc_env)
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_enter_cmd.py -v`
预期：PASS（9 passed）。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/enter_cmd.py tests/test_enter_cmd.py
git commit -m "feat(enter): profile.toml + workspace default resolution with secret redaction"
```

---

### 任务 13：`manifest.py` 清理 — 删除 v1 model 字段

**文件：**
- 修改：`wiki_workspace/manifest.py`
- 修改：`tests/test_manifest.py`
**对应 spec：** §1.8、§3.4。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_manifest.py`：
```python
def test_wiki_entry_has_no_model_attr():
    from wiki_workspace import manifest
    e = manifest.WikiEntry(name="r", path="r", display_name="R", created="2026-06-26")
    assert not hasattr(e, "model")


def test_manifest_has_no_default_model_attr():
    from wiki_workspace import manifest
    m = manifest.Manifest("1", "2026-06-26", {})
    assert not hasattr(m, "default_model")


def test_known_models_constant_removed():
    from wiki_workspace import manifest
    assert not hasattr(manifest, "KNOWN_MODELS")


def test_settable_keys_does_not_contain_model():
    from wiki_workspace import manifest
    assert "model" not in manifest.SETTABLE_KEYS


def test_validate_no_unknown_model_warn():
    """未知 model 字段已删——validate 不再发 unknown model warn。"""
    m = manifest.Manifest("1", "2026-06-26", {})
    issues = manifest.validate(m, "/tmp")
    assert not any("未知" in i.message for i in issues)
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_manifest.py -v -k "no_model or no_default or known_models or settable or no_unknown"`
预期：FAIL（属性仍存在）。

- [ ] **第 3 步：清理 `wiki_workspace/manifest.py`**

按以下删改：

1. **删除** 第 7 行 `DEFAULT_MODEL = "claude-sonnet-4-6"`。
2. **删除** `WikiEntry.__init__` 的 `model=None` 参数（第 13 行）。
3. **删除** `WikiEntry.model = model` 属性赋值（第 18 行）。
4. **删除** `WikiEntry.effective_model` 整个方法（第 21–22 行）。
5. **删除** `WikiEntry.to_dict()` 里 `if self.model: d["model"] = self.model`（第 33–34 行）。
6. **修改** `Manifest.__init__` 签名（删 `default_model`）：`def __init__(self, schema_version, created, wikis):`。删除第 42 行 `self.default_model = default_model`。
7. **修改** `Manifest.to_dict()`（删 `workspace` 块里的 `default_model` 字段）：返回 `{"schema_version": ..., "created": ..., "wikis": {...}}`——**完全不再写 `[workspace]` 段**。
8. **修改** `empty_manifest(created)` 签名：删 `default_model` 参数；改为 `return Manifest(SCHEMA_VERSION, created, {})`。
9. **修改** `parse()`（删 `default_model` 读取）：删 `default_model = ws.get("default_model", DEFAULT_MODEL)`；删 `Manifest(...)` 调用里的 `default_model=default_model`。
10. **删除** `KNOWN_MODELS` 常量整段（第 102–106 行）。
11. **修改** `SETTABLE_KEYS`：删 `"model"`，保留 `{"display_name", "description", "tags"}`。
12. **修改** `validate()`（删"未知 model"分支）：删第 189–197 行的 `if w.model and w.model not in KNOWN_MODELS` 整段。
13. **修改** `parse()` 里 `WikiEntry(...)` 构造（删 `model=` 关键字）。

修改后 `Manifest.to_dict()` 大致是：
```python
def to_dict(self):
    return {
        "schema_version": self.schema_version,
        "created": self.created,
        "wikis": {name: w.to_dict() for name, w in self.wikis.items()},
    }
```

`WikiEntry.to_dict()`：
```python
def to_dict(self):
    d = {
        "path": self.path,
        "display_name": self.display_name,
        "created": self.created,
        "tags": list(self.tags),
    }
    if self.description:
        d["description"] = self.description
    return d
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_manifest.py -v`
预期：FAIL——既有测试（如 `test_parse_builds_manifest` 等）引用 `m.default_model` / `w.model` / `KNOWN_MODELS`。**任务 18 集中清理；现在仅添加新断言。**

新断言（任务 13 第 1 步加的）应过；旧断言会失败——预期任务 18 一次清理到位。

- [ ] **第 5 步：任务暂停 + 提交（manifest.py 单独提交）**

```bash
git add wiki_workspace/manifest.py tests/test_manifest.py
git commit -m "refactor(manifest): remove v1 model fields (default_model, WikiEntry.model, KNOWN_MODELS, SETTABLE['model'])"
```

> **测试暂处红：** 任务 18 统一清理既有测试。本提交不要求 `test_manifest.py` 全绿。

---

### 任务 14：`init_cmd.py` 清理 — 移除 `--default-model`

**文件：**
- 修改：`wiki_workspace/commands/init_cmd.py`
- 修改：`tests/test_init_cmd.py`
**对应 spec：** §1.8、§2.1。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_init_cmd.py`：
```python
def test_init_no_default_model_kwarg_in_empty_manifest(tmp_path, monkeypatch):
    """v1 残留：empty_manifest 不再接受 default_model。"""
    from wiki_workspace import workspace, manifest as manifest_mod
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    target = tmp_path / "ws"
    init_cmd.run(_args(workspace=str(target)))
    m = manifest_mod.parse((target / ".workspace.toml").read_text(encoding="utf-8"))
    assert not hasattr(m, "default_model")
```

并修改既有 `_args` helper（去掉 `default_model` 字段）：
```python
def _args(**kw):
    base = dict(workspace=None, json=False)  # 删 default_model
    base.update(kw)
    return type("A", (), base)()
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_init_cmd.py -v`
预期：FAIL（既有 `test_init_default_model_stored` 还在引用 `default_model` kwarg）。

- [ ] **第 3 步：清理 `wiki_workspace/commands/init_cmd.py`**

`manifest.empty_manifest(workspace.today_iso())` 已经只传 1 个参数（任务 6 已改），保持不变；本任务确保：
- 顶部 `from wiki_workspace import errors, manifest, workspace` 不变。
- `_args` helper 不再含 `default_model`（在测试里）。
- 既有 `test_init_default_model_stored` 由任务 18 删除。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_init_cmd.py -v -k "no_default_model"`
预期：新加的 `test_init_no_default_model_kwarg_in_empty_manifest` PASS；既有 `test_init_default_model_stored` 在任务 18 删。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/init_cmd.py tests/test_init_cmd.py
git commit -m "refactor(init): drop --default-model flag wiring (param no-op)"
```

---

### 任务 15：`add_cmd.py` 清理 + wiki `.gitignore` append

**文件：**
- 修改：`wiki_workspace/commands/add_cmd.py`
- 修改：`tests/test_add_cmd.py`
**对应 spec：** §1.8、§6.1（wiki 端）。

- [ ] **第 1 步：写失败测试**

修改 `tests/test_add_cmd.py` 的 `_args` helper：
```python
def _args(name, **kw):
    base = dict(
        workspace=None, json=False, name=name,
        display_name=None, description=None,
        tag=[], topic=None, no_git=False,
        # 删: model=None
    )
    base.update(kw)
    return type("A", (), base)()
```

追加测试：
```python
def test_add_appends_profile_toml_to_wiki_gitignore(tmp_path, monkeypatch, fake_skill):
    from wiki_workspace import workspace
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_root(tmp_path)

    # 让 setup_wiki.py 假成功 + 创建 .git/ 在 wiki 根
    def fake(cmd, **kwargs):
        wiki_root = __import__("pathlib").Path(cmd[-1])
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "CLAUDE.md").write_text("# " + cmd[-2], encoding="utf-8")
        (wiki_root / "wiki").mkdir(exist_ok=True)
        (wiki_root / ".git").mkdir()  # 让 .gitignore append 触发
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(add_cmd.subprocess, "run", fake)

    code = add_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    assert code == 0
    gi = (tmp_path / "llm-systems" / ".gitignore").read_text(encoding="utf-8")
    assert "profile.toml" in gi.splitlines()


def test_add_no_git_skips_gitignore_append(tmp_path, monkeypatch, fake_skill):
    from wiki_workspace import workspace
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_root(tmp_path)
    _fake_setup_success(tmp_path, fake_skill, monkeypatch)
    # 不在 fake_setup 里建 .git/，且 tmp_path 也没有 → 不创建 .gitignore
    code = add_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    assert code == 0
    # wiki 目录无 .git/ → 不创建 .gitignore
    assert not (tmp_path / "llm-systems" / ".gitignore").exists()
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_add_cmd.py -v`
预期：FAIL（既有测试引用 `model=None`）。

- [ ] **第 3 步：清理 + 扩展 `wiki_workspace/commands/add_cmd.py`**

1. **删** `entry = manifest.WikiEntry(...)` 里 `model=args.model` 一行（第 82 行）。
2. **新增** 末尾：写 manifest 之后 append wiki `.gitignore`：

```python
import re

from wiki_workspace import _compat, errors, manifest, workspace
from wiki_workspace.commands import _common

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

WIKI_GITIGNORE_LINE = "profile.toml"  # spec §6.1


def _ensure_wiki_gitignore(wiki_root):
    """若 <wiki_root>/.git 存在则 append `profile.toml` 到 <wiki_root>/.gitignore。
    幂等。无 .git/ 则跳过。"""
    if not (wiki_root / ".git").is_dir():
        return
    gi = wiki_root / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
    if WIKI_GITIGNORE_LINE in lines:
        return
    sep = "" if (not lines or lines[-1] == "") else "\n"
    with gi.open("a", encoding="utf-8") as f:
        if sep:
            f.write(sep)
        f.write(WIKI_GITIGNORE_LINE + "\n")


def _dependency_help():
    return (
        "Install from: https://github.com/yzr95924/llm-wiki-management\n"
        "Or set LLM_WIKI_MANAGEMENT_PATH=/path/to/llm-wiki-management"
    )


def run(args):
    name = args.name
    if not KEBAB_RE.match(name):
        errors.emit_error(
            "invalid-wiki-name",
            "wiki 名 '{}' 必须 kebab-case".format(name),
            hint="llmw add {}".format(name.lower()),
        )
        return errors.EXIT_USER_ERROR

    try:
        m = _common.load_manifest(args)
        root = _common.resolve_root(args)
    except errors.CommandError as exc:
        return exc.exit_code

    if name in m.wikis:
        errors.emit_error("wiki-already-exists", "wiki '{}' 已存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR

    wiki_dir = root / name
    if wiki_dir.exists() and any(wiki_dir.iterdir()):
        errors.emit_error("wiki-already-exists", "目录 {} 已存在且非空".format(wiki_dir))
        return errors.EXIT_USER_ERROR

    skill_root = _compat.find_skill_root(workspace_root=root)
    if skill_root is None:
        errors.emit_error(
            "dep-not-found",
            "llm-wiki-management not found at any of:\n"
            "  - $LLM_WIKI_MANAGEMENT_PATH\n"
            "  - ../llm-wiki-management/SKILL.md\n"
            "  - ~/.claude/skills/llm-wiki-management/SKILL.md",
            hint=_dependency_help(),
        )
        return errors.EXIT_ENV_ERROR

    setup_script = skill_root / "scripts" / "setup_wiki.py"
    topic = args.topic or (args.display_name or name)

    if args.no_git:
        errors.emit_warn("--no-git 未被当前 setup_wiki.py 支持；已忽略")

    cmd = [sys.executable, str(setup_script), topic, str(wiki_dir)]
    errors.emit_debug("subprocess: {} (cwd={})".format(cmd, root))
    result = subprocess.run(cmd, cwd=str(root))
    if result.returncode != 0:
        errors.emit_error(
            "setup-script-failed",
            "setup_wiki.py 退出码 {}".format(result.returncode),
            hint="wiki 目录可能已部分创建；可手动 rm -rf {} 后重试".format(wiki_dir),
        )
        return errors.EXIT_ENV_ERROR

    entry = manifest.WikiEntry(
        name=name,
        path=name,
        display_name=args.display_name or topic,
        created=workspace.today_iso(),
        description=args.description or "",
        tags=list(args.tag or []),
    )
    m.wikis[name] = entry
    workspace.save_manifest(root, m)
    _ensure_wiki_gitignore(wiki_dir)

    print("Created wiki '{}' at {}".format(name, wiki_dir))
    print("  下一步：llmw wiki config --name={} 绑 profile；然后 llmw enter {}".format(name, name))
    return errors.EXIT_OK
```

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_add_cmd.py -v`
预期：新加 2 个测试 PASS；既有 6 个测试（不含 `model`/`profile` flag 的）应继续 PASS——它们的 `_args()` 已不传 `model`。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/add_cmd.py tests/test_add_cmd.py
git commit -m "refactor(add): drop --model/--profile; append profile.toml to wiki .gitignore"
```

---

### 任务 16：`config_cmd.py` 清理 — `model` key 不可 set

**文件：**
- 修改：`wiki_workspace/commands/config_cmd.py`
- 修改：`tests/test_config_cmd.py`
**对应 spec：** §1.8。

- [ ] **第 1 步：写失败测试**

修改 `tests/test_config_cmd.py`：把 `test_config_unset_model` 改为断言**拒绝** `set model` / `unset model`：
```python
def test_config_set_model_rejected(tmp_path):
    _seed(tmp_path)
    code = config_cmd.run(_args("w", "set", "model", "claude-opus-4-8", workspace=str(tmp_path)))
    assert code == errors.EXIT_ENV_ERROR


def test_config_unset_model_rejected(tmp_path):
    _seed(tmp_path)
    code = config_cmd.run(_args("w", "unset", "model", workspace=str(tmp_path)))
    assert code == errors.EXIT_ENV_ERROR
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_config_cmd.py -v`
预期：既有 `test_config_unset_model` 仍 PASS（删除后改）；新增的 `test_config_set_model_rejected` 应 FAIL（当前 `model` 在 SETTABLE 内，被允许 set）。

- [ ] **第 3 步：清理 `wiki_workspace/commands/config_cmd.py`**

1. **删** `args.action == "show"` 分支里 `print("model:         {}".format(w.effective_model(m.default_model)))` 这一行。
2. **删** `args.action == "get"` 分支里的 `if args.key in ("display_name", "description", "model", "created"):` 里的 `"model"`；保留 `description` 与 `created`。`getattr(w, args.key) if args.key != "model" else w.effective_model(m.default_model)` 改成只剩 `getattr(w, args.key)`。
3. **删** `args.action == "unset"` 分支里的 `elif args.key == "model": w.model = None`。
4. **删除** 整个 `config_cmd` 里对 `manifest.SETTABLE_KEYS["model"]` / `effective_model` 的引用——它们都已不存在，删除后不再报 AttributeError。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_config_cmd.py -v`
预期：PASS（删除 `test_config_unset_model`，加 `test_config_set_model_rejected` + `test_config_unset_model_rejected`，原有其它测试不变）。

- [ ] **第 5 步：提交**

```bash
git add wiki_workspace/commands/config_cmd.py tests/test_config_cmd.py
git commit -m "refactor(config): reject set/unset model (moved to models registry)"
```

---

### 任务 17：`cli.py` 清理 — 移除 `--model` / `--default-model` / `--profile` flags

**文件：**
- 修改：`wiki_workspace/cli.py`
- 修改：`tests/test_cli.py`
**对应 spec：** §1.8、§2.7。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_cli.py`：
```python
def test_init_has_no_default_model_flag():
    from wiki_workspace import cli
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["init", "--default-model", "x"])


def test_add_has_no_model_or_profile_flag():
    from wiki_workspace import cli
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["add", "x", "--model", "y"])
    with pytest.raises(SystemExit):
        p.parse_args(["add", "x", "--profile", "y"])


def test_enter_has_no_model_or_profile_flag():
    from wiki_workspace import cli
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["enter", "x", "--model", "y"])
    with pytest.raises(SystemExit):
        p.parse_args(["enter", "x", "--profile", "y"])
```

- [ ] **第 2 步：跑测试，确认失败**

运行：`python -m pytest tests/test_cli.py -v -k "no_default_model or no_model_or_profile"`
预期：FAIL。

- [ ] **第 3 步：清理 `wiki_workspace/cli.py`**

1. **删** `init` 子 parser 里的 `sp.add_argument("--default-model", default="claude-sonnet-4-6")`。
2. **删** `add` 子 parser 里的 `sp.add_argument("--model")`。
3. **删** `enter` 子 parser 里的 `sp.add_argument("--model")`。

- [ ] **第 4 步：跑测试，确认通过**

运行：`python -m pytest tests/test_cli.py -v`
预期：PASS。

- [ ] **第 5 步：跑全量，定位其它仍引用旧 flag 的测试**

运行：`python -m pytest -q 2>&1 | head -200`
预期：仍有部分测试 FAIL（任务 18 才统一清理）。

- [ ] **第 6 步：提交**

```bash
git add wiki_workspace/cli.py tests/test_cli.py
git commit -m "refactor(cli): drop --model/--default-model/--profile flags"
```

---

### 任务 18：测试集中清理（manifest / config / list / show / add / init）

**文件：**
- 修改：`tests/test_manifest.py`、`tests/test_config_cmd.py`、`tests/test_add_cmd.py`、`tests/test_init_cmd.py`、`tests/test_list_cmd.py`、`tests/test_show_cmd.py`
**对应 spec：** §5.3（cleanup 部分）。

- [ ] **第 1 步：清理 `tests/test_manifest.py`**

把 `SAMPLE` 里 `default_model` / `model` 字段删：
```python
SAMPLE = """\
schema_version = "1"
created = "2026-06-26"

[wikis.llm-systems]
path = "llm-systems"
display_name = "LLM Systems"
description = "research"
created = "2026-06-26"
tags = ["research", "papers"]
"""
```

把 `test_parse_builds_manifest` 里 `m.default_model` / `w.model` 断言删：
```python
def test_parse_builds_manifest():
    m = manifest.parse(SAMPLE)
    assert m.schema_version == "1"
    assert m.created == "2026-06-26"
    w = m.wikis["llm-systems"]
    assert w.display_name == "LLM Systems"
    assert w.tags == ["research", "papers"]
```

把 `test_parse_missing_fields_default` 改为：
```python
def test_parse_missing_fields_default():
    m = manifest.parse('schema_version = "1"\ncreated = "2026-06-26"\n')
    assert m.wikis == {}
```

把 `test_serialize_round_trips` 里 `assert m2.default_model == "..."` 删：
```python
def test_serialize_round_trips(tmp_path):
    m = manifest.parse(SAMPLE)
    text = manifest.serialize(m)
    m2 = manifest.parse(text)
    assert m2.wikis["llm-systems"].tags == ["research", "papers"]
```

把 `test_empty_manifest_helper` 改：
```python
def test_empty_manifest_helper():
    m = manifest.empty_manifest("2026-06-26")
    assert m.schema_version == "1"
    assert m.wikis == {}
```

把 `test_wiki_entry_defaults` 改：
```python
def test_wiki_entry_defaults():
    e = manifest.WikiEntry(name="r", path="r", display_name="R", created="2026-06-26")
    assert e.description == ""
    assert e.tags == []
```

把 `_manifest` helper 改：
```python
def _manifest(wikis):
    return manifest.Manifest("1", "2026-06-26", {w.name: w for w in wikis})
```

删 `test_validate_unknown_model_warns_not_fails`。

把 `test_validate_path_missing` 与 `test_validate_missing_claude_md` 里 `(tmp_path / "...").mkdir()` 改 `tmp_path`（已有，OK）。

- [ ] **第 2 步：清理 `tests/test_init_cmd.py`**

- **删** `test_init_default_model_stored`。
- `_args` helper 不传 `default_model`（任务 14 已改）。

- [ ] **第 3 步：清理 `tests/test_add_cmd.py`**

`_args` helper 已删 `model=None`（任务 15）。删除任何引用 `model=` 的断言。其它测试不变。

- [ ] **第 4 步：清理 `tests/test_config_cmd.py`**

- **删** `test_config_unset_model`（已被任务 16 的 `test_config_unset_model_rejected` 替换）。
- 修改 `_seed` helper 不再传 `default_model`：
```python
m = manifest.Manifest("1", "2026-06-26", {
    name: manifest.WikiEntry(name=name, path=name, display_name=name.title(), created="2026-06-26"),
})
```

- [ ] **第 5 步：清理 `tests/test_list_cmd.py`**

读 `tests/test_list_cmd.py`：
```bash
grep -n "model\|effective_model\|default_model" tests/test_list_cmd.py
```

把所有引用 `model` / `default_model` / `effective_model` 的代码删（应仅在 `_row` 与 print 表头里）。把 `_row` 改：
```python
def _row(name, w):
    return {
        "name": name,
        "path": w.path,
        "display_name": w.display_name,
        "tags": list(w.tags),
        "created": w.created,
    }
```

调用处改 `[_row(n, w) for n, w in m.wikis.items()]`。`MODEL` 表头删除。

- [ ] **第 6 步：清理 `tests/test_show_cmd.py`**

类似——grep + 删除 model 相关断言（具体行号以文件实际内容为准）。

- [ ] **第 7 步：跑全量**

运行：`python -m pytest -q 2>&1 | tail -50`
预期：所有测试 PASS。剩余少量失败可能源于 `wiki config` / `enter` 边界，按需修。

- [ ] **第 8 步：提交**

```bash
git add tests
git commit -m "test: cleanup v1 model field references across all test files"
```

---

### 任务 19：扩展 `test_e2e_smoke.py` — init → models add → wiki config → enter

**文件：**
- 修改：`tests/test_e2e_smoke.py`
**对应 spec：** §5.3（e2e）。

- [ ] **第 1 步：写失败测试**

追加到 `tests/test_e2e_smoke.py`：
```python
def test_e2e_models_then_wiki_config_then_enter(tmp_path, monkeypatch):
    """init → models add (profile p1) → wiki config (input p1) → enter (mock subprocess)
    → assert 使用 p1。"""
    from wiki_workspace import cli, workspace
    from wiki_workspace.commands import enter_cmd, models_cmd, wiki_config_cmd

    # 1) init
    ws = tmp_path / "ws"
    assert cli.main(["init", "-w", str(ws)]) == 0

    # 2) models add
    monkeypatch.setattr(models_cmd.getpass, "getpass", lambda prompt="": "sk-p1")
    assert cli.main(["models", "add", "--name", "p1",
                     "--model-id", "claude-opus-4-8",
                     "--base-url", "https://api.x",
                     "--set-default", "-w", str(ws)]) == 0

    # 3) add wiki（mock subprocess）
    fake_skill = tmp_path / "skill"
    (fake_skill / "scripts").mkdir(parents=True)
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    from wiki_workspace.commands import add_cmd
    def fake_setup(cmd, **kw):
        wiki_root = __import__("pathlib").Path(cmd[-1])
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "CLAUDE.md").write_text("# " + cmd[-2], encoding="utf-8")
        (wiki_root / "wiki").mkdir(exist_ok=True)
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(add_cmd.subprocess, "run", fake_setup)
    assert cli.main(["add", "w1", "--display-name", "W1", "-w", str(ws)]) == 0

    # 4) wiki config（交互式输入 p1）
    monkeypatch.setattr("builtins.input", lambda prompt="": "p1")
    assert cli.main(["wiki", "config", "--name", "w1", "-w", str(ws)]) == 0

    # 5) enter（mock subprocess）
    captured = {}
    def fake_run(cmd, **kw):
        captured["env"] = kw.get("env")
        captured["cmd"] = cmd
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(enter_cmd.subprocess, "run", fake_run)
    assert cli.main(["enter", "w1", "-w", str(ws)]) == 0

    # 断言：spawn 时用了 p1 的 base_url + api_key
    assert captured["env"][enter_cmd.BASE_URL_ENV] == "https://api.x"
    assert captured["env"][enter_cmd.API_KEY_ENV] == "sk-p1"


def test_e2e_enter_without_profile_uses_workspace_default(tmp_path, monkeypatch):
    """未跑 wiki config；workspace default 存在 → enter 用 default。"""
    from wiki_workspace import cli, workspace
    from wiki_workspace.commands import enter_cmd, models_cmd

    ws = tmp_path / "ws"
    cli.main(["init", "-w", str(ws)])
    monkeypatch.setattr(models_cmd.getpass, "getpass", lambda prompt="": "sk-p1")
    cli.main(["models", "add", "--name", "p1", "--model-id", "m",
              "--base-url", "https://x", "--set-default", "-w", str(ws)])

    # 加 wiki（mock）
    fake_skill = tmp_path / "skill"
    (fake_skill / "scripts").mkdir(parents=True)
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    from wiki_workspace.commands import add_cmd
    def fake_setup(cmd, **kw):
        wiki_root = __import__("pathlib").Path(cmd[-1])
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "CLAUDE.md").write_text("# x", encoding="utf-8")
        (wiki_root / "wiki").mkdir(exist_ok=True)
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(add_cmd.subprocess, "run", fake_setup)
    cli.main(["add", "w1", "-w", str(ws)])

    # enter — 不 wiki config，直接 fallback
    captured = {}
    def fake_run(cmd, **kw):
        captured["env"] = kw.get("env")
        class R:
            returncode = 0
        return R()
    monkeypatch.setattr(enter_cmd.subprocess, "run", fake_run)
    assert cli.main(["enter", "w1", "-w", str(ws)]) == 0
    assert captured["env"][enter_cmd.API_KEY_ENV] == "sk-p1"
```

- [ ] **第 2 步：跑测试，确认通过**

运行：`python -m pytest tests/test_e2e_smoke.py -v`
预期：PASS（新加 2 个 + 既有 1 个 = 3 passed）。

- [ ] **第 3 步：跑全量 + 覆盖率**

运行：`python -m pytest -q --cov=wiki_workspace --cov-report=term-missing`
预期：全绿；`models.py` / `profile.py` 接近 100%；整体 ≥ 85%。**注意：** v1 计划的 `pyproject.toml` 已设 `--cov-fail-under=85`——若不达，**不**下调；为未覆盖分支补针对性测试（多半是 `enter_cmd` 真子进程路径刻意不覆盖、`wiki_config_cmd` 复杂分支）。

- [ ] **第 4 步：提交**

```bash
git add tests/test_e2e_smoke.py
git commit -m "test: e2e models→wiki-config→enter smoke + fallback coverage"
```

---

### 任务 20：README 更新 + 最终验证

**文件：**
- 修改：`README.md`
- 修改：`pyproject.toml`（必要时增补 ruff target 或依赖）

- [ ] **第 1 步：读现状 README**

读取 `README.md`，按本特性增量更新——加 `models add/list/remove/set-default`、`wiki config --name=<wiki>`、`enter` 简化后的说明、profile 概念、gitignore 双层。

- [ ] **第 2 步：重写 README 内容**

最小改动示例：
```markdown
# llmw — LLM Workspace CLI

管理一个由 [llm-wiki-management](https://github.com/yzr95924/llm-wiki-management) wiki 组成的 workspace。

## 安装

​```bash
pip install -e .
​```

## 快速上手

​```bash
# 1. 初始化 workspace
llmw init -w ~/ws

# 2. 配置 model profiles（workspace 级，存于 models.toml，gitignored）
llmw models add --name anthropic-prod \
    --model-id claude-opus-4-8 \
    --base-url https://api.anthropic.com
#  api_key 由 stdin 提示输入（不会出现在 argv history）

# 3. 加 wiki
llmw add llm-systems --display-name "LLM Systems" --topic "LLM Systems" -w ~/ws

# 4. 给 wiki 绑 profile（per-wiki，存于 <wiki>/profile.toml，gitignored）
llmw wiki config --name=llm-systems
#  > model: anthropic-prod

# 5. 进入 wiki（自动用绑定的 profile；profile.toml 缺失则 fallback 到 workspace default）
llmw enter llm-systems -w ~/ws
​```

## Models Registry

`models.toml`（workspace 根，gitignored，权限 0600）保存多个 model profile；每个含 `name` / `model_id` / `base_url` / `api_key`。`<wiki>/profile.toml`（每个 wiki 自己的仓，gitignored）仅保存 `model = "<profile-name>"`——一个 wiki 绑定一个 profile。

profile 解析（`llmw enter` 静态、无 CLI override、无菜单）：
1. `<wiki>/profile.toml` 存在 & `model` 引用现存 profile → 用之
2. `models.toml` `default` 指向现存 profile → 用之（提示 warn）
3. 都没有 → 拒绝启动（`wiki-not-bound`）

`api_key` 一律经 `subprocess.run` 的 env 注入给 `claude`；**永不**出现在 stdout / stderr / 日志。

完整规格见 `doc/2026-06-27-models-registry-design.md` 与 `doc/design.md`。
```

- [ ] **第 3 步：本地跑全量 lint + 测试**

运行：
```bash
ruff format wiki_workspace tests
ruff format --check .
ruff check .
python -m pytest -q
```

预期：format 干净、lint 干净、测试全绿。

- [ ] **第 4 步：手工冒烟（可选）**

```bash
llmw init -w /tmp/llmw-demo
llmw models add --name demo --model-id claude-opus-4-8 --base-url https://x
# api_key 通过 stdin 提示
llmw add demo --topic "Demo" -w /tmp/llmw-demo
llmw wiki config --name=demo
#  > model: demo
llmw enter demo --dry-run -w /tmp/llmw-demo   # 检视 cmd + env（api_key 应 redact 为 ***）
```

- [ ] **第 5 步：提交**

```bash
git add README.md
git commit -m "docs: README covers models registry + wiki config + enter flow"
```

---

### 任务 21：CI workflow 同步 + 全量最终验证

**文件：**
- 修改：`.github/workflows/test.yml`（若需）
- 无新增

- [ ] **第 1 步：核对 CI 配置**

读 `.github/workflows/test.yml`，确认：
- test 矩阵仍为 `[3.7, 3.11]`（沿用 v1 决定）。
- lint job 在 3.11 上跑 `ruff check` + `ruff format --check`。
- test job 不装 `[dev]`（避免 ruff 在 3.7 上回溯）。

若 CI 已正确（v1 计划任务 20 已设），**不**改；只确认工作。

- [ ] **第 2 步：跑全量 + 覆盖率闸门**

运行：
```bash
python -m pytest -q
```

预期：全绿（`--cov-fail-under=85` 自动校验）。**不**下调闸门；若不到，补针对性测试。

- [ ] **第 3 步：跑 ruff 二次确认**

```bash
ruff check .
ruff format --check .
```

预期：均干净。

- [ ] **第 4 步：手工验证 `enter --dry-run` 不泄漏 secret**

```bash
# 在临时 workspace：
llmw init -w /tmp/llmw-final
llmw models add --name prod --model-id claude-opus-4-8 --base-url https://api.x
# 提示时输入：sk-ant-THIS-IS-SECRET
llmw add demo --topic "Demo" -w /tmp/llmw-final
llmw wiki config --name=demo   # 输入 prod
llmw enter demo --dry-run -w /tmp/llmw-final
```

预期：dry-run 输出**不**含 `sk-ant-THIS-IS-SECRET`；env 行 api_key 显示 `***`。

- [ ] **第 5 步：提交（如有 CI 调整）**

```bash
git add .github/workflows/test.yml
git commit -m "ci: verify matrix still aligned post-models-registry"
```

---

## 自检（写完后跑；结论记在这里）

**1. 规格覆盖**

| spec 章节 | 实现任务 |
| --- | --- |
| §1.2 models.toml schema | 任务 1 |
| §1.3 字段表 | 任务 1、2 |
| §1.4 校验规则 | 任务 1（`models.validate`） |
| §1.5 写盘时机 | 任务 2、5、6 |
| §1.6 schema_version | 任务 1（不做 schema_version 字段） |
| §1.7 profile.toml | 任务 7、8、9 |
| §1.8 .workspace.toml 清理 | 任务 13、14、15、16、17 |
| §2.1–2.5 models {add|list|remove|set-default} | 任务 4、5 |
| §2.6 wiki config | 任务 10、11 |
| §2.7 enter 重写 | 任务 12 |
| §3 模块边界 | 任务 1、7（DAG） |
| §4 错误 category | 任务 5、11、12（emit_error 调用） |
| §5 测试 | 任务 1、5、7、11、12、18、19 |
| §6.1 gitignore | 任务 6（workspace）、15（wiki） |
| §6.2 文件权限 0600 | 任务 2（`save_models`）、8（`save_profile`） |

**2. 占位符扫描**——本计划无 TBD / TODO / "implement later"；每处代码块完整可执行；环境变量名占位（任务 1 顶部注 + 任务 12 实跑核对）显式标注。

**3. 类型一致性**——
- `models.ModelRegistry(default, models)` / `ModelEntry(name, model_id, base_url, api_key)` 在任务 1 定义，任务 2 / 3 / 5 全部一致。
- `profile.Profile(model)` 在任务 7 定义，任务 8 / 9 / 11 / 12 全部一致。
- `workspace.load_models` / `save_models` / `load_profile` / `save_profile` 签名在任务 2、8 定义；任务 3、9、11、12 一致调用。
- `enter_cmd.BASE_URL_ENV` / `API_KEY_ENV` 在任务 12 定义；测试与 enter_cmd 一致引用。
- `_common.load_manifest(args)` / `load_models(args)` / `load_profile(wiki_root)` 签名在任务 3、9 一致（manifest/models 收 `args`、profile 收 `wiki_root`）。
- `commands/models_cmd.run_add` / `run_list` / `run_remove` / `run_set_default` 在任务 5 定义；任务 4 的 cli dispatch 一致。

**4. 本计划关闭的缺口**：
- #1 env var names（任务 12 顶部 + 验证日志）
- #2 wiki config clear 语义 = 删文件（任务 11 显式断言）
- #3 `clear` 是保留 profile 名（任务 1 `RESERVED_NAMES` + 任务 1 测试）
- #4 atomic_write 0600（任务 2、8 测试断言）
- #5 dump 始终 emit `default = ""`（任务 2 dump_models_toml 实现）

**5. 待人工验证项（合并前）**：
- Claude Code / Anthropic SDK 环境变量名（任务 12 顶部占位 + 实跑核对）
- `enter --dry-run` 真的把 env 传给子进程（任务 21 第 4 步）

---

## 验证日志（执行期补充）

> 此节由执行子 agent 填——每条修改、偏离、发现的环境变量名核实都记在这里。

---

## 执行交接

**计划已完成并保存到 `doc/plans/2026-06-27-models-registry.md`。两种执行方式：**

**1. 子 agent 驱动（推荐）**——每个任务派一个全新子 agent，任务之间 review，迭代快。对 21 个任务的计划最合适：每个子 agent 拿到一个任务 + 本计划文件 + 设计稿作为上下文，返回 diff，确认测试通过后再推进。

**2. 当前会话内执行**——用 superpowers:executing-plans 在本会话执行，分批 + 检查点 review。

**选哪种？**
