"""A tiny directed graph runner over agents (docs/DESIGN.md §9.2)."""

from __future__ import annotations

import sys
from typing import Callable

from ideate.agents.base import Agent
from ideate.agents.context import RunContext
from ideate.models import IdeationState

END = "END"
DEFAULT_MAX_STEPS = 50

Condition = Callable[[IdeationState], str]


class GraphError(Exception):
    """Malformed graph or a run that could not complete."""


class Graph:
    """Nodes keyed by agent name; each node has exactly one plain edge or one conditional edge."""

    def __init__(self) -> None:
        self.nodes: dict[str, Agent] = {}
        self.edges: dict[str, str] = {}
        self.conditions: dict[str, Condition] = {}
        self.entry: str | None = None

    def add_node(self, agent: Agent) -> None:
        """Register ``agent`` under ``agent.name`` (names must be unique and non-empty)."""
        if not agent.name:
            raise GraphError("agent has no name")
        if agent.name in self.nodes:
            raise GraphError(f"duplicate node {agent.name!r}")
        self.nodes[agent.name] = agent

    def add_edge(self, src: str, dst: str) -> None:
        """Unconditional transition ``src -> dst`` (``dst`` may be END)."""
        self._check_free(src)
        self.edges[src] = dst

    def add_conditional_edge(self, src: str, fn: Condition) -> None:
        """Transition from ``src`` to whatever node name ``fn(state)`` returns (or END)."""
        self._check_free(src)
        self.conditions[src] = fn

    def _check_free(self, src: str) -> None:
        if src not in self.nodes:
            raise GraphError(f"unknown node {src!r}")
        if src in self.edges or src in self.conditions:
            raise GraphError(f"node {src!r} already has an outgoing edge")

    def set_entry(self, name: str) -> None:
        """Choose the node the run starts at."""
        if name not in self.nodes:
            raise GraphError(f"unknown node {name!r}")
        self.entry = name

    def next_node(self, name: str, state: IdeationState) -> str:
        """The successor of ``name`` for this ``state``."""
        if name in self.edges:
            return self.edges[name]
        if name in self.conditions:
            return self.conditions[name](state)
        raise GraphError(f"node {name!r} has no outgoing edge")

    def run(self, state: IdeationState, ctx: RunContext, max_steps: int = DEFAULT_MAX_STEPS) -> IdeationState:
        """Walk from the entry node until END, appending each visited node name to ``state.visited``."""
        if self.entry is None:
            raise GraphError("graph has no entry node")
        name = self.entry
        steps = 0
        while name != END:
            agent = self.nodes.get(name)
            if agent is None:
                raise GraphError(f"unknown node {name!r}")
            if steps >= max_steps:
                raise GraphError(f"max_steps={max_steps} exceeded at node {name!r}")
            state.visited.append(name)
            if ctx.settings.verbose:
                print(f"ideate: node_start {name}", file=sys.stderr)
            agent.run(state, ctx)
            if ctx.settings.verbose:
                print(f"ideate: node_end {name}", file=sys.stderr)
            steps += 1
            name = self.next_node(name, state)
        return state
