"""SynthesizerAgent: the build proposal for the top-ranked idea (docs/DESIGN.md §9.4)."""

from __future__ import annotations

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block
from ideate.llm.schema import arr, enum, obj, str_
from ideate.models import BLOCKER_KINDS, Alternative, Idea, IdeaEvaluation, IdeationState, Proposal

SYNTHESIZER_TAG = "synthesizer"
TOP_N = 3
SYNTHESIZER_SYSTEM = (
    "You are the delivery lead of a hackathon team. Turn the top-ranked idea into a concrete "
    "build proposal the team can start executing this minute. Be specific: named tasks, named "
    "owners by role, named resources. Every human dependency (accounts, keys, sign-ups, hardware, "
    "approvals) is handed to a human now, prefixed with its blocker kind: "
    + " / ".join(f"'{kind}: '" for kind in BLOCKER_KINDS)
    + ". Never invent statistics."
)


def milestone_template(hours: int) -> str:
    """The milestone skeleton the proposal must follow, computed from the event hours."""
    return (
        f"- h0-1: first hour (repo created, pushed, git-triggered deploy confirmed to give a public URL)\n"
        f"- by h{round(hours * 0.25)} (25%): walking skeleton reachable at the public URL\n"
        f"- by h{round(hours * 0.60)} (60%): demo path works end to end (fake data allowed)\n"
        f"- at h{round(hours * 0.80)} (80%): feature freeze\n"
        f"- last {max(1, round(hours * 0.10))}h (10%): rehearse the demo and record the fallback video"
    )


PROPOSAL_REQUIREMENTS = (
    "Requirements:\n"
    "- first_hour_plan begins with: create the repo, push, and confirm the git-triggered deploy "
    "gives a public URL; then stub the demo path end to end with fake data; then hand every human "
    "dependency to a human now\n"
    "- milestones follow the template below, filled in for this idea\n"
    "- team_split always names an integration owner and a demo owner\n"
    "- human_dependencies are each prefixed with their blocker kind\n"
    "- cut_list is ordered: first item is cut first\n"
    "- pivot_trigger names the observable condition (and the hour) at which the team switches to an alternative\n"
    "- demo_script is what is said and shown, step by step, within 90 seconds"
)


def proposal_schema(runner_ups: list[str]) -> dict:
    """Proposal minus the code-filled ``idea_id``; alternatives are enum-bound to the runner-ups."""
    if runner_ups:
        alternatives = arr(obj({"idea_id": enum(runner_ups), "choose_if": str_()}), 0, len(runner_ups))
    else:
        alternatives = arr(str_(), 0, 0)
    return obj(
        {
            "executive_summary": str_(),
            "value_proposition": str_(),
            "why_this": str_(),
            "implementation_plan": arr(str_(), 3, 10),
            "demo_plan": arr(str_(), 1, 6),
            "demo_script": arr(str_(), 3, 10),
            "impact": str_(),
            "first_hour_plan": arr(str_(), 3, 8),
            "milestones": arr(str_(), 3, 6),
            "team_split": arr(str_(), 1, 6),
            "cut_list": arr(str_(), 1, 6),
            "pivot_trigger": str_(),
            "human_dependencies": arr(str_(), 0, 6),
            "alternatives": alternatives,
        }
    )


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def idea_block(idea: Idea) -> str:
    """The fields of an idea the synthesizer needs, as labelled lines."""
    rows = [
        ("One-liner", idea.one_liner),
        ("Target user", idea.target_user),
        ("Description", idea.description),
        ("Key innovation", idea.key_innovation),
        ("Technical approach", idea.technical_approach),
        ("Demo strategy", idea.demo_strategy),
        ("Demo moment", idea.demo_moment),
        ("Data sources", "; ".join(idea.data_sources)),
        ("MVP scope", "; ".join(idea.mvp_scope)),
        ("Cut first", "; ".join(idea.cut_first)),
        ("Closest existing", idea.closest_existing),
        ("Build hours estimate", str(idea.build_hours_estimate)),
        ("Risks", "; ".join(idea.risks)),
    ]
    return "\n".join(f"{label}: {value}" for label, value in rows if value)


