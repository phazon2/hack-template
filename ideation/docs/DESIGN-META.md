# Design Spec v1 — Addendum §18: the Strategic / Meta Layer

Extends `ideation/docs/DESIGN.md`. Same binding force: every signature, default, id format
and ordering rule is a contract. Nothing here changes an existing contract except where it
says "AMENDS".

## 18.0 What this layer is

The baseline system reasons about **the hackathon**. The meta layer reasons about **the
system's own way of working**. Three separate data domains, never mixed:

| Domain | Question it answers | Where it lives |
|---|---|---|
| Domain knowledge | How do you win a hackathon? | `corpus/*.md` (kinds guidance, data-source, archetype, antipattern, event) |
| Meta knowledge | How do you generate ideas, solve problems, design memory, design agent systems, judge output? | `corpus/meta/*.md` (kind `meta`), plus ingested `rules` |
| Meta memory | What has THIS system learned about its own process across runs? | `.ideate/meta.jsonl` (reflections, meta-patterns, memory sources) |

Two new agents close the loop at the process level:
- **Strategist** runs FIRST and decides *how to approach this particular problem*.
- **Reflector** runs LAST and records *what the system should do differently next time*.

Outcome memory (existing) learns from the world's verdict on an idea. Meta memory learns from
the system's own behaviour — available immediately, without waiting for a hackathon to end.

Mock quarantine applies identically: reflections and meta-patterns produced under the mock
carry `provider="mock"` and are invisible to real runs unless `include_mock=True`.

## 18.1 Additions to `models.py`

AMENDS `CHUNK_KINDS`: add `"meta"`, `"memory-source"`, `"rules"`.
Add `PROBLEM_TYPES = ("greenfield", "constrained", "integration", "data", "social", "unclear")`
and `META_PATTERN_KINDS = ("strategy", "process", "pitfall")`.

```python
@dataclass
class Strategy(Model):
    framing: str = ""                       # one paragraph: how to see this problem
    problem_type: str = "unclear"           # one of PROBLEM_TYPES
    emphasis_techniques: list[str] = []     # subset of TECHNIQUES, ordered, 2..4 entries
    retrieval_angles: list[str] = []        # extra query angles, 0..4
    rubric_emphasis: dict = {}              # criterion name -> multiplier, clamped 0.5..2.0
    rounds: int = 0                         # planned creativity rounds; 0 = use settings
    watch_for: list[str] = []               # failure modes to avoid this run, 0..5
    rationale: str = ""
    source_patterns: list[str] = []         # MetaPattern ids that informed this

    def sanitized(self, settings, rubric) -> "Strategy":
        """Clamp every field into a safe range. Called by the agent before it is stored."""
```
`sanitized` rules (binding): `problem_type` not in PROBLEM_TYPES -> `"unclear"`;
`emphasis_techniques` filtered to TECHNIQUES, deduped preserving order, truncated to 4, empty
-> `list(TECHNIQUES[:3])`; `rubric_emphasis` keys filtered to `rubric.names()`, values clamped
to [0.5, 2.0], non-numeric dropped; `rounds` clamped to `[1, settings.max_iterations]`, 0 stays
0 (meaning "use settings"); `retrieval_angles` truncated to 4; `watch_for` truncated to 5.

```python
@dataclass
class RunReflection(Model):
    run_id: str
    theme: str = ""
    created_at: str = ""
    provider: str = ""
    what_worked: list[str] = []
    what_failed: list[str] = []
    process_changes: list[str] = []   # concrete changes to how the system runs
    signal_quality: str = ""          # did the knowledge base actually help?
    winning_technique: str = ""
    judge_disagreement: str = ""
    wasted_effort: list[str] = []

@dataclass
class MetaPattern(Model):
    kind: str                          # one of META_PATTERN_KINDS
    text: str
    tags: list[str] = []
    scope: str = "global"              # "global" or a PROBLEM_TYPES value
    source_run_id: str = ""
    id: str = ""                       # __post_init__: f"meta-{sha256_hex(scope + '|' + text)[:12]}"
    provider: str = ""
    created_at: str = ""
    confidence: float = 0.5
    observations: int = 1

@dataclass
class MemorySource(Model):
    id: str                            # f"src-{sha256_hex(path)[:12]}" when empty
    path: str
    title: str = ""
    kind: str = "external"             # "ideate" | "external"
    format: str = "markdown"           # markdown | jsonl | json | text | ideate-memory | conversation | rules
    ingested_at: str = ""
    fingerprint: str = ""              # sha256 of the normalised content
    n_records: int = 0
    n_documents: int = 0
    notes: str = ""
```
AMENDS `IdeationState`: add `strategy: Strategy | None = None`, `reflection: RunReflection | None = None`.
AMENDS `IdeationResult`: add the same two fields.
AMENDS `ALL_MODELS`: append the four new dataclasses.

