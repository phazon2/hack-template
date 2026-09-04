"""Provider resolution and construction (docs/DESIGN.md §4.5).

Only the PRESENCE of credential env vars is tested; their values are never read.
"""

from __future__ import annotations

import os
import sys

from ideate.config import Settings
from ideate.llm.base import LLM, LLMConfigError

CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def resolve_provider(settings: Settings) -> str:
    """`settings.provider` if set; else 'anthropic' when a credential env var exists; else 'mock'."""
    if settings.provider:
        return settings.provider
    if any(name in os.environ for name in CREDENTIAL_ENV_VARS):
        return "anthropic"
    return "mock"


def make_llm(settings: Settings) -> LLM:
    """Build the provider for `settings`; an explicit 'anthropic' never falls back to mock."""
    provider = resolve_provider(settings)
    if provider == "mock":
        from ideate.llm.mock import MockLLM

        llm: LLM = MockLLM(seed=settings.seed)
    elif provider == "anthropic":
        from ideate.llm.anthropic_provider import AnthropicLLM

        llm = AnthropicLLM(settings.model, fallbacks=settings.fallbacks, timeout=settings.timeout)
    else:
        raise LLMConfigError(f"unknown provider {provider!r}", kind="config-fixable", hint="set IDEATE_PROVIDER to mock or anthropic")
    print(f"ideate: provider={provider} model={llm.model}", file=sys.stderr)
    return llm
