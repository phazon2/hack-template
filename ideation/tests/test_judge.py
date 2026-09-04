"""LLMJudge / PanelJudge / compare_ideas against a scripted fake LLM (DESIGN §8.3)."""

from __future__ import annotations

import json
from typing import Callable

import pytest

from ideate.evaluation.judge import LLMJudge, PanelJudge, compare_ideas, evaluation_schema, rank_ideas
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.llm.base import LLMBadOutput, LLMRequest, LLMResponse
from ideate.llm.schema import arr, bool_, enum, num, obj, str_
from ideate.models import HackathonConstraints, Idea, IdeaEvaluation, PanelVerdict, slug

CONTEXT = "Hours: 24 | Team: 3 | Judging: default rubric | Prefer: - | Must avoid: - | Tracks: -\nNotes: -"


class FakeLLM:
    """Scripted LLM: ``responder(request)`` returns the JSON data for each call."""

    provider = "fake"
    model = "fake-1"

    def __init__(self, responder: Callable[[LLMRequest], dict]):
        self.responder = responder
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        data = self.responder(request)
        return LLMResponse(text=json.dumps(data), data=data, provider=self.provider, model=self.model, requested_model=self.model)


def _idea(n: int, title: str | None = None) -> Idea:
    return Idea(title=title or f"Idea {n}", description=f"desc {n}", id=f"idea-1-{n}", one_liner=f"one liner {n}", target_user="a nurse on night shift", data_sources=["open data — access: none — x"], demo_moment="the map lights up red")


def _evaluation(idea_id: str, scores: dict[str, float], **kw) -> dict:
    raw = {
        "idea_id": idea_id,
        "scores": [{"name": n, "score": s, "rationale": f"{n} r"} for n, s in scores.items()],
        "strengths": ["s"],
        "weaknesses": ["w"],
        "suggestions": ["g"],
        "risks": [],
        "closest_existing": "",
        "demo_break_risk": "",
        "disqualified": False,
        "disqualify_reason": "",
    }
    raw.update(kw)
    return raw


def _ids_of(request: LLMRequest) -> list[str]:
    return request.json_schema["properties"]["evaluations"]["items"]["properties"]["idea_id"]["enum"]


def _uniform(score: float, **per_idea: dict) -> Callable[[LLMRequest], dict]:
    """Responder scoring every rubric criterion ``score`` (overrides per idea id as extra kwargs)."""

    def respond(request: LLMRequest) -> dict:
        evaluations = []
        for idea_id in _ids_of(request):
            base = _evaluation(idea_id, {n: score for n in DEFAULT_RUBRIC.names()})
            base.update(per_idea.get(idea_id.replace("-", "_"), {}))
            evaluations.append(base)
        return {"evaluations": evaluations}

    return respond


# --------------------------------------------------------------------------- schema + request
def test_evaluation_schema_is_exact():
    ids = ["idea-1-1", "idea-1-2"]
    names = DEFAULT_RUBRIC.names()
    expected = obj(
        {
            "evaluations": arr(
                obj(
                    {
                        "idea_id": enum(ids),
                        "scores": arr(obj({"name": enum(names), "score": num(1, 5), "rationale": str_()}), 4, 4),
                        "strengths": arr(str_(), 1, 4),
                        "weaknesses": arr(str_(), 1, 4),
                        "suggestions": arr(str_(), 1, 4),
                        "risks": arr(str_(), 0, 4),
                        "closest_existing": str_(),
                        "demo_break_risk": str_(),
                        "disqualified": bool_(),
                        "disqualify_reason": str_(),
                    }
                ),
                2,
                2,
            )
        }
    )
    assert evaluation_schema(ids, DEFAULT_RUBRIC) == expected


def test_request_shape_tag_effort_and_prompts():
    llm = FakeLLM(_uniform(4.0))
    persona = "senior engineer estimating what 3 people can ship in 24 hours"
    judge = LLMJudge(llm, DEFAULT_RUBRIC, persona, constraints=HackathonConstraints(hours=48, team_size=5))
    ideas = [_idea(1), _idea(2)]
    evals = judge.evaluate_many(ideas, CONTEXT)
    assert len(llm.calls) == 1
    request = llm.calls[0]
    assert request.tag == f"judge:{slug(persona)}"
    assert request.tag == "judge:senior-engineer-estimating-what-3-people"
    assert request.effort == "medium"
    assert request.json_schema == evaluation_schema(["idea-1-1", "idea-1-2"], DEFAULT_RUBRIC)
    assert persona in request.system
    assert "48h for 5 people" in request.system
    assert "score relative to the other ideas in this batch" in request.system.lower()
    assert "disqualify ideas that violate must-avoid" in request.system.lower()
    assert CONTEXT in request.prompt
    assert "idea-1-1" in request.prompt and "Idea 2" in request.prompt
    assert [e.idea_id for e in evals] == ["idea-1-1", "idea-1-2"]
    assert all(e.judge == persona for e in evals)
    assert all(e.weighted_score == pytest.approx(4.0) for e in evals)
    assert evals[0].strengths == ["s"] and evals[0].weaknesses == ["w"] and evals[0].suggestions == ["g"]


