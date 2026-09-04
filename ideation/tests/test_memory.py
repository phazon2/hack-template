"""MemoryStore: JSONL shapes, mock quarantine, BM25 relevance, malformed lines (DESIGN §7)."""

from __future__ import annotations

import json

import pytest

from ideate.memory.store import MemoryStore
from ideate.models import Outcome, Pattern


def _outcome(**kw) -> Outcome:
    base = dict(hackathon="hack-2026", idea_title="Pothole radar", id="out-1", recorded_at="2026-01-01T00:00:00Z")
    base.update(kw)
    return Outcome(**base)


def _pattern(text: str, provider: str = "anthropic", kind: str = "success", tags: list[str] | None = None, **kw) -> Pattern:
    return Pattern(kind=kind, text=text, tags=tags or ["hack-2026"], source_outcome_id="out-1", provider=provider, created_at="2026-01-01T00:00:00Z", **kw)


@pytest.fixture
def store(tmp_path) -> MemoryStore:
    return MemoryStore(tmp_path / "nested" / "dir" / "memory.jsonl")


def test_missing_file_is_empty(store):
    assert len(store) == 0
    assert store.outcomes() == []
    assert store.patterns() == []
    assert store.relevant_patterns("anything") == []
    assert not store.path.exists()


def test_jsonl_record_shapes_and_parent_dirs(store):
    o = _outcome()
    p = _pattern("ship the demo path first")
    store.add_outcome(o)
    store.add_pattern(p)
    assert store.path.exists()
    lines = store.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "outcome", **o.to_dict()}
    assert json.loads(lines[1]) == {"type": "pattern", **p.to_dict()}
    assert len(store) == 2


def test_round_trip_outcomes_and_patterns(store):
    o = _outcome(placed="2nd", success=True, demo_worked=True, run_id="r1", idea_id="idea-1-2")
    p = _pattern("record a fallback video", kind="failure", tags=["demo", "hack-2026"])
    store.add_outcome(o)
    store.add_pattern(p)
    assert store.outcomes() == [o]
    assert store.patterns() == [p]
    assert store.patterns(kind="failure") == [p]
    assert store.patterns(kind="success") == []


def test_mock_patterns_are_quarantined(store):
    real = _pattern("real lesson about demos")
    mock = _pattern("mock lesson about demos", provider="mock")
    store.add_pattern(real)
    store.add_pattern(mock)
    assert store.patterns() == [real]
    assert store.patterns(include_mock=True) == [real, mock]
    assert store.relevant_patterns("demos lesson") == [real]
    assert store.relevant_patterns("demos lesson", include_mock=True) == [real, mock]
    assert len(store) == 2


def test_relevant_patterns_ordering_and_k(store):
    weak = _pattern("scope down early and cut features", tags=["scope"])
    strong = _pattern("cut scope aggressively: scope is the enemy of scope", tags=["scope", "cut"])
    unrelated = _pattern("bring chargers and snacks", tags=["logistics"])
    for p in (weak, strong, unrelated):
        store.add_pattern(p)
    ranked = store.relevant_patterns("scope cut")
    assert [p.id for p in ranked] == [strong.id, weak.id]
    assert store.relevant_patterns("scope cut", k=1) == [strong]
    assert store.relevant_patterns("scope cut", k=0) == []
    assert store.relevant_patterns("scope cut", kind="failure") == []


def test_relevant_patterns_matches_on_tags(store):
    p = _pattern("use the public transit feed", tags=["transport", "gtfs"])
    store.add_pattern(_pattern("something else entirely", tags=["misc"]))
    store.add_pattern(p)
    assert store.relevant_patterns("gtfs") == [p]


def test_unknown_type_line_skipped_with_warning(store, capsys):
    store.add_outcome(_outcome())
    with store.path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "banana", "x": 1}) + "\n")
        fh.write("not json at all\n")
        fh.write("\n")
    store.add_pattern(_pattern("still readable"))
    assert len(store) == 2
    assert len(store.outcomes()) == 1
    assert len(store.patterns()) == 1
    err = capsys.readouterr().err
    assert "'banana'" in err
    assert "not valid JSON" in err
    assert capsys.readouterr().out == ""


def test_clear_removes_everything(store):
    store.add_outcome(_outcome())
    store.add_pattern(_pattern("x"))
    store.clear()
    assert len(store) == 0
    assert not store.path.exists()
    store.clear()  # idempotent
    store.add_pattern(_pattern("y"))
    assert len(store) == 1
