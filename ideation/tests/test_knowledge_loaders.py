"""load_corpus(): front matter, ids, README skipping, json/jsonl, overrides and warnings."""

import json

from ideate.knowledge.loaders import load_corpus, parse_front_matter


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_front_matter_fields_and_defaults(tmp_path):
    _write(tmp_path / "demo-strategy.md", "---\ntitle: Demo strategy\ntags: demo, pitch , judging\nkind: guidance   # comment\nsource: https://example.org/a#frag\nauthors: me\n---\n# Heading\n\nBody text.\n")
    _write(tmp_path / "nested" / "notes.txt", "# From heading\n\nplain text\n")
    _write(tmp_path / "stem.md", "no heading, no front matter")
    docs = {d.id: d for d in load_corpus([tmp_path])}
    assert sorted(docs) == ["demo-strategy", "nested__notes", "stem"]
    d = docs["demo-strategy"]
    assert d.title == "Demo strategy" and d.source == "https://example.org/a#frag"
    assert d.text == "# Heading\n\nBody text."
    assert d.metadata == {"authors": "me", "tags": ["demo", "pitch", "judging"], "kind": "guidance"}
    assert docs["nested__notes"].title == "From heading" and docs["nested__notes"].metadata == {"tags": [], "kind": "guidance"}
    assert docs["stem"].title == "stem" and docs["stem"].text == "no heading, no front matter"


def test_parse_front_matter_edge_cases():
    assert parse_front_matter("plain") == ({}, "plain")
    assert parse_front_matter("---\ntitle: x\nno closing") == ({}, "---\ntitle: x\nno closing")
    fields, body = parse_front_matter("---\nTitle: X\n\nbroken line\nkind: event\n---\nbody")
    assert fields == {"title": "X", "kind": "event"} and body == "body"


def test_readme_skipped_unknown_kind_defaults_and_warnings(tmp_path, capsys):
    _write(tmp_path / "README.md", "# skip")
    _write(tmp_path / "sub" / "readme.MD", "# skip too")
    _write(tmp_path / "weird.md", "---\nkind: rubbish\n---\ntext")
    _write(tmp_path / "ev.md", "---\nkind: evidence\n---\nclaim without a source")
    _write(tmp_path / "ok.md", "---\nkind: evidence\nsource: paper\n---\nclaim")
    _write(tmp_path / "ignored.csv", "a,b")
    docs = {d.id: d for d in load_corpus([tmp_path])}
    assert sorted(docs) == ["ev", "ok", "weird"]
    assert docs["weird"].metadata["kind"] == "guidance"
    err = capsys.readouterr().err
    assert "unknown kind 'rubbish'" in err and "evidence' without a source" in err and "ok.md" not in err


def test_json_and_jsonl_items(tmp_path):
    _write(tmp_path / "items.json", json.dumps([
        {"title": "First", "text": "alpha text", "source": "s1", "kind": "archetype", "tags": ["a", "b"], "url": "u"},
        {"text": "second text", "tags": "x, y"},
        {"title": "empty", "text": "   "},
    ]))
    _write(tmp_path / "lines.jsonl", '{"title": "L1", "text": "line one"}\n\n{"title": "L2", "text": "line two", "kind": "antipattern"}\n')
    docs = {d.id: d for d in load_corpus([tmp_path])}
    assert sorted(docs) == ["items__1", "items__2", "lines__1", "lines__2"]
    first = docs["items__1"]
    assert first.title == "First" and first.text == "alpha text" and first.source == "s1"
    assert first.metadata == {"url": "u", "tags": ["a", "b"], "kind": "archetype"}
    assert docs["items__2"].title == "items 2" and docs["items__2"].metadata == {"tags": ["x", "y"], "kind": "guidance"}
    assert docs["lines__2"].metadata["kind"] == "antipattern"


def test_later_dir_wins_with_warning_and_missing_dir_is_skipped(tmp_path, capsys):
    _write(tmp_path / "one" / "a.md", "# A1\n\nfirst")
    _write(tmp_path / "one" / "b.md", "# B\n\nonly here")
    _write(tmp_path / "two" / "a.md", "# A2\n\nsecond")
    docs = load_corpus([tmp_path / "one", tmp_path / "missing", tmp_path / "two"])
    assert [(d.id, d.title) for d in docs] == [("a", "A2"), ("b", "B")]
    err = capsys.readouterr().err
    assert "duplicate document id 'a'" in err and "corpus dir not found" in err
    assert load_corpus([]) == []
