"""OrchestratorAgent, RetrieveMoreAgent and the default graph (docs/DESIGN.md §9.3, §9.4)."""

from __future__ import annotations

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, constraints_block
from ideate.agents.creativity import CreativityAgent
from ideate.agents.domain_expert import DomainExpertAgent
from ideate.agents.evaluator import EvaluatorAgent
from ideate.agents.graph import END, Condition, Graph
from ideate.agents.reflector import ReflectorAgent
from ideate.agents.research import ResearchAgent
from ideate.agents.strategist import StrategistAgent
from ideate.agents.synthesizer import SynthesizerAgent
from ideate.config import Settings
from ideate.improvement.feedback import memory_context_for
from ideate.llm.schema import arr, obj, str_
from ideate.models import IdeationState, RetrievedChunk

ORCHESTRATOR_TAG = "orchestrator"
MAX_KNOWLEDGE = 20
MAX_KNOWLEDGE_AFTER_GAPS = 24
MAX_GAPS = 4
GAP_K = 4
EVENT_PIN_K = 8
DATA_SOURCE_PIN_K = 4
PINNED_KINDS: tuple[str, ...] = ("event", "data-source")
ORCHESTRATOR_SCHEMA = obj({"queries": arr(str_(), 1, 6)})
ORCHESTRATOR_SYSTEM = (
    "You turn a hackathon theme into short retrieval queries for a knowledge base of hackathon "
    "guidance, public data sources, project archetypes and antipatterns. Queries are 2-8 words, "
    "concrete, and cover the judging criteria and the preferred technologies."
)


def orchestrator_prompt(state: IdeationState) -> str:
    """User prompt: theme, constraints block and the expansion rule."""
    return (
        f"Theme: {state.theme}\n{constraints_block(state.constraints)}\n\n"
        "Write 1-6 search queries that expand the theme: one per judging criterion and one per "
        "preferred technology (when given), plus queries for demo strategy and public data sources "
        "relevant to the theme. Do not repeat the theme verbatim."
    )


def is_pinned(rc: RetrievedChunk) -> bool:
    """Event and data-source chunks are kept regardless of score."""
    return rc.chunk.metadata.get("kind") in PINNED_KINDS


def score_key(rc: RetrievedChunk) -> tuple[float, str]:
    """Ranked-output sort key ``(-score, id)``."""
    return (-rc.score, rc.chunk.id)


