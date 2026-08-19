"""llmw.content — wiki/workspace 内容层的确定性执行（只读探测 + 机械写）

本子包收纳原 skill scripts/ 的全部确定性代码（lint / fixtures 检查 / ingest 探测 /
机械字节写）。skill 目录零代码；本包只读 skill 侧的模板 / fixtures / SKILL.md 元数据。

写权限边界（「代码永不创作内容语义」）：
- 骨架文件写（init / upgrade 重渲染）不在本包——在 llmw/wiki/init_wiki 与后续 resync 引擎；
- wiki_write.py 是唯一机械写（纯函数 scribe，字节来自 agent 输入）；
- 本包不含任何内容散文资产（内容字节永远来自 skill 模板 / agent / 用户输入）。
"""
