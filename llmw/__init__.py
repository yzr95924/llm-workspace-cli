"""llmw — wiki workspace CLI"""

from llmw.config import skill_spec_version

__version__ = "0.1.0"
WORKSPACE_SPEC_VERSION = skill_spec_version(
    "yzr-llm-workspace-management", "workspace_spec_version"
)
WIKI_SPEC_VERSION = skill_spec_version("yzr-llm-wiki-management", "wiki_spec_version")