def test_evaluate_single_and_empty_batch():
    llm = FakeLLM(_uniform(2.0))
    judge = LLMJudge(llm, DEFAULT_RUBRIC)
    ev = judge.evaluate(_idea(7), CONTEXT)
    assert ev.idea_id == "idea-1-7" and ev.judge == "hackathon judge"
    assert judge.evaluate_many([], CONTEXT) == []
    assert len(llm.calls) == 1


def test_ideas_need_unique_ids():
    judge = LLMJudge(FakeLLM(_uniform(3.0)), DEFAULT_RUBRIC)
    with pytest.raises(ValueError):
        judge.evaluate_many([_idea(1), _idea(1)], CONTEXT)
    with pytest.raises(ValueError):
        judge.evaluate_many([Idea(title="t", description="d")], CONTEXT)


# --------------------------------------------------------------------------- post-processing
def test_duplicate_idea_ids_keep_first():
    def respond(request: LLMRequest) -> dict:
        return {"evaluations": [_evaluation("idea-1-1", {n: 5.0 for n in DEFAULT_RUBRIC.names()}), _evaluation("idea-1-1", {n: 1.0 for n in DEFAULT_RUBRIC.names()})]}

    ev = LLMJudge(FakeLLM(respond), DEFAULT_RUBRIC).evaluate(_idea(1), CONTEXT)
    assert ev.weighted_score == pytest.approx(5.0)


def test_missing_criterion_filled_unknown_dropped_and_clamped():
    def respond(request: LLMRequest) -> dict:
        scores = {"novelty": 9.0, "feasibility": -3.0, "impact": 4.0, "vibes": 5.0, "impact_dup": 1.0}
        raw = _evaluation("idea-1-1", scores)
        raw["scores"].append({"name": "impact", "score": 1.0, "rationale": "second impact"})
        return {"evaluations": [raw]}

    ev = LLMJudge(FakeLLM(respond), DEFAULT_RUBRIC).evaluate(_idea(1), CONTEXT)
    by_name = {s.name: s for s in ev.scores}
    assert list(by_name) == DEFAULT_RUBRIC.names()
    assert by_name["novelty"].score == 5.0
    assert by_name["feasibility"].score == 1.0
    assert by_name["impact"].score == 4.0 and by_name["impact"].rationale == "impact r"
    assert by_name["demoability"].score == 3.0 and by_name["demoability"].rationale == "[missing]"
    assert ev.weighted_score == pytest.approx(DEFAULT_RUBRIC.weighted_score({"novelty": 5, "feasibility": 1, "impact": 4, "demoability": 3}))


def test_missing_idea_id_is_bad_output():
    def respond(request: LLMRequest) -> dict:
        return {"evaluations": [_evaluation("idea-1-1", {n: 3.0 for n in DEFAULT_RUBRIC.names()})]}

    judge = LLMJudge(FakeLLM(respond), DEFAULT_RUBRIC)
    with pytest.raises(LLMBadOutput) as info:
        judge.evaluate_many([_idea(1), _idea(2)], CONTEXT)
    assert "idea-1-2" in str(info.value)
    with pytest.raises(LLMBadOutput):
        LLMJudge(FakeLLM(lambda r: {"nope": []}), DEFAULT_RUBRIC).evaluate(_idea(1), CONTEXT)


def test_disqualification_and_text_fields_pass_through():
    llm = FakeLLM(_uniform(3.0, idea_1_1={"disqualified": True, "disqualify_reason": "needs an account", "closest_existing": "Acme", "demo_break_risk": "wifi", "risks": ["r1"]}))
    ev = LLMJudge(llm, DEFAULT_RUBRIC).evaluate(_idea(1), CONTEXT)
    assert ev.disqualified is True and ev.disqualify_reason == "needs an account"
    assert ev.closest_existing == "Acme" and ev.demo_break_risk == "wifi" and ev.risks == ["r1"]


