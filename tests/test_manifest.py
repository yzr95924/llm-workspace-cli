from wiki_workspace import manifest

SAMPLE = """\
schema_version = "1"
created = "2026-06-26"

[workspace]
default_model = "claude-sonnet-4-6"

[wikis.llm-systems]
path = "llm-systems"
display_name = "LLM Systems"
description = "research"
model = "claude-opus-4-8"
created = "2026-06-26"
tags = ["research", "papers"]
"""


def test_parse_builds_manifest():
    m = manifest.parse(SAMPLE)
    assert m.schema_version == "1"
    assert m.created == "2026-06-26"
    assert m.default_model == "claude-sonnet-4-6"
    w = m.wikis["llm-systems"]
    assert w.display_name == "LLM Systems"
    assert w.model == "claude-opus-4-8"
    assert w.tags == ["research", "papers"]


def test_parse_missing_fields_default():
    m = manifest.parse(
        'schema_version = "1"\ncreated = "2026-06-26"\n[workspace]\ndefault_model = "x"\n'
    )
    assert m.wikis == {}


def test_serialize_round_trips(tmp_path):
    m = manifest.parse(SAMPLE)
    text = manifest.serialize(m)
    m2 = manifest.parse(text)
    assert m2.wikis["llm-systems"].tags == ["research", "papers"]
    assert m2.default_model == "claude-sonnet-4-6"


def test_empty_manifest_helper():
    m = manifest.empty_manifest("2026-06-26")
    assert m.schema_version == "1"
    assert m.wikis == {}
    assert m.default_model == "claude-sonnet-4-6"


def test_wiki_entry_defaults():
    e = manifest.WikiEntry(name="r", path="r", display_name="R", created="2026-06-26")
    assert e.description == ""
    assert e.model is None
    assert e.tags == []
