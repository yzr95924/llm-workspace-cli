# fish completion for llmw
# Install: 由 scripts/install.sh 自动 cp 到
#   ~/.config/fish/completions/llmw.fish
# fish 自动加载，无需 source。

# 参数风格：带值 flag 一律 `--flag=<value>`（= 连接；CLI 拒绝空格分隔的 --flag value）。
# 带值 flag 补全分两类（核心：fish 对带值 long option 生成 `--flag=` 候选的条件是「有 -a 值候选
# 且无 -r」——-r 会让 fish 走空格分隔语义，既不给 = 形式、又与 CLI 的 = 要求冲突）：
#   A 类（有动态值，如 --name/--model-id/--model）：`-l flag -a "(vals)"`（无 -r），
#       fish 原生同时给 --flag 与 --flag=；= 后 <Tab> 补动态值。
#   B 类（free-form 无动态值，如 --topic/--base-url）：`-a "--flag="`（直接给 = 候选），值手敲。

# 通用: workspace 路径（--workspace= 值 或 $LLMW_WORKSPACE 或默认）
function __llmw_workspace
    set -l ws ""
    for w in (commandline -opc)
        switch "$w"
            case '--workspace=*'
                set ws (string replace -- '--workspace=' '' -- "$w")
        end
    end
    if test -z "$ws"
        if set -q LLMW_WORKSPACE
            set ws "$LLMW_WORKSPACE"
        else
            set ws "$HOME/yzr-llm-wiki-workspace"
        end
    end
    echo "$ws"
end

# 动态: 当前 workspace 的 wiki 名（直读 workspace.toml，不依赖 llmw 可执行文件；未初始化返回空）
function __llmw_wikis
    set -l ws (__llmw_workspace)
    [ -f "$ws/workspace.toml" ]; or return 0
    grep -oE '^\[wikis\.[a-z0-9_-]+\]' "$ws/workspace.toml" 2>/dev/null \
        | sed 's/^\[wikis\.//; s/\]$//'
end

# 动态: 当前 workspace 的 model_id（直读 workspace_models.toml，不依赖 llmw 可执行文件；未初始化返回空）
function __llmw_model_ids
    set -l ws (__llmw_workspace)
    [ -f "$ws/workspace_models.toml" ]; or return 0
    grep -oE '^model_id[[:space:]]*=[[:space:]]*"[^"]+"' "$ws/workspace_models.toml" 2>/dev/null \
        | sed -E 's/.*"([^"]+)".*/\1/'
end

# 精确：commandline 含 $argv[1]（sub）且含 $argv[2..]（action 任一）
# 避免 __fish_seen_subcommand_from SUB ACT 的 OR 语义泄露（wiki add 与 model add 都含 "add"）
function __llmw_subact
    __fish_seen_subcommand_from $argv[1]; and __fish_seen_subcommand_from $argv[2..-1]
end

# 通用 / 顶级
set -l COMMON -l workspace -l json -l debug -l quiet -s q
set -l TOP_CMDS init config list status check-fixtures upgrade model wiki -l help -l version

# ===== 顶层 =====
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "init"            -d '初始化 workspace'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "config"          -d 'workspace.toml 读写'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "list"            -d '列出 wiki'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "status"          -d '查看运行中的 wiki agent session'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "check-fixtures"  -d '骨架探测器（检查 AGENTS.md / fixtures / legacy 一致性）'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "upgrade"         -d 'workspace 升级引擎'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "model"           -d 'workspace model registry'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -f -a "wiki"            -d 'wiki 子命令'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -l help         -d '显示帮助'
complete -c llmw -n "not __fish_seen_subcommand_from $TOP_CMDS" -l version      -d '显示版本'

# 全局 flag（任何位置）
# --workspace 用 A 类（-l workspace + 动态 -a）+ __fish_complete_directories：
#   fish 自动生成 --workspace= 候选 + Tab 触发目录补全，与 bash compgen -d / zsh _directories 对齐
complete -c llmw -l workspace -f -a "(__fish_complete_directories)" -d 'workspace 根路径'
complete -c llmw -l json      -d '输出 JSON 格式'
complete -c llmw -l debug     -d '打印 traceback'
complete -c llmw -l quiet -s q -d '抑制 INFO'

# init 子命令 flag（path / display-name，均 free-form → B 类）
complete -c llmw -n "__fish_seen_subcommand_from init" -a "--path="         -f -d 'workspace 路径'
complete -c llmw -n "__fish_seen_subcommand_from init" -a "--display-name=" -f -d 'workspace 显示名'

# list 子命令 flag（--tag free-form → B 类；wiki external list 也含 "list",用 not seen wiki 防止漏出）
complete -c llmw -n "__fish_seen_subcommand_from list; and not __fish_seen_subcommand_from wiki" -a "--tag=" -f -d '仅列出含此 tag (可重复, AND 关系)'

