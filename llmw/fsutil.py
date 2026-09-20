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
    """原子写：tmp + fsync + os.replace（POSIX 原子）；失败清理 tmp。"""
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
    """rm -rf 包装；失败异常交调用方处理。"""
    import shutil

    shutil.rmtree(path)


def chmod_600(path: Path) -> None:
    """chmod 600 best-effort（NFS 等静默跳过）；含 secret 文件落盘后统一走这里。"""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_json_optional(path: Path) -> Optional[dict]:
    """不存在 → None；JSON 非法 → ValueError（业务异常包装留给调用方）。"""
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
