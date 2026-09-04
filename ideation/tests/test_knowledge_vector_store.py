"""VectorStore: cosine search order, tie-breaking and serialization."""

import pytest

from ideate.knowledge.vector_store import VectorStore


def _store() -> VectorStore:
    s = VectorStore()
    s.add("far", [0.0, 1.0])
    s.add("near", [1.0, 0.1])
    s.add("exact", [2.0, 0.0])
    s.add("opposite", [-1.0, 0.0])
    s.add("zero", [0.0, 0.0])
    return s


def test_search_orders_by_cosine_and_omits_non_positive():
    hits = _store().search([1.0, 0.0], k=10)
    assert [h[0] for h in hits] == ["exact", "near"]
    assert hits[0][1] == pytest.approx(1.0)
    assert len(_store().search([1.0, 0.0], k=1)) == 1
    assert _store().search([0.0, 0.0], k=3) == []


def test_ties_break_by_id():
    s = VectorStore()
    s.add("b", [1.0, 0.0])
    s.add("a", [3.0, 0.0])
    assert [h[0] for h in s.search([1.0, 0.0], k=2)] == ["a", "b"]


def test_round_trip_rounds_floats_and_sorts_ids():
    s = _store()
    d = s.to_dict()
    assert list(d["vectors"]) == sorted(d["vectors"])
    clone = VectorStore.from_dict(d)
    assert len(clone) == len(s)
    assert clone.search([1.0, 0.0], k=5) == s.search([1.0, 0.0], k=5)
    s.add("pi", [3.14159265, 0.0])
    assert s.to_dict()["vectors"]["pi"] == [3.141593, 0.0]
    assert clone.get("near") == [1.0, 0.1] and clone.ids() == sorted(d["vectors"])


def test_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        _store().search([1.0, 0.0, 0.0], k=1)
