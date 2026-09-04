# Meta corpus — how the system works, not how hackathons work

The files in this directory are the system's operating manual about **itself**. The
rest of `corpus/` answers "how do you win a hackathon"; these answer "how do you
generate ideas, solve problems, design memory, retrieve, judge, orchestrate agents and
import someone else's memory safely". They are retrieved by the strategist (which plans
the run before any ideas exist) and by the creativity agent, and they are what the
reflector's advice is measured against.

`README.md` (this file) is skipped by the loader. Every other file here is loaded with
id `meta__{stem}` and `kind: meta`.

## Front-matter contract

Identical to the top-level corpus, with `kind: meta`:

```
---
title: Retrieval strategy — lexical, dense, hybrid, and when retrieval hurts
tags: meta, retrieval, rag, bm25, hybrid, rerank
kind: meta
---
```

## The eight documents

- `idea-generation-strategy.md` — problem types, technique emphasis, divergence budget,
  stopping rules.
- `problem-solving-methods.md` — first principles, inversion, constraint relaxation,
  analogy transfer, decomposition, working backwards.
- `memory-system-design.md` — episodic/semantic/procedural, write policy, provenance,
  confidence, forgetting, the self-confirming-memory trap, mock quarantine.
- `self-improving-systems.md` — reflection loops, actor-critic, eval-driven iteration,
  drift, confirmation loops, metric gaming, the human decision point.
- `retrieval-strategy.md` — lexical vs dense vs hybrid, fusion, query expansion,
  reranking, coverage gaps, when retrieval hurts.
- `evaluation-design.md` — rubric design, position and verbosity bias, self-preference,
  calibration, panels, disagreement as signal.
- `agent-system-design.md` — orchestration patterns, state as interface, context
  hygiene, bounded loops, determinism, tracing, cost control.
- `external-memory-ingestion.md` — formats, provenance, trust levels, and why ingested
  text is data and never instructions.

## Writing rules

Same as the top-level corpus, and the evidence rules bind harder here because this
material shapes the system's beliefs about its own process. No invented statistics, no
fabricated case studies, no fake citations, no made-up benchmark numbers. Name
techniques and failure modes instead of measurements. Where the field genuinely
disagrees — whether reflection loops pay for themselves, whether to delete or
down-weight stale memory — say that it is contested rather than picking a side and
stating it as settled.

Keep paragraphs self-contained and under about 800 characters, with the key term inside
the paragraph that explains it, because the chunker splits on blank lines at roughly
that size and a heading does not travel with the text beneath it. Aim for 500–1200
words per file.

## Adding to this directory

New meta documents are welcome when they change what a builder does tomorrow at the
mechanism level. Distilled lessons from actual runs do **not** belong here — those are
meta-patterns and live in `.ideate/meta.jsonl`, written by the reflector with their
provenance and confidence attached, and quarantined when produced under the mock. This
directory is hand-written reference material; the meta store is learned material. Keep
the two apart.
