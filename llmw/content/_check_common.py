"""check 系列共享 helper（read_text / semver 比较 / 模板出边扫描 / 规则清单输出）。

只承载跨文件逐字相同的无状态 helper；各 check 文件独有的 registry / schema 字段留原地。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")

# 模板零出边引用：§节号引用（如 `§6`；文件级 pattern 清单由各 check 文件自持）
TEMPLATE_OUTBOUND_SECTION_RE = re.compile(r"§[0-9]")

_ANCHOR_TABLE_RE = re.compile(r"^\[\[(\w+)\]\]\s*$")
_ANCHOR_STRING_RE = re.compile(r'^([a-z_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$')
_ANCHOR_SCALAR_RE = re.compile(r"^([a-z_]+)\s*=\s*([0-9]+|true|false)\s*$")
_ANCHOR_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def parse_anchor_entries(text: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """anchor TOML 词法解析（[[entry]] + 双引号标量）；不校验字段，schema_version 单独返回。"""
    entries = []  # type: List[Dict[str, str]]
    current = None  # type: Optional[Dict[str, str]]
    schema_version = None  # type: Optional[str]
    for raw_line in text.splitlines():
        # 行内注释：仅在引号外剥离（anchor 实际写出字符串不含 #）
        if "#" in raw_line:
            in_str = False
            cut = -1
            for i, ch in enumerate(raw_line):
                if ch == '"':
                    in_str = not in_str
                elif ch == "#" and not in_str:
                    cut = i
                    break
            if cut >= 0:
                raw_line = raw_line[:cut]
        stripped = raw_line.rstrip().strip()
        if not stripped:
            continue
        m = _ANCHOR_TABLE_RE.match(stripped)
        if m:
            if current is not None:
                entries.append(current)
            current = {}
            continue
        m = _ANCHOR_STRING_RE.match(stripped)
        if m:
            key, raw_val = m.group(1), m.group(2)
            val = re.sub(
                r"\\(.)",
                lambda mo: _ANCHOR_ESCAPES.get(mo.group(1), mo.group(1)),
                raw_val,
            )
            if current is not None:
                current[key] = val
            continue
        m = _ANCHOR_SCALAR_RE.match(stripped)
        if m and m.group(1) == "schema_version":
            schema_version = m.group(2)
    if current is not None:
        entries.append(current)
    return entries, schema_version


def read_text(path: Path) -> Optional[str]:
    """读文件文本；失败返 None（不抛异常；fixture-check 静默容错）。"""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def compare_semver(a: Optional[str], b: Optional[str]) -> str:
    """返 'equal' / 'older' / 'newer' / 'unknown'。缺值=unknown。"""
    if not a or not b:
        return "unknown"

    def parse(v: str) -> Optional[Tuple[int, int, int]]:
        m = SEMVER_RE.search(v)
        if not m:
            return None
        try:
            return tuple(int(x) for x in m.group(0).split("."))  # type: ignore
        except ValueError:
            return None

    av, bv = parse(a), parse(b)
    if not av or not bv:
        return "unknown"
    if av < bv:
        return "older"
    if av > bv:
        return "newer"
    return "equal"


def scan_template_outbound_refs(text: str, patterns: Tuple[str, ...]) -> List[str]:
    """扫模板出边引用，返回 ["<行号>:<模式>", ...]；patterns 由调用方传入。"""
    hits: List[str] = []
    for ln_no, ln in enumerate(text.splitlines(), 1):
        for pat in patterns:
            if pat in ln:
                hits.append(f"{ln_no}:{pat}")
        if TEMPLATE_OUTBOUND_SECTION_RE.search(ln):
            hits.append(f"{ln_no}:§节号引用")
    return hits


def format_rules_md(title: str, registry: List[Dict[str, object]]) -> str:
    """--list-rules markdown 输出。"""
    lines: List[str] = [
        "## " + title,
        "",
        "| ID | Severity | File | 规则引用 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for reg in registry:
        rid = reg["id"]
        sev = reg["severity"]
        file_target = reg.get("file", "")
        rule_ref = reg["rule_ref"]
        desc = reg["desc"]
        lines.append(f"| `{rid}` | {sev} | `{file_target}` | {rule_ref} | {desc} |")
    return "\n".join(lines)


def rules_json(registry: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """--list-rules JSON 输出。"""
    return [
        {
            "id": reg["id"],
            "severity": reg["severity"],
            "file": reg.get("file", ""),
            "rule_ref": reg["rule_ref"],
            "desc": reg["desc"],
        }
        for reg in registry
    ]


def print_rules(title: str, registry: List[Dict[str, object]], as_json: bool) -> int:
    """--list-rules 业务入口（自包含，无需 root）。"""
    if as_json:
        print(json.dumps(rules_json(registry), indent=2, ensure_ascii=False))
    else:
        print(format_rules_md(title, registry))
    return 0
