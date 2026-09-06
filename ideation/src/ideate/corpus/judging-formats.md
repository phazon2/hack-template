---
title: How the judging format changes what wins
tags: judging, gavel, pairwise, rubric, demo-video, submission, strategy
kind: guidance
---

# How the judging format changes what wins

Most advice about winning hackathons assumes a panel scoring you against a written rubric. A
large share of events do not work that way, and the difference changes what you should build,
how you should demo, and where the last two hours of the event should go. Find out which format
you are in before you plan the demo. Ask an organiser; they will tell you.

## Two formats, two different games

**Panel with a rubric.** Judges hold a scoring sheet with named criteria and weights, score each
project against it, and totals decide. Here the rubric is the spec: every criterion you ignore is
points left on the table, and a stated weighting tells you exactly where to spend effort. This is
the format `judging-criteria.md` describes.

**Pairwise comparison.** Judges see your project head to head against one they have already seen
and vote which impressed them more. Projects gain or lose a rating like a chess Elo, and stronger
projects attract more judges. Gavel is the common implementation of this and is used at large
university hackathons. Sophia Sharif, who set up the judging system for LA Hacks, describes it
this way in *How to win a hackathon* (youtube.com/watch?v=DizrlqWIEWs).

## Why pairwise changes your strategy

Under a rubric you are trying to satisfy criteria. Under pairwise you are trying to be more
impressive than whatever the judge saw immediately before you — often with no rubric in front of
them at all. Sharif reports the impression usually reduces to three things: technical complexity,
impact on the world, and how complete the project feels. These are absorbed as impressions from
the demo, not scored line by line.

The practical consequence is that relative impressiveness beats completeness against a checklist.
A project that does one thing that visibly could not have been easy will beat a project that
covers more ground but reads as ordinary. It also means variance matters: a memorable project
that some judges love can climb higher than one everyone rates as fine.

## The judge sees only the demo

This is the single most load-bearing fact in either format, and it is stronger than most teams
believe. The judge has not read your repository. They do not know what you built in the last
twenty-four hours, what you had to throw away, or how hard the integration was. Their entire
impression comes from a two-to-five minute window. Anything you want them to know has to be
inside that window or it does not exist.

That cuts both ways. Work that is invisible in the demo earns nothing, however hard it was. And
work that merely *looks* hard earns full credit: judges generally cannot tell which parts you
wrote and which came from a library. Sharif's advice follows directly — push as much logic as you
can into libraries so you can build more of the demo in the time you have.

## Visuals carry the impression of technical depth

Maps, hardware, live video, rendered geometry and visible maths all communicate complexity
without a word of explanation, and they land in the first seconds while the judge is forming
their comparison. A project whose interface is a text box has to argue for its depth; a project
showing points resolving on a map has already made the argument. Choose ideas that have something
worth looking at, and get that thing on screen early.

## The demo video is not a fallback

Most advice treats a recorded video as insurance for when the live demo breaks. It is that, but
it is also frequently the primary artifact. Sharif, describing picking winners at LA Hacks, says
she had roughly thirty minutes to an hour to review all the top submissions, and that the demo
video is the only way to get a holistic view of a project in that time — most people will not
even read the written description.

So the trade in the final two to three hours is not "polish the video or ship one more feature".
It is "make the artifact the decision will actually be made from, or add a feature nobody may
ever see". Start the video. This is the most commonly reversed priority at the end of a
hackathon, and reversing it correctly is close to free.

## Submit before the deadline, in whatever state you are in

Teams lose by submitting at 12:05 for a noon deadline, or by not submitting at all, while trying
to finish one more thing. The EasyA organisers make this point bluntly in *How to win a hackathon*
(youtube.com/watch?v=MPfOhJs-EKc): late submissions make judging genuinely difficult to
administer, and the five minutes almost never changes the outcome on merit. Treat the deadline as
a hard stop that arrives fifteen minutes early, and submit whatever you have then. You can keep
working and resubmit if the platform allows it.

## Sponsor prizes are a different game again

General prizes are decided on the demo alone, by judges you meet once. Sponsor prizes are decided
by people you can talk to across the whole event. That makes engagement a real strategy for
sponsor tracks: use the technology visibly, ask their engineers questions, and make sure they
know who you are and that you are building on their platform seriously. Everything in this
document still applies to sponsor prizes; there is simply more surface to work with.

## What to do with this

Ask which format the event uses. If it is pairwise, optimise for a single striking impression and
put something visual on screen in the first ten seconds. If it is a rubric, get the rubric and
treat it as the specification. In both cases, assume the judge sees nothing but the demo, and
protect the time to make the demo video.
