"""llmw — wiki workspace CLI

包内常量 SSOT: spec 版本号硬编码于此；SKILL.md frontmatter 的 *_spec_version
由 CI gate（scripts/test/smoke_fixtures.py 的 _check_spec_version_alignment）比对，
与常量不一致即挂 fixtures-smoke job。bump 流程见 MEMORY/spec-version-bump-single-repo.md。
"""

__version__ = "0.1.0"
WORKSPACE_SPEC_VERSION = "0.8.0"
WIKI_SPEC_VERSION = "0.37.0"
