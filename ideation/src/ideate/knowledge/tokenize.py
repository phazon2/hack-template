"""Deterministic tokenizer shared by BM25, the hashing embedder and the memory store.

Stdlib only and free of ideate imports on purpose: ``memory`` imports this module directly
(docs/DESIGN.md §2.1, §5).
"""

from __future__ import annotations

import re

_SPLIT = re.compile(r"[^a-z0-9]+")

# Roughly 120 common English words; kept inline so the module has no data dependency.
STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again against all also am an and any are as at be because been
    before being below between both but by can could did do does doing down during each
    few for from further had has have having he her here hers him his how i if in into is
    it its just may me might more most must my no nor not now of off on once one only or
    other our ours out over own same she should so some such than that the their theirs
    them then there these they this those through to too under until up us very was we
    were what when where which while who whom whose why will with would you your yours
    """.split()
)

# Applied once, first match wins, only when the remainder keeps >= 3 characters (§5).
_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("ies", "y"),
    ("sses", "ss"),
    ("ing", ""),
    ("ed", ""),
    ("ly", ""),
    ("es", ""),
    ("s", ""),
)


def stem(token: str) -> str:
    """Light suffix stripping: the first rule whose suffix matches and leaves >= 3 chars."""
    for suffix, replacement in _SUFFIX_RULES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)] + replacement
    return token


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop short tokens and stopwords, stem lightly."""
    out: list[str] = []
    for token in _SPLIT.split(text.lower()):
        if len(token) < 2 or token in STOPWORDS:
            continue
        out.append(stem(token))
    return out
