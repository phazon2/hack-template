---
title: Retrieval strategy — lexical, dense, hybrid, and when retrieval hurts
tags: meta, retrieval, rag, bm25, embeddings, hybrid, rerank, query-expansion, coverage
kind: meta
---

# Retrieval strategy — lexical, dense, hybrid, and when retrieval hurts

Retrieval is a ranking problem wearing a search interface. Most of the quality comes
from four decisions: how documents are cut into chunks, which scorers vote, how their
rankings are combined, and what the model is allowed to do with what comes back. Model
choice matters far less than people expect; chunking and fusion matter far more.

## Lexical retrieval is the strong baseline

A keyword scorer such as BM25 rewards rare terms, penalises long documents, and is
exactly right when the query and the corpus share vocabulary — names, identifiers, API
terms, rubric wording, error strings. It is inspectable: you can point at the term that
caused a hit. Its weakness is vocabulary mismatch: a query about "picking a project"
will not match a chunk that says "scoping" if the words never co-occur. Do not skip
lexical retrieval because it is old; skipping it is how systems lose exact-match recall.

## Dense retrieval covers the paraphrase gap

Embedding-based retrieval maps text into a vector space where paraphrases land near each
other, so it finds the chunk that answers the question in different words. Its
weaknesses are the mirror image of lexical: it is weak on rare literal tokens, it
degrades on out-of-domain vocabulary, and it is hard to explain a hit. A hashed or
otherwise cheap embedder is a real option when a learned model is unavailable; it
recovers some of the topical smoothing without a dependency, and it should be
described honestly as an approximation rather than as semantic search.

## Hybrid, fused by rank not by score

Run both and combine. Combine on ranks, not on raw scores: BM25 scores and cosine
similarities are on incomparable scales, and normalising them introduces a tuning knob
that will silently rot. Reciprocal rank fusion — summing a decreasing function of each
retriever's rank for each document — is simple, has one parameter, and is robust to one
retriever being badly calibrated. A document that both retrievers place near the top
rises; a document only one likes still surfaces.

## Query expansion, kept honest

One query rarely covers a topic. Expand into a handful of angles — a restatement, a
mechanism-level phrasing, a user-and-situation phrasing, a constraint phrasing — and
retrieve for each, then fuse. Expansion helps most when the original query is short and
abstract. It hurts when the expansions drift off-topic and pull in confident, irrelevant
material; bound the number of expansions, keep the original query's results in the pool,
and log every query actually issued so a bad expansion is visible afterwards.

## Reranking is where precision is bought

First-stage retrieval optimises recall over a large pool; reranking picks the few
things the model will actually read. A cheap lexical-overlap reranker over the top
candidates already removes obvious drift. A model-based reranker is better and costs a
call, so reserve it for the final short list. The rule that matters: retrieve wide,
rerank hard, show few. Handing a model twenty mediocre chunks is worse than handing it
four good ones, because the mediocre ones compete for attention and invite the model to
cite something merely present.

## Chunking decides your ceiling

No ranking method recovers from bad chunks. Split on natural boundaries — blank lines,
headings — and pack into chunks of a few hundred words so each one is self-contained.
The failure to watch for is orphaned context: a heading in one chunk and its explanation
in the next, so the explanatory chunk never mentions the term it explains. Write source
material with the key term inside the paragraph that explains it, and the retriever's
job becomes much easier.

## Pinning beats hoping for some material

Some material must be in context regardless of score: the event rubric, the operating
constraints, the schema the output must satisfy. Pin those chunks explicitly instead of
relying on retrieval to surface them, and reserve the remaining budget for ranked
results. Pinning is also how you guarantee a category is represented at all — for
example, at least a few chunks of a particular kind — which is a coverage guarantee
ranking alone cannot give you.

## Coverage gaps are a first-class output

Report what the retriever could not find. If a query returns nothing above a score
floor, that is a fact worth surfacing: the knowledge base does not cover this, so
downstream claims about it are unsupported. Systems that silently return their best
five chunks no matter how bad the match teach the model that something relevant always
exists, which is precisely how confident fabrication is trained into a pipeline.

## When retrieval hurts

Retrieval hurts when the corpus is thin and generic, because generic text retrieves for
every query and displaces the specific instruction that would have helped. It hurts when
chunks contradict each other and nothing resolves the conflict. It hurts when retrieved
text is stale and the model treats it as current. And it hurts when the task is
generative rather than factual: asking for unusual ideas while flooding the context with
conventional material biases output toward the conventional. Measure with retrieval
disabled at least once before assuming it helps.

## Provenance all the way through

Give every chunk an id, show ids with the text, and require citations by id constrained
to the ids actually supplied. This makes hallucinated citations structurally impossible
rather than merely discouraged, and it lets a reader click through to the source. Carry
the provenance of ingested material as well, so a claim can be traced back to which
source it came from and how much that source is trusted.

## What to measure

Track, per run: how many queries were issued, how many distinct documents contributed
to the final context, the score of the lowest-ranked chunk shown, and how many queries
hit the coverage floor. Those four numbers explain most retrieval regressions without
needing a labelled evaluation set, and they are cheap to compute from the trace you
should already be keeping.
