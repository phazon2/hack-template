"""OrchestratorAgent, RetrieveMoreAgent, the default graph and the end-to-end mock run (docs/DESIGN.md §9.3, §9.4, §17)."""

from __future__ import annotations

from ideate.agents.context import RunContext, TracingLLM, constraints_block, is_canonical_tag
from ideate.agents.creativity import diverse, validate_idea
from ideate.agents.graph import END
from ideate.agents.orchestrator import (
    MAX_KNOWLEDGE,
    MAX_KNOWLEDGE_AFTER_GAPS,
    ORCHESTRATOR_SCHEMA,
    OrchestratorAgent,
    RetrieveMoreAgent,
    after_evaluator,
    after_retrieve_more,
    build_default_graph,
    cap_knowledge,
    merge_best,
)
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import (
    Chunk,
    CriterionScore,
    HackathonConstraints,
    IdeaEvaluation,
    IdeationState,
    PanelVerdict,
    Pattern,
    ResearchFindings,
    RetrievedChunk,
)

THEME = "AI for climate resilience"


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def rc(id: str, score: float, kind: str = "guidance") -> RetrievedChunk:
    return RetrievedChunk(Chunk(id, id.split("#")[0], "text", 0, {"kind": kind, "title": id}), score)


def verdict(idea_id: str, weighted: float, disqualified: bool = False) -> PanelVerdict:
    consensus = IdeaEvaluation(idea_id, scores=[CriterionScore("novelty", weighted)], weighted_score=weighted, disqualified=disqualified, judge="consensus")
    return PanelVerdict(idea_id, [], consensus, 1.0)


def scripted_judge_entry(ids: list[str], score: float) -> dict:
    return {
        "evaluations": [
            {
                "idea_id": i,
                "scores": [{"name": n, "score": score, "rationale": "r"} for n in DEFAULT_RUBRIC.names()],
                "strengths": ["s"], "weaknesses": ["w"], "suggestions": ["g"], "risks": [],
                "closest_existing": "", "demo_break_risk": "", "disqualified": False, "disqualify_reason": "",
            }
            for i in ids
        ]
    }


# --------------------------------------------------------------------------- helpers
def test_merge_best_keeps_highest_score_per_id():
    merged = merge_best([rc("a#0", 0.2), rc("b#0", 0.5), rc("a#0", 0.9), rc("b#0", 0.5)])
    assert [(m.chunk.id, m.score) for m in merged] == [("a#0", 0.9), ("b#0", 0.5)]


def test_cap_knowledge_pins_event_and_data_source_and_sorts():
    extras = [rc("g#1", 0.1), rc("g#2", 0.9), rc("e#0", 0.0, "event"), rc("d#0", 0.05, "data-source"), rc("g#3", 0.5)]
    kept, added = cap_knowledge([], extras, 3)
    assert added == 3
    assert [k.chunk.id for k in kept] == ["g#2", "d#0", "e#0"]  # pinned survive; sorted by (-score, id)
    base = [rc("g#2", 0.9)]
    kept2, added2 = cap_knowledge(base, extras + [rc("g#2", 0.95)], 2)
    assert added2 == 2 and [k.chunk.id for k in kept2] == ["g#2", "d#0", "e#0"] and kept2[0].score == 0.9


def test_orchestrator_schema():
    assert ORCHESTRATOR_SCHEMA["properties"]["queries"] == {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6}


