"""Brute-force cosine vector store (docs/DESIGN.md §5)."""

from __future__ import annotations

import math


class VectorStore:
    """Maps ids to dense vectors; ``search`` ranks by cosine similarity, ties broken by id."""

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}
        self._norms: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self._vectors)

    def ids(self) -> list[str]:
        """All stored ids in sorted order."""
        return sorted(self._vectors)

    def get(self, id: str) -> list[float]:
        """The stored vector for ``id`` (a copy)."""
        return list(self._vectors[id])

    def add(self, id: str, vector: list[float]) -> None:
        """Store ``vector`` under ``id`` (re-adding replaces)."""
        vec = [float(x) for x in vector]
        self._vectors[id] = vec
        self._norms[id] = math.sqrt(sum(x * x for x in vec))

    def search(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        """Top-``k`` ``(id, cosine)`` sorted by ``(-score, id)``; non-positive scores omitted."""
        query = [float(x) for x in vector]
        qnorm = math.sqrt(sum(x * x for x in query))
        if k <= 0 or qnorm == 0.0:
            return []
        hits: list[tuple[str, float]] = []
        for id, vec in self._vectors.items():
            norm = self._norms[id]
            if norm == 0.0:
                continue
            if len(vec) != len(query):
                raise ValueError(f"dimension mismatch: query has {len(query)}, {id!r} has {len(vec)}")
            score = sum(a * b for a, b in zip(query, vec)) / (qnorm * norm)
            if score > 0.0:
                hits.append((id, score))
        hits.sort(key=lambda p: (-p[1], p[0]))
        return hits[:k]

    def to_dict(self) -> dict:
        """Serializable form; floats rounded to 6 decimals so the JSON is byte-stable."""
        return {"vectors": {id: [round(x, 6) for x in self._vectors[id]] for id in sorted(self._vectors)}}

    @classmethod
    def from_dict(cls, d: dict) -> "VectorStore":
        store = cls()
        for id, vec in d.get("vectors", {}).items():
            store.add(id, vec)
        return store
