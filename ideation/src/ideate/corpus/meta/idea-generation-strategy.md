---
title: Choosing an idea-generation strategy per problem type
tags: meta, strategy, ideation, divergence, convergence, problem-type, planning
kind: meta
---

# Choosing an idea-generation strategy per problem type

Generating ideas is not one activity. The right first move depends on what kind of
problem the theme actually poses, and the cheapest way to waste a run is to apply the
same broad divergence to every theme. Before generating anything, classify the problem,
pick two to four techniques that fit the class, decide how many rounds you can afford,
and write down the failure modes you are watching for. That plan is the strategy, and
it should be one paragraph you could read aloud, not a checklist.

## Six problem types worth distinguishing

A **greenfield** theme is broad ("build something for cities") and the constraint is
attention, not capability. A **constrained** theme names must-use technology, a sponsor
API, or a forbidden category. An **integration** theme is about connecting systems that
already exist. A **data** theme hands you a dataset or a feed and asks what it is good
for. A **social** theme centres on coordination between people rather than computation.
An **unclear** theme is one you cannot confidently classify yet, and the honest move is
to say so and spend the first pass on framing rather than on ideas.

## What each type needs first

Greenfield needs aggressive divergence and hard diversity quotas, because the default
output is the same three ideas everyone submits. Constrained needs the constraint used
as a generator: start from the mandatory API's most unusual capability and work outward.
Integration needs a map of the seams — where two systems disagree about time, identity
or units is where the idea lives. Data needs profiling before ideation: what is actually
in the columns, what is missing, what changes over time. Social needs a named group in a
named situation and a mechanism, not a feature list.

## Divergence pays, until it does not

Divergence is worth its cost when the obvious answers are cheap to name and clearly
crowded. Generate widely, enforce quotas — at least four distinct named users and three
distinct primary data sources across a batch — and reject anything whose demo moment
cannot be written in a sentence. Divergence stops paying once new candidates are
recombinations of earlier ones rather than genuinely different bets. That is a
detectable condition: when a round produces no idea that changes the user, the data
source, or the mechanism, the round was overhead and the next one will be too.

## A stopping rule you can compute

Do not run rounds to a fixed number out of habit. Run until you have enough strong
candidates by an explicit threshold, or until a round adds no new mechanism, whichever
comes first, with a hard ceiling so the loop always terminates. A ceiling matters more
than an optimum: an unbounded refinement loop is the most common way an automated
ideation process burns budget while the score curve flattens. Two productive rounds
beat four repetitive ones, and the second round should refine the current leaders while
adding candidates from techniques not yet used.

## Framing before generating

The single highest-leverage step is the framing sentence: how should this problem be
seen? "This is a coordination problem disguised as a data problem" changes every idea
that follows. Write the framing first, commit to it, and let the techniques serve it.
If two framings are both plausible and lead somewhere different, generate a small batch
under each rather than averaging them into a vague middle. Averaged framings produce
ideas that are inoffensive and unmemorable.

## Emphasis, not exclusivity

Choosing techniques means ordering them, not banning the rest. A strategy that names
analogical transfer and assumption breaking for a greenfield theme should still let a
direct idea through if it is the best one; the emphasis changes which technique gets the
first and most slots. Hard exclusion is brittle because the classification is a guess.
Bounded emphasis — a short ordered list, a modest reweighting of the rubric, a few extra
retrieval angles — gets most of the benefit and fails softly when the guess is wrong.

## Watch-for lists beat generic warnings

A strategy should name the specific failure modes it expects for this problem, not
recite general advice. For a data theme: "every idea will be a dashboard." For a
constrained theme: "the mandatory API becomes a thin wrapper." For a social theme: "the
idea will assume everyone installs an app." Three to five such lines, fed into the
generation prompt as things to avoid, reliably shift output away from the default
attractor, because they are specific enough to be checkable against a candidate.

## Reusing what earlier runs learned

Past strategies are evidence about the process, not about the world. If runs on
constrained themes repeatedly produced thin wrappers, that is a process lesson worth
carrying forward as an emphasis change. Keep those lessons scoped: a lesson learned on
a data theme should not silently steer a social one. Scope every recorded lesson to a
problem type or mark it global deliberately, and treat a lesson observed once as weaker
than one observed repeatedly.

## Signs the strategy was wrong

The plan is wrong when the generated batch clusters on one mechanism, when the top
candidates all cite the same single source, when the emphasised techniques produce the
weakest ideas, or when the strategy's watch-for list describes nothing that actually
happened. All four are observable at the end of a run without any external verdict,
which is what makes strategy a fast feedback loop compared with waiting for a real
outcome. Record the mismatch plainly; a strategy that failed and was noticed is worth
more than one that succeeded and was not examined.
