"""Pipeline facade: ``IdeationSystem`` and ``IdeationResult.from_state`` (docs/DESIGN.md §11)."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ideate import __version__
from ideate.agents.context import RunContext, TracingLLM, utc_now
from ideate.agents.evaluator import judge_context, persona_text
from ideate.agents.orchestrator import build_default_graph
from ideate.config import Settings
from ideate.evaluation.judge import PanelJudge, compare_ideas
from ideate.evaluation.rubric import Rubric
from ideate.improvement.feedback import learn_from_outcome
from ideate.knowledge.embeddings import HashingEmbedder
from ideate.knowledge.loaders import load_corpus
from ideate.knowledge.rerank import LLMReranker
from ideate.knowledge.retriever import FORMAT_VERSION, KnowledgeBase, corpus_fingerprint
from ideate.llm.base import LLM, LLMConfigError, LLMRequest
from ideate.llm.factory import make_llm
from ideate.llm.schema import bool_, obj, str_
from ideate.memory.store import MemoryStore
from ideate.models import (
    Document,
    HackathonConstraints,
    Idea,
    IdeationResult,
    IdeationState,
    Outcome,
    PanelVerdict,
    Pattern,
)

MOCK_PROVIDER = "mock"
PROBE_TAG = "probe"
PROBE_SCHEMA = obj({"ok": bool_(), "model_self_report": str_()})
PROBE_SYSTEM = "You are a connectivity probe. Answer with JSON only."
PROBE_PROMPT = 'Reply with {"ok": true, "model_self_report": "<the model name you believe you are>"}.'
RESULT_FILE = "result.json"
REPORT_FILE = "report.md"
RECEIPT_STAMP = "%Y%m%dT%H%M%SZ"


def result_from_state(
    state: IdeationState, ctx: RunContext, settings: Settings, run_id: str, created_at: str
) -> IdeationResult:
    """Freeze a finished run into an ``IdeationResult`` (queries come from ``ctx.queries_issued``)."""
    provider = ctx.llm.provider
    return IdeationResult(
        run_id=run_id,
        created_at=created_at,
        version=__version__,
        theme=state.theme,
        constraints=state.constraints,
        provider=provider,
        model=ctx.llm.model,
        settings=settings.to_dict(),
        queries=list(ctx.queries_issued),
        knowledge=list(state.knowledge),
        research=state.research,
        assessment=state.assessment,
        ideas=list(state.ideas),
        verdicts=list(state.verdicts),
        ranking=list(state.ranking),
        proposal=state.proposal,
        iterations=state.iteration,
        retrieval_rounds=state.retrieval_rounds,
        coverage_gaps=list(state.coverage_gaps),
        trace=list(ctx.trace),
        is_placeholder=provider == MOCK_PROVIDER,
    )


# ``IdeationResult.from_state`` lives here, not in models.py (DESIGN §2.1).
IdeationResult.from_state = staticmethod(result_from_state)  # type: ignore[attr-defined]


def receipt_stamp(timestamp: str) -> str:
    """``probe-<UTC timestamp>`` file stem for an ISO-8601 timestamp (naive times count as UTC)."""
    dt = datetime.fromisoformat(timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(RECEIPT_STAMP)


class IdeationSystem:
    """The public facade: ideate / judge / learn / probe plus index and run persistence."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLM | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.settings = settings if settings is not None else Settings.from_env()
        self.llm = llm
        self.now = now or utc_now
        self.memory = MemoryStore(self.settings.memory_path)

    # ------------------------------------------------------------------ providers
    def _llm(self) -> LLM:
        return self.llm if self.llm is not None else make_llm(self.settings)

    def _tracing(self, llm: LLM, trace: list) -> TracingLLM:
        return TracingLLM(llm, trace, self.settings, now=self.now)

    # ------------------------------------------------------------------ ideate
    def ideate(self, theme: str, constraints: HackathonConstraints | None = None) -> IdeationResult:
        """Run the default agent graph for ``theme`` and return the frozen result."""
        constraints = constraints if constraints is not None else HackathonConstraints()
        settings = self.settings
        llm = self._llm()
        is_mock = llm.provider == MOCK_PROVIDER
        kb = self.load_or_build_index()
        kb.add_memory_patterns(self.memory.patterns(include_mock=is_mock))
        rubric = Rubric.from_judging_criteria(constraints.judging_criteria)
        trace: list = []
        ctx = RunContext(self._tracing(llm, trace), kb, self.memory, rubric, settings, trace)
        if settings.reranker == "llm":
            kb.reranker = LLMReranker(ctx.llm, effort=settings.effort_light)
        elif settings.reranker == "none":
            kb.reranker = None
        state = IdeationState(theme, constraints)
        build_default_graph(settings).run(state, ctx)
        return result_from_state(state, ctx, settings, run_id=uuid.uuid4().hex[:12], created_at=self.now())

    # ------------------------------------------------------------------ judge
    def judge(
        self, ideas: list[Idea], theme: str, constraints: HackathonConstraints | None = None
    ) -> tuple[list[PanelVerdict], list[str]]:
        """Judge externally supplied ideas with the persona panel; empty ids become ``idea-0-{n}``."""
        constraints = constraints if constraints is not None else HackathonConstraints()
        for n, idea in enumerate(ideas, 1):
            if not idea.id:
                idea.id = f"idea-0-{n}"
        state = IdeationState(theme, constraints)
        rubric = Rubric.from_judging_criteria(constraints.judging_criteria)
        personas = [persona_text(p, state) for p in self.settings.judge_personas]
        llm = self._tracing(self._llm(), [])
        panel = PanelJudge(llm, rubric, personas, constraints=constraints, effort=self.settings.effort_light)
        return compare_ideas(panel, ideas, judge_context(state))

    # ------------------------------------------------------------------ learn
    def learn(self, outcome: Outcome) -> list[Pattern]:
        """Distil ``outcome`` into memory patterns (persisted with the provider that produced them)."""
        return learn_from_outcome(outcome, self._llm(), self.memory, now=self.now, effort=self.settings.effort_light)

    # ------------------------------------------------------------------ probe
    def probe(self) -> dict:
        """One real structured call; refuses under the mock BEFORE touching any file."""
        llm = self._llm()
        if llm.provider == MOCK_PROVIDER:
            raise LLMConfigError(
                "probe requires a real provider; current provider is mock",
                kind="config-fixable",
                hint="set IDEATE_PROVIDER=anthropic and credentials",
            )
        request = LLMRequest(
            system=PROBE_SYSTEM,
            prompt=PROBE_PROMPT,
            tag=PROBE_TAG,
            json_schema=PROBE_SCHEMA,
            max_tokens=self.settings.max_tokens,
            effort=self.settings.effort_light,
        )
        resp = llm.complete(request)
        return {
            "provider": resp.provider,
            "requested_model": resp.requested_model or llm.model,
            "served_model": resp.model,
            "fallback_ran": resp.fallback_ran,
            "message_id": resp.message_id,
            "request_id": resp.request_id,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "stop_reason": resp.stop_reason,
            "timestamp": self.now(),
        }

    # ------------------------------------------------------------------ index
    def _documents(self) -> list[Document]:
        return load_corpus(self.settings.all_corpus_dirs())

    def _configure(self, kb: KnowledgeBase) -> KnowledgeBase:
        kb.bm25_weight = self.settings.bm25_weight
        kb.vector_weight = self.settings.vector_weight
        kb.rrf_k = self.settings.rrf_k
        return kb

    def _try_load(self, documents: list[Document]) -> KnowledgeBase | None:
        """Load the saved index when its meta matches the corpus and settings, else ``None``."""
        s = self.settings
        index_dir = Path(s.index_dir)
        try:
            meta = json.loads((index_dir / "meta.json").read_text(encoding="utf-8"))
            embedder = meta.get("embedder") or {}
            matches = (
                meta.get("format_version") == FORMAT_VERSION
                and meta.get("corpus_fingerprint") == corpus_fingerprint(documents)
                and embedder.get("name") == HashingEmbedder.name
                and int(embedder.get("dim", -1)) == s.embedding_dim
                and int(meta.get("chunk_size", -1)) == s.chunk_size
                and int(meta.get("chunk_overlap", -1)) == s.chunk_overlap
            )
            if not matches:
                return None
            return self._configure(KnowledgeBase.load(index_dir))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def build_index(self, force: bool = False) -> KnowledgeBase:
        """Return a usable index: the saved one when still valid (unless ``force``), else rebuild and save."""
        documents = self._documents()
        if not force:
            kb = self._try_load(documents)
            if kb is not None:
                return kb
        s = self.settings
        kb = KnowledgeBase.build(
            documents,
            embedder=HashingEmbedder(s.embedding_dim),
            chunk_size=s.chunk_size,
            overlap=s.chunk_overlap,
        )
        self._configure(kb)
        kb.save(Path(s.index_dir), now=self.now)
        stats = kb.stats()
        print(
            f"ideate: index rebuilt at {s.index_dir} ({stats['n_docs']} docs, {stats['n_chunks']} chunks)",
            file=sys.stderr,
        )
        return kb

    def load_or_build_index(self) -> KnowledgeBase:
        """Load the saved index when format, fingerprint, embedder and chunk params match; else rebuild."""
        return self.build_index(force=False)

    # ------------------------------------------------------------------ persistence
    def save_run(self, result: IdeationResult) -> Path:
        """Write ``<runs_dir>/<run_id>/result.json`` and ``report.md``; returns the run directory."""
        from ideate.report import render_json, render_markdown

        run_dir = Path(self.settings.runs_dir) / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / RESULT_FILE).write_text(render_json(result) + "\n", encoding="utf-8")
        (run_dir / REPORT_FILE).write_text(render_markdown(result), encoding="utf-8")
        return run_dir

    def save_receipt(self, receipt: dict) -> Path:
        """Write ``<receipts_dir>/probe-<UTC timestamp>.json``; refuses a mock receipt (evidence discipline)."""
        if receipt.get("provider") == MOCK_PROVIDER:
            raise ValueError("refusing to write a receipt from the mock provider: mock output is not evidence")
        receipts_dir = Path(self.settings.receipts_dir)
        receipts_dir.mkdir(parents=True, exist_ok=True)
        path = receipts_dir / f"probe-{receipt_stamp(str(receipt.get('timestamp') or self.now()))}.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def load_result(path: Path | str) -> IdeationResult:
    """Read a ``result.json`` written by ``save_run``."""
    return IdeationResult.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