# status 子命令 flag（--tmux 是 bool）
complete -c llmw -n "__fish_seen_subcommand_from status" -l tmux -d '输出单行 ●N [✗M]（供状态条集成）'

# check-fixtures 子命令（--target-format free-form → B 类；--list-rules bool）
complete -c llmw -n "__fish_seen_subcommand_from check-fixtures; and not __fish_seen_subcommand_from wiki" -a "--target-format=" -f -d '目标 format 版本（缺省读 llmw.WORKSPACE_FORMAT_VERSION）'
complete -c llmw -n "__fish_seen_subcommand_from check-fixtures; and not __fish_seen_subcommand_from wiki" -l list-rules         -d '列出所有 detector 规则（不跑检查）'

# upgrade 子命令（--apply / --yes bool）
complete -c llmw -n "__fish_seen_subcommand_from upgrade; and not __fish_seen_subcommand_from wiki" -l apply -d 'dry-run 模式变 apply 模式（写文件；TTY 默认 dry-run）'
complete -c llmw -n "__fish_seen_subcommand_from upgrade; and not __fish_seen_subcommand_from wiki" -l yes -s y -d '跳过 TTY 二次确认'

# ===== config 子命令（顶层 config: not seen wiki 防止漏入 wiki config 上下文）=====
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from get set unset" -f -a "get"    -d '取值'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from get set unset" -f -a "set"    -d '设值'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from get set unset" -f -a "unset"  -d '清值'

complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from get unset" -f -a "enter_cli"        -d 'agent CLI (claude|qodercli|opencode)'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from get unset" -f -a "templates_version" -d 'templates 版本(只读)'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from get unset" -f -a "created_at"        -d '创建时间(只读)'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from get unset" -f -a "schema_version"    -d 'schema 版本(只读)'
complete -c llmw -n "__fish_seen_subcommand_from config; and not __fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from set"       -f -a "enter_cli"        -d 'agent CLI (claude|qodercli|opencode)'

# ===== model 子命令 =====
set -l MODEL_ACTS add list show set-default unset-default remove
# ===== model 子命令（顶层 model: not seen wiki 防止漏入 wiki 上下文,
# 尤其是 `wiki config set model` 中 "model" 作为 key 的 word）=====
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "add"             -d '新增 model 条目'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "list"            -d '列出所有 model 条目'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "show"            -d '查看单条 model'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "set-default"     -d '标记默认 model'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "unset-default"   -d '清空默认标记'
complete -c llmw -n "__fish_seen_subcommand_from model; and not __fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $MODEL_ACTS" -f -a "remove"          -d '删除 model 条目'

# model list / unset-default（无专属 flag；显式 scope 声明，与 bash / zsh 对应分支对齐；
# 全局 --workspace=/--json/--debug/--quiet/-q 由文件顶部 COMMON 段兜底）
complete -c llmw -n "__llmw_subact model list"            -f -d '列出所有 model 条目'
complete -c llmw -n "__llmw_subact model unset-default"   -f -d '清空默认标记'

# model add（全 free-form → B 类；--default 是 bool flag）
complete -c llmw -n "__llmw_subact model add" -a "--model-id=" -f -d 'registry slug'
complete -c llmw -n "__llmw_subact model add" -a "--name="     -f -d '网关模型名'
complete -c llmw -n "__llmw_subact model add" -a "--base-url=" -f -d 'API base URL'
complete -c llmw -n "__llmw_subact model add" -a "--api-key="  -f -d 'API key'
complete -c llmw -n "__llmw_subact model add" -l default  -d '标记为默认'

# model show / set-default / remove（--model-id 有动态值 → A 类，无 -r）
complete -c llmw -n "__llmw_subact model show set-default remove" -l model-id -f -a "(__llmw_model_ids)" -d 'model_id'
complete -c llmw -n "__llmw_subact model remove" -l yes -s y -d '跳过确认'

# ===== wiki 子命令 =====
set -l WIKI_ACTS add remove rename show config enter stop lint check-fixtures upgrade ingest-diff write external
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "add"             -d '新建 wiki'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "remove"          -d '移除 wiki'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "rename"          -d '重命名 wiki (目录 + 索引 + metadata)'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "show"            -d '查看 wiki 详情'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "config"          -d '读写 wiki_metadata.toml'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "enter"           -d '启动 AI agent session'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "stop"            -d '终止 wiki 的 agent 窗口'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "lint"            -d 'wiki lint 检查'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "check-fixtures"  -d 'wiki 骨架探测器'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "upgrade"         -d 'wiki 升级引擎'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "ingest-diff"     -d '列出未摄取 raw 文件'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "write"           -d 'wiki 内容写入编排'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -f -a "external"        -d 'raw/external 接入 / 重建编排'

