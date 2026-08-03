"""workspace_local.toml 读写 (主机相关运行时配置)

承接原 workspace.toml 的三个运行时字段——``default_model`` / ``enter_cli`` /
``enter_byobu``——它们描述"**这台主机**装了哪个 agent / 是否有 byobu / 默认用哪个
model"，跨主机共用一个 git 跟踪的 workspace.toml 会互相覆盖产生 churn。schema v2 起
从 workspace.toml (git 跟踪的结构数据) 拆出，落本文件，gitignored (workspace
.gitignore managed block)。无 secret (api_key 在 workspace_models.toml)，不 chmod 600。

与 workspace/store.py 风格对齐：dataclass + load/save/create_skeleton，原子写。
load 文件缺失返回空骨架（不写盘）——与"运行时配置未设"同态，调用点免判空文件。
"""

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from llmw._compat import toml_loads, toml_dump
from llmw.errors import SchemaVersionUnsupported
from llmw.fsutil import atomic_write, now_iso8601

SCHEMA_VERSION_SUPPORTED = 1


@dataclass
class WorkspaceLocal:
    """workspace_local.toml 解析结果 (主机相关运行时配置)。

    三字段全可选 (None = 未设)：default_model / enter_cli / enter_byobu。
    与 ``WorkspaceToml`` 正交——结构数据 (wiki 注册表 / schema 元信息) 仍在 workspace.toml。
    """

    schema_version: int
    created_at: str
    default_model: Optional[str] = None
    enter_cli: Optional[str] = None  # "claude" (默认) | "qodercli" | "opencode"
    # True = wiki enter 在 byobu 固定 session (llm_workspace) 按 wiki 名开窗口；
    # None/False = 阻塞直启。session 名是代码常量 (llmw/wiki/byobu.py)，不可配。
    enter_byobu: Optional[bool] = None


def load(workspace_root: Path) -> WorkspaceLocal:
    """从 <workspace_root>/workspace_local.toml 加载并校验。

    文件不存在 → 返回空骨架 (三字段 None，schema_version 当前版本)。不写盘——
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

    # 严格只吃真 TOML 布尔；手改成 "true"/"false" 字符串按 unset 处理
    # (防 Python bool("false") is True 陷阱把 byobu 模式静默打开，与 ws_store.load 一致)
    enter_byobu_raw = raw.get("enter_byobu")
    return WorkspaceLocal(
        schema_version=sv,
        created_at=raw.get("created_at", now_iso8601()),
        default_model=raw.get("default_model"),
        enter_cli=raw.get("enter_cli"),
        enter_byobu=enter_byobu_raw if isinstance(enter_byobu_raw, bool) else None,
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
    if wl.default_model is not None:
        data["default_model"] = wl.default_model
    # enter_cli = "claude" 是默认值，不落盘 (行不存在即 claude)，与 store.py 旧逻辑一致
    if wl.enter_cli is not None and wl.enter_cli != "claude":
        data["enter_cli"] = wl.enter_cli
    # 仅 True 落盘 (enter_byobu = true)；None/False 同态——行不存在即为关
    if wl.enter_byobu:
        data["enter_byobu"] = True

    buf = io.StringIO()
    toml_dump(data, buf)
    atomic_write(toml_path, buf.getvalue())