## 18.2 `ideate/meta/` package

Import position in the DAG (AMENDS §2.1): `memory` <- `meta` <- `evaluation`. `meta` may import
`models`, `config`, `llm`, `knowledge`, `memory`; nothing below it imports `meta` except
`agents`, `pipeline`, `report`, `cli`.

### `meta/store.py` — `MetaStore(path: Path)`
JSONL, one record per line, exactly `{"type": "reflection" | "meta_pattern" | "memory_source", **obj.to_dict()}`.
Unknown `type` skipped with a stderr warning. Missing file -> empty. Parent dirs created on write.
```python
add_reflection(r: RunReflection) -> None
add_meta_pattern(p: MetaPattern) -> MetaPattern     # merge-on-write, see below
add_source(s: MemorySource) -> None
reflections(include_mock: bool = False) -> list[RunReflection]
meta_patterns(kind=None, scope=None, include_mock=False) -> list[MetaPattern]
relevant_meta_patterns(query, kind=None, scope=None, k=5, include_mock=False) -> list[MetaPattern]
sources() -> list[MemorySource]
source_for(path: str) -> MemorySource | None
clear() -> None
```
**Merge-on-write:** `add_meta_pattern` keys on `id` (scope + text hash). When a record with that
id already exists, the stored copy's `observations += 1` and
`confidence = min(0.95, round(1 - (1 - confidence) * 0.6, 4))` and the file is rewritten;
otherwise the record is appended as given. This is what makes a repeated observation stronger
than a one-off without ever fabricating evidence. Rewriting preserves line order (the merged
record stays at its original position).
`relevant_meta_patterns` ranks by BM25 over `text + " " + tags` multiplied by `confidence`,
sorted by `(-score, id)`.

### `meta/ingest.py`
```python
DETECTORS: tuple[tuple[str, Callable[[Path], bool]], ...]   # (format, predicate), tried in order
def detect_format(path: Path) -> str
def ingest_path(path, *, kind="external", title=None, now=None) -> tuple[MemorySource, list[Document]]
def ingest_into(path, store: MetaStore, *, kind="external", title=None, now=None) -> tuple[MemorySource, list[Document]]
```
Formats and normalisation (each produced `Document` carries
`metadata = {"kind": <chunk kind>, "memory_source": source.id, "source_path": str(path), "tags": [...]}`):
- `ideate-memory`: a `.jsonl` whose first parseable line has `type` in `{"outcome", "pattern"}`.
  One Document per record. Outcome text: `"Outcome ({hackathon}): {idea_title}. Placed: {placed}. Success: {success}. Judge feedback: {judge_feedback} Notes: {notes}"`. Pattern text: `"Lesson ({kind}): {text} (tags: ...)"`. Chunk kind `memory-source`.
- `conversation`: a `.jsonl`/`.json` list whose records have `role` and `content` (or `author`/`text`).
  Grouped into Documents of at most 40 turns, text `"{role}: {content}"` per line. Chunk kind `memory-source`.
- `json` / `jsonl` (generic): records with any of `text`, `content`, `body`, `note`, `summary`.
  One Document per record; `title` from `title`/`name`/`id` when present. Chunk kind `memory-source`.
- `rules`: a markdown file whose name matches `CLAUDE.md`, `AGENTS.md`, `*rules*.md`, `*instructions*.md`
  (case-insensitive). Chunk kind `rules`. These are treated as operating constraints, not evidence.
