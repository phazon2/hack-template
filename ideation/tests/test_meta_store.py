"""MetaStore JSONL shapes, merge-on-write and quarantine, plus the new models (DESIGN-META §18.1/§18.2)."""

from __future__ import annotations

import json

import pytest

from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.meta.store import MetaStore
from ideate.models import (
    ALL_MODELS,
    CHUNK_KINDS,
    META_PATTERN_KINDS,
    PROBLEM_TYPES,
    TECHNIQUES,
    IdeationResult,
    IdeationState,
    MemorySource,
    MetaPattern,
    RunReflection,
    Strategy,
    sha256_hex,
)


@pytest.fixture
def store(tmp_path) -> MetaStore:
    return MetaStore(tmp_path / "nested" / "dir" / "meta.jsonl")


def _pattern(text: str, scope: str = "global", provider: str = "anthropic", **kw) -> MetaPattern:
    base = dict(kind="strategy", text=text, tags=["retrieval"], source_run_id="run-1", provider=provider, created_at="2026-01-01T00:00:00Z", scope=scope)
    base.update(kw)
    return MetaPattern(**base)


def _reflection(provider: str = "anthropic", run_id: str = "run-1") -> RunReflection:
    return RunReflection(
        run_id=run_id,
        theme="urban mobility",
        created_at="2026-01-01T00:00:00Z",
        provider=provider,
        what_worked=["the walking skeleton came first"],
        process_changes=["retrieve twice before generating"],
    )


# --------------------------------------------------------------------------- models
def test_new_models_are_registered_and_round_trip():
    for model in (Strategy, RunReflection, MetaPattern, MemorySource):
        assert model in ALL_MODELS
    pattern = _pattern("prefer one strong angle over four weak ones")
    assert MetaPattern.from_dict(pattern.to_dict()) == pattern
    reflection = _reflection()
    assert RunReflection.from_dict(reflection.to_dict()) == reflection
    source = MemorySource(id="", path="/tmp/notes.md", n_documents=2)
    assert MemorySource.from_dict(source.to_dict()) == source


def test_chunk_kinds_and_new_tuples():
    for kind in ("meta", "memory-source", "rules"):
        assert kind in CHUNK_KINDS
    assert PROBLEM_TYPES == ("greenfield", "constrained", "integration", "data", "social", "unclear")
    assert META_PATTERN_KINDS == ("strategy", "process", "pitfall")


def test_ids_are_content_addressed_and_stable():
    a = MetaPattern(kind="process", text="write the demo script first", scope="greenfield")
    b = MetaPattern(kind="pitfall", text="write the demo script first", scope="greenfield")
    assert a.id == b.id == f"meta-{sha256_hex('greenfield|write the demo script first')[:12]}"
    assert MetaPattern(kind="process", text="write the demo script first").id != a.id
    assert MetaPattern(kind="process", text="x", id="meta-fixed").id == "meta-fixed"
    assert MemorySource(id="", path="/a/b.md").id == f"src-{sha256_hex('/a/b.md')[:12]}"
    assert MemorySource(id="src-given", path="/a/b.md").id == "src-given"


def test_state_and_result_carry_strategy_and_reflection():
    state = IdeationState(theme="t", constraints=None)
    assert (state.strategy, state.reflection, state.dropped_invalid, state.dropped_duplicate) == (None, None, 0, 0)
    result = IdeationResult(run_id="r", created_at="c", version="v", theme="t", constraints=None, provider="mock", model="m")
    assert (result.strategy, result.reflection) == (None, None)
    rebuilt = IdeationResult.from_dict({**result.to_dict(), "strategy": {"rounds": 2}, "reflection": {"run_id": "r"}})
    assert rebuilt.strategy == Strategy(rounds=2)
    assert rebuilt.reflection == RunReflection(run_id="r")


def test_settings_gain_the_meta_layer_flags():
    s = Settings()
    assert (s.meta_path, s.strategist, s.reflector, s.meta_k) == (".ideate/meta.jsonl", True, True, 6)