def merge_best(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Dedupe by chunk id keeping the highest-scoring copy (first seen wins ties), in first-seen order."""
    best: dict[str, RetrievedChunk] = {}
    for rc in chunks:
        current = best.get(rc.chunk.id)
        if current is None or rc.score > current.score:
            best[rc.chunk.id] = rc
    return list(best.values())


def cap_knowledge(base: list[RetrievedChunk], extras: list[RetrievedChunk], cap: int) -> tuple[list[RetrievedChunk], int]:
    """Add ``extras`` to ``base`` up to ``cap`` chunks; pinned extras always survive, others by ``(-score, id)``.

    ``base`` is never dropped. Returns the merged list sorted by ``(-score, id)`` and the number added.
    """
    known = {rc.chunk.id for rc in base}
    new = [rc for rc in merge_best(extras) if rc.chunk.id not in known]
    pinned = [rc for rc in new if is_pinned(rc)]
    rest = sorted((rc for rc in new if not is_pinned(rc)), key=score_key)
    room = max(0, cap - len(base) - len(pinned))
    kept = pinned + rest[:room]
    return sorted(base + kept, key=score_key), len(kept)


class OrchestratorAgent(Agent):
    """Expands the theme into queries, retrieves and pins the knowledge, loads memory context."""

    name = "orchestrator"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        request = ctx.request(
            ORCHESTRATOR_TAG, ORCHESTRATOR_SYSTEM, orchestrator_prompt(state), ORCHESTRATOR_SCHEMA, effort=ctx.settings.effort_light
        )
        data = ctx.llm.complete(request).data
        raw = data.get("queries", []) if isinstance(data, dict) else []
        expansions = [str(q).strip() for q in raw if str(q).strip()]
        angles = list(state.strategy.retrieval_angles) if state.strategy else []
        state.queries = list(dict.fromkeys([state.theme] + angles + expansions))

        retrieved: list[RetrievedChunk] = []
        for query in state.queries:
            retrieved.extend(ctx.retrieve(query))
        retrieved.extend(ctx.retrieve(state.theme, k=EVENT_PIN_K, kind="event"))
        data_query = " ".join([state.theme] + list(state.constraints.tech_preferences))
        retrieved.extend(ctx.retrieve(data_query, k=DATA_SOURCE_PIN_K, kind="data-source"))
        state.knowledge, _ = cap_knowledge([], retrieved, MAX_KNOWLEDGE)
        state.memory_context = memory_context_for(state.theme, ctx.memory, include_mock=ctx.llm.provider == "mock")
        return state


class RetrieveMoreAgent(Agent):
    """Corrective retrieval for the research coverage gaps; no LLM call."""

    name = "retrieve_more"

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        gaps = list(state.research.coverage_gaps[:MAX_GAPS]) if state.research else []
        extras: list[RetrievedChunk] = []
        for gap in gaps:
            extras.extend(ctx.retrieve(gap, k=GAP_K))
        state.knowledge, added = cap_knowledge(state.knowledge, extras, MAX_KNOWLEDGE_AFTER_GAPS)
        state.coverage_gaps = gaps
        state.retrieve_more_added = added
        return state


def after_retrieve_more(settings: Settings) -> Condition:
    """Condition A: research again while gaps added chunks and rounds remain, else domain_expert."""

    def choose(state: IdeationState) -> str:
        if state.retrieve_more_added >= 1 and state.retrieval_rounds < settings.max_retrieval_rounds:
            return ResearchAgent.name
        return DomainExpertAgent.name

    return choose


def planned_rounds(state: IdeationState, settings: Settings) -> int:
    """``min(strategy.rounds or settings.max_iterations, settings.max_iterations)`` (§18.3 loop rule B)."""
    planned = state.strategy.rounds if state.strategy and state.strategy.rounds else settings.max_iterations
    return min(planned, settings.max_iterations)


def after_evaluator(settings: Settings) -> Condition:
    """Condition B (the ONLY loop rule): another creativity round while too few strong ideas and rounds remain."""

    def choose(state: IdeationState) -> str:
        strong = [
            v for v in state.verdicts
            if not v.consensus.disqualified and v.consensus.weighted_score >= settings.accept_threshold
        ]
        if len(strong) < settings.min_strong_ideas and state.iteration < planned_rounds(state, settings):
            return CreativityAgent.name
        return SynthesizerAgent.name

    return choose


def build_default_graph(settings: Settings, run_id: str = "") -> Graph:
    """[strategist ->] orchestrator -> research -> retrieve_more -> (A) -> domain_expert -> creativity -> evaluator -> (B) -> synthesizer -> [reflector ->] END.

    The strategist and the reflector are the meta layer (DESIGN-META §18.3); each is present only
    when its setting is on. ``run_id`` is stamped on what the reflector writes to meta memory.
    """
    graph = Graph()
    agents: list = [StrategistAgent()] if settings.strategist else []
    agents.extend(
        [
            OrchestratorAgent(),
            ResearchAgent(),
            RetrieveMoreAgent(),
            DomainExpertAgent(),
            CreativityAgent(),
            EvaluatorAgent(),
            SynthesizerAgent(),
        ]
    )
    if settings.reflector:
        agents.append(ReflectorAgent(run_id))
    for agent in agents:
        graph.add_node(agent)
    if settings.strategist:
        graph.add_edge(StrategistAgent.name, OrchestratorAgent.name)
    graph.add_edge(OrchestratorAgent.name, ResearchAgent.name)
    graph.add_edge(ResearchAgent.name, RetrieveMoreAgent.name)
    graph.add_conditional_edge(RetrieveMoreAgent.name, after_retrieve_more(settings))
    graph.add_edge(DomainExpertAgent.name, CreativityAgent.name)
    graph.add_edge(CreativityAgent.name, EvaluatorAgent.name)
    graph.add_conditional_edge(EvaluatorAgent.name, after_evaluator(settings))
    if settings.reflector:
        graph.add_edge(SynthesizerAgent.name, ReflectorAgent.name)
        graph.add_edge(ReflectorAgent.name, END)
    else:
        graph.add_edge(SynthesizerAgent.name, END)
    graph.set_entry(StrategistAgent.name if settings.strategist else OrchestratorAgent.name)
    return graph
