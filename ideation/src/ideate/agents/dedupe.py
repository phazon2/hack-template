"""Two-stage duplicate removal for generated ideas.

Duplication, not novelty, is the measured bottleneck in LLM ideation: after deduplicating at 0.8
cosine on sentence embeddings, Si et al. (arXiv 2409.04109) found roughly 5% of seed ideas
survived, and generating more simply produced more repeats. So this is the highest-value control
in the pipeline, and it is worth two passes.

**Stage one is lexical and free.** Cosine over the hashed n-gram embedder already in the repo,
measured on real idea pairs: a near-copy scores about 0.80, a reworded duplicate about 0.20, and
two genuinely different ideas about 0.00. That separates near-copies cleanly and says nothing
useful about the rest — a hashed lexical embedder has no way to know that "surplus food" and
"leftover groceries" are the same thing.

**Stage two asks the model**, because the duplicates that matter survive rewording and nothing
lexical can see them. This is not the published method: reproducing that needs real sentence
embeddings, which need torch, which the core does not carry. It is the closest available
substitute, and unlike idea *ranking* — where LLM judges score near chance — deciding whether two
descriptions denote the same idea is a comparison task with a checkable answer.
"""

from __future__ import annotations

from ideate.agents.context import RunContext
from ideate.llm.base import LLMError
from ideate.llm.schema import arr, enum, obj, str_
from ideate.models import Idea

DEDUPE_TAG = "dedupe"
# Calibrated on the hashed embedder, not carried over from the sentence-embedding literature:
# near-copies land near 0.80 and everything else well below, so this catches them and no more.
LEXICAL_THRESHOLD = 0.65
MIN_IDEAS_TO_ASK = 3

DEDUPE_SYSTEM = (
    "You decide whether hackathon ideas are the same idea described differently. Two ideas are the "
    "same when they serve the same user with the same mechanism, however different the wording, the "
    "product name or the framing. They are different when either the user or the mechanism differs, "
    "even if the domain is shared. Group only what you would be comfortable calling a repeat to the "
    "team that wrote them; when unsure, leave them separate."
)


def dedupe_prompt(ideas: list[Idea]) -> str:
    """One block per idea, with the fields that carry its identity."""
    blocks = [
        f"[{idea.id}] {idea.title} — {idea.one_liner}\n"
        f"    user: {idea.target_user}\n"
        f"    does: {idea.description}\n"
        f"    innovation: {idea.key_innovation}"
        for idea in ideas
    ]
    return (
        "Ideas:\n\n"
        + "\n\n".join(blocks)
        + "\n\nReturn each group of ids that are the same idea in different words. Most batches "
        "contain some repeats; a batch with none is normal too. Never put an id in more than one "
        "group, and never group ideas that merely share a domain."
    )


def duplicate_groups(ideas: list[Idea], ctx: RunContext) -> list[list[str]]:
    """Groups of ids the model considers the same idea; empty when it finds none or the call fails.

    A failure here must not lose ideas, so an error yields no groups and the batch passes through.
    """
    if len(ideas) < MIN_IDEAS_TO_ASK:
        return []
    ids = [idea.id for idea in ideas]
    schema = obj(
        {
            "groups": arr(
                obj({"idea_ids": arr(enum(ids), 2, len(ids)), "why": str_()}),
                0,
                max(1, len(ids) // 2),
            )
        }
    )
    request = ctx.request(
        DEDUPE_TAG,
        DEDUPE_SYSTEM,
        dedupe_prompt(ideas),
        schema,
        effort=ctx.settings.effort_light,
    )
    try:
        data = ctx.llm.complete(request).data
    except LLMError:
        return []
    raw = data if isinstance(data, dict) else {}

    known = set(ids)
    claimed: set[str] = set()
    groups: list[list[str]] = []
    for group in raw.get("groups") or []:
        members = [i for i in dict.fromkeys(group.get("idea_ids") or []) if i in known and i not in claimed]
        if len(members) < 2:
            continue
        claimed.update(members)
        groups.append(members)
    return groups


def drop_semantic_duplicates(ideas: list[Idea], ctx: RunContext) -> tuple[list[Idea], int]:
    """Keep the first idea of each duplicate group; return the survivors and how many were dropped.

    The first is kept because the batch is generated in the prompt's own order, so the earlier
    idea is the one the later one is a variation of.
    """
    groups = duplicate_groups(ideas, ctx)
    if not groups:
        return list(ideas), 0
    drop = {member for group in groups for member in group[1:]}
    survivors = [idea for idea in ideas if idea.id not in drop]
    return survivors, len(ideas) - len(survivors)