# --------------------------------------------------------------------------- orchestrator
def test_orchestrator_expands_retrieves_pins_and_caps(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = IdeationState(THEME, HackathonConstraints(tech_preferences=["python", "fastapi"]))
    OrchestratorAgent().run(state, ctx)
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.tag == "orchestrator" and call.effort == ctx.settings.effort_light and call.json_schema == ORCHESTRATOR_SCHEMA
    assert constraints_block(state.constraints) in call.prompt
    assert state.queries[0] == THEME and len(state.queries) == len(set(state.queries)) == 3
    assert ctx.queries_issued == state.queries + [THEME, f"{THEME} python fastapi"]
    ids = [k.chunk.id for k in state.knowledge]
    assert 0 < len(ids) <= MAX_KNOWLEDGE and len(ids) == len(set(ids))
    assert [(-k.score, k.chunk.id) for k in state.knowledge] == sorted((-k.score, k.chunk.id) for k in state.knowledge)
    assert sum(1 for k in state.knowledge if k.chunk.metadata.get("kind") == "data-source") >= 4
    assert state.memory_context == ""
    assert [t.agent for t in ctx.trace] == ["orchestrator"]


def test_orchestrator_scripted_queries_are_deduped_and_memory_context_loaded(kb, tmp_path):
    mock = MockLLM(seed=0, scripted={"orchestrator": [{"queries": ["  weather api ", "weather api", THEME, "", "demo strategy"]}]})
    ctx = make_ctx(kb, tmp_path, llm=mock)
    ctx.memory.add_pattern(Pattern("failure", "climate dashboards without a named user lose", tags=["climate"], provider="mock"))
    ctx.memory.add_pattern(Pattern("success", "a resilience map that loads live weather", tags=["climate"], provider="anthropic"))
    state = IdeationState(THEME, HackathonConstraints())
    OrchestratorAgent().run(state, ctx)
    assert state.queries == [THEME, "weather api", "demo strategy"]
    assert "Avoid: climate dashboards without a named user lose" in state.memory_context  # mock visible under the mock provider
    assert "Leverage: a resilience map that loads live weather" in state.memory_context


# --------------------------------------------------------------------------- retrieve_more
def test_retrieve_more_adds_gap_chunks_without_llm(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = IdeationState(THEME, HackathonConstraints())
    OrchestratorAgent().run(state, ctx)
    before = {k.chunk.id for k in state.knowledge}
    n_calls = len(mock.calls)
    gaps = ["spotify music api", "pitch structure opening", "team roles integration owner", "earthquake feeds", "fifth gap ignored"]
    state.research = ResearchFindings(coverage_gaps=gaps)
    RetrieveMoreAgent().run(state, ctx)
    assert len(mock.calls) == n_calls
    assert state.coverage_gaps == gaps[:4]
    assert ctx.queries_issued[-4:] == gaps[:4]
    after = {k.chunk.id for k in state.knowledge}
    assert before <= after and len(after) <= MAX_KNOWLEDGE_AFTER_GAPS
    assert state.retrieve_more_added == len(after) - len(before) >= 1
    assert [(-k.score, k.chunk.id) for k in state.knowledge] == sorted((-k.score, k.chunk.id) for k in state.knowledge)


def test_retrieve_more_without_research_adds_nothing(kb, tmp_path):
    ctx = make_ctx(kb, tmp_path)
    state = IdeationState(THEME, HackathonConstraints())
    state.knowledge = [rc("g#1", 0.5)]
    RetrieveMoreAgent().run(state, ctx)
    assert state.retrieve_more_added == 0 and state.coverage_gaps == [] and len(state.knowledge) == 1
    assert ctx.queries_issued == []


# --------------------------------------------------------------------------- conditions
def test_condition_a():
    settings = Settings(provider="mock", max_retrieval_rounds=2)
    choose = after_retrieve_more(settings)
    state = IdeationState(THEME, HackathonConstraints())
    state.retrieve_more_added, state.retrieval_rounds = 1, 1
    assert choose(state) == "research"
    state.retrieval_rounds = 2
    assert choose(state) == "domain_expert"
    state.retrieve_more_added, state.retrieval_rounds = 0, 1
    assert choose(state) == "domain_expert"


def test_condition_b_is_the_only_loop_rule():
    settings = Settings(provider="mock", accept_threshold=3.8, min_strong_ideas=2, max_iterations=2)
    choose = after_evaluator(settings)
    state = IdeationState(THEME, HackathonConstraints())
    state.iteration = 1
    state.verdicts = [verdict("a", 4.0), verdict("b", 3.0)]
    assert choose(state) == "creativity"
    state.verdicts.append(verdict("c", 4.5, disqualified=True))
    assert choose(state) == "creativity"
    state.verdicts.append(verdict("d", 3.8))
    assert choose(state) == "synthesizer"
    state.verdicts = [verdict("a", 1.0)]
    state.iteration = 2
    assert choose(state) == "synthesizer"


def test_build_default_graph_structure():
    g = build_default_graph(Settings(provider="mock", strategist=False, reflector=False))
    assert list(g.nodes) == ["orchestrator", "research", "retrieve_more", "domain_expert", "creativity", "evaluator", "synthesizer"]
    assert g.entry == "orchestrator"
    assert g.edges == {"orchestrator": "research", "research": "retrieve_more", "domain_expert": "creativity", "creativity": "evaluator", "synthesizer": END}
    assert set(g.conditions) == {"retrieve_more", "evaluator"}


def test_build_default_graph_wraps_the_run_in_the_meta_layer():
    g = build_default_graph(Settings(provider="mock"))
    assert list(g.nodes)[0] == "strategist" and list(g.nodes)[-1] == "reflector"
    assert g.entry == "strategist"
    assert g.edges["strategist"] == "orchestrator"
    assert g.edges["synthesizer"] == "reflector" and g.edges["reflector"] == END
    assert set(g.conditions) == {"retrieve_more", "evaluator"}


# --------------------------------------------------------------------------- end to end
def expected_trace_len(state, settings) -> int:
    """DESIGN-META §18.10: strategist + 1 + retrieval_rounds + 1 + iterations * (1 + personas) + 1 + reflector."""
    return (
        int(settings.strategist)
        + 1
        + state.retrieval_rounds
        + 1
        + state.iteration * (1 + len(settings.judge_personas))
        + 1
        + int(settings.reflector)
    )


def run_default(kb, tmp_path, llm=None, **overrides):
    ctx = make_ctx(kb, tmp_path, llm=llm, **overrides)
    state = IdeationState(THEME, HackathonConstraints())
    build_default_graph(ctx.settings).run(state, ctx)
    return state, ctx


def test_full_graph_under_default_mock(kb, tmp_path):
    mock = MockLLM(seed=0)
    state, ctx = run_default(kb, tmp_path, llm=mock)
    settings = ctx.settings
    # The mock strategist plans the midpoint of int_(1, max_iterations), so loop rule B stops at 1.
    assert state.strategy is not None and state.iteration == state.strategy.rounds == 1
    assert len(state.ideas) == settings.ideas_per_round * state.iteration
    assert 1 <= state.retrieval_rounds <= settings.max_retrieval_rounds
    ids = [i.id for i in state.ideas]
    assert len(set(ids)) == len(ids)
    assert {v.idea_id for v in state.verdicts} == set(ids) and len(state.verdicts) == len(ids)
    assert sorted(state.ranking) == sorted(ids)
    assert state.proposal is not None and state.proposal.idea_id == state.ranking[0]
    assert state.research is not None and state.assessment is not None
    assert len(ctx.trace) == expected_trace_len(state, settings)
    assert all(is_canonical_tag(t.agent) for t in ctx.trace)
    assert all(t.error is None for t in ctx.trace)
    assert all(len(i.citations) >= 1 for i in state.ideas)
    assert all(validate_idea(i, state.constraints) == [] for i in state.ideas)
    assert diverse(state.ideas, []) == state.ideas
    assert all(i.id == f"idea-{r}-{n}" for r in (1, 2) for n, i in enumerate([x for x in state.ideas if x.id.startswith(f"idea-{r}-")], 1))
    assert state.visited[:4] == ["strategist", "orchestrator", "research", "retrieve_more"]
    assert state.visited[-1] == "reflector" and state.visited.count("creativity") == 1 and state.visited.count("evaluator") == 1
    assert state.reflection is not None and state.reflection.provider == "mock"
    assert len(mock.calls) == len(ctx.trace)  # no corrective retries under synthesized output
    angles = state.strategy.retrieval_angles
    assert state.queries[0] == THEME and state.queries[1 : 1 + len(angles)] == angles
    assert ctx.queries_issued[:2] == [THEME, THEME]  # the strategist's meta and rules retrievals
    assert ctx.queries_issued[2 : 2 + len(state.queries)] == state.queries


def test_full_graph_without_the_meta_layer_keeps_the_baseline_shape(kb, tmp_path):
    mock = MockLLM(seed=0)
    state, ctx = run_default(kb, tmp_path, llm=mock, strategist=False, reflector=False)
    settings = ctx.settings
    assert state.strategy is None and state.reflection is None
    assert state.iteration == settings.max_iterations == 2
    # The diversity filter may drop a near-duplicate of round 1 in round 2 (state.dropped_duplicate).
    assert len(state.ideas) == settings.ideas_per_round * state.iteration - state.dropped_duplicate
    assert settings.ideas_per_round <= len(state.ideas) <= settings.ideas_per_round * state.iteration
    assert len(ctx.trace) == expected_trace_len(state, settings)
    assert not any(t.agent in ("strategist", "reflector") for t in ctx.trace)
    assert state.visited[0] == "orchestrator" and state.visited[-1] == "synthesizer"
    assert state.queries[0] == THEME and ctx.queries_issued[: len(state.queries)] == state.queries


def normalized_state(state) -> dict:
    """State dict with the reflection's wall-clock timestamp zeroed (the only volatile field)."""
    d = state.to_dict()
    if d.get("reflection"):
        d["reflection"] = dict(d["reflection"], created_at="")
    return d


def test_full_graph_is_deterministic(kb, tmp_path):
    state1, ctx1 = run_default(kb, tmp_path)
    state2, ctx2 = run_default(kb, tmp_path)
    assert normalized_state(state1) == normalized_state(state2)
    assert ctx1.queries_issued == ctx2.queries_issued
    steps1 = [dict(t.to_dict(), duration_ms=0, started_at="") for t in ctx1.trace]
    steps2 = [dict(t.to_dict(), duration_ms=0, started_at="") for t in ctx2.trace]
    assert steps1 == steps2


def test_accept_branch_stops_after_one_round(kb, tmp_path):
    ids = [f"idea-1-{n}" for n in range(1, 9)]
    mock = MockLLM(seed=0, scripted={"judge": [scripted_judge_entry(ids, 5.0)] * 3})
    state, ctx = run_default(kb, tmp_path, llm=mock)
    assert state.iteration == 1
    assert len(state.ideas) == 8 and state.visited.count("creativity") == 1
    assert all(v.consensus.weighted_score == 5.0 for v in state.verdicts)
    assert len(ctx.trace) == expected_trace_len(state, ctx.settings)
    assert state.proposal.idea_id == state.ranking[0]
    assert mock.remaining_scripts() == {"judge": 0}


def test_research_runs_once_when_no_coverage_gaps(kb, tmp_path):
    findings = {"trends": ["t"], "case_studies": [], "pitfalls": ["p"], "opportunities": ["o"], "citations": [], "coverage_gaps": []}
    mock = MockLLM(seed=0, scripted={"research": [findings]})
    state, ctx = run_default(kb, tmp_path, llm=mock)
    assert [t.agent for t in ctx.trace].count("research") == 1
    assert state.retrieval_rounds == 1 and state.retrieve_more_added == 0 and state.coverage_gaps == []
    assert state.visited.count("retrieve_more") == 1


def test_research_reruns_when_gaps_add_chunks(kb, tmp_path):
    findings = {
        "trends": ["t"], "case_studies": [], "pitfalls": ["p"], "opportunities": ["o"], "citations": [],
        "coverage_gaps": ["spotify music api playlists", "pitch opening slide structure"],
    }
    mock = MockLLM(seed=0, scripted={"research": [findings]})
    state, ctx = run_default(kb, tmp_path, llm=mock)
    assert [t.agent for t in ctx.trace].count("research") == 2
    assert state.retrieval_rounds == 2 and state.visited.count("retrieve_more") == 2
    assert state.coverage_gaps == state.research.coverage_gaps[:4]  # from the LAST research round
    assert len(ctx.trace) == expected_trace_len(state, ctx.settings)
