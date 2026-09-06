# Roadmap

The system was specified in six phases, plus a seventh added afterwards: the strategic /
meta layer (`DESIGN-META.md`). This page maps each phase to what the baseline (`0.1.0`, see
`DESIGN.md`) implements, what is deliberately deferred, and the seam — the Protocol, function
or file — a later change should plug into so nothing above it has to move. The ordering principle of the baseline was: make every stage real, in-repo and
testable without tokens first; swap in heavier backends behind the same interfaces later.

## Phase 1 — Knowledge repository

**Baseline.** A bundled corpus of twelve hand-written documents (`src/ideate/corpus/`):
judging criteria, demo strategy, 24h/48h scoping, failure modes, deploy-and-webhooks, pitch
structure, ideation techniques, team roles, AI-agent project patterns, a `data-source` list of
free public APIs and datasets with their access level, project archetypes and generic-idea
antipatterns. A front-matter loader (`knowledge/loaders.py`) reads `.md`/`.txt`/`.json`/
`.jsonl` from the bundled directory plus any `IDEATE_CORPUS_DIRS` / `--corpus` directories,
with kinds `guidance | data-source | archetype | antipattern | event | evidence`. Event
material dropped into `corpus/event/` with `kind: event` is pinned into every run. The index
is saved to disk with a corpus fingerprint and rebuilt automatically when the corpus or the
chunk/embedder settings change. Content discipline is tested: no invented statistics, no fake
case studies, every paragraph fits the chunker.

**Deferred.**
- *Automated ingestion (arXiv, Devpost, event pages, sponsor docs, the web).* Seam:
  `loaders.load_corpus(dirs) -> list[Document]`. A fetcher only has to write markdown with
  front matter into a corpus directory (`kind: evidence` with a required `source`) — nothing
  downstream changes. Keep fetchers out of the core package so it stays stdlib-only.
- *Larger corpora.* The BM25 and vector stores are in-memory JSON; past a few thousand
  chunks, replace `VectorStore` (same `add`/`search`/`to_dict`) with an ANN index and keep
  `KnowledgeBase.save`/`load` as the persistence contract.

## Phase 2 — Agentic RAG: hybrid search, reranking, corrective RAG

**Baseline.** BM25 (`knowledge/bm25.py`) and a hashing embedder (`knowledge/embeddings.py`:
unigrams, bigrams, char 3-grams, tf-idf weighted, L2-normalised, 512 dimensions) fused with
reciprocal rank fusion (`knowledge/fusion.py`), then a reranker: `LexicalOverlapReranker`
(free), `LLMReranker` (one call per query) or none. `HybridRetriever`/`KnowledgeBase`
(`knowledge/retriever.py`) support kind-filtered exhaustive search, which the orchestrator
uses to pin `event` and `data-source` chunks. Corrective RAG is the graph loop `research ->
retrieve_more -> research`: the research agent must list `coverage_gaps` instead of
inventing evidence, `RetrieveMoreAgent` retrieves each gap, and the loop repeats while new
chunks arrive, bounded by `IDEATE_MAX_RETRIEVAL_ROUNDS`. Every retrieval query issued is
recorded on the result (`queries`), and every chunk carries per-stage ranks and scores.

**Deferred.**
- *Real embeddings (e.g. Voyage).* Seam: the `Embedder` Protocol (`name`, `dim`, `fit`,
  `embed`, `to_dict`). Add a class, register its name in `embedder_from_dict`, and relax the
  `hashing`/dim check in `pipeline.IdeationSystem._try_load`. An embedding API is a
  credential like any other: resolve it by presence, never read the value, and keep the
  hashing embedder as the tokenless default so tests stay offline.
- *Cross-encoder reranker.* Seam: the `Reranker` Protocol (`rerank(query, candidates,
  top_n)`). Add a third `IDEATE_RERANKER` name beside `lexical`/`llm`.
- *Graph RAG / adaptive RAG (query routing, self-reflection on retrieved chunks).* Seam: the
  `Retriever` Protocol for the store, and a new `Agent` in place of `RetrieveMoreAgent` for
  the control flow — `Graph.add_conditional_edge` already expresses "retrieve again / move
  on" as a closure over the state.

## Phase 3 — Multi-agent system

