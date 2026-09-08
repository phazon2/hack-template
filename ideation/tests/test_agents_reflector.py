"""ReflectorAgent: run data in, reflection and meta-patterns out (DESIGN-META §18.3, §18.10)."""

from __future__ import annotations

from ideate.agents.context import RunContext, TracingLLM
from ideate.agents.creativity import CreativityAgent
from ideate.agents.orchestrator import build_default_graph
from ideate.agents.reflector import (
    REFLECTOR_SCHEMA,
    REFLECTOR_SYSTEM,
    ReflectorAgent,
    agent_costs,
    derived_run_id,
    lowest_criterion,
    parse_patterns,
)
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.knowledge.retriever import KnowledgeBase
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.meta.ingest import TRUST_NOTE
from ideate.meta.store import MetaStore
from ideate.models import (
    META_PATTERN_KINDS,
    PROBLEM_TYPES,
    TECHNIQUES,
    CriterionScore,
    Document,
    HackathonConstraints,
    Idea,
    IdeaEvaluation,
    IdeationState,
    PanelVerdict,
    Strategy,
    TechnicalAssessment,
    TraceStep,
)

THEME = "AI for climate resilience"
FIXED_NOW = "2026-01-02T03:04:05+00:00"


def small_kb() -> KnowledgeBase:
    documents = [
        Document(
            id="guidance__demo",
            title="Demo strategy",
            text="A climate demo lands in ninety seconds with a recorded fallback and no login.",
            metadata={"kind": "guidance", "title": "Demo strategy", "tags": ["demo"]},
        ),
        Document(
            id="antipattern__dashboard",
            title="Generic dashboards",
            text="A climate dashboard with no named user is the most common hackathon antipattern.",
            metadata={"kind": "antipattern", "title": "Generic dashboards", "tags": ["antipattern"]},
        ),
    ]
    return KnowledgeBase.build(documents)


