"""learn_from_outcome and memory_context_for (docs/DESIGN.md §10)."""

from __future__ import annotations

from ideate.improvement.feedback import LEARN_SCHEMA, learn_from_outcome, memory_context_for
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import Outcome, Pattern


def outcome() -> Outcome:
    return Outcome(hackathon="ClimateHack 2026", idea_title="Flood alert for river wardens", success=True, placed="2nd", judge_feedback="demo landed", what_was_cut="map view")


def test_learn_schema_shape():
    props = LEARN_SCHEMA["properties"]["patterns"]
    assert (props["minItems"], props["maxItems"]) == (1, 6)
    assert props["items"]["properties"]["kind"]["enum"] == ["success", "failure"]
    assert (props["items"]["properties"]["tags"]["minItems"], props["items"]["properties"]["tags"]["maxItems"]) == (1, 5)


def test_learn_from_outcome_persists_outcome_and_patterns(tmp_path):
    mock = MockLLM(seed=0)
    memory = MemoryStore(tmp_path / "memory.jsonl")
    o = outcome()
    patterns = learn_from_outcome(o, mock, memory, now=lambda: "2026-02-02T00:00:00+00:00")
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.tag == "learn" and call.effort == "medium" and call.json_schema == LEARN_SCHEMA
    assert "ClimateHack 2026" in call.prompt and "demo landed" in call.prompt and "map view" in call.prompt
    assert len(patterns) == 2
    for p in patterns:
        assert p.provider == "mock"
        assert p.created_at == "2026-02-02T00:00:00+00:00"
        assert p.source_outcome_id == o.id
        assert "ClimateHack 2026" in p.tags
        assert p.kind in ("success", "failure") and p.text.startswith("[mock]")
        assert p.id.startswith("pat-")
    assert o.recorded_at == "2026-02-02T00:00:00+00:00"
    assert [x.id for x in memory.outcomes()] == [o.id]
    assert memory.patterns() == []  # mock patterns are quarantined
    assert [p.id for p in memory.patterns(include_mock=True)] == [p.id for p in patterns]


def test_learn_from_outcome_does_not_duplicate_outcome(tmp_path):
    memory = MemoryStore(tmp_path / "memory.jsonl")
    o = outcome()
    learn_from_outcome(o, MockLLM(seed=0), memory)
    learn_from_outcome(o, MockLLM(seed=1), memory)
    assert len(memory.outcomes()) == 1
    assert len(memory.patterns(include_mock=True)) == 4


def test_learn_from_outcome_scripted_tags_get_hackathon_appended(tmp_path):
    scripted = {"learn": [{"patterns": [{"kind": "failure", "text": "cut the map first", "tags": ["scope"]}]}]}
    memory = MemoryStore(tmp_path / "memory.jsonl")
    patterns = learn_from_outcome(outcome(), MockLLM(scripted=scripted), memory)
    assert len(patterns) == 1
    assert patterns[0].tags == ["scope", "ClimateHack 2026"] and patterns[0].kind == "failure"


def test_memory_context_for_empty_and_mock_quarantine(tmp_path):
    memory = MemoryStore(tmp_path / "memory.jsonl")
    assert memory_context_for("flood alerts", memory) == ""
    memory.add_pattern(Pattern("success", "flood gauge demo landed in a minute", tags=["flood"], provider="mock"))
    assert memory_context_for("flood gauge demo", memory) == ""
    assert memory_context_for("flood gauge demo", memory, include_mock=True) == "- Leverage: flood gauge demo landed in a minute"
    memory.add_pattern(Pattern("failure", "flood map view was never finished", tags=["flood"], provider="anthropic"))
    assert memory_context_for("flood map", memory) == "- Avoid: flood map view was never finished"
    both = memory_context_for("flood", memory, include_mock=True)
    assert "- Leverage: flood gauge demo landed in a minute" in both and "- Avoid: flood map view was never finished" in both
    assert memory_context_for("unrelated topic entirely", memory, include_mock=True) == ""
    assert memory_context_for("flood", memory, k=0, include_mock=True) == ""
