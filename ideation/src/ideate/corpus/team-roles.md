---
title: Team roles and splitting work in a small hackathon team
tags: team, roles, integration-owner, demo-owner, communication, workflow
kind: guidance
---

# Team roles and splitting work in a small hackathon team

A hackathon team of two to four people does not need a manager, but it does need two
named responsibilities that are almost always missing: someone who owns integration
and someone who owns the demo. Everything else can be shared. This file describes the
roles that matter, how to split the work, and how to communicate without meetings.

## Integration owner

The integration owner keeps the deployed walking skeleton alive. They set up the
repository and the git-triggered deploy in the first hour, they merge every branch as
soon as it is demoable, they are the first to know when a push breaks the public URL,
and they have the authority to revert. They also own the demo path end to end: when
someone says "my part works", the integration owner is the one who checks it works on
the deployed version, with the demo data, from a clean browser. Without this role,
integration happens at the end and fails.

## Demo owner

The demo owner is responsible for the demo moment landing on stage. From the first
hour they write the demo path as a script, choose the exact inputs, keep the seeded
data fallback working, and by the last ten percent of the clock they record the
fallback video. After the feature freeze they have veto over any change that touches
the demo path. The demo owner is usually the presenter, but not always; the key is
that one person is thinking about the pitch the whole time rather than only in the
last hour.

## Builders

Everyone, including the two owners, builds. Split by vertical slice rather than by
layer: one person takes "input arrives and is parsed", another takes "result is
displayed", rather than one taking "database" and another taking "frontend". Each
slice should be demoable on its own with fake data on either side. Hand-offs between
slices are the integration owner's problem, and they should happen every couple of
hours, not once at the end.

## The human-dependency runner

Someone with a phone and the relevant accounts handles every dependency that needs a
human: creating the deploy-provider connection, signing up for a sponsor API key,
requesting dataset access, buying credits. This is not a full-time role; it is the
person who drops what they are doing for five minutes whenever a builder says "this
needs an account". The rule is that builders never wait on a dependency; they stub it,
hand it to the runner, and keep going.

## Two-person teams

With two people, one is integration owner and builder, the other is demo owner and
builder. The scope shrinks accordingly: one data source, one flow, one screen. Two
people who have each shipped one vertical slice by 25% of the clock will beat four
people who are still arguing about architecture.

## Four-person teams

With four, the temptation is to build four things. Do not. Two people take the demo
path, one person takes the data source and integration, one person takes the pitch,
the deploy and the seeded-data fallback. The fourth person's job sounds small and it is
the one that most often decides the result.

## Communication without meetings

Use a single shared document with three sections: the demo moment (one sentence, never
changes after hour one), the cut list in priority order, and a running log of what is
deployed. Every merge adds a line to the log. Stand-ups are thirty seconds at 25%, 60%
and 80% of the clock: what is on the public URL, what is blocked, what is next on the
cut list. Anything longer than that is time not spent building.

## Decision rules

Decide before you start how ties are broken: the demo owner decides anything about
the pitch and the demo path, the integration owner decides anything about the deploy
and the merge order, and scope questions are settled by the cut list. When a proposal
would add scope, the default answer is no unless the demo moment cannot land without
it.

## Handling the person who wants to rewrite it

Someone on every team wants to switch frameworks or restructure at hour ten. The
integration owner's answer is: after the demo path works end to end on the public URL,
and only if the cut list is empty. That condition is never met, which is the point.

## Rehearsal is a team activity

The last hour belongs to the pitch. Everyone watches the rehearsal, everyone gives one
piece of feedback, the presenter and the driver run it again. The builders' last job
is to make sure the deployed version and the recorded fallback both exist and match.

## When someone burns out

Long events break people. If a team member goes quiet, hand them the smallest
self-contained task on the cut list or send them to sleep. A rested person at the
pitch is worth more than an exhausted one who pushed one more feature at 4am.
