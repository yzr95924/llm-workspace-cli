"""llmw status STATE 判定纯函数测试（T13，巡检收尾 #11）。

覆盖 llmw/backends.match_working/match_waiting（模式注册表，单一真源）、
llmw/wiki/status._classify_state（判定短路优先级）、_state_sorted（actionable-first）。

只测纯函数——capture-pane 经 monkeypatch，零 tmux/subprocess 依赖（CI 无 tmux 可跑）。
模式样本为合成文本，结构源自 opencode 1.18.18 真实屏幕（2026-08-15 实测：
工作态底部状态行含 "esc interrupt" + braille spinner；空闲态底部输入行
"ctrl+p commands"）。
"""

from llmw.backends import match_waiting, match_working
from llmw.wiki import byobu
from llmw.wiki.status import _classify_state, _state_sorted

# ===== match_working / match_waiting（llmw/backends.py） =====


def test_match_working_opencode_esc_interrupt():
    tail = "╭─ esc interrupt\n╰─ ctrl+p commands  │  esc to cancel"
    assert match_working(tail, "opencode") is True


def test_match_working_opencode_spinner():
    tail = "⠹ thinking about your request..."
    assert match_working(tail, "opencode") is True


def test_match_working_opencode_absent():
    assert match_working("just a shell prompt $ ", "opencode") is False


def test_match_working_unregistered_backend_false():
    # claude/qodercli 占位未配置 + 未知/无标 → 一律 False（调用方降级 unknown）
    assert match_working("esc interrupt", "claude") is False
    assert match_working("esc interrupt", "qodercli") is False
    assert match_working("esc interrupt", None) is False


def test_match_waiting_opencode_input_line():
    tail = "╭─ ctrl+p commands\n╰─ ╹▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀"
    assert match_waiting(tail, "opencode") is True


def test_match_waiting_exclusive_with_working():
    # working 标志在场时 waiting 必须互斥（判据：waiting AND NOT working）
    tail = "esc interrupt\nctrl+p commands"
    assert match_working(tail, "opencode") is True
    assert match_waiting(tail, "opencode") is False


def test_match_waiting_unregistered_backend_false():
    assert match_waiting("ctrl+p commands", "claude") is False
    assert match_waiting("ctrl+p commands", None) is False


# ===== _classify_state（短路优先级：dead → shell → capture → unknown） =====


def _state_dict(**kw):
    base = {
        "dead": False,
        "pcmd": "opencode",
        "backend": "opencode",
        "window_id": "@1",
    }
    base.update(kw)
    return base


def test_classify_dead_short_circuit_no_capture(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        return ""

    monkeypatch.setattr(byobu, "capture_pane_tail", boom)
    assert _classify_state(_state_dict(dead=True)) == "dead"
    assert calls == []  # dead 短路：零 capture 调用


def test_classify_shell_short_circuit_no_capture(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        return ""

    monkeypatch.setattr(byobu, "capture_pane_tail", boom)
    for shell in ("fish", "bash", "zsh", "sh", "dash", "ash"):
        assert _classify_state(_state_dict(pcmd=shell, backend="claude")) == "shell"
    assert calls == []  # 假活短路：零 capture 调用


def test_classify_pcmd_case_insensitive():
    # pcmd 已由 _row_to_dict 归一为 basename；大小写不敏感
    assert _classify_state(_state_dict(pcmd="Fish", backend="claude")) == "shell"


def test_classify_working_via_capture(monkeypatch):
    monkeypatch.setattr(byobu, "capture_pane_tail", lambda wid: "⠹ esc interrupt")
    assert _classify_state(_state_dict()) == "working"


def test_classify_waiting_via_capture(monkeypatch):
    monkeypatch.setattr(
        byobu, "capture_pane_tail", lambda wid: "╭─ ctrl+p commands\n╰─ ╹▀▀▀▀"
    )
    assert _classify_state(_state_dict()) == "waiting"


def test_classify_unknown_when_backend_unregistered(monkeypatch):
    # claude 无模式注册 → capture 到什么都无法判 → unknown
    monkeypatch.setattr(byobu, "capture_pane_tail", lambda wid: "esc interrupt")
    assert _classify_state(_state_dict(backend="claude")) == "unknown"


def test_classify_unknown_fallback(monkeypatch):
    monkeypatch.setattr(byobu, "capture_pane_tail", lambda wid: "some random output")
    assert _classify_state(_state_dict()) == "unknown"


def test_classify_window_id_passed_to_capture(monkeypatch):
    seen = []

    def fake(wid):
        seen.append(wid)
        return ""

    monkeypatch.setattr(byobu, "capture_pane_tail", fake)
    _classify_state(_state_dict(window_id="@42"))
    assert seen == ["@42"]


# ===== _state_sorted（actionable first） =====


def _row(wiki, window, state):
    return {"wiki": wiki, "window": window, "state": state}


def test_state_sorted_actionable_first():
    rows = [
        _row("a", "main", "working"),
        _row("b", "main", "dead"),
        _row("c", "main", "waiting"),
        _row("d", "main", "shell"),
        _row("e", "main", "unknown"),
    ]
    got = [r["wiki"] for r in _state_sorted(rows)]
    # waiting/shell（0）最前 → working/unknown（1）→ dead（2）最后
    assert got == ["c", "d", "a", "e", "b"]


def test_state_sorted_stable_within_group():
    rows = [
        _row("b", "main", "working"),
        _row("a", "main", "working"),
        _row("c", "main", "dead"),
    ]
    got = [r["wiki"] for r in _state_sorted(rows)]
    assert got == ["a", "b", "c"]  # 同级按 (wiki, window) 字典序


def test_state_sorted_unknown_state_default_rank():
    # 未知 state 值（未来新增值未入表）→ 按 1 处理（working 档），不崩
    rows = [_row("a", "main", "future-state"), _row("b", "main", "waiting")]
    got = [r["wiki"] for r in _state_sorted(rows)]
    assert got == ["b", "a"]
