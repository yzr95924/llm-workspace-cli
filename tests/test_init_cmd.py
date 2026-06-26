from wiki_workspace import errors, workspace
from wiki_workspace.commands import init_cmd


def _args(**kw):
    base = dict(workspace=None, default_model="claude-sonnet-4-6", json=False)
    base.update(kw)
    return type("A", (), base)()


def test_init_creates_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    target = tmp_path / "ws"
    code = init_cmd.run(_args(workspace=str(target)))
    assert code == 0
    assert (target / ".workspace.toml").is_file()
    assert (target / "CLAUDE.md").is_file()
    assert "llmw" in (target / "CLAUDE.md").read_text(encoding="utf-8")


def test_init_refuses_existing(tmp_path):
    target = tmp_path / "ws"
    target.mkdir()
    (target / ".workspace.toml").write_text("x", encoding="utf-8")
    code = init_cmd.run(_args(workspace=str(target)))
    assert code == errors.EXIT_USER_ERROR


def test_init_default_model_stored(tmp_path, monkeypatch):
    from wiki_workspace import manifest

    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    target = tmp_path / "ws"
    init_cmd.run(_args(workspace=str(target), default_model="claude-opus-4-8"))
    m = manifest.parse((target / ".workspace.toml").read_text(encoding="utf-8"))
    assert m.default_model == "claude-opus-4-8"
