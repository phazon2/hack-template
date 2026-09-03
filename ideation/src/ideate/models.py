"""All shared dataclasses for the ideation system, plus serialization helpers.

Rules (docs/DESIGN.md §3):
- stdlib only; nothing here imports other ideate modules.
- every list/dict default uses field(default_factory=...).
- to_dict(obj) is a module-level function; every dataclass also has .to_dict() and
  .from_dict(d) (ignores unknown keys, applies defaults, rebuilds nested dataclasses).
- never use builtin hash() on str/bytes anywhere in the codebase.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import types
import typing
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, ClassVar, TypeVar

TECHNIQUES: tuple[str, ...] = (
    "analogical",
    "assumption_breaking",
    "reverse",
    "scale",
    "combination",
    "direct",
)
BLOCKER_KINDS: tuple[str, ...] = ("config-fixable", "do-it-myself", "genuinely human-only")
CHUNK_KINDS: tuple[str, ...] = ("guidance", "data-source", "archetype", "antipattern", "event", "evidence", "memory")


# --------------------------------------------------------------------------- helpers
def slug(text: str) -> str:
    """lowercase, runs of non-alphanumerics -> '-', strip '-', max 40 chars."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].rstrip("-")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def to_dict(obj: Any) -> Any:
    """Plain-dict form of a dataclass (nested dataclasses become dicts, no type tags)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, list):
        return [to_dict(o) for o in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def _unwrap_optional(tp: Any) -> Any:
    origin = typing.get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return args[0] if len(args) == 1 else tp
    return tp


def _build(tp: Any, value: Any) -> Any:
    """Recursively rebuild `value` according to type annotation `tp`."""
    if value is None:
        return None
    tp = _unwrap_optional(tp)
    origin = typing.get_origin(tp)
    if origin in (list, typing.List):
        (item_tp,) = typing.get_args(tp) or (Any,)
        return [_build(item_tp, v) for v in value] if isinstance(value, list) else value
    if origin in (dict, typing.Dict):
        return dict(value) if isinstance(value, dict) else value
    if isinstance(tp, type) and is_dataclass(tp) and isinstance(value, dict):
        return from_dict(tp, value)
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


T = TypeVar("T")


def from_dict(cls: type[T], d: dict) -> T:
    """Build dataclass `cls` from a dict, ignoring unknown keys and applying defaults."""
    if not isinstance(d, dict):
        raise TypeError(f"{cls.__name__}.from_dict expects a dict, got {type(d).__name__}")
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if not f.init or f.name not in d:
            continue
        kwargs[f.name] = _build(hints.get(f.name, Any), d[f.name])
    return cls(**kwargs)  # type: ignore[call-arg]


class Model:
    """Mixin giving every dataclass .to_dict() / .from_dict()."""

    def to_dict(self) -> dict:
        return to_dict(self)

    @classmethod
    def from_dict(cls, d: dict):
        return from_dict(cls, d)


# --------------------------------------------------------------------------- knowledge
@dataclass
class Document(Model):
    id: str
    title: str
    text: str
    source: str = ""
    metadata: dict = field(default_factory=dict)  # tags: list[str], kind, url, published, authors


@dataclass
class Chunk(Model):
    id: str
    doc_id: str
    text: str
    position: int
    metadata: dict = field(default_factory=dict)  # title, source, kind, tags


@dataclass
class RetrievedChunk(Model):
    chunk: Chunk
    score: float  # score of the LAST stage that touched it
    ranks: dict = field(default_factory=dict)  # 1-based positions per stage: bm25, vector, fused, rerank
    scores: dict = field(default_factory=dict)  # bm25 (raw), vector (cosine), rrf, rerank


# --------------------------------------------------------------------------- run inputs
@dataclass
class HackathonConstraints(Model):
    hours: int = 24
    team_size: int = 3
    judging_criteria: list[str] = field(default_factory=list)  # raw strings, e.g. "innovation:40"
    tech_preferences: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    tracks: list[str] = field(default_factory=list)
    notes: str = ""


# --------------------------------------------------------------------------- agent outputs
@dataclass
class ResearchFindings(Model):
    trends: list[str] = field(default_factory=list)
    case_studies: list[str] = field(default_factory=list)
    pitfalls: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)


@dataclass
class TechnicalAssessment(Model):
    constraints: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    challenges: list[str] = field(default_factory=list)
    breakthroughs: list[str] = field(default_factory=list)
    suggested_stack: list[str] = field(default_factory=list)
    building_blocks: list[str] = field(default_factory=list)  # concrete APIs/datasets/libs with access level
    hour_budget: list[str] = field(default_factory=list)  # setup / walking skeleton / build / integrate / rehearse


@dataclass
class Idea(Model):
    title: str
    description: str
    id: str = ""  # code-filled: idea-{iteration}-{n}
    one_liner: str = ""
    target_user: str = ""
    key_innovation: str = ""
    technique: str = "direct"
    technical_approach: str = ""
    demo_strategy: str = ""
    demo_moment: str = ""
    data_sources: list[str] = field(default_factory=list)
    mvp_scope: list[str] = field(default_factory=list)
    cut_first: list[str] = field(default_factory=list)
    closest_existing: str = ""
    build_hours_estimate: int = 0
    risks: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    parent_id: str | None = None


@dataclass
class CriterionScore(Model):
    name: str
    score: float
    rationale: str = ""


@dataclass
class IdeaEvaluation(Model):
    idea_id: str
    scores: list[CriterionScore] = field(default_factory=list)
    weighted_score: float = 0.0  # code-filled from the rubric (1..5)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    closest_existing: str = ""
    demo_break_risk: str = ""
    disqualified: bool = False
    disqualify_reason: str = ""
    judge: str = ""  # code-filled: persona text or "consensus"

    def score_for(self, name: str, default: float = 3.0) -> float:
        for s in self.scores:
            if s.name == name:
                return s.score
        return default


@dataclass
class PanelVerdict(Model):
    idea_id: str
    evaluations: list[IdeaEvaluation] = field(default_factory=list)
    consensus: IdeaEvaluation = field(default_factory=lambda: IdeaEvaluation(idea_id=""))
    agreement: float = 0.0


@dataclass
class Alternative(Model):
    idea_id: str
    choose_if: str


@dataclass
class Proposal(Model):
    idea_id: str = ""  # code-filled = ranking[0]
    executive_summary: str = ""
    value_proposition: str = ""
    why_this: str = ""
    implementation_plan: list[str] = field(default_factory=list)
    demo_plan: list[str] = field(default_factory=list)
    demo_script: list[str] = field(default_factory=list)
    impact: str = ""
    first_hour_plan: list[str] = field(default_factory=list)
    milestones: list[str] = field(default_factory=list)
    team_split: list[str] = field(default_factory=list)
    cut_list: list[str] = field(default_factory=list)
    pivot_trigger: str = ""
    human_dependencies: list[str] = field(default_factory=list)  # "config-fixable: ..." etc.
    alternatives: list[Alternative] = field(default_factory=list)


@dataclass
class TraceStep(Model):
    agent: str  # canonical tag (DESIGN §9.1)
    provider: str
    model: str  # served model
    requested_model: str = ""
    prompt_sha256: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    request_id: str | None = None
    started_at: str = ""
    stop_reason: str | None = None
    error: str | None = None


# --------------------------------------------------------------------------- run state / result
@dataclass
class IdeationState(Model):
    theme: str
    constraints: HackathonConstraints
    queries: list[str] = field(default_factory=list)
    knowledge: list[RetrievedChunk] = field(default_factory=list)
    memory_context: str = ""
    research: ResearchFindings | None = None
    assessment: TechnicalAssessment | None = None
    ideas: list[Idea] = field(default_factory=list)
    verdicts: list[PanelVerdict] = field(default_factory=list)
    ranking: list[str] = field(default_factory=list)
    proposal: Proposal | None = None
    critiques: list[str] = field(default_factory=list)
    iteration: int = 0
    retrieval_rounds: int = 0
    coverage_gaps: list[str] = field(default_factory=list)
    retrieve_more_added: int = 0
    visited: list[str] = field(default_factory=list)

    def verdict_for(self, idea_id: str) -> PanelVerdict | None:
        for v in self.verdicts:
            if v.idea_id == idea_id:
                return v
        return None

    def idea_for(self, idea_id: str) -> Idea | None:
        for i in self.ideas:
            if i.id == idea_id:
                return i
        return None


@dataclass
class IdeationResult(Model):
    run_id: str
    created_at: str
    version: str
    theme: str
    constraints: HackathonConstraints
    provider: str
    model: str
    settings: dict = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)
    knowledge: list[RetrievedChunk] = field(default_factory=list)
    research: ResearchFindings | None = None
    assessment: TechnicalAssessment | None = None
    ideas: list[Idea] = field(default_factory=list)
    verdicts: list[PanelVerdict] = field(default_factory=list)
    ranking: list[str] = field(default_factory=list)
    proposal: Proposal | None = None
    iterations: int = 0
    retrieval_rounds: int = 0
    coverage_gaps: list[str] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    is_placeholder: bool = False

    def idea_for(self, idea_id: str) -> Idea | None:
        for i in self.ideas:
            if i.id == idea_id:
                return i
        return None

    def verdict_for(self, idea_id: str) -> PanelVerdict | None:
        for v in self.verdicts:
            if v.idea_id == idea_id:
                return v
        return None


# --------------------------------------------------------------------------- memory
@dataclass
class Outcome(Model):
    hackathon: str
    idea_title: str
    idea_summary: str = ""
    id: str = ""
    placed: str | None = None
    success: bool = False
    judge_feedback: str = ""
    notes: str = ""
    what_was_cut: str = ""
    demo_worked: bool | None = None
    run_id: str | None = None
    idea_id: str | None = None
    recorded_at: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = new_id("out")


@dataclass
class Pattern(Model):
    kind: str  # "success" | "failure"
    text: str
    tags: list[str] = field(default_factory=list)
    source_outcome_id: str = ""
    id: str = ""
    provider: str = ""  # "mock" patterns are quarantined from real runs
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"pat-{sha256_hex(self.source_outcome_id + self.text)[:12]}"


ALL_MODELS: tuple[type, ...] = (
    Document, Chunk, RetrievedChunk, HackathonConstraints, ResearchFindings, TechnicalAssessment,
    Idea, CriterionScore, IdeaEvaluation, PanelVerdict, Alternative, Proposal, TraceStep,
    IdeationState, IdeationResult, Outcome, Pattern,
)