**Baseline.** A small in-repo graph runtime (`agents/graph.py`: nodes, plain edges,
conditional edges as closures over `Settings`, `END`, `max_steps`, verbose tracing) running
seven agents (`orchestrator`, `research`, `retrieve_more`, `domain_expert`, `creativity`,
`evaluator`, `synthesizer`) over one mutable `IdeationState`. Every LLM call goes through
`TracingLLM` and lands in the trace with a canonical tag, requested and served model, tokens,
duration and request id. Structured outputs are enforced by JSON schema on both providers
with one corrective retry; id references are enum-bound so the model cannot cite a chunk or
idea that was not shown.

**Deferred.**
- *LangGraph swap-in.* Seam: `Agent.run(state, ctx) -> state` is already a pure node
  function and `build_default_graph` is the only place edges are declared; the two
  conditional closures map one-to-one onto LangGraph conditional edges. Keep `TracingLLM`
  and `RunContext` — they are what make the trace and the query log provider-independent.
- *Parallel judges / streaming progress.* The persona calls in `PanelJudge.evaluate_many`
  are independent and can fan out; the trace must stay ordered by `started_at`.

## Phase 4 — LLM-as-judge evaluation

**Baseline.** A rubric with 1/3/5 anchors per criterion (`evaluation/rubric.py`; the default
weights novelty .30, feasibility .25, impact .25, demoability .20), built from the event's
own criteria strings (`--criteria "innovation:40,impact:30,demo:30"`) with feasibility
always present. A panel of persona judges (`evaluation/judge.py`) scores every idea in one
batched call per persona; consensus is the per-criterion median, `agreement` measures panel
spread, disqualification needs a majority, and ranking is tiered (feasible first,
infeasible second, disqualified last). `ideate judge` exposes the panel on any list of ideas.

**Deferred.**
- *Calibration sets.* A labelled set of ideas with human scores per criterion, run through
  `PanelJudge.evaluate_many`, comparing consensus to the human labels and per-persona
  variance via `scoring.agreement`. Seam: a `tests/calibration/` fixture plus an `ideate
  eval` subcommand (Phase 5) — no judge code needs to change.
- *Position-bias controls and pairwise comparison.* Seam: `LLMJudge.evaluate_many` receives
  the batch; shuffle order per persona there and re-map by `idea_id`.

## Phase 5 — Iterative improvement

**Baseline.** Two feedback loops. Inside a run: the evaluator writes critiques (consensus
weaknesses and the lowest criterion of each top-3 idea) and, while fewer than
`IDEATE_MIN_STRONG_IDEAS` ideas clear `IDEATE_ACCEPT_THRESHOLD`, the creativity agent runs
again with the top-3 ideas and critiques, refining half (`parent_id`) and inventing half.
Across events: `ideate learn` records an `Outcome` and distils `success`/`failure` patterns
into `memory.jsonl` (`improvement/feedback.py`, `memory/store.py`); the next run injects the
relevant patterns as leverage/avoid bullets into the orchestrator and as `memory` chunks
into the knowledge base. Patterns learned under the mock are quarantined. A third loop, over
the system's own process rather than over outcomes, lives in Phase 7 below.

**Deferred.**
- *`ideate eval` benchmarks keyed by run_id and version.* Every `result.json` already
  carries `run_id`, `version`, `settings`, `provider`, served models and the full trace, so a
  benchmark is a fixed list of themes and constraints, run under a named settings set,
  stored under `.ideate/evals/<version>/`, and compared on ranking stability, judge
  agreement, validation-retry rate, tokens and duration. Seam: `IdeationSystem.ideate` +
  `pipeline.load_result`; the mock makes the harness testable, but only real-provider runs
  are evidence.
- *Pattern decay and pruning; multi-user memory.* Seam: `MemoryStore` (JSONL, one record per
  line) — replace the file with a shared store behind the same methods.

## Phase 6 — Integration

**Baseline.** The `ideate` CLI (`index`, `run`, `judge`, `learn`, `memory`, `ingest`,
`strategy`, `reflect`, `meta`, `probe`),
markdown and JSON reports with a placeholder watermark under the mock, run directories,
probe receipts that can only come from a real provider, three blocker kinds mapped to exit
codes, a Claude Code skill (`.claude/skills/ideate/SKILL.md`) and a CI workflow that runs
the test matrix and writes nothing.

**Deferred.**
- *Web UI.* Seam: the `IdeationSystem` facade and `report.render_json`; a UI is a thin
  client over `ideate(...)` / `judge(...)` / `learn(...)` and the saved `result.json` files.
