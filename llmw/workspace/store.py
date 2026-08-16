"""workspace.toml 读写 + schema 校验

schema v2: workspace.toml 只承载**结构数据** (schema 元信息 + wiki 注册表)。
原 v1 的运行时字段是主机相关配置：``enter_cli`` v2 起迁出到 workspace_local.toml
(见 llmw/workspace/local_store.py)；``enter_byobu`` / ``default_model`` 静默丢弃
(enter_byobu 设计 doc/session-visibility-design.md §2.5 删除；default_model 不在
resolve 路径、误导性死配置面，"默认 model" 由 registry ``is_default`` 表达)。
老 v1 workspace 首次 load 自动迁移 (自愈、幂等，见 ``_migrate_v1_to_v2``)。
"""

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from llmw import WORKSPACE_SPEC_VERSION, WIKI_SPEC_VERSION
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
    """workspace.toml 解析结果 (schema v2: 结构数据 only)

    v2 起不再含运行时字段——``enter_cli`` 迁出到 ``workspace_local.toml``
    (见 local_store.py)；``enter_byobu`` / ``default_model`` 删除 (见
    ``_migrate_v1_to_v2``)。
    """

    schema_version: int
    created_at: str
    templates_version: str = "1"
    wikis: Dict[str, WikiEntry] = field(default_factory=dict)


def load(workspace_root: Path) -> WorkspaceToml:
    """从 <workspace_root>/workspace.toml 加载并校验。

    schema_version=1 (老 workspace) → 自动迁移到 v2 后 reload (自愈、幂等)。
    """
    toml_path = workspace_root / "workspace.toml"
    with open(toml_path, "rb") as f:
        raw = toml_loads(f.read().decode("utf-8"))

    sv = raw.get("schema_version")
    if sv == 1:
        _migrate_v1_to_v2(workspace_root, raw)
        return load(workspace_root)  # 迁移后 reload 为 v2
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


def _migrate_v1_to_v2(workspace_root: Path, raw_v1: dict) -> None:
    """workspace.toml schema v1 → v2: 把 enter_cli 抽到 workspace_local.toml，
    workspace.toml 重写为 v2。

    - v1 的 ``default_model`` 字段**静默丢弃**——它不在 ``resolve_for_wiki`` 解析路径
      (仅 wiki show 兜底显示)，是无功能的误导性配置面；"默认 model" 由 registry 的
      ``is_default`` 单一表达。
    - v1 的 ``enter_byobu`` 字段**静默丢弃**（设计 doc/session-visibility-design.md
      §2.5 已删除该配置——窗口路径全环境成立，直启模式无存在场景）。
    - merge 不覆盖：local 已有值 (用户可能已在另一台机配过) 优先，仅填空。
    - 空值不落 local 文件：v1 字段 unset 时不创建 workspace_local.toml。
    - 写 local 前确保 gitignore 含 ``workspace_local.toml`` 排除行 (否则 secret/隐私
      配置可能被误提交)。

    自愈迁移：老 workspace 首次 ``load`` 即触发，幂等 (迁完 schema_version=2，下次
    load 走 v2 分支不再进)。lazy import 避免 store ↔ local_store 循环。
    """
    from llmw.workspace import local_store
    from llmw.workspace.gitignore import ensure_workspace_gitignore

    # 抽出 v1 运行时字段
    enter_cli = raw_v1.get("enter_cli")

    # 写 local 前确保 gitignore 就位
    ensure_workspace_gitignore(workspace_root)

    # merge 进 local (不覆盖已有)
    local = local_store.load(workspace_root)
    if enter_cli is not None and local.enter_cli is None:
        local.enter_cli = enter_cli
    # 仅当确有运行时值才落 local 文件 (避免空文件)
    if local.enter_cli:
        local_store.save(workspace_root, local)

    # workspace.toml 重写为 v2 (drop 3 运行时字段)
    data = {
        "schema_version": SCHEMA_VERSION_SUPPORTED,
        "created_at": raw_v1["created_at"],
        "templates_version": raw_v1.get("templates_version", "1"),
    }
    wikis = {}
    for name, info in raw_v1.get("wikis", {}).items():
        wikis[name] = {"path": info["path"], "created_at": info["created_at"]}
    if wikis:
        data["wikis"] = wikis

    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(workspace_root / "workspace.toml", buf.getvalue())


def create_skeleton(workspace_root: Path) -> WorkspaceToml:
    """init 时调用：生成空 workspace.toml (schema v2)。

    templates_version 编码双 spec 版本(spec §14)，供 skill scan 前比对：
    形如 ``workspace_spec=0.2.0; wiki_spec=0.5.0``。
    """
    ws = WorkspaceToml(
        schema_version=SCHEMA_VERSION_SUPPORTED,
        created_at=now_iso8601(),
        templates_version=(
            f"workspace_spec={WORKSPACE_SPEC_VERSION}; wiki_spec={WIKI_SPEC_VERSION}"
        ),
    )
    save(workspace_root, ws)
    return ws
