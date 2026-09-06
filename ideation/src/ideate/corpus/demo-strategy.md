---
title: Demo strategy for hackathons
tags: demo, pitch, judging, demo-moment, fallback, rehearsal
kind: guidance
---

# Demo strategy for hackathons

The demo is the product at a hackathon. Nobody installs your code; the judges see a
few minutes on a screen and decide. Everything about scoping, team split and the last
hours of the clock should be derived from the demo you intend to show.

## Design the demo moment first

The demo moment is the single on-screen event at roughly the ninety-second mark where
the judge gets it without narration. It is a thing happening, not a thing being
described: a live map lighting up as data arrives, a document turning into a filled
form, an agent visibly correcting itself. Write the demo moment as one sentence before
writing any code, and reject ideas whose demo moment you cannot phrase. If the moment
needs a slide to be understood, the idea needs to change, not the slide.

## Work backwards from the moment

Once the demo moment exists, list exactly what must be true on screen for it to land:
which data is real, which interaction the judge sees, which output must be visibly
correct. That list is the MVP scope. Everything not on that list is a cut candidate.
Teams that scope forwards from features end up with a broad set of half-working parts
and no moment; teams that scope backwards from the moment ship something small that
lands.

## The demo path is the only path that matters

Choose one path through the product and make it bulletproof: one input, one flow, one
output. Test that exact path, with the exact data, on the exact machine and browser
that will be on stage. Never demo a path you did not rehearse, never accept input from
the audience on stage, and never type a URL live when a bookmark will do. If the
product has a search box, decide the exact query in advance and use the same one every
time.

## Real data over fake data, but fake data over no demo

Judges notice live data and reward it: a real weather feed, a real repository, a real
public dataset. But a demo that depends on a flaky third party can die on stage. The
rule is: stub the demo path end to end with fake data in the first hour so there is
always something to show, then replace the fake data with real data one source at a
time as they prove reliable. Keep the fake path available behind a flag as a fallback.
Never present a fake-data demo as if it were live; say "this is seeded data" if it is.

## Record the demo video, and start it earlier than feels comfortable

By the last ten percent of the clock, record a screen capture of the demo path working
end to end. Networks fail, projectors fail, laptops sleep. A recording turns a
catastrophe into a minor stumble: "the wifi dropped, here is the same flow recorded
an hour ago". Judges do not penalise a fallback that was clearly recorded during the
event; they penalise a blank screen. Keep the recording on the presenting laptop, not
in the cloud.

Treating that recording as only a fallback undersells it badly. At many events the demo
video is the artifact the decision is actually made from: organisers reviewing a pile of
top submissions have well under an hour for all of them, they rely on the video for a
holistic view, and most will not read the written description at all. So when the last
two or three hours present the usual trade — one more feature, or the video — the video
almost always wins, because a feature nobody watches scores nothing. See
`judging-formats.md` for who is watching and when.

## No login on stage

A demo should require no login, no signup, no two-factor prompt and no personal
credentials. If the product needs an account for a real user, pre-authenticate before
walking up or use a demo mode. A public URL that anyone in the room can open on their
phone is worth more than a local app, because the judge can try it while you talk and
because it proves the thing is actually deployed.

## Show, then explain

Open with the moment, not the problem. Thirty seconds of setup at most: who the user
is and what hurts. Then the demo moment. Then, and only then, the explanation of how it
works and what makes it novel. Pitches that spend two minutes on the problem and leave
thirty seconds for a rushed demo lose to pitches that show the product in the first
minute and use the remaining time to answer the questions the demo raised.

## Rehearse on the clock

Rehearse the full pitch and demo at least three times, timed, with the team member who
will actually present. The first rehearsal reveals what is broken; the second reveals
what is slow; the third makes it smooth. Cut anything that pushes the pitch over the
allotted time; judges stop listening when the timer goes off. The person driving the
demo should not be the person talking unless you have rehearsed that combination.

## Latency is part of the demo

An LLM call that takes twenty seconds is twenty seconds of the judge staring at a
spinner. Pre-warm caches, precompute expensive steps for the demo path, stream partial
output where possible, and put a visible progress indicator on anything longer than
two seconds. If a step is unavoidably slow, narrate what is happening during it rather
than standing in silence.

## Feature freeze protects the demo

Set a feature freeze at roughly eighty percent of the clock. After the freeze, no new
capabilities, only fixes to the demo path and the pitch. The last-hour feature that
"just needs a small change" is the most common way a working demo becomes a broken
one. The demo owner has veto over any change after the freeze.

## A checklist for the last hour

Demo path tested on the presenting machine. Bookmarks open. Fake-data fallback flag
known. Recording saved locally. Laptop charged and sleep disabled. Public URL on a
slide or QR code. Pitch timed under the limit. Presenter and driver agreed. Nothing
else matters in the last hour.
