"""LLM protocol, request/response types and the error taxonomy (docs/DESIGN.md §4.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ideate.models import BLOCKER_KINDS


@dataclass
class LLMRequest:
    system: str
    prompt: str
    tag: str  # canonical tag, see DESIGN §9.1
    json_schema: dict | None = None
    max_tokens: int = 16000
    effort: str = "high"  # low|medium|high|xhigh|max


@dataclass
class LLMResponse:
    text: str
    data: dict | list | None  # parsed + validated JSON when json_schema was given
    provider: str  # "mock" | "anthropic"
    model: str  # SERVED model
    requested_model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    message_id: str | None = None
    request_id: str | None = None
    stop_reason: str | None = None
    fallback_ran: bool = False


@runtime_checkable
class LLM(Protocol):
    provider: str
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class LLMError(Exception):
    """Base class for all provider errors."""


class LLMConfigError(LLMError):
    """Something a human must fix. `kind` is one of models.BLOCKER_KINDS."""

    def __init__(self, message: str, kind: str = "config-fixable", hint: str = ""):
        if kind not in BLOCKER_KINDS:
            raise ValueError(f"kind must be one of {BLOCKER_KINDS}, got {kind!r}")
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.hint = hint

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class LLMRefusal(LLMError):
    """The model declined (stop_reason == "refusal"). Genuinely human-only."""

    def __init__(self, category: str | None, explanation: str | None):
        super().__init__(f"refusal category={category!r}: {explanation or 'no explanation'}")
        self.category = category
        self.explanation = explanation


class LLMTransientError(LLMError):
    """Rate limit / server error / network: retry later."""


class LLMBadOutput(LLMError):
    """Output did not satisfy the schema after the single corrective retry, or was truncated."""
