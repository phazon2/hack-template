"""Improvement loop: turn a recorded outcome into reusable patterns (docs/DESIGN.md §10)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ideate.llm.base import LLM, LLMRequest
from ideate.llm.schema import arr, enum, obj, str_
from ideate.memory.store import MemoryStore
from ideate.models import Outcome, Pattern

LEARN_TAG = "learn"
LEARN_EFFORT = "medium"  # "effort light" (Settings.effort_light default)
PATTERN_KINDS = ("success", "failure")
LEARN_SCHEMA = obj(
    {
        "patterns": arr(
            obj({"kind": enum(list(PATTERN_KINDS)), "text": str_(), "tags": arr(str_(), 1, 5)}),
            1,
            6,
        )
    }
)
LEARN_SYSTEM = (
    "You distil hackathon outcomes into short, reusable rules for future ideation runs. "
    "Each pattern is a 'success' rule to leverage or a 'failure' rule to avoid, stated as one "
    "concrete sentence about scope, the demo, or data sources. Do not invent facts that are not "
    "in the outcome; do not restate the idea itself."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def outcome_prompt(outcome: Outcome) -> str:
    """The user prompt for ``learn``: every recorded field of the outcome plus the ask."""
    rows = [
        ("Hackathon", outcome.hackathon),
        ("Idea", outcome.idea_title),
        ("Summary", outcome.idea_summary),
        ("Placed", outcome.placed or "not placed"),
        ("Success", "yes" if outcome.success else "no"),
        ("Demo worked", "unknown" if outcome.demo_worked is None else ("yes" if outcome.demo_worked else "no")),
        ("Judge feedback", outcome.judge_feedback),
        ("What was cut", outcome.what_was_cut),
        ("Notes", outcome.notes),
    ]
    body = "\n".join(f"{label}: {value or '-'}" for label, value in rows)
    return (
        f"Recorded hackathon outcome:\n{body}\n\n"
        "Write 1-6 patterns. Each is either a 'success' rule (what to leverage again) or a "
        "'failure' rule (what to avoid), about scope, the demo, or data sources. Tag each pattern "
        f"with 1-5 short lowercase topic tags; always include the tag {outcome.hackathon!r}."
    )


def learn_from_outcome(
    outcome: Outcome,
    llm: LLM,
    memory: MemoryStore,
    now: Callable[[], str] | None = None,
    effort: str = LEARN_EFFORT,
) -> list[Pattern]:
    """One ``learn`` call; persists the outcome (once) and the resulting patterns; returns them."""
    clock = now or _utc_now
    if not outcome.recorded_at:
        outcome.recorded_at = clock()
    response = llm.complete(
        LLMRequest(system=LEARN_SYSTEM, prompt=outcome_prompt(outcome), tag=LEARN_TAG, json_schema=LEARN_SCHEMA, effort=effort)
    )
    data = response.data if isinstance(response.data, dict) else {}
    patterns: list[Pattern] = []
    for raw in data.get("patterns", []):
        if not isinstance(raw, dict):
            continue
        tags = [str(t) for t in raw.get("tags", []) if str(t)]
        if outcome.hackathon not in tags:
            tags.append(outcome.hackathon)
        patterns.append(
            Pattern(
                kind=str(raw.get("kind", "failure")),
                text=str(raw.get("text", "")),
                tags=tags,
                source_outcome_id=outcome.id,
                provider=response.provider,
                created_at=clock(),
            )
        )
    if all(o.id != outcome.id for o in memory.outcomes()):
        memory.add_outcome(outcome)
    for pattern in patterns:
        memory.add_pattern(pattern)
    return patterns


def memory_context_for(theme: str, memory: MemoryStore, k: int = 5, include_mock: bool = False) -> str:
    """``Leverage: ...`` / ``Avoid: ...`` bullets from the patterns relevant to ``theme``; "" when none."""
    patterns = memory.relevant_patterns(theme, k=k, include_mock=include_mock)
    lines = [f"- {'Leverage' if p.kind == 'success' else 'Avoid'}: {p.text}" for p in patterns]
    return "\n".join(lines)
