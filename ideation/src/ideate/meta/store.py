"""Meta memory as a JSONL file (docs/DESIGN-META.md §18.2).

One record per line: ``{"type": "reflection" | "meta_pattern" | "memory_source", **obj.to_dict()}``.
Reflections and meta-patterns produced under the mock provider are quarantined exactly like
outcome patterns: they are only returned when ``include_mock`` is set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ideate.knowledge.bm25 import BM25Index
from ideate.models import MemorySource, MetaPattern, RunReflection

MOCK_PROVIDER = "mock"
REFLECTION = "reflection"
META_PATTERN = "meta_pattern"
MEMORY_SOURCE = "memory_source"
_RECORD_TYPES = (REFLECTION, META_PATTERN, MEMORY_SOURCE)
MAX_CONFIDENCE = 0.95
MERGE_DECAY = 0.6  # each fresh observation removes 40% of the remaining doubt


class MetaStore:
    """JSONL store of run reflections, meta-patterns and ingested memory sources."""

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

    def _rewrite(self, records: list[dict]) -> None:
        """Replace the file with ``records`` in the given order (merge-on-write keeps line order)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def _warn(self, message: str) -> None:
        print(f"ideate: meta {self.path}: {message}", file=sys.stderr)

    # ------------------------------------------------------------------ writes
    def add_reflection(self, reflection: RunReflection) -> None:
        """Append a run reflection (its ``provider`` decides the mock quarantine)."""
        self._append({"type": REFLECTION, **reflection.to_dict()})

    def add_meta_pattern(self, pattern: MetaPattern) -> MetaPattern:
        """Merge-on-write by id: a repeat observation bumps ``observations`` and ``confidence``.

        A pattern whose id is not stored yet is appended as given. A repeat rewrites the stored
        record in place, so line order never changes. Returns the record now on disk.
        """
        records = self._records()
        for position, record in enumerate(records):
            if record["type"] != META_PATTERN or record.get("id") != pattern.id:
                continue
            stored = MetaPattern.from_dict(record)
            stored.observations += 1
            stored.confidence = min(MAX_CONFIDENCE, round(1 - (1 - stored.confidence) * MERGE_DECAY, 4))
            records[position] = {"type": META_PATTERN, **stored.to_dict()}
            self._rewrite(records)
            return stored
        self._append({"type": META_PATTERN, **pattern.to_dict()})
        return pattern

    def add_source(self, source: MemorySource) -> None:
        """Register an ingested memory source; re-registering the same id replaces it in place."""
        records = self._records()
        for position, record in enumerate(records):
            if record["type"] == MEMORY_SOURCE and record.get("id") == source.id:
                records[position] = {"type": MEMORY_SOURCE, **source.to_dict()}
                self._rewrite(records)
                return
        self._append({"type": MEMORY_SOURCE, **source.to_dict()})

    def clear(self) -> None:
        """Forget everything: the file is removed."""
        if self.path.exists():
            self.path.unlink()

    # ------------------------------------------------------------------ reads
    def __len__(self) -> int:
        return len(self._records())

    def reflections(self, include_mock: bool = False) -> list[RunReflection]:
        """Run reflections in file order; mock-provider reflections only with ``include_mock``."""
        out: list[RunReflection] = []
        for record in self._records():
            if record["type"] != REFLECTION:
                continue
            reflection = RunReflection.from_dict(record)
            if reflection.provider == MOCK_PROVIDER and not include_mock:
                continue
            out.append(reflection)
        return out

    def meta_patterns(
        self, kind: str | None = None, scope: str | None = None, include_mock: bool = False
    ) -> list[MetaPattern]:
        """Meta-patterns in file order, filtered by ``kind``/``scope``; mock rows need ``include_mock``."""
        out: list[MetaPattern] = []
        for record in self._records():
            if record["type"] != META_PATTERN:
                continue
            pattern = MetaPattern.from_dict(record)
            if kind is not None and pattern.kind != kind:
                continue
            if scope is not None and pattern.scope != scope:
                continue
            if pattern.provider == MOCK_PROVIDER and not include_mock:
                continue
            out.append(pattern)
        return out

    def relevant_meta_patterns(
        self,
        query: str,
        kind: str | None = None,
        scope: str | None = None,
        k: int = 5,
        include_mock: bool = False,
    ) -> list[MetaPattern]:
        """Top-``k`` by BM25 over ``text + tags`` multiplied by confidence, sorted by ``(-score, id)``."""
        candidates = self.meta_patterns(kind=kind, scope=scope, include_mock=include_mock)
        if not candidates or k <= 0:
            return []
        by_id: dict[str, MetaPattern] = {}
        index = BM25Index()
        for pattern in candidates:
            if pattern.id in by_id:
                continue
            by_id[pattern.id] = pattern
            index.add(pattern.id, pattern.text + " " + " ".join(pattern.tags))
        index.build()
        scored = [(pid, score * by_id[pid].confidence) for pid, score in index.search(query, len(by_id))]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return [by_id[pid] for pid, _ in scored[:k]]

    def sources(self) -> list[MemorySource]:
        """Every registered memory source in file order."""
        return [MemorySource.from_dict(r) for r in self._records() if r["type"] == MEMORY_SOURCE]

    def source_for(self, path: str) -> MemorySource | None:
        """The registered source whose ``path`` matches, else ``None`` (last registration wins)."""
        found: MemorySource | None = None
        for source in self.sources():
            if source.path == str(path):
                found = source
        return found
