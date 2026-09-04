"""The meta-memory context block shown to the strategist and the creativity agent (§18.2)."""

from __future__ import annotations

from ideate.knowledge.retriever import Retriever
from ideate.meta.store import MetaStore
from ideate.models import PROBLEM_TYPES

META_KIND = "meta"
GLOBAL_SCOPE = "global"
EXPANSION_CHUNKS = 2  # meta-corpus titles folded into the relevance query


def _expanded_query(theme: str, problem_type: str, kb: Retriever | None) -> str:
    """``theme`` plus the problem type plus a couple of meta-corpus titles, so a pattern phrased
    in process vocabulary still matches a domain theme."""
    parts = [theme]
    if problem_type:
        parts.append(problem_type)
    if kb is not None:
        for retrieved in kb.retrieve(theme, k=EXPANSION_CHUNKS, kind=META_KIND):
            title = str(retrieved.chunk.metadata.get("title", "")).strip()
            if title:
                parts.append(title)
    return " ".join(p for p in parts if p)


def meta_context_for(
    theme: str,
    problem_type: str,
    kb: Retriever | None,
    store: MetaStore,
    *,
    k: int = 6,
    include_mock: bool = False,
) -> str:
    """Up to ``k`` bullets ``- [kind|scope|confidence] text``; "" when nothing is relevant.

    Only ``global`` patterns and patterns scoped to ``problem_type`` are shown.
    """
    if k <= 0:
        return ""
    allowed = {GLOBAL_SCOPE}
    if problem_type in PROBLEM_TYPES:
        allowed.add(problem_type)
    total = len(store.meta_patterns(include_mock=include_mock))
    if not total:
        return ""
    ranked = store.relevant_meta_patterns(
        _expanded_query(theme, problem_type, kb), k=total, include_mock=include_mock
    )
    lines = [f"- [{p.kind}|{p.scope}|{p.confidence:.2f}] {p.text}" for p in ranked if p.scope in allowed]
    return "\n".join(lines[:k])
