"""Reciprocal rank fusion on a hand-computed example."""

import pytest

from ideate.knowledge.fusion import fuse_with_ranks, reciprocal_rank_fusion


def test_rrf_matches_hand_computation():
    rankings = {"bm25": ["a", "b", "c"], "vector": ["b", "a", "d"]}
    fused = reciprocal_rank_fusion(rankings, k=60)
    expected = {
        "a": 1 / 61 + 1 / 62,
        "b": 1 / 62 + 1 / 61,
        "c": 1 / 63,
        "d": 1 / 63,
    }
    assert [id for id, _ in fused] == ["a", "b", "c", "d"]  # a/b tie -> id order, c/d tie -> id order
    for id, score in fused:
        assert score == pytest.approx(expected[id])


def test_weights_and_k_change_scores():
    rankings = {"bm25": ["a", "b"], "vector": ["b"]}
    fused = dict(reciprocal_rank_fusion(rankings, k=1, weights={"bm25": 0.4, "vector": 0.6}))
    assert fused["a"] == pytest.approx(0.4 / 2)
    assert fused["b"] == pytest.approx(0.4 / 3 + 0.6 / 2)


def test_fuse_with_ranks_reports_per_stage_ranks_and_ignores_duplicates():
    out = fuse_with_ranks({"bm25": ["a", "a", "b"], "vector": ["b"]}, k=60)
    assert out[0][0] == "b" and out[0][2] == {"bm25": 2, "vector": 1}
    assert out[1][0] == "a" and out[1][2] == {"bm25": 1}
    assert fuse_with_ranks({}, k=60) == []
