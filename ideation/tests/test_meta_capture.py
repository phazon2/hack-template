"""The capture layer: charter, notes, fetch and gaps.

These four exist because the improvement loop cannot depend on its owner remembering to run
it. The tests below pin the properties that make that true: a charter is always present, a
note costs nothing and is never quarantined, fetched material is always attributed, and a gap
produces a command rather than a question.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ideate.meta.charter import DEFAULT_CHARTER, load_charter, save_charter
from ideate.meta.fetch import (
    FetchError,
    arxiv_query_url,
    fetch_arxiv,
    fetch_url,
    parse_arxiv,
    parse_page,
    write_docs,
)
from ideate.meta.gaps import Gap, collect_gaps, render_gaps
from ideate.meta.store import MetaStore
from ideate.models import HUMAN_CONFIDENCE, HUMAN_PROVIDER, META_PATTERN_KINDS, MetaPattern

ARXIV_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-01T00:00:00Z</published>
    <title>Retrieval  Augmented
      Generation for Teams</title>
    <summary>We study how retrieval changes
      team decisions under time pressure.</summary>
    <author><name>A Researcher</name></author>
    <author><name>B Researcher</name></author>
    <category term="cs.IR"/>
    <category term="cs.AI"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v2</id>
    <title>Incomplete entry</title>
  </entry>
</feed>
"""


# --------------------------------------------------------------------------- charter
def test_charter_falls_back_to_the_bundled_default(tmp_path):
    """There is never a run without a charter: a missing file means the default, not nothing."""
    text, from_file = load_charter(tmp_path / "absent.md")
    assert from_file is False
    assert text == DEFAULT_CHARTER


def test_charter_default_states_the_constraints_it_exists_for(tmp_path):
    """The default charter must carry the facts the strategist cannot infer on its own."""
    text = DEFAULT_CHARTER.lower()
    assert "will not log" in text  # capture cannot depend on the owner remembering
    assert "ideate note" in text  # and it names the mechanism that replaces remembering
    assert "config-fixable" in text and "do-it-myself" in text  # blocker taxonomy survives


def test_charter_round_trip_and_empty_file_is_treated_as_absent(tmp_path):
    path = tmp_path / "charter.md"
    save_charter(path, "  # Mine\n\nDo the thing.  ")
    text, from_file = load_charter(path)
    assert from_file is True and text.startswith("# Mine")

    path.write_text("   \n\n", encoding="utf-8")
    text, from_file = load_charter(path)
    assert from_file is False and text == DEFAULT_CHARTER


def test_strategist_prompt_puts_the_charter_first(tmp_path):
    """Pinned, not retrieved: the charter must not compete with snippets on relevance."""
    from ideate.agents.strategist import strategist_prompt
    from ideate.models import HackathonConstraints, IdeationState

    state = IdeationState(theme="grid resilience", constraints=HackathonConstraints())
    prompt = strategist_prompt(state, [], [], "", 2, charter="CHARTER-MARKER")
    assert prompt.index("CHARTER-MARKER") < prompt.index("grid resilience")

    without = strategist_prompt(state, [], [], "", 2)
    assert "CHARTER-MARKER" not in without


# --------------------------------------------------------------------------- notes
def test_note_is_human_sourced_and_never_quarantined(tmp_path):
    """A correction outranks anything the system inferred, and mock quarantine must not hide it."""
    assert "correction" in META_PATTERN_KINDS
    store = MetaStore(tmp_path / "meta.jsonl")
    stored = store.add_meta_pattern(
        MetaPattern(
            kind="correction",
            text="prefer a live demo over a slide",
            tags=["demo"],
            provider=HUMAN_PROVIDER,
            confidence=HUMAN_CONFIDENCE,
        )
    )
    assert stored.provider == HUMAN_PROVIDER and stored.confidence == HUMAN_CONFIDENCE

    # Visible with the default (quarantining) read, unlike a mock-authored pattern.
    store.add_meta_pattern(MetaPattern(kind="process", text="mock lesson", provider="mock"))
    visible = store.meta_patterns()
    assert [p.text for p in visible] == ["prefer a live demo over a slide"]


def test_repeating_a_note_strengthens_it_instead_of_duplicating(tmp_path):
    store = MetaStore(tmp_path / "meta.jsonl")
    first = store.add_meta_pattern(MetaPattern(kind="correction", text="same lesson", provider=HUMAN_PROVIDER))
    second = store.add_meta_pattern(MetaPattern(kind="correction", text="same lesson", provider=HUMAN_PROVIDER))
    assert first.id == second.id
    assert second.observations == 2
    assert len(store.meta_patterns(kind="correction")) == 1


