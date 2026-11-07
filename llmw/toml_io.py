"""TOML 读写：stdlib tomllib + 手写 dump。

Python 基线升至 3.12 后不再需要 tomli 回退；dump 仍由本模块统一实现
（tomllib 只有 loads / loads，没有 dump）。
"""

import io
from tomllib import TOMLDecodeError, loads as toml_loads

__all__ = ["TOMLDecodeError", "toml_loads", "toml_dump"]


def _toml_dumps(data: dict) -> str:
    # 简单实现：仅处理本项目使用的 dict[str, scalar | list | dict]
    buf = io.StringIO()
    _dump_section(buf, data, prefix="")
    return buf.getvalue()


def _dump_section(buf: io.StringIO, data: dict, prefix: str) -> None:
    scalars: dict[str, object] = {}
    arrays: list[tuple[str, list[dict]]] = []
    tables: dict[str, dict] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            tables[k] = v
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            # array-of-tables: [[prefix.k]]
            arrays.append((k, v))
        else:
            scalars[k] = v
    # 先写 scalars，再写 array-of-tables，最后写 tables（保持正确 TOML 解析顺序）
    _dump_kv(buf, scalars.items())
    for k, items in arrays:
        for item in items:
            buf.write(f"\n[[{prefix}{k}]]\n")
            _dump_kv(buf, item.items())
    for k, v in tables.items():
        buf.write(f"\n[{prefix}{k}]\n")
        _dump_section(buf, v, prefix=f"{prefix}{k}.")


# 不转义则含 \ 或 " 的值产出非法 TOML，load 即炸
_BASIC_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",  # U+0008
    "\t": "\\t",  # U+0009
    "\n": "\\n",  # U+000A
    "\f": "\\f",  # U+000C
    "\r": "\\r",  # U+000D
}


def _toml_escape_str(s: str) -> str:
    """转义为合法 TOML basic string 内容（不含两侧双引号）。

    逐字符处理， 天然避免二次转义；其余控制字符 (U+0000..U+001F 除已列举) 用 \\uXXXX。
    """
    out = []
    for ch in s:
        if ch in _BASIC_ESCAPES:
            out.append(_BASIC_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _dump_kv(buf: io.StringIO, items) -> None:
    for k, v in items:
        if isinstance(v, str):
            buf.write(f'{k} = "{_toml_escape_str(v)}"\n')
        elif isinstance(v, bool):
            buf.write(f"{k} = {str(v).lower()}\n")
        elif isinstance(v, list):
            inner = ", ".join(
                f'"{_toml_escape_str(x)}"'
                if isinstance(x, str)
                else (str(x).lower() if isinstance(x, bool) else str(x))
                for x in v
            )
            buf.write(f"{k} = [{inner}]\n")
        else:
            buf.write(f"{k} = {v}\n")


def toml_dump(data: dict, fp) -> None:
    """统一手写 dump 实现（stdlib tomllib 没有 dump）。"""
    fp.write(_toml_dumps(data))
