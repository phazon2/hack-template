"""HybridRetriever / KnowledgeBase: fusion output, kind filter, memory chunks, save/load, determinism."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ideate.knowledge.bm25 import BM25Index
from ideate.knowledge.embeddings import HashingEmbedder
from ideate.knowledge.rerank import LexicalOverlapReranker
from ideate.knowledge.retriever import HybridRetriever, KnowledgeBase, Retriever, corpus_fingerprint, memory_chunk
from ideate.knowledge.vector_store import VectorStore
from ideate.models import Document, Pattern, sha256_hex

SRC = Path(__file__).resolve().parents[1] / "src"


def _docs() -> list[Document]:
    return [
        Document(id="demo", title="Demo strategy", text="A demo that lands in ninety seconds wins. Record a fallback video before the pitch.", metadata={"kind": "guidance", "tags": ["demo"]}),
        Document(id="deploy", title="Deploy", text="Git-triggered deploy gives a public url and a webhook receiver early.", metadata={"kind": "guidance"}),
        Document(id="apis", title="Public APIs", text="OpenWeather (access: free key) provides weather forecasts. NASA APOD (access: none) provides astronomy pictures.", metadata={"kind": "data-source"}),
        Document(id="event", title="Event page", text="This event judges on innovation and a live weather demo.", metadata={"kind": "event"}),
    ]


def test_build_and_retrieve_reports_stage_ranks_and_scores():
    kb = KnowledgeBase.build(_docs())
    assert isinstance(kb, Retriever) and isinstance(kb.reranker, LexicalOverlapReranker)
    assert kb.stats() == {"n_docs": 4, "n_chunks": 4, "n_memory_chunks": 0, "embedder": "hashing", "dim": 512}
    out = kb.retrieve("fallback video demo", k=2)
    assert [rc.chunk.id for rc in out] == ["demo#0", "event#0"]
    top = out[0]
    assert top.ranks["bm25"] == 1 and top.ranks["vector"] == 1 and top.ranks["fused"] == 1 and top.ranks["rerank"] == 1
    assert set(top.scores) == {"bm25", "vector", "rrf", "rerank"} and top.score == top.scores["rerank"]
    assert top.scores["rrf"] == pytest.approx(0.4 / 61 + 0.6 / 61)


def test_identity_reranker_returns_rrf_scores_and_omits_absent_stage_keys():
    kb = KnowledgeBase.build(_docs())
    kb.reranker = None
    out = kb.retrieve("webhook receiver", k=3)
    assert out[0].chunk.id == "deploy#0" and out[0].score == out[0].scores["rrf"]
    assert "rerank" not in out[0].ranks
    only_vector = [rc for rc in out if "bm25" not in rc.ranks]
    assert only_vector and all("bm25" not in rc.scores and "vector" in rc.scores for rc in only_vector)


def test_kind_filter_is_exhaustive_and_exclusive():
    kb = KnowledgeBase.build(_docs())
    assert [rc.chunk.id for rc in kb.retrieve("weather", k=5, kind="data-source")] == ["apis#0"]
    assert [rc.chunk.id for rc in kb.retrieve("weather", k=5, kind="event")] == ["event#0"]
    assert kb.retrieve("weather", k=5, kind="antipattern") == []
    # candidates=1 would normally cut the pool, but a kind search is exhaustive
    assert [rc.chunk.id for rc in kb.retrieve("weather", k=5, candidates=1, kind="event")] == ["event#0"]


def test_empty_index_and_k_zero():
    kb = KnowledgeBase.build([])
    assert kb.retrieve("anything") == [] and kb.stats()["n_chunks"] == 0
    assert kb.corpus_fingerprint == sha256_hex("")
    assert KnowledgeBase.build(_docs()).retrieve("demo", k=0) == []


def test_memory_patterns_are_retrievable_but_never_saved(tmp_path):
    kb = KnowledgeBase.build(_docs())
    pattern = Pattern(kind="failure", text="skipped the fallback recording and the demo broke", tags=["demo", "risk"], provider="anthropic")
    assert kb.add_memory_patterns([pattern]) == 1
    chunk = memory_chunk(pattern)
    assert chunk.id == f"memory#{pattern.id}" and chunk.metadata["kind"] == "memory"
    assert chunk.text == "Past outcome lesson (failure): skipped the fallback recording and the demo broke (tags: demo, risk)"
    assert kb.stats()["n_memory_chunks"] == 1 and kb.stats()["n_chunks"] == 4
    assert [rc.chunk.id for rc in kb.retrieve("fallback recording", k=3, kind="memory")] == [chunk.id]
    assert any(rc.chunk.id == chunk.id for rc in kb.retrieve("fallback recording demo", k=5))
    kb.save(tmp_path, now=lambda: "2026-09-03T00:00:00+00:00")
    chunks = json.loads((tmp_path / "chunks.json").read_text())
    assert [c["id"] for c in chunks] == sorted(c["id"] for c in chunks) and not any(c["id"].startswith("memory#") for c in chunks)
    assert chunk.id not in json.loads((tmp_path / "vectors.json").read_text())["vectors"]
    assert chunk.id not in {d["id"] for d in json.loads((tmp_path / "bm25.json").read_text())["docs"]}
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta == {
        "format_version": 1, "embedder": {"name": "hashing", "dim": 512}, "chunk_size": 800, "chunk_overlap": 120,
        "corpus_fingerprint": kb.corpus_fingerprint, "n_docs": 4, "n_chunks": 4, "built_at": "2026-09-03T00:00:00+00:00",
    }


def test_save_load_round_trip_preserves_retrieval(tmp_path):
    kb = KnowledgeBase.build(_docs(), chunk_size=200, overlap=30)
    kb.save(tmp_path / "idx")
    loaded = KnowledgeBase.load(tmp_path / "idx")
    assert loaded.stats() == kb.stats()
    assert loaded.corpus_fingerprint == kb.corpus_fingerprint == corpus_fingerprint(_docs())
    assert (loaded.chunk_size, loaded.chunk_overlap) == (200, 30)
    for query in ("fallback video demo", "weather forecast api", "public url webhook"):
        before, after = kb.retrieve(query, k=4), loaded.retrieve(query, k=4)
        assert [rc.chunk.id for rc in before] == [rc.chunk.id for rc in after]
        assert [rc.ranks for rc in before] == [rc.ranks for rc in after]
        for b, a in zip(before, after):
            assert b.scores == pytest.approx(a.scores)
    (tmp_path / "idx" / "meta.json").write_text(json.dumps({"format_version": 2}))
    with pytest.raises(ValueError):
        KnowledgeBase.load(tmp_path / "idx")


def test_corpus_fingerprint_formula_and_add_documents():
    docs = _docs()
    expected = sha256_hex("\n".join(f"{d.id}:{sha256_hex(d.text)}" for d in sorted(docs, key=lambda d: d.id)))
    assert corpus_fingerprint(list(reversed(docs))) == expected
    kb = KnowledgeBase.build(docs[:2])
    assert kb.corpus_fingerprint != expected
    assert kb.add_documents(docs[2:]) == 2
    assert kb.corpus_fingerprint == expected and kb.stats()["n_docs"] == 4
    assert [rc.chunk.id for rc in kb.retrieve("weather", k=1, kind="data-source")] == ["apis#0"]


def test_hybrid_retriever_with_explicit_components_and_custom_embedder():
    embedder = HashingEmbedder(dim=64)
    kb = KnowledgeBase.build(_docs(), embedder=embedder)
    assert kb.embedder is embedder and kb.stats()["dim"] == 64
    retriever = HybridRetriever(kb.chunks, kb.bm25, kb.vectors, kb.embedder, reranker=None, bm25_weight=1.0, vector_weight=0.0, rrf_k=1)
    out = retriever.retrieve("webhook receiver", k=1)
    assert out[0].chunk.id == "deploy#0" and out[0].scores["rrf"] == pytest.approx(1.0 / 2)
    assert isinstance(retriever, Retriever)
    assert HybridRetriever({}, BM25Index(), VectorStore(), embedder).retrieve("x") == []


_BUILD_SCRIPT = """
import sys
from pathlib import Path
from ideate.knowledge.loaders import load_corpus
from ideate.knowledge.retriever import KnowledgeBase
corpus, out = sys.argv[1], sys.argv[2]
KnowledgeBase.build(load_corpus([corpus])).save(out, now=lambda: "fixed")
"""


def test_vectors_json_is_byte_identical_across_processes(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for d in _docs():
        (corpus / f"{d.id}.md").write_text(f"---\ntitle: {d.title}\nkind: {d.metadata['kind']}\n---\n{d.text}\n", encoding="utf-8")
    script = tmp_path / "build.py"
    script.write_text(_BUILD_SCRIPT)
    outputs = []
    for seed in ("1", "4242"):
        out = tmp_path / f"idx{seed}"
        env = {**os.environ, "PYTHONPATH": str(SRC), "PYTHONHASHSEED": seed}
        subprocess.run([sys.executable, str(script), str(corpus), str(out)], check=True, env=env, capture_output=True)
        outputs.append({name: (out / name).read_bytes() for name in ("vectors.json", "bm25.json", "chunks.json", "embedder.json", "meta.json")})
    assert outputs[0] == outputs[1]
    assert len(outputs[0]["vectors.json"]) > 100