# --------------------------------------------------------------------------- panel + ranking
def test_panel_one_call_per_persona_consensus_and_agreement():
    scores_by_persona = {"judge:optimist": 5.0, "judge:pessimist": 1.0, "judge:realist": 4.0}

    def respond(request: LLMRequest) -> dict:
        return _uniform(scores_by_persona[request.tag])(request)

    llm = FakeLLM(respond)
    panel = PanelJudge(llm, DEFAULT_RUBRIC, ["optimist", "pessimist", "realist"])
    verdicts = panel.evaluate_many([_idea(1), _idea(2)], CONTEXT)
    assert [c.tag for c in llm.calls] == ["judge:optimist", "judge:pessimist", "judge:realist"]
    assert [v.idea_id for v in verdicts] == ["idea-1-1", "idea-1-2"]
    v = verdicts[0]
    assert [e.judge for e in v.evaluations] == ["optimist", "pessimist", "realist"]
    assert v.consensus.judge == "consensus"
    assert v.consensus.weighted_score == pytest.approx(4.0)
    assert 0.0 < v.agreement < 1.0
    assert panel.evaluate(_idea(3), CONTEXT).idea_id == "idea-1-3"
    with pytest.raises(ValueError):
        PanelJudge(llm, DEFAULT_RUBRIC, [])


def test_compare_ideas_tiers_are_a_permutation():
    overrides = {
        "idea_1_1": {"scores": [{"name": n, "score": 5.0 if n != "feasibility" else 2.0, "rationale": ""} for n in DEFAULT_RUBRIC.names()]},
        "idea_1_2": {"scores": [{"name": n, "score": 5.0, "rationale": ""} for n in DEFAULT_RUBRIC.names()], "disqualified": True, "disqualify_reason": "must-avoid"},
        "idea_1_3": {"scores": [{"name": n, "score": 4.0, "rationale": ""} for n in DEFAULT_RUBRIC.names()]},
        "idea_1_4": {"scores": [{"name": n, "score": 4.0, "rationale": ""} for n in DEFAULT_RUBRIC.names()]},
        "idea_1_5": {"scores": [{"name": n, "score": 3.0, "rationale": ""} for n in DEFAULT_RUBRIC.names()]},
    }
    llm = FakeLLM(_uniform(3.0, **overrides))
    panel = PanelJudge(llm, DEFAULT_RUBRIC, ["a", "b"])
    ideas = [_idea(1, "Sinks: feasibility 2"), _idea(2, "Disqualified"), _idea(3, "Zeta"), _idea(4, "Alpha"), _idea(5, "Middle")]
    verdicts, ranking = compare_ideas(panel, ideas, CONTEXT)
    assert len(verdicts) == 5
    assert sorted(ranking) == sorted(i.id for i in ideas)
    # tier 1 by (-weighted, title): Alpha(4) before Zeta(4), then Middle(3); tier 2 the feasibility-2 idea; tier 3 disqualified.
    assert ranking == ["idea-1-4", "idea-1-3", "idea-1-5", "idea-1-1", "idea-1-2"]


def test_rank_ideas_without_feasibility_criterion_counts_as_three():
    ideas = [_idea(1, "B"), _idea(2, "A")]
    verdicts = [
        PanelVerdict(idea_id="idea-1-1", consensus=IdeaEvaluation(idea_id="idea-1-1", weighted_score=4.0)),
        PanelVerdict(idea_id="idea-1-2", consensus=IdeaEvaluation(idea_id="idea-1-2", weighted_score=4.0)),
    ]
    assert rank_ideas(ideas, verdicts) == ["idea-1-2", "idea-1-1"]  # both tier 1, tie broken by title
    with pytest.raises(ValueError):
        rank_ideas(ideas + [_idea(3)], verdicts)


def test_panel_over_mock_llm_yields_permutation_with_all_threes():
    pytest.importorskip("ideate.llm.mock")
    from ideate.llm.mock import MockLLM

    llm = MockLLM(seed=0)
    panel = PanelJudge(llm, DEFAULT_RUBRIC, ["judge one", "engineer two", "domain three"])
    ideas = [_idea(n) for n in range(1, 5)]
    verdicts, ranking = compare_ideas(panel, ideas, CONTEXT)
    assert len(llm.calls) == 3
    assert sorted(ranking) == [i.id for i in ideas]
    assert len(verdicts) == 4
    for v in verdicts:
        assert len(v.evaluations) == 3
        assert all(s.score == 3.0 for e in v.evaluations for s in e.scores)
        assert all(s.score == 3.0 for s in v.consensus.scores)
        assert v.consensus.weighted_score == pytest.approx(3.0)
        assert v.consensus.disqualified is False
        assert v.agreement == 1.0
    # deterministic across runs
    _, ranking2 = compare_ideas(PanelJudge(MockLLM(seed=0), DEFAULT_RUBRIC, ["judge one", "engineer two", "domain three"]), ideas, CONTEXT)
    assert ranking2 == ranking
