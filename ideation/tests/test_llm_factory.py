"""docs/DESIGN.md §4.5: provider resolution by env-var presence only; construction; stderr line."""

from __future__ import annotations

import os

import pytest

from ideate.config import Settings
from ideate.llm.anthropic_provider import AnthropicLLM
from ideate.llm.base import LLMConfigError
from ideate.llm.factory import CREDENTIAL_ENV_VARS, make_llm, resolve_provider
from ideate.llm.mock import MockLLM


@pytest.fixture
def clean_env(monkeypatch):
    for name in CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_explicit_provider_wins(clean_env, monkeypatch):
    assert resolve_provider(Settings(provider="mock")) == "mock"
    assert resolve_provider(Settings(provider="anthropic")) == "anthropic"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "present")
    assert resolve_provider(Settings(provider="mock")) == "mock"


def test_no_credentials_resolves_to_mock(clean_env):
    assert resolve_provider(Settings()) == "mock"


@pytest.mark.parametrize("name", CREDENTIAL_ENV_VARS)
def test_presence_of_credential_var_resolves_to_anthropic(clean_env, monkeypatch, name):
    monkeypatch.setenv(name, "")
    assert resolve_provider(Settings()) == "anthropic", "presence, not value, must decide"


def test_resolve_never_reads_credential_values(clean_env, monkeypatch):
    class Env(dict):
        def __getitem__(self, key):
            if key in CREDENTIAL_ENV_VARS:
                raise AssertionError(f"read value of {key}")
            return super().__getitem__(key)

        def get(self, key, default=None):
            if key in CREDENTIAL_ENV_VARS:
                raise AssertionError(f"read value of {key}")
            return super().get(key, default)

    env = Env(os.environ)
    env["ANTHROPIC_API_KEY"] = "must-not-be-read"
    monkeypatch.setattr(os, "environ", env)
    assert resolve_provider(Settings()) == "anthropic"


def test_make_llm_mock_uses_seed_and_prints_one_stderr_line(clean_env, capsys):
    llm = make_llm(Settings(provider="mock", seed=7))
    assert isinstance(llm, MockLLM) and llm.seed == 7
    out, err = capsys.readouterr()
    assert out == ""
    assert err == "ideate: provider=mock model=mock-1\n"


def test_make_llm_anthropic_passes_settings_and_never_falls_back(clean_env, monkeypatch, capsys):
    import anthropic

    built = {}

    class Recorder:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr(anthropic, "Anthropic", Recorder)
    settings = Settings(provider="anthropic", model="claude-opus-4-8", fallbacks=False, timeout=42.0)
    llm = make_llm(settings)
    assert isinstance(llm, AnthropicLLM)
    assert llm.model == "claude-opus-4-8" and llm.fallbacks is False and llm.timeout == 42.0
    assert built == {"timeout": 42.0}
    assert capsys.readouterr().err == "ideate: provider=anthropic model=claude-opus-4-8\n"


def test_make_llm_anthropic_without_package_raises_not_mock(clean_env, monkeypatch, capsys):
    import sys

    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(LLMConfigError) as ei:
        make_llm(Settings(provider="anthropic"))
    assert ei.value.kind == "config-fixable"
    assert capsys.readouterr().err == ""


def test_make_llm_unknown_provider(clean_env):
    settings = Settings()
    settings.provider = "openai"
    with pytest.raises(LLMConfigError) as ei:
        make_llm(settings)
    assert ei.value.kind == "config-fixable"


def test_default_settings_with_credential_present_builds_anthropic(clean_env, monkeypatch, capsys):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: object())
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "")
    llm = make_llm(Settings())
    assert isinstance(llm, AnthropicLLM) and llm.model == "claude-opus-5"
    assert capsys.readouterr().err == "ideate: provider=anthropic model=claude-opus-5\n"
