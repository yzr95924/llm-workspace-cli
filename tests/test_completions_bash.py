"""bash 补全行为测试。

用 bash 直接驱动 `_llmw` 函数（COMP_WORDS / COMP_CWORD 注入 + 读 COMPREPLY），
覆盖关键场景 + 断言"post-action 不再 offer --name"等负面行为。

只测 bash（CI python 容器必有 bash；fish/zsh 在 CI 上不可用）。
zsh/fish 的等价行为由 `test_completions_sync.py` 的"命令词缺失"检查 + 本地
`fish -n` / `zsh -n` 语法检查守护；语义级测试需交互，CI 不做。
"""

import os
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASH_COMP = os.path.join(REPO, "completions", "llmw.bash")

# 所有子命令（顶层 + wiki + model + write + external）用于 smoke 加载检查
TOP_CMDS = [
    "init",
    "config",
    "list",
    "status",
    "check-fixtures",
    "upgrade",
    "model",
    "wiki",
]
WIKI_ACTS = [
    "add",
    "remove",
    "rename",
    "show",
    "config",
    "enter",
    "stop",
    "lint",
    "check-fixtures",
    "upgrade",
    "ingest-diff",
    "write",
    "external",
]
WRITE_ACTS = ["log", "index", "touch", "new", "memory"]
EXTERNAL_ACTS = ["add", "remove", "list", "rebuild"]


