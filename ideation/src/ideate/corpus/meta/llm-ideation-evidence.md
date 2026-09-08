---
title: What the research says about LLM idea generation, and what it breaks in this system
tags: ideation, novelty, diversity, duplication, llm-judge, evaluation, evidence, meta
kind: meta
---

# What the research says about LLM idea generation, and what it breaks in this system

Six studies of LLM ideation, read together, contradict two assumptions this system was built on.
They are recorded here because both assumptions are load-bearing, and because the corrections
point at cheaper changes than the ones that were planned.

Sources: Si, Yang & Hashimoto, *Can LLMs Generate Novel Research Ideas?* (arXiv 2409.04109);
Meincke, Mollick & Terwiesch, *Prompting Diverse Ideas* (arXiv 2402.01727); Hu et al., *Nova*
(arXiv 2410.14255); Girotra, Meincke, Terwiesch & Ulrich, *Ideas Are Dimes a Dozen* (Wharton);
Gu et al., *LLMs Can Realize Combinatorial Creativity* (arXiv 2412.14141); Gu & Krenn,
*Interesting Scientific Idea Generation using Knowledge Graphs* (arXiv 2405.17044).

## Novelty was not the deficit

Si et al. ran the first properly controlled head-to-head: 100+ NLP researchers wrote ideas and
blind-reviewed both human and LLM ideas. **LLM ideas were judged more novel than expert human
ideas (p < 0.05)**, and slightly weaker on feasibility. Girotra et al. found the same shape in a
product-innovation setting: GPT-4 ideas scored higher on purchase intent than elite MBA students',
with most of the best ideas in the pooled sample coming from the model.

So a system that reaches for "our ideas are not novel enough, ground them in papers to fix it" is
solving a problem the evidence does not show. Both studies point the other way: raw per-idea
novelty is a relative strength, and feasibility is the softer edge.

## Duplication is the deficit

The same paper locates the real bottleneck. Generating more ideas does not produce more distinct
ideas — Si et al. report that after deduplicating seed ideas at 0.8 cosine similarity on sentence
embeddings, **roughly 5% survived as non-duplicates**, and that scaling inference-time generation
"simply leads to repeating duplicate ideas".

Meincke et al. measure the same failure from the other side: pools of GPT-4 ideas are **less
diverse than pools produced by groups of humans**, across 35 prompting strategies. Diversity is
improvable by prompting — chain-of-thought scored highest of everything they tried and came close
to human group dispersion — but it is not there by default.

This matches what a repeat hackathon entrant notices first: the ideas keep arriving in the same
shape, event after event. That is not a novelty failure. It is a coverage failure, and it is
invisible from inside a single run because each individual idea looks fine.

## LLM judges rank ideas at roughly chance

Si et al. benchmarked LLM evaluators against human review scores on their own idea set, scoring
each evaluator's accuracy at separating top-ranked from bottom-ranked ideas (50.0 is chance):

| Evaluator | Accuracy |
|---|---|
| Random | 50.0 |
| Human reviewers, ICLR'24 | 71.9 |
| Human reviewers, NeurIPS'21 | 66.0 |
| Claude-3.5 pairwise | 53.3 |
| Claude-3.5 direct | 51.7 |
| GPT-4o direct | 50.0 |
| GPT-4o pairwise | 45.0 |
| "AI Scientist" reviewer | 43.3 |

Every LLM evaluator lands near chance; two fall below it. The authors' conclusion is blunt: LLMs
cannot yet evaluate ideas reliably, despite LLM-as-judge being the standard move in prior work.

This is the finding that costs the most here, because a judge panel is exactly what this system
uses to pick the idea it recommends. Adding personas to that panel adds cost and consensus
without adding accuracy — several near-chance judges agreeing is not evidence.

One qualification worth keeping: their pairwise ranker did reach non-trivial accuracy on *papers*
when calibrated against 1200 real ICLR submissions with known review scores. Pairwise plus a real
calibration signal is not the same thing as direct scoring against a rubric, and it is the only
LLM evaluation shape in these papers that demonstrably beat chance.

## What actually raised diversity

Three interventions have evidence behind them, all cheap:

**Planned iterative retrieval.** Nova retrieves external knowledge in rounds, deliberately
widening and deepening across iterations rather than fetching once. It reports **3.4× more unique
novel ideas** than the same system without it, and 2.5× more top-rated ideas than the prior state
of the art. Retrieval helps — but as a diversity mechanism, not a novelty patch, and iteratively
rather than in one shot.

**Chain-of-thought prompting.** The highest-diversity strategy of the 35 Meincke et al. tested,
and the one producing the most unique ideas.

**Few-shot with highly rated examples.** Girotra et al. found that showing the model examples of
ideas that scored well further improved its output. Real winner text is the natural source.

## What this changes here

- Deduplication is the highest-value control in the pipeline, and a token-overlap filter tuned to
  drop the occasional near-twin is far too weak against a generator that mostly repeats itself.
  The published threshold is 0.8 cosine on sentence embeddings, and even that leaves ~5%.
- More ideas per round buys duplicates. Prefer more diverse retrieval per idea over a bigger batch.
- A judge panel should be treated as a weak filter for obvious failures, not as the mechanism that
  picks the winner. Where ranking matters, pairwise against known-good references beats direct
  rubric scoring, and neither should be trusted as though it were a human reviewer.
- Winner taglines from real galleries are the few-shot examples the evidence supports using.
