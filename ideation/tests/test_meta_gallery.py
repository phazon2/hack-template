"""Galleries: winners kept beside their neighbours.

A gallery is the only evidence here with the outcome attached, so the parsing has to be exact
about which projects carried the label. Every test injects the opener; nothing reaches Devpost.
"""

from __future__ import annotations

import json

import pytest

from ideate.meta.fetch import FetchError
from ideate.meta.gallery import (
    MIN_GALLERY_CHARS,
    Gallery,
    Submission,
    as_document,
    discover,
    fetch_gallery,
    gallery_url,
    parse_gallery,
    sweep,
)

PAGE = """Connect with the participants

Filter submissions

AegisFlow

The AI investigates, then stops. A human keeps the pen.

Winner

Signet

Anyone can check it with dig and openssl.

Winner

Sensentia

Turns human signals into adaptive actions through secure cloud APIs.

DealProof

AI can draft the deal. DealProof proves it

1 – 24 of 315
"""


def _padded(text: str) -> str:
    """Gallery text long enough to pass the rendered-page gate."""
    return text + "\n" + ("filler line for length. " * 40)


# --------------------------------------------------------------------------- parsing
def test_winners_are_separated_from_their_neighbours():
    g = parse_gallery(PAGE, "Test Event", "https://x.devpost.com/project-gallery")
    assert [s.name for s in g.winners] == ["AegisFlow", "Signet"]
    assert [s.name for s in g.others] == ["Sensentia", "DealProof"]
    assert g.has_outcomes


def test_taglines_survive_intact():
    g = parse_gallery(PAGE, "t", "u")
    assert g.winners[1].tagline == "Anyone can check it with dig and openssl."
    assert g.others[0].tagline.startswith("Turns human signals")


def test_pagination_furniture_is_not_read_as_a_project():
    g = parse_gallery(PAGE, "t", "u")
    assert all("1 – 24" not in s.name for s in g.submissions)
    assert len(g.submissions) == 4


def test_a_winner_with_no_tagline_is_still_a_winner():
    text = "Filter submissions\n\nQuietProject\n\nWinner\n\nOther\n\nA tagline\n"
    g = parse_gallery(text, "t", "u")
    assert [s.name for s in g.winners] == ["QuietProject"]
    assert g.winners[0].tagline == ""


def test_a_gallery_with_no_announced_winners_says_so():
    text = "Filter submissions\n\nAlpha\n\nOne tagline\n\nBeta\n\nAnother tagline\n"
    g = parse_gallery(text, "t", "u")
    assert not g.has_outcomes and len(g.others) == 2


# --------------------------------------------------------------------------- fetching
def test_gallery_url_is_built_from_the_event_url():
    assert gallery_url("https://x.devpost.com") == "https://x.devpost.com/project-gallery"
    assert gallery_url("https://x.devpost.com/") == "https://x.devpost.com/project-gallery"


def test_an_unrendered_shell_page_is_refused_not_parsed_as_empty():
    """Many Devpost galleries return a shell; treating that as 'no winners' would be a lie."""
    with pytest.raises(FetchError, match="rendered no listing"):
        fetch_gallery("https://x.devpost.com", opener=lambda _: b"<html><body>tiny</body></html>")


def test_fetch_gallery_parses_a_rendered_page():
    g = fetch_gallery(
        "https://x.devpost.com",
        title="Event",
        opener=lambda _: f"<html><body><p>{_padded(PAGE)}</p></body></html>".encode(),
    )
    assert len(g.winners) == 2 and g.url.endswith("/project-gallery")


def test_discover_reads_the_public_index():
    payload = json.dumps({"hackathons": [
        {"title": "Alpha", "url": "https://a.devpost.com"},
        {"title": "NoUrl"},
    ]}).encode()
    events = discover("agents", opener=lambda _: payload)
    assert [e["title"] for e in events] == ["Alpha"]  # entries without a URL are unusable


def test_discover_rejects_a_non_json_index():
    with pytest.raises(FetchError, match="not JSON"):
        discover(opener=lambda _: b"<html>404</html>")


# --------------------------------------------------------------------------- sweeping
def test_sweep_reports_what_it_skipped_without_overclaiming():
    """Silence would read as 'nothing found', and 'no winners' would assert more than was seen."""
    index = json.dumps({"hackathons": [
        {"title": "Announced", "url": "https://win.devpost.com"},
        {"title": "Pending", "url": "https://pending.devpost.com"},
        {"title": "Shell", "url": "https://shell.devpost.com"},
    ]}).encode()
    pending = _padded("Filter submissions\n\nAlpha\n\nA tagline\n")

    def opener(url: str) -> bytes:
        if "devpost.com/api" in url:
            return index
        if url.startswith("https://win."):
            return _padded(PAGE).encode()
        if url.startswith("https://pending."):
            return pending.encode()
        return b"shell"

    found, skipped = sweep("agents", opener=opener)
    assert [g.title for g in found] == ["Announced"]
    reasons = dict(skipped)
    # Never "no winners announced": organisers often announce in Discord or by email and
    # leave the gallery untouched, so the page is all that was actually observed.
    assert reasons["Pending"] == "no winner labels on the gallery page"
    assert "rendered no listing" in reasons["Shell"]


def test_sweep_respects_the_limit():
    index = json.dumps({"hackathons": [
        {"title": f"E{i}", "url": f"https://e{i}.devpost.com"} for i in range(10)
    ]}).encode()
    seen: list[str] = []

    def opener(url: str) -> bytes:
        seen.append(url)
        return index if "devpost.com/api" in url else b"shell"

    sweep("q", limit=3, opener=opener)
    assert len([u for u in seen if "project-gallery" in u]) == 3


# --------------------------------------------------------------------------- document
def test_the_document_keeps_both_groups_and_states_the_sampling_caveat():
    g = parse_gallery(PAGE, "Test Event", "https://x.devpost.com/project-gallery")
    doc = as_document(g)
    assert "WINNERS" in doc.text and "LISTED WITHOUT A WINNER LABEL" in doc.text
    assert "AegisFlow" in doc.text and "Sensentia" in doc.text
    # The caveat has to travel with the data, or a later reader over-reads the comparison.
    assert "not a fair sample" in doc.text
    assert doc.url == "https://x.devpost.com/project-gallery"
    assert "winners" in doc.tags


def test_a_gallery_without_winners_is_never_written_as_evidence():
    g = Gallery(title="t", url="u", submissions=[Submission("A", "b", False)])
    with pytest.raises(FetchError, match="no announced winners"):
        as_document(g)


def test_min_gallery_chars_is_stated_once():
    assert MIN_GALLERY_CHARS == 800
