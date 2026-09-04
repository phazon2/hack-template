# Event materials go here

This folder is empty on purpose. Before a hackathon, drop the material that is
specific to that event into this directory so the ideation run is grounded in
what the judges and sponsors actually said, not in generic guidance.

## What to add

- The event page: theme, tracks, schedule, team-size and hour limits, prize list.
- The judging rubric, verbatim, including weights. Also pass the weights on the
  command line (`ideate run --criteria "innovation:40,impact:30,demo:30"`) so the
  judge panel scores against the same rubric it reads about.
- Sponsor API docs and challenge briefs: what the API does, how you get access
  (no key / free key / account), rate limits, and any "must use X" rules.
- Anything the organisers said in the kickoff talk about what they want to see.

## Format

Plain markdown (`.md`) or text (`.txt`), one file per source, with front matter:

```
---
title: Acme Hack 2026 judging rubric
tags: rubric, judging, acme
kind: event
source: https://example.org/rubric
---
```

`kind: event` is what matters. The orchestrator pins every `event` chunk into the
context of every run regardless of retrieval score, so keep these files short
and factual: a rubric page and an API summary retrieve far better than a
50-page PDF dump. If you paste a long page, keep the paragraphs short, because
each one is chunked at roughly 800 characters.

`README.md` (this file) is skipped by the loader. Any other file here is loaded
with id `event__{stem}`. Remove or replace the files after the event so the
next run is not contaminated by an old rubric.