def verdict_block(consensus: IdeaEvaluation) -> str:
    """Consensus scores and critique of one idea."""
    scores = ", ".join(f"{s.name}={s.score:g}" for s in consensus.scores)
    lines = [
        f"Consensus weighted score: {consensus.weighted_score:.2f} ({scores})",
        f"Strengths:\n{_bullets(consensus.strengths)}",
        f"Weaknesses:\n{_bullets(consensus.weaknesses)}",
        f"Suggestions:\n{_bullets(consensus.suggestions)}",
        f"Demo break risk: {consensus.demo_break_risk or '-'}",
    ]
    if consensus.disqualified:
        lines.append(f"Disqualified: {consensus.disqualify_reason or 'yes'}")
    return "\n".join(lines)


def synthesizer_prompt(state: IdeationState) -> str:
    """User prompt: constraints, the top-3 ideas with their verdicts, the assessment and the requirements."""
    a = state.assessment
    parts = [f"Theme: {state.theme}\n{constraints_block(state.constraints)}"]
    for position, idea_id in enumerate(state.ranking[:TOP_N], 1):
        idea = state.idea_for(idea_id)
        if idea is None:
            continue
        verdict = state.verdict_for(idea_id)
        label = "BUILD THIS" if position == 1 else f"runner-up {position - 1}"
        block = f"### {label}: {idea.id}: {idea.title}\n{idea_block(idea)}"
        if verdict is not None:
            block += f"\n{verdict_block(verdict.consensus)}"
        parts.append(block)
    parts.append(
        "Technical assessment:\n"
        f"Challenges:\n{_bullets(a.challenges if a else [])}\n"
        f"Suggested stack:\n{_bullets(a.suggested_stack if a else [])}\n"
        f"Building blocks:\n{_bullets(a.building_blocks if a else [])}\n"
        f"Hour budget:\n{_bullets(a.hour_budget if a else [])}"
    )
    parts.append(f"{PROPOSAL_REQUIREMENTS}\n\nMilestone template ({state.constraints.hours} hours):\n{milestone_template(state.constraints.hours)}")
    parts.append("Write the proposal for the BUILD THIS idea. For each runner-up give the condition under which the team should choose it instead.")
    return "\n\n".join(parts)


def _strings(values: object) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


def parse_proposal(raw: dict, top_id: str, runner_ups: list[str]) -> Proposal:
    """Build the ``Proposal`` from a validated instance; ``idea_id`` is code-set to the top idea."""
    alternatives = [
        Alternative(idea_id=str(alt["idea_id"]), choose_if=str(alt.get("choose_if", "")))
        for alt in raw.get("alternatives", []) or []
        if isinstance(alt, dict) and alt.get("idea_id") in runner_ups
    ]
    return Proposal(
        idea_id=top_id,
        executive_summary=str(raw.get("executive_summary", "")),
        value_proposition=str(raw.get("value_proposition", "")),
        why_this=str(raw.get("why_this", "")),
        implementation_plan=_strings(raw.get("implementation_plan")),
        demo_plan=_strings(raw.get("demo_plan")),
        demo_script=_strings(raw.get("demo_script")),
        impact=str(raw.get("impact", "")),
        first_hour_plan=_strings(raw.get("first_hour_plan")),
        milestones=_strings(raw.get("milestones")),
        team_split=_strings(raw.get("team_split")),
        cut_list=_strings(raw.get("cut_list")),
        pivot_trigger=str(raw.get("pivot_trigger", "")),
        human_dependencies=_strings(raw.get("human_dependencies")),
        alternatives=alternatives,
    )


class SynthesizerAgent(Agent):
    """One ``synthesizer`` call producing ``state.proposal`` for ``state.ranking[0]``."""

    name = "synthesizer"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        if not state.ranking:
            raise ValueError("synthesizer needs a non-empty ranking")
        runner_ups = state.ranking[1:TOP_N]
        request = ctx.request(SYNTHESIZER_TAG, SYNTHESIZER_SYSTEM, synthesizer_prompt(state), proposal_schema(runner_ups))
        data = ctx.llm.complete(request).data
        raw = data if isinstance(data, dict) else {}
        state.proposal = parse_proposal(raw, state.ranking[0], runner_ups)
        return state
