"""llmw 自定义异常 + 错误格式化"""

from typing import Optional


class LlmwError(Exception):
    """所有 CLI 异常的基类"""

    exit_code: int = 1
    user_message: str = ""

    def __init__(self, message: Optional[str] = None, hint: Optional[str] = None):
        self.message = message or self.user_message
        self.hint = hint
        super().__init__(self.message)


# ===== 用户错误 (exit_code = 1) =====


class WorkspaceNotFound(LlmwError):
    exit_code = 1
    user_message = "未找到 workspace 根"


class WorkspaceExists(LlmwError):
    exit_code = 1
    user_message = "目标路径已存在且非空"


class WikiNotFound(LlmwError):
    exit_code = 1
    user_message = "wiki 不在当前 workspace 中"


class WikiExists(LlmwError):
    exit_code = 1
    user_message = "wiki 名重复"


class WikiAlreadyInitialized(LlmwError):
    """spec §8: 目标目录已含 CLAUDE.md 或 wiki/index.md,拒绝覆盖"""

    exit_code = 1
    user_message = "wiki 目录已初始化"


class WikiDirMissing(LlmwError):
    exit_code = 1
    user_message = "wiki 子目录缺失"


class PurgeRequiresConfirmation(LlmwError):
    exit_code = 1
    user_message = "非 TTY 下 --purge 需要 --yes 确认"


class InvalidConfigKey(LlmwError):
    exit_code = 1
    user_message = "config KEY 不在白名单"


class KeyNotUnsettable(LlmwError):
    exit_code = 1
    user_message = "KEY 不可 unset"


class MissingRequiredFlag(LlmwError):
    exit_code = 1
    user_message = "非 TTY 下 metadata 字段缺 flag"


class SpaceFormNotAllowed(LlmwError):
    """CLI 参数风格约定: 带值 flag 必须 --flag=value, 不接受空格分隔的 --flag value"""

    exit_code = 1
    user_message = "参数风格不支持空格分隔"

    def __init__(self, token: str):
        super().__init__(
            message=f"参数风格不支持空格分隔: {token} <VALUE>",
            hint=f"请改用 = 连接: {token}=<VALUE>",
        )


class SchemaVersionUnsupported(LlmwError):
    exit_code = 1
    user_message = "schema_version 不被当前 CLI 支持"


class WikiMetadataCorrupt(LlmwError):
    """wiki_metadata.toml 结构不符 schema（必填字段缺失等）——exit 1 用户可修，不归内部错误。"""

    exit_code = 1
    user_message = "wiki_metadata.toml 损坏或不完整"


class InvalidWikiName(LlmwError):
    exit_code = 1
    user_message = "wiki 名格式非法"


class InvalidWindowSuffix(LlmwError):
    """R1: enter --window-suffix / stop --window-suffix 非法（窗口名拼接失败）"""

    exit_code = 1
    user_message = "window suffix 非法"


class WindowBackendMismatch(LlmwError):
    """R2: enter 复用判定命中带标活窗但 @llmw_backend 与当前 backend 不符。

    复用它会吞掉用户"切换 agent"的意图——拒绝并提示先 stop 或 --window-suffix。
    """

    exit_code = 1
    user_message = "窗口正在运行不同的 agent backend"


class NoRunningSession(LlmwError):
    """R6: wiki stop 无候选窗口"""

    exit_code = 1
    user_message = "没有运行中的 session"


class MultipleRunningSessions(LlmwError):
    """R6: wiki stop 候选 >1 且未给 --window-suffix 消歧"""

    exit_code = 1
    user_message = "存在多个运行中的 session，需要 --window-suffix 消歧"


class StopRequiresConfirmation(LlmwError):
    """R6: 非 TTY 下 wiki stop 需要 --yes 确认"""

    exit_code = 1
    user_message = "非 TTY 下 stop 需要 --yes 确认"


class InvalidTagValue(LlmwError):
    exit_code = 1
    user_message = "tag 值非法"


# ===== 环境错误 (exit_code = 2) =====


class SkillMissing(LlmwError):
    exit_code = 2
    user_message = "SKILL 目录缺失（skill 随 CLI 同仓，仓库完整克隆即含）"


class SetupFailed(LlmwError):
    """wiki 初始化失败:模板缺失、渲染异常、atomic_write 失败等"""

    exit_code = 2
    user_message = "wiki 初始化失败"


class BackupFailed(LlmwError):
    """wiki remove --purge 前的备份步骤失败(mv / mkdir 任一失败)

    备份失败时不动 wiki;用户可加 --no-backup 跳过备份直接删。
    """

    exit_code = 2
    user_message = "wiki 备份失败"


class ClaudeNotFound(LlmwError):
    exit_code = 2
    user_message = "agent CLI 不在 PATH"


class ByobuNotFound(LlmwError):
    exit_code = 2
    user_message = "byobu-tmux 不在 PATH"


class ByobuCommandFailed(LlmwError):
    exit_code = 2
    user_message = "byobu/tmux 命令执行失败"


class PythonUnavailable(LlmwError):
    exit_code = 2
    user_message = "sys.executable 不可执行"


# ===== model registry 错误 (exit_code = 1) =====


class ModelNotInRegistry(LlmwError):
    exit_code = 1
    user_message = "wiki 引用了不存在的 model_id"


class ModelDefaultNotSet(LlmwError):
    exit_code = 1
    user_message = "workspace 没有默认 model"


class ModelDefaultAmbiguous(LlmwError):
    exit_code = 1
    user_message = "registry 存在多条 is_default=true, 数据损坏"


class ModelIdConflict(LlmwError):
    exit_code = 1
    user_message = "model_id 已存在"


class ModelIsDefault(LlmwError):
    exit_code = 1
    user_message = "目标 model 是默认, 不能直接 remove"


class InvalidModelField(LlmwError):
    exit_code = 1
    user_message = "model 字段值非法"


class RegistryMissing(LlmwError):
    exit_code = 1
    user_message = "workspace_models.toml 不存在"


class OverlayFileUnparseable(LlmwError):
    exit_code = 1
    user_message = "overlay 文件不是合法 JSON"


# ===== 内部错误 (exit_code = 3) =====


class InternalError(LlmwError):
    exit_code = 3
    user_message = "未预期的内部错误"


def format_error(err: LlmwError, debug: bool = False) -> str:
    """渲染为 [llmw] error: ... / [llmw] hint: ... 格式"""
    lines = [f"[llmw] error: {err.message}"]
    if err.hint:
        lines.append(f"[llmw] hint: {err.hint}")
    if debug:
        import traceback

        lines.append("[llmw] traceback:")
        lines.append(traceback.format_exc())
    return "\n".join(lines)
