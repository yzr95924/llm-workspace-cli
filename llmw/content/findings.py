"""lint finding 注册表——finding 名 / severity / 含义 / 修法的唯一真源（SSOT）。

消费端：
- ``wiki_lint.severity_of``（严重性映射）
- ``llmw wiki lint --explain [name]``（解释输出；agent 按需读，替代散文镜像）

新增 deterministic 检查 = 本表加一条 + wiki_lint.py 发射同名 finding；
``tests/test_findings_registry.py`` 双向穷举校验（漏配 / 死条目均红）。
severity 取值：error / warn / info。
"""

from typing import NamedTuple, Optional, Tuple

from llmw.content.page_types import CONTENT_TYPES, TYPES_DISPLAY


class FindingSpec(NamedTuple):
    """一条 finding 的规格。"""

    severity: str
    summary: str  # 触发条件 / 意味着什么
    fix: str  # 修法（命令或动作）


FINDINGS = {
    # --- error：结构 / 纪律违规，必须修 ---
    "broken-link": FindingSpec(
        "error",
        "wiki/**/*.md 正文 Markdown 链接 / 图片的相对路径不指向现存文件（外部 URL 跳过）",
        "修正链接目标，或补齐被引文件",
    ),
    "external-anchor-corrupt": FindingSpec(
        "error",
        "raw/external/.symlink-anchor.toml 解析失败或 0 个有效 entry",
        "检查 TOML 语法；无法修复时用 `llmw wiki external add` 重建（CLI 持有 schema SSOT）",
    ),
    "external-anchor-missing": FindingSpec(
        "error",
        "raw/external/ 下有 symlink，但 anchor 文件（.symlink-anchor.toml）不存在",
        "用 `llmw wiki external add <path> --name=<name>` 注册，或移除多余 symlink",
    ),
    "external-source-name-invalid": FindingSpec(
        "error",
        "raw/external/ 顶层出现不合命名规范的 symlink / 子目录 / 普通文件（要求 kebab-case symlink、扁平布局）",
        "改名或清理；接入走 `llmw wiki external add` 正路（命名规则由 CLI 持有）",
    ),
    "external-symlink-missing": FindingSpec(
        "error",
        "anchor 有 entry，但 raw/external/ 顶层无对应 symlink",
        "`llmw wiki external rebuild` 重建 symlink",
    ),
    "external-target-dead": FindingSpec(
        "error",
        "anchor entry 的 target 路径不存在（目标仓被移动 / 删除）",
        "确认目标仓新路径后 `llmw wiki external remove <name>` + `add` 重挂",
    ),
    "frontmatter-delimiter-glued": FindingSpec(
        "error",
        "frontmatter 闭合 `---` 与正文粘连（如 `---# 标题`）——定界符失效、整页不渲染",
        "手动 Edit 在闭合 `---` 后补换行",
    ),
    "index-entry-wrong-section": FindingSpec(
        "error",
        "index.md 条目落在与页 type 不符的 `##` 类别段",
        "`llmw wiki write index remove` + `add` 重挂（修复后的 add 按 type 归回正确段）",
    ),
    "index-missing": FindingSpec(
        "error",
        "wiki/index.md 不存在（wiki 单一入口缺失）",
        "按 fixture `index.md.txt` 形态重建，或恢复自 git 历史",
    ),
    "invalid-tags": FindingSpec(
        "error",
        "frontmatter `tags` 不是 list 类型（内容页与 MEMORY/*.md 均查）",
        "改为 YAML list（如 `tags: [tag-a, tag-b]`）",
    ),
    "invalid-type": FindingSpec(
        "error",
        f"frontmatter `type` 取值非法；内容页应为 {TYPES_DISPLAY}",
        f"改为 {len(CONTENT_TYPES)} 类之一（字段定义见夹具头部契约）",
    ),
    "log-missing": FindingSpec(
        "error",
        "wiki/log.md 不存在",
        "按 fixture `log.md.txt` 形态重建",
    ),
    "missing-frontmatter": FindingSpec(
        "error",
        "内容页缺必填 frontmatter 字段（title / type / created / updated / tags）；MEMORY/*.md 仅 title 必填",
        "补齐缺失字段（字段契约 canonical 见各 fixture 头部）",
    ),
    "missing-sources": FindingSpec(
        "error",
        "source / synthesis 页缺 `sources` 字段或为空",
        "补 `sources:`（wiki 根相对 raw/ 路径；synthesis 可指 wiki 内页）",
    ),
    "orphan-page": FindingSpec(
        "error",
        "非 index / log 页未被 wiki/index.md 引用",
        "`llmw wiki write index add` 补条目；或按归档流程从 index 移除",
    ),
    "raw-modified": FindingSpec(
        "error",
        "git 仓内 raw/ 的 tracked 文件有未提交改动（raw/ 是不可变真相源）",
        "问用户：还原改动，或确认后提交",
    ),
    "source-in-discussions": FindingSpec(
        "error",
        "source 页的 sources 指向 raw/discussions/（provenance 后门）",
        "走草稿消化路径：消化式或转正式 `mv` 后再 ingest",
    ),
    "sources-absolute-path": FindingSpec(
        "error",
        "source 页 sources 元素是绝对路径（Unix / Windows 盘符 / UNC）——破坏跨机器可移植性",
        "改为 wiki 根相对 raw/ 路径",
    ),
    "sources-external-anchor-missing": FindingSpec(
        "error",
        "sources 以 raw/external/ 起始但缺 anchor entry",
        "`llmw wiki external add` 注册该外部仓",
    ),
    "sources-external-symlink-missing": FindingSpec(
        "error",
        "sources 引用的 raw/external/<name> 对应的 symlink 不存在",
        "`llmw wiki external rebuild` 重建",
    ),
    "sources-malformed": FindingSpec(
        "error",
        "sources 的 raw/external/ 路径格式非法（段数 < 3，形如 raw/external/<name>/...）",
        "改为 `raw/external/<name>/<path>` 形式（接入走 `llmw wiki external add`）",
    ),
    "sources-missing": FindingSpec(
        "error",
        "sources 元素指向的路径不可访问 / 不存在（external 场景为跟随 symlink 后不可访问）",
        "修正路径或补齐文件；外部仓先 `llmw wiki external rebuild`",
    ),
    "sources-out-of-root": FindingSpec(
        "error",
        "sources 路径解析后不在 wiki 根下（路径穿越）",
        "改为 wiki 根相对路径",
    ),
    # --- warn：可疑 / 漂移，建议修 ---
    "contested-page": FindingSpec(
        "warn",
        "页面标记 `contested: true`（存在未解决矛盾）",
        "裁定矛盾后移除标记；矛盾仍在则保持",
    ),
    "contradiction-asymmetric": FindingSpec(
        "warn",
        "`contradictions` 引用 A→B 但 B 未反向标注 A（字段要求双向标注）",
        "在 B 页补反向 `contradictions` 标注",
    ),
    "contradiction-target-missing": FindingSpec(
        "warn",
        "`contradictions` 指向的页面不存在",
        "修正路径或补页",
    ),
    "duplicate-title": FindingSpec(
        "warn",
        "同一 `title` 出现在多个 wiki 页",
        "评估合并候选；确需并存则改标题区分",
    ),
    "external-anchor-orphan": FindingSpec(
        "warn",
        "raw/external/ 下有 symlink 但 anchor 无对应 entry（必填关联）",
        "`llmw wiki external add` 注册，或移除该 symlink",
    ),
    "external-target-drift": FindingSpec(
        "warn",
        "symlink 实际解析路径与 anchor target 不一致",
        "`llmw wiki external rebuild` 以 anchor 为准重建 symlink",
    ),
    "filename-not-kebab": FindingSpec(
        "warn",
        "文件名非 kebab-case（小写 + `-`）",
        "改名并更新全部引用",
    ),
    "frontmatter-no-blank-line": FindingSpec(
        "warn",
        "frontmatter 闭合 `---` 与正文之间缺空行（已偏离金标准，页面仍可渲染）",
        "在闭合 `---` 后补空行",
    ),
    "index-review-badge-drift": FindingSpec(
        "warn",
        "index.md 条目的 ✓/✗ 标识与被链页 frontmatter 的 reviewed 状态不一致",
        "`llmw wiki write index add` 重挂条目刷新标识",
    ),
    "invalid-reviewed-value": FindingSpec(
        "warn",
        '`reviewed` 取值非严格 `true`（如 `"true"` / `yes` / `1` / `false`）',
        "改为 `true` 或整体省略",
    ),
    "log-format": FindingSpec(
        "warn",
        'log.md 行不符格式约定（破坏 `grep "^## \\[" log.md` 可用性；canonical 见 fixture 头部）',
        "正路 `llmw wiki write log` 重写；带外手改则修正该行",
    ),
    "log-truncation-recommended": FindingSpec(
        "warn",
        "log.md 条目数超过滚动窗口上限（完整历史靠 git）",
        "`llmw wiki write log` 写入时自动截断；或手删最旧保最近 N 条",
    ),
    "memory-index-dangling": FindingSpec(
        "warn",
        "MEMORY.md 索引指向的 `<slug>.md` 不存在（短条目 `- 一句话事实` 无链接、不算）",
        "删除该索引行，或补齐条目文件",
    ),
    "oversized-page": FindingSpec(
        "warn",
        "内容页正文非空行数超过阈值（阈值随 finding 文本输出；MEMORY 无上限）",
        "拆成子主题页 + cross-link",
    ),
    "related-broken-link": FindingSpec(
        "warn",
        "frontmatter `related` / `compared` 元素按内容根 wiki/ 相对解析后文件不存在",
        "修正路径（如 `concepts/X.md`）或补页",
    ),
    "reviewed-at-missing": FindingSpec(
        "warn",
        "`reviewed: true` 但缺 `reviewed_at`",
        "补 `reviewed_at`（正路 `llmw wiki write touch`）",
    ),
    "reviewed-at-orphan": FindingSpec(
        "warn",
        "存在 `reviewed_at` 但缺 `reviewed: true`",
        "补 `reviewed: true` 或删 `reviewed_at`",
    ),
    "reviewed-stale": FindingSpec(
        "warn",
        "`reviewed: true` 但 `updated` 晚于 `reviewed_at`（LLM 修改后漏清戳）",
        "重新审核并 `llmw wiki write touch`；或不审则删两字段回未审核态",
    ),
    "stale-summary": FindingSpec(
        "warn",
        "source 页 `updated` 距今天数超过阈值（阈值随 finding 文本输出）",
        "复查上游源文件是否有更新，必要时重摄取",
    ),
    "wiki-format-version-ahead": FindingSpec(
        "warn",
        "wiki 的 Wiki Format 版本领先当前 CLI / skill 支持版本",
        "更新 CLI / skill 安装以对齐",
    ),
    "wiki-format-version-stale": FindingSpec(
        "warn",
        "wiki 的 Wiki Format 版本落后当前 CLI / skill 支持版本",
        "跑 `llmw wiki lint --check-version --apply` 取 upgrade plan，按 upgrade 流程升级",
    ),
    "wiki-format-version-unparsed": FindingSpec(
        "warn",
        "AGENTS.md 末尾「当前配置」表的 `Wiki Format 版本` 行无法解析",
        "跑 `llmw wiki lint --check-version` 诊断，或按模板形态修表格行",
    ),
    # --- info：提示 / 审计循环，不强制 ---
    "memory-not-indexed": FindingSpec(
        "info",
        "MEMORY/*.md（非 MEMORY.md）未在 MEMORY.md 索引段列出——下次会话加载后不可见",
        "`llmw wiki write memory add` 原子追加索引行（格式 canonical 见 fixture 头部）",
    ),
    "pending-review": FindingSpec(
        "info",
        "非 log/index 页未含 `reviewed: true`（新常态，仅提示）",
        "人工审核后 `llmw wiki write touch` 落戳；不审则忽略",
    ),
    "tag-not-in-taxonomy": FindingSpec(
        "info",
        "页面 tag 不在 wiki/tags.md 白名单（审计循环：用户删 bullet 后残留引用页显形）",
        "用户裁定：加回 tags.md，或从页面删该 tag",
    ),
}  # type: Dict[str, FindingSpec]