# wiki --name / --path（wiki 但未选 action 时；--name 有动态值 → A 类，无 -r；--path 目录补全）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -l name -f -a "(__llmw_wikis)" -d '目标 wiki 名'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and not __fish_seen_subcommand_from $WIKI_ACTS" -l path -f -a "(__fish_complete_directories)" -d '目标 wiki 根目录'

# wiki add（topic/display-name/description/tag free-form → B 类；--model 有动态值 → A 类；--git 是 bool）
complete -c llmw -n "__llmw_subact wiki add" -a "--topic="        -f -d 'wiki 主题'
complete -c llmw -n "__llmw_subact wiki add" -a "--display-name=" -f -d '显示名'
complete -c llmw -n "__llmw_subact wiki add" -a "--description="  -f -d '描述'
complete -c llmw -n "__llmw_subact wiki add" -a "--tag="          -f -d 'tag (可重复)'
complete -c llmw -n "__llmw_subact wiki add" -l model -f -a "(__llmw_model_ids)" -d '绑定的 model_id'
complete -c llmw -n "__llmw_subact wiki add" -l git -d 'opt-in: 初始化 git 仓'

# wiki remove
complete -c llmw -n "__llmw_subact wiki remove" -l purge       -d '同时删除 wiki 子目录'
complete -c llmw -n "__llmw_subact wiki remove" -l no-backup   -d '跳过 --purge 的备份步骤'
complete -c llmw -n "__llmw_subact wiki remove" -l yes -s y    -d '跳过确认'

# wiki rename（--old 有动态值 → A 类，无 -r；--new free-form → B 类，无 -r）
complete -c llmw -n "__llmw_subact wiki rename" -l old -f -a "(__llmw_wikis)" -d '当前 wiki 名'
complete -c llmw -n "__llmw_subact wiki rename" -a "--new=" -f -d '新 wiki 名 (须符合 NAME_RE)'

# wiki show（无专属 flag；COMMON 兜底）

# wiki config（cfg_action / cfg_key 子层补全；无 --name 后置 offer）

# wiki config cfg_action（get/set/unset 三选一）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "get"   -d '取值'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "set"   -d '设值'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and not __fish_seen_subcommand_from get set unset" -f -a "unset" -d '清值'

# wiki config cfg_key（display_name / description / tags / model；cfg_action 之后）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "display_name" -d '显示名'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "description"  -d '描述'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "tags"         -d 'tags (可重复)'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from config; and __fish_seen_subcommand_from get set unset" -f -a "model"        -d '绑定的 model_id'

# wiki enter（--dry-run bool / --window-suffix free-form → B 类；无 --name 后置 offer）
complete -c llmw -n "__llmw_subact wiki enter" -l dry-run -d '仅打印 overlay 不启动 claude'
complete -c llmw -n "__llmw_subact wiki enter" -a "--window-suffix=" -f -d '并行窗口后缀（拼接为 <wiki>-<suffix>）'

# wiki stop（--window-suffix free-form → B 类；--yes bool；无 --name 后置 offer）
complete -c llmw -n "__llmw_subact wiki stop" -a "--window-suffix=" -f -d '只匹配 <wiki>-<suffix> 窗口'
complete -c llmw -n "__llmw_subact wiki stop" -l yes -s y -d '跳过确认'

# wiki lint（--severity 有离散值 → A 类候选；其余 bool）
complete -c llmw -n "__llmw_subact wiki lint" -a "--severity=error" -f -d '仅 error'
complete -c llmw -n "__llmw_subact wiki lint" -a "--severity=warn"  -f -d '仅 warn'
complete -c llmw -n "__llmw_subact wiki lint" -a "--severity=info"  -f -d '仅 info'
complete -c llmw -n "__llmw_subact wiki lint" -a "--severity=all"   -f -d '全部（默认）'
complete -c llmw -n "__llmw_subact wiki lint" -l no-git              -d '跳过 raw/ 的 git status 检查'
complete -c llmw -n "__llmw_subact wiki lint" -l check-version       -d '扫 format 版本 + legacy 现场（互斥模式）'
complete -c llmw -n "__llmw_subact wiki lint" -l apply               -d '与 --check-version 联用：stdout JSON 输出 upgrade plan'

# wiki check-fixtures（同顶层版本；free-form target-format + list-rules bool）
complete -c llmw -n "__llmw_subact wiki check-fixtures" -a "--target-format=" -f -d '目标 format 版本'
complete -c llmw -n "__llmw_subact wiki check-fixtures" -l list-rules         -d '列出 detector 规则（不跑检查）'

