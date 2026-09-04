"""TracingLLM, RunContext and the prompt blocks (docs/DESIGN.md §9.1)."""

from __future__ import annotations

import pytest

from ideate.agents.context import (
    RunContext,
    TracingLLM,
    constraints_block,
    is_canonical_tag,
    knowledge_block,
)
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.llm.base import LLMRequest, LLMTransientError
from ideate.llm.mock import MockLLM
from ideate.llm.schema import obj, str_
from ideate.memory.store import MemoryStore
from ideate.models import Chunk, HackathonConstraints, RetrievedChunk, sha256_hex


class _Boom:
    provider = "mock"
    model = "mock-1"

    def complete(self, request: LLMRequest):
        raise LLMTransientError("boom")


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def test_tracing_llm_records_success_step():
    trace = []
    settings = Settings(provider="mock")
    llm = TracingLLM(MockLLM(seed=0), trace, settings, now=lambda: "2026-01-01T00:00:00+00:00")
    assert llm.provider == "mock" and llm.model == "mock-1"
    request = LLMRequest(system="sys", prompt="hello world prompt", tag="research", json_schema=obj({"a": str_()}))
    resp = llm.complete(request)
    assert resp.data["a"].startswith("[mock]")
    assert len(trace) == 1
    step = trace[0]
    assert step.agent == "research"
    assert step.provider == "mock" and step.model == "mock-1" and step.requested_model == "mock-1"
    assert step.prompt_sha256 == sha256_hex("sys\nhello world prompt")
    assert step.input_tokens == resp.input_tokens and step.output_tokens == resp.output_tokens
    assert step.started_at == "2026-01-01T00:00:00+00:00"
    assert step.stop_reason == "end_turn" and step.request_id is None and step.error is None
    assert step.duration_ms >= 0


def test_tracing_llm_records_error_then_reraises():
    trace = []
    llm = TracingLLM(_Boom(), trace, Settings(provider="mock"))
    with pytest.raises(LLMTransientError):
        llm.complete(LLMRequest(system="s", prompt="p", tag="probe"))
    assert len(trace) == 1
    step = trace[0]
    assert step.error == "LLMTransientError: boom"
    assert step.input_tokens == 0 and step.output_tokens == 0
    assert step.agent == "probe" and step.provider == "mock" and step.model == "mock-1"


def test_tracing_llm_verbose_writes_one_stderr_line(capsys):
    llm = TracingLLM(MockLLM(seed=0), [], Settings(provider="mock", verbose=True))
    llm.complete(LLMRequest(system="s", prompt="p", tag="probe"))
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = [line for line in captured.err.splitlines() if line]
    assert len(lines) == 1 and lines[0].startswith("ideate: llm probe mock/mock-1")


def test_tracing_llm_silent_by_default(capsys):
    llm = TracingLLM(MockLLM(seed=0), [], Settings(provider="mock"))
    llm.complete(LLMRequest(system="s", prompt="p", tag="probe"))
    assert capsys.readouterr().err == ""


def test_run_context_request_fills_defaults(kb, tmp_path):
    ctx = make_ctx(kb, tmp_path, max_tokens=1234, effort="xhigh")
    req = ctx.request("research", "sys", "prompt")
    assert (req.tag, req.system, req.prompt) == ("research", "sys", "prompt")
    assert req.max_tokens == 1234 and req.effort == "xhigh" and req.json_schema is None
    schema = obj({"x": str_()})
    light = ctx.request("orchestrator", "s", "p", schema, effort="low")
    assert light.effort == "low" and light.json_schema is schema


def test_run_context_retrieve_records_queries_and_uses_settings(kb, tmp_path):
    ctx = make_ctx(kb, tmp_path, retrieve_k=3)
    hits = ctx.retrieve("public weather api without an account")
    assert len(hits) == 3
    assert ctx.queries_issued == ["public weather api without an account"]
    data = ctx.retrieve("data sources", k=2, kind="data-source")
    assert len(data) == 2 and all(rc.chunk.metadata["kind"] == "data-source" for rc in data)
    assert ctx.queries_issued == ["public weather api without an account", "data sources"]
    assert ctx.kb.retrieve("public weather api without an account", k=3, candidates=ctx.settings.retrieve_candidates) == hits


def test_constraints_block_defaults_and_values():
    assert constraints_block(HackathonConstraints()) == (
        "Hours: 24 | Team: 3 | Judging: default rubric | Prefer: - | Must avoid: - | Tracks: -\nNotes: -"
    )
    c = HackathonConstraints(
        hours=48, team_size=4, judging_criteria=["innovation:40", "impact:60"], tech_preferences=["python", "fastapi"],
        must_avoid=["blockchain"], tracks=["health"], notes="remote event",
    )
    assert constraints_block(c) == (
        "Hours: 48 | Team: 4 | Judging: innovation:40, impact:60 | Prefer: python, fastapi"
        " | Must avoid: blockchain | Tracks: health\nNotes: remote event"
    )


def test_knowledge_block_numbers_snippets():
    chunks = [
        RetrievedChunk(Chunk("doc#0", "doc", "first text", 0, {"title": "Doc", "kind": "guidance"}), 0.9),
        RetrievedChunk(Chunk("apis#2", "apis", "second text", 2, {"title": "APIs", "kind": "data-source"}), 0.5),
        RetrievedChunk(Chunk("bare#0", "bare", "third", 0, {}), 0.1),
    ]
    block = knowledge_block(chunks)
    assert block.split("\n\n") == [
        "[C1] (doc#0; guidance; Doc) first text",
        "[C2] (apis#2; data-source; APIs) second text",
        "[C3] (bare#0; guidance; bare) third",
    ]
    assert knowledge_block([]) == ""


def test_canonical_tags():
    for tag in ("orchestrator", "research", "domain_expert", "creativity", "rerank", "synthesizer", "learn", "probe", "judge:x"):
        assert is_canonical_tag(tag)
    for tag in ("judge:", "judge", "evaluator", "retrieve_more", ""):
        assert not is_canonical_tag(tag)
