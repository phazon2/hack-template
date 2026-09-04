---
title: Patterns for AI agent projects that demo well
tags: ai, agents, llm, tool-use, retrieval, rag, evals, guardrails, cost, latency, demo
kind: guidance
---

# Patterns for AI agent projects that demo well

Agent projects are the most common hackathon submission and the most likely to fail
on stage. The ones that land share a few patterns: a narrow tool-use loop, visible
reasoning, retrieval over real material, a cost and latency budget, and guardrails
that the demo actually exercises. This file covers each.

## The tool-use loop

An agent at its simplest is a loop: the model receives a task and a list of tools,
picks a tool with arguments, the code runs the tool, the result goes back to the
model, and the loop continues until the model says it is done. Keep the loop tiny for
a hackathon: three to five tools, a hard cap on iterations, and structured output
(JSON with a schema) for every tool call so parsing never fails on stage. The demo
value is in watching the loop: show each tool call and result as it happens rather than
hiding it behind a spinner.

## Tools that do something visible

The best agent demos have at least one tool whose effect is visible outside the chat:
a row appears in a spreadsheet, a map pin moves, a calendar event is created, a file
is written, a webhook fires. Judges are tired of agents that only produce text. An
agent that reads three sources, decides, and then acts on the world is a demo moment;
an agent that summarises is a feature.

## Retrieval over real material

Retrieval-augmented generation is only interesting when the material is real and
specific: the event's own rubric, a public dataset, a code repository, a set of
regulations. Build the simplest retrieval that works: split documents into chunks of a
few hundred words, index with a keyword scorer such as BM25 and, if you have time, a
vector store; fuse the two rankings; show the model the top handful of chunks with ids
and require it to cite them. Citations in the output are a demo feature: the judge
can click one and see the source. Bounding the model's references to known ids with an
enum in the schema is a cheap way to stop hallucinated citations.

## Structured output everywhere

Ask for JSON that matches a schema for every model call that feeds code. Validate it,
clamp numbers into range, truncate over-long lists, and retry once with the validation
error appended before giving up. Never parse free text with a regex on the demo path.
Where the provider supports schema-constrained output, use it; where it does not,
put the schema in the prompt and validate on the way out.

## Evals, even tiny ones

An agent that works on one example is a coin toss on stage. Write a handful of test
cases (five to ten inputs with expected properties of the output, not exact strings),
run them after every change, and use them to choose between prompts. A tiny eval
suite is also a pitch asset: "we tested against these cases and it passes all of them"
is a feasibility claim with evidence behind it. Keep the eval inputs close to the demo
inputs so the demo path is the most tested path.

## Guardrails the demo exercises

Guardrails are only convincing when the judge sees them fire. Build one: the agent
refuses an out-of-scope request, asks for confirmation before a destructive action,
flags a low-confidence answer, or declines when the retrieved material does not cover
the question. Then put that case in the demo. An agent that says "no evidence in the
sources for that" and shows what it did find is more impressive than one that answers
everything.

## Cost and latency budget

Decide the budget per demo run before building: how many model calls, how many tokens,
how many seconds. A typical hackathon demo can afford a few calls per interaction and a
few seconds of visible latency if progress is streamed. Beyond that, judges lose
attention. Techniques that fit the budget: one structured call instead of a chain of
small ones, a cheaper model for classification and routing steps, caching every
retrieval and every model response for the demo inputs, and precomputing anything
that does not depend on the live input.

## Streaming and visible progress

Stream tokens or at least stream steps. A progress line that says "searching
regulations… found 4 sections… drafting answer" keeps the judge engaged during a
ten-second call; a blank screen does not. Log every tool call to the UI. The trace is
the demo.

## Determinism where it matters

Make the demo path as repeatable as possible: fixed inputs, cached retrieval, low
variance in the prompt, and a recorded fallback. If the provider supports it, use
structured output and keep the prompt stable. Seeded fake outputs are fine for
development but must be labelled as placeholders and must never appear in the pitch as
if they were real model output.

## Real calls versus mocks

Develop against a mock model so the loop and the UI can be built without tokens, but
make one real call as soon as credentials exist and keep that response as evidence.
The mock tells you the plumbing works; only a real call tells you the model can do the
task. Never let a passing mock persuade the team that the agent is finished.

## Memory, lightly

Agents that remember past interactions demo well when the memory is visible: "last
time you asked about X, so I checked Y first." Implement it as a small store of
outcomes and lessons that gets retrieved by keyword, not as a full conversation
history. Show the retrieved memory in the UI so the judge sees why the agent chose
what it chose.

## What makes an agent demo land

A named user with a real task. A visible loop with a few tools. At least one action on
the world. Citations the judge can click. A guardrail that fires on purpose. Latency
under a few seconds with streamed progress. A recorded fallback. And honesty about
what is seeded. Agent projects that have all of these place; agent projects that are a
chat box over a prompt do not.
