from wiki_workspace import errors, manifest, workspace
from wiki_workspace.commands import config_cmd


def _args(name, action, key=None, value=None, **kw):
    base = dict(workspace=None, json=False, name=name, action=action, key=key, value=value)
    base.update(kw)
    return type("A", (), base)()


def _seed(root, name="w"):
    d = root / name
    d.mkdir()
    (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = manifest.Manifest(
        "1",
        "2026-06-26",
        "claude-sonnet-4-6",
        {
            name: manifest.WikiEntry(
                name=name, path=name, display_name=name.title(), created="2026-06-26"
            )
        },
    )
    workspace.save_manifest(root, m)


def test_config_show(tmp_path, capsys):
    _seed(tmp_path)
    code = config_cmd.run(_args("w", "show", workspace=str(tmp_path)))
    assert code == 0
    assert "W" in capsys.readouterr().out


def test_config_set_display_name(tmp_path):
    _seed(tmp_path)
    code = config_cmd.run(_args("w", "set", "display_name", "New Name", workspace=str(tmp_path)))
    assert code == 0
    m, _ = manifest.load_and_validate(
        (tmp_path / ".workspace.toml").read_text(encoding="utf-8"), tmp_path
    )
    assert m.wikis["w"].display_name == "New Name"


def test_config_set_tags_comma(tmp_path):
    _seed(tmp_path)
    config_cmd.run(_args("w", "set", "tags", "a,b,c", workspace=str(tmp_path)))
    m, _ = manifest.load_and_validate(
        (tmp_path / ".workspace.toml").read_text(encoding="utf-8"), tmp_path
    )
    assert m.wikis["w"].tags == ["a", "b", "c"]


def test_config_unset_required_rejected(tmp_path):
    _seed(tmp_path)
    code = config_cmd.run(_args("w", "unset", "display_name", workspace=str(tmp_path)))
    assert code == errors.EXIT_ENV_ERROR  # 非法 key


def test_config_unset_model(tmp_path):
    _seed(tmp_path)
    config_cmd.run(_args("w", "set", "model", "claude-opus-4-8", workspace=str(tmp_path)))
    code = config_cmd.run(_args("w", "unset", "model", workspace=str(tmp_path)))
    assert code == 0
    m, _ = manifest.load_and_validate(
        (tmp_path / ".workspace.toml").read_text(encoding="utf-8"), tmp_path
    )
    assert m.wikis["w"].model is None


def test_config_get(tmp_path, capsys):
    _seed(tmp_path)
    code = config_cmd.run(_args("w", "get", "display_name", workspace=str(tmp_path)))
    assert code == 0
    assert "W" in capsys.readouterr().out


def test_config_wiki_not_found(tmp_path):
    _seed(tmp_path)
    code = config_cmd.run(_args("ghost", "show", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR
