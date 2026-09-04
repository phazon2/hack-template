"""Embedder protocol and the dependency-free feature-hashing embedder (docs/DESIGN.md §5)."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from ideate.knowledge.tokenize import tokenize


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def fit(self, texts: list[str]) -> None: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def to_dict(self) -> dict: ...


def _features(tokens: list[str]) -> list[str]:
    """Prefixed unigram (u:), bigram (b:) and padded char-3-gram (c:) features of a token list."""
    feats = ["u:" + t for t in tokens]
    feats.extend(f"b:{a}_{b}" for a, b in zip(tokens, tokens[1:]))
    for token in tokens:
        padded = f"#{token}#"
        feats.extend("c:" + padded[i : i + 3] for i in range(len(padded) - 2))
    return feats


class HashingEmbedder:
    """blake2b feature hashing with a sign bit, tf-idf weighting and L2 normalisation."""

    name = "hashing"

    def __init__(self, dim: int = 512, idf: dict[str, float] | None = None) -> None:
        if dim < 1:
            raise ValueError("dim must be >= 1")
        self.dim = int(dim)
        self._idf: dict[str, float] = {k: float(v) for k, v in (idf or {}).items()}
        self._slots: dict[str, tuple[int, float]] = {}

    def _slot(self, feature: str) -> tuple[int, float]:
        """(index, sign) of a feature; index from blake2b, sign from a personalised blake2b low bit."""
        slot = self._slots.get(feature)
        if slot is None:
            raw = feature.encode("utf-8")
            index = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big") % self.dim
            low_bit = hashlib.blake2b(raw, digest_size=8, person=b"sign").digest()[-1] & 1
            slot = (index, -1.0 if low_bit else 1.0)
            self._slots[feature] = slot
        return slot

    def fit(self, texts: list[str]) -> None:
        """Compute idf = log((1 + N) / (1 + df)) + 1 over the feature document frequencies."""
        df: dict[str, int] = {}
        for text in texts:
            for feature in dict.fromkeys(_features(tokenize(text))):
                df[feature] = df.get(feature, 0) + 1
        n = len(texts)
        self._idf = {feature: math.log((1 + n) / (1 + count)) + 1.0 for feature, count in df.items()}

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Unit-norm vectors (all-zero when a text has no features)."""
        out: list[list[float]] = []
        for text in texts:
            tf: dict[str, int] = {}
            for feature in _features(tokenize(text)):
                tf[feature] = tf.get(feature, 0) + 1
            vec = [0.0] * self.dim
            for feature, count in tf.items():
                index, sign = self._slot(feature)
                vec[index] += sign * (1.0 + math.log(count)) * self._idf.get(feature, 1.0)
            norm = math.sqrt(sum(x * x for x in vec))
            out.append([x / norm for x in vec] if norm > 0.0 else vec)
        return out

    def to_dict(self) -> dict:
        return {"name": self.name, "dim": self.dim, "idf": dict(sorted(self._idf.items()))}


def embedder_from_dict(d: dict) -> Embedder:
    """Rebuild an embedder from ``to_dict`` output; only ``hashing`` is known to the baseline."""
    name = d.get("name")
    if name != HashingEmbedder.name:
        raise ValueError(f"unknown embedder {name!r}")
    return HashingEmbedder(dim=int(d["dim"]), idf=d.get("idf") or {})
