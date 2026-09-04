---
title: Scoping a 24-hour or 48-hour hackathon build
tags: scoping, planning, mvp, cut-list, milestones, hour-budget, walking-skeleton
kind: guidance
---

# Scoping a 24-hour or 48-hour hackathon build

Scope is the variable most teams get wrong, and they get it wrong in the same
direction every time: too big. A team of three has perhaps forty productive
person-hours in a 24-hour event once sleep, food, setup and the pitch are removed.
Plan for that number, not for seventy-two.

## The hour budget

Split the clock into named phases and defend the boundaries. First hour: repo,
deploy, walking skeleton with fake data. By 25% of the clock: the walking skeleton
is demoable on a public URL. By 60%: the demo path works end to end with real data.
At 80%: feature freeze. Last 10%: rehearse, record the fallback, sleep if you can.
These percentages work for both 24-hour and 48-hour events; the 48-hour version
simply lets you make the demo path richer, not the feature list longer.

## Walking skeleton

A walking skeleton is the thinnest possible end-to-end version of the demo path:
input arrives, something happens, output appears, all deployed. Nothing is good yet,
but everything is connected. Building the skeleton first means integration problems
surface in hour two instead of hour twenty-two, which is the difference between a
fixable problem and a dead demo. Fake every expensive part with hard-coded data and
replace the fakes one at a time.

## Vertical slice, not horizontal layers

Do not build the database layer, then the API layer, then the UI. Build one feature
through all layers, then the next. A vertical slice that works is demoable at any
moment; three horizontal layers that are each ninety percent done are demoable never.
When someone proposes "let's get all the models right first", that is horizontal
thinking and it will cost you the demo.

## Write the cut list before you start

List the features you plan to build in the order you would cut them if time runs out,
and agree on that order before the first commit. Cutting under pressure at hour twenty
is emotional and slow; cutting from a pre-agreed list is a thirty-second decision. The
cut list also tells you what to build last, because anything near the top of the cut
list should not consume early hours. Typical first cuts: user accounts, settings pages,
a second data source, mobile layout, anything described as "nice to have".

## The MVP is defined by the demo moment

The minimum viable product at a hackathon is exactly what is needed for the demo
moment to land, plus enough surrounding UI that it does not look like a test harness.
Write the demo moment as one sentence, list what must be on screen for it, and that is
the MVP. Anything the judge will not see in the demo is not in the MVP no matter how
architecturally important it feels.

## Estimate honestly, then halve

Engineers estimate the happy path. Hackathon time is consumed by the unhappy path:
the API that needs an account, the library that will not install, the CORS error, the
model that returns malformed JSON. A useful discipline is to estimate each piece,
double it, and then check the total against forty person-hours. If the total does not
fit, cut from the list now rather than at hour twenty.

## Kill dependencies that need a human

Anything that requires a signup, a paid tier, a hardware device, a dataset download
that needs approval, or a credential the team does not already have is a human
dependency. Identify them in the first hour and hand each one to a human immediately:
the person who can create the account does it now, on their phone, while the rest of
the team builds. Never plan a demo around a dependency that is still pending at 25% of
the clock; swap to an alternative that needs no account.

## Pivot triggers

Decide in advance what would make you pivot: the core API turns out to need paid
access, the model cannot do the key task reliably, the data is not available in the
format you assumed. Write down the trigger and the alternative. A pivot at 25% of the
clock with a pre-agreed alternative is survivable; a pivot at 70% is usually fatal, so
the trigger check has to happen early and honestly.

## Integration is a job, not an afterthought

Assign one person as the integration owner from the start. Their job is to keep the
deployed walking skeleton working as pieces land, to merge often, and to be the person
who says no to a change that breaks the demo path. Teams without an integration owner
discover at hour twenty-two that three individually working parts do not fit together.

## 48-hour specifics

The extra day tempts teams into adding features. Resist. Use the second day to make
the demo path more convincing: real data instead of seeded data, a polished demo
moment, better error handling on the one path that matters, a rehearsed pitch. A
48-hour project with one excellent flow beats a 48-hour project with five adequate
ones. Also plan sleep explicitly; a team that has slept presents better than one that
has not, and presenting is half the score.

## Signs you are over-scoped

More than one data source in the MVP. A feature that needs an account not yet created.
An architecture diagram with more than four boxes. Any use of the words "platform" or
"ecosystem" in the plan. A demo that has not run end to end by 60% of the clock. Any
of these should trigger a cut-list review immediately.
