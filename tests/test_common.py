import pytest

from wiki_workspace import errors, manifest, workspace
from wiki_workspace.commands import _common


def _seed(root, entries):
    m = manifest.Manifest("1", "2026-06-26", "claude-sonnet-4-6", {e.name: e for e in entries})
    workspace.save_manifest(root, m)


def test_load_manifest_ok(tmp_path):
    from wiki_workspace import manifest as M

    wdir = tmp_path / "w"
    wdir.mkdir()
    (wdir / "CLAUDE.md").write_text("x", encoding="utf-8")
    _seed(tmp_path, [M.WikiEntry(name="w", path="w", display_name="W", created="2026-06-26")])
    args = type("A", (), {"workspace": str(tmp_path)})()
    m = _common.load_manifest(args)
    assert "w" in m.wikis


def test_load_manifest_not_initialized(tmp_path):
    args = type("A", (), {"workspace": str(tmp_path / "missing")})()
    with pytest.raises(errors.CommandError) as ei:
        _common.load_manifest(args)
    assert ei.value.category == "workspace-not-initialized"


def test_load_manifest_validation_error(tmp_path):
    # path 指向不存在的目录
    _seed(
        tmp_path,
        [manifest.WikiEntry(name="ghost", path="ghost", display_name="G", created="2026-06-26")],
    )
    args = type("A", (), {"workspace": str(tmp_path)})()
    with pytest.raises(errors.CommandError) as ei:
        _common.load_manifest(args)
    assert ei.value.exit_code == errors.EXIT_USER_ERROR
