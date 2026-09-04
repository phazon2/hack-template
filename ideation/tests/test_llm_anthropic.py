"""docs/DESIGN.md §4.4 / §17: AnthropicLLM against a fake client. No network, ever."""

from __future__ import annotations

import inspect
import json
import sys
from types import SimpleNamespace

import httpx2
import pytest

import anthropic
from ideate.llm.anthropic_provider import FALLBACK_BETA, FORBIDDEN_KWARGS, AnthropicLLM
from ideate.llm.base import LLM, LLMBadOutput, LLMConfigError, LLMRefusal, LLMRequest, LLMTransientError
from ideate.llm.schema import arr, enum, int_, num, obj, str_

MODEL = "claude-opus-5"
SCHEMA = obj({"queries": arr(str_(), 1, 6), "score": num(1, 5), "hours": int_(1, 24), "tag": enum(["a", "b"])})
GOOD = {"queries": ["q1"], "score": 4.0, "hours": 3, "tag": "a"}


def message(text_or_blocks=None, *, model=MODEL, stop_reason="end_turn", stop_details=None, iterations=None):
    if isinstance(text_or_blocks, list):
        content = text_or_blocks
    else:
        content = [SimpleNamespace(type="text", text=text_or_blocks if text_or_blocks is not None else json.dumps(GOOD))]
    return SimpleNamespace(
        id="msg_test",
        model=model,
        stop_reason=stop_reason,
        stop_details=stop_details,
        content=content,
        usage=SimpleNamespace(input_tokens=1, output_tokens=1, iterations=iterations),
        _request_id="req_test",
    )


