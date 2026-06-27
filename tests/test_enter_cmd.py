from wiki_workspace import errors, manifest, workspace
from wiki_workspace.commands import enter_cmd


def _args(name, **kw):
    base = dict(
        workspace=None,
        json=False,
        name=name,
        model=None,
        claude_md_check="warn",
        dry_run=False,
    )
    base.update(kw)
    return type("A", (), base)()


def _seed(root, name="llm-systems"):
    d = root / name
    d.mkdir()
    (d / "CLAUDE.md").write_text("# x", encoding="utf-8")
    m = manifest.Manifest(
        "1",
        "2026-06-26",
        "claude-sonnet-4-6",
        {
            name: manifest.WikiEntry(
                name=name,
                path=name,
                display_name="X",
                created="2026-06-26",
                model="claude-opus-4-8",
            )
        },
    )
    workspace.save_manifest(root, m)


def test_enter_dry_run_prints_cmd(tmp_path, capsys):
    _seed(tmp_path)
    code = enter_cmd.run(_args("llm-systems", dry_run=True, workspace=str(tmp_path)))
    out = capsys.readouterr().out
    assert code == 0
    assert "claude" in out
    assert "--add-dir" in out
    assert "--model" in out and "claude-opus-4-8" in out


def test_enter_missing_claude_md_fail_mode(tmp_path):
    root = tmp_path
    (root / "w").mkdir()  # 无 CLAUDE.md
    workspace.save_manifest(
        root,
        manifest.Manifest(
            "1",
            "2026-06-26",
            "claude-sonnet-4-6",
            {"w": manifest.WikiEntry("w", "w", "W", "2026-06-26")},
        ),
    )
    code = enter_cmd.run(_args("w", claude_md_check="fail", workspace=str(root)))
    assert code == errors.EXIT_USER_ERROR


def test_enter_not_found(tmp_path):
    _seed(tmp_path)
    code = enter_cmd.run(_args("ghost", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR


def test_enter_dry_run_includes_system_prompt(tmp_path, capsys):
    _seed(tmp_path)
    enter_cmd.run(_args("llm-systems", dry_run=True, workspace=str(tmp_path)))
    out = capsys.readouterr().out
    assert "workspace root" in out.lower()
