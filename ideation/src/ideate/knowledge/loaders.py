"""Corpus loader: markdown/text with front matter, JSON and JSONL (docs/DESIGN.md §5)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from ideate.models import Document

CORPUS_KINDS: tuple[str, ...] = ("guidance", "data-source", "archetype", "antipattern", "event", "evidence")
DEFAULT_KIND = "guidance"
_TEXT_SUFFIXES = {".md", ".txt"}
_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_COMMENT = re.compile(r"\s+#.*$")


def _warn(message: str) -> None:
    print(f"ideate: {message}", file=sys.stderr)


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` block of ``key: value`` lines from the body; keys are lowercased."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            fields: dict[str, str] = {}
            for line in lines[1:end]:
                if ":" not in line or not line.strip():
                    continue
                key, value = line.split(":", 1)
                fields[key.strip().lower()] = _COMMENT.sub("", value).strip()
            return fields, "\n".join(lines[end + 1 :])
    return {}, text


def _split_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    return [t.strip() for t in str(value or "").split(",") if t.strip()]


def _kind(value: object, where: str) -> str:
    kind = str(value or DEFAULT_KIND).strip().lower()
    if kind not in CORPUS_KINDS:
        _warn(f"{where}: unknown kind {kind!r}; using {DEFAULT_KIND!r}")
        return DEFAULT_KIND
    return kind


def _file_id(path: Path, root: Path) -> str:
    return "__".join(path.relative_to(root).with_suffix("").parts)


def _document(id: str, title: str, text: str, source: str, kind: str, tags: list[str], extra: dict, where: str) -> Document:
    if kind == "evidence" and not source:
        _warn(f"{where}: kind 'evidence' without a source")
    metadata = {**extra, "tags": tags, "kind": kind}
    return Document(id=id, title=title, text=text, source=source, metadata=metadata)


def _load_text_file(path: Path, root: Path) -> Document:
    fields, body = parse_front_matter(path.read_text(encoding="utf-8", errors="replace"))
    body = body.strip()
    heading = _HEADING.search(body)
    title = fields.pop("title", "") or (heading.group(1) if heading else path.stem)
    extra = {k: v for k, v in fields.items() if k not in ("tags", "kind", "source")}
    return _document(
        _file_id(path, root), title, body, fields.get("source", ""),
        _kind(fields.get("kind"), str(path)), _split_tags(fields.get("tags")), extra, str(path),
    )


def _load_json_items(path: Path, root: Path) -> list[Document]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".jsonl":
        items = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        loaded = json.loads(raw)
        items = loaded if isinstance(loaded, list) else [loaded]
    file_id = _file_id(path, root)
    docs: list[Document] = []
    for n, item in enumerate(items, 1):
        where = f"{path}#{n}"
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            _warn(f"{where}: skipped (no text)")
            continue
        extra = {k: v for k, v in item.items() if k not in ("title", "text", "source", "kind", "tags")}
        docs.append(
            _document(
                f"{file_id}__{n}", str(item.get("title") or f"{path.stem} {n}"), str(item["text"]).strip(),
                str(item.get("source") or ""), _kind(item.get("kind"), where), _split_tags(item.get("tags")), extra, where,
            )
        )
    return docs


def load_corpus(dirs: list[str | Path]) -> list[Document]:
    """Load every ``.md``/``.txt``/``.json``/``.jsonl`` under ``dirs`` (later dirs override ids)."""
    docs: dict[str, Document] = {}
    origins: dict[str, str] = {}
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            _warn(f"corpus dir not found: {root}")
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            suffix = path.suffix.lower()
            if suffix in _TEXT_SUFFIXES:
                if path.name.lower() == "readme.md":
                    continue
                loaded = [_load_text_file(path, root)]
            elif suffix in (".json", ".jsonl"):
                loaded = _load_json_items(path, root)
            else:
                continue
            for doc in loaded:
                if doc.id in docs:
                    _warn(f"duplicate document id {doc.id!r}: {path} overrides {origins[doc.id]}")
                docs[doc.id] = doc
                origins[doc.id] = str(path)
    return [docs[id] for id in sorted(docs)]