# wiki upgrade（--apply / --yes bool；原 --dry-run flag 已删：默认就是 dry-run，加 --apply 显式写入）
complete -c llmw -n "__llmw_subact wiki upgrade" -l apply   -d '落地（重渲染 byte-owned / 块替换 block-owned / 嫁接 header-owned）'
complete -c llmw -n "__llmw_subact wiki upgrade" -l yes -s y -d '跳过 TTY 二次确认'

# wiki ingest-diff（--relative / --check-stale bool）
complete -c llmw -n "__llmw_subact wiki ingest-diff" -l relative     -d '输出相对 wiki 根而非 raw/'
complete -c llmw -n "__llmw_subact wiki ingest-diff" -l check-stale  -d '额外检查 source 页 updated 早于 raw mtime'

# ===== wiki write 子命令 =====
set -l WIKI_WRITE_ACTS log index touch new memory
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and not __fish_seen_subcommand_from $WIKI_WRITE_ACTS" -f -a "log"    -d '追加 log 条目'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and not __fish_seen_subcommand_from $WIKI_WRITE_ACTS" -f -a "index"  -d '操作 index 条目'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and not __fish_seen_subcommand_from $WIKI_WRITE_ACTS" -f -a "touch"  -d '刷新 wiki 页面的 updated 字段'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and not __fish_seen_subcommand_from $WIKI_WRITE_ACTS" -f -a "new"    -d '创建新 wiki 内容页'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and not __fish_seen_subcommand_from $WIKI_WRITE_ACTS" -f -a "memory" -d '创建/索引 MEMORY 条目'

# wiki write log: --op 有离散值 → A 类；其余 free-form（B 类）/ bool
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--op=ingest" -f -d 'op=ingest'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--op=query"  -f -d 'op=query'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--op=lint"   -f -d 'op=lint'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--op=setup"  -f -d 'op=setup'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--title="      -f -d '标题'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -l bulk           -d '批量模式'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--topic="     -f -d '主题'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from log" -a "--count="     -f -d '计数'

# wiki write index: add | remove（positional）+ posarg 自由文本路径（不补）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from index; and not __fish_seen_subcommand_from add remove" -f -a "add"    -d '添加条目'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from index; and not __fish_seen_subcommand_from add remove" -f -a "remove" -d '删除条目'

# wiki write new（type/title/slug/tags/sources free-form → B 类；--description B 类）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from new" -a "--type="        -f -d 'type (source / comparison / synthesis / concept / entity)'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from new" -a "--slug="        -f -d '页面 slug'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from new" -a "--title="       -f -d '标题'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from new" -a "--description="  -f -d '描述'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from new" -a "--tags="         -f -d 'tags 逗号分隔'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from new" -a "--sources="      -f -d 'sources (raw 路径，逗号分隔)'

# wiki write memory（slug/title free-form → B 类；--index-line free-form）
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from memory" -a "--slug="        -f -d 'MEMORY 条目 slug'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from memory" -a "--title="       -f -d '短名（≤30 字）'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from write; and __fish_seen_subcommand_from memory" -a "--index-line="  -f -d '索引行'

# ===== wiki external 子命令 =====
set -l WIKI_EXTERNAL_ACTS add remove list rebuild
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from external; and not __fish_seen_subcommand_from $WIKI_EXTERNAL_ACTS" -f -a "add"     -d '接入外部仓（命名协商 + 登记 + 建 symlink）'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from external; and not __fish_seen_subcommand_from $WIKI_EXTERNAL_ACTS" -f -a "remove"  -d '注销外部仓（删 entry + 删 symlink）'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from external; and not __fish_seen_subcommand_from $WIKI_EXTERNAL_ACTS" -f -a "list"    -d '列出所有 entry + 状态'
complete -c llmw -n "__fish_seen_subcommand_from wiki; and __fish_seen_subcommand_from external; and not __fish_seen_subcommand_from $WIKI_EXTERNAL_ACTS" -f -a "rebuild" -d '跨主机重建（新机器跑一次）'

# wiki external add（--name / --notes free-form → B 类）
complete -c llmw -n "__llmw_subact wiki external; and __fish_seen_subcommand_from add" -a "--name="  -f -d 'kebab-case symlink 名（与用户协商）'
complete -c llmw -n "__llmw_subact wiki external; and __fish_seen_subcommand_from add" -a "--notes=" -f -d '接入备注（agent scribe 进 anchor）'

# wiki external list（--json bool）
# （无专属 flag，留空 scope 声明——全局 --json 由文件顶部 COMMON 段兜底，避免重复定义）

# wiki external rebuild（--target NAME=PATH free-form → B 类；--yes bool）
complete -c llmw -n "__llmw_subact wiki external; and __fish_seen_subcommand_from rebuild" -a "--target=" -f -d '覆盖本地路径 NAME=PATH（可重复）'
complete -c llmw -n "__llmw_subact wiki external; and __fish_seen_subcommand_from rebuild" -l yes -s y -d '跳过 TTY 二次确认'
