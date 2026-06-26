import json

from wiki_workspace import manifest, workspace
from wiki_workspace.commands import list_cmd


def _args(**kw):
    base = dict(workspace=None, tag=None, json=False)
    base.update(kw)
    return type("A", (), base)()


def _seed(root, wikis):
    m = manifest.Manifest("1", "2026-06-26", "claude-sonnet-4-6", {w.name: w for w in wikis})
    workspace.save_manifest(root, m)


def _wiki(name, **kw):
    base = dict(path=name, display_name=name.title(), created="2026-06-26")
    base.update(kw)
    return manifest.WikiEntry(name=name, **base)


def test_list_table(tmp_path, capsys):
    for n in ("llm-systems", "recipes"):
        d = tmp_path / n
        d.mkdir()
        (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    _seed(
        tmp_path,
        [
            _wiki("llm-systems", model="claude-opus-4-8", tags=["research"]),
            _wiki("recipes", tags=["cooking"]),
        ],
    )
    code = list_cmd.run(_args(workspace=str(tmp_path)))
    out = capsys.readouterr().out
    assert code == 0
    assert "llm-systems" in out and "recipes" in out


def test_list_tag_filter(tmp_path, capsys):
    for n in ("llm-systems", "recipes"):
        d = tmp_path / n
        d.mkdir()
        (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    _seed(
        tmp_path,
        [_wiki("llm-systems", tags=["research"]), _wiki("recipes", tags=["cooking"])],
    )
    list_cmd.run(_args(workspace=str(tmp_path), tag="research"))
    out = capsys.readouterr().out
    assert "llm-systems" in out and "recipes" not in out


def test_list_json(tmp_path, capsys):
    d = tmp_path / "llm-systems"
    d.mkdir()
    (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    _seed(tmp_path, [_wiki("llm-systems", tags=["research"])])
    list_cmd.run(_args(workspace=str(tmp_path), json=True))
    obj = json.loads(capsys.readouterr().out)
    assert obj["exit_code"] == 0
    assert obj["result"]["wikis"][0]["name"] == "llm-systems"


def test_list_not_initialized(tmp_path):
    from wiki_workspace import errors

    code = list_cmd.run(_args(workspace=str(tmp_path / "nope")))
    assert code == errors.EXIT_USER_ERROR