def _bash_complete(comp_line):
    """跑 bash，source 补全文件，把 `comp_line`（可带尾空格模拟光标位置）拆成
    COMP_WORDS，设 COMP_CWORD，调 _llmw，返回 COMPREPLY 列表。

    约定："llmw wiki "（尾空格）表示光标在 wiki 后等着补下一个词；"llmw wiki"
    （无尾空格）表示光标还在 wiki 字符串内部（很少用，主要用于测 word-splitting）。
    """
    # 末尾空格 → words 末尾追加空串，模拟光标在下一个词位置
    words = comp_line.split(" ")
    if not words[-1]:
        words = words[:-1] + [""] if comp_line.endswith(" ") else words
    # 空串作为最后一个元素：保持；其余元素是真实单词
    cword = len(words) - 1
    bash_arr = "(" + " ".join(_bash_quote(w) for w in words) + ")"
    bash_script = (
        f'source "{BASH_COMP}"\n'
        f"COMP_WORDS={bash_arr}\n"
        f"COMP_CWORD={cword}\n"
        f"_llmw\n"
        f'printf "%s\\n" "${{COMPREPLY[@]}}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", bash_script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.fail(f"bash 执行失败:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return [line for line in result.stdout.splitlines() if line]


def _bash_quote(s):
    """单引号包裹字符串。空串 → ''（bash 保留空数组槽位）。"""
    if s == "":
        return "''"
    return "'" + s.replace("'", "'\\''") + "'"


@pytest.mark.skipif(not shutil.which("bash"), reason="bash 不可用")
class TestBashCompletionBehavior:
    def test_top_level_offers_all_commands(self):
        cands = _bash_complete("llmw ")
        for cmd in TOP_CMDS:
            assert cmd in cands, f"顶层缺命令: {cmd} (实际: {cands})"

    def test_wiki_pre_action_offers_all_acts_and_selectors(self):
        cands = _bash_complete("llmw wiki ")
        for act in WIKI_ACTS:
            assert act in cands, f"wiki 缺子命令: {act} (实际: {cands})"
        # pre-action 必须同时 offer --name= 与 --path=
        assert "--name=" in cands, "wiki pre-action 缺 --name="
        assert "--path=" in cands, "wiki pre-action 缺 --path="

    @pytest.mark.parametrize("act", ["show", "config", "enter", "stop"])
    def test_wiki_post_action_no_name_offer(self, act):
        """CLI 拒收 post-action --name（只挂在 p_wiki 上），补全不应 offer。"""
        cands = _bash_complete(f"llmw wiki {act} ")
        assert "--name=" not in cands, (
            f"wiki {act} post-action 不应该 offer --name= (实际: {cands})"
        )

    def test_wiki_write_offers_all_sub_actions(self):
        cands = _bash_complete("llmw wiki write ")
        for act in WRITE_ACTS:
            assert act in cands, f"wiki write 缺子动作: {act} (实际: {cands})"

    def test_wiki_external_offers_all_sub_actions(self):
        cands = _bash_complete("llmw wiki external ")
        for act in EXTERNAL_ACTS:
            assert act in cands, f"wiki external 缺子动作: {act} (实际: {cands})"

    def test_wiki_write_log_offers_op_choices(self):
        cands = _bash_complete("llmw wiki write log ")
        for op in ["--op=", "--title=", "--bulk"]:
            assert op in cands, f"wiki write log 缺 flag: {op} (实际: {cands})"

    def test_wiki_lint_offers_expected_flags(self):
        cands = _bash_complete("llmw wiki lint ")
        for fl in ["--severity=", "--no-git", "--check-version", "--apply"]:
            assert fl in cands, f"wiki lint 缺 flag: {fl} (实际: {cands})"

    def test_workspace_config_set_no_dead_default_model(self):
        """default_model 已从 CONFIG_KEYS 删除（resolve 只读 is_default），set 不应 offer。"""
        cands = _bash_complete("llmw config set ")
        assert "default_model" not in cands, (
            f"config set 不应 offer 已删除的 default_model (实际: {cands})"
        )
        # 但 enter_cli（唯一可 set key）应在
        assert "enter_cli" in cands

    def test_wiki_config_set_keys(self):
        """wiki config set 应 offer display_name / description / tags / model。"""
        cands = _bash_complete("llmw wiki config set ")
        for key in ["display_name", "description", "tags", "model"]:
            assert key in cands, f"wiki config set 缺 key: {key} (实际: {cands})"

    def test_workspace_config_set_with_leading_global_flag(self):
        """regression: 旧版 `COMP_CWORD -eq 3` 在全局 flag 前置时错位。

        `llmw --json config set <TAB>` 应该与 `llmw config set <TAB>` 语义一致，
        仍 offer enter_cli。
        """
        cands = _bash_complete("llmw --json config set ")
        assert "enter_cli" in cands, (
            f"全局 flag 前置时 config set 应仍 offer enter_cli (实际: {cands})"
        )

    def test_wiki_write_index_offers_add_remove(self):
        """wiki write index 应 offer add/remove 子动作（与 fish/zsh 对齐）。"""
        cands = _bash_complete("llmw wiki write index ")
        for act in ("add", "remove"):
            assert act in cands, f"wiki write index 缺动作: {act} (实际: {cands})"


@pytest.mark.skipif(not shutil.which("bash"), reason="bash 不可用")
class TestBashDynamicValueCompletion:
    """带动态值的 --flag=value 补全——需要真实 workspace 文件做 _llmw_wikis 探测。"""

    def _setup_workspace(self, tmp_path, wiki_names=("alpha",)):
        """造一个最小 workspace（workspace.toml 含注册 wikis），返回 workspace 根。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        lines = ['schema_version = "2"', 'created_at = "2026-01-01T00:00:00Z"', ""]
        for n in wiki_names:
            lines.append(f"[wikis.{n}]")
            lines.append(f'path = "{n}"')
            lines.append(f'created_at = "2026-01-01T00:00:00Z"')
            lines.append("")
        (ws / "workspace.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return ws

    def _bash_complete_with_env(self, comp_line, env_extra):
        """同 _bash_complete，但注入 env（LLMW_WORKSPACE）。"""
        words = comp_line.split(" ")
        if not words[-1]:
            words = words[:-1] + [""] if comp_line.endswith(" ") else words
        cword = len(words) - 1
        bash_arr = "(" + " ".join(self._bash_quote(w) for w in words) + ")"
        bash_script = (
            f'source "{BASH_COMP}"\n'
            f"COMP_WORDS={bash_arr}\n"
            f"COMP_CWORD={cword}\n"
            f"_llmw\n"
            f'printf "%s\\n" "${{COMPREPLY[@]}}"\n'
        )
        env = dict(os.environ)
        env.update(env_extra)
        result = subprocess.run(
            ["bash", "-c", bash_script],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        if result.returncode != 0:
            pytest.fail(
                f"bash 执行失败:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
        return [line for line in result.stdout.splitlines() if line]

    @staticmethod
    def _bash_quote(s):
        if s == "":
            return "''"
        return "'" + s.replace("'", "'\\''") + "'"

    def test_wiki_name_equals_dynamic(self, tmp_path):
        ws = self._setup_workspace(tmp_path, wiki_names=("alpha", "beta"))
        cands = self._bash_complete_with_env(
            "llmw wiki --name=", {"LLMW_WORKSPACE": str(ws)}
        )
        assert "alpha" in cands and "beta" in cands, (
            f"wiki --name= 应动态返回 wiki 名 (实际: {cands})"
        )

    def test_wiki_rename_old_equals_dynamic(self, tmp_path):
        ws = self._setup_workspace(tmp_path, wiki_names=("alpha",))
        cands = self._bash_complete_with_env(
            "llmw wiki rename --old=", {"LLMW_WORKSPACE": str(ws)}
        )
        assert "alpha" in cands, (
            f"wiki rename --old= 应动态返回 wiki 名 (实际: {cands})"
        )

    def test_model_add_name_no_wiki_leak(self, tmp_path):
        """`model add --name=` 是网关模型名（free-form），不应漏出 wiki 名。"""
        ws = self._setup_workspace(tmp_path, wiki_names=("alpha",))
        cands = self._bash_complete_with_env(
            "llmw model add --name=", {"LLMW_WORKSPACE": str(ws)}
        )
        assert "alpha" not in cands, (
            f"model add --name= 不应漏出 wiki 名 (实际: {cands})"
        )

    def test_wiki_external_add_name_no_wiki_leak(self, tmp_path):
        """`wiki external add --name=` 是新 kebab 名（free-form），不应漏出 wiki 名。"""
        ws = self._setup_workspace(tmp_path, wiki_names=("alpha",))
        cands = self._bash_complete_with_env(
            "llmw wiki external add --name=", {"LLMW_WORKSPACE": str(ws)}
        )
        assert "alpha" not in cands, (
            f"wiki external add --name= 不应漏出 wiki 名 (实际: {cands})"
        )
