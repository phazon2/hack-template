"""Anthropic provider (docs/DESIGN.md §4.4). The `anthropic` package is imported lazily.

Credentials are never read or passed: the SDK client resolves them itself.
"""

from __future__ import annotations

from typing import Any

from ideate.llm._common import complete_with_validation
from ideate.llm.base import LLMBadOutput, LLMConfigError, LLMError, LLMRefusal, LLMRequest, LLMResponse, LLMTransientError
from ideate.llm.schema import for_api

FALLBACK_BETA = "server-side-fallback-2026-07-01"
CREDENTIALS_HINT = "set ANTHROPIC_API_KEY (or log in with the Anthropic CLI); ideate never prompts for or stores a key"
FORBIDDEN_KWARGS = ("temperature", "top_p", "top_k", "thinking")


class AnthropicLLM:
    """Structured-output calls through `client.beta.messages.stream` with server-side fallbacks."""

    provider = "anthropic"

    def __init__(self, model: str, fallbacks: bool = True, timeout: float = 600.0, client: Any = None):
        try:
            import anthropic
        except ImportError as e:
            raise LLMConfigError("anthropic package not installed", kind="config-fixable", hint='pip install "ideate[anthropic]"') from e
        self._sdk = anthropic
        self.model = model
        self.fallbacks = fallbacks
        self.timeout = timeout
        try:
            self.client = client or anthropic.Anthropic(timeout=timeout)
        except anthropic.AnthropicError as e:
            raise self._translate(e) from e

    # ------------------------------------------------------------------ public
    def complete(self, request: LLMRequest) -> LLMResponse:
        """One streamed call, validated against the schema with one corrective retry."""
        return complete_with_validation(request, self._attempt)

    def build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        """The exact keyword arguments sent to `beta.messages.stream` for `request`."""
        output_config: dict[str, Any] = {"effort": request.effort}
        if request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": for_api(request.json_schema)}
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.prompt}],
            output_config=output_config,
        )
        if self.fallbacks:
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        return kwargs

    # ------------------------------------------------------------------ internals
    def _attempt(self, request: LLMRequest) -> LLMResponse:
        try:
            with self.client.beta.messages.stream(**self.build_kwargs(request)) as stream:
                message = stream.get_final_message()
        except self._sdk.AnthropicError as e:
            raise self._translate(e) from e
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise LLMRefusal(getattr(details, "category", None), getattr(details, "explanation", None))
        if message.stop_reason == "max_tokens" and request.json_schema is not None:
            raise LLMBadOutput(f"output truncated at max_tokens={request.max_tokens}; raise IDEATE_MAX_TOKENS")
        text = next((block.text for block in message.content if getattr(block, "type", None) == "text"), None)
        if text is None:
            raise LLMBadOutput(f"no text block in response (stop_reason={message.stop_reason!r})")
        usage = message.usage
        iterations = getattr(usage, "iterations", None) or []
        fallback_ran = any(getattr(it, "type", None) == "fallback_message" for it in iterations) or message.model != self.model
        return LLMResponse(
            text=text,
            data=None,
            provider=self.provider,
            model=message.model,
            requested_model=self.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            message_id=message.id,
            request_id=getattr(message, "_request_id", None),
            stop_reason=message.stop_reason,
            fallback_ran=fallback_ran,
        )

    def _translate(self, e: Exception) -> LLMError:
        """Map an SDK exception to the ideate error taxonomy (most specific first)."""
        sdk = self._sdk
        if isinstance(e, sdk.AuthenticationError):
            return LLMConfigError(f"authentication failed: {e}", kind="do-it-myself", hint=CREDENTIALS_HINT)
        if isinstance(e, sdk.PermissionDeniedError):
            return LLMConfigError(f"permission denied: {e}", kind="do-it-myself", hint="use credentials that are allowed to call this model")
        if isinstance(e, sdk.NotFoundError):
            return LLMConfigError(f"unknown model {self.model!r}: {e}", kind="config-fixable", hint="unknown model; set IDEATE_MODEL / --model")
        if isinstance(e, sdk.BadRequestError):
            return LLMConfigError(str(e), kind="config-fixable", hint="fix the request parameters (model, max_tokens, effort) named in the server message")
        if isinstance(e, (sdk.RateLimitError, sdk.InternalServerError, sdk.APIConnectionError)):
            return LLMTransientError(f"{type(e).__name__}: {e}")
        if isinstance(e, sdk.APIStatusError):
            if e.status_code >= 500:
                return LLMTransientError(f"server error {e.status_code}: {e}")
            return LLMConfigError(f"API error {e.status_code}: {e}", kind="config-fixable", hint="see the server message")
        kind = "do-it-myself" if "api_key" in str(e).lower() else "config-fixable"
        hint = CREDENTIALS_HINT if kind == "do-it-myself" else "see the error message"
        return LLMConfigError(f"{type(e).__name__}: {e}", kind=kind, hint=hint)