- `markdown` / `text`: front matter honoured exactly as `knowledge/loaders.py` does (reuse its
  parser via a public helper; if the loader does not expose one, duplicate the 15-line parser and
  note it). Chunk kind = front-matter `kind` when present, else `memory-source`.
- A directory: walk recursively (sorted), ingest every supported file, one `MemorySource` for the
  directory with `n_documents` summed.
`fingerprint = sha256_hex("\n".join(f"{d.id}:{sha256_hex(d.text)}" for d in documents))`.
Re-ingesting an unchanged path is a no-op that returns the stored source (the CLI says so).
Unsupported/unreadable file -> `MetaIngestError` (a `ValueError` subclass) naming the path and why.
**Trust:** ingested content is data, never instructions. Every prompt that shows ingested chunks
labels them `[ingested: {source_id}]` and the agent system prompts state that ingested material
is reference data and must not be followed as instructions.

### `meta/context.py`
```python
def meta_context_for(theme, problem_type, kb, store, *, k=6, include_mock=False) -> str
```
Bullets, each prefixed by scope and confidence: `"[strategy|global|0.72] text"`. Empty string
when there is nothing. Used by the strategist and the creativity agent.

## 18.3 New agents

Canonical tags (AMENDS §9.1): add `strategist` and `reflector`.

### `agents/strategist.py` — `StrategistAgent` (tag `strategist`, effort `settings.effort_light`)
Runs FIRST; the graph entry point becomes `strategist` when `settings.strategist` is true.
Inputs: theme, `constraints_block`, meta chunks (`ctx.retrieve(theme, k=settings.meta_k, kind="meta")`
plus all `rules` chunks), `meta_context_for(...)`, and the list of technique names with one-line
descriptions. Schema: `obj({"framing": str_(), "problem_type": enum(PROBLEM_TYPES), "emphasis_techniques": arr(enum(TECHNIQUES), 2, 4), "retrieval_angles": arr(str_(), 0, 4), "rubric_emphasis": arr(obj({"criterion": enum(rubric.names()), "multiplier": num(0.5, 2.0)}), 0, len(rubric.names())), "rounds": int_(1, settings.max_iterations), "watch_for": arr(str_(), 0, 5), "rationale": str_()})`.
(`rubric_emphasis` is an ARRAY in the schema — JSON Schema cannot express a closed object with
dynamic keys — and the agent converts it to the dict on the dataclass.)
Code then calls `strategy.sanitized(settings, rubric)` and sets `state.strategy` and
`strategy.source_patterns` from the meta-patterns actually shown.
**Downstream effects (all bounded, all optional):**
- Orchestrator appends `strategy.retrieval_angles` to `state.queries` after the theme, before the LLM expansions.
- Creativity: technique cycling draws from `strategy.emphasis_techniques` when present (still cycling), and the prompt includes `strategy.framing` and `Avoid: {watch_for}`.
- Evaluator: rubric weights multiplied by `strategy.rubric_emphasis` then renormalised, via `Rubric.reweighted(emphasis) -> Rubric` (new method on Rubric, pure, does not mutate).
- Loop rule B (AMENDS §9.3): `planned = strategy.rounds or settings.max_iterations`; the loop continues while `len(strong) < settings.min_strong_ideas and state.iteration < min(planned, settings.max_iterations)`.
When `settings.strategist` is false the entry node is `orchestrator` and every effect above is skipped.

### `agents/reflector.py` — `ReflectorAgent` (tag `reflector`, effort `settings.effort_light`)
Runs after the synthesizer, before END, when `settings.reflector` is true.
Inputs (computed by code, not the LLM): the strategy; per-agent call and token totals from the
trace; `retrieval_rounds`; `coverage_gaps`; how many ideas were dropped by `validate_idea` and by
the diversity filter (AMENDS: `IdeationState` gains `dropped_invalid: int = 0` and
`dropped_duplicate: int = 0`, incremented by the creativity agent); the technique of each top-3
idea; consensus weighted scores and per-idea `agreement`; the lowest-scoring criterion overall.
Schema: `obj({"what_worked": arr(str_(), 1, 4), "what_failed": arr(str_(), 0, 4), "process_changes": arr(str_(), 1, 4), "signal_quality": str_(), "winning_technique": enum(TECHNIQUES), "judge_disagreement": str_(), "wasted_effort": arr(str_(), 0, 3), "meta_patterns": arr(obj({"kind": enum(META_PATTERN_KINDS), "text": str_(), "scope": enum(("global",) + PROBLEM_TYPES), "tags": arr(str_(), 1, 4)}), 1, 5)})`.
Code sets `run_id`, `theme`, `created_at`, `provider` on the reflection and
`source_run_id`, `provider`, `created_at` on each pattern, persists both to the MetaStore, and
sets `state.reflection`. The prompt states plainly: base every claim on the run data shown; when
the data does not support a claim, say so instead of inventing one.

