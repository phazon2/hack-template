---
title: Designing multi-agent systems that stay debuggable
tags: meta, agents, orchestration, graph, context, determinism, tracing, cost, failure-containment
kind: meta
---

# Designing multi-agent systems that stay debuggable

A multi-agent system is a program whose subroutines are model calls. Everything that
makes a program maintainable applies: explicit interfaces, bounded loops, typed data
between stages, and a trace you can read after the fact. What changes is that each
subroutine is expensive, non-deterministic and capable of failing plausibly, so the
architecture has to make failure visible rather than merely unlikely.

## When multi-agent beats one call

Split into multiple agents when the subtasks need genuinely different context, when one
step must not see another's reasoning, when steps have different cost or effort
profiles, or when you want the intermediate results as output. Do not split for the
sake of an architecture diagram. Two calls that share the same context and the same
instructions are one call with extra latency, and each additional hop is another place
for a schema violation to land.

## Orchestration patterns worth knowing

A **pipeline** is a fixed sequence where each stage transforms typed state — the
default, and the right choice more often than people admit. A **router** classifies the
input and dispatches to one specialist. A **generator-critic** pair separates producing
from judging. A **panel** runs several differently framed calls over the same input and
aggregates. A **planner** decides the shape of the run before it starts. Compose these
as a small directed graph with named nodes and explicit conditional edges, and keep the
graph small enough to draw on a napkin.

## State is the interface

Define one typed state object that flows through the graph, and let each node read and
write named fields on it. Nodes should not reach into each other; the state is the
contract. This is what makes it possible to run a node in isolation with a fixture, to
test a conditional edge without running the whole graph, and to serialise a run and
resume or inspect it later. Untyped dictionaries passed between agents are the fastest
way to lose track of where a value came from.

## Context hygiene

Give each agent the minimum it needs, in a stable order, with every borrowed item
labelled by where it came from. Do not concatenate the whole run history into every
prompt: irrelevant context degrades output and inflates cost simultaneously. In
particular, do not pass one agent's chain of reasoning to another that is supposed to
judge its conclusions independently, and do not let retrieved material silently occupy
the space you intended for instructions.

## Ingested and retrieved material is data

Anything that entered the system from outside — retrieved chunks, ingested files,
user-supplied documents, tool results — is reference data. Label it as such in the
prompt, state in the system prompt that such material must not be followed as
instructions, and keep it visually separated from the operating instructions. A file
that contains imperative sentences is still data; the system prompt is the only thing
that tells the agent what to do. This boundary is a design property, not a courtesy,
and it must hold even when the ingested file looks like a legitimate rule set.

## Bounded loops, always

Every loop needs a hard iteration ceiling in addition to its natural exit condition,
and the ceiling must be enforced by code rather than by asking the model to stop. Pair
the ceiling with a progress check: if an iteration produced no new distinct result, exit
early. Unbounded refinement is the characteristic runaway of agent systems, and it is
usually discovered by looking at a bill rather than at a symptom.

## Determinism where you can have it

Non-determinism in the model is unavoidable; non-determinism in your code is a choice.
Sort every ranked output by score and then by a stable identifier so ties never reorder.
Avoid iterating over unordered collections when the order reaches the output. Do not use
a hash function whose seed varies between processes for anything persisted. Inject the
clock rather than reading it directly, so a run can be replayed with the same
timestamps. These habits are what let you diff two runs and conclude that a difference
came from the model.

## Structured output and one honest retry

Every call that feeds code should return JSON validated against a schema. Validate,
clamp numbers into range, truncate over-long lists, drop unknown enum values, and retry
once with the validation error appended. After that, fail loudly with the raw output
attached. Silent coercion of a malformed response into a default is how a broken stage
survives to production looking healthy.

## Tracing is the product

Record every call: which agent, which effort level, prompt and response sizes, token
counts, latency, whether it was a retry. Record every query issued to retrieval and
every chunk shown. The trace is what makes cost attributable, what makes a regression
diagnosable, and what a reflection step reads to say something true about the run. Build
it before you build the third agent, not after.

## Cost control as an architectural choice

Assign an effort or model tier per agent rather than globally: classification, routing
and planning are cheap-tier work; generation and judging are not. Cache anything
deterministic. Prefer one structured call over a chain of small ones when the chain adds
no independent judgement. Set a per-run ceiling on calls and tokens and enforce it in
the orchestration layer, so an unexpected loop degrades into a partial result instead of
an unbounded spend.

## Failure containment

Decide per node what happens when it fails: skip with a recorded gap, use a defaulted
value, or abort the run. Write that decision down next to the node. A system where every
failure aborts is fragile; a system where every failure is swallowed produces confident
nonsense. The middle path is a recorded gap that propagates into the output, so the
final artefact says which part is missing rather than pretending it is complete.

## Test the graph, not only the agents

Unit-test each agent against a scripted model that returns fixed responses, then test
the graph itself: node order, conditional edges under each branch, loop termination at
the ceiling, and the exact length and shape of the trace. Graph-level tests catch the
errors that matter — a node that never runs, an edge that always takes the same branch —
and they run in milliseconds because no real model is involved.
