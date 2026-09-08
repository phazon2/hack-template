"""Rank ideas by comparison against real winners, not by scoring them against a rubric.

Si et al. (arXiv 2409.04109) benchmarked LLM evaluators against human review scores and found
direct rubric scoring at chance — GPT-4o scored 50.0 where random is 50.0, Claude-3.5 51.7,
against humans at 66 to 72. The one shape that reached non-trivial accuracy was pairwise
comparison calibrated against references with known outcomes.

This system has such references: taglines from submissions that actually won, collected by
``ideate gallery``. So ranking asks a comparative question with a calibrated anchor — would this
idea beat a project that really won — instead of asking for a score out of five.

The panel keeps its job of catching disqualifications and writing critiques. It just stops being
the thing that picks the winner, because the evidence says it cannot do that reliably.
"""

from __future__ import annotations

import re

from ideate.config import Settings
from ideate.knowledge.loaders import load_corpus
from ideate.llm.base import LLM, LLMError, LLMRequest
from ideate.llm.schema import arr, enum, int_, obj, str_
from ideate.models import Idea

PAIRWISE_TAG = "pairwise"
MAX_REFERENCES = 6
MIN_IDEAS_TO_RANK = 2
# A winners block in a gallery document, written by meta.gallery.as_document.
_WINNER_LINE = re.compile(r"^- (?P<name>[^:]{1,80}): (?P<tagline>.+)$")
_WINNER_HEADING = "WINNERS"
_OTHER_HEADING = "LISTED WITHOUT A WINNER LABEL"

PAIRWISE_SYSTEM = (
    "You compare hackathon submissions head to head. You are shown projects that really won their "
    "events and a set of candidate ideas. For each candidate, judge how many of the real winners it "
    "would beat if a tired judge saw both and had to pick one. Judge them as a judge would: on what "
    "is visible in the pitch, how specific and checkable it is, and whether it would survive being "
    "described from memory to another judge. Do not reward ambition that is not demonstrable, and do "
    "not penalise a modest idea that lands cleanly."
)


def winner_references(texts: list[str], limit: int = MAX_REFERENCES) -> list[str]:
    """Winner taglines parsed out of gallery documents, in document order, deduplicated.

    Only lines under the winners heading are taken: a gallery also lists the projects that were
    not labelled, and anchoring on those would calibrate the ranking against the wrong outcome.
    """
    found: list[str] = []
    for text in texts:
        in_winners = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == _WINNER_HEADING:
                in_winners = True
                continue
            if stripped == _OTHER_HEADING or (stripped.isupper() and stripped and in_winners and stripped != _WINNER_HEADING):
                in_winners = False
                continue
            if not in_winners:
                continue
            match = _WINNER_LINE.match(stripped)
            if match:
                tagline = match.group("tagline").strip()
                if tagline and tagline not in found:
                    found.append(f"{match.group('name').strip()}: {tagline}")
    return found[:limit]


def references_from_corpus(settings: Settings, limit: int = MAX_REFERENCES) -> list[str]:
    """Winner taglines read from whole corpus documents, not from retrieved chunks.

    Calibration anchors are not a relevance question: they are a fixed set the ranking is measured
    against, so they are loaded entire like the charter. Going through the chunk index would split
    a winners block across chunks and return whichever fragment happened to match the query, which
    is how this returned nothing at all in its first form.

    Reads every configured corpus directory, so galleries written by ``ideate gallery`` are picked
    up automatically alongside the bundled ones.
    """
    try:
        documents = load_corpus(settings.all_corpus_dirs())
    except OSError:
        return []
    texts = [d.text for d in documents if d.metadata.get("kind") == "evidence"]
    return winner_references(texts, limit)


def pairwise_prompt(ideas: list[Idea], references: list[str]) -> str:
    """The candidates and the real winners they are being measured against."""
    winners = "\n".join(f"W{n}. {ref}" for n, ref in enumerate(references, 1))
    candidates = "\n\n".join(
        f"[{idea.id}] {idea.title} — {idea.one_liner}\n"
        f"    user: {idea.target_user}\n"
        f"    demo moment: {idea.demo_moment}\n"
        f"    innovation: {idea.key_innovation}"
        for idea in ideas
    )
    return (
        f"Projects that actually won their hackathons ({len(references)}):\n{winners}\n\n"
        f"Candidate ideas:\n\n{candidates}\n\n"
        f"For each candidate, give beats = how many of the {len(references)} real winners it would "
        "beat head to head, and one sentence of reasoning naming the winner it would most struggle "
        "against. Use the full range; if a candidate would beat none of them, say 0."
    )


def pairwise_scores(
    ideas: list[Idea],
    references: list[str],
    llm: LLM,
    max_tokens: int = 16000,
    effort: str = "medium",
) -> dict[str, int]:
    """Wins against the reference winners, per idea id. Empty when it cannot be computed.

    An empty result is the caller's signal to fall back to the panel's own ordering, so a failed
    or impossible comparison degrades to the previous behaviour instead of producing a fake rank.
    """
    if len(ideas) < MIN_IDEAS_TO_RANK or not references:
        return {}
    ids = [idea.id for idea in ideas]
    schema = obj(
        {
            "comparisons": arr(
                obj({"idea_id": enum(ids), "beats": int_(0, len(references)), "hardest": str_()}),
                len(ids),
                len(ids),
            )
        }
    )
    request = LLMRequest(
        system=PAIRWISE_SYSTEM,
        prompt=pairwise_prompt(ideas, references),
        tag=PAIRWISE_TAG,
        json_schema=schema,
        max_tokens=max_tokens,
        effort=effort,
    )
    try:
        data = llm.complete(request).data
    except LLMError:
        return {}
    raw = data if isinstance(data, dict) else {}

    scores: dict[str, int] = {}
    for row in raw.get("comparisons") or []:
        idea_id = row.get("idea_id")
        if idea_id in set(ids) and idea_id not in scores:
            scores[idea_id] = max(0, min(int(row.get("beats") or 0), len(references)))
    return scores if len(scores) == len(ids) else {}
