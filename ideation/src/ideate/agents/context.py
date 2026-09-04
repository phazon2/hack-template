"""Run context shared by every agent: traced LLM, retrieval, prompt blocks (docs/DESIGN.md §9.1)."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from ideate.config import Settings
from ideate.evaluation.rubric import Rubric
from ideate.knowledge.retriever import KnowledgeBase
from ideate.llm.base import LLM, LLMRequest, LLMResponse
from ideate.memory.store import MemoryStore
from ideate.models import HackathonConstraints, RetrievedChunk, TraceStep, sha256_hex

# Canonical LLMRequest.tag values (== TraceStep.agent); judge tags are "judge:<persona-slug>".
CANONICAL_TAGS: tuple[str, ...] = (
    "orchestrator",
    "research",
    "domain_expert",
    "creativity",
    "rerank",
    "synthesizer",
    "learn",
    "probe",
)
JUDGE_TAG_PREFIX = "judge:"


def is_canonical_tag(tag: str) -> bool:
    """True for a fixed canonical tag or a ``judge:<slug>`` tag with a non-empty slug."""
    return tag in CANONICAL_TAGS or (tag.startswith(JUDGE_TAG_PREFIX) and len(tag) > len(JUDGE_TAG_PREFIX))


def utc_now() -> str:
    """Current wall-clock time as ISO-8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


class TracingLLM:
    """An ``LLM`` wrapper that appends one ``TraceStep`` per call (success or failure)."""

    def __init__(
        self,
        inner: LLM,
        trace: list[TraceStep],
        settings: Settings,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.inner = inner
        self.trace = trace
        self.settings = settings
        self.now = now or utc_now

    @property
    def provider(self) -> str:
        return self.inner.provider

    @property
    def model(self) -> str:
        return self.inner.model

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Delegate to the inner LLM, recording a trace step; errors are recorded then re-raised."""
        started_at = self.now()
        t0 = time.perf_counter()
        prompt_sha256 = sha256_hex(request.system + "\n" + request.prompt)
        try:
            resp = self.inner.complete(request)
        except Exception as e:
            step = TraceStep(
                agent=request.tag,
                provider=self.inner.provider,
                model=self.inner.model,
                requested_model=self.inner.model,
                prompt_sha256=prompt_sha256,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                started_at=started_at,
                error=f"{type(e).__name__}: {e}",
            )
            self.trace.append(step)
            self._log(step)
            raise
        step = TraceStep(
            agent=request.tag,
            provider=resp.provider,
            model=resp.model,
            requested_model=self.inner.model,
            prompt_sha256=prompt_sha256,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            request_id=resp.request_id,
            started_at=started_at,
            stop_reason=resp.stop_reason,
            error=None,
        )
        self.trace.append(step)
        self._log(step)
        return resp

    def _log(self, step: TraceStep) -> None:
        if not self.settings.verbose:
            return
        status = f"error={step.error}" if step.error else f"in={step.input_tokens} out={step.output_tokens}"
        print(f"ideate: llm {step.agent} {step.provider}/{step.model} {status} {step.duration_ms}ms", file=sys.stderr)


@dataclass
class RunContext:
    """Everything an agent may touch during a run."""

    llm: TracingLLM
    kb: KnowledgeBase
    memory: MemoryStore
    rubric: Rubric
    settings: Settings
    trace: list[TraceStep]
    queries_issued: list[str] = field(default_factory=list)

    def request(
        self,
        tag: str,
        system: str,
        prompt: str,
        json_schema: dict | None = None,
        effort: str | None = None,
    ) -> LLMRequest:
        """Build an ``LLMRequest`` with the run's ``max_tokens`` and default effort filled in."""
        return LLMRequest(
            system=system,
            prompt=prompt,
            tag=tag,
            json_schema=json_schema,
            max_tokens=self.settings.max_tokens,
            effort=effort or self.settings.effort,
        )

    def retrieve(self, query: str, k: int | None = None, kind: str | None = None) -> list[RetrievedChunk]:
        """Retrieve from the knowledge base with the run's settings, recording the query."""
        self.queries_issued.append(query)
        return self.kb.retrieve(
            query,
            k=k or self.settings.retrieve_k,
            candidates=self.settings.retrieve_candidates,
            kind=kind,
        )


def constraints_block(c: HackathonConstraints) -> str:
    """The fixed-format constraints line every agent prompt includes verbatim."""
    return (
        f"Hours: {c.hours} | Team: {c.team_size}"
        f" | Judging: {', '.join(c.judging_criteria) or 'default rubric'}"
        f" | Prefer: {', '.join(c.tech_preferences) or '-'}"
        f" | Must avoid: {', '.join(c.must_avoid) or '-'}"
        f" | Tracks: {', '.join(c.tracks) or '-'}"
        f"\nNotes: {c.notes or '-'}"
    )


def knowledge_block(chunks: list[RetrievedChunk]) -> str:
    """Numbered snippets ``[C{n}] ({chunk.id}; {kind}; {title}) {text}``, one paragraph each."""
    lines = []
    for n, rc in enumerate(chunks, 1):
        kind = rc.chunk.metadata.get("kind", "guidance")
        title = rc.chunk.metadata.get("title", rc.chunk.doc_id)
        lines.append(f"[C{n}] ({rc.chunk.id}; {kind}; {title}) {rc.chunk.text}")
    return "\n\n".join(lines)
