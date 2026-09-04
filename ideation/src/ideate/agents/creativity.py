"""CreativityAgent: technique-cycled idea generation with validation and diversity (docs/DESIGN.md §9.4)."""

from __future__ import annotations

import re

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block, knowledge_block
from ideate.agents.research import citations_schema, known_ids
from ideate.knowledge.tokenize import tokenize
from ideate.llm.base import LLMBadOutput
from ideate.llm.schema import arr, enum, int_, obj, str_
from ideate.models import TECHNIQUES, HackathonConstraints, Idea, IdeationState, RetrievedChunk

CREATIVITY_TAG = "creativity"
ANTIPATTERN_KIND = "antipattern"
ANTIPATTERN_K = 4
NEW_PARENT = "new"
MIN_DEMO_MOMENT_WORDS = 4
DIVERSITY_THRESHOLD = 0.6
MIN_DISTINCT_USERS = 4
MIN_DISTINCT_SOURCES = 3

GENERIC_USERS: frozenset[str] = frozenset(
    {"users", "people", "businesses", "everyone", "companies", "students", "developers", "consumers"}
)

TECHNIQUE_HINTS: dict[str, str] = {
    "analogical": "transplant a mechanism that works in a different domain into this theme",
    "assumption_breaking": "name a default assumption of the theme and build on its negation",
    "reverse": "invert the usual workflow: who acts, when it happens, or what flows to whom",
    "scale": "take a manual, occasional practice and make it far cheaper, faster or more frequent",
    "combination": "join two building blocks from the resource menu that are rarely combined",
    "direct": "solve the most painful named problem in the theme head-on, no twist required",
}

