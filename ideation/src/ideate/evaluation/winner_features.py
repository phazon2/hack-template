"""A single scalar for how much a pitch looks like one that wins — and the gate that decides
whether that scalar is allowed to exist yet.

**Why this module is mostly about validation.** An optimisation loop needs a number to climb, and
the number is the whole risk: climb a number that does not track winning and the loop converges
confidently on noise. The Princeton result that agents "commit to weak approaches too fast and
cannot backtrack" is that failure with a research agent attached. So the scoring here is cheap and
the checking is expensive, which is the opposite of the usual ratio and deliberate.

**Why deterministic features and not an LLM judge.** Si et al. (arXiv 2409.04109) measured LLM
evaluators at roughly chance for ranking ideas. A judge that is near chance cannot be the metric an
optimiser climbs, at any price. These features are regexes and counts: free, reproducible, and
auditable line by line, which is what an outer loop needs to run thousands of times.

**Why "similarity to known winners" is not the metric.** It is the obvious formulation and it is a
trap in two directions. Maximising similarity to past winners converges on the mean of past winners
— and duplication, not novelty, is the measured bottleneck in LLM ideation (Si et al.: ~5% of seed
ideas survive deduplication). Winners also win partly by being distinctive, so the target would
erode the thing it is trying to select for. What generalises is *form* — how specifically a thing
is pitched — not *subject matter*. So every feature here reads shape, none reads topic, and
``content_echo`` actively penalises reusing a known winner's domain.

**The gate.** A feature earns a place in the composite only when its AUC confidence interval clears
chance on outcome-labelled data (``validated_features``). Below that bar ``pitch_score`` returns
None rather than a number, because a plausible-looking score is worse than no score: no score stops
an optimiser, a wrong score steers it. Features flagged ``GOODHART_PRONE`` never enter a composite
however well they measure, because they are trivially gameable by the generator being scored.

Labelled data comes from ``ideate gallery``. Every event added enlarges the sample, so the gate
opens on its own once the evidence is there — nothing here needs re-tuning by hand.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from ideate.config import Settings
from ideate.knowledge.loaders import load_corpus

WINNER_HEADING = "WINNERS"
OTHER_HEADING = "LISTED WITHOUT A WINNER LABEL"
_ENTRY = re.compile(r"^- (?P<name>[^:]{1,80}): (?P<pitch>.+)$")

# Below this many labelled examples per side, no feature is trusted whatever it measures: the
# Hanley-McNeil interval at 14 vs 10 is roughly +/- 0.20, wide enough to contain chance for
# anything short of a perfect separator.
MIN_PER_SIDE = 20
CHANCE = 0.5

# Vocabulary that says nothing checkable. Drawn from the unlabelled projects in the observed
# gallery, where it clusters: "turns human signals and context into real-time insights and adaptive
# actions through secure cloud APIs" has a noun in every slot and not one of them can be verified.
ABSTRACT = frozenset(
    """insights seamless adaptive real-time ecosystem platform solution solutions leverage empower
    revolutionize cutting-edge holistic synergy streamline optimize optimizes actionable robust
    scalable innovative transform transforms harness unlock dynamic intelligent smart powerful
    comprehensive end-to-end autonomously autonomous proactive trusted trustworthy signals
    frictionless next-generation state-of-the-art best-in-class world-class""".split()
)

_MOMENT = re.compile(r"^(before|when|after|every|the moment|you |your )", re.I)
_CONTRARIAN = re.compile(r"(everyone is |opposite bet|makes the opposite|but nobody|don't\.|doesn't\.)", re.I)
_SECOND_PERSON = re.compile(r"\byou\b|\byour\b", re.I)
_WORD = re.compile(r"[A-Za-z0-9.\-&']+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def _lower(text: str) -> list[str]:
    return [w.lower().strip(".,;:") for w in _words(text)]


# --------------------------------------------------------------------------- features
def f_abstraction(text: str) -> float:
    """Share of words that are unfalsifiable filler. Lower is better, so this returns 1 - rate."""
    words = _lower(text)
    if not words:
        return 0.0
    return 1.0 - sum(1 for w in words if w in ABSTRACT) / len(words)


def f_moment_open(text: str) -> float:
    """Opens on a situation the reader is standing in, rather than on a market or a category."""
    return 1.0 if _MOMENT.match(text.strip()) else 0.0


def f_contrarian(text: str) -> float:
    """Names the crowded field and bets against it, doing the judge's comparison for them."""
    return 1.0 if _CONTRARIAN.search(text) else 0.0


def f_second_person(text: str) -> float:
    """Addresses the reader directly, which puts them in the scenario instead of beside it."""
    return 1.0 if _SECOND_PERSON.search(text) else 0.0

def f_numeric(text: str) -> float:
    """Contains a specific quantity — a count, a price, a duration — rather than a vague degree."""
    return 1.0 if any(c.isdigit() for c in text) else 0.0


def f_sentences(text: str) -> float:
    """Sentence count. GOODHART_PRONE: a generator told to raise this just adds sentences."""
    return float(len(re.findall(r"[.!?]", text)) or 1)


def f_length(text: str) -> float:
    """Word count. GOODHART_PRONE: trivially inflatable, and it dominates on small samples."""
    return float(len(_words(text)))


FEATURES: dict[str, Callable[[str], float]] = {
    "abstraction": f_abstraction,
    "moment_open": f_moment_open,
    "contrarian": f_contrarian,
    "second_person": f_second_person,
    "numeric": f_numeric,
    "sentences": f_sentences,
    "length": f_length,
}

