"""Content checks for the bundled seed corpus (docs/DESIGN.md §14). Stdlib only, no ideate imports."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[1] / "src" / "ideate" / "corpus"
ALLOWED_KINDS = {"guidance", "data-source", "archetype", "antipattern", "event", "evidence"}
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
MIN_WORDS = 400
MAX_WORDS = 1200


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


def test_at_least_twelve_documents() -> None:
    assert len(DOCS) >= 12
    assert EXPECTED_FILES <= {p.name for p in DOCS}


def test_readmes_exist_and_document_the_contract() -> None:
    top = (CORPUS / "README.md").read_text(encoding="utf-8")
    event = (CORPUS / "event" / "README.md").read_text(encoding="utf-8")
    for key in ("title", "tags", "kind", "source"):
        assert f"{key}" in top
    assert "kind: event" in event


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


def test_no_invented_statistics() -> None:
    """Percentages are allowed only as clock fractions (10%, 25%, 60%, 70%, 80%) — never as claims."""
    allowed = {"10%", "25%", "60%", "70%", "80%"}
    for path in DOCS:
        found = set(re.findall(r"\d+(?:\.\d+)?%", _body(path)))
        assert found <= allowed, f"{path.name}: unexpected percentages {found - allowed}"