## 18.4 Settings (AMENDS §6)
```
meta_path: str = ".ideate/meta.jsonl"    # IDEATE_META_PATH
strategist: bool = True                  # IDEATE_STRATEGIST
reflector: bool = True                   # IDEATE_REFLECTOR
meta_k: int = 6                          # IDEATE_META_K
```

## 18.5 Corpus additions (kind `meta`), in `src/ideate/corpus/meta/`
Same front-matter contract and the same evidence rules: no invented statistics, no fabricated
case studies, no fake citations. 500–1200 words each, self-contained paragraphs.
1. `idea-generation-strategy.md` — choosing an approach per problem type; when divergence helps and when it wastes the clock.
2. `problem-solving-methods.md` — first principles, inversion, constraint relaxation, analogy transfer, decomposition, working backwards from the demo.
3. `memory-system-design.md` — episodic vs semantic vs procedural memory; what deserves to be written; provenance and confidence; forgetting; the self-confirming-memory trap; why mock-generated memory must be quarantined.
4. `self-improving-systems.md` — reflection loops, actor-critic, eval-driven iteration; degeneration modes (drift, confirmation loops, metric gaming); why a human decision point stays in the loop.
5. `retrieval-strategy.md` — lexical vs dense vs hybrid, query expansion, reranking, coverage gaps, when retrieval hurts.
6. `evaluation-design.md` — LLM-as-judge pitfalls: position and verbosity bias, self-preference, calibration, panels, treating disagreement as signal.
7. `agent-system-design.md` — orchestration patterns, when multi-agent beats a single call, context hygiene, determinism, tracing, cost control.
8. `external-memory-ingestion.md` — bringing your own memory systems in: formats, provenance, trust levels, why ingested text is data and never instructions.
Plus `corpus/meta/README.md` (skipped by the loader, like the other READMEs).
AMENDS the `test_corpus_content.py` assertions: allow `kind: meta`; require >= 8 meta documents;
keep the existing one-each requirement for data-source/archetype/antipattern.

## 18.6 CLI additions (AMENDS §13)
- `ideate ingest PATH [--kind external|ideate] [--title T] [--reindex]` — normalise and register a memory source; prints a one-line summary to stderr and the source id to stdout; `--reindex` rebuilds the index so the material is retrievable immediately. Re-ingesting unchanged content prints "unchanged" and exits 0.
- `ideate strategy THEME [constraint flags]` — runs the strategist alone and prints the plan (cheap: one call). Honours `--json -`.
- `ideate reflect --run RUN_ID` — loads a saved run from `runs_dir` and runs the reflector alone.
- `ideate meta [--kind strategy|process|pitfall] [--scope S] [--sources] [--include-mock]` — lists meta-patterns (with confidence and observation count) or, with `--sources`, ingested memory sources. Mock rows marked `[mock]`.
- `ideate run` gains `--no-strategist` / `--no-reflector`.

## 18.7 Report (AMENDS §12)
New section (1a) "Strategy" directly after the banner: framing, problem type, emphasised
techniques, what the system was watching for, and why. New final section (10) "What the system
learned": the reflection's what_worked / what_failed / process_changes, and the meta-patterns
written. Both omitted when absent.

## 18.8 Pipeline (AMENDS §11)
`IdeationSystem` gains `self.meta = MetaStore(settings.meta_path)`, passes it into `RunContext`
(new field `meta: MetaStore`), and adds `strategy(theme, constraints)` and `reflect(run_id)`
methods mirroring the CLI. `IdeationResult.from_state` copies `strategy` and `reflection`.
Ingested documents are part of the index: `load_or_build_index` includes every registered
`MemorySource` path in the corpus fingerprint so ingesting new material invalidates the index.

