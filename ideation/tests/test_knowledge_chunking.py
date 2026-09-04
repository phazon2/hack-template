"""split_document(): paragraph packing, long-paragraph splitting, overlap and metadata."""

from ideate.knowledge.chunking import split_document
from ideate.models import Document


def _doc(text: str, **meta) -> Document:
    return Document(id="doc", title="Title", text=text, source="src", metadata=meta)


def test_short_document_is_one_chunk_with_metadata_and_default_kind():
    chunks = split_document(_doc("one paragraph.\n\nanother paragraph.", tags=["a", "b"]))
    assert len(chunks) == 1
    c = chunks[0]
    assert c.id == "doc#0" and c.doc_id == "doc" and c.position == 0
    assert c.text == "one paragraph.\n\nanother paragraph."
    assert c.metadata == {"title": "Title", "source": "src", "kind": "guidance", "tags": ["a", "b"]}


def test_paragraphs_are_packed_greedily_and_positions_are_sequential():
    paras = [f"paragraph {i} " + "x" * 30 for i in range(6)]
    chunks = split_document(_doc("\n\n".join(paras)), chunk_size=100, overlap=0)
    assert [c.position for c in chunks] == list(range(len(chunks)))
    assert all(len(c.text) <= 100 for c in chunks)
    assert chunks[0].text.count("paragraph") == 2
    assert "".join(c.text for c in chunks).count("paragraph") == 6


def test_long_paragraph_is_split_by_sentences_then_characters():
    sentences = "First sentence here. Second sentence here! Third one? " * 4
    chunks = split_document(_doc(sentences.strip()), chunk_size=60, overlap=0)
    assert all(len(c.text) <= 60 for c in chunks)
    assert all(c.text[-1] in ".!?" for c in chunks)
    giant = "a" * 150
    pieces = split_document(_doc(giant), chunk_size=60, overlap=0)
    assert [len(c.text) for c in pieces] == [60, 60, 30]


def test_overlap_prepends_tail_of_previous_chunk_except_first():
    text = "\n\n".join("p%d " % i + "y" * 40 for i in range(4))
    chunks = split_document(_doc(text), chunk_size=50, overlap=10)
    assert len(chunks) == 4
    assert not chunks[0].text.startswith("y")
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.text.startswith(prev.text[-10:])


def test_kind_and_empty_text():
    assert split_document(_doc("hello", kind="event"))[0].metadata["kind"] == "event"
    assert split_document(_doc("   \n\n  ")) == []
