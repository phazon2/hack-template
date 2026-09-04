"""Score arithmetic: weighted_score, median, agreement, aggregate (DESIGN §8.2)."""

from __future__ import annotations

import pytest

from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.evaluation.scoring import aggregate, agreement, median, weighted_score
from ideate.models import CriterionScore, IdeaEvaluation


def _eval(scores: dict[str, float], **kw) -> IdeaEvaluation:
    return IdeaEvaluation(idea_id="idea-1-1", scores=[CriterionScore(n, s) for n, s in scores.items()], **kw)


def test_weighted_score_normalises_weights_and_fills_missing_with_three():
    weights = {"a": 2.0, "b": 2.0}
    assert weighted_score({"a": 5.0, "b": 1.0}, weights) == pytest.approx(3.0)
    assert weighted_score({"a": 5.0}, weights) == pytest.approx(4.0)
    assert weighted_score({}, weights) == pytest.approx(3.0)
    assert weighted_score({"a": 5.0, "b": 5.0}, {"a": 40, "b": 60}) == pytest.approx(5.0)
    assert weighted_score({"a": 5.0}, {}) == pytest.approx(3.0)


def test_median():
    assert median([3.0]) == 3.0
    assert median([1.0, 5.0]) == 3.0
    assert median([5.0, 1.0, 4.0]) == 4.0
    with pytest.raises(ValueError):
        median([])


def test_agreement_single_eval_is_one_and_spread_lowers_it():
    assert agreement([_eval({"novelty": 4.0})]) == 1.0
    assert agreement([]) == 1.0
    same = [_eval({"novelty": 4.0, "impact": 2.0}), _eval({"novelty": 4.0, "impact": 2.0})]
    assert agreement(same) == 1.0
    spread = [_eval({"novelty": 2.0}), _eval({"novelty": 4.0})]
    assert agreement(spread) == pytest.approx(0.5)
    extreme = [_eval({"novelty": 1.0}), _eval({"novelty": 5.0})]
    assert agreement(extreme) == 0.0


def test_aggregate_median_majority_and_union():
    evals = [
        _eval({"novelty": 5.0, "feasibility": 2.0, "impact": 4.0, "demoability": 4.0}, strengths=["fast"], weaknesses=["scope"], disqualified=True, disqualify_reason="uses a paid API", judge="p1"),
        _eval({"novelty": 3.0, "feasibility": 4.0, "impact": 4.0, "demoability": 2.0}, strengths=["fast", "clear"], weaknesses=["scope", "login"], closest_existing="Acme", judge="p2"),
        _eval({"novelty": 1.0, "feasibility": 3.0, "impact": 5.0, "demoability": 3.0}, strengths=["clear"], suggestions=["cut login"], disqualified=True, demo_break_risk="wifi", judge="p3"),
    ]
    consensus = aggregate(evals, DEFAULT_RUBRIC)
    assert consensus.idea_id == "idea-1-1"
    assert consensus.judge == "consensus"
    assert [s.name for s in consensus.scores] == DEFAULT_RUBRIC.names()
    assert {s.name: s.score for s in consensus.scores} == {"novelty": 3.0, "feasibility": 3.0, "impact": 4.0, "demoability": 3.0}
    assert consensus.weighted_score == pytest.approx(DEFAULT_RUBRIC.weighted_score({"novelty": 3, "feasibility": 3, "impact": 4, "demoability": 3}))
    assert consensus.strengths == ["fast", "clear"]
    assert consensus.weaknesses == ["scope", "login"]
    assert consensus.suggestions == ["cut login"]
    assert consensus.risks == []
    assert consensus.disqualified is True
    assert consensus.disqualify_reason == "uses a paid API"
    assert consensus.closest_existing == "Acme"
    assert consensus.demo_break_risk == "wifi"


def test_aggregate_minority_disqualification_does_not_carry():
    evals = [_eval({"novelty": 4.0}, disqualified=True, disqualify_reason="x"), _eval({"novelty": 4.0}), _eval({"novelty": 4.0})]
    consensus = aggregate(evals, DEFAULT_RUBRIC)
    assert consensus.disqualified is False
    assert consensus.disqualify_reason == "x"
    assert consensus.score_for("feasibility") == 3.0  # missing criteria default to 3.0 per judge


def test_aggregate_needs_at_least_one_eval():
    with pytest.raises(ValueError):
        aggregate([], DEFAULT_RUBRIC)
