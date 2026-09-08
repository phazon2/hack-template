"""EvaluatorAgent (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.context import RunContext, TracingLLM, constraints_block
from ideate.agents.evaluator import Defaulting, EvaluatorAgent, critiques_for, judge_context, persona_text
from ideate.config import DEFAULT_PERSONAS, Settings
from ideate.evaluation.pairwise import PAIRWISE_TAG
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.evaluation.scoring import aggregate
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import CriterionScore, HackathonConstraints, Idea, IdeaEvaluation, IdeationState, PanelVerdict, ResearchFindings, TechnicalAssessment, slug


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def idea(n: int, title: str | None = None) -> Idea:
    return Idea(title or f"Idea {n}", "desc", id=f"idea-1-{n}", one_liner="o", target_user="u", demo_moment="a b c d", data_sources=["d"], build_hours_estimate=5)


def verdict(idea_id: str, weaknesses: list[str], scores: dict[str, float]) -> PanelVerdict:
    ev = IdeaEvaluation(idea_id, scores=[CriterionScore(n, scores.get(n, 3.0)) for n in DEFAULT_RUBRIC.names()], weaknesses=weaknesses)
    return PanelVerdict(idea_id, [ev], aggregate([ev], DEFAULT_RUBRIC), 1.0)


def base_state() -> IdeationState:
    state = IdeationState("AI for climate resilience", HackathonConstraints(hours=36, team_size=4))
    state.assessment = TechnicalAssessment(challenges=["hard part"], building_blocks=["Open-Meteo — access: none"], hour_budget=["h0-1 setup"])
    state.research = ResearchFindings(trends=["t1", "t2", "t3", "t4"], pitfalls=["p1"], opportunities=["o1"])
    return state


def test_persona_placeholders():
    state = base_state()
    assert persona_text(DEFAULT_PERSONAS[1], state) == "senior engineer estimating what 4 people can ship in 36 hours"
    assert persona_text(DEFAULT_PERSONAS[2], state) == "domain expert in AI for climate resilience who knows what already exists"
    assert persona_text("judge of {unknown} things", state) == "judge of {unknown} things"
    assert Defaulting(a=1)["b"] == "{b}"


def test_judge_context_contents():
    state = base_state()
    text = judge_context(state)
    assert constraints_block(state.constraints) in text
    assert "hard part" in text and "Open-Meteo — access: none" in text and "h0-1 setup" in text
    assert "- t3" in text and "- t4" not in text  # top research bullets only


def test_critiques_for_top3_dedup_and_cap():
    state = base_state()
    state.ideas = [idea(n) for n in range(1, 5)]
    state.ranking = ["idea-1-1", "idea-1-2", "idea-1-3", "idea-1-4"]
    state.verdicts = [
        verdict("idea-1-1", ["w1", "w2", "w3", "w4"], {"impact": 1.0}),
        verdict("idea-1-2", ["w2", "w5", "w6", "w7"], {"demoability": 2.0}),
        verdict("idea-1-3", ["w8", "w9", "w10"], {}),
        verdict("idea-1-4", ["never shown"], {"novelty": 1.0}),
    ]
    critiques = critiques_for(state)
    assert len(critiques) == 9
    assert critiques[:5] == ["w1", "w2", "w3", "w4", "lowest criterion: impact"]
    assert "lowest criterion: demoability" in critiques
    assert "never shown" not in critiques and len(set(critiques)) == 9


def _score(state, idea_id: str) -> float:
    return state.verdict_for(idea_id).consensus.weighted_score


def test_run_judges_only_unjudged_and_reranks_all(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = base_state()
    state.ideas = [idea(1, "Zeta"), idea(2, "Alpha"), idea(3, "Mid")]
    old = verdict("idea-1-1", ["old weakness"], {"novelty": 5.0, "impact": 5.0, "feasibility": 5.0, "demoability": 5.0})
    state.verdicts = [old]
    EvaluatorAgent().run(state, ctx)
    # One call per persona to judge, then one pairwise call to order them against real winners.
    expected_tags = [f"judge:{slug(persona_text(p, state))}" for p in DEFAULT_PERSONAS]
    assert [c.tag for c in mock.calls] == [*expected_tags, PAIRWISE_TAG]
    judge_calls = mock.calls[: len(DEFAULT_PERSONAS)]
    assert all(c.effort == ctx.settings.effort_light for c in mock.calls)
    for call, persona in zip(judge_calls, DEFAULT_PERSONAS):
        ids = call.json_schema["properties"]["evaluations"]["items"]["properties"]["idea_id"]["enum"]
        assert ids == ["idea-1-2", "idea-1-3"]
        assert constraints_block(state.constraints) in call.prompt
        assert f"You are a {persona_text(persona, state)}." in call.system
        assert "36h for 4 people" in call.system  # rubric anchors substituted from the constraints
    assert state.verdicts[0] is old
    assert {v.idea_id for v in state.verdicts} == {"idea-1-1", "idea-1-2", "idea-1-3"}
    # Every idea gets a win count, and the ranking follows it: wins against real winners order the
    # tier, not the panel's weighted score. Ties inside the tier fall back to score, then title.
    assert set(state.pairwise_wins) == {"idea-1-1", "idea-1-2", "idea-1-3"}
    by_wins = sorted(state.ideas, key=lambda i: (-state.pairwise_wins[i.id], -_score(state, i.id), i.title))
    assert state.ranking == [i.id for i in by_wins]
    assert state.critiques[:2] == ["old weakness", "lowest criterion: novelty"]
    assert len(state.critiques) <= 9
    assert [t.agent for t in ctx.trace] == [*expected_tags, PAIRWISE_TAG]


def test_run_without_pending_ideas_makes_no_calls(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock)
    state = base_state()
    state.ideas = [idea(1), idea(2)]
    state.verdicts = [verdict("idea-1-1", [], {"impact": 1.0}), verdict("idea-1-2", [], {"impact": 5.0})]
    EvaluatorAgent().run(state, ctx)
    assert mock.calls == []
    assert state.ranking == ["idea-1-2", "idea-1-1"]
