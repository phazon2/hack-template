"""Graph runner rules (docs/DESIGN.md §9.2)."""

from __future__ import annotations

import pytest

from ideate.agents.base import Agent
from ideate.agents.context import RunContext, TracingLLM
from ideate.agents.graph import END, Graph, GraphError
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import HackathonConstraints, IdeationState


class Tick(Agent):
    """Appends its name to ``state.critiques`` so tests can observe execution order."""

    def __init__(self, name: str):
        self.name = name

    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        state.critiques.append(self.name)
        state.iteration += 1
        return state


def make_ctx(kb, tmp_path, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def chain() -> Graph:
    g = Graph()
    for name in ("a", "b", "c"):
        g.add_node(Tick(name))
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", END)
    g.set_entry("a")
    return g


def test_run_visits_nodes_in_order_and_returns_same_state(kb, tmp_path):
    state = IdeationState("t", HackathonConstraints())
    out = chain().run(state, make_ctx(kb, tmp_path))
    assert out is state
    assert state.visited == ["a", "b", "c"]
    assert state.critiques == ["a", "b", "c"]


def test_conditional_edge_loops_until_condition_changes(kb, tmp_path):
    g = Graph()
    g.add_node(Tick("loop"))
    g.add_node(Tick("done"))
    g.add_conditional_edge("loop", lambda s: "loop" if s.iteration < 3 else "done")
    g.add_edge("done", END)
    g.set_entry("loop")
    state = IdeationState("t", HackathonConstraints())
    g.run(state, make_ctx(kb, tmp_path))
    assert state.visited == ["loop", "loop", "loop", "done"]


def test_node_has_exactly_one_outgoing_edge():
    g = Graph()
    g.add_node(Tick("a"))
    g.add_edge("a", END)
    with pytest.raises(GraphError):
        g.add_conditional_edge("a", lambda s: END)
    g2 = Graph()
    g2.add_node(Tick("a"))
    g2.add_conditional_edge("a", lambda s: END)
    with pytest.raises(GraphError):
        g2.add_edge("a", END)


def test_missing_edge_unknown_target_and_entry_errors(kb, tmp_path):
    g = Graph()
    g.add_node(Tick("a"))
    with pytest.raises(GraphError):
        g.run(IdeationState("t", HackathonConstraints()), make_ctx(kb, tmp_path))  # no entry
    g.set_entry("a")
    with pytest.raises(GraphError):  # no outgoing edge
        g.run(IdeationState("t", HackathonConstraints()), make_ctx(kb, tmp_path))
    g.add_edge("a", "ghost")
    with pytest.raises(GraphError):  # unknown target
        g.run(IdeationState("t", HackathonConstraints()), make_ctx(kb, tmp_path))
    with pytest.raises(GraphError):
        g.add_edge("nope", END)
    with pytest.raises(GraphError):
        g.set_entry("nope")
    with pytest.raises(GraphError):
        g.add_node(Tick("a"))
    with pytest.raises(GraphError):
        g.add_node(Tick(""))


def test_max_steps_exceeded_raises(kb, tmp_path):
    g = Graph()
    g.add_node(Tick("loop"))
    g.add_conditional_edge("loop", lambda s: "loop")
    g.set_entry("loop")
    state = IdeationState("t", HackathonConstraints())
    with pytest.raises(GraphError, match="max_steps"):
        g.run(state, make_ctx(kb, tmp_path), max_steps=5)
    assert state.visited == ["loop"] * 5


def test_verbose_prints_node_lines_to_stderr_only(kb, tmp_path, capsys):
    chain().run(IdeationState("t", HackathonConstraints()), make_ctx(kb, tmp_path, verbose=True))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "ideate: node_start a", "ideate: node_end a",
        "ideate: node_start b", "ideate: node_end b",
        "ideate: node_start c", "ideate: node_end c",
    ]


def test_quiet_by_default(kb, tmp_path, capsys):
    chain().run(IdeationState("t", HackathonConstraints()), make_ctx(kb, tmp_path))
    assert capsys.readouterr() == ("", "")
