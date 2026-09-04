"""The agent interface (docs/DESIGN.md §9.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ideate.agents.context import RunContext
from ideate.models import IdeationState


class Agent(ABC):
    """A graph node: mutates the state in place and returns the same object."""

    name: str = ""

    @abstractmethod
    def run(self, state: IdeationState, ctx: RunContext) -> IdeationState:
        """Advance the run; must return the same ``state`` object it was given."""