def make_ctx(kb, tmp_path, llm=None, meta=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace: list = []
    return RunContext(
        TracingLLM(llm or MockLLM(seed=0), trace, settings, now=lambda: FIXED_NOW),
        kb,
        MemoryStore(tmp_path / "memory.jsonl"),
        DEFAULT_RUBRIC,
        settings,
        trace,
        meta=meta,
    )


def idea(idea_id: str, technique: str = "reverse") -> Idea:
    return Idea(
        id=idea_id,
        title=f"Gauge alerts {idea_id}",
        description="alerts a warden",
        one_liner=f"gauge alerts {idea_id}",
        target_user="volunteer river warden on night duty",
        technique=technique,
        demo_moment="the gauge crosses the line",
        data_sources=["USGS water — access: none — gauge readings"],
        build_hours_estimate=8,
    )


def verdict(idea_id: str, novelty: float, impact: float, agreement: float = 0.9) -> PanelVerdict:
    consensus = IdeaEvaluation(
        idea_id,
        scores=[CriterionScore("novelty", novelty), CriterionScore("impact", impact)],
        weighted_score=(novelty + impact) / 2,
        judge="consensus",
    )
    return PanelVerdict(idea_id, [], consensus, agreement)


def finished_state() -> IdeationState:
    state = IdeationState(THEME, HackathonConstraints())
    state.strategy = Strategy(
        framing="Sensing before prediction.",
        problem_type="data",
        emphasis_techniques=["reverse", "scale"],
        retrieval_angles=["river gauge open data"],
        rubric_emphasis={"novelty": 2.0},
        rounds=1,
        watch_for=["dashboards with no user"],
    )
    state.ideas = [idea("idea-1-1", "reverse"), idea("idea-1-2", "scale"), idea("idea-1-3", "direct")]
    state.verdicts = [verdict("idea-1-1", 4.5, 4.0), verdict("idea-1-2", 3.0, 2.0, 0.4), verdict("idea-1-3", 3.5, 2.5)]
    state.ranking = ["idea-1-1", "idea-1-3", "idea-1-2"]
    state.iteration = 1
    state.retrieval_rounds = 2
    state.coverage_gaps = ["river gauge coverage"]
    state.critiques = ["lowest criterion: impact"]
    state.dropped_invalid = 3
    state.dropped_duplicate = 2
    return state


def scripted_reflection(**overrides) -> dict:
    data = {
        "what_worked": ["the reverse technique produced the top-ranked idea"],
        "what_failed": ["two creativity calls produced duplicates"],
        "process_changes": ["retrieve river gauge sources before the first creativity round"],
        "signal_quality": "the retrieved snippets changed the demo moment of the top idea",
        "winning_technique": "reverse",
        "judge_disagreement": "one idea scored with agreement 0.40; the rest agreed",
        "wasted_effort": ["the second retrieval round added nothing"],
        "meta_patterns": [
            {
                "kind": "process",
                "text": "Retrieve the data sources before the first creativity round on data themes.",
                "scope": "data",
                "tags": ["retrieval", "data"],
            }
        ],
    }
    data.update(overrides)
    return data


def run_reflector(tmp_path, meta=None, data: dict | None = None, run_id: str = "run-fixed-1", **overrides):
    mock = MockLLM(seed=0, scripted={"reflector": [data or scripted_reflection()]})
    ctx = make_ctx(small_kb(), tmp_path, llm=mock, meta=meta, **overrides)
    state = finished_state()
    ReflectorAgent(run_id).run(state, ctx)
    return state, ctx, mock


# --------------------------------------------------------------------------- schema and prompt
def test_reflector_schema_matches_the_spec():
    props = REFLECTOR_SCHEMA["properties"]
    assert (props["what_worked"]["minItems"], props["what_worked"]["maxItems"]) == (1, 4)
    assert (props["what_failed"]["minItems"], props["what_failed"]["maxItems"]) == (0, 4)
    assert (props["process_changes"]["minItems"], props["process_changes"]["maxItems"]) == (1, 4)
    assert props["winning_technique"]["enum"] == list(TECHNIQUES)
    assert props["wasted_effort"]["maxItems"] == 3
    patterns = props["meta_patterns"]
    assert (patterns["minItems"], patterns["maxItems"]) == (1, 5)
    row = patterns["items"]["properties"]
    assert row["kind"]["enum"] == list(META_PATTERN_KINDS)
    assert row["scope"]["enum"] == ["global"] + list(PROBLEM_TYPES)
    assert (row["tags"]["minItems"], row["tags"]["maxItems"]) == (1, 4)


def test_system_prompt_demands_evidence_and_states_the_trust_rule():
    assert "Base every claim on the run data shown" in REFLECTOR_SYSTEM
    assert "instead of inventing one" in REFLECTOR_SYSTEM
    assert TRUST_NOTE in REFLECTOR_SYSTEM


def test_prompt_carries_the_code_computed_run_data(tmp_path):
    _, _, mock = run_reflector(tmp_path)
    prompt = [c for c in mock.calls if c.tag == "reflector"][0].prompt
    assert "problem_type: data" in prompt and "Sensing before prediction." in prompt
    assert "emphasis_techniques: reverse, scale" in prompt and "watch_for: dashboards with no user" in prompt
    assert "retrieval rounds: 2" in prompt and "river gauge coverage" in prompt
    assert "ideas dropped as invalid: 3" in prompt and "ideas dropped as duplicates: 2" in prompt
    assert "idea-1-1 (technique=reverse): weighted score 4.25, panel agreement 0.90" in prompt
    assert "Lowest-scoring criterion across the whole run: impact (mean 2.83)" in prompt
    assert "reflector: 1 call" not in prompt  # its own call is not in the trace yet
    assert "lowest criterion: impact" in prompt


def test_prompt_reports_the_per_agent_cost_from_the_trace(tmp_path):
    ctx = make_ctx(small_kb(), tmp_path, llm=MockLLM(seed=0, scripted={"reflector": [scripted_reflection()]}))
    ctx.trace.extend(
        [
            TraceStep(agent="creativity", provider="mock", model="mock-1", input_tokens=100, output_tokens=40),
            TraceStep(agent="creativity", provider="mock", model="mock-1", input_tokens=110, output_tokens=50),
            TraceStep(agent="judge:hackathon-judge", provider="mock", model="mock-1", input_tokens=10, output_tokens=5),
        ]
    )
    state = finished_state()
    ReflectorAgent("run-fixed-1").run(state, ctx)
    prompt = [c for c in ctx.llm.inner.calls if c.tag == "reflector"][0].prompt
    assert "- creativity: 2 call(s), 210 input tokens, 90 output tokens" in prompt
    assert "- judge:hackathon-judge: 1 call(s), 10 input tokens, 5 output tokens" in prompt


def test_prompt_says_plainly_when_no_strategist_ran(tmp_path):
    mock = MockLLM(seed=0, scripted={"reflector": [scripted_reflection()]})
    ctx = make_ctx(small_kb(), tmp_path, llm=mock)
    state = finished_state()
    state.strategy = None
    ReflectorAgent().run(state, ctx)
    prompt = [c for c in mock.calls if c.tag == "reflector"][0].prompt
    assert "(no strategist ran; the default process was used)" in prompt


# --------------------------------------------------------------------------- code-computed inputs
def test_agent_costs_totals_in_first_call_order():
    trace = [
        TraceStep(agent="orchestrator", provider="mock", model="m", input_tokens=5, output_tokens=1),
        TraceStep(agent="creativity", provider="mock", model="m", input_tokens=7, output_tokens=2),
        TraceStep(agent="orchestrator", provider="mock", model="m", input_tokens=3, output_tokens=4),
    ]
    assert agent_costs(trace) == [("orchestrator", 2, 8, 5), ("creativity", 1, 7, 2)]
    assert agent_costs([]) == []


def test_lowest_criterion_is_the_lowest_mean_over_every_verdict():
    state = finished_state()
    name, mean = lowest_criterion(state)
    assert name == "impact" and round(mean, 2) == 2.83
    assert lowest_criterion(IdeationState(THEME, HackathonConstraints())) is None


def test_derived_run_id_is_deterministic_and_overridable():
    state = finished_state()
    assert derived_run_id(state) == derived_run_id(finished_state())
    assert derived_run_id(state).startswith("run-") and len(derived_run_id(state)) == 16
    other = finished_state()
    other.theme = "AI for logistics"
    assert derived_run_id(other) != derived_run_id(state)


def test_parse_patterns_drops_rows_without_a_kind_or_text():
    rows = [
        {"kind": "pitfall", "text": "  keep me  ", "scope": "data", "tags": ["a"]},
        {"kind": "pitfall", "text": "   ", "tags": []},
        {"kind": "not-a-kind", "text": "drop me"},
        {"kind": "process", "text": "unknown scope falls back", "scope": "martian"},
        "not a row",
    ]
    patterns = parse_patterns(rows, "run-1", "anthropic", FIXED_NOW)
    assert [p.text for p in patterns] == ["keep me", "unknown scope falls back"]
    assert [p.scope for p in patterns] == ["data", "global"]
    assert all(p.source_run_id == "run-1" and p.provider == "anthropic" and p.created_at == FIXED_NOW for p in patterns)


# --------------------------------------------------------------------------- persistence
def test_reflector_persists_the_reflection_and_its_patterns(tmp_path):
    store = MetaStore(tmp_path / "meta.jsonl")
    state, _, _ = run_reflector(tmp_path, meta=store)
    assert state.reflection is not None
    assert state.reflection.run_id == "run-fixed-1" and state.reflection.theme == THEME
    assert state.reflection.provider == "mock" and state.reflection.created_at == FIXED_NOW
    assert state.reflection.winning_technique == "reverse"
    assert state.reflection.what_worked == ["the reverse technique produced the top-ranked idea"]
    stored = store.reflections(include_mock=True)
    assert len(stored) == 1 and stored[0].to_dict() == state.reflection.to_dict()
    patterns = store.meta_patterns(include_mock=True)
    assert len(patterns) == 1
    assert patterns[0].kind == "process" and patterns[0].scope == "data"
    assert patterns[0].source_run_id == "run-fixed-1" and patterns[0].provider == "mock"
    assert patterns[0].observations == 1 and patterns[0].confidence == 0.5


def test_mock_output_is_quarantined_from_real_runs(tmp_path):
    store = MetaStore(tmp_path / "meta.jsonl")
    run_reflector(tmp_path, meta=store)
    assert store.reflections() == [] and store.meta_patterns() == []
    assert store.relevant_meta_patterns("data sources retrieval") == []
    assert len(store.reflections(include_mock=True)) == 1
    assert len(store.meta_patterns(include_mock=True)) == 1


def test_a_repeated_lesson_is_merged_not_duplicated(tmp_path):
    store = MetaStore(tmp_path / "meta.jsonl")
    run_reflector(tmp_path, meta=store, run_id="run-a")
    run_reflector(tmp_path, meta=store, run_id="run-b")
    patterns = store.meta_patterns(include_mock=True)
    assert len(patterns) == 1
    assert patterns[0].observations == 2 and patterns[0].confidence == 0.7
    assert patterns[0].source_run_id == "run-a"  # the first observation keeps provenance
    assert len(store.reflections(include_mock=True)) == 2


def test_reflector_without_a_meta_store_still_sets_the_state(tmp_path):
    state, _, _ = run_reflector(tmp_path, meta=None)
    assert state.reflection is not None and state.reflection.run_id == "run-fixed-1"


def test_run_id_falls_back_to_a_deterministic_derivation(tmp_path):
    store = MetaStore(tmp_path / "meta.jsonl")
    mock = MockLLM(seed=0, scripted={"reflector": [scripted_reflection()]})
    ctx = make_ctx(small_kb(), tmp_path, llm=mock, meta=store)
    state = finished_state()
    ReflectorAgent().run(state, ctx)
    assert state.reflection.run_id == derived_run_id(state)


def test_the_clock_is_injectable(tmp_path):
    mock = MockLLM(seed=0, scripted={"reflector": [scripted_reflection()]})
    ctx = make_ctx(small_kb(), tmp_path, llm=mock)
    state = finished_state()
    ReflectorAgent("run-1", now=lambda: "2030-06-01T00:00:00+00:00").run(state, ctx)
    assert state.reflection.created_at == "2030-06-01T00:00:00+00:00"


# --------------------------------------------------------------------------- the counters it reads
def test_creativity_counts_dropped_ideas_for_the_reflection(tmp_path):
    kb = small_kb()
    good = _raw_idea("Gauge alerts for wardens")
    invalid = _raw_idea("Dashboard for everyone", target_user="everyone")
    duplicate = _raw_idea("Gauge alerts for wardens")
    batch = {"ideas": [good, invalid, duplicate]}
    mock = MockLLM(seed=0, scripted={"creativity": [batch, {"ideas": [good, invalid, duplicate]}]})
    ctx = make_ctx(kb, tmp_path, llm=mock, ideas_per_round=3)
    state = IdeationState(THEME, HackathonConstraints())
    state.knowledge = ctx.retrieve(THEME, k=2)
    state.assessment = TechnicalAssessment(building_blocks=["Open-Meteo — access: none — forecasts"])
    CreativityAgent().run(state, ctx)
    assert state.dropped_invalid == 2  # the generic target_user, once per call (one retry)
    assert state.dropped_duplicate >= 1
    assert len(state.ideas) == 1


def _raw_idea(title: str, **kw) -> dict:
    d = dict(
        title=title,
        one_liner=f"{title} in a sentence",
        description="what it does",
        target_user="volunteer river warden on night duty",
        key_innovation="k",
        technique="direct",
        technical_approach="python",
        demo_strategy="live",
        demo_moment="the gauge crosses the line",
        data_sources=["USGS water — access: none — gauge readings"],
        mvp_scope=["m"],
        cut_first=["c"],
        closest_existing="",
        build_hours_estimate=8,
        risks=["r"],
        citations=[],
    )
    d.update(kw)
    return d


# --------------------------------------------------------------------------- graph
def test_reflector_disabled_means_synthesizer_goes_straight_to_end():
    graph = build_default_graph(Settings(provider="mock", reflector=False))
    assert "reflector" not in graph.nodes and graph.edges["synthesizer"] == "END"


def test_full_graph_with_the_meta_layer_writes_to_the_meta_store(tmp_path):
    kb = small_kb()
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), max_iterations=1)
    store = MetaStore(tmp_path / "meta.jsonl")
    trace: list = []
    ctx = RunContext(
        TracingLLM(MockLLM(seed=0), trace, settings, now=lambda: FIXED_NOW),
        kb,
        MemoryStore(tmp_path / "memory.jsonl"),
        DEFAULT_RUBRIC,
        settings,
        trace,
        meta=store,
    )
    state = IdeationState(THEME, HackathonConstraints())
    build_default_graph(settings, run_id="run-e2e").run(state, ctx)
    assert state.visited[0] == "strategist" and state.visited[-1] == "reflector"
    assert len(trace) == 1 + 1 + state.retrieval_rounds + 1 + state.iteration * (3 + len(settings.judge_personas)) + 1 + 1
    assert state.reflection is not None and state.reflection.run_id == "run-e2e"
    assert store.reflections(include_mock=True)[0].run_id == "run-e2e"
    assert store.meta_patterns(include_mock=True)
    assert store.meta_patterns() == []  # everything the mock wrote stays quarantined
