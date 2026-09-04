"""Outcome + pattern memory as a JSONL file (docs/DESIGN.md §7).

One record per line: ``{"type": "outcome", **outcome.to_dict()}`` or
``{"type": "pattern", **pattern.to_dict()}``. Patterns produced under the mock provider are
quarantined: they are only returned when ``include_mock`` is set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ideate.knowledge.bm25 import BM25Index
from ideate.models import Outcome, Pattern

MOCK_PROVIDER = "mock"
_RECORD_TYPES = ("outcome", "pattern")


class MemoryStore:
    """Append-only JSONL store of outcomes and learned patterns."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------ io
    def _records(self) -> list[dict]:
        """Every well-formed record in file order; unknown or malformed lines warn and are skipped."""
        if not self.path.exists():
            return []
        records: list[dict] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    self._warn(f"line {lineno} is not valid JSON ({e.msg}); skipped")
                    continue
                kind = record.get("type") if isinstance(record, dict) else None
                if kind not in _RECORD_TYPES:
                    self._warn(f"line {lineno} has unknown record type {kind!r}; skipped")
                    continue
                records.append(record)
        return records

    def _append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def _warn(self, message: str) -> None:
        print(f"ideate: memory {self.path}: {message}", file=sys.stderr)

    # ------------------------------------------------------------------ writes
    def add_outcome(self, outcome: Outcome) -> None:
        """Append an outcome record."""
        self._append({"type": "outcome", **outcome.to_dict()})

    def add_pattern(self, pattern: Pattern) -> None:
        """Append a pattern record (its ``provider`` decides the mock quarantine)."""
        self._append({"type": "pattern", **pattern.to_dict()})

    def clear(self) -> None:
        """Forget everything: the file is removed."""
        if self.path.exists():
            self.path.unlink()

    # ------------------------------------------------------------------ reads
    def __len__(self) -> int:
        return len(self._records())

    def outcomes(self) -> list[Outcome]:
        """All recorded outcomes in file order."""
        return [Outcome.from_dict(r) for r in self._records() if r["type"] == "outcome"]

    def patterns(self, kind: str | None = None, include_mock: bool = False) -> list[Pattern]:
        """Patterns in file order, filtered by ``kind``; mock-provider patterns only with ``include_mock``."""
        out: list[Pattern] = []
        for record in self._records():
            if record["type"] != "pattern":
                continue
            pattern = Pattern.from_dict(record)
            if kind is not None and pattern.kind != kind:
                continue
            if pattern.provider == MOCK_PROVIDER and not include_mock:
                continue
            out.append(pattern)
        return out

    def relevant_patterns(
        self, query: str, kind: str | None = None, k: int = 5, include_mock: bool = False
    ) -> list[Pattern]:
        """Top-``k`` patterns by BM25 over ``text + tags`` (index built on demand; zero scores omitted)."""
        candidates = self.patterns(kind=kind, include_mock=include_mock)
        if not candidates or k <= 0:
            return []
        by_id: dict[str, Pattern] = {}
        index = BM25Index()
        for pattern in candidates:
            if pattern.id in by_id:
                continue
            by_id[pattern.id] = pattern
            index.add(pattern.id, pattern.text + " " + " ".join(pattern.tags))
        index.build()
        return [by_id[pattern_id] for pattern_id, _ in index.search(query, k)]
