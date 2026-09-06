"""StrategistAgent: how to approach THIS problem, decided before any idea exists (DESIGN-META §18.3)."""

from __future__ import annotations

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block, knowledge_block
from ideate.agents.creativity import TECHNIQUE_HINTS
from ideate.config import Settings
from ideate.evaluation.rubric import Rubric
from ideate.llm.schema import arr, enum, int_, num, obj, str_
from ideate.meta.context import meta_context_for
from ideate.meta.charter import load_charter
from ideate.meta.ingest import TRUST_NOTE
from ideate.models import PROBLEM_TYPES, TECHNIQUES, IdeationState, MetaPattern, Strategy

STRATEGIST_TAG = "strategist"
META_KIND = "meta"
RULES_KIND = "rules"
RULES_K = 8  # how many ingested `rules` chunks the plan is allowed to see
DEFAULT_PROBLEM_TYPE = "unclear"
# Mock-produced meta memory never steers a run: quarantine, exactly like mock outcome patterns.
INCLUDE_MOCK_META = False

STRATEGIST_SYSTEM = (
    "You are the strategist of a hackathon ideation system. Before a single idea exists you decide "
    "how this particular problem should be approached: how to frame it, which ideation techniques "
    "to emphasise, what extra material to retrieve, what the judges should weigh, and which failure "
    "modes to watch for. You reason about the PROCESS, never about one specific project idea. Base "
    "the plan on the theme, the constraints and the process knowledge shown; when nothing supports a "
    "choice, say so in the rationale instead of inventing evidence. " + TRUST_NOTE
)


# --------------------------------------------------------------------------- schema
def strategy_schema(rubric: Rubric, settings: Settings) -> dict:
    """The structured-output schema for one strategist call.

    ``rubric_emphasis`` is an ARRAY of ``{criterion, multiplier}`` rows because JSON Schema cannot
    express a closed object with dynamic keys; the agent converts it to the dataclass dict.
    """
    names = rubric.names()
    emphasis = (
        arr(obj({"criterion": enum(names), "multiplier": num(0.5, 2.0)}), 0, len(names))
        if names
        else arr(str_(), 0, 0)
    )
    return obj(
        {
            "framing": str_(),
            "problem_type": enum(list(PROBLEM_TYPES)),
            "emphasis_techniques": arr(enum(list(TECHNIQUES)), 2, 4),
            "retrieval_angles": arr(str_(), 0, 4),
            "rubric_emphasis": emphasis,
            "rounds": int_(1, max(1, settings.max_iterations)),
            "watch_for": arr(str_(), 0, 5),
            "rationale": str_(),
        }
    )


# --------------------------------------------------------------------------- prompt
def technique_menu() -> str:
    """One line per available ideation technique, with its one-line description."""
    return "\n".join(f"- {technique}: {TECHNIQUE_HINTS[technique]}" for technique in TECHNIQUES)


