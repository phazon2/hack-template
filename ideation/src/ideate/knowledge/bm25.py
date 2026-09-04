"""Okapi BM25 over tokenized chunks (docs/DESIGN.md §5). Stdlib only; ``memory`` imports it."""

from __future__ import annotations

import math

from ideate.knowledge.tokenize import tokenize


class BM25Index:
    """In-memory BM25 index keyed by chunk id.

    ``add`` records term frequencies, ``build`` computes idf and the average length, and
    ``search`` builds lazily when the index is stale. IDF = log(1 + (N - n + 0.5) / (n + 0.5)).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = float(k1)
        self.b = float(b)
        self._tf: dict[str, dict[str, int]] = {}
        self._length: dict[str, int] = {}
        self._postings: dict[str, dict[str, int]] = {}
        self._idf: dict[str, float] = {}
        self._avgdl = 0.0
        self._built = False

    def __len__(self) -> int:
        return len(self._tf)

    def add(self, chunk_id: str, text: str) -> None:
        """Index ``text`` under ``chunk_id`` (re-adding an id replaces it)."""
        tokens = tokenize(text)
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        self._tf[chunk_id] = tf
        self._length[chunk_id] = len(tokens)
        self._built = False

    def build(self) -> None:
        """Compute postings, idf and average document length."""
        postings: dict[str, dict[str, int]] = {}
        for chunk_id in sorted(self._tf):
            for term, count in self._tf[chunk_id].items():
                postings.setdefault(term, {})[chunk_id] = count
        n_docs = len(self._tf)
        self._postings = postings
        self._idf = {
            term: math.log(1.0 + (n_docs - len(docs) + 0.5) / (len(docs) + 0.5)) for term, docs in postings.items()
        }
        self._avgdl = (sum(self._length.values()) / n_docs) if n_docs else 0.0
        self._built = True

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Top-``k`` ``(chunk_id, score)`` sorted by ``(-score, id)``; zero scores omitted."""
        if not self._built:
            self.build()
        if k <= 0 or not self._tf:
            return []
        scores: dict[str, float] = {}
        for term in tokenize(query):
            docs = self._postings.get(term)
            if not docs:
                continue
            idf = self._idf[term]
            for chunk_id, tf in docs.items():
                norm = 1.0 - self.b + self.b * (self._length[chunk_id] / self._avgdl if self._avgdl else 0.0)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + idf * tf * (self.k1 + 1.0) / (tf + self.k1 * norm)
        ranked = sorted(((cid, s) for cid, s in scores.items() if s > 0.0), key=lambda p: (-p[1], p[0]))
        return ranked[:k]

    def to_dict(self) -> dict:
        """Serializable form: parameters plus per-chunk term frequencies in sorted-id order."""
        return {
            "k1": self.k1,
            "b": self.b,
            "docs": [{"id": cid, "tf": dict(sorted(self._tf[cid].items()))} for cid in sorted(self._tf)],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BM25Index":
        """Rebuild an index written by ``to_dict``."""
        index = cls(k1=d.get("k1", 1.5), b=d.get("b", 0.75))
        for doc in d.get("docs", []):
            tf = {str(term): int(count) for term, count in doc["tf"].items()}
            index._tf[doc["id"]] = tf
            index._length[doc["id"]] = sum(tf.values())
        index.build()
        return index
