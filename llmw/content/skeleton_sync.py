"""rename 骨架同步计划：AGENTS.md 重渲染 + index/log 头部 topic 行替换（纯计划，零写盘）。

机械 scribe 收口 content/（与 upgrade 的 byte-owned 渲染同族）；写盘与回滚由 manager.rename 编排。
手改检测语义与 upgrade._agents_md_pristine 对齐：无指纹或指纹不符 → drift（须 --yes 确认才覆盖）。
"""

import hashlib
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from llmw import WIKI_FORMAT_VERSION, __version__
from llmw.config import wiki_templates_dir
from llmw.content.render import read_template, render_wiki_agents_md, setup_date
from llmw.fsutil import sha256_file

_TOPIC_PH = "{{TOPIC_NAME}}"

# fixture 模板 → wiki 相对路径：仅 header-owned 且出生头部含 topic 行的文件
# （templates 全域 grep 确认 tags.md / scripts.md 无 {{TOPIC_NAME}}，不入列）
_TOPIC_FIXTURES = (
    ("index.md", "wiki/index.md"),
    ("log.md", "wiki/log.md"),
)


class SkeletonSyncPlan(NamedTuple):
    """writes / backups 键为 wiki 相对路径；插入序 = 写盘序（AGENTS.md 在前）。"""

    writes: Dict[str, str]
    backups: Dict[str, str]
    agents_new_digest: Optional[str]
    drift: bool
    warnings: List[str]


def empty_plan() -> SkeletonSyncPlan:
    """topic 自定义时的空计划：writes/backups 空 → 落盘与回滚天然 no-op，调用方免判 None。"""
    return SkeletonSyncPlan(writes={}, backups={}, agents_new_digest=None, drift=False, warnings=[])


def plan_skeleton_sync(wiki_dir: Path, old_topic: str, new_topic: str, meta) -> SkeletonSyncPlan:
    """生成 new_topic 下的骨架同步计划（只读，不写盘）。

    meta 为 wiki_store.WikiMetadata（消费 created_at / agents_md_sha256）。
    活文件严格 utf-8 读（异于 checker 侧 errors="replace" 的宽松读）：计划字节会被
    原样写回，宽松读会把损坏字节替换成 U+FFFD 再落盘，等于借 rename 固化损坏。
    Raises: SetupFailed（包内 fixture 模板缺失）。
    """
    writes = {}  # type: Dict[str, str]
    backups = {}  # type: Dict[str, str]
    warnings = []  # type: List[str]

    agents_p = wiki_dir / "AGENTS.md"
    agents_digest = None  # type: Optional[str]
    drift = False
    if agents_p.is_file():
        old_text = agents_p.read_text(encoding="utf-8")
        new_text = render_wiki_agents_md(
            topic=new_topic,
            setup_date=setup_date(meta.created_at),
            cli_version=__version__,
            format_version=WIKI_FORMAT_VERSION,
        )
        agents_digest = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
        current = sha256_file(agents_p)
        if not meta.agents_md_sha256 or current != meta.agents_md_sha256:
            drift = True
        backups["AGENTS.md"] = old_text
        writes["AGENTS.md"] = new_text
    else:
        warnings.append("AGENTS.md 不存在，跳过重渲染（可 `llmw wiki upgrade --apply` 重建）")

    fixtures = wiki_templates_dir() / "fixtures"
    for tmpl_name, rel in _TOPIC_FIXTURES:
        target = wiki_dir / rel
        if not target.is_file():
            warnings.append(f"{rel} 不存在，跳过头部 topic 同步")
            continue
        template = read_template(fixtures / tmpl_name)
        topic_lines = [ln for ln in template.splitlines() if _TOPIC_PH in ln]
        if not topic_lines:
            continue
        old_text = target.read_text(encoding="utf-8")
        lines = old_text.splitlines(keepends=True)
        replaced = 0
        unmatched = 0
        for tpl_line in topic_lines:
            old_form = tpl_line.replace(_TOPIC_PH, old_topic)
            new_form = tpl_line.replace(_TOPIC_PH, new_topic)
            hit = False
            for i, ln in enumerate(lines):
                if ln.rstrip("\n") == old_form:
                    lines[i] = new_form + ("\n" if ln.endswith("\n") else "")
                    hit = True
                    replaced += 1
            if not hit:
                unmatched += 1
        if replaced:
            backups[rel] = old_text
            writes[rel] = "".join(lines)
        if unmatched:
            warnings.append(f"{rel} 有 {unmatched}/{len(topic_lines)} 条 topic 行非出生形态（可能被手改），未同步")

    return SkeletonSyncPlan(
        writes=writes,
        backups=backups,
        agents_new_digest=agents_digest,
        drift=drift,
        warnings=warnings,
    )
