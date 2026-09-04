"""Judging rubric: criteria with weights and 1/3/5 anchors (docs/DESIGN.md §8.1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ideate.evaluation import scoring
from ideate.models import HackathonConstraints, slug

ANCHOR_LEVELS: tuple[int, ...] = (1, 3, 5)
FEASIBILITY = "feasibility"
FEASIBILITY_SHARE = 0.15  # share of the total weight feasibility gets when a custom rubric omits it
DEFAULT_WEIGHT = 1.0


@dataclass
class Criterion:
    """One rubric line: ``anchors`` describe what a 1, a 3 and a 5 look like."""

    name: str
    weight: float
    description: str
    anchors: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": self.weight,
            "description": self.description,
            "anchors": {int(k): v for k, v in self.anchors.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Criterion":
        """Rebuild from a dict; anchor keys are coerced with ``int()`` (JSON turns them into strings)."""
        return cls(
            name=str(d["name"]),
            weight=float(d.get("weight", DEFAULT_WEIGHT)),
            description=str(d.get("description", "")),
            anchors={int(k): str(v) for k, v in d.get("anchors", {}).items()},
        )


def _criterion(name: str, weight: float, description: str, one: str, three: str, five: str) -> Criterion:
    return Criterion(name=name, weight=weight, description=description, anchors={1: one, 3: three, 5: five})


DEFAULT_RUBRIC_CRITERIA: tuple[Criterion, ...] = (
    _criterion(
        "novelty",
        0.30,
        "How new the combination is to the judges of this event.",
        "exists as a common product or tutorial; judges have seen it at this event before",
        "known pattern with one real twist or a new domain",
        "judges have not seen this combination; the key innovation is one sentence and it IS the demo",
    ),
    _criterion(
        FEASIBILITY,
        0.25,
        "Whether this team can build a demoable slice in the time available.",
        "needs more than {hours}h for {team_size} people, or depends on an account, signup or hardware the team lacks",
        "vertical slice buildable in ~60% of {hours}h with a plausible cut list",
        "walking skeleton demoable by 25% of {hours}h using named APIs/datasets that need no account",
    ),
    _criterion(
        "impact",
        0.25,
        "Whether a named user with a named pain gets a visible benefit.",
        "no concrete user named",
        "a named user with a named pain; benefit plausible",
        "a named user, a named pain, and a measurable before/after the demo can show",
    ),
    _criterion(
        "demoability",
        0.20,
        "Whether the aha moment lands live, fast and without setup.",
        "needs a slide or explanation to be understood",
        "works live but the aha takes more than 90 seconds",
        "the demo moment lands in <= 90 seconds, has a recorded fallback, and needs no login",
    ),
)

# Canonical criteria that judging-criteria strings can map to but the default rubric omits.
_EXTRA_CRITERIA: dict[str, Criterion] = {
    "design": _criterion(
        "design",
        DEFAULT_WEIGHT,
        "Whether the interface makes the demo path obvious.",
        "confusing or unstyled; a first-time user cannot find the demo path",
        "clean, conventional interface that does not get in the way",
        "the interface itself makes the aha obvious without any explanation",
    ),
    "business": _criterion(
        "business",
        DEFAULT_WEIGHT,
        "Whether someone would adopt or pay for it, and how they would find it.",
        "no plausible buyer or adopter and no path to the first users",
        "a plausible buyer or adopter and a sketch of how they find it",
        "a named buyer with an existing budget and a concrete path to the first hundred users",
    ),
}

GENERIC_ANCHORS: dict[int, str] = {
    1: "clearly fails this criterion",
    3: "adequate on this criterion; nothing a judge would remark on",
    5: "outstanding on this criterion; a judge would cite it as a reason to win",
}

# (case-insensitive substring keywords, canonical criterion name); first matching row wins.
KEYWORD_TABLE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("innovation", "novel", "original", "creativ"), "novelty"),
    (("feasib", "technical", "complexity", "execution"), FEASIBILITY),
    (("impact", "value", "useful", "potential"), "impact"),
    (("demo", "presentation", "pitch", "polish"), "demoability"),
    (("design", "ux", "usability"), "design"),
    (("business", "market", "viab"), "business"),
)


# Every criterion a judging-criteria string can map to, by canonical name.
CANONICAL_CRITERIA: dict[str, Criterion] = {c.name: c for c in DEFAULT_RUBRIC_CRITERIA} | _EXTRA_CRITERIA


def _fresh(base: Criterion, weight: float) -> Criterion:
    """A copy of a canonical criterion carrying ``weight``."""
    return Criterion(base.name, weight, base.description, dict(base.anchors))


def _substitute(text: str, constraints: HackathonConstraints) -> str:
    return text.replace("{hours}", str(constraints.hours)).replace("{team_size}", str(constraints.team_size))


@dataclass
class Rubric:
    """An ordered list of criteria; weights need not sum to 1 (scoring normalises them)."""

    criteria: list[Criterion] = field(default_factory=list)

    def names(self) -> list[str]:
        """Criterion names in rubric order."""
        return [c.name for c in self.criteria]

    def weights(self) -> dict[str, float]:
        """Raw (un-normalised) weight per criterion, in rubric order."""
        return {c.name: c.weight for c in self.criteria}

    def weighted_score(self, scores: dict[str, float]) -> float:
        """Weighted 1..5 score; criteria absent from ``scores`` count as 3.0."""
        return scoring.weighted_score(scores, self.weights())

    def reweighted(self, emphasis: dict[str, float]) -> "Rubric":
        """A NEW rubric whose weights are multiplied by ``emphasis`` and renormalised.

        Unknown names in ``emphasis`` are ignored and the receiver is never mutated. The total
        weight is preserved, so only the balance between criteria changes (DESIGN-META §18.9).
        """
        criteria = [Criterion(c.name, c.weight, c.description, dict(c.anchors)) for c in self.criteria]
        total = sum(c.weight for c in criteria)
        for criterion in criteria:
            criterion.weight *= float(emphasis.get(criterion.name, DEFAULT_WEIGHT))
        scaled_total = sum(c.weight for c in criteria)
        if total <= 0 or scaled_total <= 0:
            return Rubric(criteria=[Criterion(c.name, c.weight, c.description, dict(c.anchors)) for c in self.criteria])
        for criterion in criteria:
            criterion.weight *= total / scaled_total
        return Rubric(criteria=criteria)

    def to_prompt(self, constraints: HackathonConstraints | None = None) -> str:
        """Rubric text for a judge prompt, with ``{hours}``/``{team_size}`` filled from ``constraints``."""
        c = constraints or HackathonConstraints()
        total = sum(cr.weight for cr in self.criteria)
        lines = ["Scoring rubric (score each criterion 1-5; weights are percentages of the final score):"]
        for criterion in self.criteria:
            share = (criterion.weight / total * 100) if total > 0 else 0.0
            lines.append(f"- {criterion.name} ({share:.0f}%): {_substitute(criterion.description, c)}")
            for level in ANCHOR_LEVELS:
                if level in criterion.anchors:
                    lines.append(f"    {level} = {_substitute(criterion.anchors[level], c)}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"criteria": [c.to_dict() for c in self.criteria]}

    @classmethod
    def from_dict(cls, d: dict) -> "Rubric":
        return cls(criteria=[Criterion.from_dict(c) for c in d.get("criteria", [])])

    @classmethod
    def from_judging_criteria(cls, items: list[str] | str) -> "Rubric":
        """Build a rubric from ``name[:weight]`` strings (a comma-joined string is also accepted).

        Names map to canonical criteria through ``KEYWORD_TABLE``; unknown names become slug
        criteria with generic anchors; duplicates merge by adding weights; feasibility is
        appended at 15% of the total when absent; an empty input yields ``DEFAULT_RUBRIC``.
        """
        raw_items = [items] if isinstance(items, str) else list(items)
        parts = [part.strip() for item in raw_items for part in str(item).split(",") if part.strip()]
        if not parts:
            return cls(criteria=list(DEFAULT_RUBRIC_CRITERIA))
        merged: dict[str, Criterion] = {}
        for part in parts:
            name, weight = _parse_item(part)
            criterion = _resolve(name, weight)
            if criterion.name in merged:
                merged[criterion.name].weight += weight
            else:
                merged[criterion.name] = criterion
        criteria = list(merged.values())
        if FEASIBILITY not in merged:
            total = sum(c.weight for c in criteria)
            criteria.append(_fresh(CANONICAL_CRITERIA[FEASIBILITY], total * FEASIBILITY_SHARE / (1 - FEASIBILITY_SHARE)))
        return cls(criteria=criteria)


def _parse_item(item: str) -> tuple[str, float]:
    """Split ``name[:weight]``; a missing weight is 1.0, a malformed one is a ValueError."""
    name, sep, weight_text = item.partition(":")
    name = name.strip()
    if not name:
        raise ValueError(f"judging criterion has no name: {item!r}")
    if not sep or not weight_text.strip():
        return name, DEFAULT_WEIGHT
    try:
        weight = float(weight_text)
    except ValueError as e:
        raise ValueError(f"judging criterion {item!r}: weight must be a number") from e
    if weight <= 0:
        raise ValueError(f"judging criterion {item!r}: weight must be positive")
    return name, weight


def _resolve(name: str, weight: float) -> Criterion:
    """Map a raw criterion name to a fresh Criterion carrying ``weight``."""
    lowered = name.lower()
    for keywords, canonical in KEYWORD_TABLE:
        if any(keyword in lowered for keyword in keywords):
            return _fresh(CANONICAL_CRITERIA[canonical], weight)
    return Criterion(slug(name) or "criterion", weight, f"Judging criterion '{name}' as stated by the event.", dict(GENERIC_ANCHORS))


DEFAULT_RUBRIC = Rubric(criteria=list(DEFAULT_RUBRIC_CRITERIA))
