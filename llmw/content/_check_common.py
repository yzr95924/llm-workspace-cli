"""check 系列共享 helper（read_text / semver 比较 / 模板出边扫描 / 规则清单输出）。

wiki_fixtures / workspace_fixtures / wiki_lint / upgrade / upgrade_workspace 的逐字重复
脚手架下沉到本文件——保留各自文件自己的 CHECK_REGISTRY、check_* 函数、
TEMPLATE_OUTBOUND_PATTERNS（两份清单条目不同，有意分歧）。

模块边界：本文件只承载**跨文件逐字相同的无状态 helper**；各 check 文件独有的
输出 schema 字段（fix / wiki_format 等）仍留在各自 _format_human 与 run_checks 里。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")

# 模板零出边引用：§节号引用（如「§6」）——与文件级 pattern 清单（各 check 文件独自定义）联用。
TEMPLATE_OUTBOUND_SECTION_RE = re.compile(r"§[0-9]")


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
    """扫模板文本中的出边引用，返回 ["<行号>:<模式>", ...]（空 = 干净）。

    检测逻辑直接喂合成文本便于测试；check 函数做文件 IO + 报告。
    patterns 由调用方传入（wiki_fixtures 与 workspace_fixtures 的清单条目不同）。
    """
    hits: List[str] = []
    for ln_no, ln in enumerate(text.splitlines(), 1):
        for pat in patterns:
            if pat in ln:
                hits.append(f"{ln_no}:{pat}")
        if TEMPLATE_OUTBOUND_SECTION_RE.search(ln):
            hits.append(f"{ln_no}:§节号引用")
    return hits


def format_rules_md(title: str, registry: List[Dict[str, object]]) -> str:
    """--list-rules markdown 输出：代码真源 → 规则清单。"""
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
