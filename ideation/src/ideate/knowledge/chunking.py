"""Paragraph-packing document chunker with character overlap (docs/DESIGN.md §5)."""

from __future__ import annotations

import re

from ideate.models import Chunk, Document

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _pieces(paragraph: str, chunk_size: int) -> list[str]:
    """Split an over-long paragraph by sentences, then any over-long sentence by characters."""
    out: list[str] = []
    for sentence in _SENTENCE.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= chunk_size:
            out.append(sentence)
        else:
            out.extend(sentence[i : i + chunk_size] for i in range(0, len(sentence), chunk_size))
    return out


def _pack(units: list[tuple[str, str]], chunk_size: int) -> list[str]:
    """Greedily pack ``(text, separator_before)`` units into strings of <= chunk_size chars."""
    chunks: list[str] = []
    current = ""
    for text, sep in units:
        if not current:
            current = text
        elif len(current) + len(sep) + len(text) <= chunk_size:
            current = current + sep + text
        else:
            chunks.append(current)
            current = text
    if current:
        chunks.append(current)
    return chunks


def split_document(doc: Document, chunk_size: int = 800, overlap: int = 120) -> list[Chunk]:
    """Chunk ``doc`` into <= ``chunk_size``-char pieces, prepending ``overlap`` chars of the previous chunk."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    units: list[tuple[str, str]] = []
    for paragraph in _PARAGRAPH.split(doc.text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= chunk_size:
            units.append((paragraph, "\n\n"))
        else:
            for i, piece in enumerate(_pieces(paragraph, chunk_size)):
                units.append((piece, "\n\n" if i == 0 else " "))
    metadata = {
        "title": doc.title,
        "source": doc.source,
        "kind": doc.metadata.get("kind") or "guidance",
        "tags": list(doc.metadata.get("tags") or []),
    }
    chunks: list[Chunk] = []
    previous = ""
    for position, core in enumerate(_pack(units, chunk_size)):
        text = core if position == 0 or overlap <= 0 else previous[-overlap:] + "\n" + core
        chunks.append(Chunk(id=f"{doc.id}#{position}", doc_id=doc.id, text=text, position=position, metadata=dict(metadata)))
        previous = text
    return chunks
