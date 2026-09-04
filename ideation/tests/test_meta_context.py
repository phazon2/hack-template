"""meta_context_for: scope filtering, confidence-weighted order, quarantine (DESIGN-META §18.2)."""

from __future__ import annotations

import pytest

from ideate.meta.context import meta_context_for
from ideate.meta.store import MetaStore
from ideate.models import Chunk, MetaPattern, RetrievedChunk


@pytest.fixture
def store(tmp_path) -> MetaStore:
    return MetaStore(tmp_path / "meta.jsonl")


class _StubKB:
    """A retriever that returns one titled meta chunk, recording how it was called."""

    def __init__(self, title: str = "") -> None:
        self.title = title
        self.calls: list[tuple[str, int, str | None]] = []

    def retrieve(self, query: str, k: int = 8, candidates: int = 40, kind: str | None = None):
        self.calls.append((query, k, kind))
        if not self.title:
            return []
        chunk = Chunk(id="c1", doc_id="d1", text="body", position=0, metadata={"title": self.title, "kind": "meta"})
        return [RetrievedChunk(chunk=chunk, score=1.0)]


def _add(store: MetaStore, text: str, **kw) -> MetaPattern:
    base = dict(kind="strategy", text=text, tags=["process"], scope="global", provider="anthropic")
    base.update(kw)
    return store.add_meta_pattern(MetaPattern(**base))


def test_empty_store_and_non_positive_k(store):
    assert meta_context_for("urban mobility", "data", None, store) == ""
    _add(store, "retrieval before generation")
    assert meta_context_for("retrieval", "data", None, store, k=0) == ""


def test_bullets_carry_kind_scope_and_confidence(store):
    _add(store, "retrieval before generation", kind="process", confidence=0.72)
    assert meta_context_for("retrieval", "data", None, store) == "- [process|global|0.72] retrieval before generation"


def test_only_global_and_matching_scope_are_shown(store):
    _add(store, "retrieval before generation", scope="global")
    _add(store, "retrieval before generation", scope="data")
    _add(store, "retrieval before generation", scope="social")
    text = meta_context_for("retrieval", "data", None, store)
    assert sorted(line.split("|")[1] for line in text.splitlines()) == ["data", "global"]
    assert "social" not in text


def test_unknown_problem_type_keeps_only_global(store):
    _add(store, "retrieval before generation", scope="global")
    _add(store, "retrieval before generation", scope="data")
    text = meta_context_for("retrieval", "not-a-problem-type", None, store)
    assert text == "- [strategy|global|0.50] retrieval before generation"


def test_order_follows_confidence_then_id(store):
    _add(store, "judging panels disagree on novelty", scope="global", confidence=0.5)
    _add(store, "judging panels disagree on novelty", scope="data", confidence=0.9)
    lines = meta_context_for("judging novelty", "data", None, store).splitlines()
    assert [line.split("|")[1] for line in lines] == ["data", "global"]


def test_k_truncates(store):
    for text in ("retrieval one", "retrieval two", "retrieval three"):
        _add(store, text)
    assert len(meta_context_for("retrieval", "data", None, store, k=2).splitlines()) == 2


def test_mock_patterns_are_quarantined(store):
    _add(store, "mock idea about retrieval", provider="mock")
    _add(store, "real idea about retrieval", provider="anthropic")
    assert meta_context_for("retrieval", "data", None, store).count("\n") == 0
    assert "mock idea" not in meta_context_for("retrieval", "data", None, store)
    assert len(meta_context_for("retrieval", "data", None, store, include_mock=True).splitlines()) == 2


def test_kb_titles_widen_the_relevance_query(store):
    _add(store, "coverage gaps mean the corpus is thin", kind="pitfall")
    kb = _StubKB(title="coverage gaps")
    assert meta_context_for("urban mobility", "data", None, store) == ""
    assert "coverage gaps" in meta_context_for("urban mobility", "data", kb, store)
    assert kb.calls == [("urban mobility", 2, "meta")]


def test_accepts_a_real_knowledge_base(store, kb):
    _add(store, "retrieval before generation")
    assert meta_context_for("retrieval", "data", kb, store).startswith("- [strategy|global|")
