"""BM25Index: ranking, ordering, zero-score omission and serialization."""

import math

from ideate.knowledge.bm25 import BM25Index


def _index() -> BM25Index:
    idx = BM25Index()
    idx.add("c", "hackathon judging rewards a demo that lands in ninety seconds")
    idx.add("a", "webhook receiver public url via git triggered deploy")
    idx.add("b", "public datasets and free apis with no account needed")
    idx.build()
    return idx


def test_exact_term_document_ranks_first_and_zero_scores_are_omitted():
    idx = _index()
    hits = idx.search("webhook receiver", k=10)
    assert hits[0][0] == "a"
    assert [h[0] for h in hits] == ["a"]
    assert idx.search("unrelatedterm", k=10) == []
    assert idx.search("", k=10) == []


def test_results_sorted_by_score_then_id_and_truncated_to_k():
    idx = _index()
    hits = idx.search("public", k=10)
    assert len(hits) == 2 and hits[0][1] > 0
    # equal-length docs with a single shared query term tie -> id order
    tie = BM25Index()
    tie.add("z", "alpha beta")
    tie.add("y", "alpha gamma")
    assert [h[0] for h in tie.search("alpha", k=5)] == ["y", "z"]
    assert len(tie.search("alpha", k=1)) == 1
    assert tie.search("alpha", k=0) == []


def test_idf_formula_and_len():
    idx = _index()
    assert len(idx) == 3
    assert math.isclose(idx._idf["public"], math.log(1 + (3 - 2 + 0.5) / (2 + 0.5)))


def test_round_trip_and_lazy_build():
    idx = _index()
    clone = BM25Index.from_dict(idx.to_dict())
    assert clone.to_dict() == idx.to_dict()
    assert clone.search("demo ninety seconds", k=3) == idx.search("demo ninety seconds", k=3)
    lazy = BM25Index()
    lazy.add("only", "lazy build on search")
    assert lazy.search("lazy", k=1)[0][0] == "only"
