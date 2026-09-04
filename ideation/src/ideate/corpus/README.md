# Seed corpus

This directory is the bundled knowledge base that the ideation system searches
(hybrid BM25 + hashed-vector retrieval, then a reranker). Every `.md` or `.txt`
file here becomes one `Document`; `README.md` files are skipped by the loader.
JSON (`list` of objects) and JSONL files are also accepted, one document per item.

## Front-matter contract

Every markdown file starts with a block delimited by `---` lines containing
`key: value` pairs. Keys are lowercased by the loader. A trailing ` # comment`
after a value is stripped.

```
---
title: Demo strategy for hackathons
tags: demo, pitch, judging
kind: guidance          # guidance | data-source | archetype | antipattern | event | evidence
source: (required for kind: evidence)
---
```

- `title` — short, specific. Falls back to the first `# ` heading, then the file stem.
- `tags` — comma-separated; used as chunk metadata and in memory retrieval.
- `kind` — one of `guidance`, `data-source`, `archetype`, `antipattern`, `event`,
  `evidence`. Unknown kinds fall back to `guidance` with a stderr warning.
  The orchestrator pins every `event` chunk and at least four `data-source`
  chunks into every run, so those kinds matter beyond ranking.
- `source` — a URL or citation. Required for `kind: evidence`; optional elsewhere.
  Any other key ends up in `Document.metadata` untouched (`url`, `published`, `authors`).

Document ids are the path relative to this directory with `/` replaced by `__`
and the extension removed (`event/rubric.md` -> `event__rubric`). Chunk ids are
`{doc_id}#{position}`, and those chunk ids are what ideas and research cite.

## Writing guidance that retrieves well

The chunker packs blank-line-separated paragraphs into chunks of about 800
characters, so keep paragraphs self-contained and put the key term inside the
paragraph that explains it. A heading alone does not travel with the text below
it once a chunk boundary falls between them. Prefer concrete, opinionated,
actionable advice over generalities, and never include invented statistics,
fabricated case studies or made-up quotes: the research agent is instructed to
say "no evidence in knowledge base" rather than guess, and it can only do that
honestly if the corpus is honest too. Numbers are fine when they are
definitional ("a 3-minute pitch", "by 25% of the clock").

## Adding event material

Drop the event page, the sponsor API docs and the judging rubric into
`event/` as markdown with `kind: event` (see `event/README.md`). Extra corpora
outside the package can be added with `IDEATE_CORPUS_DIRS` (`os.pathsep`
separated) or `ideate run --corpus DIR`; a document id that appears in two
directories is taken from the later one, with a stderr warning. After changing
any file run `ideate index` (or just `ideate run`, which rebuilds the index
when the corpus fingerprint changes).
