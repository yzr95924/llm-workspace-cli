# Scripts

> 本目录存放本 wiki 自维护的脚本（项目级 ingest 扩展 / 外部 CLI 胶水 / 自动化 hook）。
>
> **加载机制**：`<wiki-root>/AGENTS.md` 顶部单行 `@scripts/SCRIPTS.md` 自动加载本文件全文；
> 不展开 `@import` 的 agent 由 AGENTS.md 顶部 Read 指令兜底（直接 Read 本文件）。
>
> 形态（单段）：每脚本一段 `### <name> — <label>` 子节（首行起头
> `` - `<name>` — <一句话用途> `` one-liner，后接 4 要素契约）。
>
> 脚本增删时**只改本文件**——`@import` 引用自动同步指向全文，AGENTS.md 不持有副本，无漂移。
>
> 何时写 / 编排纪律见 `yzr-llm-wiki-management/SKILL.md` §核心原则 §12（本文件不重复，
> 避免口径分裂）；路径与契约详细定义见 `yzr-llm-wiki-management/references/wiki-spec.md` §14。

## 索引

<!-- 每脚本一段：### <name> — <label>，首行起头 `- \`<name>\` — <一句话用途>` one-liner，
     后接 4 要素（使用场景 / 调用约定 / 作用 / 可选前置依赖） -->
（暂无脚本 —— 在此追加一段：`### <name> — <label>` + 完整 4 要素）