# --------------------------------------------------------------------------- Strategy.sanitized
def test_sanitized_clamps_every_field():
    settings = Settings(max_iterations=2)
    strategy = Strategy(
        framing="see it as a routing problem",
        problem_type="wildly-unknown",
        emphasis_techniques=["reverse", "reverse", "telepathy", "scale", "combination", "direct", "analogical"],
        retrieval_angles=["a", "b", "c", "d", "e"],
        rubric_emphasis={"novelty": 5.0, "feasibility": 0.1, "impact": "high", "made_up": 1.5, "demoability": 1.25},
        rounds=9,
        watch_for=["1", "2", "3", "4", "5", "6"],
        rationale="because",
        source_patterns=["meta-1"],
    )
    clean = strategy.sanitized(settings, DEFAULT_RUBRIC)
    assert clean.problem_type == "unclear"
    assert clean.emphasis_techniques == ["reverse", "scale", "combination", "direct"]
    assert clean.retrieval_angles == ["a", "b", "c", "d"]
    assert clean.rubric_emphasis == {"novelty": 2.0, "feasibility": 0.5, "demoability": 1.25}
    assert clean.rounds == 2
    assert clean.watch_for == ["1", "2", "3", "4", "5"]
    assert (clean.framing, clean.rationale, clean.source_patterns) == (strategy.framing, "because", ["meta-1"])
    assert strategy.rubric_emphasis["novelty"] == 5.0 and strategy.rounds == 9  # never mutated


def test_sanitized_defaults_and_rounds_zero():
    settings = Settings(max_iterations=3)
    clean = Strategy(problem_type="data", emphasis_techniques=["nope"], rounds=0).sanitized(settings, DEFAULT_RUBRIC)
    assert clean.emphasis_techniques == list(TECHNIQUES[:3])
    assert clean.problem_type == "data"
    assert clean.rounds == 0  # 0 means "use settings"
    assert Strategy(rounds=-4).sanitized(settings, DEFAULT_RUBRIC).rounds == 1
    assert Strategy(rounds=3).sanitized(settings, DEFAULT_RUBRIC).rounds == 3


def test_sanitized_takes_duck_typed_settings_and_rubric():
    class _Settings:
        max_iterations = 1

    class _Rubric:
        def names(self):
            return ["speed"]

    clean = Strategy(rubric_emphasis={"speed": 1.5, "novelty": 2.0, "flag": True}, rounds=7).sanitized(_Settings(), _Rubric())
    assert clean.rubric_emphasis == {"speed": 1.5}
    assert clean.rounds == 1


# --------------------------------------------------------------------------- store io
def test_missing_file_is_empty(store):
    assert len(store) == 0
    assert store.reflections() == []
    assert store.meta_patterns() == []
    assert store.sources() == []
    assert store.source_for("/anywhere") is None
    assert store.relevant_meta_patterns("anything") == []
    assert not store.path.exists()


def test_record_shapes_and_parent_dirs(store):
    reflection = _reflection()
    pattern = _pattern("retrieve before you generate")
    source = MemorySource(id="", path="/tmp/notes.md", format="markdown")
    store.add_reflection(reflection)
    store.add_meta_pattern(pattern)
    store.add_source(source)
    lines = store.path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"type": "reflection", **reflection.to_dict()}
    assert json.loads(lines[1]) == {"type": "meta_pattern", **pattern.to_dict()}
    assert json.loads(lines[2]) == {"type": "memory_source", **source.to_dict()}
    assert len(store) == 3
    assert store.reflections() == [reflection]
    assert store.meta_patterns() == [pattern]
    assert store.sources() == [source]
    assert store.source_for("/tmp/notes.md") == source


def test_unknown_and_malformed_lines_are_skipped_with_a_warning(store, capsys):
    store.add_meta_pattern(_pattern("good line"))
    with store.path.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "banana", "id": "x"}\n')
        fh.write("not json at all\n")
    assert [p.text for p in store.meta_patterns()] == ["good line"]
    err = capsys.readouterr().err
    assert "unknown record type 'banana'" in err
    assert "not valid JSON" in err


def test_clear_removes_the_file(store):
    store.add_meta_pattern(_pattern("something"))
    store.clear()
    assert not store.path.exists()
    assert store.meta_patterns() == []