class _Stream:
    def __init__(self, outcome):
        self._outcome = outcome

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class FakeClient:
    """`client.beta.messages.stream(**kwargs)` records kwargs; outcomes are consumed FIFO."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception) and getattr(outcome, "_raise_on_stream", False):
            raise outcome
        return _Stream(outcome)


def llm(*outcomes, fallbacks=True, model=MODEL):
    client = FakeClient(*outcomes)
    return AnthropicLLM(model, fallbacks=fallbacks, timeout=12.5, client=client), client


def req(schema=SCHEMA, effort="high", max_tokens=16000, prompt="user prompt"):
    return LLMRequest(system="system text", prompt=prompt, tag="orchestrator", json_schema=schema, max_tokens=max_tokens, effort=effort)


def sdk_error(cls, status=400, body=None, msg="server says no"):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(msg, response=httpx2.Response(status, request=request), body=body)


# --------------------------------------------------------------------------- construction
def test_protocol_and_attributes():
    provider, client = llm()
    assert isinstance(provider, LLM)
    assert provider.provider == "anthropic" and provider.model == MODEL
    assert provider.client is client and provider.timeout == 12.5 and provider.fallbacks is True


def test_missing_package_raises_config_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(LLMConfigError) as ei:
        AnthropicLLM(MODEL)
    assert ei.value.kind == "config-fixable"
    assert "not installed" in ei.value.message and 'pip install "ideate[anthropic]"' == ei.value.hint


def test_default_client_is_built_without_api_key_argument(monkeypatch):
    seen = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(anthropic, "Anthropic", Recorder)
    provider = AnthropicLLM(MODEL, timeout=7.0)
    assert isinstance(provider.client, Recorder)
    assert seen == {"timeout": 7.0}


# --------------------------------------------------------------------------- call shape
def test_kwargs_shape_with_schema_and_fallbacks():
    provider, client = llm(message())
    provider.complete(req())
    (kw,) = client.calls
    assert kw["model"] == MODEL and kw["max_tokens"] == 16000 and kw["system"] == "system text"
    assert kw["messages"] == [{"role": "user", "content": "user prompt"}]
    assert kw["output_config"]["effort"] == "high"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    for key in FORBIDDEN_KWARGS:
        assert key not in kw
    assert set(FORBIDDEN_KWARGS) == {"temperature", "top_p", "top_k", "thinking"}


def test_sent_schema_is_stripped_at_depth():
    provider, client = llm(message())
    provider.complete(req())
    sent = client.calls[0]["output_config"]["format"]["schema"]
    text = json.dumps(sent)
    for key in ("minimum", "maximum", "minItems", "maxItems"):
        assert key not in text
    assert sent["properties"]["tag"]["enum"] == ["a", "b"]
    assert sent["required"] == ["queries", "score", "hours", "tag"]
    assert "minItems" in SCHEMA["properties"]["queries"]  # original untouched


def test_no_schema_omits_format_and_returns_text():
    provider, client = llm(message("plain answer"))
    r = provider.complete(req(schema=None, effort="medium"))
    assert client.calls[0]["output_config"] == {"effort": "medium"}
    assert r.text == "plain answer" and r.data is None


def test_fallbacks_off_omits_betas_and_fallbacks():
    provider, client = llm(message(), fallbacks=False)
    provider.complete(req())
    assert "betas" not in client.calls[0] and "fallbacks" not in client.calls[0]


def test_kwargs_match_installed_sdk_stream_signature():
    from anthropic.resources.beta.messages import Messages

    params = inspect.signature(Messages.stream).parameters
    for fallbacks in (True, False):
        provider, _ = llm(fallbacks=fallbacks)
        for schema in (SCHEMA, None):
            for key in provider.build_kwargs(req(schema=schema)):
                assert key in params, f"{key!r} is not a beta.messages.stream parameter"


# --------------------------------------------------------------------------- response fields
def test_response_fields_from_message():
    provider, _ = llm(message())
    r = provider.complete(req())
    assert r.data == GOOD and r.text == json.dumps(GOOD)
    assert r.provider == "anthropic" and r.model == MODEL and r.requested_model == MODEL
    assert r.message_id == "msg_test" and r.request_id == "req_test"
    assert r.input_tokens == 1 and r.output_tokens == 1
    assert r.stop_reason == "end_turn" and r.fallback_ran is False


def test_served_model_differs_sets_fallback_ran():
    provider, _ = llm(message(model="claude-opus-4-8"))
    r = provider.complete(req())
    assert r.fallback_ran is True and r.model == "claude-opus-4-8" and r.requested_model == MODEL


def test_fallback_iteration_sets_fallback_ran():
    provider, _ = llm(message(iterations=[SimpleNamespace(type="message"), SimpleNamespace(type="fallback_message")]))
    assert provider.complete(req()).fallback_ran is True


def test_leading_fallback_block_still_yields_first_text_block():
    blocks = [SimpleNamespace(type="fallback", model="claude-opus-4-8"), SimpleNamespace(type="text", text=json.dumps(GOOD)), SimpleNamespace(type="text", text="second")]
    provider, _ = llm(message(blocks))
    r = provider.complete(req())
    assert r.data == GOOD and r.text == json.dumps(GOOD)


def test_no_text_block_raises_bad_output():
    provider, _ = llm(message([SimpleNamespace(type="fallback")]))
    with pytest.raises(LLMBadOutput):
        provider.complete(req())


# --------------------------------------------------------------------------- post-processing
def test_refusal_raises_llm_refusal():
    provider, _ = llm(message(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber", explanation=None)))
    with pytest.raises(LLMRefusal) as ei:
        provider.complete(req())
    assert ei.value.category == "cyber" and ei.value.explanation is None


def test_refusal_without_details():
    provider, _ = llm(message(stop_reason="refusal"))
    with pytest.raises(LLMRefusal) as ei:
        provider.complete(req())
    assert ei.value.category is None


def test_max_tokens_with_schema_raises_without_retry():
    provider, client = llm(message(stop_reason="max_tokens"), message())
    with pytest.raises(LLMBadOutput) as ei:
        provider.complete(req(max_tokens=333))
    assert "max_tokens=333" in str(ei.value) and "IDEATE_MAX_TOKENS" in str(ei.value)
    assert len(client.calls) == 1


def test_max_tokens_without_schema_returns_text():
    provider, _ = llm(message("partial", stop_reason="max_tokens"))
    r = provider.complete(req(schema=None))
    assert r.text == "partial" and r.stop_reason == "max_tokens"


# --------------------------------------------------------------------------- validation policy
def test_coerce_clamps_and_truncates_silently():
    bad = {"queries": ["1", "2", "3", "4", "5", "6", "7"], "score": 9, "hours": 0, "tag": "b"}
    provider, client = llm(message(json.dumps(bad)))
    r = provider.complete(req())
    assert r.data == {"queries": ["1", "2", "3", "4", "5", "6"], "score": 5, "hours": 1, "tag": "b"}
    assert len(client.calls) == 1


def test_one_corrective_retry_then_success():
    provider, client = llm(message(json.dumps({"queries": [], "score": 3, "hours": 3, "tag": "zzz"})), message())
    r = provider.complete(req())
    assert r.data == GOOD and len(client.calls) == 2
    retry_prompt = client.calls[1]["messages"][0]["content"]
    assert retry_prompt.startswith("user prompt\n\nYour previous output failed validation: ")
    assert "minItems" in retry_prompt and "not in enum" in retry_prompt
    assert retry_prompt.endswith("Return only JSON matching the schema.")
    assert client.calls[0]["messages"][0]["content"] == "user prompt"


def test_parse_error_then_second_failure_raises_bad_output():
    provider, client = llm(message("{not json"), message(json.dumps({"queries": ["x"]})))
    with pytest.raises(LLMBadOutput) as ei:
        provider.complete(req())
    assert len(client.calls) == 2
    assert "invalid JSON" in client.calls[1]["messages"][0]["content"]
    assert "missing required property" in str(ei.value)


# --------------------------------------------------------------------------- error chain
@pytest.mark.parametrize(
    "exc,expected_kind",
    [
        (lambda: sdk_error(anthropic.AuthenticationError, 401, {"error": {"message": "invalid x-api-key"}}), "do-it-myself"),
        (lambda: sdk_error(anthropic.PermissionDeniedError, 403), "do-it-myself"),
        (lambda: sdk_error(anthropic.NotFoundError, 404), "config-fixable"),
        (lambda: sdk_error(anthropic.BadRequestError, 400), "config-fixable"),
        (lambda: sdk_error(anthropic.APIStatusError, 409), "config-fixable"),
        (lambda: anthropic.AnthropicError("Could not resolve authentication method: set api_key"), "do-it-myself"),
        (lambda: anthropic.AnthropicError("something else"), "config-fixable"),
    ],
)
def test_config_errors(exc, expected_kind):
    provider, _ = llm(exc())
    with pytest.raises(LLMConfigError) as ei:
        provider.complete(req())
    assert ei.value.kind == expected_kind
    assert isinstance(ei.value.__cause__, anthropic.AnthropicError)


def test_authentication_error_hint_and_never_prompts():
    provider, _ = llm(sdk_error(anthropic.AuthenticationError, 401))
    with pytest.raises(LLMConfigError) as ei:
        provider.complete(req())
    assert ei.value.hint == "set ANTHROPIC_API_KEY (or log in with the Anthropic CLI); ideate never prompts for or stores a key"


def test_not_found_hint_names_model_setting():
    provider, _ = llm(sdk_error(anthropic.NotFoundError, 404))
    with pytest.raises(LLMConfigError) as ei:
        provider.complete(req())
    assert ei.value.hint == "unknown model; set IDEATE_MODEL / --model"


def test_bad_request_keeps_server_message_verbatim():
    provider, _ = llm(sdk_error(anthropic.BadRequestError, 400, msg="max_tokens: 99 > 64000"))
    with pytest.raises(LLMConfigError) as ei:
        provider.complete(req())
    assert ei.value.message == "max_tokens: 99 > 64000"


@pytest.mark.parametrize(
    "exc",
    [
        lambda: sdk_error(anthropic.RateLimitError, 429),
        lambda: sdk_error(anthropic.InternalServerError, 500),
        lambda: sdk_error(anthropic.APIStatusError, 503),
        lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")),
        lambda: anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")),
    ],
)
def test_transient_errors(exc):
    provider, _ = llm(exc())
    with pytest.raises(LLMTransientError):
        provider.complete(req())


def test_error_raised_by_stream_call_itself_is_mapped():
    err = sdk_error(anthropic.RateLimitError, 429)
    err._raise_on_stream = True
    provider, client = llm(err)
    with pytest.raises(LLMTransientError):
        provider.complete(req())
    assert len(client.calls) == 1


def test_transient_error_is_not_retried_by_validation_policy():
    provider, client = llm(sdk_error(anthropic.InternalServerError, 500), message())
    with pytest.raises(LLMTransientError):
        provider.complete(req())
    assert len(client.calls) == 1


def test_non_sdk_exceptions_propagate_unchanged():
    provider, _ = llm(RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        provider.complete(req())
