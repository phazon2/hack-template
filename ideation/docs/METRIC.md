# The winner metric, and why it is currently switched off

A self-improving loop needs a number to climb. This document records what that number would be,
what the outcome-labelled data actually supports, and the gate that keeps the number from being
used before it is real. Code: `evaluation/winner_features.py`. Command: `ideate score`.

## The design constraint that shaped everything

Two published findings bound what the metric can be:

- **LLM judges rank ideas at roughly chance** (Si et al., arXiv 2409.04109: GPT-4o 50.0,
  Claude-3.5 51.7, where random is 50.0). A near-chance judge cannot be an optimisation target at
  any price, so the metric is deterministic features — regexes and counts — not a model call.
- **Duplication, not novelty, is the bottleneck** (same paper: ~5% of seed ideas survive
  deduplication). So "maximise similarity to known winners" is self-defeating: it converges on the
  mean of past winners and erodes the distinctiveness that winning partly consists of.

The resolution: score **form**, never **subject matter**. How specifically a thing is pitched
generalises across events. What it is about does not, and copying it is the duplication failure
arriving by another route.

## What the labelled data says

One event, first gallery page: 14 winners, 10 projects listed without the label. Every feature,
measured, with Hanley-McNeil 95% intervals:

| Feature | AUC | 95% CI | Verdict |
|---|---|---|---|
| sentences | 0.743 | [0.54, 0.94] | barred — gameable |
| length | 0.707 | [0.50, 0.92] | barred — gameable |
| moment_open | 0.607 | [0.38, 0.84] | chance |
| second_person | 0.600 | [0.37, 0.83] | chance |
| abstraction | 0.589 | [0.36, 0.82] | chance |
| contrarian | 0.571 | [0.34, 0.81] | chance |
| numeric | 0.536 | [0.30, 0.77] | chance |

**Nothing substantive separates winners from non-winners at this sample size.** The only two
features that clear chance are sentence count and word count — that is, winners wrote more. That is
almost certainly not a quality signal, and it is trivially gameable: a generator told to raise it
writes padding and scores better. Both are permanently barred from the composite
(`GOODHART_PRONE`), reported so their dominance on a small sample stays visible, never used.

Two further cautions on the table above. The features were written *after reading these same
taglines*, so this is in-sample description, not prediction. And the gallery sorts winners to the
top, so the unlabelled projects beside them are whatever fell there, not a fair draw from the other
three hundred submissions.

## The base-rate error this replaced

An earlier reading of the same gallery concluded that "the winning move was restraint made legible"
— AI that stops, refuses, proves — because seven of fourteen winners pitch it. Checking the other
column: five of ten non-winners pitch it too. **50% against 50%: no discriminative power at all.**
It was the theme of the event, not the edge of the winners.

That error came from reading only the winners' column, and it is the precise failure an
optimisation loop industrialises: every frequent pattern looks causal until you count how often it
appears in the failures. `corpus/winning-submission-language.md` now carries the correction.

## The gate

`pitch_score` returns `None` — not a default, not 0.5 — unless:

1. there are at least **20 labelled examples per side** (`MIN_PER_SIDE`), and
2. the feature's whole confidence interval clears 0.5, and
3. the feature is not `GOODHART_PRONE`.

`None` stops an optimiser. A plausible-looking number steers it somewhere arbitrary with
confidence, which is strictly worse than no number.

## What opens the gate

Nothing here needs re-tuning. `ideate gallery <event-url>` appends outcome-labelled pitches to the
corpus, `ideate score` re-measures across every event present, and the gate opens on its own.

Current shortfall: **6 more winners and 10 more non-winners** — one or two more events with
announced winners. At 20 per side a genuinely 0.70 feature clears chance; at 14 vs 10 it cannot.

The practical obstacle is that Devpost events often show "judging" on the site long after winners
go out by Discord or email, so a sweep finds galleries with no labels. Events whose winners are
known from another channel can be passed by URL directly.

## Only then, the loop

With a validated metric the AIDE-style outer loop becomes safe to point at the parts of the system
that have one: dedup rate, retrieval coverage, and the pitch score itself. It stays pointed away
from the parts that do not — the idea, the demo, the design — which is where human judgement
decides and where an unvalidated proxy would do the most damage.
