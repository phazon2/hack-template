"""Settings for the ideation system (stdlib only). See docs/DESIGN.md §6."""

from __future__ import annotations

import importlib.resources
import os
from dataclasses import dataclass, field, fields
from typing import Any

DEFAULT_MODEL = "claude-opus-5"
ENV_PREFIX = "IDEATE_"

DEFAULT_PERSONAS: list[str] = [
    "hackathon judge who has judged 50 events and rewards a demo that lands in 90 seconds",
    "senior engineer estimating what {team_size} people can ship in {hours} hours",
    "domain expert in {theme} who knows what already exists",
]

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def bundled_corpus_dir() -> str:
    return str(importlib.resources.files("ideate") / "corpus")


class SettingsError(ValueError):
    """Invalid setting value (a config-fixable blocker)."""


@dataclass
class Settings:
    provider: str | None = None  # None -> resolved by llm.factory.resolve_provider
    model: str = DEFAULT_MODEL
    effort: str = "high"
    effort_light: str = "medium"
    max_tokens: int = 16000
    fallbacks: bool = True
    timeout: float = 600.0
    corpus_dirs: list[str] = field(default_factory=list)
    bundled_corpus: bool = True
    index_dir: str = ".ideate/index"
    memory_path: str = ".ideate/memory.jsonl"
    runs_dir: str = ".ideate/runs"
    receipts_dir: str = ".ideate/receipts"
    ideas_per_round: int = 8
    accept_threshold: float = 3.8
    min_strong_ideas: int = 3
    max_iterations: int = 2
    max_retrieval_rounds: int = 2
    judge_personas: list[str] = field(default_factory=lambda: list(DEFAULT_PERSONAS))
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieve_k: int = 8
    retrieve_candidates: int = 40
    embedding_dim: int = 512
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    rrf_k: int = 60
    reranker: str = "lexical"  # lexical | llm | none
    seed: int = 0
    verbose: bool = False

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_env(cls, overrides: dict[str, Any] | None = None, environ: dict[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            key = ENV_PREFIX + f.name.upper()
            if key in env:
                kwargs[f.name] = _parse(f.name, env[key], f.type)
        for k, v in (overrides or {}).items():
            if v is None:
                continue
            if k not in {f.name for f in fields(cls)}:
                raise SettingsError(f"unknown setting: {k}")
            kwargs[k] = v
        s = cls(**kwargs)
        s.validate()
        return s

    def validate(self) -> None:
        if self.reranker not in ("lexical", "llm", "none"):
            raise SettingsError(f"reranker must be lexical|llm|none, got {self.reranker!r}")
        if self.provider is not None and self.provider not in ("mock", "anthropic"):
            raise SettingsError(f"provider must be mock|anthropic, got {self.provider!r}")
        for name in ("effort", "effort_light"):
            if getattr(self, name) not in ("low", "medium", "high", "xhigh", "max"):
                raise SettingsError(f"{name} must be low|medium|high|xhigh|max")
        for name in ("ideas_per_round", "max_iterations", "max_retrieval_rounds", "retrieve_k", "chunk_size", "embedding_dim", "max_tokens"):
            if int(getattr(self, name)) < 1:
                raise SettingsError(f"{name} must be >= 1")
        if not self.judge_personas:
            raise SettingsError("judge_personas must not be empty")

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def all_corpus_dirs(self) -> list[str]:
        dirs = [bundled_corpus_dir()] if self.bundled_corpus else []
        return dirs + list(self.corpus_dirs)


def _parse(name: str, raw: str, tp: Any) -> Any:
    tp_s = tp if isinstance(tp, str) else getattr(tp, "__name__", str(tp))
    try:
        if name in ("corpus_dirs",):
            return [p for p in raw.split(os.pathsep) if p]
        if name in ("judge_personas",):
            return [p.strip() for p in raw.split("|") if p.strip()]
        if tp_s.startswith("bool"):
            low = raw.strip().lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
            raise SettingsError(f"{ENV_PREFIX}{name.upper()}: expected a boolean, got {raw!r}")
        if tp_s.startswith("int"):
            return int(raw)
        if tp_s.startswith("float"):
            return float(raw)
        if tp_s.startswith("str | None"):
            return raw or None
        return raw
    except ValueError as e:
        raise SettingsError(f"{ENV_PREFIX}{name.upper()}: {e}") from e
