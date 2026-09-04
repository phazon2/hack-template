"""Rerankers: lexical overlap math, new-object contract, LLMReranker success and fallback."""

import pytest

from ideate.knowledge.rerank import LexicalOverlapReranker, LLMReranker, Reranker
from ideate.llm.base import LLMBadOutput, LLMRequest, LLMResponse, LLMTransientError
from ideate.models import Chunk, RetrievedChunk


def _rc(id: str, text: str, rrf: float) -> RetrievedChunk:
    chunk = Chunk(id=id, doc_id="d", text=text, position=0, metadata={"kind": "guidance"})
    return RetrievedChunk(chunk=chunk, score=rrf, ranks={"fused": 1}, scores={"rrf": rrf})


def _candidates() -> list[RetrievedChunk]:
    return [
        _rc("c1", "git triggered deploy gives a public url", 0.03),
        _rc("c2", "demo lands in ninety seconds", 0.02),
        _rc("c3", "public url and webhook receiver for the demo", 0.01),
    ]


def test_lexical_reranker_scores_and_returns_new_objects():
    cands = _candidates()
    out = LexicalOverlapReranker().rerank("public url demo", cands, top_n=3)
    assert isinstance(LexicalOverlapReranker(), Reranker)
    # query tokens {public, url, demo}: c1 overlap 2/3 mm 1.0; c2 1/3 mm .5; c3 3/3 mm 0
    expected = {"c1": 0.6 * 1.0 + 0.4 * 2 / 3, "c2": 0.6 * 0.5 + 0.4 / 3, "c3": 0.4}
    assert [rc.chunk.id for rc in out] == ["c1", "c2", "c3"]
    for rank, rc in enumerate(out, 1):
        assert rc.score == pytest.approx(expected[rc.chunk.id])
        assert rc.scores["rerank"] == rc.score and rc.ranks["rerank"] == rank
        assert rc.scores["rrf"] == pytest.approx(rc.scores["rrf"]) and rc.ranks["fused"] == 1
    assert all(new is not old for new in out for old in cands)
    assert all("rerank" not in old.ranks and "rerank" not in old.scores for old in cands)


def test_lexical_reranker_edge_cases():
    const = [_rc("a", "x", 0.5), _rc("b", "y", 0.5)]
    out = LexicalOverlapReranker().rerank("", const, top_n=5)
    assert [rc.chunk.id for rc in out] == ["a", "b"] and all(rc.score == pytest.approx(0.6) for rc in out)
    assert LexicalOverlapReranker().rerank("q", [], top_n=3) == []
    assert len(LexicalOverlapReranker().rerank("q", const, top_n=1)) == 1


class _FakeLLM:
    provider = "fake"
    model = "fake-1"

    def __init__(self, data=None, error: Exception | None = None):
        self.data, self.error, self.calls = data, error, []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return LLMResponse(text="", data=self.data, provider=self.provider, model=self.model)


def test_llm_reranker_uses_relevance_over_ten_and_enum_schema():
    llm = _FakeLLM(data={"scores": [{"chunk_id": "c3", "relevance": 9}, {"chunk_id": "c1", "relevance": 4}, {"chunk_id": "c2", "relevance": 4}, {"chunk_id": "zzz", "relevance": 10}]})
    out = LLMReranker(llm).rerank("public url", _candidates(), top_n=2)
    assert [rc.chunk.id for rc in out] == ["c3", "c1"]
    assert out[0].score == pytest.approx(0.9) and out[0].ranks["rerank"] == 1 and out[0].scores["rrf"] == 0.01
    assert out[1].score == pytest.approx(0.4) and out[1].ranks["rerank"] == 2
    req = llm.calls[0]
    assert req.tag == "rerank" and req.effort == "medium"
    item = req.json_schema["properties"]["scores"]["items"]
    assert item["properties"]["chunk_id"]["enum"] == ["c1", "c2", "c3"]
    assert item["properties"]["relevance"] == {"type": "number", "minimum": 0, "maximum": 10}
    assert req.json_schema["properties"]["scores"]["minItems"] == 3 == req.json_schema["properties"]["scores"]["maxItems"]
    assert "c2" in req.prompt and "public url" in req.prompt


@pytest.mark.parametrize("error", [LLMTransientError("rate limited"), LLMBadOutput("bad json")])
def test_llm_reranker_falls_back_to_input_order_on_llm_error(error):
    out = LLMReranker(_FakeLLM(error=error)).rerank("q", _candidates(), top_n=2)
    assert [rc.chunk.id for rc in out] == ["c1", "c2"]
    assert [rc.score for rc in out] == [0.03, 0.02]
    assert [rc.scores["rerank"] for rc in out] == [0.03, 0.02]
    assert [rc.ranks["rerank"] for rc in out] == [1, 2]


def test_llm_reranker_malformed_data_falls_back_and_non_llm_errors_propagate():
    out = LLMReranker(_FakeLLM(data={"nope": 1})).rerank("q", _candidates(), top_n=3)
    assert [rc.chunk.id for rc in out] == ["c1", "c2", "c3"]
    assert LLMReranker(_FakeLLM(data={"scores": []})).rerank("q", [], top_n=3) == []
    with pytest.raises(RuntimeError):
        LLMReranker(_FakeLLM(error=RuntimeError("boom"))).rerank("q", _candidates(), top_n=3)
