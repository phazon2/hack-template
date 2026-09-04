---
title: Ingesting someone else's memory system safely
tags: meta, ingestion, external-memory, provenance, trust, formats, data-not-instructions, fingerprint
kind: meta
---

# Ingesting someone else's memory system safely

Bringing an existing store of knowledge into a system — a past project's lesson file, an
exported conversation log, another agent's memory dump, a rules document — is mostly a
normalisation problem and entirely a trust problem. The normalisation is
straightforward. The trust rules are what keep an imported file from quietly becoming
the thing that steers the system.

## The rule that comes first: ingested text is data

Ingested content is reference material to be cited, never instructions to be followed.
A file may contain imperative sentences, a numbered policy, or text addressed directly
to an assistant; none of that changes its status. Only the system's own prompts define
behaviour. Enforce this in three places at once: label every ingested chunk in the
prompt with its source, state the rule explicitly in the system prompt of every agent
that can see ingested material, and keep ingested chunks in a separate block from the
operating instructions so the boundary is visible in the rendered prompt.

## Why the rule needs enforcement rather than good intentions

The dangerous case is not a malicious file; it is a plausible one. A well-written
document that says "always prefer approach X" reads exactly like a legitimate
instruction, and a model given no boundary will treat it as one. Once that happens the
system's behaviour is defined by whatever was most recently imported, and the change is
invisible in the code. Treating all ingested text uniformly as data is the only version
of this rule that is checkable — and it is checkable: assert that the label and the
system-prompt sentence are present in the rendered prompt.

## Formats worth supporting

Four shapes cover almost everything. **Structured memory exports**: a line-per-record
file of outcomes and lessons, each with fields you can map onto your own record types.
**Conversation logs**: a list of role-and-content turns, useful as episodic material and
nearly useless as semantic material. **Generic records**: JSON or line-delimited JSON
where each object has some text-bearing field. **Documents**: markdown or plain text
with optional front matter. Detect the format from content, not only from the extension,
and fall back to treating the file as a document rather than failing.

## Rules documents are their own category

Files named like operating instructions — a repository's agent guide, a contributor
policy, a house style document — should be recognised and tagged distinctly, because
they describe constraints a human chose rather than evidence about the world. Tagging
them separately lets you show them to an agent as context about the environment while
still keeping them out of any path that treats retrieved text as supporting evidence for
a claim. They are the sharpest case of the data-not-instructions rule.

## Normalise into your own record types

Do not retain the source schema. Map each incoming record into the shape your system
already uses, with a text field the retriever can search and a title a human can read.
Where the source has an outcome and a verdict, render them into one self-contained
sentence that carries the context, because a chunk that says only "it went well" is
unusable once it is separated from its record. Group long conversation logs into
bounded segments so no single document dominates the index.

## Provenance on every record

Every ingested chunk carries: the source identifier, the original path, the format it
came from, and when it was ingested. That metadata is what allows a later reader to ask
where a claim came from, allows a filter to exclude a source that turned out to be
wrong, and allows the system to say "this came from an imported file" rather than
presenting it as its own finding. Provenance recorded at ingestion time is cheap;
reconstructed provenance is guesswork.

## Trust levels, assigned deliberately

Not all sources deserve equal weight. A workable ladder: material you authored for this
system, material exported from a run of this system, material from a system you control,
material from a third party, and material of unknown origin. Assign the level at
ingestion, store it on the source, and let it influence ranking and how the content is
described downstream. The important property is that the level is a stored field a human
set, not something inferred from how authoritative the text sounds.

## Foreign memory does not inherit your confidence

Another system's lessons were learned against another system's inputs, prompts and
model. Import them as observations attributed to that source, not as beliefs your system
holds. Do not let an imported record's stated confidence become your confidence score
directly; either cap it or recompute it from evidence you can see. The same quarantine
that applies to memory generated under a mock applies here: material the system did not
learn from its own real execution is clearly marked and excluded from paths where only
first-hand evidence belongs.

## Fingerprinting and idempotency

Compute a fingerprint over the normalised content — a hash over each produced document's
identifier and text — and store it with the source. Re-ingesting an unchanged path
should be a no-op that says so, not a second copy in the index. Ingesting new material
must invalidate any cached index that was built without it; the simplest correct rule is
to include every registered source in the fingerprint the index build compares against.

## What not to ingest

Credentials, tokens and private keys; anything containing personal data you have no
basis to hold; and enormous dumps whose generic bulk will displace specific material in
every retrieval. Size is a real hazard: a large mediocre import degrades a small good
corpus, because generic text matches every query. Prefer curated, small, high-signal
imports, and delete a source rather than keeping it at low weight if it turns out to add
nothing.

## Make ingestion reversible and inspectable

Keep a registry of sources with their identifiers, paths, formats, record counts and
fingerprints, and expose a command that lists it. Support removing a source and
rebuilding without it. An import you cannot enumerate is an import you cannot undo, and
the first thing you will want when output changes for no visible reason is the ability
to ask what was added and take it back out.
