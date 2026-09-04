"""ReflectorAgent: what this run taught the system about its own process (DESIGN-META §18.3)."""

from __future__ import annotations

from typing import Callable

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block, utc_now
from ideate.llm.schema import arr, enum, obj, str_
from ideate.meta.ingest import TRUST_NOTE
from ideate.models import (
    META_PATTERN_KINDS,
    PROBLEM_TYPES,
    TECHNIQUES,
    IdeationState,
    MetaPattern,
    RunReflection,
    TraceStep,
    sha256_hex,
)

REFLECTOR_TAG = "reflector"
TOP_N = 3
GLOBAL_SCOPE = "global"
PATTERN_SCOPES: tuple[str, ...] = (GLOBAL_SCOPE,) + PROBLEM_TYPES

REFLECTOR_SYSTEM = (
    "You are the meta-reviewer of a hackathon ideation system. You judge the RUN, not the ideas: "
    "which parts of the process earned their cost, which produced nothing, and what the system "
    "should do differently next time. Base every claim on the run data shown; when the data does "
    "not support a claim, say so instead of inventing one. Meta-patterns are short reusable rules "
    "about how the system works, never facts about the world, and never statistics. " + TRUST_NOTE
)

REFLECTOR_SCHEMA = obj(
    {
        "what_worked": arr(str_(), 1, 4),
        "what_failed": arr(str_(), 0, 4),
        "process_changes": arr(str_(), 1, 4),
        "signal_quality": str_(),
        "winning_technique": enum(list(TECHNIQUES)),
        "judge_disagreement": str_(),
        "wasted_effort": arr(str_(), 0, 3),
        "meta_patterns": arr(
            obj(
                {
                    "kind": enum(list(META_PATTERN_KINDS)),
                    "text": str_(),
                    "scope": enum(list(PATTERN_SCOPES)),
                    "tags": arr(str_(), 1, 4),
                }
            ),
            1,
            5,
        ),
    }
)


# --------------------------------------------------------------------------- run data (code, not LLM)
def agent_costs(trace: list[TraceStep]) -> list[tuple[str, int, int, int]]:
    """``(agent, calls, input_tokens, output_tokens)`` per agent, in first-call order."""
    totals: dict[str, list[int]] = {}
    for step in trace:
        row = totals.setdefault(step.agent, [0, 0, 0])
        row[0] += 1
        row[1] += step.input_tokens
        row[2] += step.output_tokens
    return [(agent, row[0], row[1], row[2]) for agent, row in totals.items()]


def lowest_criterion(state: IdeationState) -> tuple[str, float] | None:
    """The criterion with the lowest mean consensus score across every judged idea, or ``None``."""
    scores: dict[str, list[float]] = {}
    for verdict in state.verdicts:
        for score in verdict.consensus.scores:
            scores.setdefault(score.name, []).append(score.score)
    if not scores:
        return None
    means = [(name, sum(values) / len(values)) for name, values in scores.items()]
    means.sort(key=lambda pair: (pair[1], pair[0]))
    return means[0]


def derived_run_id(state: IdeationState) -> str:
    """A deterministic id for a run that was not given one (no wall clock, no uuid)."""
    material = state.theme + "|" + "|".join(idea.id for idea in state.ideas)
    return f"run-{sha256_hex(material)[:12]}"


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def strategy_block(state: IdeationState) -> str:
    """What the strategist planned, or a line saying no strategist ran."""
    strategy = state.strategy
    if strategy is None:
        return "- (no strategist ran; the default process was used)"
    return (
        f"- problem_type: {strategy.problem_type}\n"
        f"- emphasis_techniques: {', '.join(strategy.emphasis_techniques) or '(none)'}\n"
        f"- retrieval_angles: {', '.join(strategy.retrieval_angles) or '(none)'}\n"
        f"- rubric_emphasis: {', '.join(f'{k} x{v}' for k, v in strategy.rubric_emphasis.items()) or '(default weights)'}\n"
        f"- planned rounds: {strategy.rounds or 'settings default'}\n"
        f"- watch_for: {', '.join(strategy.watch_for) or '(none)'}\n"
        f"- framing: {strategy.framing or '(none given)'}"
    )


def cost_block(ctx: RunContext) -> str:
    """One line per agent: calls and token totals taken from the trace."""
    rows = agent_costs(ctx.trace)
    if not rows:
        return "- (no calls recorded)"
    return "\n".join(
        f"- {agent}: {calls} call(s), {tokens_in} input tokens, {tokens_out} output tokens"
        for agent, calls, tokens_in, tokens_out in rows
    )


def outcome_block(state: IdeationState) -> str:
    """The top-3 ideas with their technique, consensus score and panel agreement."""
    lines = []
    for idea_id in state.ranking[:TOP_N]:
        idea = state.idea_for(idea_id)
        verdict = state.verdict_for(idea_id)
        if idea is None or verdict is None:
            continue
        lines.append(
            f"- {idea.id} (technique={idea.technique}): weighted score "
            f"{verdict.consensus.weighted_score:.2f}, panel agreement {verdict.agreement:.2f}"
        )
    return "\n".join(lines) if lines else "- (no ranked ideas)"


