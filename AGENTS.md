# AGENTS.md

本仓两件套：`llmw/`（CLI，管理 workspace / wiki 元数据 + tmux 窗口编排）与
`yzr-llm-wiki-management/`（SKILL，纯 markdown，同仓分发）。CLI 只管元数据与 session
启动；wiki 内容的语义判断归 session 内的 skill / agent。命令面文档真源 = `README.md`
（受 CI gate 校验；本文件不在 gate 扫描域，勿把命令表复制进来）。

## 常用命令

```bash
python3 -m pytest -q                              # 全部测试；裸 `pytest` 在未 pip install -e . 时 import 不到 llmw
python3 -m pytest tests/test_wiki_rename.py -q    # 单文件；-k <关键词> 单测
ruff format --check . && ruff check .             # lint（CI 钉 ruff==0.15.20）
python3 -m llmw --help                            # 免安装直接跑 CLI
```

功能完整安装走 `./scripts/install.sh`（wrapper 内嵌仓库路径 + PYTHONPATH，不用 pip / venv）；`pip install -e .` 只服务开发 / CI。

## 改动后必跑的 gate（CI 同款，standalone 可直接跑）

| 改了什么 | 跑什么 |
| --- | --- |
| CLI 子命令 / flag / finding / reason 等枚举 / rule_ref / 语义断言豁免，或 SKILL 文本 | `python3 scripts/test/check_skill_cli_contract.py` |
| `llmw/content/templates/`（模板或 fixtures） | `python3 scripts/test/smoke_fixtures.py` |
| `scripts/install.sh` / `uninstall.sh` | `bash scripts/test/test_install_uninstall.sh`（临时 HOME 隔离） |
| `WIKI_FORMAT_VERSION`（`llmw/__init__.py`） | 必须与 SKILL.md frontmatter 同 commit（smoke_fixtures 比对） |

## 架构红线与 SSOT

- **代码不创作内容语义**：确定性操作（骨架渲染 / 注册表变换 / 机械 scribe）全部收口在
  `llmw/content/`；`raw/`、`wiki/` 下的语义写入归 skill 在 session 内执行。唯一例外：
  `raw/external/` 的 anchor + symlink（经 `llmw wiki external` 子命令）。
- **单向约束**：SKILL 文本不引 CLI 包内符号（`llmw.content.xxx` / `module.SYMBOL` 形态），对 CLI 的感知以接口契约为限——
  只引命令名 / finding 名 / 输出字段值（如 ingest-diff 的 reason）；gate 面 9 判红。
- 命令面 SSOT = `llmw.cli.build_parser()` 单一 argparse 树。**新增子命令须手动同步
  `completions/` 三件套**（bash / fish / zsh，`tests/test_completions_sync.py` 守护，
  历史漂移过数月）。
- 带值 flag 一律 `--flag=VALUE` 等号形式（CLI 全局拒绝空格分隔；文档中的示例同样要求）。
- 新增 agent backend 只改 `llmw/backends.py`（`KNOWN_BACKENDS` + `STATE_PATTERNS`）。
- finding 口径唯一入口 = `llmw wiki lint --explain`（注册表 `llmw/content/findings.py`）；skill prose 不得镜像 severity 清单。
- 元数据 toml 的 schema 校验全在 store 层（workspace / wiki / models 各自 store 的 validate）；manager 不重复校验。
- api_key 打印必过 `llmw/models/redact.py` 出口；model 配置不读环境变量（禁止 `os.environ.get("ANTHROPIC_*")` 类读取）。

## 架构边界与演进原则

三载体按传播成本分工（重 → 轻）；新规则 / 新功能放能承载它的最轻载体：

- `llmw/content/`：机械判定 + 行为常量 SSOT + 骨架字节所有权（发版全局生效）
- wiki 模板 + fixtures：常驻纪律内核 + 出生字节（改动 = format bump + 逐实例 upgrade）
- `yzr-llm-*/` skill：工作流 + 写页语义（改文档即生效，不碰实例字节）

演进判据：

1. 能机械判定的做成 lint / write，不写成文档规则
2. 强制值（改动影响代码行为）只存 CLI 常量；模板 / fixture 用 `{{占位符}}` 消费；skill 对值零感知——写路径走命令，
   带外手改读实例文件说明块；文档确需出现值（如 SKILL.md frontmatter 版本，属 CI 绊线）必须 gate 钉住，禁止手抄
3. 建议值（不影响代码行为）留在文档并标「建议」，不得事后升级为 lint 检查
4. write 子命令三居一才加：格式多字段 / 滚动窗口类不变量 / 高频
5. 仅模板 / fixture 字节变才 bump `WIKI_FORMAT_VERSION`
6. 无法机器校验的跨载体断言登记 gate 豁免清单，禁止沉默的未钉住

## 工具链硬约束

- **Python 3.7 兼容是硬约束**：CI 矩阵 py3.7 + py3.11（官方容器）+ 全子模块 import smoke。
  勿用 3.8+ 语法（walrus、import 期求值的 `dict[str, str]` 注解等）；pytest 钉 `<8`
  （pytest 8 要求 py≥3.8）。
- ruff 双配置并存是刻意的：根 = 默认规则（E4/E7/E9/F）+ target py37；
  `llmw/content/ruff.toml` 局部覆盖 = 120 行宽 + E/W/F/I/B/UP（约 6500 行既有代码，
  不 reflow）。`ruff format .` 会按文件就近选配置，别用手动根配置格式化 content 包。
- Markdown 行宽 ≤ 120（`.markdownlint.jsonc` MD013；表格 / 代码块豁免）。
- skill 目录（`yzr-llm-*/`）禁 `.py` 文件（CI find 判红）；确定性代码全归 `llmw/content/`。
- 编辑模板 / fixtures 前先读 `llmw/content/templates/wiki/fixtures/README.md` 的「规则分层」——每条纪律恰有一个 canonical 家，别处只写指针。

## 跨会话记忆（索引）

<!-- 下方 @引用若未被自动展开（看不到正文），用 Read 工具读取 -->
@MEMORY/MEMORY.md
