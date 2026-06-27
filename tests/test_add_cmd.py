from wiki_workspace import _compat, errors, manifest, workspace
from wiki_workspace.commands import add_cmd


def _args(name, **kw):
    base = dict(
        workspace=None,
        json=False,
        name=name,
        display_name=None,
        description=None,
        model=None,
        tag=[],
        topic=None,
        no_git=False,
    )
    base.update(kw)
    return type("A", (), base)()


def _seed_root(root):
    workspace.save_manifest(root, manifest.empty_manifest("2026-06-26"))


def _fake_setup_success(tmp_path, fake_skill, monkeypatch):
    """让 subprocess.run 假装 setup_wiki.py 成功：把目录造出来。"""

    def fake(cmd, **kwargs):
        # cmd == [python, <skill>/scripts/setup_wiki.py, topic, wiki_root]
        wiki_root = __import__("pathlib").Path(cmd[-1])
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "CLAUDE.md").write_text("# " + cmd[-2], encoding="utf-8")
        (wiki_root / "wiki").mkdir(exist_ok=True)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(add_cmd.subprocess, "run", fake)


def test_add_missing_dependency_hard_fails(tmp_path, monkeypatch):
    _seed_root(tmp_path)
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(tmp_path / "nope"))
    # 隔离：屏蔽真实的 ~/.claude/skills/llm-wiki-management（第 3 级探测）
    monkeypatch.setattr(_compat, "_HOME_SKILL_PATH", tmp_path / "no-skill", raising=False)
    code = add_cmd.run(_args("foo", workspace=str(tmp_path)))
    assert code == errors.EXIT_ENV_ERROR


def test_add_creates_wiki_and_manifest_entry(tmp_path, monkeypatch, fake_skill):
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_root(tmp_path)
    _fake_setup_success(tmp_path, fake_skill, monkeypatch)

    code = add_cmd.run(
        _args(
            "llm-systems",
            display_name="LLM Systems",
            topic="LLM Systems",
            tag=["research"],
            workspace=str(tmp_path),
        )
    )
    assert code == 0
    m, _ = manifest.load_and_validate(
        (tmp_path / ".workspace.toml").read_text(encoding="utf-8"), tmp_path
    )
    w = m.wikis["llm-systems"]
    assert w.display_name == "LLM Systems"
    assert "research" in w.tags
    assert (tmp_path / "llm-systems" / "CLAUDE.md").is_file()


def test_add_duplicate_name_fails(tmp_path, monkeypatch, fake_skill):
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_root(tmp_path)
    # 预置一个已存在的 wiki 条目 + 目录
    d = tmp_path / "llm-systems"
    d.mkdir()
    (d / "CLAUDE.md").write_text("x", encoding="utf-8")
    m = manifest.empty_manifest("2026-06-26")
    m.wikis["llm-systems"] = manifest.WikiEntry("llm-systems", "llm-systems", "X", "2026-06-26")
    workspace.save_manifest(tmp_path, m)
    code = add_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR


def test_add_invalid_name_fails(tmp_path):
    _seed_root(tmp_path)
    code = add_cmd.run(_args("Bad_Name", workspace=str(tmp_path)))
    assert code == errors.EXIT_USER_ERROR


def test_add_setup_script_failure_no_manifest_write(tmp_path, monkeypatch, fake_skill):
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_root(tmp_path)

    def fake(cmd, **kwargs):
        class R:
            returncode = 2

        return R()

    monkeypatch.setattr(add_cmd.subprocess, "run", fake)
    code = add_cmd.run(_args("llm-systems", workspace=str(tmp_path)))
    assert code == errors.EXIT_ENV_ERROR
    m, _ = manifest.load_and_validate(
        (tmp_path / ".workspace.toml").read_text(encoding="utf-8"), tmp_path
    )
    assert "llm-systems" not in m.wikis  # 不写半截 manifest


def test_add_no_git_flag_warns_and_ignored(tmp_path, monkeypatch, fake_skill, capsys):
    monkeypatch.setattr(workspace, "today_iso", lambda: "2026-06-26")
    monkeypatch.setenv("LLM_WIKI_MANAGEMENT_PATH", str(fake_skill))
    _seed_root(tmp_path)
    _fake_setup_success(tmp_path, fake_skill, monkeypatch)
    code = add_cmd.run(_args("llm-systems", no_git=True, workspace=str(tmp_path)))
    assert code == 0
    assert "no-git" in capsys.readouterr().err.lower()
