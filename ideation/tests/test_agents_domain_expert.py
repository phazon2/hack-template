"""DomainExpertAgent (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.context import RunContext, TracingLLM, constraints_block
from ideate.agents.domain_expert import DOMAIN_EXPERT_SCHEMA, DomainExpertAgent, domain_expert_prompt, research_block
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import HackathonConstraints, IdeationState, ResearchFindings


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def test_schema_bounds():
    props = DOMAIN_EXPERT_SCHEMA["properties"]
    for name in ("constraints", "required_skills", "challenges", "breakthroughs", "suggested_stack"):
        assert (props[name]["minItems"], props[name]["maxItems"]) == (1, 6)
    assert (props["building_blocks"]["minItems"], props["building_blocks"]["maxItems"]) == (1, 8)
    assert (props["hour_budget"]["minItems"], props["hour_budget"]["maxItems"]) == (3, 6)


def test_research_block_handles_missing_and_present_findings():
    assert research_block(None) == "(no research findings)"
    block = research_block(ResearchFindings(trends=["a trend"], pitfalls=["a pitfall"]))
    assert "- a trend" in block and "- a pitfall" in block
    assert "Case studies:\n- (none)" in block


def test_prompt_shows_only_data_source_chunks(kb, tmp_path):
    ctx = make_ctx(kb, tmp_path)
    state = IdeationState("weather apps", HackathonConstraints(tech_preferences=["python"]))
    state.knowledge = ctx.retrieve("weather", k=6) + ctx.retrieve("weather", k=3, kind="data-source")
    state.research = ResearchFindings(trends=["trend one"], coverage_gaps=["gap one"])
    prompt = domain_expert_prompt(state)
    assert constraints_block(state.constraints) in prompt
    assert "trend one" in prompt and "gap one" in prompt
    for rc in state.knowledge:
        shown = f"({rc.chunk.id}; " in prompt
        assert shown == (rc.chunk.metadata.get("kind") == "data-source"), rc.chunk.id
    assert "24 hours" in prompt


def test_run_makes_one_high_effort_call_and_fills_assessment(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = IdeationState("weather apps", HackathonConstraints())
    state.knowledge = ctx.retrieve("weather", k=4, kind="data-source")
    out = DomainExpertAgent().run(state, ctx)
    assert out is state
    assert len(mock.calls) == 1
    assert mock.calls[0].tag == "domain_expert" and mock.calls[0].effort == "high"
    assert mock.calls[0].json_schema == DOMAIN_EXPERT_SCHEMA
    a = state.assessment
    assert a is not None
    assert 1 <= len(a.building_blocks) <= 8 and 3 <= len(a.hour_budget) <= 6
    assert all(s.startswith("[mock]") for s in a.building_blocks + a.challenges + a.suggested_stack)
    assert [t.agent for t in ctx.trace] == ["domain_expert"]