# --------------------------------------------------------------------------- merge-on-write
def test_merge_on_write_bumps_observations_and_confidence_without_duplicating(store):
    pattern = _pattern("retrieval twice beats retrieval once")
    first = store.add_meta_pattern(pattern)
    assert (first.observations, first.confidence) == (1, 0.5)
    second = store.add_meta_pattern(_pattern("retrieval twice beats retrieval once", source_run_id="run-2"))
    assert (second.observations, second.confidence) == (2, 0.7)
    third = store.add_meta_pattern(_pattern("retrieval twice beats retrieval once"))
    assert (third.observations, third.confidence) == (3, 0.82)
    stored = store.meta_patterns()
    assert len(stored) == 1
    assert stored[0].source_run_id == "run-1"  # the stored copy wins; nothing is fabricated
    assert len(store.path.read_text(encoding="utf-8").splitlines()) == 1


def test_merge_confidence_is_capped(store):
    pattern = _pattern("cap me")
    for _ in range(9):
        merged = store.add_meta_pattern(pattern)
    assert merged.confidence == 0.95
    assert merged.observations == 9


def test_merge_preserves_line_order(store):
    for text in ("first", "second", "third"):
        store.add_meta_pattern(_pattern(text))
    store.add_meta_pattern(_pattern("first"))
    texts = [json.loads(line)["text"] for line in store.path.read_text(encoding="utf-8").splitlines()]
    assert texts == ["first", "second", "third"]
    assert [p.observations for p in store.meta_patterns()] == [2, 1, 1]


def test_add_source_replaces_the_same_id_in_place(store):
    store.add_source(MemorySource(id="", path="/tmp/a.md", n_documents=1))
    store.add_source(MemorySource(id="", path="/tmp/b.md", n_documents=1))
    store.add_source(MemorySource(id="", path="/tmp/a.md", n_documents=7))
    assert [(s.path, s.n_documents) for s in store.sources()] == [("/tmp/a.md", 7), ("/tmp/b.md", 1)]


# --------------------------------------------------------------------------- filters and ranking
def test_kind_and_scope_filters(store):
    store.add_meta_pattern(_pattern("a", kind="strategy", scope="global"))
    store.add_meta_pattern(_pattern("b", kind="pitfall", scope="data"))
    assert [p.text for p in store.meta_patterns(kind="pitfall")] == ["b"]
    assert [p.text for p in store.meta_patterns(scope="global")] == ["a"]
    assert [p.text for p in store.meta_patterns(kind="strategy", scope="data")] == []


def test_mock_reflections_and_patterns_are_quarantined(store):
    store.add_reflection(_reflection(provider="mock", run_id="run-mock"))
    store.add_reflection(_reflection(provider="anthropic", run_id="run-real"))
    store.add_meta_pattern(_pattern("mock lesson about retrieval", provider="mock"))
    store.add_meta_pattern(_pattern("real lesson about retrieval", provider="anthropic"))
    assert [r.run_id for r in store.reflections()] == ["run-real"]
    assert [r.run_id for r in store.reflections(include_mock=True)] == ["run-mock", "run-real"]
    assert [p.text for p in store.meta_patterns()] == ["real lesson about retrieval"]
    assert len(store.meta_patterns(include_mock=True)) == 2
    assert [p.text for p in store.relevant_meta_patterns("retrieval")] == ["real lesson about retrieval"]
    assert len(store.relevant_meta_patterns("retrieval", include_mock=True)) == 2


def test_relevant_meta_patterns_weights_by_confidence(store):
    store.add_meta_pattern(_pattern("query expansion helps sparse corpora", scope="global", confidence=0.5))
    store.add_meta_pattern(_pattern("query expansion helps sparse corpora", scope="data", confidence=0.9))
    ranked = store.relevant_meta_patterns("query expansion")
    assert [p.scope for p in ranked] == ["data", "global"]


def test_relevant_meta_patterns_break_ties_by_id_and_respect_k(store):
    for scope in ("global", "data", "social"):
        store.add_meta_pattern(_pattern("identical wording about judging", scope=scope, confidence=0.5))
    ranked = store.relevant_meta_patterns("judging", k=2)
    ids = sorted(p.id for p in store.meta_patterns())
    assert [p.id for p in ranked] == ids[:2]
    assert store.relevant_meta_patterns("judging", k=0) == []
    assert store.relevant_meta_patterns("nothing matches this text at all") == []
