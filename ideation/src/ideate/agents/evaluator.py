"""EvaluatorAgent: persona panel over the unjudged ideas, ranking and critiques (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block
from ideate.evaluation.judge import PanelJudge, rank_ideas
from ideate.models import IdeationState

TOP_N = 3
MAX_CRITIQUES = 9
TOP_RESEARCH_BULLETS = 3
LOWEST_CRITERION_PREFIX = "lowest criterion: "


class Defaulting(dict):
    """``format_map`` mapping that leaves unknown ``{placeholders}`` untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def persona_text(persona: str, state: IdeationState) -> str:
    """Substitute ``{hours}``, ``{team_size}`` and ``{theme}`` into a persona template."""
    return persona.format_map(
        Defaulting(hours=state.constraints.hours, team_size=state.constraints.team_size, theme=state.theme)
    )


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def judge_context(state: IdeationState) -> str:
    """Judge context: constraints block, assessment highlights and the top research bullets."""
    a = state.assessment
    r = state.research
    parts = [
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}",
        "Technical assessment:\n"
        f"Challenges:\n{_bullets(a.challenges if a else [])}\n"
        f"Building blocks:\n{_bullets(a.building_blocks if a else [])}\n"
        f"Hour budget:\n{_bullets(a.hour_budget if a else [])}",
        "Research highlights:\n"
        f"Trends:\n{_bullets(r.trends[:TOP_RESEARCH_BULLETS] if r else [])}\n"
        f"Pitfalls:\n{_bullets(r.pitfalls[:TOP_RESEARCH_BULLETS] if r else [])}\n"
        f"Opportunities:\n{_bullets(r.opportunities[:TOP_RESEARCH_BULLETS] if r else [])}",
    ]
    return "\n\n".join(parts)


def critiques_for(state: IdeationState) -> list[str]:
    """Consensus weaknesses of the top-3 ideas plus their lowest criterion, deduped, at most 9."""
    out: list[str] = []
    for idea_id in state.ranking[:TOP_N]:
        verdict = state.verdict_for(idea_id)
        if verdict is None:
            continue
        consensus = verdict.consensus
        out.extend(consensus.weaknesses)
        if consensus.scores:
            lowest = min(consensus.scores, key=lambda s: s.score)
            out.append(f"{LOWEST_CRITERION_PREFIX}{lowest.name}")
    return list(dict.fromkeys(out))[:MAX_CRITIQUES]


class EvaluatorAgent(Agent):
    """Judges ideas without a verdict, then re-ranks every idea and refreshes the critiques."""

    name = "evaluator"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        personas = [persona_text(p, state) for p in ctx.settings.judge_personas]
        panel = PanelJudge(ctx.llm, ctx.rubric, personas, constraints=state.constraints, effort=ctx.settings.effort_light)
        judged = {v.idea_id for v in state.verdicts}
        pending = [idea for idea in state.ideas if idea.id not in judged]
        if pending:
            state.verdicts.extend(panel.evaluate_many(pending, judge_context(state)))
        state.ranking = rank_ideas(state.ideas, state.verdicts)
        state.critiques = critiques_for(state)
        return state