## 18.9 Interfaces this layer plugs into (verified against the built code)

- `agents/context.py` defines `CANONICAL_TAGS` (a tuple) and `is_canonical_tag(tag)`; ADD
  `"strategist"` and `"reflector"` to the tuple.
- `RunContext` is a dataclass with fields `llm, kb, memory, rubric, settings, trace, queries_issued`.
  ADD `meta: MetaStore | None = None` (last field, defaulted so existing constructions keep working).
  Its `request(tag, system, prompt, json_schema=None, effort=None)` and
  `retrieve(query, k=None, kind=None)` are used unchanged.
- `evaluation/rubric.py` has `Rubric.names()`, `.weights()`, `.weighted_score()`, `.to_prompt()`,
  `.to_dict()/.from_dict()`, `.from_judging_criteria()`, and `DEFAULT_RUBRIC`. ADD a pure
  `Rubric.reweighted(emphasis: dict[str, float]) -> Rubric` that returns a NEW Rubric with each
  criterion's weight multiplied by `emphasis.get(name, 1.0)` and renormalised; unknown names in
  `emphasis` are ignored; the receiver is never mutated.
- `knowledge/loaders.py` exposes `parse_front_matter(text) -> tuple[dict, str]` — reuse it in
  `meta/ingest.py` rather than duplicating the parser.
- `memory/store.py` shows the JSONL store shape to mirror (`__init__(path)`, `_records()`,
  `_append(record)`, `_warn(message)`, typed accessors). `MetaStore` follows the same shape and
  adds a `_rewrite(records)` helper for merge-on-write.
- `pipeline.py` has the module-level `result_from_state(state, ctx, settings, run_id, created_at)`
  attached as `IdeationResult.from_state`, plus `IdeationSystem._documents()`, `_try_load()`,
  `build_index(force)`, `load_or_build_index()`, `save_run()`, `save_receipt()` and the
  module-level `load_result(path)`. Extend `_documents()` to append the documents of every
  registered `MemorySource` so ingested material is indexed and fingerprinted.
- `cli.py` uses `sub.add_parser(...)` plus one `cmd_<name>(args) -> int` per subcommand and a
  `main(argv=None) -> int`; follow that shape for the new subcommands.
- `agents/orchestrator.py` has `build_default_graph(settings)` and the conditional-edge closures
  `after_retrieve_more(settings)` / `after_evaluator(settings)`. Extend the builder in place.

## 18.10 Testing (AMENDS §17)
- Trace-length formula becomes `strategist + 1 + retrieval_rounds + 1 + iterations * (1 + len(personas)) + 1 + reflector` where `strategist`/`reflector` are 1 when enabled, 0 otherwise. Test both enabled and both disabled.
- `Strategy.sanitized` clamps: out-of-range multipliers, unknown criteria, unknown techniques, rounds above `max_iterations`, unknown problem type.
- Strategist effects are observable: with a scripted strategy naming `retrieval_angles`, those queries appear in `ctx.queries_issued`; with `rubric_emphasis` doubling one criterion, the evaluator's weights change and `Rubric.reweighted` leaves the original untouched.
- MetaStore: merge-on-write bumps `observations` and `confidence` and does not duplicate; line order preserved; mock quarantine; `relevant_meta_patterns` confidence weighting.
- Ingest: each format detected and normalised (ideate-memory jsonl, conversation jsonl, generic json, CLAUDE.md as `rules`, markdown with front matter, a directory); re-ingest unchanged is a no-op; unreadable path raises `MetaIngestError`; ingested chunks carry `memory_source` provenance; ingesting a CLAUDE.md does not cause any agent prompt to treat it as an instruction (assert the `[ingested: ...]` label and the system-prompt sentence are present).
- Determinism unchanged: two identical runs produce identical results after the standard exclusions, with the meta layer enabled.
- CLI: `ideate ingest` on a temp CLAUDE.md then `ideate meta --sources` lists it; `ideate strategy "theme"` prints a plan under the mock and is watermarked; `ideate reflect --run <id>` works on a saved run.
