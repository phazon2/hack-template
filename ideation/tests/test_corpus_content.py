"""Content checks for the bundled seed corpus (docs/DESIGN.md §14). Stdlib only, no ideate imports."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[1] / "src" / "ideate" / "corpus"
ALLOWED_KINDS = {"guidance", "data-source", "archetype", "antipattern", "event", "evidence", "meta"}
EXPECTED_FILES = {
    "judging-criteria.md",
    "demo-strategy.md",
    "scoping-24h-48h.md",
    "failure-modes.md",
    "deploy-and-webhooks.md",
    "pitch-structure.md",
    "idea-techniques.md",
    "team-roles.md",
    "ai-agent-project-patterns.md",
    "public-data-and-apis.md",
    "project-archetypes.md",
    "generic-idea-antipatterns.md",
}
EXPECTED_META_FILES = {
    "idea-generation-strategy.md",
    "problem-solving-methods.md",
    "memory-system-design.md",
    "self-improving-systems.md",
    "retrieval-strategy.md",
    "evaluation-design.md",
    "agent-system-design.md",
    "external-memory-ingestion.md",
}
MIN_WORDS = 400
MIN_META_WORDS = 500
MAX_WORDS = 1200


def _meta_documents() -> list[Path]:
    return [p for p in _documents() if p.parent.name == "meta"]


def _documents() -> list[Path]:
    return sorted(p for p in CORPUS.rglob("*.md") if p.name.lower() != "readme.md")


def _front_matter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{path.name}: missing front matter"
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = re.sub(r"\s+#.*$", "", value).strip()
    raise AssertionError(f"{path.name}: unterminated front matter")


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("---", 2)[2] if text.startswith("---") else text


DOCS = _documents()
META_DOCS = _meta_documents()


def test_at_least_twelve_documents() -> None:
    assert len(DOCS) >= 12
    assert EXPECTED_FILES <= {p.name for p in DOCS}


def test_readmes_exist_and_document_the_contract() -> None:
    top = (CORPUS / "README.md").read_text(encoding="utf-8")
    event = (CORPUS / "event" / "README.md").read_text(encoding="utf-8")
    meta = (CORPUS / "meta" / "README.md").read_text(encoding="utf-8")
    for key in ("title", "tags", "kind", "source"):
        assert f"{key}" in top
    assert "kind: event" in event
    assert "kind: meta" in meta
    assert "never instructions" in meta


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_front_matter_contract(path: Path) -> None:
    fm = _front_matter(path)
    assert fm.get("title"), f"{path.name}: title missing"
    assert fm.get("tags"), f"{path.name}: tags missing"
    assert all(t.strip() for t in fm["tags"].split(",")), f"{path.name}: empty tag"
    assert fm.get("kind") in ALLOWED_KINDS, f"{path.name}: kind {fm.get('kind')!r} not allowed"
    if fm["kind"] == "evidence":
        assert fm.get("source"), f"{path.name}: evidence needs a source"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_no_placeholders(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "TODO" not in text, f"{path.name}: contains TODO"
    assert "lorem" not in text.lower(), f"{path.name}: contains lorem"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_word_count_bounds(path: Path) -> None:
    words = len(_body(path).split())
    assert MIN_WORDS <= words <= MAX_WORDS, f"{path.name}: {words} words"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_paragraphs_fit_chunker(path: Path) -> None:
    """Paragraphs should stay self-contained under the 800-char chunk size (DESIGN §5)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", _body(path)) if p.strip()]
    too_long = [p[:40] for p in paragraphs if len(p) > 800]
    assert not too_long, f"{path.name}: paragraphs over 800 chars: {too_long}"


def test_exactly_one_of_each_special_kind() -> None:
    kinds = [_front_matter(p)["kind"] for p in DOCS]
    assert kinds.count("data-source") == 1
    assert kinds.count("archetype") == 1
    assert kinds.count("antipattern") == 1
    assert _front_matter(CORPUS / "public-data-and-apis.md")["kind"] == "data-source"
    assert _front_matter(CORPUS / "project-archetypes.md")["kind"] == "archetype"
    assert _front_matter(CORPUS / "generic-idea-antipatterns.md")["kind"] == "antipattern"


