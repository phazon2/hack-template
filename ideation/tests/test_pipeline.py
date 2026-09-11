"""IdeationSystem facade: e2e under the mock, judge/learn/probe, index lifecycle, persistence (DESIGN §11, §17)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ideate import __version__
from ideate.agents.context import is_canonical_tag
from ideate.agents.creativity import diverse, validate_idea
from ideate.config import Settings
from ideate.evaluation.rubric import Rubric
from ideate.knowledge.retriever import KnowledgeBase
from ideate.llm.base import LLMConfigError, LLMRequest, LLMResponse
from ideate.llm.mock import MockLLM
from ideate.meta.ingest import ingest_into
from ideate.models import PROBLEM_TYPES, TECHNIQUES, HackathonConstraints, Idea, IdeationResult, Outcome, Pattern
from ideate.pipeline import IdeationSystem, receipt_stamp, result_from_state, state_from_result
from ideate.report import PLACEHOLDER_BANNER

THEME = "AI for climate resilience"
FIXED_NOW = "2026-01-02T03:04:05+00:00"


def fixed_now() -> str:
    return FIXED_NOW


@pytest.fixture
def system(settings):
    return IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    """One default-mock run shared by the read-only e2e assertions."""
    root = tmp_path_factory.mktemp("e2e")
    settings = Settings(
        provider="mock",
        index_dir=str(root / "index"),
        memory_path=str(root / "memory.jsonl"),
        runs_dir=str(root / "runs"),
        receipts_dir=str(root / "receipts"),
        meta_path=str(root / "meta.jsonl"),
        # Isolated too: these default to the repo's own .ideate/, which now carries
        # committed corpus material, and a test must never read it.
        fetched_dir=str(root / "fetched"),
        charter_path=str(root / "charter.md"),
    )
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    return settings, system, system.ideate(THEME, HackathonConstraints())


class FakeRealLLM:
    """A non-mock provider that answers the probe without any network."""

    provider = "anthropic"
    model = "claude-opus-5"

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            text='{"ok": true, "model_self_report": "opus"}',
            data={"ok": True, "model_self_report": "opus"},
            provider="anthropic",
            model="claude-opus-4-8",
            requested_model=self.model,
            input_tokens=11,
            output_tokens=7,
            message_id="msg_1",
            request_id="req_1",
            stop_reason="end_turn",
            fallback_ran=True,
        )


# --------------------------------------------------------------------------- e2e
def test_e2e_default_mock(e2e):
    settings, _, result = e2e
    assert isinstance(result, IdeationResult)
    # Loop rule B now honours the strategist's planned rounds (DESIGN-META §18.3).
    assert 1 <= result.iterations <= settings.max_iterations
    # Conservation law, not a raw count: every generated idea is either kept or dropped as a
    # near-duplicate by the Jaccard filter, and how many collide depends on the generated text.
    assert (
        len(result.ideas) == settings.ideas_per_round * result.iterations - result.dropped_duplicate
    )
    ids = [i.id for i in result.ideas]
    assert len(set(ids)) == len(ids)
    assert {v.idea_id for v in result.verdicts} == set(ids) and len(result.verdicts) == len(ids)
    assert sorted(result.ranking) == sorted(ids)
    assert result.proposal is not None and result.proposal.idea_id == result.ranking[0]
    assert result.is_placeholder is True and result.provider == "mock" and result.model == "mock-1"
    assert len(result.trace) == (
        int(settings.strategist) + 1 + result.retrieval_rounds + 1
        + result.iterations * (3 + len(settings.judge_personas)) + 1 + int(settings.reflector)
    )
    assert all(is_canonical_tag(t.agent) for t in result.trace)
    assert all(t.error is None for t in result.trace)
    assert all(len(i.citations) >= 1 for i in result.ideas)
    assert all(validate_idea(i, result.constraints) == [] for i in result.ideas)
    assert diverse(result.ideas, []) == result.ideas


def test_e2e_result_metadata(e2e):
    settings, _, result = e2e
    assert result.version == __version__
    assert result.created_at == FIXED_NOW and len(result.run_id) == 12
    assert result.theme == THEME and result.settings == settings.to_dict()
    assert result.queries and result.queries[0] == THEME
    assert result.research is not None and result.assessment is not None
    assert result.retrieval_rounds >= 1 and len(result.coverage_gaps) == 2
    assert result.knowledge and all(rc.chunk.metadata.get("kind") != "memory" for rc in result.knowledge)
    assert all(t.started_at == FIXED_NOW for t in result.trace)


def test_from_state_is_attached_to_the_result_class():
    assert IdeationResult.from_state is result_from_state


def test_ideate_defaults_constraints(system):
    result = system.ideate(THEME)
    assert result.constraints == HackathonConstraints()


def test_ideate_with_llm_reranker_traces_rerank_calls(settings):
    settings.reranker = "llm"
    result = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now).ideate(THEME)
    assert any(t.agent == "rerank" for t in result.trace)
    assert all(is_canonical_tag(t.agent) for t in result.trace)
    assert result.proposal is not None and result.proposal.idea_id == result.ranking[0]


def test_ideate_with_reranker_none_still_completes(settings):
    settings.reranker = "none"
    result = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now).ideate(THEME)
    assert not any(t.agent == "rerank" for t in result.trace)
    # The exact count is theme/prompt dependent under the mock (diversity filter); see the agents owner's notes.
    assert (
        len(result.ideas) + result.dropped_duplicate
        == settings.ideas_per_round * result.iterations
    )
    assert sorted(result.ranking) == sorted(i.id for i in result.ideas)


# --------------------------------------------------------------------------- judge
def test_judge_assigns_ids_and_ranks_everything(system):
    ideas = [Idea(title="Flood alert bot", description="warns farmers"), Idea(title="Heat map", description="maps heat islands", id="custom")]
    verdicts, ranking = system.judge(ideas, "climate", HackathonConstraints(judging_criteria=["innovation:40", "impact:30", "demo:30"]))
    assert [i.id for i in ideas] == ["idea-0-1", "custom"]
    assert sorted(ranking) == sorted(["idea-0-1", "custom"])
    assert [v.idea_id for v in verdicts] == ["idea-0-1", "custom"]
    assert all(len(v.evaluations) == len(system.settings.judge_personas) for v in verdicts)
    assert all(v.consensus.judge == "consensus" for v in verdicts)
    names = {s.name for s in verdicts[0].consensus.scores}
    assert names == {"novelty", "impact", "demoability", "feasibility"}
    assert len(system.llm.calls) == len(system.settings.judge_personas)


# --------------------------------------------------------------------------- learn
def test_learn_persists_outcome_and_mock_patterns(system, settings):
    outcome = Outcome(hackathon="ClimateHack", idea_title="Flood alert bot", success=True)
    patterns = system.learn(outcome)
    assert patterns and all(isinstance(p, Pattern) and p.provider == "mock" for p in patterns)
    assert all(p.source_outcome_id == outcome.id and p.created_at == FIXED_NOW for p in patterns)
    assert all("ClimateHack" in p.tags for p in patterns)
    assert outcome.recorded_at == FIXED_NOW
    assert Path(settings.memory_path).exists()
    assert [o.id for o in system.memory.outcomes()] == [outcome.id]
    assert system.memory.patterns() == []
    assert [p.id for p in system.memory.patterns(include_mock=True)] == [p.id for p in patterns]


# --------------------------------------------------------------------------- probe
def test_probe_under_mock_raises_config_error_before_touching_files(system, settings):
    with pytest.raises(LLMConfigError) as info:
        system.probe()
    assert info.value.kind == "config-fixable"
    assert info.value.message == "probe requires a real provider; current provider is mock"
    assert "IDEATE_PROVIDER=anthropic" in info.value.hint
    assert not Path(settings.receipts_dir).exists()
    assert not Path(settings.index_dir).exists()
    assert not Path(settings.memory_path).exists()
    assert not Path(settings.runs_dir).exists()
    assert system.llm.calls == []


def test_probe_with_real_provider_makes_one_call_and_returns_receipt(settings):
    llm = FakeRealLLM()
    system = IdeationSystem(settings, llm=llm, now=fixed_now)
    receipt = system.probe()
    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call.tag == "probe" and call.effort == settings.effort_light
    assert call.json_schema["properties"].keys() == {"ok", "model_self_report"}
    assert receipt == {
        "provider": "anthropic",
        "requested_model": "claude-opus-5",
        "served_model": "claude-opus-4-8",
        "fallback_ran": True,
        "message_id": "msg_1",
        "request_id": "req_1",
        "input_tokens": 11,
        "output_tokens": 7,
        "stop_reason": "end_turn",
        "timestamp": FIXED_NOW,
    }
    path = system.save_receipt(receipt)
    assert path == Path(settings.receipts_dir) / "probe-20260102T030405Z.json"
    assert json.loads(path.read_text()) == receipt


def test_save_receipt_refuses_mock_receipts(system, settings):
    with pytest.raises(ValueError):
        system.save_receipt({"provider": "mock", "timestamp": FIXED_NOW})
    assert not Path(settings.receipts_dir).exists()


def test_receipt_stamp_normalises_to_utc():
    assert receipt_stamp("2026-01-02T05:04:05+02:00") == "20260102T030405Z"
    assert receipt_stamp("2026-01-02T03:04:05") == "20260102T030405Z"


# --------------------------------------------------------------------------- save_run
def test_save_run_layout(e2e):
    settings, system, result = e2e
    run_dir = system.save_run(result)
    assert run_dir == Path(settings.runs_dir) / result.run_id
    assert sorted(p.name for p in run_dir.iterdir()) == ["report.md", "result.json"]
    data = json.loads((run_dir / "result.json").read_text())
    assert data["run_id"] == result.run_id and data["placeholder_notice"] == PLACEHOLDER_BANNER
    assert IdeationResult.from_dict(data).to_dict() == result.to_dict()
    report = (run_dir / "report.md").read_text()
    assert report.splitlines()[0] == f"> **{PLACEHOLDER_BANNER}**"


# --------------------------------------------------------------------------- index lifecycle
def write_doc(corpus: Path, text: str) -> None:
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "extra.md").write_text(f"---\ntitle: Extra\nkind: guidance\n---\n# Extra\n\n{text}\n", encoding="utf-8")


def test_load_or_build_index_builds_then_loads(system, settings, capsys, monkeypatch):
    kb1 = system.load_or_build_index()
    assert "index rebuilt" in capsys.readouterr().err
    assert (Path(settings.index_dir) / "meta.json").exists()
    monkeypatch.setattr("ideate.pipeline.KnowledgeBase.build", lambda *a, **k: pytest.fail("rebuilt an unchanged index"))
    kb2 = system.load_or_build_index()
    assert "index rebuilt" not in capsys.readouterr().err
    assert kb2.stats() == kb1.stats()
    assert kb2.corpus_fingerprint == kb1.corpus_fingerprint
    assert kb2.bm25_weight == settings.bm25_weight and kb2.rrf_k == settings.rrf_k
    assert kb2.retrieve("demo strategy", k=3)[0].chunk.id == kb1.retrieve("demo strategy", k=3)[0].chunk.id


def test_load_or_build_index_rebuilds_on_fingerprint_mismatch(settings, tmp_path, capsys):
    corpus = tmp_path / "corpus"
    write_doc(corpus, "Flood sensors on bridges report river levels.")
    settings.corpus_dirs = [str(corpus)]
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    before = system.load_or_build_index().stats()
    write_doc(corpus, "Flood sensors on bridges report river levels every minute.")
    capsys.readouterr()
    after = system.load_or_build_index().stats()
    assert "index rebuilt" in capsys.readouterr().err
    assert after["n_docs"] == before["n_docs"]
    meta = json.loads((Path(settings.index_dir) / "meta.json").read_text())
    assert meta["corpus_fingerprint"] == system.load_or_build_index().corpus_fingerprint


@pytest.mark.parametrize(
    "change",
    [
        {"chunk_size": 400},
        {"chunk_overlap": 60},
        {"embedding_dim": 64},
    ],
)
def test_load_or_build_index_rebuilds_when_settings_differ(settings, capsys, change):
    IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now).load_or_build_index()
    capsys.readouterr()
    changed = replace(settings, **change)
    kb = IdeationSystem(changed, llm=MockLLM(seed=0), now=fixed_now).load_or_build_index()
    assert "index rebuilt" in capsys.readouterr().err
    meta = json.loads((Path(settings.index_dir) / "meta.json").read_text())
    assert meta["chunk_size"] == changed.chunk_size and meta["chunk_overlap"] == changed.chunk_overlap
    assert meta["embedder"]["dim"] == changed.embedding_dim == kb.stats()["dim"]


def test_load_or_build_index_rebuilds_on_bad_format_version(system, settings, capsys):
    system.load_or_build_index()
    meta_path = Path(settings.index_dir) / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["format_version"] = 99
    meta_path.write_text(json.dumps(meta))
    capsys.readouterr()
    system.load_or_build_index()
    assert "index rebuilt" in capsys.readouterr().err
    assert json.loads(meta_path.read_text())["format_version"] == 1


def test_build_index_force_rebuilds(system, settings, capsys):
    system.build_index()
    capsys.readouterr()
    system.build_index(force=True)
    assert "index rebuilt" in capsys.readouterr().err
    assert json.loads((Path(settings.index_dir) / "meta.json").read_text())["built_at"] == FIXED_NOW


def test_build_index_with_empty_corpus(settings):
    settings.bundled_corpus = False
    kb = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now).build_index()
    assert kb.stats()["n_docs"] == 0 and kb.stats()["n_chunks"] == 0
    assert kb.retrieve("anything") == []


def test_ideate_indexes_mock_patterns_only_under_the_mock(settings, monkeypatch):
    """A mock run indexes mock + real patterns; a real-provider run would see only the real one."""
    indexed: list[list[str]] = []

    def record(self, patterns):
        indexed.append([p.text for p in patterns])
        return len(patterns)

    monkeypatch.setattr(KnowledgeBase, "add_memory_patterns", record)
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    system.memory.add_pattern(Pattern(kind="success", text="ship a public url first", tags=["deploy"], provider="mock"))
    system.memory.add_pattern(Pattern(kind="failure", text="never depend on an account", tags=["accounts"], provider="anthropic"))
    result = system.ideate(THEME)
    assert result.is_placeholder and result.proposal is not None
    assert indexed == [["ship a public url first", "never depend on an account"]]
    assert [p.text for p in system.memory.patterns()] == ["never depend on an account"]


# --------------------------------------------------------------------------- meta layer (DESIGN-META §18.8)
RULES_TEXT = (
    "# Team operating rules\n\n"
    "Ship a public URL before hour nine of the hackathon. Never drive a signup, 2FA or SSO flow: "
    "the human creates every account.\n\n"
    "Mock output is never evidence. A receipt only counts when it comes from a real probe.\n"
)


def write_rules(tmp_path: Path, text: str = RULES_TEXT) -> Path:
    path = tmp_path / "CLAUDE.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_result_carries_the_strategy_and_the_reflection(e2e):
    _, _, result = e2e
    assert result.strategy is not None and result.reflection is not None
    assert result.strategy.problem_type in PROBLEM_TYPES
    assert 2 <= len(result.strategy.emphasis_techniques) <= 4
    assert result.reflection.run_id == result.run_id and result.reflection.theme == THEME
    assert result.reflection.provider == "mock" and result.reflection.created_at == FIXED_NOW
    assert result.reflection.process_changes and result.reflection.what_worked
    # The round trip through JSON keeps both (they are ordinary result fields).
    assert IdeationResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_a_run_writes_quarantined_meta_memory(e2e):
    _, system, result = e2e
    assert system.meta.reflections() == [], "mock reflections must not reach a real run"
    quarantined = system.meta.reflections(include_mock=True)
    assert [r.run_id for r in quarantined][-1:] == [result.run_id]
    assert system.meta.meta_patterns() == []
    written = system.meta_patterns_for(result.run_id, include_mock=True)
    assert written and all(p.source_run_id == result.run_id and p.provider == "mock" for p in written)
    assert system.meta_patterns_for("no-such-run", include_mock=True) == []


def test_run_without_the_meta_layer_keeps_the_baseline_shape(settings):
    settings.strategist = False
    settings.reflector = False
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    result = system.ideate(THEME)
    assert result.strategy is None and result.reflection is None
    assert result.iterations == settings.max_iterations
    assert len(result.trace) == (
        1 + result.retrieval_rounds + 1 + result.iterations * (3 + len(settings.judge_personas)) + 1
    )
    assert not any(t.agent in ("strategist", "reflector") for t in result.trace)
    assert len(system.meta) == 0 and not Path(settings.meta_path).exists()


def test_strategy_is_one_strategist_call(settings):
    llm = MockLLM(seed=0)
    system = IdeationSystem(settings, llm=llm, now=fixed_now)
    strategy = system.strategy(THEME, HackathonConstraints(judging_criteria=["innovation:60", "demo:40"]))
    assert [c.tag for c in llm.calls] == ["strategist"]
    assert strategy.problem_type in PROBLEM_TYPES
    assert 2 <= len(strategy.emphasis_techniques) <= 4
    assert all(t in TECHNIQUES for t in strategy.emphasis_techniques)
    assert 0 <= strategy.rounds <= settings.max_iterations
    assert set(strategy.rubric_emphasis) <= set(Rubric.from_judging_criteria(["innovation:60", "demo:40"]).names())
    assert all(0.5 <= m <= 2.0 for m in strategy.rubric_emphasis.values())
    assert system.strategy(THEME).to_dict() == system.strategy(THEME).to_dict()


def test_reflect_reruns_the_reflector_over_a_saved_run(settings):
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    result = system.ideate(THEME)
    system.save_run(result)
    before = len(system.meta.reflections(include_mock=True))
    known = {p.id for p in system.meta.meta_patterns(include_mock=True)}
    reflection = system.reflect(result.run_id)
    assert reflection.run_id == result.run_id and reflection.theme == THEME
    assert reflection.created_at == FIXED_NOW and reflection.provider == "mock"
    assert len(system.meta.reflections(include_mock=True)) == before + 1
    added = [p for p in system.meta.meta_patterns(include_mock=True) if p.id not in known]
    assert added and all(p.source_run_id == result.run_id and p.observations == 1 for p in added)

    # Reflecting on the same saved run again is the same prompt, so the patterns merge, not duplicate.
    system.reflect(result.run_id)
    stored = {p.id: p for p in system.meta.meta_patterns(include_mock=True)}
    assert set(stored) == known | {p.id for p in added}
    assert all(stored[p.id].observations == 2 and stored[p.id].confidence == 0.7 for p in added)
    assert all(stored[pid].observations == 1 for pid in known)


def test_reflect_on_an_unknown_run_is_a_named_error(settings):
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    with pytest.raises(ValueError) as info:
        system.reflect("nope")
    assert "run 'nope' not found" in str(info.value)


def test_documents_include_registered_memory_sources(settings, tmp_path):
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    plain = len(system._documents())
    source, documents = ingest_into(write_rules(tmp_path), system.meta)
    assert source.format == "rules" and source.n_documents == 1
    combined = system._documents()
    assert len(combined) == plain + 1
    assert [d.id for d in documents][0] in [d.id for d in combined]
    ingested = next(d for d in combined if d.id.startswith("src-"))
    assert ingested.metadata["kind"] == "rules" and ingested.metadata["memory_source"] == source.id


def test_ingesting_new_material_invalidates_the_index(settings, tmp_path, capsys):
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    before = system.load_or_build_index()
    capsys.readouterr()
    assert system.load_or_build_index().corpus_fingerprint == before.corpus_fingerprint
    assert "index rebuilt" not in capsys.readouterr().err

    rules = write_rules(tmp_path)
    ingest_into(rules, system.meta)
    after = system.load_or_build_index()
    assert "index rebuilt" in capsys.readouterr().err
    assert after.corpus_fingerprint != before.corpus_fingerprint
    assert after.stats()["n_docs"] == before.stats()["n_docs"] + 1
    assert any(rc.chunk.id.startswith("src-") for rc in after.retrieve("public URL signup 2FA account", k=8))

    rules.write_text(RULES_TEXT + "\nAlways state whether a blocker is config-fixable.\n", encoding="utf-8")
    ingest_into(rules, system.meta)
    capsys.readouterr()
    changed = system.load_or_build_index()
    assert "index rebuilt" in capsys.readouterr().err
    assert changed.corpus_fingerprint != after.corpus_fingerprint


def test_a_vanished_memory_source_is_skipped_with_a_warning(settings, tmp_path, capsys):
    system = IdeationSystem(settings, llm=MockLLM(seed=0), now=fixed_now)
    rules = write_rules(tmp_path)
    source, _ = ingest_into(rules, system.meta)
    rules.unlink()
    capsys.readouterr()
    documents = system._documents()
    assert f"memory source {source.id} skipped" in capsys.readouterr().err
    assert not any(d.id.startswith("src-") for d in documents)


def test_state_from_result_round_trips_the_run(e2e):
    _, _, result = e2e
    state = state_from_result(result)
    assert state.theme == result.theme and state.constraints == result.constraints
    assert [i.id for i in state.ideas] == [i.id for i in result.ideas]
    assert state.ranking == result.ranking and state.iteration == result.iterations
    assert state.retrieval_rounds == result.retrieval_rounds
    assert state.strategy == result.strategy and state.reflection == result.reflection
