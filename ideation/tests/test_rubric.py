"""Rubric: anchors, prompt substitution and judging-criteria mapping (DESIGN §8.1)."""

from __future__ import annotations

import json

import pytest

from ideate.evaluation.rubric import DEFAULT_RUBRIC, GENERIC_ANCHORS, Criterion, Rubric
from ideate.models import HackathonConstraints


def _share(rubric: Rubric, name: str) -> float:
    weights = rubric.weights()
    return weights[name] / sum(weights.values())


def test_default_rubric_weights_and_anchors():
    assert DEFAULT_RUBRIC.names() == ["novelty", "feasibility", "impact", "demoability"]
    assert DEFAULT_RUBRIC.weights() == {"novelty": 0.30, "feasibility": 0.25, "impact": 0.25, "demoability": 0.20}
    for criterion in DEFAULT_RUBRIC.criteria:
        assert set(criterion.anchors) == {1, 3, 5}
        assert all(criterion.anchors[level] for level in (1, 3, 5))
        assert criterion.description


def test_to_prompt_substitutes_hours_and_team_size():
    text = DEFAULT_RUBRIC.to_prompt(HackathonConstraints(hours=36, team_size=4))
    assert "36h for 4 people" in text
    assert "~60% of 36h" in text
    assert "{hours}" not in text and "{team_size}" not in text
    assert "novelty (30%)" in text and "feasibility (25%)" in text
    default_text = DEFAULT_RUBRIC.to_prompt()
    assert "24h for 3 people" in default_text


def test_from_judging_criteria_appends_feasibility_at_15_percent():
    rubric = Rubric.from_judging_criteria("innovation,impact")
    assert rubric.names() == ["novelty", "impact", "feasibility"]
    assert _share(rubric, "feasibility") == pytest.approx(0.15)
    assert rubric.weights()["novelty"] == 1.0 and rubric.weights()["impact"] == 1.0
    assert set(rubric.criteria[-1].anchors) == {1, 3, 5}


def test_from_judging_criteria_explicit_weights():
    rubric = Rubric.from_judging_criteria("innovation:40,impact:30,demo:30")
    weights = rubric.weights()
    assert weights["novelty"] == 40.0
    assert weights["impact"] == 30.0
    assert weights["demoability"] == 30.0
    assert _share(rubric, "feasibility") == pytest.approx(0.15)


def test_from_judging_criteria_accepts_list_and_keywords():
    rubric = Rubric.from_judging_criteria(["Technical Complexity:50", "Business Viability", "UX Design", "Pitch"])
    assert rubric.names() == ["feasibility", "business", "design", "demoability"]
    assert rubric.weights()["feasibility"] == 50.0
    assert rubric.weights()["business"] == 1.0


def test_unknown_criterion_becomes_slug_criterion():
    rubric = Rubric.from_judging_criteria(["Social Good!:2", "impact"])
    social = rubric.criteria[0]
    assert social.name == "social-good"
    assert social.weight == 2.0
    assert social.anchors == GENERIC_ANCHORS
    assert rubric.names() == ["social-good", "impact", "feasibility"]


def test_duplicates_merge_by_adding_weights():
    rubric = Rubric.from_judging_criteria("innovation:20,novelty:30,creative")
    assert rubric.names() == ["novelty", "feasibility"]
    assert rubric.weights()["novelty"] == 51.0


def test_empty_input_is_default_rubric():
    assert Rubric.from_judging_criteria([]).to_dict() == DEFAULT_RUBRIC.to_dict()
    assert Rubric.from_judging_criteria("").to_dict() == DEFAULT_RUBRIC.to_dict()


def test_bad_weight_is_a_value_error():
    with pytest.raises(ValueError):
        Rubric.from_judging_criteria("innovation:lots")
    with pytest.raises(ValueError):
        Rubric.from_judging_criteria("innovation:0")


def test_weighted_score_missing_criteria_count_as_three():
    assert DEFAULT_RUBRIC.weighted_score({"novelty": 5, "feasibility": 5, "impact": 5, "demoability": 5}) == pytest.approx(5.0)
    assert DEFAULT_RUBRIC.weighted_score({}) == pytest.approx(3.0)
    assert DEFAULT_RUBRIC.weighted_score({"novelty": 5}) == pytest.approx(0.3 * 5 + 0.7 * 3)


def test_dict_round_trip_through_json_coerces_anchor_keys():
    rubric = Rubric.from_judging_criteria("innovation:40,Social Good:10")
    restored = Rubric.from_dict(json.loads(json.dumps(rubric.to_dict())))
    assert restored.to_dict() == rubric.to_dict()
    assert all(isinstance(k, int) for c in restored.criteria for k in c.anchors)
    criterion = Criterion.from_dict({"name": "x", "weight": "2", "description": "d", "anchors": {"1": "a", "3": "b", "5": "c"}})
    assert criterion.weight == 2.0 and criterion.anchors == {1: "a", 3: "b", 5: "c"}