def test_data_source_entries_have_access_lines() -> None:
    body = _body(CORPUS / "public-data-and-apis.md")
    access = re.findall(r"^access: (none|free key|account)$", body, flags=re.MULTILINE)
    assert len(access) >= 25
    assert set(access) == {"none", "free key", "account"}


def test_deploy_file_states_the_public_url_chain_and_mock_rule() -> None:
    text = _body(CORPUS / "deploy-and-webhooks.md").lower()
    assert "public url" in text
    assert "webhook" in text
    assert "egress" in text
    assert "scaffolding" in text and "never evidence" in text


CLOCK_FRACTIONS = {"10%", "25%", "60%", "70%", "80%"}
# An arXiv id, a URL, or a front-matter source is enough to make a number checkable.
ATTRIBUTION = re.compile(r"arXiv\s*\d{4}\.\d{4,5}|https?://|^source:", re.I | re.M)


def test_percentages_are_either_clock_fractions_or_attributed() -> None:
    """The rule is that a number must be checkable, not that numbers are forbidden.

    Hand-written guidance may only use the clock fractions, so it cannot smuggle in an invented
    statistic. A document that cites its sources may quote their figures, because the reader can
    go and verify them — which is the whole point of the evidence rule.
    """
    for path in DOCS:
        body = _body(path)
        found = set(re.findall(r"\d+(?:\.\d+)?%", body))
        extra = found - CLOCK_FRACTIONS
        if not extra:
            continue
        assert ATTRIBUTION.search(path.read_text(encoding="utf-8")), (
            f"{path.name}: percentages {extra} with no source to check them against"
        )


def test_an_unattributed_percentage_would_still_fail(tmp_path) -> None:
    """The relaxed rule must still catch the thing it was written for."""
    doc = tmp_path / "invented.md"
    doc.write_text("---\ntitle: t\ntags: a\nkind: guidance\n---\n\nWins rise 47% here.\n", encoding="utf-8")
    raw = doc.read_text(encoding="utf-8")
    found = set(re.findall(r"\d+(?:\.\d+)?%", raw.split("---", 2)[2])) - CLOCK_FRACTIONS
    assert found == {"47%"} and not ATTRIBUTION.search(raw)


# --------------------------------------------------------------------------- meta layer (§18.5)
def test_meta_corpus_has_at_least_eight_documents() -> None:
    assert len(META_DOCS) >= 8
    assert EXPECTED_META_FILES <= {p.name for p in META_DOCS}
    assert all(_front_matter(p)["kind"] == "meta" for p in META_DOCS)


def test_meta_documents_are_long_enough() -> None:
    """§18.5 asks for 500-1200 words; the shared upper bound already applies."""
    for path in META_DOCS:
        words = len(_body(path).split())
        assert MIN_META_WORDS <= words <= MAX_WORDS, f"{path.name}: {words} words"


def test_meta_kind_is_only_used_inside_the_meta_directory() -> None:
    outside = [p.name for p in DOCS if p.parent.name != "meta" and _front_matter(p)["kind"] == "meta"]
    assert not outside, f"kind 'meta' used outside corpus/meta: {outside}"


def test_memory_design_covers_the_required_ground() -> None:
    body = _body(CORPUS / "meta" / "memory-system-design.md").lower()
    for term in ("episodic", "semantic", "procedural", "provenance", "confidence", "forgetting"):
        assert term in body, f"memory-system-design.md: missing {term}"
    assert "self-confirming" in body
    assert "mock" in body and "quarantin" in body


def test_self_improvement_doc_covers_degeneration_and_the_human_point() -> None:
    body = _body(CORPUS / "meta" / "self-improving-systems.md").lower()
    for term in ("reflection", "actor-critic", "eval", "drift", "confirmation loop", "metric gaming"):
        assert term in body, f"self-improving-systems.md: missing {term}"
    assert "human" in body and "contested" in body


def test_ingestion_doc_states_the_data_not_instructions_rule() -> None:
    body = _body(CORPUS / "meta" / "external-memory-ingestion.md").lower()
    assert "never instructions" in body or "never be followed as instructions" in body
    assert "reference material" in body or "reference data" in body
    for term in ("provenance", "trust level", "fingerprint", "format"):
        assert term in body, f"external-memory-ingestion.md: missing {term}"
