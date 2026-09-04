---
title: Building systems that improve themselves without degenerating
tags: meta, self-improvement, reflection, actor-critic, evals, drift, metric-gaming, human-in-the-loop
kind: meta
---

# Building systems that improve themselves without degenerating

A self-improving system is a loop: act, observe, distil a change, apply the change,
act again. Every part of that loop can be built cheaply and every part can fail
silently. The difference between a system that gets better and one that merely gets
more confident is whether the observation step is grounded in something the system did
not author, and whether the change surface is bounded.

## Reflection loops

Reflection is the system reading its own execution and proposing changes. It works when
the reflection is fed structured run data — how many calls, which techniques produced
the surviving candidates, where the judges disagreed, which criterion scored lowest,
what was dropped and why — rather than being asked to introspect from memory. Compute
the facts in code, hand them to the model, and require every claim to point at one of
them. A reflection prompt that does not supply the data gets narrative instead of
analysis, and narrative is where invented detail comes from.

## Separate what changed from what happened

Keep the record of what happened (episodic) apart from the proposed change
(procedural). The value of that split shows up when a change turns out to be bad: you
can withdraw the change while keeping the observations that motivated it. Systems that
write only conclusions lose the ability to re-derive anything, and their history becomes
a list of assertions with no way to tell which were well-founded.

## Actor-critic

Split generation from judgement. The actor produces candidates; the critic scores them
against an explicit rubric and returns specific defects; the actor revises. The pattern
works because the critic's job is narrower and its output is checkable. Three rules keep
it honest: the critic must cite the criterion it is applying, the critic should not be
the same call as the actor, and revision must state what changed. Without the last rule
the actor will resubmit the original candidate with new adjectives, and the score will
rise because the language improved.

## The critic's independence is the whole point

A critic that shares the actor's context and prompt inherits the actor's blind spots.
Give the critic the rubric, the candidate, and the evidence — not the actor's reasoning.
Where the budget allows, use a panel with different framings rather than one critic
asked repeatedly, and treat their disagreement as information about the candidate rather
than as noise to be averaged away.

## Eval-driven iteration

A small fixed set of cases with expected properties of the output — not exact strings —
turns prompt and process changes from taste into measurement. Run the set after every
change, keep the cases close to the real inputs, and add a case every time a real
failure surprises you. The discipline that matters most: freeze a holdout the tuning
loop never sees. Without it, you cannot distinguish improvement from fitting the
handful of examples you happened to write down first.

## Degeneration mode: drift

Each iteration makes a small change that is locally reasonable; twenty iterations later
the system is doing something no one chose. Drift is detectable by keeping a reference
run — fixed inputs, fixed seed, stored output — and diffing against it periodically. It
is prevented by bounding the change surface: let self-improvement adjust ordering,
emphasis and a few numeric knobs within clamped ranges, and require a human edit for
anything that changes the contract.

## Degeneration mode: confirmation loops

The system generates output, evaluates its own output, records that the output was good,
retrieves that record next time, and produces the same output more confidently. The loop
is closed and self-sealing. Break it with external signal wherever one exists — a real
outcome, a human verdict, a held-out case — and where none exists, refuse to let
confidence rise. A system with no external signal can still record observations; it must
not be allowed to promote them into beliefs.

## Degeneration mode: metric gaming

Any metric the system optimises against becomes a target it can satisfy without
satisfying the intent. If the rubric rewards specificity, output grows longer and adds
detail that is specific and irrelevant. If it rewards novelty, output becomes strange.
Countermeasures: rotate or hold out part of the rubric, include a criterion that
penalises the gaming behaviour directly, score against properties an outside observer
would recognise, and periodically read raw output instead of scores. This is a general
tendency of proxy measures, not a defect of one particular rubric.

## Bound the change surface deliberately

Write down what self-improvement is allowed to touch. A defensible boundary: it may
reorder techniques, adjust criterion weights within a clamped multiplier range, add a
small number of retrieval angles, and set the planned number of rounds within the
configured ceiling. It may not rewrite prompts wholesale, add tools, change schemas, or
alter thresholds that gate safety or spend. Everything outside the boundary is a
proposal a person reviews. Clamping is not timidity; it is what makes an automated
change reversible and auditable.

## Where the human decision point belongs

Put the human at the point where a change becomes durable, not at every step. Automated
reflection and automated proposal are fine; automated promotion of a proposal into a
default that survives across runs is where review earns its cost. In practice that means
the system may write records and may apply bounded, per-run adjustments on its own, and
a person approves changes to defaults, prompts, thresholds and anything touching money,
credentials or published output. Review the reflections in batches, not one at a time.

## Measuring whether the loop helps at all

Keep the ability to turn the loop off. Run the same inputs with self-improvement
disabled and compare on the held-out cases. If the gap is not visible, the loop is
costing tokens and adding a failure mode for no return, and the honest conclusion is to
disable it and keep only the record-keeping. Whether reflection loops pay for themselves
in a given setting is genuinely contested; treat it as an empirical question for your
own workload rather than something settled by the pattern's popularity.
