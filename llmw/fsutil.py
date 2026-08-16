"""文件系统原子写 + 辅助"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def now_iso8601() -> str:
    """UTC ISO8601 时间，秒精度，Z 后缀"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write(path: Path, content: str) -> None:
    """原子写文件

    1. 写 <path>.tmp.<pid>
    2. flush + fsync
    3. os.replace() (POSIX 原子)
    4. 失败时清理 tmp 文件
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def safe_rmtree(path: Path) -> None:
    """rm -rf 包装：失败由调用方处理（已存在的目录可能被外部占用）"""
    import shutil

    shutil.rmtree(path)


def chmod_600(path: Path) -> None:
    """chmod 600 best-effort：NFS 等不支持 chmod 的 FS 上静默跳过（权限安全是 best-effort）。

    含 secret 的文件（registry / overlay）落盘后统一走这里，避免各处重复 try/except。
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_json_optional(path: Path) -> Optional[dict]:
    """读 JSON 文件：不存在 → None；JSON 非法 → ValueError（调用方按语义转业务异常）。

    共享 overlay 两模块的"读现有文件"IO 骨架——文件级语义（不存在/非法）在此统一，
    业务级语义（OverlayFileUnparseable 的 hint 文案）留在调用方。
    """
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
