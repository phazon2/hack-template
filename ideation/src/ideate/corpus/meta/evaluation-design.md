---
title: Designing evaluation with model judges you can trust
tags: meta, evaluation, llm-judge, rubric, bias, calibration, panel, disagreement
kind: meta
---

# Designing evaluation with model judges you can trust

A model judge is a measuring instrument, and like any instrument it has systematic
errors. The useful question is not "is the judge right" but "which known biases apply
here, which have I controlled, and what does the residual disagreement tell me". Design
the rubric, the presentation and the aggregation with the biases in mind, and the judge
becomes a usable signal; ignore them and you get a confident number with no content.

## Write the rubric before you see any output

A rubric written after reading candidates encodes the candidates. Fix the criteria,
their weights and their scale before generation, and define each criterion by what
would make it score low as well as high. Four to six criteria is a good range: fewer and
the score is a vibe, more and the judge stops distinguishing them. Publish the rubric to
the generator too — hiding it does not produce an honest test, it produces a mismatch
between what was asked for and what is measured.

## Anchor the scale or it will compress

Model judges cluster scores in a narrow band near the top of whatever scale you give
them. Counter it by anchoring: describe concretely what a low, middle and high score
look like for each criterion, and require the judge to name the specific evidence for
its number. Anchoring turns a scale from an opinion into a classification. Without it,
a five-point scale effectively becomes a two-point one, and ranking becomes noise.

## Position bias

Judges are sensitive to the order in which candidates are presented, especially in
pairwise comparison. Control it by randomising order with a recorded seed, or better,
by evaluating both orders and keeping only the comparisons that agree. When the two
orders disagree, that pair is genuinely close and should be recorded as a tie rather
than resolved by whichever order you happened to run.

## Verbosity and style bias

Longer, more fluent, more confidently structured answers tend to score higher than their
content warrants. Counter it by scoring criteria that reward specific checkable content
— a named user, a stated data source and access level, a demo moment in one sentence —
rather than overall impression, and by capping the length the judge sees so a long
candidate cannot win on volume. Be explicit in the prompt that length is not a merit.

## Self-preference

A model tends to favour text produced by itself or by a model with similar style. Where
budget allows, use a different model for judging than for generation. Where it does not,
reduce the coupling: strip generator-specific formatting before judging, do not show the
generator's reasoning, and prefer criteria that check for the presence of facts over
criteria that ask whether the writing is good. Self-preference is a real and repeatedly
observed effect; the size of it varies by model and task, so treat it as a hazard to
control rather than a constant to correct for.

## Pointwise, pairwise, or both

Pointwise scoring gives you an absolute number that is comparable across runs but is
poorly calibrated. Pairwise comparison is more reliable about ordering but costs
quadratically and gives no absolute level. A practical combination is pointwise scoring
for the whole batch to get a shortlist, then pairwise comparison within the shortlist to
settle the order of the top few. Do not average a pointwise score with a pairwise win
rate; they measure different things.

## Panels and how to aggregate

A panel of judges with different framings — a pragmatist, a domain expert, a sceptic —
gives more than one judge run three times, because the variation is structural rather
than sampling noise. Aggregate with the median rather than the mean so a single extreme
score cannot carry a candidate, and keep every individual score rather than only the
aggregate. Panels cost linearly in judges, so use a small panel on the shortlist rather
than a large one on everything.

## Disagreement is signal, not noise

Record the spread of scores per candidate and treat it as a first-class output. High
agreement on a high score is a strong candidate. High agreement on a low score is a
clear reject. Wide disagreement usually means the candidate is unusual, the rubric is
ambiguous on this case, or the evidence is thin — all three are worth a human look, and
all three are erased by reporting only the mean. Surfacing the most-disagreed candidate
is often more useful than surfacing the winner.

## Determinism and reproducibility

An evaluation you cannot repeat is not a measurement. Fix the prompt, fix the candidate
order or record the seed that shuffled it, request structured output, and sort ties by a
stable key so equal scores do not reorder between runs. Store the judge's raw output
alongside the aggregate so a surprising ranking can be inspected instead of re-run. The
same discipline that makes a demo repeatable makes an evaluation credible.

## Validate the judge against something outside itself

Before trusting a judge, check it against a small set of cases where you already know
the answer: two candidates you are confident are ordered, one deliberately broken
candidate, one that satisfies the letter of the rubric while missing its intent. If the
judge cannot order those, tune the rubric before tuning anything else. Agreement with
human judgement on a handful of cases is weak evidence, but it is external evidence,
which is more than a self-consistent score provides.

## What a judge cannot tell you

A model judge cannot tell you whether something will work when built, whether a user
wants it, or whether it is genuinely novel in the world. It evaluates the description
in front of it. Keep that boundary explicit in how scores are reported, and reserve the
words that imply external validation for signals that actually came from outside the
system — a real outcome, a real user, a working deployment.
