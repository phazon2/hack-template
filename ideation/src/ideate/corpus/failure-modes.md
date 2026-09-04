---
title: Hackathon failure modes and how to avoid them
tags: failure, risk, pitfalls, integration, scope-creep, demo-break, credentials
kind: guidance
---

# Hackathon failure modes and how to avoid them

Hackathon projects rarely fail because the idea was bad. They fail in a handful of
predictable ways that have nothing to do with the idea, and each has a cheap
prevention if you apply it early. This file lists the recurring failure modes, the
symptom that signals each, and the fix.

## Integration at the end

Symptom: three people build three parts in isolation for twenty hours, then try to
connect them in the last two. Nothing fits; the demo is a screen recording of one
part. Prevention: build a walking skeleton in hour one, deploy it, and integrate
continuously. Every piece lands into a working whole. Name an integration owner
whose job is keeping the deployed version alive.

## Scope creep after a good first hour

Symptom: the skeleton works early, confidence rises, and the team adds features
instead of hardening the demo path. At 80% of the clock the original path is broken by
a late change. Prevention: a written cut list, a feature freeze at 80% of the clock,
and a demo owner with veto over post-freeze changes. Use spare time for real data and
polish on the one path that matters.

## The blocked dependency

Symptom: the plan depends on an API key, an account approval, a paid tier, a hardware
device or a dataset that is "coming". Hours pass while someone waits. Prevention: in
the first hour, list every dependency that needs a human, hand each one to a human
immediately, and choose an alternative that needs no account as a fallback. Never let
a pending dependency block the demo path past 25% of the clock.

## Credentials on stage

Symptom: the demo requires the presenter to log in, and the login triggers two-factor,
a captcha or an expired session. Prevention: no login on the demo path. Pre-authenticate
before walking up, use a demo mode, or design the flow so the judge never sees an auth
screen. Never put personal credentials in the repo or in the demo environment.

## The live third party that dies

Symptom: the demo pulls from a public API that is rate-limited, slow or down during
judging. Prevention: cache the demo-path responses locally, keep a seeded-data
fallback behind a flag, and record the demo working an hour before judging. Say
"seeded data" honestly if that is what is on screen.

## Environment drift

Symptom: it works on one laptop and nowhere else, usually because of a local
environment variable, a locally installed tool, or a file that was never committed.
Prevention: deploy from the repo from hour one so the deployed version is the source
of truth. If it does not work on the public URL, it does not work.

## The unfinished happy path

Symptom: the team built error handling, settings, accounts and a landing page, but the
core interaction still returns a placeholder. Prevention: vertical slices. The first
thing built is the demo moment with fake data; everything else waits until that moment
lands.

## Malformed model output

Symptom: an LLM-powered feature works most of the time but returns unparseable output
on stage. Prevention: constrain output with a JSON schema where the provider supports
it, validate and retry once with the error message, fall back to a deterministic path,
and rehearse with the exact demo prompt several times so you know it is stable.

## Mock mistaken for reality

Symptom: everything passes against a mock, the team assumes the real integration works,
and the first real call on stage fails on authentication, quota or a changed response
shape. Prevention: treat mocks as scaffolding. A mock passing licenses nothing; make
one real call as early as the credential exists and keep the receipt of that call. Never
demo output that came from a mock as if it were real.

## The pitch that never shows the product

Symptom: two minutes on the problem, a slide of architecture, and thirty seconds of a
rushed demo that fails. Prevention: open with the demo moment within the first minute,
explain afterwards, rehearse three times on the clock, and cut the pitch to fit the
time limit with margin.

## The team that did not sleep

Symptom: the final pitch is delivered by someone who has been awake for thirty hours,
mumbling through a demo they can no longer operate. Prevention: schedule sleep for a
48-hour event, and for a 24-hour event make sure the presenter rests before the pitch
even if others keep polishing.

## Exotic stack chosen at the event

Symptom: someone wanted to try a new framework, language or database and the team
spends six hours on setup and unfamiliar errors. Prevention: use what the team already
knows for everything except the one component that is the point of the project. Novelty
belongs in the idea, not in the toolchain.

## Disqualification by rule

Symptom: the project uses something the brief said to avoid, or visibly reuses work
from before the event, and is quietly dropped from the shortlist. Prevention: read the
brief's must-avoid list and any sponsor rules in the first hour, and treat them as hard
constraints during ideation rather than discovering them at submission.

## Data that does not exist in the assumed shape

Symptom: the idea assumed a dataset with a field it does not have, or an API that
returns something it does not return. Prevention: before committing to an idea, make
one real request to each data source and look at the actual response. Fifteen minutes
of probing saves hours of building on a wrong assumption.

## How to use this list

At the first-hour planning meeting, walk through the list and mark which failure
modes apply to your plan. Every one that applies gets a named owner and a concrete
prevention step written next to it. Revisit at 25% and 60% of the clock. Teams that
do this rarely hit the wall; teams that skip it hit it in the same places every time.
