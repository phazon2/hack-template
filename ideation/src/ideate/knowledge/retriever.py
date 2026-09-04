"""Hybrid retrieval and the persisted knowledge base (docs/DESIGN.md §5)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from ideate.knowledge.bm25 import BM25Index
from ideate.knowledge.chunking import split_document
from ideate.knowledge.embeddings import Embedder, HashingEmbedder, embedder_from_dict
from ideate.knowledge.fusion import fuse_with_ranks
from ideate.knowledge.rerank import LexicalOverlapReranker, Reranker
from ideate.knowledge.vector_store import VectorStore
from ideate.models import Chunk, Document, Pattern, RetrievedChunk, sha256_hex

FORMAT_VERSION = 1
MEMORY_KIND = "memory"


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, query: str, k: int = 8, candidates: int = 40, kind: str | None = None) -> list[RetrievedChunk]: ...


def corpus_fingerprint(documents: list[Document]) -> str:
    """sha256 over ``id:sha256(text)`` lines in id order (duplicate ids collapse to the last)."""
    hashes = {d.id: sha256_hex(d.text) for d in documents}
    return sha256_hex("\n".join(f"{id}:{hashes[id]}" for id in sorted(hashes)))


def memory_chunk(pattern: Pattern) -> Chunk:
    """The runtime-only chunk shape for a memory pattern (docs/DESIGN.md §7)."""
    return Chunk(
        id=f"memory#{pattern.id}",
        doc_id="memory",
        text=f"Past outcome lesson ({pattern.kind}): {pattern.text} (tags: {', '.join(pattern.tags)})",
        position=0,
        metadata={"title": f"Memory: {pattern.kind}", "source": "memory", "kind": MEMORY_KIND, "tags": list(pattern.tags)},
    )


class HybridRetriever:
    """BM25 + vector search fused with RRF, optionally reranked."""

    def __init__(
        self,
        chunks: dict[str, Chunk],
        bm25: BM25Index,
        vectors: VectorStore,
        embedder: Embedder,
        reranker: Reranker | None = None,
        bm25_weight: float = 0.4,
        vector_weight: float = 0.6,
        rrf_k: int = 60,
    ) -> None:
        self.chunks = chunks
        self.bm25 = bm25
        self.vectors = vectors
        self.embedder = embedder
        self.reranker = reranker
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rrf_k = rrf_k

    def retrieve(self, query: str, k: int = 8, candidates: int = 40, kind: str | None = None) -> list[RetrievedChunk]:
        """Top-``k`` chunks; ``kind`` makes both searches exhaustive and filters before fusion."""
        if not self.chunks or k <= 0:
            return []
        n = len(self.chunks) if kind is not None else candidates
        bm25_hits = [(id, s) for id, s in self.bm25.search(query, n) if self._accept(id, kind)]
        query_vector = self.embedder.embed([query])[0]
        vector_hits = [(id, s) for id, s in self.vectors.search(query_vector, n) if self._accept(id, kind)]
        bm25_scores, vector_scores = dict(bm25_hits), dict(vector_hits)
        fused = fuse_with_ranks(
            {"bm25": [id for id, _ in bm25_hits], "vector": [id for id, _ in vector_hits]},
            k=self.rrf_k,
            weights={"bm25": self.bm25_weight, "vector": self.vector_weight},
        )
        pool: list[RetrievedChunk] = []
        for position, (id, score, stage_ranks) in enumerate(fused[: max(k * 3, 20)], 1):
            ranks: dict[str, int] = {}
            scores: dict[str, float] = {}
            if id in bm25_scores:
                ranks["bm25"], scores["bm25"] = stage_ranks["bm25"], bm25_scores[id]
            if id in vector_scores:
                ranks["vector"], scores["vector"] = stage_ranks["vector"], vector_scores[id]
            ranks["fused"], scores["rrf"] = position, score
            pool.append(RetrievedChunk(chunk=self.chunks[id], score=score, ranks=ranks, scores=scores))
        if self.reranker is None:
            return pool[:k]
        return self.reranker.rerank(query, pool, k)

    def _accept(self, id: str, kind: str | None) -> bool:
        chunk = self.chunks.get(id)
        return chunk is not None and (kind is None or chunk.metadata.get("kind") == kind)


class KnowledgeBase:
    """Chunks + BM25 + vectors + embedder, buildable from documents and persisted to a directory."""

    def __init__(
        self,
        chunks: dict[str, Chunk],
        bm25: BM25Index,
        vectors: VectorStore,
        embedder: Embedder,
        reranker: Reranker | None = None,
        bm25_weight: float = 0.4,
        vector_weight: float = 0.6,
        rrf_k: int = 60,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> None:
        self.chunks = chunks
        self.bm25 = bm25
        self.vectors = vectors
        self.embedder = embedder
        self.reranker = reranker
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rrf_k = rrf_k
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._doc_hashes: dict[str, str] = {}
        self._loaded_fingerprint: str | None = None
        self._loaded_n_docs = 0

    # ------------------------------------------------------------------ construction
    @classmethod
    def build(
        cls, documents: list[Document], *, embedder: Embedder | None = None, chunk_size: int = 800, overlap: int = 120
    ) -> "KnowledgeBase":
        """Chunk ``documents``, fit the embedder on the chunk texts and index everything."""
        kb = cls(
            {}, BM25Index(), VectorStore(), embedder or HashingEmbedder(512),
            reranker=LexicalOverlapReranker(), chunk_size=chunk_size, chunk_overlap=overlap,
        )
        chunks = [c for d in documents for c in split_document(d, chunk_size, overlap)]
        kb.embedder.fit([c.text for c in chunks])
        kb._record(documents)
        kb._index(chunks)
        return kb

    def add_documents(self, documents: list[Document]) -> int:
        """Chunk, index and embed ``documents`` with the already-fitted embedder; returns chunks added."""
        chunks = [c for d in documents for c in split_document(d, self.chunk_size, self.chunk_overlap)]
        self._record(documents)
        self._index(chunks)
        return len(chunks)

    def add_memory_patterns(self, patterns: list[Pattern]) -> int:
        """Index memory patterns as runtime-only chunks (kind ``memory``, never saved)."""
        chunks = [memory_chunk(p) for p in patterns]
        self._index(chunks)
        return len(chunks)

    def _record(self, documents: list[Document]) -> None:
        for d in documents:
            self._doc_hashes[d.id] = sha256_hex(d.text)

    def _index(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            self.chunks[c.id] = c
            self.bm25.add(c.id, c.text)
        self.bm25.build()
        if chunks:
            for c, vec in zip(chunks, self.embedder.embed([c.text for c in chunks])):
                self.vectors.add(c.id, [round(x, 6) for x in vec])

    # ------------------------------------------------------------------ retrieval
    def retrieve(self, query: str, k: int = 8, candidates: int = 40, kind: str | None = None) -> list[RetrievedChunk]:
        """Hybrid retrieval over the current index (see HybridRetriever)."""
        retriever = HybridRetriever(
            self.chunks, self.bm25, self.vectors, self.embedder, self.reranker,
            bm25_weight=self.bm25_weight, vector_weight=self.vector_weight, rrf_k=self.rrf_k,
        )
        return retriever.retrieve(query, k=k, candidates=candidates, kind=kind)

    # ------------------------------------------------------------------ introspection
    @property
    def corpus_fingerprint(self) -> str:
        """Fingerprint of the documents indexed in this process, else the one loaded from meta.json."""
        if self._doc_hashes:
            return sha256_hex("\n".join(f"{id}:{h}" for id, h in sorted(self._doc_hashes.items())))
        return self._loaded_fingerprint if self._loaded_fingerprint is not None else sha256_hex("")

    def _persistent_ids(self) -> list[str]:
        return sorted(id for id, c in self.chunks.items() if c.metadata.get("kind") != MEMORY_KIND)

    def stats(self) -> dict:
        n_chunks = len(self._persistent_ids())
        return {
            "n_docs": self._loaded_n_docs + len(self._doc_hashes),
            "n_chunks": n_chunks,
            "n_memory_chunks": len(self.chunks) - n_chunks,
            "embedder": self.embedder.name,
            "dim": self.embedder.dim,
        }

    # ------------------------------------------------------------------ persistence
    def save(self, dir: Path | str, now: Callable[[], str] | None = None) -> None:
        """Write chunks/bm25/vectors/embedder/meta JSON files, excluding memory chunks."""
        out = Path(dir)
        out.mkdir(parents=True, exist_ok=True)
        ids = self._persistent_ids()
        bm25 = BM25Index(self.bm25.k1, self.bm25.b)
        vectors = VectorStore()
        for id in ids:
            bm25.add(id, self.chunks[id].text)
            vectors.add(id, self.vectors.get(id))
        bm25.build()
        meta = {
            "format_version": FORMAT_VERSION,
            "embedder": {"name": self.embedder.name, "dim": self.embedder.dim},
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "corpus_fingerprint": self.corpus_fingerprint,
            "n_docs": self._loaded_n_docs + len(self._doc_hashes),
            "n_chunks": len(ids),
            "built_at": now() if now is not None else datetime.now(timezone.utc).isoformat(),
        }
        _write_json(out / "chunks.json", [self.chunks[id].to_dict() for id in ids], indent=2)
        _write_json(out / "bm25.json", bm25.to_dict())
        _write_json(out / "vectors.json", vectors.to_dict())
        _write_json(out / "embedder.json", self.embedder.to_dict())
        _write_json(out / "meta.json", meta, indent=2)

    @classmethod
    def load(cls, dir: Path | str) -> "KnowledgeBase":
        """Read an index written by ``save``; raises ValueError on an unknown format_version."""
        src = Path(dir)
        meta = _read_json(src / "meta.json")
        if meta.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"unsupported index format_version {meta.get('format_version')!r}")
        chunks = {c.id: c for c in (Chunk.from_dict(d) for d in _read_json(src / "chunks.json"))}
        kb = cls(
            chunks,
            BM25Index.from_dict(_read_json(src / "bm25.json")),
            VectorStore.from_dict(_read_json(src / "vectors.json")),
            embedder_from_dict(_read_json(src / "embedder.json")),
            reranker=LexicalOverlapReranker(),
            chunk_size=int(meta["chunk_size"]),
            chunk_overlap=int(meta["chunk_overlap"]),
        )
        kb._loaded_fingerprint = str(meta["corpus_fingerprint"])
        kb._loaded_n_docs = int(meta["n_docs"])
        return kb


def _write_json(path: Path, data: object, indent: int | None = None) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=indent) + "\n", encoding="utf-8")


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
