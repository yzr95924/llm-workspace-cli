"""workspace_local.toml 读写 (主机相关运行时配置)

承接原 workspace.toml 的运行时字段 ``enter_cli``——它描述"**这台主机**装了哪个 agent"，
跨主机共用一个 git 跟踪的 workspace.toml 会互相覆盖产生 churn。schema v2 起从
workspace.toml (git 跟踪的结构数据) 拆出，落本文件，gitignored (workspace .gitignore
managed block)。无 secret (api_key 在 workspace_models.toml)，不 chmod 600。

(原 v1 的 ``default_model`` 字段在 schema v2 迁移时**静默丢弃**——它本就不在
``resolve_for_wiki`` 解析路径里、仅 wiki show 兜底显示，是误导性死配置面；"默认 model"
概念由 registry 的 ``is_default`` 单一表达。原 ``enter_byobu`` 字段在设计
doc/session-visibility-design.md 起同样删除——窗口路径已全环境成立，直启模式无存在
场景；老文件残留该键时 load 静默忽略，下次 save 自然抹除，不做主动迁移。)

与 workspace/store.py 风格对齐：dataclass + load/save/create_skeleton，原子写。
load 文件缺失返回空骨架（不写盘）——与"运行时配置未设"同态，调用点免判空文件。
"""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from llmw._compat import toml_loads, toml_dump
from llmw.backends import DEFAULT_BACKEND
from llmw.errors import SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 1


@dataclass
class WorkspaceLocal:
    """workspace_local.toml 解析结果 (主机相关运行时配置)。

    字段全可选 (None = 未设)：enter_cli。
    与 ``WorkspaceToml`` 正交——结构数据 (wiki 注册表 / schema 元信息) 仍在 workspace.toml。
    """

    schema_version: int
    created_at: str
    enter_cli: Optional[str] = (
        None  # DEFAULT_BACKEND (claude) | "qodercli" | "opencode"
    )


def load(workspace_root: Path) -> WorkspaceLocal:
    """从 <workspace_root>/workspace_local.toml 加载并校验。

    文件不存在 → 返回空骨架 (字段 None，schema_version 当前版本)。不写盘——
    纯读路径 (如 ``enter``) 不会因读配置而落出空文件。
    """
    toml_path = workspace_root / "workspace_local.toml"
    if not toml_path.is_file():
        return WorkspaceLocal(
            schema_version=SCHEMA_VERSION_SUPPORTED,
            created_at=now_iso8601(),
        )

    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read().decode("utf-8"))

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"workspace_local.toml schema_version={sv} 不被支持 "
            f"(当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移 schema_version",
        )

    # 注：老 local 文件可能残留 enter_byobu 行（随 doc/session-visibility-design.md §2.5 删除）——TOML 对未知 key
    # 宽容，这里不读即静默忽略，不 bump schema_version；下次 save 自然抹除。
    return WorkspaceLocal(
        schema_version=sv,
        created_at=raw.get("created_at", now_iso8601()),
        enter_cli=raw.get("enter_cli"),
    )


def save(workspace_root: Path, wl: WorkspaceLocal) -> None:
    """原子写回 <workspace_root>/workspace_local.toml。

    无 chmod——本文件不含 secret (api_key 在 workspace_models.toml)。
    created_at 透传：load 读出 → 改字段 → save 写回，created_at 稳定不变。
    """
    toml_path = workspace_root / "workspace_local.toml"
    data = {
        "schema_version": wl.schema_version,
        "created_at": wl.created_at,
    }
    # enter_cli = 默认 backend 时不落盘 (行不存在即默认)，与 store.py 旧逻辑一致
    if wl.enter_cli is not None and wl.enter_cli != DEFAULT_BACKEND:
        data["enter_cli"] = wl.enter_cli

    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())
