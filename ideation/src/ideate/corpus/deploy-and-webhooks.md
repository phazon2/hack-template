---
title: Git-triggered deploy, public URLs and webhooks in the first hour
tags: deploy, webhook, public-url, git, mock, evidence, integration, first-hour
kind: guidance
---

# Git-triggered deploy, public URLs and webhooks in the first hour

A public URL in the first hour is the single highest-leverage thing a hackathon team
can do. It proves the project is real, it lets every judge try it on their phone, it is
the webhook receiver for any inbound integration, and it turns "works on my laptop"
into "works". Getting it requires no special network access from the machine you are
coding on.

## Git-triggered deploy needs no local egress

The chain is: push to the repository, the hosting provider watches the repository,
the provider builds on its own infrastructure, the build gets a public URL. Nothing
in that chain depends on the coding environment being able to reach the deploy
target directly. A sandboxed cloud container, a locked-down laptop, a corporate
network that blocks outbound traffic: none of them matter, because the only thing the
coding environment has to do is push git commits. If git push works, a public URL is
possible. Never conclude a public URL is impossible because the local environment
cannot reach the provider.

## The first-hour sequence

Create the repository. Push a hello-world that serves one page. Connect the repository
to a git-triggered hosting provider (a human does this once; it takes minutes). Push
again and confirm the public URL renders the page. Only then start building. Teams that
defer deployment to "when there is something worth showing" discover at 80% of the
clock that the build fails on the provider, an environment variable is missing, or the
framework needs a config file. Deploying in hour one means every later push is
incremental and every integration problem shows up while it is still small.

## The public URL is the webhook receiver

Any integration that calls you back (a payment event, a chat message, a repository
push, a sensor upload, an inbound email) needs a URL it can reach. The deployed app is
that URL. Add a route that accepts a POST, logs the body, and returns 200; point the
external service at it; confirm one real event arrives. That confirmation is the
walking skeleton for every webhook-driven idea, and it can exist by the end of the
first hour. Tunnels from a laptop are a fallback, not the plan: they die when the
laptop sleeps, and they are useless during the pitch if the presenter's machine is on
stage.

## Verify the receiver with a real event

Send the external service a real trigger and watch the log on the deployed app. Do not
consider the webhook working because a local curl to localhost succeeded, and do not
consider it working because a unit test posted a hand-written payload. The payload the
real service sends differs from the one in the docs more often than you would expect,
and the signature-verification step fails on real requests in ways it never fails on
fake ones.

## Mocks are scaffolding, never evidence

A mock exists so that work can continue before the real thing is available. It encodes
your assumptions about the API: the shape of the response, the status codes, the
timing. When the mock passes, the only thing you have learned is that your code agrees
with your own assumptions. It has told you nothing about whether the real service
agrees. A mock passing does not license a real call, does not prove the integration
works, and must never be the source of a screenshot, a receipt, a demo result or a
"we integrated with X" claim in the pitch.

## The mock's only job

The mock's job is to make the day you get real access as short as possible: change the
base URL, run the probe, look at the real response. That means the mock should sit
behind the same interface as the real client, be switchable by configuration rather
than code changes, and be obviously labelled everywhere its output appears. Output
produced under a mock should carry a visible placeholder marker so nobody in the team,
and no judge, mistakes it for real data.

## One real call early beats a hundred mock passes

As soon as a credential or endpoint exists, make one real call, capture the exact
response, and keep it as the receipt that the integration is real. Compare it to what
the mock assumed and fix the mock. Then build against that real shape. Teams that do
this find the surprising differences at hour three; teams that do not find them on
stage.

## Credentials and accounts

The deploy provider connection, the API key for a sponsor service, the account for a
data source: each of these is a human dependency. The tool or agent doing the building
should never handle a personal credential, never drive a signup or two-factor flow, and
never store a key in the repository. The right move is to stop, name exactly what is
needed, and hand it to the team member who can do it on their phone in five minutes.
Classify each blocker honestly: config-fixable (a setting or variable the team can
change), do-it-myself (a human must log in or sign up), or genuinely human-only (a
judgement or approval nobody can automate). Collapsing all three into "blocked" hides
the fact that most of them take minutes to clear.

## Environment variables on the provider

Anything the app needs at runtime that is secret or environment-specific goes into the
provider's environment settings, not into the repository. Set them in the first hour
alongside the initial deploy so a later push does not fail for want of a variable. Keep
a non-secret sample env file in the repo listing the variable names with placeholder
values so the next person knows what to set.

## What a judge sees

A public URL on a slide or QR code, a demo that runs on the deployed version, a webhook
that visibly fires during the demo when something happens in an external service:
these are proof of feasibility that no amount of architecture slides can match. They
are also cheap, provided they were set up in hour one rather than hour twenty.