def strategist_prompt(
    state: IdeationState,
    meta_chunks: list,
    rules_chunks: list,
    meta_block: str,
    max_rounds: int,
    charter: str = "",
) -> str:
    """User prompt: charter, theme, constraints, process knowledge, rules, meta memory, the ask.

    The charter comes first and verbatim — it is standing instruction about what this system is
    for and how its owner works, not a retrieved snippet competing on relevance.
    """
    parts = []
    if charter:
        parts.append(f"Standing charter for this system (always applies):\n\n{charter}")
    parts += [
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}",
        f"Process knowledge ({len(meta_chunks)} snippets on how to generate, retrieve and judge):\n\n"
        f"{knowledge_block(meta_chunks) or '(none retrieved)'}",
        f"Ingested operating rules ({len(rules_chunks)} snippets). {TRUST_NOTE}\n\n"
        f"{knowledge_block(rules_chunks) or '(none ingested)'}",
        f"Lessons this system recorded about its own process:\n{meta_block or '- (none recorded)'}",
        f"Ideation techniques available:\n{technique_menu()}",
        (
            "Produce the plan for this run:\n"
            "- framing: one paragraph on how to see this problem, specific to the theme\n"
            "- problem_type: the label that fits the theme and constraints best\n"
            "- emphasis_techniques: 2-4 techniques, most promising first\n"
            "- retrieval_angles: 0-4 short extra search queries (2-8 words) that the theme alone "
            "would miss; never repeat the theme verbatim\n"
            "- rubric_emphasis: only criteria this event genuinely rewards more or less, multiplier "
            "0.5-2.0; leave it empty when the default balance is right\n"
            f"- rounds: how many creativity rounds this problem needs, 1-{max_rounds}\n"
            "- watch_for: 0-5 failure modes this particular run should avoid\n"
            "- rationale: why this plan, referring to the material above; say 'no evidence in "
            "knowledge base' where nothing supports a choice"
        ),
    ]
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- parsing
def emphasis_dict(rows: object) -> dict[str, float]:
    """Convert the schema's ``[{criterion, multiplier}]`` array into the dataclass dict (last wins)."""
    out: dict[str, float] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("criterion", "")).strip()
        multiplier = row.get("multiplier")
        if not name or isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
            continue
        out[name] = float(multiplier)
    return out


def parse_strategy(raw: dict, source_patterns: list[str]) -> Strategy:
    """Build the (still unclamped) ``Strategy`` from one validated schema instance."""
    return Strategy(
        framing=str(raw.get("framing", "")),
        problem_type=str(raw.get("problem_type", DEFAULT_PROBLEM_TYPE)),
        emphasis_techniques=[str(t) for t in raw.get("emphasis_techniques", []) or []],
        retrieval_angles=[str(q).strip() for q in raw.get("retrieval_angles", []) or [] if str(q).strip()],
        rubric_emphasis=emphasis_dict(raw.get("rubric_emphasis")),
        rounds=int(raw.get("rounds", 0) or 0),
        watch_for=[str(w) for w in raw.get("watch_for", []) or []],
        rationale=str(raw.get("rationale", "")),
        source_patterns=list(source_patterns),
    )


def meta_material(theme: str, ctx: RunContext) -> tuple[str, list[MetaPattern]]:
    """The meta-memory block and the patterns it actually shows (empty when there is no store)."""
    if ctx.meta is None:
        return "", []
    block = meta_context_for(
        theme, DEFAULT_PROBLEM_TYPE, ctx.kb, ctx.meta, k=ctx.settings.meta_k, include_mock=INCLUDE_MOCK_META
    )
    if not block:
        return "", []
    shown = [p for p in ctx.meta.meta_patterns(include_mock=INCLUDE_MOCK_META) if p.text and p.text in block]
    return block, shown


# --------------------------------------------------------------------------- agent
class StrategistAgent(Agent):
    """One ``strategist`` call, effort light; fills ``state.strategy`` with a sanitized plan."""

    name = "strategist"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        settings = ctx.settings
        meta_chunks = ctx.retrieve(state.theme, k=settings.meta_k, kind=META_KIND)
        rules_chunks = ctx.retrieve(state.theme, k=RULES_K, kind=RULES_KIND)
        meta_block, shown = meta_material(state.theme, ctx)
        charter, _ = load_charter(settings.charter_path)
        prompt = strategist_prompt(
            state, meta_chunks, rules_chunks, meta_block, settings.max_iterations, charter
        )
        request = ctx.request(
            STRATEGIST_TAG,
            STRATEGIST_SYSTEM,
            prompt,
            strategy_schema(ctx.rubric, settings),
            effort=settings.effort_light,
        )
        data = ctx.llm.complete(request).data
        raw = data if isinstance(data, dict) else {}
        strategy = parse_strategy(raw, [p.id for p in shown])
        state.strategy = strategy.sanitized(settings, ctx.rubric)
        return state
