"""ResearchAgent: evidence-bound findings from the retrieved snippets (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block, knowledge_block
from ideate.llm.schema import arr, enum, obj, str_
from ideate.models import IdeationState, ResearchFindings

RESEARCH_TAG = "research"
RESEARCH_RULE = (
    "If the snippets do not cover something you need, list it in coverage_gaps and write "
    "'no evidence in knowledge base' in the relevant bullet — never invent case studies or statistics."
)
RESEARCH_SYSTEM = (
    "You are the research analyst of a hackathon ideation team. You summarise ONLY what the "
    "numbered knowledge snippets support: trends, documented case studies, pitfalls and "
    "opportunities relevant to the theme and constraints. Every bullet should be traceable to a "
    "snippet you cite by chunk id. " + RESEARCH_RULE
)


def citations_schema(shown_ids: list[str]) -> dict:
    """``arr(enum(ids), 0, len(ids))`` when ids are shown, else the empty-list schema."""
    if shown_ids:
        return arr(enum(shown_ids), 0, len(shown_ids))
    return arr(str_(), 0, 0)


def research_schema(shown_ids: list[str]) -> dict:
    """The structured-output schema for one research call."""
    return obj(
        {
            "trends": arr(str_(), 1, 5),
            "case_studies": arr(str_(), 0, 5),
            "pitfalls": arr(str_(), 1, 5),
            "opportunities": arr(str_(), 1, 5),
            "citations": citations_schema(shown_ids),
            "coverage_gaps": arr(str_(), 0, 4),
        }
    )


def research_prompt(state: IdeationState) -> str:
    """User prompt: theme, constraints block, the numbered snippets and the evidence rule."""
    return (
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}\n\n"
        f"Knowledge snippets ({len(state.knowledge)}):\n\n{knowledge_block(state.knowledge)}\n\n"
        f"{RESEARCH_RULE}\n"
        "Cite the snippets you relied on by their chunk id in citations."
    )


def known_ids(values: object, shown_ids: list[str]) -> list[str]:
    """Keep only ids that were shown, dropping duplicates and keeping order."""
    if not isinstance(values, list):
        return []
    shown = set(shown_ids)
    return list(dict.fromkeys(str(v) for v in values if str(v) in shown))


def _strings(values: object) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


class ResearchAgent(Agent):
    """One ``research`` call per retrieval round; unknown citation ids are dropped."""

    name = "research"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        state.retrieval_rounds += 1
        shown_ids = [rc.chunk.id for rc in state.knowledge]
        request = ctx.request(RESEARCH_TAG, RESEARCH_SYSTEM, research_prompt(state), research_schema(shown_ids))
        data = ctx.llm.complete(request).data
        raw = data if isinstance(data, dict) else {}
        state.research = ResearchFindings(
            trends=_strings(raw.get("trends")),
            case_studies=_strings(raw.get("case_studies")),
            pitfalls=_strings(raw.get("pitfalls")),
            opportunities=_strings(raw.get("opportunities")),
            citations=known_ids(raw.get("citations"), shown_ids),
            coverage_gaps=_strings(raw.get("coverage_gaps")),
        )
        return state
