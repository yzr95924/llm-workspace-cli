"""llmw wiki rename: happy + error paths + 原子性 (staging 清理) + 骨架同步/窗口阻断。

按 MEMORY 短条目"测试优先级低 — prototype 阶段不写自动化测试,跑通后补;
agent 不主动加测试代码"。本次实现同步补基本 happy path + 关键 error + 原子性回归,
后续补充覆盖由维护者按需添加。
"""

from pathlib import Path

import pytest

from llmw import WIKI_FORMAT_VERSION, __version__
from llmw.content.wiki_fixtures import run_checks
from llmw.errors import (
    InvalidWikiName,
    RenameRequiresConfirmation,
    WikiExists,
    WikiNotFound,
    WikiSessionActive,
)
from llmw.fsutil import sha256_file
from llmw.wiki import init_wiki
from llmw.wiki import manager as wiki_mgr
from llmw.wiki import store as wiki_store
from llmw.workspace import store as ws_store


@pytest.fixture(autouse=True)
def _no_real_tmux(monkeypatch):
    """rename 测试默认隔离真实 tmux（活跃窗口阻断行为由专测 monkeypatch 回来）。"""
    from llmw.wiki import byobu as _byobu

    monkeypatch.setattr(_byobu, "byobu_available", lambda: False)


@pytest.fixture
def full_workspace_with_wiki(tmp_path: Path) -> Path:
    """全骨架 wiki（init_wiki.render_and_write 出生 + 指纹回填），供骨架同步断言。"""
    ws = ws_store.create_skeleton(tmp_path)
    ws.wikis["foo"] = ws_store.WikiEntry(
        name="foo", path="foo", created_at="2026-01-01T00:00:00Z"
    )
    ws_store.save(tmp_path, ws)
    foo = tmp_path / "foo"
    foo.mkdir()
    meta = wiki_store.create_skeleton(foo, "foo", "foo")
    setup_date = (meta.created_at or "").replace("T", " ")[:16]
    init_wiki.render_and_write(
        foo,
        "foo",
        setup_date,
        cli_version=__version__,
        format_version=WIKI_FORMAT_VERSION,
    )
    meta.agents_md_sha256 = sha256_file(foo / "AGENTS.md") or ""
    wiki_store.save(foo, meta)
    return tmp_path


# ===== happy path =====


def test_rename_happy_path(workspace_with_wiki: Path, capsys):
    """foo → bar: 3 处全改 (workspace.toml key, 目录名, meta.name)。"""
    ws_root = workspace_with_wiki
    old_dir = ws_root / "foo"

    wiki_mgr.rename(ws_root, "foo", "bar")

    # 1. workspace.toml 切换
    ws = ws_store.load(ws_root)
    assert "foo" not in ws.wikis
    assert "bar" in ws.wikis
    # created_at 保留
    assert ws.wikis["bar"].created_at == "2026-01-01T00:00:00Z"
    assert ws.wikis["bar"].path == "bar"

    # 2. 子目录改名,旧目录消失
    assert not old_dir.exists()
    new_dir = ws_root / "bar"
    assert new_dir.is_dir()

    # 3. wiki_metadata.toml name 改写
    meta = wiki_store.load(new_dir)
    assert meta.name == "bar"

    # 4. 原有内容保留 (copytree 验证)
    assert (new_dir / "notes.txt").read_text(encoding="utf-8") == "# foo scaffold\n"

    # 5. 打印信息含 old → new + path
    out = capsys.readouterr().out
    assert "foo" in out and "bar" in out
    assert "path" in out


def test_rename_topic_syncs_when_default(workspace_with_wiki: Path):
    """topic 默认值 == old (add 时未传 --topic) → 同步成 new。"""
    ws_root = workspace_with_wiki
    wiki_mgr.rename(ws_root, "foo", "bar")
    meta = wiki_store.load(ws_root / "bar")
    assert meta.topic == "bar"


def test_rename_topic_preserved_when_custom(workspace_with_wiki: Path):
    """topic 与 old 不同 → 不动 topic。"""
    ws_root = workspace_with_wiki
    # 改 foo 的 topic 为自定义值
    foo_dir = ws_root / "foo"
    meta = wiki_store.load(foo_dir)
    meta.topic = "My Custom Topic"
    wiki_store.save(foo_dir, meta)

    wiki_mgr.rename(ws_root, "foo", "bar")
    meta = wiki_store.load(ws_root / "bar")
    assert meta.topic == "My Custom Topic"
    assert meta.name == "bar"


