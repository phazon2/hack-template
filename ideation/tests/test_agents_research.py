"""ResearchAgent (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.context import RunContext, TracingLLM, constraints_block, knowledge_block
from ideate.agents.research import RESEARCH_RULE, ResearchAgent, citations_schema, known_ids, research_schema
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import HackathonConstraints, IdeationState


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def state_with_knowledge(ctx: RunContext, k: int = 6) -> IdeationState:
    state = IdeationState("open data for cities", HackathonConstraints(must_avoid=["blockchain"]))
    state.knowledge = ctx.retrieve("public data api demo", k=k)
    return state


def test_citations_schema_is_enum_bound_or_empty():
    assert citations_schema(["a", "b"]) == {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}, "minItems": 0, "maxItems": 2}
    assert citations_schema([]) == {"type": "array", "items": {"type": "string"}, "minItems": 0, "maxItems": 0}
    schema = research_schema(["x"])
    assert set(schema["properties"]) == {"trends", "case_studies", "pitfalls", "opportunities", "citations", "coverage_gaps"}
    assert schema["properties"]["coverage_gaps"]["maxItems"] == 4


def test_known_ids_drops_unknown_and_duplicates():
    assert known_ids(["a", "zzz", "b", "a"], ["a", "b"]) == ["a", "b"]
    assert known_ids("not a list", ["a"]) == []


def test_research_run_increments_rounds_and_fills_findings(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = state_with_knowledge(ctx)
    shown = [rc.chunk.id for rc in state.knowledge]
    ResearchAgent().run(state, ctx)
    assert state.retrieval_rounds == 1
    assert len(mock.calls) == 1
    call = mock.calls[0]
    assert call.tag == "research" and call.effort == "high" and call.max_tokens == ctx.settings.max_tokens
    assert constraints_block(state.constraints) in call.prompt
    assert knowledge_block(state.knowledge) in call.prompt
    assert RESEARCH_RULE in call.prompt and RESEARCH_RULE in call.system
    assert call.json_schema["properties"]["citations"]["items"]["enum"] == shown
    r = state.research
    assert r is not None
    assert 1 <= len(r.trends) <= 5 and 1 <= len(r.pitfalls) <= 5 and 1 <= len(r.opportunities) <= 5
    assert r.citations and set(r.citations) <= set(shown)
    assert len(r.coverage_gaps) == 2  # mock array default
    assert ctx.trace[0].agent == "research"
    ResearchAgent().run(state, ctx)
    assert state.retrieval_rounds == 2


def test_research_with_no_knowledge_uses_empty_citation_schema(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = IdeationState("t", HackathonConstraints())
    ResearchAgent().run(state, ctx)
    assert mock.calls[0].json_schema["properties"]["citations"]["maxItems"] == 0
    assert state.research.citations == []


def test_scripted_research_keeps_only_shown_citations(kb, tmp_path):
    ctx0 = make_ctx(kb, tmp_path)
    state = state_with_knowledge(ctx0, k=3)
    shown = [rc.chunk.id for rc in state.knowledge]
    scripted = {
        "research": [
            {
                "trends": ["t"], "case_studies": [], "pitfalls": ["p"], "opportunities": ["o"],
                "citations": [shown[1], shown[1], shown[0]], "coverage_gaps": [],
            }
        ]
    }
    mock = MockLLM(seed=0, scripted=scripted)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    ResearchAgent().run(state, ctx)
    assert state.research.citations == [shown[1], shown[0]]
    assert state.research.coverage_gaps == []
    assert len(mock.calls) == 1
