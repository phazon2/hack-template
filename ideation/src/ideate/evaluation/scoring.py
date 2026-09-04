"""Score arithmetic shared by the rubric and the judges (docs/DESIGN.md §8.2).

Imports nothing from ``rubric`` (which delegates here); ``aggregate`` only needs an object with
``names()`` and ``weighted_score()``.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

from ideate.models import CriterionScore, IdeaEvaluation

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps scoring below rubric in the DAG
    from ideate.evaluation.rubric import Rubric

NEUTRAL_SCORE = 3.0
SCORE_MIN = 1.0
SCORE_MAX = 5.0
CONSENSUS_JUDGE = "consensus"


def clamp_score(value: float) -> float:
    """Clamp a criterion score into [1, 5] as a float."""
    return min(SCORE_MAX, max(SCORE_MIN, float(value)))


def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted mean over ``weights`` (normalised); criteria missing from ``scores`` count as 3.0."""
    total = sum(weights.values())
    if total <= 0:
        return NEUTRAL_SCORE
    return sum(w * scores.get(name, NEUTRAL_SCORE) for name, w in weights.items()) / total


def median(values: list[float]) -> float:
    """Median of a non-empty list of numbers."""
    if not values:
        raise ValueError("median of an empty list")
    return float(statistics.median(values))


def _criterion_names(evals: list[IdeaEvaluation]) -> list[str]:
    """Criterion names in order of first appearance across the evaluations."""
    names: dict[str, None] = {}
    for ev in evals:
        for s in ev.scores:
            names.setdefault(s.name, None)
    return list(names)


def agreement(evals: list[IdeaEvaluation]) -> float:
    """``1 - mean(pstdev per criterion) / 2`` clamped to [0, 1]; fewer than two evals -> 1.0."""
    if len(evals) < 2:
        return 1.0
    names = _criterion_names(evals)
    if not names:
        return 1.0
    spread = statistics.mean(statistics.pstdev([ev.score_for(name) for ev in evals]) for name in names)
    return min(1.0, max(0.0, 1.0 - spread / 2.0))


def _union(lists: list[list[str]]) -> list[str]:
    """Concatenate, dropping duplicates while keeping first-seen order."""
    return list(dict.fromkeys(item for items in lists for item in items))


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def aggregate(evals: list[IdeaEvaluation], rubric: "Rubric") -> IdeaEvaluation:
    """Consensus of several judges' evaluations of the same idea.

    Per-criterion median (rubric criteria first, then any extra names in first-seen order),
    lists unioned in order, ``disqualified`` by strict majority, first non-empty reason/texts.
    """
    if not evals:
        raise ValueError("aggregate needs at least one evaluation")
    names = list(dict.fromkeys(list(rubric.names()) + _criterion_names(evals)))
    scores = [
        CriterionScore(name=name, score=median([ev.score_for(name) for ev in evals]), rationale=f"median of {len(evals)} judges")
        for name in names
    ]
    return IdeaEvaluation(
        idea_id=evals[0].idea_id,
        scores=scores,
        weighted_score=rubric.weighted_score({s.name: s.score for s in scores}),
        strengths=_union([ev.strengths for ev in evals]),
        weaknesses=_union([ev.weaknesses for ev in evals]),
        suggestions=_union([ev.suggestions for ev in evals]),
        risks=_union([ev.risks for ev in evals]),
        closest_existing=_first_non_empty([ev.closest_existing for ev in evals]),
        demo_break_risk=_first_non_empty([ev.demo_break_risk for ev in evals]),
        disqualified=sum(1 for ev in evals if ev.disqualified) * 2 > len(evals),
        disqualify_reason=_first_non_empty([ev.disqualify_reason for ev in evals]),
        judge=CONSENSUS_JUDGE,
    )