# 跳过提示（注记，非 finding）：经 [NOTES] 输出、不参与 severity 过滤。
# 注册表穷举测试据此豁免该前缀。
NOTE_PREFIXES = ("raw-immutable-skipped",)


def severity_of(finding: str) -> str:
    """从 finding 文本（``<name>: <message>``）取严重性；未注册名兜底 info。"""
    name = finding.split(":", 1)[0].strip()
    spec = FINDINGS.get(name)
    return spec.severity if spec is not None else "info"


def _grouped() -> Tuple[Tuple[str, ...], ...]:
    order = ("error", "warn", "info")
    return tuple(tuple(sorted(n for n, s in FINDINGS.items() if s.severity == sev)) for sev in order)


def explain(name: Optional[str] = None, as_json: bool = False) -> int:
    """`lint --explain` 业务入口（自包含，无需 wiki_root）；name=None/"all" 列全部。"""
    import json
    import sys

    if name == "all":
        name = None
    if name is not None and name not in FINDINGS:
        print(f"ERROR: 未知 finding `{name}`", file=sys.stderr)
        print(f"hint: 用 `llmw wiki lint --explain` 查看全部 {len(FINDINGS)} 条", file=sys.stderr)
        return 1

    if as_json:
        names = [name] if name else sorted(FINDINGS)
        payload = [
            {
                "name": n,
                "severity": FINDINGS[n].severity,
                "summary": FINDINGS[n].summary,
                "fix": FINDINGS[n].fix,
            }
            for n in names
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if name:
        s = FINDINGS[name]
        print(f"{name}  [{s.severity.upper()}]")
        print(f"  {s.summary}")
        print(f"  fix: {s.fix}")
        return 0

    print(f"lint finding 清单（{len(FINDINGS)} 条；severity: error / warn / info）")
    for sev, names in zip(("error", "warn", "info"), _grouped()):
        if not names:
            continue
        print(f"\n[{sev.upper()}] ({len(names)})")
        for n in names:
            s = FINDINGS[n]
            print(f"  {n}")
            print(f"      {s.summary}")
            print(f"      fix: {s.fix}")
    return 0