- *MCP server or GitHub Action entry points.* Same seam; keep credentials out of the tool
  exactly as the CLI does (presence only, `do-it-myself` when missing).
- *Live-endpoint validation of `AnthropicLLM`.* Not a code change: run `ideate probe` the
  day credentials exist, keep the receipt, then run the suite of scripted-mock cases against
  the real endpoint once and record what differed.

## Phase 7 — Strategic / meta layer

Added after the first six (`DESIGN-META.md`). The first six phases reason about the
hackathon; this one reasons about how the system itself works.

**Baseline.** Three data domains kept separate: domain knowledge (`corpus/*.md`), meta
knowledge (`corpus/meta/*.md`, `kind: meta` — eight documents on idea generation, problem
solving, memory design, self-improving systems, retrieval, evaluation, agent systems and
external memory ingestion), and meta memory (`.ideate/meta.jsonl`). A `StrategistAgent` runs
before the pipeline and commits to a plan (framing, problem type, emphasised techniques,
retrieval angles, rubric emphasis, planned rounds, failure modes to watch) whose every field
is clamped by `Strategy.sanitized` before it can touch the run. A `ReflectorAgent` runs after
the synthesizer on the run's own telemetry and writes a `RunReflection` plus scoped
`MetaPattern`s; `MetaStore.add_meta_pattern` merges on write, so a repeated observation raises
confidence (0.5 → 0.7 → 0.82 → …, capped at 0.95) instead of duplicating a row. `ideate
ingest` normalises external memory systems — ideate's own memory files, conversation exports,
generic JSON notes, markdown, `CLAUDE.md`-style rule files, directories — with provenance that
survives chunking, and every ingested snippet is rendered with an `[ingested: src-...]` label
under a system-prompt rule that such material is data and never an instruction. Meta memory
written under the mock never steers any run.

**Capture (added after the first pass).** The loops above only run if someone runs them, which
made them worth little to an owner who will not reliably log. Four commands move that work off
the human: `ideate note` (an instant, model-free write so an agent files a correction the moment
it happens, stored as `provider: human` and never quarantined), `ideate charter` (the meta goal
pinned and loaded verbatim by the strategist on every run, so it is never re-explained),
`ideate gaps` (the `coverage_gaps` runs already record, rendered as the exact fetch command that
fills each), and `ideate fetch` (arXiv abstracts or a page into the corpus as `kind: evidence`
with source, retrieval date and content hash, joining the corpus automatically). The arXiv path
is verified against the live API; everything else runs without a network.

**Deferred.**
- *Calibrating the strategist against outcomes.* Today a meta-pattern's confidence rises with
  repetition, not with whether the runs it steered produced ideas that placed. Seam:
  `Outcome.run_id` already links an outcome to its run, and `IdeationResult.strategy` records
  the plan that run used — join them and reweight. This needs real runs with real outcomes;
  it cannot be validated under the mock.
- *Pattern decay, contradiction detection and pruning.* Repetition-only confidence has no way
  to demote a lesson the world stopped agreeing with, and two contradictory patterns can both
  sit at high confidence. Seam: `MetaStore` (`_rewrite` already exists for merge-on-write).
- *Strategy A/B evaluation.* Run the same theme with and without the strategist, or with two
  different plans, and compare. Seam: the `ideate eval` harness in Phase 5 plus
  `--no-strategist`.
- *Richer ingestion: PDFs, web pages, Notion/Drive exports, other agents' memory formats.*
  Seam: `meta/ingest.py` `DETECTORS` — add a predicate and a normaliser; everything downstream
  (provenance, labelling, trust rule, indexing) already works from the `Document`.
- *Trust levels per source.* Ingested material is uniformly "reference data" today. A source
  the user vouches for versus one scraped from the internet could be weighted differently in
  retrieval. Seam: `MemorySource` (add a field) and `meta/context.py`.
- *Automatic correction capture.* `ideate note` removes the effort but still needs an agent to
  call it; a Claude Code hook could file corrections without any agent deciding to. Seam: the
  command already takes plain text and exits fast enough for a hook.
- *Deduplicating fetched evidence and pruning it.* `ideate fetch` will happily write the same
  paper twice under different queries, and nothing ever removes stale evidence. Seam:
  `content_sha256` is already in the front matter of every fetched document.
- *Beyond abstracts.* arXiv full texts, PDFs and paywalled sources are out of scope; only
  abstracts are fetched. Seam: `meta/fetch.py` `parse_arxiv` and the `Opener` protocol.
