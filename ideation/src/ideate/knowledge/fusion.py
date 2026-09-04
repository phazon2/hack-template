"""Reciprocal rank fusion (docs/DESIGN.md §5)."""

from __future__ import annotations


def fuse_with_ranks(
    rankings: dict[str, list[str]], k: int = 60, weights: dict[str, float] | None = None
) -> list[tuple[str, float, dict[str, int]]]:
    """RRF with the per-stage 1-based ranks attached: score = sum_s w_s / (k + rank_s).

    Sorted by ``(-score, id)``; an id absent from a stage simply omits that stage's key.
    """
    weights = weights or {}
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for stage, ids in rankings.items():
        weight = float(weights.get(stage, 1.0))
        for rank, id in enumerate(dict.fromkeys(ids), 1):
            scores[id] = scores.get(id, 0.0) + weight / (k + rank)
            ranks.setdefault(id, {})[stage] = rank
    ordered = sorted(scores, key=lambda id: (-scores[id], id))
    return [(id, scores[id], ranks[id]) for id in ordered]


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]], k: int = 60, weights: dict[str, float] | None = None
) -> list[tuple[str, float]]:
    """RRF scores only, sorted by ``(-score, id)``."""
    return [(id, score) for id, score, _ in fuse_with_ranks(rankings, k=k, weights=weights)]