def reflector_prompt(state: IdeationState, ctx: RunContext) -> str:
    """User prompt: only run data computed by code, plus the ask."""
    lowest = lowest_criterion(state)
    lowest_line = (
        f"{lowest[0]} (mean {lowest[1]:.2f})" if lowest is not None else "(no criterion scores recorded)"
    )
    parts = [
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}",
        f"The plan the strategist chose:\n{strategy_block(state)}",
        f"Cost of the run, per agent:\n{cost_block(ctx)}",
        (
            "Retrieval:\n"
            f"- retrieval rounds: {state.retrieval_rounds}\n"
            f"- knowledge snippets shown: {len(state.knowledge)}\n"
            f"- coverage gaps the research agent reported:\n{_bullets(state.coverage_gaps)}"
        ),
        (
            "Idea funnel:\n"
            f"- creativity rounds: {state.iteration}\n"
            f"- ideas kept: {len(state.ideas)}\n"
            f"- ideas dropped as invalid: {state.dropped_invalid}\n"
            f"- ideas dropped as duplicates: {state.dropped_duplicate}"
        ),
        f"Top-ranked ideas:\n{outcome_block(state)}",
        f"Lowest-scoring criterion across the whole run: {lowest_line}",
        f"Critiques the panel kept returning:\n{_bullets(state.critiques)}",
        (
            "Write the reflection:\n"
            "- what_worked / what_failed: about the PROCESS, each tied to a number above\n"
            "- process_changes: concrete changes to how this system runs next time\n"
            "- signal_quality: did the retrieved knowledge actually change the ideas, or not\n"
            "- winning_technique: the technique of the ideas that ranked highest\n"
            "- judge_disagreement: what the agreement numbers say; when they are uniform, say so\n"
            "- wasted_effort: work that cost calls or tokens and changed nothing\n"
            "- meta_patterns: 1-5 reusable rules; scope them to a problem type only when the run "
            "shows the rule is specific to it, otherwise use 'global'\n"
            "State 'the run data does not show this' rather than inventing a cause."
        ),
    ]
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- parsing
def _strings(values: object) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


def parse_patterns(raw: object, run_id: str, provider: str, created_at: str) -> list[MetaPattern]:
    """Build the meta-patterns from the schema rows, dropping rows with no kind or no text."""
    patterns: list[MetaPattern] = []
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind", ""))
        text = str(row.get("text", "")).strip()
        scope = str(row.get("scope", GLOBAL_SCOPE))
        if kind not in META_PATTERN_KINDS or not text:
            continue
        patterns.append(
            MetaPattern(
                kind=kind,
                text=text,
                tags=_strings(row.get("tags")),
                scope=scope if scope in PATTERN_SCOPES else GLOBAL_SCOPE,
                source_run_id=run_id,
                provider=provider,
                created_at=created_at,
            )
        )
    return patterns


# --------------------------------------------------------------------------- agent
class ReflectorAgent(Agent):
    """One ``reflector`` call, effort light; writes the reflection and its meta-patterns to meta memory."""

    name = "reflector"

    def __init__(self, run_id: str = "", now: Callable[[], str] | None = None) -> None:
        self.run_id = run_id
        self.now = now

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        request = ctx.request(
            REFLECTOR_TAG,
            REFLECTOR_SYSTEM,
            reflector_prompt(state, ctx),
            REFLECTOR_SCHEMA,
            effort=ctx.settings.effort_light,
        )
        response = ctx.llm.complete(request)
        raw = response.data if isinstance(response.data, dict) else {}
        run_id = self.run_id or derived_run_id(state)
        created_at = self._now(ctx)()
        reflection = RunReflection(
            run_id=run_id,
            theme=state.theme,
            created_at=created_at,
            provider=response.provider,
            what_worked=_strings(raw.get("what_worked")),
            what_failed=_strings(raw.get("what_failed")),
            process_changes=_strings(raw.get("process_changes")),
            signal_quality=str(raw.get("signal_quality", "")),
            winning_technique=str(raw.get("winning_technique", "")),
            judge_disagreement=str(raw.get("judge_disagreement", "")),
            wasted_effort=_strings(raw.get("wasted_effort")),
        )
        patterns = parse_patterns(raw.get("meta_patterns"), run_id, response.provider, created_at)
        state.reflection = reflection
        if ctx.meta is not None:
            ctx.meta.add_reflection(reflection)
            for pattern in patterns:
                ctx.meta.add_meta_pattern(pattern)
        return state

    def _now(self, ctx: RunContext) -> Callable[[], str]:
        """The injected clock, else the run's traced clock, else UTC now (wall clock stays injectable)."""
        return self.now or getattr(ctx.llm, "now", utc_now)
