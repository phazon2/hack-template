"""DomainExpertAgent: technical assessment and the resource menu (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block, knowledge_block
from ideate.llm.schema import arr, obj, str_
from ideate.models import IdeationState, ResearchFindings, TechnicalAssessment

DOMAIN_EXPERT_TAG = "domain_expert"
DATA_SOURCE_KIND = "data-source"
DOMAIN_EXPERT_SYSTEM = (
    "You are a senior engineer who has shipped many hackathon projects and knows which public "
    "APIs, datasets and libraries a small team can wire up in hours. Assess what is technically "
    "possible for this theme under the constraints. Name concrete building blocks with their "
    "access level (none | free key | account) taken from the data-source snippets or well-known "
    "public resources; prefer resources that need no account. Split the hours into a budget: "
    "setup, walking skeleton with a public URL, build, integrate, rehearse. Never invent "
    "statistics or benchmarks."
)
DOMAIN_EXPERT_SCHEMA = obj(
    {
        "constraints": arr(str_(), 1, 6),
        "required_skills": arr(str_(), 1, 6),
        "challenges": arr(str_(), 1, 6),
        "breakthroughs": arr(str_(), 1, 6),
        "suggested_stack": arr(str_(), 1, 6),
        "building_blocks": arr(str_(), 1, 8),
        "hour_budget": arr(str_(), 3, 6),
    }
)


def research_block(research: ResearchFindings | None) -> str:
    """Research findings as labelled bullet lists (``(none)`` when research has not run)."""
    if research is None:
        return "(no research findings)"
    sections = [
        ("Trends", research.trends),
        ("Case studies", research.case_studies),
        ("Pitfalls", research.pitfalls),
        ("Opportunities", research.opportunities),
        ("Coverage gaps", research.coverage_gaps),
    ]
    lines = []
    for label, items in sections:
        lines.append(f"{label}:")
        lines.extend(f"- {item}" for item in items)
        if not items:
            lines.append("- (none)")
    return "\n".join(lines)


def domain_expert_prompt(state: IdeationState) -> str:
    """User prompt: constraints block, research findings and the data-source snippets."""
    data_chunks = [rc for rc in state.knowledge if rc.chunk.metadata.get("kind") == DATA_SOURCE_KIND]
    return (
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}\n\n"
        f"Research findings:\n{research_block(state.research)}\n\n"
        f"Data-source snippets ({len(data_chunks)}):\n\n{knowledge_block(data_chunks) or '(none retrieved)'}\n\n"
        "Produce the technical assessment. building_blocks are the resource menu the ideation "
        "step will draw from: each entry names one API/dataset/library, its access level and what "
        f"it provides. hour_budget must add up to {state.constraints.hours} hours."
    )


def _strings(values: object) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


class DomainExpertAgent(Agent):
    """One ``domain_expert`` call producing ``state.assessment``."""

    name = "domain_expert"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        request = ctx.request(DOMAIN_EXPERT_TAG, DOMAIN_EXPERT_SYSTEM, domain_expert_prompt(state), DOMAIN_EXPERT_SCHEMA)
        data = ctx.llm.complete(request).data
        raw = data if isinstance(data, dict) else {}
        state.assessment = TechnicalAssessment(
            constraints=_strings(raw.get("constraints")),
            required_skills=_strings(raw.get("required_skills")),
            challenges=_strings(raw.get("challenges")),
            breakthroughs=_strings(raw.get("breakthroughs")),
            suggested_stack=_strings(raw.get("suggested_stack")),
            building_blocks=_strings(raw.get("building_blocks")),
            hour_budget=_strings(raw.get("hour_budget")),
        )
        return state
