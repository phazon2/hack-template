"""SynthesizerAgent (docs/DESIGN.md §9.4)."""

from __future__ import annotations

import pytest

from ideate.agents.context import RunContext, TracingLLM, constraints_block
from ideate.agents.synthesizer import SynthesizerAgent, milestone_template, proposal_schema, synthesizer_prompt
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.evaluation.scoring import aggregate
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import CriterionScore, HackathonConstraints, Idea, IdeaEvaluation, IdeationState, PanelVerdict, TechnicalAssessment


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def ranked_state(n: int) -> IdeationState:
    state = IdeationState("civic tech", HackathonConstraints(hours=48))
    state.assessment = TechnicalAssessment(challenges=["c"], suggested_stack=["python"], building_blocks=["Socrata — access: none"], hour_budget=["h0-1"])
    for k in range(1, n + 1):
        state.ideas.append(Idea(f"Idea {k}", "desc", id=f"idea-1-{k}", one_liner=f"one liner {k}", target_user="clerk"))
        ev = IdeaEvaluation(f"idea-1-{k}", scores=[CriterionScore(name, 3.0) for name in DEFAULT_RUBRIC.names()], weaknesses=[f"weak {k}"])
        state.verdicts.append(PanelVerdict(f"idea-1-{k}", [ev], aggregate([ev], DEFAULT_RUBRIC), 1.0))
    state.ranking = [f"idea-1-{k}" for k in range(1, n + 1)]
    return state


def test_proposal_schema_alternatives():
    s = proposal_schema(["idea-1-2", "idea-1-3"])
    assert "idea_id" not in s["properties"]
    alt = s["properties"]["alternatives"]
    assert alt["items"]["properties"]["idea_id"]["enum"] == ["idea-1-2", "idea-1-3"] and alt["maxItems"] == 2
    assert proposal_schema([])["properties"]["alternatives"] == {"type": "array", "items": {"type": "string"}, "minItems": 0, "maxItems": 0}
    props = s["properties"]
    assert (props["first_hour_plan"]["minItems"], props["first_hour_plan"]["maxItems"]) == (3, 8)
    assert (props["milestones"]["minItems"], props["milestones"]["maxItems"]) == (3, 6)
    assert (props["team_split"]["minItems"], props["team_split"]["maxItems"]) == (1, 6)
    assert (props["cut_list"]["minItems"], props["cut_list"]["maxItems"]) == (1, 6)
    assert (props["human_dependencies"]["minItems"], props["human_dependencies"]["maxItems"]) == (0, 6)
    assert (props["demo_script"]["minItems"], props["demo_script"]["maxItems"]) == (3, 10)


def test_milestone_template_uses_hours():
    text = milestone_template(48)
    assert "by h12 (25%)" in text and "by h29 (60%)" in text and "at h38 (80%)" in text and "last 5h (10%)" in text


def test_prompt_contains_top3_verdicts_and_constraints():
    state = ranked_state(5)
    prompt = synthesizer_prompt(state)
    assert constraints_block(state.constraints) in prompt
    assert "BUILD THIS: idea-1-1" in prompt and "runner-up 1: idea-1-2" in prompt and "runner-up 2: idea-1-3" in prompt
    assert "idea-1-4" not in prompt
    assert "weak 1" in prompt and "Socrata — access: none" in prompt
    assert "integration owner" in prompt and "public URL" in prompt and milestone_template(48) in prompt


def test_run_sets_idea_id_and_alternatives(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = ranked_state(4)
    SynthesizerAgent().run(state, ctx)
    assert len(mock.calls) == 1 and mock.calls[0].tag == "synthesizer" and mock.calls[0].effort == "high"
    p = state.proposal
    assert p is not None and p.idea_id == "idea-1-1"
    assert [a.idea_id for a in p.alternatives] == ["idea-1-2", "idea-1-3"]
    assert 3 <= len(p.first_hour_plan) <= 8 and 3 <= len(p.milestones) <= 6 and 3 <= len(p.demo_script) <= 10
    assert p.executive_summary.startswith("[mock]") and p.pivot_trigger.startswith("[mock]")
    assert [t.agent for t in ctx.trace] == ["synthesizer"]


def test_run_with_single_idea_has_no_alternatives(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = ranked_state(1)
    SynthesizerAgent().run(state, ctx)
    assert state.proposal.idea_id == "idea-1-1" and state.proposal.alternatives == []
    assert mock.calls[0].json_schema["properties"]["alternatives"]["maxItems"] == 0


def test_run_requires_ranking(kb, tmp_path):
    ctx = make_ctx(kb, tmp_path)
    with pytest.raises(ValueError):
        SynthesizerAgent().run(IdeationState("t", HackathonConstraints()), ctx)
