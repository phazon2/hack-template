---
title: Designing memory for an agent system
tags: meta, memory, episodic, semantic, procedural, provenance, confidence, forgetting, quarantine
kind: meta
---

# Designing memory for an agent system

Memory is the part of an agent system most often built as an afterthought and most
often the reason the system gets worse over time. A memory design is four decisions:
what kinds of memory exist, what earns a write, how a record carries its provenance and
confidence, and how records lose force or leave. Get those wrong and the system will
confidently repeat its own early mistakes back to itself forever.

## Episodic, semantic, procedural

Keep three kinds separate, because they have different write rules and different decay
rules. **Episodic** memory is what happened: this run, this input, this outcome, with a
timestamp and an id. **Semantic** memory is what is believed to be true: a generalisation
distilled from several episodes. **Procedural** memory is how to act: a change to the
process itself — which technique to emphasise, which check to run first. Mixing them
produces a store where a single anecdote reads like a law, which is exactly the failure
you are trying to prevent.

## Episodes are cheap, generalisations are not

Write episodes liberally: they are append-only facts about your own execution and they
cost little. Write semantic and procedural records reluctantly, and only when there is
a stated basis in one or more episodes. The distillation step — reading several episodes
and proposing a generalisation — is where fabrication enters a memory system, so it must
be the step with the most scrutiny. A generalisation with no episode behind it is an
opinion the system will later treat as a finding.

## What earns a write

A record earns a write when it would change a future decision, is specific enough to be
checkable, and is not already in the store. "Retrieval helped" earns nothing. "On data
themes the corpus returned mostly generic guidance and the useful chunks came from the
event material" earns a write, because it names a scope, a mechanism and a next action.
Apply the same bar to failure: a record of what did not work is often more valuable than
a record of what did, and is much less likely to be confabulated after the fact.

## Merge on write instead of accumulating duplicates

Key each generalisation by a hash of its scope and text, and when the same record
arrives again, increase its observation count and raise its confidence toward a ceiling
rather than appending a second copy. This makes a repeated observation stronger than a
one-off without inventing evidence, and it keeps the store from being dominated by
whichever lesson the system happens to phrase most often. Keep the ceiling below
certainty: no amount of self-observation should produce a record the system treats as
beyond revision.

## Provenance is a field, not a comment

Every record carries where it came from: which run, which provider or model produced it,
when it was written, and what kind of evidence it rests on. Provenance is what makes
selective retrieval possible later — retrieving only records from real runs, only
records above a confidence floor, only records scoped to this problem type. A memory
store without provenance fields cannot be filtered, and a store that cannot be filtered
can only be trusted wholesale or deleted wholesale.

## Confidence should move on evidence, not on rereading

Confidence rises when an independent episode supports the record and falls when an
episode contradicts it. It must not rise because the record was retrieved often or
because the model restated it. Restating is not evidence. A system whose confidence
grows with retrieval frequency will converge on whatever it said first, which is the
mechanism behind the self-confirming-memory trap described below.

## Decay and forgetting

Memory needs an exit. Options that work in practice: age-based decay of confidence so
old records must be re-observed to stay strong; capacity limits per scope with eviction
of the lowest-confidence record; and explicit invalidation when the environment changes
(a new rubric, a new corpus, a new model). Forgetting is contested in the sense that
teams disagree about whether to delete or merely down-weight; the defensible default is
to down-weight and keep the record with its provenance, so an audit can still explain
why the system behaved as it did.

## The self-confirming-memory trap

The trap: the system writes a lesson, retrieves that lesson into the next run's context,
produces output shaped by it, then reflects on that output and writes the same lesson
again with higher confidence. Nothing external ever entered the loop, but the record now
looks well-supported. Defences: require that a confidence increase come from an episode
whose input differs from the one that produced the original record; count observations
per distinct run rather than per write; keep retrieval of memory bounded so it never
crowds out fresh material; and periodically run with memory disabled to see whether the
output actually degrades.

## Mock-generated memory must be quarantined

When the system runs against a mock or seeded model, everything it writes is a fixture,
not a finding. Mark those records with the provider that produced them and exclude them
by default from any run against a real provider, with an explicit opt-in flag for
inspecting them. This is not tidiness. A mock encodes the assumptions of whoever wrote
it; letting its output flow into memory means the system's beliefs about its own process
were authored by the test harness. The same rule applies to any record generated during
development with placeholder inputs.

## Make memory visible and reversible

Show which records were retrieved and how they influenced the decision, in the run
output and in the trace. Provide a way to list, filter and clear the store. A memory
system whose contents cannot be inspected is indistinguishable from a prompt someone
edited in secret, and when behaviour drifts the store is the first place to look.
