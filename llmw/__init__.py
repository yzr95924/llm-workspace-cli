"""llmw — wiki workspace CLI

包内常量 SSOT: format 版本号硬编码于此；SKILL.md frontmatter 的 *_format_version
由 CI gate（scripts/test/smoke_fixtures.py 的 _check_format_version_alignment）比对，
与常量不一致即挂 fixtures-smoke job。bump 流程见 MEMORY/format-version-bump-single-repo.md。
"""

__version__ = "0.1.0"
WORKSPACE_FORMAT_VERSION = "0.10.0"
WIKI_FORMAT_VERSION = "0.41.0"