# Measurable, and still barred from any composite. These rise whenever the text simply gets longer,
# so a generator optimising against them writes padding and scores better for it. They are reported
# so a reader can see them dominating a small sample — which is exactly what they do at 14 vs 10 —
# without that dominance reaching the number anything optimises.
GOODHART_PRONE = frozenset({"sentences", "length"})


# --------------------------------------------------------------------------- labelled data
def split_labelled(texts: list[str]) -> tuple[list[str], list[str]]:
    """Winner pitches and non-winner pitches parsed out of gallery documents.

    A document contributes to both sides or neither: a gallery that lists winners without listing
    anything else gives no negatives, and a metric validated against no negatives is not validated.
    """
    winners: list[str] = []
    others: list[str] = []
    for text in texts:
        bucket: list[str] | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == WINNER_HEADING:
                bucket = winners
                continue
            if stripped == OTHER_HEADING:
                bucket = others
                continue
            if stripped.isupper() and stripped and bucket is not None:
                bucket = None
                continue
            if bucket is None:
                continue
            match = _ENTRY.match(stripped)
            if match:
                pitch = match.group("pitch").strip()
                if pitch and pitch not in bucket:
                    bucket.append(pitch)
    return winners, others


def labelled_from_corpus(settings: Settings) -> tuple[list[str], list[str]]:
    """Every outcome-labelled pitch in the corpus, across all events ``ideate gallery`` has written."""
    try:
        documents = load_corpus(settings.all_corpus_dirs())
    except OSError:
        return [], []
    return split_labelled([d.text for d in documents if d.metadata.get("kind") == "evidence"])


# --------------------------------------------------------------------------- validation
def auc(positive: list[float], negative: list[float]) -> float:
    """P(a random winner scores above a random non-winner); 0.5 is chance."""
    if not positive or not negative:
        return CHANCE
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def auc_interval(area: float, n_pos: int, n_neg: int, z: float = 1.96) -> tuple[float, float]:
    """Hanley-McNeil 95% interval for an AUC.

    This is the whole gate. The point estimate on a small sample is nearly meaningless — 0.74 at
    14 vs 10 carries an interval that reaches from 0.55 to 0.94 — and reporting the point estimate
    alone is how a system talks itself into optimising noise.
    """
    if n_pos < 1 or n_neg < 1:
        return (0.0, 1.0)
    q1 = area / (2 - area) if area < 2 else 0.0
    q2 = 2 * area**2 / (1 + area)
    variance = (area * (1 - area) + (n_pos - 1) * (q1 - area**2) + (n_neg - 1) * (q2 - area**2)) / (n_pos * n_neg)
    se = math.sqrt(max(0.0, variance))
    return (max(0.0, area - z * se), min(1.0, area + z * se))


@dataclass(frozen=True)
class FeatureReport:
    """One feature measured against outcome labels."""

    name: str
    auc: float
    ci_low: float
    ci_high: float
    winner_mean: float
    other_mean: float
    goodhart_prone: bool

    @property
    def separates(self) -> bool:
        """True only when the whole interval clears chance — not when the point estimate does."""
        return self.ci_low > CHANCE

    @property
    def usable(self) -> bool:
        return self.separates and not self.goodhart_prone


def validate(winners: list[str], others: list[str]) -> list[FeatureReport]:
    """Measure every feature against the labels, best-separating first."""
    reports: list[FeatureReport] = []
    for name, fn in FEATURES.items():
        pos = [fn(t) for t in winners]
        neg = [fn(t) for t in others]
        area = auc(pos, neg)
        # A feature can be predictive by being consistently LOWER for winners. Orientation is a
        # property of the feature, not evidence about it, so fold it in before judging the area.
        if area < CHANCE:
            area = 1.0 - area
        low, high = auc_interval(area, len(winners), len(others))
        reports.append(
            FeatureReport(
                name=name,
                auc=area,
                ci_low=low,
                ci_high=high,
                winner_mean=sum(pos) / len(pos) if pos else 0.0,
                other_mean=sum(neg) / len(neg) if neg else 0.0,
                goodhart_prone=name in GOODHART_PRONE,
            )
        )
    return sorted(reports, key=lambda r: (-r.auc, r.name))


def enough_data(winners: list[str], others: list[str]) -> bool:
    """Whether the sample is large enough for any feature to be believed."""
    return min(len(winners), len(others)) >= MIN_PER_SIDE


def validated_features(reports: list[FeatureReport], winners: list[str], others: list[str]) -> list[str]:
    """Features allowed into the composite: enough data, interval clears chance, not gameable."""
    if not enough_data(winners, others):
        return []
    return [r.name for r in reports if r.usable]


def pitch_score(text: str, names: list[str]) -> float | None:
    """Mean of the validated features, 0..1 — or None when nothing has earned the right to score.

    None is the honest answer and the useful one: it stops an optimiser instead of pointing it
    somewhere arbitrary. Callers must handle it rather than defaulting to 0.5, which would be a
    fabricated measurement wearing a number's clothes.
    """
    usable = [n for n in names if n in FEATURES]
    if not usable:
        return None
    values = [min(1.0, max(0.0, FEATURES[n](text))) for n in usable]
    return sum(values) / len(values)


def shortfall(winners: list[str], others: list[str]) -> str:
    """One line saying what is missing before the metric can be trusted."""
    if enough_data(winners, others):
        return ""
    need_w = max(0, MIN_PER_SIDE - len(winners))
    need_o = max(0, MIN_PER_SIDE - len(others))
    return (
        f"{len(winners)} winners + {len(others)} non-winners; need {MIN_PER_SIDE} of each "
        f"({need_w} more winners, {need_o} more non-winners). Run `ideate gallery <event-url>` on "
        "events whose winners are announced."
    )
