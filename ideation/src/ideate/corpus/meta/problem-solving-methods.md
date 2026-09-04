---
title: Problem-solving methods and when each one applies
tags: meta, problem-solving, first-principles, inversion, constraints, analogy, decomposition, backwards
kind: meta
---

# Problem-solving methods and when each one applies

Methods are not interchangeable. Each one makes a different assumption about where the
difficulty lives — in the premises, in the direction of the search, in the constraints,
in the structure, or in the end state — and applying the wrong one produces motion
without progress. This file names six methods, the signal that each is the right one,
the mechanical steps, and the way each fails when used out of place.

## First principles

Use it when the received framing is inherited rather than examined: everyone builds X
because everyone builds X. The mechanical step is to write the problem as a list of
things that must be true, separate the physical or legal necessities from the
conventions, and rebuild only from the necessities. The output is a shorter problem.
Its failure mode is reinventing solved subproblems: decomposing to fundamentals is
expensive, and if you take it too far you will spend the budget rebuilding something
you could have imported. Go to first principles on the core claim, not on the plumbing.

## Inversion

Instead of asking how to succeed, ask what would guarantee failure, then design the
avoidance. Inversion is the right method when the success criteria are vague but the
failure modes are vivid, which is nearly always true under time pressure. The
mechanical step is to write five ways the effort dies, rank them by likelihood, and
convert the top two into design constraints. Inversion also generates ideas directly:
reverse the direction of an existing flow so information finds the user instead of the
user finding information. Its failure mode is defensiveness — a plan that only avoids
disasters and never commits to an upside.

## Constraint relaxation and constraint tightening

Every problem carries constraints, and most of them are assumed rather than given. List
them explicitly, mark each as hard (physics, rules, deadline) or soft (habit, tooling,
scope), then relax one soft constraint and see what becomes possible. Tightening works
just as well in the other direction: forcing a solution to work for exactly one person,
one street, or one minute removes generality and usually reveals a sharper mechanism.
The failure mode of relaxation is producing an idea that depends on the constraint you
relaxed still being relaxed when you build it.

## Analogy transfer

Move a specific mechanism from a domain where it is solved into the domain you are
working in. The transfer must be at the mechanism level — "a queue where the longest
waiter gets first pick", not "social features" — because the value comes from
inheriting the source domain's design decisions. The mechanical step is to name the
structural problem abstractly, find a domain that faces it constantly, and lift the
mechanism with its preconditions. The failure mode is surface analogy: matching
vocabulary rather than structure, which produces ideas that sound clever and do not work.

## Decomposition

Split the problem into parts that can be attacked independently, then define the
interfaces between them before building any part. Decomposition is right when the
problem is large but not conceptually strange. The discipline is that the interfaces are
written first and are the deliverable; a decomposition whose parts are agreed but whose
seams are not is how integration failures are manufactured. The failure mode is
decomposing along the wrong axis — by technology instead of by user-visible outcome —
so that no single part is demonstrable on its own.

## Working backwards from the end state

Write the final artefact first: the demo script, the screenshot, the sentence a judge
repeats to another judge, the API response the caller receives. Then ask what must exist
for that artefact to be real, and build only that. This method is the strongest one
under a deadline because it makes the cut list obvious: anything not on the path to the
written end state is optional by construction. Its failure mode is optimising for a
scripted moment while the underlying capability is hollow, which is why the written end
state should include one unscripted case.

## Choosing between methods

Match the method to where the difficulty is. Premises are suspect: first principles.
Success is vague, failure is vivid: inversion. The space feels boxed in: constraint
relaxation. The space feels blank: analogy transfer. The problem is large and familiar:
decomposition. The deadline is the binding constraint: work backwards. When two methods
both apply, run the cheaper one first and use its output as the input to the second.
Running all six on every problem is a way of avoiding the choice.

## Combining methods without mush

Methods compose in sequence, not in parallel. Work backwards to fix the end state, then
decompose the path to it, then invert each part to find what would break it. Each step
takes a concrete artefact from the previous one. What does not work is blending: an
output that is partly a first-principles rebuild and partly an analogy tends to inherit
the weaknesses of both, because the assumptions behind them were never reconciled.

## Knowing when the method is not the problem

Sometimes the method is fine and the input is thin: no real user, no accessible data,
no way to observe whether the thing worked. No amount of methodological technique fixes
missing ground truth. The correct move is to say the input is insufficient and name what
would make it sufficient — a named user in a named situation, one data source with its
access level stated, and one observable outcome — rather than to run another round of
generation and mistake volume for progress.
