"""workspace_local.toml 读写（主机相关运行时配置，如 enter_cli）。

从 workspace.toml 拆出避免跨主机 churn；gitignored、无 secret 不 chmod。
load 缺文件返回空骨架（不写盘）；老键（default_model / enter_byobu）静默忽略，下次 save 抹除。
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
    """解析结果；字段全可选（None = 未设）。结构数据仍在 workspace.toml。"""

    schema_version: int
    created_at: str
    enter_cli: Optional[str] = None  # 未设 = DEFAULT_BACKEND


def load(workspace_root: Path) -> WorkspaceLocal:
    """加载校验；文件不存在 → 空骨架（不写盘，纯读路径不落空文件）。"""
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

    return WorkspaceLocal(
        schema_version=sv,
        created_at=raw.get("created_at", now_iso8601()),
        enter_cli=raw.get("enter_cli"),
    )


def save(workspace_root: Path, wl: WorkspaceLocal) -> None:
    """原子写回；无 chmod（不含 secret）；created_at 透传保持稳定。"""
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
