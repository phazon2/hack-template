"""Rerankers over fused candidates (docs/DESIGN.md §5)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ideate.knowledge.tokenize import tokenize
from ideate.llm.base import LLM, LLMBadOutput, LLMError, LLMRequest
from ideate.llm.schema import arr, enum, num, obj
from ideate.models import RetrievedChunk


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]: ...


def _finalize(scored: list[tuple[RetrievedChunk, float]], top_n: int, keep_order: bool = False) -> list[RetrievedChunk]:
    """New RetrievedChunk objects carrying rerank scores and 1-based rerank ranks."""
    ordered = scored if keep_order else sorted(scored, key=lambda p: (-p[1], p[0].chunk.id))
    out: list[RetrievedChunk] = []
    for rank, (rc, score) in enumerate(ordered[:top_n], 1):
        out.append(
            RetrievedChunk(
                chunk=rc.chunk,
                score=score,
                ranks={**rc.ranks, "rerank": rank},
                scores={**rc.scores, "rerank": score},
            )
        )
    return out


def _rrf(rc: RetrievedChunk) -> float:
    return float(rc.scores.get("rrf", rc.score))


class LexicalOverlapReranker:
    """0.6 * min-max normalised rrf + 0.4 * query-token overlap ratio."""

    def rerank(self, query: str, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        if not candidates or top_n <= 0:
            return []
        rrf = [_rrf(c) for c in candidates]
        lo, hi = min(rrf), max(rrf)
        query_tokens = set(tokenize(query))
        scored: list[tuple[RetrievedChunk, float]] = []
        for rc, value in zip(candidates, rrf):
            minmax = 1.0 if hi == lo else (value - lo) / (hi - lo)
            overlap = len(query_tokens & set(tokenize(rc.chunk.text))) / len(query_tokens) if query_tokens else 0.0
            scored.append((rc, 0.6 * minmax + 0.4 * overlap))
        return _finalize(scored, top_n)


_SYSTEM = (
    "You are a retrieval reranker for a hackathon ideation assistant. Score how useful each "
    "snippet is for answering the query on a 0-10 scale. Return one score per chunk_id."
)


class LLMReranker:
    """One structured LLM call (tag ``rerank``); falls back to input order on any LLMError."""

    def __init__(self, llm: LLM, effort: str = "medium", snippet_chars: int = 600) -> None:
        self.llm = llm
        self.effort = effort
        self.snippet_chars = snippet_chars

    def _prompt(self, query: str, candidates: list[RetrievedChunk]) -> str:
        lines = [f"Query: {query}", "", "Candidates:"]
        for i, rc in enumerate(candidates, 1):
            snippet = " ".join(rc.chunk.text.split())[: self.snippet_chars]
            lines.append(f"[{i}] chunk_id={rc.chunk.id} kind={rc.chunk.metadata.get('kind', '')}: {snippet}")
        return "\n".join(lines)

    def rerank(self, query: str, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]:
        if not candidates or top_n <= 0:
            return []
        ids = list(dict.fromkeys(rc.chunk.id for rc in candidates))
        schema = obj({"scores": arr(obj({"chunk_id": enum(ids), "relevance": num(0, 10)}), len(ids), len(ids))})
        request = LLMRequest(
            system=_SYSTEM, prompt=self._prompt(query, candidates), tag="rerank", json_schema=schema, effort=self.effort
        )
        try:
            relevance = _parse_scores(self.llm.complete(request).data, ids)
        except LLMError:
            return _finalize([(rc, _rrf(rc)) for rc in candidates], top_n, keep_order=True)
        return _finalize([(rc, relevance.get(rc.chunk.id, 0.0)) for rc in candidates], top_n)


def _parse_scores(data: object, ids: list[str]) -> dict[str, float]:
    """chunk_id -> relevance / 10; unknown ids dropped, the first entry per id wins."""
    if not isinstance(data, dict) or not isinstance(data.get("scores"), list):
        raise LLMBadOutput("rerank output is not an object with a scores array")
    known = set(ids)
    out: dict[str, float] = {}
    for item in data["scores"]:
        if not isinstance(item, dict):
            continue
        chunk_id, relevance = item.get("chunk_id"), item.get("relevance")
        if chunk_id in known and chunk_id not in out and isinstance(relevance, (int, float)) and not isinstance(relevance, bool):
            out[chunk_id] = min(max(float(relevance), 0.0), 10.0) / 10.0
    return out
