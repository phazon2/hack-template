"""Deterministic offline LLM (docs/DESIGN.md §4.3). Placeholder output, never evidence.

Never imports `knowledge`: it has its own tiny tokenizer so the llm layer stays below the
knowledge layer in the import DAG.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter, deque

from ideate.llm._common import complete_with_validation
from ideate.llm.base import LLMRequest, LLMResponse

_STOPWORDS = frozenset(
    "a an and are as at be by for from in is it of on or that the this to with you your".split()
)
_WORD_RE = re.compile(r"[a-z0-9]+")
_INDEX_RE = re.compile(r"\[(\d+)\]")
_SALIENT_COUNT = 24
_WORDS_PER_STRING = 4


def _seed(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()[:8], "big")


def salient_tokens(prompt: str) -> list[str]:
    """The 24 most frequent non-stopword tokens of `prompt` (ties alphabetical), padded to 4 with 'mock'."""
    counts = Counter(t for t in _WORD_RE.findall(prompt.lower()) if t not in _STOPWORDS)
    ranked = [tok for tok, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:_SALIENT_COUNT]]
    while len(ranked) < _WORDS_PER_STRING:
        ranked.append("mock")
    return ranked


def _leaf(path: str) -> str:
    stripped = _INDEX_RE.sub("", path)
    return stripped.rsplit(".", 1)[-1] or "value"


def _innermost_index(path: str) -> int | None:
    found = _INDEX_RE.findall(path)
    return int(found[-1]) if found else None


def _array_size(schema: dict) -> int:
    max_items = schema.get("maxItems")
    n = schema.get("minItems") or 0
    if max_items is None or max_items >= 2:
        n = max(n, 2)
    if max_items is not None:
        n = min(n, max_items)
    return n


def _midpoint(schema: dict) -> int | float:
    lo, hi = schema.get("minimum"), schema.get("maximum")
    value: float = (lo + hi) / 2 if lo is not None and hi is not None else 5.0
    if lo is not None:
        value = max(value, lo)
    if hi is not None:
        value = min(value, hi)
    return math.floor(value) if schema.get("type") == "integer" else float(value)


class MockLLM:
    """Schema-driven deterministic generator with optional scripted answers per tag."""

    provider = "mock"
    model = "mock-1"

    def __init__(self, seed: int = 0, scripted: dict[str, list[dict | str]] | None = None):
        self.seed = seed
        self.calls: list[LLMRequest] = []
        self._scripts: dict[str, deque[dict | str]] = {k: deque(v) for k, v in (scripted or {}).items()}

    # ------------------------------------------------------------------ public
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Answer from the script (FIFO) or synthesize from the schema; validated like any provider."""
        return complete_with_validation(request, self._attempt)

    def remaining_scripts(self) -> dict[str, int]:
        """Number of unconsumed scripted entries per key (for tests)."""
        return {k: len(q) for k, q in self._scripts.items()}

    # ------------------------------------------------------------------ internals
    def _attempt(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        text = self._scripted_text(request.tag)
        if text is None:
            text = self._synthesize(request)
        prompt = request.prompt
        return LLMResponse(
            text=text,
            data=None,
            provider=self.provider,
            model=self.model,
            requested_model=self.model,
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
            message_id=f"mock-{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]}",
            request_id=None,
            stop_reason="end_turn",
        )

    def _scripted_text(self, tag: str) -> str | None:
        keys = [tag] + ([tag.split(":", 1)[0]] if ":" in tag else [])
        for key in keys:
            queue = self._scripts.get(key)
            if queue:
                entry = queue.popleft()
                return entry if isinstance(entry, str) else json.dumps(entry)
        return None

    def _synthesize(self, request: LLMRequest) -> str:
        synth = _Synthesizer(self.seed, request.tag, request.prompt)
        if request.json_schema is None:
            return f"[mock] {request.tag}: {synth.words('')}"
        return json.dumps(synth.generate(request.json_schema, ""))

    def generate(self, schema: dict, path: str = "", tag: str = "", prompt: str = "") -> object:
        """Deterministic instance of `schema` at JSON `path` (e.g. 'ideas[3].title') for a tag/prompt."""
        return _Synthesizer(self.seed, tag, prompt).generate(schema, path)


class _Synthesizer:
    """Schema walker for one (seed, tag, prompt) triple (docs/DESIGN.md §4.3 generation rules)."""

    def __init__(self, seed: int, tag: str, prompt: str):
        self.seed, self.tag, self.prompt = seed, tag, prompt
        self.salient = salient_tokens(prompt)

    def words(self, path: str) -> str:
        """Four salient tokens drawn by the rng seeded from seed|tag|prompt(|path)."""
        parts = (self.seed, self.tag, self.prompt) + ((path,) if path else ())
        rng = random.Random(_seed(*parts))
        return " ".join(rng.sample(self.salient, _WORDS_PER_STRING))

    def generate(self, schema: dict, path: str) -> object:
        if "enum" in schema:
            values = schema["enum"]
            return values[(_innermost_index(path) or 0) % len(values)]
        tp = schema.get("type")
        if tp == "object":
            return {k: self.generate(sub, f"{path}.{k}" if path else k) for k, sub in schema.get("properties", {}).items()}
        if tp == "array":
            return [self.generate(schema["items"], f"{path}[{i}]") for i in range(_array_size(schema))]
        if tp == "string":
            i = _innermost_index(path)
            idx = f"#{i}" if i is not None else ""
            return f"[mock] {_leaf(path)}{idx}: {self.words(path)}"
        if tp in ("integer", "number"):
            return _midpoint(schema)
        if tp == "boolean":
            return False
        raise ValueError(f"MockLLM cannot synthesize schema type {tp!r} at {path or '$'}")