# --------------------------------------------------------------------------- fetch
def test_parse_arxiv_extracts_metadata_and_skips_incomplete_entries():
    docs = parse_arxiv(ARXIV_FEED)
    assert len(docs) == 1  # the entry without a summary is skipped, not half-written
    doc = docs[0]
    assert doc.title == "Retrieval Augmented Generation for Teams"  # whitespace normalised
    assert doc.url == "http://arxiv.org/abs/2401.00001v1"
    assert doc.authors == ["A Researcher", "B Researcher"]
    assert doc.published == "2024-01-01"
    assert "arxiv" in doc.tags and "cs.IR" in doc.tags
    assert "time pressure" in doc.text


def test_parse_arxiv_rejects_an_empty_or_broken_feed():
    with pytest.raises(FetchError):
        parse_arxiv(b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>")
    with pytest.raises(FetchError):
        parse_arxiv(b"not xml at all <<<")


def test_fetch_arxiv_uses_an_injected_opener_and_a_well_formed_url():
    seen: list[str] = []

    def opener(url: str) -> bytes:
        seen.append(url)
        return ARXIV_FEED

    docs = fetch_arxiv("retrieval augmented generation", max_results=3, opener=opener)
    assert len(docs) == 1
    assert seen[0].startswith("https://export.arxiv.org/api/query?")
    assert "max_results=3" in seen[0]
    # Scoped and ANDed, URL-encoded: not arXiv's default loose OR over every field.
    assert "abs%3A%22retrieval%22+AND+abs%3A%22augmented%22" in seen[0]


def test_arxiv_query_url_clamps_and_rejects_empty():
    assert "max_results=50" in arxiv_query_url("retrieval", 999)
    assert "max_results=1" in arxiv_query_url("retrieval", 0)
    with pytest.raises(FetchError):
        arxiv_query_url("   ")


def test_parse_page_keeps_visible_text_and_drops_scripts():
    html = b"""<html><head><title>Demo tips</title><style>p{color:red}</style></head>
    <body><nav>skip me</nav><p>First paragraph.</p><script>alert('no')</script>
    <p>Second paragraph.</p></body></html>"""
    doc = parse_page(html, "https://example.com/tips")
    assert doc.title == "Demo tips"
    assert "First paragraph." in doc.text and "Second paragraph." in doc.text
    assert "alert" not in doc.text and "skip me" not in doc.text and "color:red" not in doc.text


def test_fetch_url_refuses_non_http_schemes():
    for url in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"):
        with pytest.raises(FetchError):
            fetch_url(url, opener=lambda _: b"<p>hi</p>")


def test_written_evidence_is_always_attributed(tmp_path):
    """`kind: evidence` without a source is exactly what the evidence rules forbid."""
    docs = parse_arxiv(ARXIV_FEED)
    paths = write_docs(docs, tmp_path / "fetched", "2026-09-04T00:00:00+00:00")
    text = Path(paths[0]).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "kind: evidence" in text
    assert "source: http://arxiv.org/abs/2401.00001v1" in text
    assert "retrieved: 2026-09-04T00:00:00+00:00" in text
    assert "content_sha256: " in text
    assert "authors: A Researcher, B Researcher" in text


def test_fetched_documents_load_back_as_evidence_chunks(tmp_path):
    """Round trip: what fetch writes, the corpus loader reads, with its source intact."""
    from ideate.knowledge.chunking import split_document
    from ideate.knowledge.loaders import load_corpus

    write_docs(parse_arxiv(ARXIV_FEED), tmp_path / "fetched", "2026-09-04T00:00:00+00:00")
    documents = load_corpus([tmp_path / "fetched"])
    assert len(documents) == 1
    assert documents[0].metadata["kind"] == "evidence"
    assert documents[0].source == "http://arxiv.org/abs/2401.00001v1"
    chunk = split_document(documents[0], chunk_size=400, overlap=0)[0]
    assert chunk.metadata["kind"] == "evidence"
    assert chunk.metadata["source"] == "http://arxiv.org/abs/2401.00001v1"


# --------------------------------------------------------------------------- gaps
def _write_run(runs_dir: Path, run_id: str, theme: str, gaps: list[str], placeholder: bool = False) -> None:
    directory = runs_dir / run_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(
        json.dumps({"run_id": run_id, "theme": theme, "coverage_gaps": gaps, "is_placeholder": placeholder}),
        encoding="utf-8",
    )


def test_gaps_merge_across_runs_and_rank_by_frequency(tmp_path):
    runs = tmp_path / "runs"
    _write_run(runs, "r1", "food banks", ["no data on cold chain logistics", "rare: donor churn"])
    _write_run(runs, "r2", "grid resilience", ["no data on cold chain logistics"])
    gaps = collect_gaps(runs)
    assert [g.text for g in gaps][0] == "no data on cold chain logistics"
    assert gaps[0].count == 2 and set(gaps[0].runs) == {"r1", "r2"}
    assert len(gaps[0].themes) == 2


def test_placeholder_runs_are_excluded_by_default(tmp_path):
    """Mock gaps are generated text; fetching real papers to answer them would be nonsense."""
    runs = tmp_path / "runs"
    _write_run(runs, "r1", "mock theme", ["invented gap"], placeholder=True)
    assert collect_gaps(runs) == []
    assert len(collect_gaps(runs, include_placeholder=True)) == 1


def test_a_gap_produces_a_command_not_a_question(tmp_path):
    gap = Gap(text="no evidence about cold chain logistics for food banks")
    query = gap.query()
    assert "no" not in query.split() and "evidence" not in query.split()
    assert "cold" in query and "logistics" in query
    assert gap.fetch_command(3) == f'ideate fetch --arxiv "{query}" --max 3'


def test_render_gaps_is_actionable_or_says_there_is_nothing(tmp_path):
    assert "No coverage gaps recorded" in render_gaps([])
    text = render_gaps([Gap(text="no data on donor churn", runs=["r1"], themes=["food banks"])])
    assert "ideate fetch --arxiv" in text and "food banks" in text


def test_missing_or_unreadable_runs_directory_is_not_an_error(tmp_path):
    assert collect_gaps(tmp_path / "nope") == []
    runs = tmp_path / "runs"
    (runs / "broken").mkdir(parents=True)
    (runs / "broken" / "result.json").write_text("{not json", encoding="utf-8")
    assert collect_gaps(runs) == []


def test_arxiv_query_is_scoped_to_abstracts_and_anded():
    """A bare phrase must not become arXiv's default loose OR across every field."""
    from ideate.meta.fetch import build_arxiv_query

    assert build_arxiv_query("hackathon team collaboration") == (
        'abs:"hackathon" AND abs:"team" AND abs:"collaboration"'
    )


def test_arxiv_query_passes_through_an_explicit_field_query():
    from ideate.meta.fetch import build_arxiv_query

    for query in ("cat:cs.HC AND ti:hackathon", "au:Smith", "all:retrieval"):
        assert build_arxiv_query(query) == query


def test_arxiv_query_does_not_mistake_a_colon_inside_a_term_for_a_field():
    from ideate.meta.fetch import build_arxiv_query

    assert build_arxiv_query("covid:19 response") == 'abs:"covid" AND abs:"19" AND abs:"response"'


def test_arxiv_query_rejects_a_phrase_with_no_usable_terms():
    from ideate.meta.fetch import FetchError, build_arxiv_query

    with pytest.raises(FetchError):
        build_arxiv_query("a ! ?")


def test_arxiv_ladder_relaxes_from_all_terms_down_to_the_anchor():
    """ANDing every term is precise but often matches nothing; the ladder always ends on-topic."""
    from ideate.meta.fetch import arxiv_query_ladder

    ladder = arxiv_query_ladder("hackathon judging criteria")
    assert ladder == [
        'abs:"hackathon" AND abs:"judging" AND abs:"criteria"',
        'abs:"hackathon" AND abs:"judging"',
        'abs:"hackathon"',
    ]


def test_arxiv_ladder_never_relaxes_an_explicit_field_query():
    from ideate.meta.fetch import arxiv_query_ladder

    assert arxiv_query_ladder("cat:cs.HC AND ti:hackathon") == ["cat:cs.HC AND ti:hackathon"]


def test_fetch_arxiv_walks_the_ladder_until_a_rung_matches():
    """The first two rungs return an empty feed; the third matches and is what we keep."""
    empty = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
    seen: list[str] = []

    def opener(url: str) -> bytes:
        seen.append(url)
        return ARXIV_FEED if len(seen) == 3 else empty

    docs = fetch_arxiv("hackathon judging criteria", max_results=2, opener=opener)
    assert len(docs) == 1 and len(seen) == 3


def test_fetch_arxiv_reports_a_true_negative_rather_than_inventing_one():
    """When arXiv really has nothing, say so — never fall back to unrelated results."""
    empty = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
    with pytest.raises(FetchError, match="even after relaxing"):
        fetch_arxiv("hackathon judging criteria", opener=lambda _: empty)


def test_fetch_arxiv_does_not_retry_a_transport_failure():
    """Relaxing the query cannot fix an unreachable host, so it must not be tried three times."""
    calls: list[str] = []

    def opener(url: str) -> bytes:
        calls.append(url)
        raise FetchError("could not fetch: host unreachable")

    with pytest.raises(FetchError, match="host unreachable"):
        fetch_arxiv("hackathon judging criteria", opener=opener)
    assert len(calls) == 1


def test_fetched_material_is_part_of_the_corpus_without_being_wired_in(tmp_path, monkeypatch):
    """`ideate fetch` fills the system's own gaps; requiring a manual --corpus would undo that."""
    from ideate.config import Settings

    monkeypatch.chdir(tmp_path)
    settings = Settings(fetched_dir="fetched")
    assert "fetched" not in settings.all_corpus_dirs()  # nothing fetched yet

    write_docs(parse_arxiv(ARXIV_FEED), tmp_path / "fetched", "2026-09-04T00:00:00+00:00")
    assert "fetched" in settings.all_corpus_dirs()
    # Ordering matters: bundled guidance first, fetched evidence next, explicit dirs last.
    assert settings.all_corpus_dirs()[-1] == "fetched"
