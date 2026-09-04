---
title: Ideation techniques with prompt templates
tags: ideation, creativity, analogical, assumption-breaking, reverse, scale, combination, brainstorming
kind: guidance
---

# Ideation techniques with prompt templates

Brainstorming without structure produces the same ten ideas every team produces:
a chatbot, a dashboard, a marketplace. Structured techniques force the search away
from the obvious. Each technique below has a description, the failure it corrects,
and a prompt template you can fill in for a given theme and constraints. Run every
technique at least once and keep the ideas that surprise you.

## Analogical transfer

Take a mechanism that works well in one domain and move it into the theme's domain.
The mechanism must be specific: not "social features" but "a queue where the person
who waited longest gets first pick". Analogies work because the source domain has
already solved the hard design problems; you inherit them. The failure this corrects is
starting from a blank page. Template: "In [source domain], the problem of [specific
problem] is solved by [specific mechanism]. In [theme domain], the analogous problem
is [X], faced by [named user]. What would [mechanism] look like there, and what is the
one screen that shows it working?"

## Assumption breaking

List the assumptions every existing solution in the theme domain shares, then build
the idea that violates one of them. Assumptions are things like "the user has a
smartphone", "the data is entered by the user", "the result is shown after the
request", "there is one user per account". Breaking one usually reveals a user nobody
serves. The failure this corrects is building another clone with a different colour
scheme. Template: "Every existing tool for [theme] assumes [assumption]. Name a
user for whom that assumption is false: [named role in named situation]. Describe the
tool that works for them, what it needs instead of the assumption, and what is
visibly different in the first ten seconds of use."

## Reverse

Invert the direction of the process: instead of the user finding information, the
information finds the user; instead of detecting a problem, preventing it; instead of
the expert teaching the novice, the novice's questions training the expert's
material. Reversal often turns a passive dashboard into an active agent, which is a
much better demo. The failure this corrects is producing tools that only display
things. Template: "The standard flow in [theme] is [A does B to get C]. Reverse it:
[C arrives at A without asking] or [B is done by the system, A only approves]. Who is
the named user that benefits, and what is the on-screen moment when the reversed
flow visibly saves them effort?"

## Scale

Take the idea and push one dimension to an extreme: one user or a million, one second
or a year, one item or a whole city, free or expensive, private or fully public. At
the extreme, the design changes shape and a new idea appears. Scaling down is often
more productive than scaling up at a hackathon: "this for a single street" is
buildable in a day and demoable on a map. The failure this corrects is ideas that are
correct but featureless. Template: "Take [idea]. Make it for exactly one [unit: person,
street, classroom, shift] instead of everyone; or for one [minute, day] instead of
always. What becomes possible only at that scale, and what is the demo moment that
would be impossible at the normal scale?"

## Combination

Join two data sources, two capabilities or two user groups that are never combined,
and look for the interaction between them. Good combinations are between things that
are each ordinary and together produce a behaviour neither has: a public transit feed
plus a weather feed; a code repository plus a calendar; a museum collection plus a
map. The failure this corrects is single-source ideas that read as a wrapper around
one API. Template: "Combine [data source or capability A] with [B], both freely
accessible with no account. What question can be answered, or action taken, only
when both are present? Who asks that question ([named user]), and what is the one
screen that shows the answer appearing?"

## Direct

Sometimes the straightforward idea is right: the theme names a problem and the
obvious tool for it does not exist yet, or exists badly. Direct ideas must clear a
higher bar on the twist, because judges have seen the obvious version. Template: "The
obvious tool for [theme] is [X]. It already exists as [closest existing]. What is the
one specific thing that version gets wrong for [named user], and what is the smallest
tool that gets it right? Describe the demo moment that shows the difference."

## Constraints as a generator

Judging criteria, must-avoid lists and tech preferences are inputs, not just filters.
A rubric heavy on impact points at ideas with a named user and a before/after; a
must-avoid of "no chatbots" points at agents that act rather than converse; a
preference for a sponsor API points at ideas where that API is the core. Template:
"Given [criteria weights], [must avoid], [preferred tech], which technique above is
most likely to produce an idea that scores high on the heaviest criterion while
staying inside the constraints? Apply it."

## Running a session

Generate at least eight ideas per round using different techniques, require at least
four distinct named users and three distinct primary data sources across the batch,
and reject any idea whose demo moment cannot be written in one sentence. Then score
against the rubric, take the top three, and run a second round that refines those
three (stating exactly what changed) while adding new ones from techniques not yet
used. Two rounds is usually enough; a third rarely adds anything the first two missed.

## Validating an idea before committing

Every surviving idea should have: a named user in a named situation (not "users" or
"developers"), at least one data source with its access level stated, a demo moment of
at least a full sentence, an hour estimate within the event limit, and a named closest
existing product. Anything missing one of these is a topic, not an idea.
