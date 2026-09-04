---
title: How hackathon judges actually score
tags: judging, rubric, criteria, scoring, novelty, feasibility, impact, demoability
kind: guidance
---

# How hackathon judges actually score

Judging criteria on the event page are the official story. The unofficial story is
that judges see a project for three to five minutes, form an impression in the first
sixty seconds, and then fill in the rubric to justify that impression. Design for the
impression first and the rubric second, but make sure every rubric line has an obvious
answer in what you show.

## The four criteria almost every rubric reduces to

Most hackathon rubrics collapse into four questions, whatever their labels: novelty
(is this something I have not seen?), feasibility (did they actually build it, and
could a team this size have built it honestly in this time?), impact (who is this for
and does it matter to them?), and demoability (did the demo make the point without
explanation?). "Technical complexity" is usually a proxy for feasibility done well.
"Presentation" is usually demoability. "Creativity" and "innovation" are novelty.
Map the official labels to these four before you start scoping.

## Novelty is judged relative to the room

Novelty is not measured against the whole world; it is measured against the other
projects the judge saw that day and the ones they saw at the last few events. A
chatbot over documents is not novel because the judge has seen five of them today.
A known pattern applied to a domain the judge has never seen it applied to reads as
novel even if a startup somewhere already does it. The judge's private test is: "can I
describe the key innovation in one sentence, and is that sentence the demo?" If the
innovation requires two paragraphs of context, it scores as a known pattern.

## Feasibility is judged by what you show working, not what you claim

Judges have learned to discount claims. "We integrated with three APIs" scores nothing
unless the demo pulls live data from one of them in front of the judge. A vertical
slice that works end to end beats a broad set of half-built features every time. The
tell-tale signs of infeasible scope are: a demo that only runs on a laptop with a
particular login, features described in the future tense, and a slide that lists
architecture instead of showing behaviour. Judges also ask themselves whether the
thing needed an account, hardware or dataset the team clearly did not have; if the
answer is yes, feasibility drops regardless of how polished the slides look.

## Impact needs a named user with a named pain

"This helps people be more productive" scores one on impact. "A night-shift nurse
who has to reconcile three medication lists at handover" scores high because the
judge can picture the person and the pain. The strongest impact stories also show a
before and after inside the demo: here is the situation without the tool, here is the
same situation with it, and the difference is visible on screen. Do not ask the judge
to imagine the benefit; show it.

## Demoability is the multiplier

Demoability multiplies the other three. A novel, feasible, impactful project that
needs a slide to be understood loses to a merely good project whose demo moment
lands in ninety seconds. The demo moment is the on-screen event where the judge
understands the whole idea without narration. Design the project backwards from that
moment: what has to be on screen, what data has to be real, what interaction the
judge has to see. Everything else is optional.

## Reading a rubric with weights

When the event publishes weights (for example innovation 40, impact 30, demo 30),
treat them as instructions about where to spend hours, not just how you will be
scored. A rubric that puts forty points on innovation is telling you that a polished
clone will not place; a rubric that puts forty points on "technical achievement" is
telling you that a thin wrapper around one API will not place. When feasibility is
absent from a rubric, judges still apply it implicitly, so never scope as if it did
not exist.

## Disqualifiers judges apply silently

Some things end the conversation regardless of score: work that visibly predates the
event, violating a must-avoid rule in the brief, a demo that requires the judge to
log in to something, a project that only works with the team's personal credentials,
and a pitch that spends the whole time on the problem and never shows the product.
Judges rarely say these out loud; the project simply does not appear in the shortlist.

## Sponsor tracks and side prizes

Sponsor prizes are usually judged by the sponsor's own people against one question:
did they use our thing in a way that makes it look good? A project that uses the
sponsor API as its core, not as a bolted-on afterthought, wins those prizes with less
competition than the main track. If a sponsor track fits the idea naturally, build the
integration early enough that it is in the demo, and say the sponsor's product name in
the pitch.

## What to do with this

Before committing to an idea, write the one-sentence key innovation, the named user
and pain, the demo moment, and the honest hour estimate. If any of the four is blank,
the idea is not ready. If all four exist, the judge's impression is under your
control, and the rubric will follow.