def test_rename_json_output(workspace_with_wiki: Path, capsys):
    """--json 模式输出可解析 JSON,含 topic_changed 等关键字段。"""
    import json

    wiki_mgr.rename(workspace_with_wiki, "foo", "bar", as_json=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["old"] == "foo"
    assert data["new"] == "bar"
    assert data["topic_changed"] is True
    assert data["topic_old"] == "foo"
    assert data["topic_new"] == "bar"
    assert data["created_at"] == "2026-01-01T00:00:00Z"
    assert data["path"].endswith("/bar")


def test_rename_quiet_suppresses_info(workspace_with_wiki: Path, capsys):
    """--quiet 只打一行,不打 path / topic / created_at 行。"""
    wiki_mgr.rename(workspace_with_wiki, "foo", "bar", quiet=True)
    out = capsys.readouterr().out
    assert "wiki 已重命名" in out
    assert "path:" not in out
    assert "created_at" not in out


# ===== error paths =====


def test_rename_new_already_in_registry(workspace_with_two_wikis: Path):
    """new 已是另一个 wiki → WikiExists,foo 与 bar 均不变。"""
    ws_root = workspace_with_two_wikis
    with pytest.raises(WikiExists):
        wiki_mgr.rename(ws_root, "foo", "bar")

    # 状态完全不变
    ws = ws_store.load(ws_root)
    assert set(ws.wikis) == {"foo", "bar"}
    assert (ws_root / "foo").is_dir()
    assert (ws_root / "bar").is_dir()


def test_rename_old_not_found(workspace_with_wiki: Path):
    with pytest.raises(WikiNotFound):
        wiki_mgr.rename(workspace_with_wiki, "nonexistent", "bar")


def test_rename_same_name_rejected(workspace_with_wiki: Path):
    """old == new → InvalidWikiName (带 hint),原件不动。"""
    with pytest.raises(InvalidWikiName) as exc_info:
        wiki_mgr.rename(workspace_with_wiki, "foo", "foo")
    assert "无变更" in str(exc_info.value)
    # 原件仍存在
    assert (workspace_with_wiki / "foo").is_dir()


def test_rename_invalid_new_name_format(workspace_with_wiki: Path):
    """new 含大写字母 → InvalidWikiName (NAME_RE 检查)。"""
    with pytest.raises(InvalidWikiName):
        wiki_mgr.rename(workspace_with_wiki, "foo", "FOO")


def test_rename_new_path_exists_on_disk(workspace_with_wiki: Path):
    """new 不在 registry 但 fs 上已有同名目录 (残留空目录) → WikiExists。"""
    ws_root = workspace_with_wiki
    stray = ws_root / "bar"
    stray.mkdir()
    (stray / "garbage.txt").write_text("x", encoding="utf-8")

    with pytest.raises(WikiExists):
        wiki_mgr.rename(ws_root, "foo", "bar")

    # 残留目录未动
    assert stray.is_dir()
    assert (stray / "garbage.txt").exists()
    # 原 foo 仍存在
    assert (ws_root / "foo").is_dir()


# ===== 原子性: staging 清理 =====


def test_rename_staging_cleaned_on_happy_path(workspace_with_wiki: Path):
    """成功路径下 .llmw-trash/rename-*-to-* staging 已被切到新名,不应残留。"""
    ws_root = workspace_with_wiki
    wiki_mgr.rename(ws_root, "foo", "bar")

    trash = ws_root / ".llmw-trash"
    if trash.exists():
        leftovers = list(trash.glob("rename-*-to-*"))
        assert not leftovers, f"staging 未清理: {leftovers}"


def test_rename_staging_cleaned_on_phase2_failure(
    workspace_with_wiki: Path, monkeypatch
):
    """Phase 2 (workspace.toml save) 失败 → staging 必须被清掉,原件不动。"""
    from llmw.wiki import manager as m

    def boom(*args, **kwargs):
        raise OSError("simulated workspace.toml write failure")

    # 在 ws_store.save 调用前一步 patch(Phase 2 第一行 ws.wikis[new] = 之后,
    # 但 save 调用点前;实际通过 monkeypatch 整个 ws_store.save 即可)
    monkeypatch.setattr(m.ws_store, "save", boom)

    with pytest.raises(OSError, match="simulated"):
        m.rename(workspace_with_wiki, "foo", "bar")

    # staging 必须清理
    trash = workspace_with_wiki / ".llmw-trash"
    if trash.exists():
        leftovers = list(trash.glob("rename-*-to-*"))
        assert not leftovers, f"staging 残留: {leftovers}"

    # 原件不动
    assert (workspace_with_wiki / "foo").is_dir()
    ws = ws_store.load(workspace_with_wiki)
    assert "foo" in ws.wikis
    assert "bar" not in ws.wikis


def test_rename_staging_cleaned_on_phase3_failure(
    workspace_with_wiki: Path, monkeypatch
):
    """Phase 3 (atomic rename) 失败 → staging 清理 + workspace.toml 回滚。"""
    from llmw.wiki import manager as m

    # 强制 staging.rename 抛 OSError(模拟 POSIX rename 失败)
    def boom_rename(self, *args, **kwargs):
        raise OSError("simulated atomic rename failure")

    monkeypatch.setattr(m.Path, "rename", boom_rename)

    with pytest.raises(OSError, match="simulated"):
        m.rename(workspace_with_wiki, "foo", "bar")

    # staging 必须清理
    trash = workspace_with_wiki / ".llmw-trash"
    if trash.exists():
        leftovers = list(trash.glob("rename-*-to-*"))
        assert not leftovers, f"staging 残留: {leftovers}"

    # workspace.toml 必须回滚
    ws = ws_store.load(workspace_with_wiki)
    assert "foo" in ws.wikis, "workspace.toml 未回滚,foo 丢失"
    assert "bar" not in ws.wikis, "workspace.toml 未回滚,残留 bar"

    # foo 元数据未变
    assert (workspace_with_wiki / "foo").is_dir()


# ===== 骨架同步（AGENTS.md 重渲染 + index/log 头部 topic） =====


def test_rename_resyncs_skeleton_headers(full_workspace_with_wiki: Path):
    """topic 默认值 rename: AGENTS.md/index/log 头部随新 topic 同步, 指纹对齐, lint 转绿。"""
    ws_root = full_workspace_with_wiki
    wiki_mgr.rename(ws_root, "foo", "bar")
    bar = ws_root / "bar"

    agents = (bar / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# bar Wiki：LLM 维护守则")
    assert "| 主题 | bar |" in agents

    index = (bar / "wiki" / "index.md").read_text(encoding="utf-8")
    assert 'title: "bar Index"' in index
    assert "# bar Wiki\n" in index

    log = (bar / "wiki" / "log.md").read_text(encoding="utf-8")
    assert 'title: "bar Log"' in log

    meta = wiki_store.load(bar)
    assert meta.agents_md_sha256 == sha256_file(bar / "AGENTS.md")

    # 核心回归: rename 返回即 lint 一致态（修复前 agents-md-template-sync 判红）
    report = run_checks(bar, WIKI_FORMAT_VERSION)
    failures = [c["id"] for c in report["checks"] if c["passed"] is False]
    assert failures == []


def test_rename_custom_topic_leaves_skeleton_untouched(full_workspace_with_wiki: Path):
    """topic 自定义 → rename 不碰骨架（topic 行不含 old，无可同步对象）。"""
    ws_root = full_workspace_with_wiki
    foo = ws_root / "foo"
    meta = wiki_store.load(foo)
    meta.topic = "My Custom Topic"
    wiki_store.save(foo, meta)
    before = {
        rel: (foo / rel).read_bytes()
        for rel in ("AGENTS.md", "wiki/index.md", "wiki/log.md")
    }

    wiki_mgr.rename(ws_root, "foo", "bar")

    bar = ws_root / "bar"
    for rel, data in before.items():
        assert (bar / rel).read_bytes() == data
    assert wiki_store.load(bar).topic == "My Custom Topic"


def test_rename_agents_md_drift_requires_yes(full_workspace_with_wiki: Path):
    """AGENTS.md 手改（指纹不符）且未 --yes → RenameRequiresConfirmation, 零副作用。"""
    ws_root = full_workspace_with_wiki
    agents = ws_root / "foo" / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n<!-- my custom rule -->\n",
        encoding="utf-8",
    )

    with pytest.raises(RenameRequiresConfirmation):
        wiki_mgr.rename(ws_root, "foo", "bar")

    assert "<!-- my custom rule -->" in agents.read_text(encoding="utf-8")
    assert (ws_root / "foo").is_dir()
    ws = ws_store.load(ws_root)
    assert "foo" in ws.wikis and "bar" not in ws.wikis


def test_rename_drift_yes_overwrites(full_workspace_with_wiki: Path):
    """手改 + --yes → 按模板重渲染覆盖, 定制内容丢弃, 指纹更新为渲染稿。"""
    ws_root = full_workspace_with_wiki
    agents = ws_root / "foo" / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n<!-- my custom rule -->\n",
        encoding="utf-8",
    )

    wiki_mgr.rename(ws_root, "foo", "bar", yes=True)

    new_agents = (ws_root / "bar" / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- my custom rule -->" not in new_agents
    assert new_agents.startswith("# bar Wiki：LLM 维护守则")
    meta = wiki_store.load(ws_root / "bar")
    assert meta.agents_md_sha256 == sha256_file(ws_root / "bar" / "AGENTS.md")


def test_rename_hand_edited_header_line_skipped_with_warn(
    full_workspace_with_wiki: Path, capsys
):
    """index.md H1 被手改成非出生形态 → 该行跳过 + stderr warning, frontmatter topic 行照常同步。"""
    ws_root = full_workspace_with_wiki
    idx = ws_root / "foo" / "wiki" / "index.md"
    idx.write_text(
        idx.read_text(encoding="utf-8").replace("# foo Wiki\n", "# Portal\n", 1),
        encoding="utf-8",
    )

    wiki_mgr.rename(ws_root, "foo", "bar")

    index = (ws_root / "bar" / "wiki" / "index.md").read_text(encoding="utf-8")
    assert 'title: "bar Index"' in index
    assert "# Portal\n" in index
    assert "# foo Wiki\n" not in index
    err = capsys.readouterr().err
    assert "wiki/index.md" in err and "非出生形态" in err


def test_rename_missing_skeleton_warns(workspace_with_wiki: Path, capsys):
    """骨架文件缺失（最小 wiki）→ rename 照常成功 + stderr warning, 不无中生有重建。"""
    wiki_mgr.rename(workspace_with_wiki, "foo", "bar")
    res = capsys.readouterr()
    assert "AGENTS.md 不存在" in res.err
    assert "骨架同步" not in res.out


def test_rename_skeleton_write_failure_rolls_back(
    full_workspace_with_wiki: Path, monkeypatch
):
    """Phase 2 骨架写盘失败 → AGENTS.md/index 恢复旧字节 + metadata（含指纹）回滚。"""
    from llmw.fsutil import atomic_write as real_atomic_write
    from llmw.wiki import manager as m

    state = {"boom": True}

    def fake_atomic_write(path, content):
        if state["boom"] and str(path).endswith("log.md"):
            state["boom"] = False
            raise OSError("simulated skeleton write failure")
        return real_atomic_write(path, content)

    monkeypatch.setattr(m, "atomic_write", fake_atomic_write)

    ws_root = full_workspace_with_wiki
    foo = ws_root / "foo"
    before_agents = (foo / "AGENTS.md").read_text(encoding="utf-8")

    with pytest.raises(OSError, match="simulated"):
        m.rename(ws_root, "foo", "bar")

    assert (foo / "AGENTS.md").read_text(encoding="utf-8") == before_agents
    assert 'title: "foo Index"' in (foo / "wiki" / "index.md").read_text(
        encoding="utf-8"
    )
    meta = wiki_store.load(foo)
    assert meta.name == "foo" and meta.topic == "foo"
    assert meta.agents_md_sha256 == sha256_file(foo / "AGENTS.md")
    ws = ws_store.load(ws_root)
    assert "foo" in ws.wikis and "bar" not in ws.wikis


def test_rename_active_session_blocks(workspace_with_wiki: Path, monkeypatch):
    """旧名挂着 @llmw_wiki 带标窗口 → WikiSessionActive 硬阻断, 磁盘与 registry 不动。"""
    from llmw.wiki import byobu as _byobu
    from llmw.wiki import manager as m

    monkeypatch.setattr(_byobu, "byobu_available", lambda: True)
    row = _byobu.WindowRow(
        session="llm_workspace",
        window_id="@0",
        window_name="foo-main",
        activity="1",
        dead="0",
        dead_time="",
        wiki="foo",
        started="1",
        backend="opencode",
        pcmd="node",
    )
    monkeypatch.setattr(_byobu, "list_windows", lambda: [row])

    with pytest.raises(WikiSessionActive):
        m.rename(workspace_with_wiki, "foo", "bar")

    assert (workspace_with_wiki / "foo").is_dir()
    ws = ws_store.load(workspace_with_wiki)
    assert "foo" in ws.wikis and "bar" not in ws.wikis
