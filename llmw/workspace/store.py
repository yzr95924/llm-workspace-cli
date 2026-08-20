"""workspace.toml 读写 + schema 校验

schema v2: workspace.toml 只承载**结构数据** (schema 元信息 + wiki 注册表)。
v1（``enter_cli`` / ``enter_byobu`` / ``default_model``）已于 2026-08 退役，
load v1 → ``SchemaVersionUnsupported``（无自愈路径）。
"""

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from llmw import WORKSPACE_FORMAT_VERSION, WIKI_FORMAT_VERSION
from llmw._compat import toml_loads, toml_dump
from llmw.errors import SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 2


@dataclass
class WikiEntry:
    """workspace.toml [wikis.<name>] 表项"""

    name: str
    path: str
    created_at: str


@dataclass
class WorkspaceToml:
    """workspace.toml 解析结果 (schema v2: 结构数据 only)"""

    schema_version: int
    created_at: str
    templates_version: str = "1"
    wikis: Dict[str, WikiEntry] = field(default_factory=dict)


def load(workspace_root: Path) -> WorkspaceToml:
    """从 <workspace_root>/workspace.toml 加载并校验。"""
    toml_path = workspace_root / "workspace.toml"
    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read().decode("utf-8"))

    sv = raw.get("schema_version")
    if sv != SCHEMA_VERSION_SUPPORTED:
        raise SchemaVersionUnsupported(
            f"workspace.toml schema_version={sv} 不被支持 "
            f"(当前 CLI 仅支持 v{SCHEMA_VERSION_SUPPORTED})",
            hint="升级 CLI 或手动迁移 schema_version",
        )

    wikis: Dict[str, WikiEntry] = {}
    for name, info in raw.get("wikis", {}).items():
        wikis[name] = WikiEntry(
            name=name,
            path=info["path"],
            created_at=info.get("created_at", ""),
        )

    return WorkspaceToml(
        schema_version=sv,
        created_at=raw.get("created_at", ""),
        templates_version=raw.get("templates_version", "1"),
        wikis=wikis,
    )


def save(workspace_root: Path, ws: WorkspaceToml) -> None:
    """写回 <workspace_root>/workspace.toml (原子写)。schema v2: 仅结构数据。"""
    toml_path = workspace_root / "workspace.toml"
    data = {
        "schema_version": ws.schema_version,
        "created_at": ws.created_at,
        "templates_version": ws.templates_version,
    }

    if ws.wikis:
        wiki_table = {}
        for name, entry in ws.wikis.items():
            wiki_table[name] = {
                "path": entry.path,
                "created_at": entry.created_at,
            }
        data["wikis"] = wiki_table

    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())


def create_skeleton(workspace_root: Path) -> WorkspaceToml:
    """init 时调用：生成空 workspace.toml (schema v2)。

    templates_version 编码双 format 版本（供 llmw upgrade 收尾比对），供 skill scan 前比对：
    形如 ``workspace_format=0.2.0; wiki_format=0.5.0``。
    """
    ws = WorkspaceToml(
        schema_version=SCHEMA_VERSION_SUPPORTED,
        created_at=now_iso8601(),
        templates_version=(
            f"workspace_format={WORKSPACE_FORMAT_VERSION}; wiki_format={WIKI_FORMAT_VERSION}"
        ),
    )
    save(workspace_root, ws)
    return ws