CREATIVITY_SYSTEM = (
    "You are the ideation lead of a hackathon team. You generate a batch of distinct, buildable "
    "project ideas, each produced with the ideation technique assigned to its slot. Every idea "
    "names a specific target user (a role in a situation, never a generic group), data sources "
    "with their access level, a demo moment that lands on screen in about 90 seconds, an honest "
    "build-hour estimate within the event's hours, and cites at least one of the shown snippets "
    "by chunk id. Ideas that use anything in the must-avoid list are invalid. Never invent "
    "statistics, prior winners or case studies."
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- schema
def idea_schema(shown_ids: list[str], hours: int, parent_ids: list[str] | None = None) -> dict:
    """Schema of one idea; ``parent_ids`` (round >= 2) adds ``parent_id: enum(top3 + ["new"])``."""
    props = {
        "title": str_(),
        "one_liner": str_(),
        "description": str_(),
        "target_user": str_(),
        "key_innovation": str_(),
        "technique": enum(list(TECHNIQUES)),
        "technical_approach": str_(),
        "demo_strategy": str_(),
        "demo_moment": str_(),
        "data_sources": arr(str_(), 1, 4),
        "mvp_scope": arr(str_(), 1, 5),
        "cut_first": arr(str_(), 1, 4),
        "closest_existing": str_(),
        "build_hours_estimate": int_(1, max(1, hours)),
        "risks": arr(str_(), 1, 4),
        "citations": citations_schema(shown_ids),
    }
    if parent_ids is not None:
        props["parent_id"] = enum(list(parent_ids) + [NEW_PARENT])
    return obj(props)


def batch_schema(n: int, shown_ids: list[str], hours: int, parent_ids: list[str] | None = None) -> dict:
    """``obj({"ideas": arr(IDEA_SCHEMA, n, n)})``."""
    return obj({"ideas": arr(idea_schema(shown_ids, hours, parent_ids), n, n)})


# --------------------------------------------------------------------------- validation
def simple_tokens(text: str) -> set[str]:
    """Mock-style ``[a-z0-9]+`` token set (used for the diversity filter)."""
    return set(_TOKEN_RE.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    """Token-set Jaccard similarity (0.0 when both sets are empty)."""
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def idea_signature(idea: Idea) -> set[str]:
    """The token set the diversity filter compares: ``title + " " + one_liner``."""
    return simple_tokens(idea.title + " " + idea.one_liner)


def validate_idea(idea: Idea, constraints: HackathonConstraints) -> list[str]:
    """Violations of the hard idea rules (empty list when the idea is acceptable)."""
    flags: list[str] = []
    user = idea.target_user.strip().lower()
    if not user or user in GENERIC_USERS:
        flags.append(f"target_user {idea.target_user!r} is empty or generic; name a role in a situation")
    if not idea.data_sources:
        flags.append("data_sources is empty")
    if len(idea.demo_moment.split()) < MIN_DEMO_MOMENT_WORDS:
        flags.append(f"demo_moment has fewer than {MIN_DEMO_MOMENT_WORDS} words")
    if idea.build_hours_estimate > constraints.hours:
        flags.append(f"build_hours_estimate {idea.build_hours_estimate} exceeds the {constraints.hours} hours available")
    text_tokens = set(tokenize(" ".join((idea.title, idea.description, idea.technical_approach))))
    for term in constraints.must_avoid:
        term_tokens = tokenize(term)
        if term_tokens and all(t in text_tokens for t in term_tokens):
            flags.append(f"uses must-avoid term {term!r}")
    return flags


def diverse(candidates: list[Idea], earlier: list[Idea], threshold: float = DIVERSITY_THRESHOLD) -> list[Idea]:
    """Drop each candidate whose signature Jaccard with ANY earlier or previously kept idea exceeds ``threshold``."""
    seen = [idea_signature(i) for i in earlier]
    kept: list[Idea] = []
    for idea in candidates:
        sig = idea_signature(idea)
        if any(jaccard(sig, s) > threshold for s in seen):
            continue
        seen.append(sig)
        kept.append(idea)
    return kept


# --------------------------------------------------------------------------- prompt
def technique_lines(n: int) -> str:
    """One line per idea slot: slot k uses ``TECHNIQUES[k % 6]``."""
    lines = []
    for k in range(n):
        technique = TECHNIQUES[k % len(TECHNIQUES)]
        lines.append(f"- idea {k + 1}: technique={technique} ({TECHNIQUE_HINTS[technique]})")
    return "\n".join(lines)


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def refinement_block(state: IdeationState, top3: list[Idea]) -> str:
    """Round >= 2 material: the top-3 ideas with their consensus critique, plus the run critiques."""
    parts = ["Top-3 ideas from the previous round (refine roughly half of this batch from these):"]
    for idea in top3:
        verdict = state.verdict_for(idea.id)
        weaknesses = verdict.consensus.weaknesses if verdict else []
        suggestions = verdict.consensus.suggestions if verdict else []
        parts.append(
            f"### {idea.id}: {idea.title}\nOne-liner: {idea.one_liner}\n"
            f"Weaknesses:\n{_bullets(weaknesses, 'none recorded')}\nSuggestions:\n{_bullets(suggestions, 'none recorded')}"
        )
    parts.append(f"Critiques to address:\n{_bullets(state.critiques, 'none recorded')}")
    parts.append(
        "Roughly half of the ideas must refine a top-3 idea: set parent_id to its id and state in "
        "the description what changed and why. The other half are new ideas with parent_id = \"new\"."
    )
    return "\n\n".join(parts)


def creativity_prompt(state: IdeationState, n: int, shown: list[RetrievedChunk], antipatterns: list[RetrievedChunk], top3: list[Idea]) -> str:
    """User prompt for one creativity call (a pure function of the state and the shown chunks)."""
    building_blocks = state.assessment.building_blocks if state.assessment else []
    hours = state.constraints.hours
    parts = [
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}",
        f"Round {state.iteration}: generate exactly {n} ideas. Technique per slot:\n{technique_lines(n)}",
        f"Lessons from past outcomes (leverage the successes, avoid the failures):\n{state.memory_context or '- (no past outcomes recorded)'}",
        f"Resource menu (building blocks with access level):\n{_bullets(building_blocks, '(no assessment yet)')}",
        (
            "Antipatterns — do not produce one of these unless you state the twist that makes it different:\n\n"
            f"{knowledge_block(antipatterns) or '(none retrieved)'}"
        ),
        f"Knowledge snippets ({len(shown)}):\n\n{knowledge_block(shown)}",
        (
            "Rules for the batch:\n"
            f"- at least {MIN_DISTINCT_USERS} distinct target_users across the batch, each a named role in a named situation\n"
            f"- at least {MIN_DISTINCT_SOURCES} distinct primary data_sources across the batch, each written as "
            "'name — access: none|free key|account — what it provides'\n"
            "- every idea cites at least one shown snippet by chunk id in citations\n"
            f"- demo_moment describes what is on screen at ~90 seconds; build_hours_estimate is between 1 and {hours}\n"
            "- ideas that use anything in Must avoid are invalid"
        ),
    ]
    if top3:
        parts.append(refinement_block(state, top3))
    return "\n\n".join(parts)


def retry_prompt(prompt: str, violations: list[str]) -> str:
    """The first prompt plus the violations of the previous batch."""
    return prompt + "\n\nYour previous batch had invalid ideas; regenerate the whole batch fixing these:\n" + _bullets(violations, "")


# --------------------------------------------------------------------------- agent
def parse_idea(raw: dict, shown_ids: list[str], parent_ids: list[str] | None) -> Idea:
    """Build an ``Idea`` (no id yet) from one validated schema instance."""
    parent = raw.get("parent_id")
    parent_id = str(parent) if parent_ids is not None and parent in parent_ids else None
    return Idea(
        title=str(raw.get("title", "")),
        description=str(raw.get("description", "")),
        one_liner=str(raw.get("one_liner", "")),
        target_user=str(raw.get("target_user", "")),
        key_innovation=str(raw.get("key_innovation", "")),
        technique=str(raw.get("technique", "direct")) if raw.get("technique") in TECHNIQUES else "direct",
        technical_approach=str(raw.get("technical_approach", "")),
        demo_strategy=str(raw.get("demo_strategy", "")),
        demo_moment=str(raw.get("demo_moment", "")),
        data_sources=[str(s) for s in raw.get("data_sources", []) or []],
        mvp_scope=[str(s) for s in raw.get("mvp_scope", []) or []],
        cut_first=[str(s) for s in raw.get("cut_first", []) or []],
        closest_existing=str(raw.get("closest_existing", "")),
        build_hours_estimate=int(raw.get("build_hours_estimate", 0) or 0),
        risks=[str(s) for s in raw.get("risks", []) or []],
        citations=known_ids(raw.get("citations"), shown_ids),
        parent_id=parent_id,
    )


def merge_shown(knowledge: list[RetrievedChunk], extra: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """``knowledge`` followed by the ``extra`` chunks whose ids are not already present."""
    by_id = {rc.chunk.id: rc for rc in knowledge}
    for rc in extra:
        by_id.setdefault(rc.chunk.id, rc)
    return list(by_id.values())


class CreativityAgent(Agent):
    """One ``creativity`` call (plus at most one whole-batch retry) appending ideas to the state."""

    name = "creativity"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        state.iteration += 1
        n = ctx.settings.ideas_per_round
        antipatterns = ctx.retrieve(state.theme, k=ANTIPATTERN_K, kind=ANTIPATTERN_KIND)
        shown = merge_shown(state.knowledge, antipatterns)
        shown_ids = [rc.chunk.id for rc in shown]
        top3 = [i for i in (state.idea_for(i) for i in state.ranking[:3]) if i is not None] if state.iteration >= 2 else []
        parent_ids = [i.id for i in top3] if state.iteration >= 2 else None
        schema = batch_schema(n, shown_ids, state.constraints.hours, parent_ids)
        prompt = creativity_prompt(state, n, shown, antipatterns, top3)

        survivors, violations = self._generate(ctx, prompt, schema, state, shown_ids, parent_ids)
        if violations:
            more, _ = self._generate(ctx, retry_prompt(prompt, violations), schema, state, shown_ids, parent_ids)
            survivors.extend(more)
        if not survivors:
            raise LLMBadOutput(f"creativity round {state.iteration}: no idea passed validation after one retry")
        kept = diverse(survivors, state.ideas)[:n]
        for k, idea in enumerate(kept, 1):
            idea.id = f"idea-{state.iteration}-{k}"
        state.ideas.extend(kept)
        return state

    def _generate(
        self,
        ctx: RunContext,
        prompt: str,
        schema: dict,
        state: IdeationState,
        shown_ids: list[str],
        parent_ids: list[str] | None,
    ) -> tuple[list[Idea], list[str]]:
        """One call; returns the ideas that pass ``validate_idea`` and the violations of the rest."""
        data = ctx.llm.complete(ctx.request(CREATIVITY_TAG, CREATIVITY_SYSTEM, prompt, schema)).data
        raw_ideas = data.get("ideas", []) if isinstance(data, dict) else []
        survivors: list[Idea] = []
        violations: list[str] = []
        for position, raw in enumerate(raw_ideas, 1):
            if not isinstance(raw, dict):
                continue
            idea = parse_idea(raw, shown_ids, parent_ids)
            flags = validate_idea(idea, state.constraints)
            if flags:
                violations.append(f"idea {position} ({idea.title}): " + "; ".join(flags))
            else:
                survivors.append(idea)
        return survivors, violations
