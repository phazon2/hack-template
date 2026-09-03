# Ideation System — Design Spec v1 (implementation contract)

This document is the single source of truth for the baseline. Several engineers (or agents)
implement disjoint file sets against it in parallel, so every signature, default, id format
and ordering rule below is binding. When this doc and code disagree, fix the code.

Repo: `phazon2/hack-template`, branch `claude/hackathon-ideation-system-hlsks3`.
Everything lives under `ideation/` (a self-contained Python 3.11 project) plus one thin
Claude Code skill at `.claude/skills/ideate/SKILL.md` and one CI workflow. `main` and the
template root are otherwise untouched; the branch can be merged, kept long-lived, or split
into its own repo with `git subtree split -P ideation`.

## 1. Goals of the baseline
1. The whole pipeline runs end to end with zero API tokens via a deterministic mock LLM.
   Tests cover every module and the end-to-end path. No test ever touches the network.
2. The day the user has Anthropic credentials: `export ANTHROPIC_API_KEY=...` (or
   `IDEATE_PROVIDER=anthropic` with an Anthropic CLI profile) and `ideate probe` makes ONE
   real call and writes a receipt. Nothing else changes.
3. Evidence discipline (repo `CLAUDE.md`): mock outputs are placeholders, never evidence.
   Every report produced under the mock is watermarked (§12). `ideate probe` refuses to run
   under the mock. Receipts come only from a real provider response. CI never writes report
   or receipt files. Patterns learned under the mock are quarantined from real runs (§7).
4. No credentials are handled: the tool never reads the *values* of credential env vars,
   never accepts a key flag, never prompts. Missing credentials are reported as a
   `do-it-myself` blocker (exact wording, §13).
5. Minimal dependencies: the core is pure stdlib. `anthropic` is an optional extra,
   `pytest` is dev-only. No numpy/faiss/langchain/sentence-transformers. Every retrieval
   primitive is implemented in-repo behind a Protocol so heavier backends can be swapped in.

Non-goals (see `docs/ROADMAP.md`): real embedding models, cross-encoder rerankers, graph RAG,
automated arXiv/Devpost/web ingestion, a web UI, multi-user memory, `ideate eval` benchmarks.

## 2. Layout
```
ideation/
  pyproject.toml
  README.md
  docs/DESIGN.md              # this file
  docs/ROADMAP.md             # user's 6 phases -> baseline status -> later
  src/ideate/
    __init__.py               # __version__ = "0.1.0"; lazy __getattr__ for IdeationSystem
    __main__.py               # from ideate.cli import main; raise SystemExit(main())
    models.py                 # ALL shared dataclasses + to_dict/from_dict + slug()
    config.py                 # Settings, DEFAULT_MODEL
    llm/__init__.py
    llm/base.py               # LLM Protocol, LLMRequest, LLMResponse, error classes
    llm/schema.py             # schema builders, for_api(), validate(), coerce()
    llm/mock.py               # MockLLM
    llm/anthropic_provider.py # AnthropicLLM
    llm/factory.py            # make_llm(settings), resolve_provider(settings)
    knowledge/__init__.py
    knowledge/tokenize.py     # tokenize()
    knowledge/loaders.py      # load_corpus(dirs) -> list[Document]
    knowledge/chunking.py     # split_document()
    knowledge/bm25.py         # BM25Index
    knowledge/embeddings.py   # Embedder Protocol, HashingEmbedder, embedder_from_dict
    knowledge/vector_store.py # VectorStore
    knowledge/fusion.py       # reciprocal_rank_fusion, fuse_with_ranks
    knowledge/rerank.py       # Reranker Protocol, LexicalOverlapReranker, LLMReranker
    knowledge/retriever.py    # Retriever Protocol, HybridRetriever, KnowledgeBase
    knowledge/pinning.py      # (optional helper) not required
    corpus/                   # seed knowledge, package data (§15)
    corpus/README.md          # front-matter contract (skipped by the loader)
    corpus/event/README.md    # drop event materials here (skipped by the loader)
    memory/__init__.py
    memory/store.py           # MemoryStore
    evaluation/__init__.py
    evaluation/rubric.py      # Criterion, Rubric, DEFAULT_RUBRIC
    evaluation/scoring.py     # weighted_score, median, agreement, aggregate
    evaluation/judge.py       # LLMJudge, PanelJudge, compare_ideas
    improvement/__init__.py
    improvement/feedback.py   # learn_from_outcome, memory_context_for
    agents/__init__.py
    agents/context.py         # TracingLLM, RunContext, constraints_block
    agents/base.py            # Agent ABC
    agents/graph.py           # Graph, GraphError, END
    agents/orchestrator.py    # OrchestratorAgent, RetrieveMoreAgent, build_default_graph
    agents/research.py        # ResearchAgent
    agents/domain_expert.py   # DomainExpertAgent
    agents/creativity.py      # CreativityAgent, TECHNIQUES, GENERIC_USERS, validate_idea
    agents/evaluator.py       # EvaluatorAgent
    agents/synthesizer.py     # SynthesizerAgent
    pipeline.py               # IdeationSystem, IdeationResult.from_state
    report.py                 # PLACEHOLDER_BANNER, render_markdown, render_json
    cli.py                    # main(argv=None) -> int
  tests/
    conftest.py               # inserts <ideation>/src at the front of sys.path; fixtures
    test_*.py
.github/workflows/ideation-ci.yml
.claude/skills/ideate/SKILL.md
```

### 2.1 Import rules (a DAG; violations are bugs)
Imports may only point downward in this order:
`models` <- `config` <- `llm` <- `knowledge` <- `memory` <- `evaluation` <- `improvement` <- `agents` <- `pipeline` <- `report` <- `cli`.
- `models.py` and `config.py` import only the stdlib.
- `llm/*` imports only `models`, `config`, `llm.base`, `llm.schema`. `llm/mock.py` never imports `knowledge`.
- `memory` may import `knowledge.bm25` and `knowledge.tokenize`; `knowledge` never imports `memory`.
- `IdeationResult.from_state` lives in `pipeline.py` (not in `models.py`).
- `ideate/__init__.py` exports `__version__` and a lazy `__getattr__` for `IdeationSystem`.
  Subpackage `__init__.py` files import only their own submodules (or nothing).
- `DEFAULT_MODEL = "claude-opus-5"` is defined once, in `config.py`.

### 2.2 pyproject.toml
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "ideate"
version = "0.1.0"
description = "Hackathon ideation system: hybrid RAG + multi-agent + LLM-judge panel + outcome memory"
requires-python = ">=3.11"
dependencies = []
[project.optional-dependencies]
anthropic = ["anthropic>=1.3"]
dev = ["pytest>=8"]
[project.scripts]
ideate = "ideate.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
[tool.setuptools.package-data]
ideate = ["corpus/**/*.md"]
[tool.pytest.ini_options]
testpaths = ["tests"]
```

## 3. Data contracts (`models.py`)
All types are `@dataclass`. Every list/dict default uses `field(default_factory=...)`.

**Serialization convention.** `models.to_dict(obj)` is a module-level function built on
`dataclasses.asdict` (nested dataclasses become plain dicts, no type tags, `None` stays
`null`). Every dataclass also has `def to_dict(self) -> dict` (delegates) and
`@classmethod from_dict(cls, d: dict)` that ignores unknown keys, applies defaults for missing
keys, and recursively rebuilds nested dataclasses (lists of dataclasses included).
A parametrised round-trip test covers every dataclass.

**Ids and helpers.**
- `slug(text: str) -> str`: lowercase, every run of non-alphanumerics -> `-`, strip leading/
  trailing `-`, truncate to 40 chars.
- `sha256_hex(text: str) -> str`.
- Never use builtin `hash()` on str/bytes anywhere in the codebase (PYTHONHASHSEED varies).

```python
TECHNIQUES = ("analogical", "assumption_breaking", "reverse", "scale", "combination", "direct")
BLOCKER_KINDS = ("config-fixable", "do-it-myself", "genuinely human-only")

@dataclass
class Document:
    id: str; title: str; text: str; source: str = ""; metadata: dict = {}   # metadata: tags(list[str]), kind, url, published, authors

@dataclass
class Chunk:
    id: str; doc_id: str; text: str; position: int; metadata: dict = {}    # metadata: title, source, kind, tags

@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float                       # score of the LAST stage that touched it
    ranks: dict[str, int] = {}         # 1-based positions per stage: bm25, vector, fused, rerank (absent stage -> key omitted)
    scores: dict[str, float] = {}      # bm25 (raw), vector (cosine), rrf (fused), rerank (final) — keys present only when produced

@dataclass
class HackathonConstraints:
    hours: int = 24
    team_size: int = 3
    judging_criteria: list[str] = []   # raw strings, e.g. "innovation:40"
    tech_preferences: list[str] = []
    must_avoid: list[str] = []
    tracks: list[str] = []
    notes: str = ""

@dataclass
class ResearchFindings:
    trends: list[str] = []; case_studies: list[str] = []; pitfalls: list[str] = []
    opportunities: list[str] = []; citations: list[str] = []; coverage_gaps: list[str] = []

@dataclass
class TechnicalAssessment:
    constraints: list[str] = []; required_skills: list[str] = []; challenges: list[str] = []
    breakthroughs: list[str] = []; suggested_stack: list[str] = []
    building_blocks: list[str] = []    # concrete APIs/datasets/libs with access level
    hour_budget: list[str] = []        # split of hours: setup / walking skeleton / build / integrate / rehearse

@dataclass
class Idea:
    title: str
    description: str
    id: str = ""                       # code-filled: idea-{iteration}-{n}, n 1-based; "idea-0-{n}" for `ideate judge`
    one_liner: str = ""                # <= 20 words
    target_user: str = ""              # a named role in a named situation
    key_innovation: str = ""
    technique: str = "direct"          # one of TECHNIQUES
    technical_approach: str = ""
    demo_strategy: str = ""
    demo_moment: str = ""              # the on-screen moment at ~90 seconds
    data_sources: list[str] = []       # "name — access: none|free key|account — what it provides"
    mvp_scope: list[str] = []
    cut_first: list[str] = []          # ordered
    closest_existing: str = ""
    build_hours_estimate: int = 0
    risks: list[str] = []
    citations: list[str] = []          # chunk ids that were shown
    parent_id: str | None = None       # round >= 2 refinements

@dataclass
class CriterionScore:
    name: str; score: float; rationale: str = ""        # score 1..5

@dataclass
class IdeaEvaluation:
    idea_id: str
    scores: list[CriterionScore] = []
    weighted_score: float = 0.0        # code-filled from rubric (1..5)
    strengths: list[str] = []; weaknesses: list[str] = []; suggestions: list[str] = []; risks: list[str] = []
    closest_existing: str = ""
    demo_break_risk: str = ""
    disqualified: bool = False
    disqualify_reason: str = ""
    judge: str = ""                    # code-filled: persona text, or "consensus"

@dataclass
class PanelVerdict:
    idea_id: str
    evaluations: list[IdeaEvaluation] = []
    consensus: IdeaEvaluation = IdeaEvaluation(idea_id="")   # via default_factory
    agreement: float = 0.0

@dataclass
class Alternative:
    idea_id: str; choose_if: str

@dataclass
class Proposal:
    idea_id: str = ""                  # code-filled = ranking[0]
    executive_summary: str = ""; value_proposition: str = ""; why_this: str = ""
    implementation_plan: list[str] = []; demo_plan: list[str] = []; demo_script: list[str] = []
    impact: str = ""
    first_hour_plan: list[str] = []; milestones: list[str] = []; team_split: list[str] = []
    cut_list: list[str] = []; pivot_trigger: str = ""
    human_dependencies: list[str] = [] # each prefixed "config-fixable: " / "do-it-myself: " / "genuinely human-only: "
    alternatives: list[Alternative] = []

@dataclass
class TraceStep:
    agent: str                         # canonical tag (§9.1)
    provider: str; model: str          # served model
    requested_model: str = ""
    prompt_sha256: str = ""
    input_tokens: int = 0; output_tokens: int = 0
    duration_ms: int = 0
    request_id: str | None = None
    started_at: str = ""               # ISO-8601 UTC
    stop_reason: str | None = None
    error: str | None = None

@dataclass
class IdeationState:
    theme: str
    constraints: HackathonConstraints
    queries: list[str] = []
    knowledge: list[RetrievedChunk] = []
    memory_context: str = ""
    research: ResearchFindings | None = None
    assessment: TechnicalAssessment | None = None
    ideas: list[Idea] = []
    verdicts: list[PanelVerdict] = []
    ranking: list[str] = []
    proposal: Proposal | None = None
    critiques: list[str] = []
    iteration: int = 0
    retrieval_rounds: int = 0
    coverage_gaps: list[str] = []
    retrieve_more_added: int = 0
    visited: list[str] = []

@dataclass
class IdeationResult:
    run_id: str; created_at: str; version: str
    theme: str; constraints: HackathonConstraints
    provider: str; model: str
    settings: dict = {}
    queries: list[str] = []
    knowledge: list[RetrievedChunk] = []
    research: ResearchFindings | None = None
    assessment: TechnicalAssessment | None = None
    ideas: list[Idea] = []
    verdicts: list[PanelVerdict] = []
    ranking: list[str] = []
    proposal: Proposal | None = None
    iterations: int = 0
    retrieval_rounds: int = 0
    coverage_gaps: list[str] = []
    trace: list[TraceStep] = []
    is_placeholder: bool = False       # provider == "mock"

@dataclass
class Outcome:
    hackathon: str
    idea_title: str
    idea_summary: str = ""
    id: str = ""                       # default f"out-{uuid4().hex[:12]}" assigned in __post_init__ when empty
    placed: str | None = None
    success: bool = False
    judge_feedback: str = ""
    notes: str = ""
    what_was_cut: str = ""
    demo_worked: bool | None = None
    run_id: str | None = None
    idea_id: str | None = None
    recorded_at: str = ""              # code-filled ISO-8601 UTC (injectable `now`)

@dataclass
class Pattern:
    kind: str                          # "success" | "failure"
    text: str
    tags: list[str] = []
    source_outcome_id: str = ""
    id: str = ""                       # default f"pat-{sha256_hex(source_outcome_id + text)[:12]}" in __post_init__ when empty
    provider: str = ""                 # LLMResponse.provider that produced it ("mock" quarantined)
    created_at: str = ""
```

**Schema vs dataclass rule.** LLM-facing JSON schemas never contain code-filled fields
(`Idea.id`, `IdeaEvaluation.judge`, `IdeaEvaluation.weighted_score`, `Proposal.idea_id`,
`Pattern.id/source_outcome_id/provider/created_at`, `Outcome.id/recorded_at`). Code fills
them after parsing.

## 4. LLM layer

### 4.1 `llm/base.py`
```python
@dataclass
class LLMRequest:
    system: str; prompt: str; tag: str
    json_schema: dict | None = None
    max_tokens: int = 16000
    effort: str = "high"               # low|medium|high|xhigh|max

@dataclass
class LLMResponse:
    text: str
    data: dict | list | None           # parsed + validated JSON when json_schema given
    provider: str                      # "mock" | "anthropic"
    model: str                         # SERVED model
    requested_model: str = ""
    input_tokens: int = 0; output_tokens: int = 0
    message_id: str | None = None
    request_id: str | None = None
    stop_reason: str | None = None
    fallback_ran: bool = False

class LLM(Protocol):
    provider: str
    model: str
    def complete(self, request: LLMRequest) -> LLMResponse: ...

class LLMError(Exception): ...
class LLMConfigError(LLMError):
    def __init__(self, message: str, kind: str = "config-fixable", hint: str = ""): ...  # kind in BLOCKER_KINDS
class LLMRefusal(LLMError):
    def __init__(self, category: str | None, explanation: str | None): ...
class LLMTransientError(LLMError): ...
class LLMBadOutput(LLMError): ...
```

### 4.2 `llm/schema.py`
Builders (every object schema sets `additionalProperties: False` and `required` = all props
unless `required` is given): `obj(props: dict, required: list[str] | None = None)`,
`arr(items, min_items=None, max_items=None)`, `str_()`, `num(minimum=None, maximum=None)`,
`int_(minimum=None, maximum=None)`, `bool_()`, `enum(values: list[str])`.
- `for_api(schema) -> dict`: deep copy with `minimum`, `maximum`, `multipleOf`, `minLength`,
  `maxLength`, `minItems`, `maxItems`, `pattern` removed at every depth (keeps `type`,
  `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `description`).
- `validate(instance, schema, path="$") -> list[str]` error strings; supports type (incl.
  integer vs number), properties, required, additionalProperties, items, enum, minimum,
  maximum, minItems, maxItems.
- `coerce(instance, schema) -> instance`: clamps numbers into [minimum, maximum] and truncates
  arrays to `maxItems` (deep copy). Providers run `coerce` first, then `validate`.

**Validation-failure policy (both providers):** numeric out of range -> clamp silently;
`maxItems` exceeded -> truncate; any remaining error (missing required, wrong type, minItems,
unknown enum value, JSON parse error) -> ONE corrective retry with the suffix
`"\n\nYour previous output failed validation: {errors}. Return only JSON matching the schema."`
appended to the prompt, then `LLMBadOutput`.

**Enum-bound references.** Whenever the valid id set is known at prompt time the schema uses
`enum`: `citations: arr(enum(shown_chunk_ids), 0, len(shown_chunk_ids))` (research, ideas);
`idea_id: enum(batch_ids)` (judges); `chunk_id: enum(candidate_ids)` (LLMReranker);
`parent_id: enum(top3_ids + ["new"])` (round >= 2 creativity); `technique: enum(TECHNIQUES)`;
criterion `name: enum(rubric.names())`. When the shown list is empty the field is
`arr(str_(), 0, 0)`. Code still drops unknown ids as defence in depth.

### 4.3 `llm/mock.py` — `MockLLM(seed: int = 0, scripted: dict[str, list[dict | str]] | None = None)`
- `provider = "mock"`, `model = "mock-1"`. Records every request in `self.calls: list[LLMRequest]`.
- `scripted` lookup: exact `request.tag`, then the prefix before `:`; entries are consumed FIFO
  (a `dict` entry becomes `data` and `text = json.dumps(data)`; a `str` entry is text; if a
  schema is given the dict is coerced+validated like any provider output).
- Otherwise synthesize from `json_schema` (no schema -> text `"[mock] {tag}: {words}"`).
  Seed: `rng = random.Random(int.from_bytes(hashlib.sha256(f"{seed}|{tag}|{prompt}".encode()).digest()[:8], "big"))`.
  `generate(schema, path)` where `path` is the JSON path including array indices
  (e.g. `ideas[3].title`):
  - strings: `f"[mock] {leaf}{idx}: {words}"`; `leaf` = last property name; `idx` = `#n` when
    inside an array (innermost index) else ""; `words` = 4 tokens drawn from the salient list
    by a per-path rng seeded from `sha256(f"{seed}|{tag}|{prompt}|{path}")`.
  - salient tokens = the 24 most frequent tokens of the prompt, ties broken alphabetically,
    using the mock's OWN tokenizer `re.findall(r"[a-z0-9]+", text.lower())` minus a tiny inline
    stopword list (never imports `knowledge.tokenize`). Fewer than 4 tokens -> pad with "mock".
  - numbers: midpoint of [minimum, maximum] (`integer` -> floor); unbounded -> 5 (number 5.0).
  - booleans: `False`. enums: `values[i % len(values)]` with `i` the innermost enclosing array
    index (0 at top level).
  - arrays: `n = minItems or 0; n = max(n, 2) unless maxItems is not None and maxItems < 2; n = min(n, maxItems) if maxItems is not None` — i.e. 2 when unbounded, exactly `k` when min==max==k, 0 when max==0.
  - `input_tokens = len(prompt)//4`, `output_tokens = len(text)//4`, `message_id = f"mock-{sha256(prompt)[:12]}"`, `request_id=None`, `stop_reason="end_turn"`.
- Consequences (tests rely on these): every criterion score is 3.0; `disqualified` is False;
  the idea loop runs exactly `max_iterations` rounds; `coverage_gaps` has 2 entries; enum
  arrays are permutations; all strings start with `[mock]`.

### 4.4 `llm/anthropic_provider.py` — `AnthropicLLM(model: str, fallbacks: bool = True, timeout: float = 600.0, client=None)`
- `import anthropic` lazily inside `__init__`; `ImportError` -> `LLMConfigError("anthropic package not installed", kind="config-fixable", hint='pip install "ideate[anthropic]"')`.
- Client: `client or anthropic.Anthropic(timeout=timeout)` — never pass `api_key`, never read env values.
- Call shape:
  ```python
  kwargs = dict(model=self.model, max_tokens=request.max_tokens, system=request.system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": request.effort, **({"format": {"type": "json_schema", "schema": for_api(schema)}} if schema else {})})
  if self.fallbacks: kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
  with self.client.beta.messages.stream(**kwargs) as s: message = s.get_final_message()
  ```
  Never send `temperature`, `top_p`, `top_k` or `thinking` (adaptive thinking is the default on Opus 5).
- Post-processing order: (1) `stop_reason == "refusal"` -> `sd = getattr(message, "stop_details", None)`; raise `LLMRefusal(getattr(sd, "category", None), getattr(sd, "explanation", None))`. (2) `stop_reason == "max_tokens"` with a schema -> `LLMBadOutput(f"output truncated at max_tokens={n}; raise IDEATE_MAX_TOKENS")`, no retry. (3) text = first content block with `type == "text"` (skip `fallback` and other blocks); none -> `LLMBadOutput`. (4) schema: `json.loads` -> `coerce` -> `validate` -> retry policy (§4.2).
- Response fields: `model = message.model` (served), `requested_model = self.model`,
  `message_id = message.id`, `request_id = getattr(message, "_request_id", None)`,
  `fallback_ran = any(getattr(e, "type", None) == "fallback_message" for e in (getattr(message.usage, "iterations", None) or [])) or message.model != self.model`,
  tokens from `message.usage.input_tokens/output_tokens`.
- Error chain (most-specific first): `AuthenticationError` -> `LLMConfigError(kind="do-it-myself", hint="set ANTHROPIC_API_KEY (or log in with the Anthropic CLI); ideate never prompts for or stores a key")`; `PermissionDeniedError` -> do-it-myself; `NotFoundError` -> config-fixable ("unknown model; set IDEATE_MODEL / --model"); `BadRequestError` -> config-fixable with the server message verbatim; `RateLimitError`, `InternalServerError`, `APIConnectionError`, `APITimeoutError` -> `LLMTransientError`; other `APIStatusError` -> transient if `status_code >= 500` else config-fixable; `anthropic.AnthropicError` catch-all -> `LLMConfigError(kind="do-it-myself" if "api_key" in str(e).lower() else "config-fixable")`.

### 4.5 `llm/factory.py`
- `resolve_provider(settings) -> str`: `settings.provider` if set; else `"anthropic"` if
  `"ANTHROPIC_API_KEY" in os.environ or "ANTHROPIC_AUTH_TOKEN" in os.environ` (presence only);
  else `"mock"`.
- `make_llm(settings) -> LLM`: `"mock"` -> `MockLLM(seed=settings.seed)`; `"anthropic"` ->
  `AnthropicLLM(settings.model, fallbacks=settings.fallbacks, timeout=settings.timeout)`;
  anything else -> `LLMConfigError(kind="config-fixable")`. An explicit `anthropic` NEVER falls
  back to mock. Prints one line to stderr: `ideate: provider={provider} model={model}`.

## 5. Knowledge layer
- `tokenize(text) -> list[str]`: lowercase; split on non-alphanumerics; drop tokens shorter
  than 2 chars; drop stopwords (inline list of ~120 English words); light stemming: apply the
  FIRST matching suffix rule once, in this order, only when the remainder has >= 3 chars:
  `ies->y`, `sses->ss`, `ing->""`, `ed->""`, `ly->""`, `es->""`, `s->""`.
- `split_document(doc, chunk_size=800, overlap=120) -> list[Chunk]`: split text into paragraphs
  (blank-line separated), greedily pack paragraphs into chunks <= chunk_size chars; a paragraph
  longer than chunk_size is split by sentences (`(?<=[.!?])\s+`) then by characters; overlap =
  last `overlap` chars of the previous chunk prepended (not for the first). `position` starts at
  0; `id = f"{doc.id}#{position}"`; `metadata = {"title", "source", "kind", "tags"}` copied from
  the document (`kind` default `"guidance"`).
- `BM25Index(k1=1.5, b=0.75)`: `add(chunk_id, text)`, `build()`, `search(query, k) -> list[tuple[str, float]]`
  (sorted by `(-score, id)`, zero-score chunks omitted), `to_dict()/from_dict()`, `__len__`.
  IDF = `log(1 + (N - n + 0.5) / (n + 0.5))`.
- `Embedder` Protocol: `name: str`, `dim: int`, `fit(texts) -> None`, `embed(texts) -> list[list[float]]`, `to_dict() -> dict`.
  `HashingEmbedder(dim=512)`: features = unigram tokens, bigrams (`a_b`), char 3-grams of each
  token with `#` padding (`#ab`, `abc`, `bc#`), each prefixed (`u:`, `b:`, `c:`); index =
  `int.from_bytes(blake2b(feature, digest_size=8).digest(), "big") % dim`; sign from the low bit
  of `blake2b(feature, digest_size=8, person=b"sign")`; weight = `(1 + log(tf)) * idf(feature)`;
  `fit` computes idf = `log((1 + N) / (1 + df)) + 1` (unseen -> 1.0); L2-normalized; all-zero ->
  zero vector. `to_dict() = {"name": "hashing", "dim", "idf": {...}}`; `embedder_from_dict(d)`.
- `VectorStore`: `add(id, vector)`, `search(vector, k) -> list[tuple[str, float]]` (cosine,
  sorted by `(-score, id)`), `to_dict()/from_dict()`, `__len__`.
- `reciprocal_rank_fusion(rankings: dict[str, list[str]], k: int = 60, weights: dict[str, float] | None = None) -> list[tuple[str, float]]`
  score = Σ w_s / (k + rank_s) with 1-based ranks; sorted by `(-score, id)`.
  `fuse_with_ranks(same args) -> list[tuple[str, float, dict[str, int]]]`.
- `Reranker` Protocol: `rerank(query, candidates: list[RetrievedChunk], top_n: int) -> list[RetrievedChunk]`
  returning NEW objects with `score = scores["rerank"]`, `ranks["rerank"]` = 1-based position,
  other keys copied. `LexicalOverlapReranker`: `0.6 * minmax(scores["rrf"] over candidates) + 0.4 * |query tokens ∩ chunk tokens| / |query tokens|`
  (minmax of a constant set -> 1.0; empty query tokens -> 0). `LLMReranker(llm)`: one call,
  tag `rerank`, schema `obj({"scores": arr(obj({"chunk_id": enum(ids), "relevance": num(0, 10)}), len(ids), len(ids))})`,
  `rerank score = relevance / 10`; on `LLMError` falls back to input order with `rerank` scores
  copied from `rrf`.
- `Retriever` Protocol: `retrieve(query: str, k: int = 8, candidates: int = 40, kind: str | None = None) -> list[RetrievedChunk]`.
  `HybridRetriever(chunks: dict[str, Chunk], bm25, vectors, embedder, reranker=None, bm25_weight=0.4, vector_weight=0.6, rrf_k=60)`:
  bm25 top-`candidates` and vector top-`candidates` (when `kind` is given both searches are
  exhaustive, `k=len(chunks)`, and filtered by `chunk.metadata.get("kind") == kind` before
  fusion); `fuse_with_ranks`; keep top `max(k * 3, 20)`; rerank (or identity when `reranker is
  None`, with `score` = rrf) to `k`. Empty index -> `[]`.
- `KnowledgeBase(chunks, bm25, vectors, embedder, reranker=None, bm25_weight=0.4, vector_weight=0.6, rrf_k=60)` satisfies `Retriever`:
  - `@classmethod build(cls, documents, *, embedder=None, chunk_size=800, overlap=120)`; default `HashingEmbedder(512)` fitted on chunk texts; `build([])` is valid.
  - `add_documents(documents) -> int` (chunk, `bm25.build()`, embed); `add_memory_patterns(patterns) -> int` (runtime only, see §7 for chunk shape).
  - `retrieve(...)`; `save(dir: Path)`; `@classmethod load(cls, dir)`; `stats() -> dict` (`n_docs`, `n_chunks`, `n_memory_chunks`, `embedder`, `dim`); attribute `reranker` settable; property `corpus_fingerprint`.
  - Files: `chunks.json`, `bm25.json`, `vectors.json`, `embedder.json`, `meta.json = {"format_version": 1, "embedder": {"name", "dim"}, "chunk_size", "chunk_overlap", "corpus_fingerprint", "n_docs", "n_chunks", "built_at"}`.
    `save` writes only chunks with `metadata["kind"] != "memory"`. Chunk dicts are written in sorted-id order; `vectors.json` is byte-identical across processes.
  - `corpus_fingerprint = sha256_hex("\n".join(f"{d.id}:{sha256_hex(d.text)}" for d in sorted(docs, key=lambda d: d.id)))`.
- `loaders.load_corpus(dirs: list[str | Path]) -> list[Document]`: for each dir (in order) walk
  recursively, sorted paths; `.md`/`.txt` -> one Document; files named `README.md` (case-insensitive)
  are skipped; optional front matter = a block delimited by `---` lines at the top with
  `key: value` pairs (`title`, `tags` comma-separated, `kind`, `source`, others -> metadata);
  `.json` (list of objects) / `.jsonl` -> objects with `title`, `text`, optional `source`, `kind`, `tags`.
  `id` = path relative to its corpus dir with `/` -> `__` and extension stripped (json items:
  `f"{fileid}__{n}"`). `kind` ∈ `guidance | data-source | archetype | antipattern | event | evidence`,
  default `guidance`. If two dirs yield the same id the later wins (warn on stderr). `source`
  missing on `kind: evidence` -> stderr warning. Title defaults to the first `# ` heading or the
  file stem.

## 6. Settings (`config.py`)
`@dataclass Settings` with `from_env(overrides: dict | None = None) -> Settings` (env prefix
`IDEATE_`, overrides win; ints/floats via `int()`/`float()`; bools accept `1/true/yes/on`
case-insensitively; list settings split on `|`; directory lists on `os.pathsep`) and
`to_dict()` (no secrets exist in Settings). Fields and defaults:
```
provider: str | None = None           # IDEATE_PROVIDER
model: str = DEFAULT_MODEL            # IDEATE_MODEL
effort: str = "high"                  # research/domain_expert/creativity/synthesizer
effort_light: str = "medium"          # orchestrator expansion, judges, rerank, learn, probe
max_tokens: int = 16000
fallbacks: bool = True
timeout: float = 600.0
corpus_dirs: list[str] = []           # IDEATE_CORPUS_DIRS (os.pathsep); extra dirs on top of the bundled one
bundled_corpus: bool = True           # IDEATE_BUNDLED_CORPUS
index_dir: str = ".ideate/index"
memory_path: str = ".ideate/memory.jsonl"
runs_dir: str = ".ideate/runs"
receipts_dir: str = ".ideate/receipts"
ideas_per_round: int = 8
accept_threshold: float = 3.8
min_strong_ideas: int = 3
max_iterations: int = 2
max_retrieval_rounds: int = 2
judge_personas: list[str] = [DEFAULT_PERSONAS...]   # IDEATE_JUDGE_PERSONAS, "|"-separated
chunk_size: int = 800; chunk_overlap: int = 120
retrieve_k: int = 8; retrieve_candidates: int = 40
embedding_dim: int = 512; bm25_weight: float = 0.4; vector_weight: float = 0.6; rrf_k: int = 60
reranker: str = "lexical"             # lexical | llm | none
seed: int = 0
verbose: bool = False
```
- `Settings.all_corpus_dirs() -> list[str]`: `[bundled_corpus_dir()] if bundled_corpus else []` + `corpus_dirs`, where `bundled_corpus_dir() = str(importlib.resources.files("ideate") / "corpus")`.
- `DEFAULT_PERSONAS = ["hackathon judge who has judged 50 events and rewards a demo that lands in 90 seconds", "senior engineer estimating what {team_size} people can ship in {hours} hours", "domain expert in {theme} who knows what already exists"]` — placeholders substituted from the state via `str.format_map` with a defaulting dict.

## 7. Memory (`memory/store.py`)
`MemoryStore(path: Path)`: JSONL, one record per line, exactly `{"type": "outcome", **outcome.to_dict()}` or `{"type": "pattern", **pattern.to_dict()}`; unknown `type` lines skipped with a stderr warning; missing file -> empty; parent dirs created on write.
Methods: `add_outcome(o)`, `add_pattern(p)`, `outcomes() -> list[Outcome]`,
`patterns(kind=None, include_mock=False) -> list[Pattern]`,
`relevant_patterns(query, kind=None, k=5, include_mock=False) -> list[Pattern]` (BM25 over
`text + " " + " ".join(tags)`, built on demand), `clear()`, `__len__`.
Records with `provider == "mock"` are excluded unless `include_mock`.
Memory chunks for the KB: `Chunk(id=f"memory#{pattern.id}", doc_id="memory", text=f"Past outcome lesson ({kind}): {text} (tags: {', '.join(tags)})", position=0, metadata={"title": f"Memory: {kind}", "source": "memory", "kind": "memory", "tags": tags})`.

## 8. Evaluation
### 8.1 `rubric.py`
`Criterion(name: str, weight: float, description: str, anchors: dict[int, str])` (anchor keys
exactly {1, 3, 5}; `from_dict` coerces keys with `int(k)`). `Rubric(criteria: list[Criterion])`:
`names()`, `weights() -> dict[str, float]`, `weighted_score(scores: dict[str, float]) -> float`
(delegates to scoring), `to_prompt(constraints: HackathonConstraints | None = None) -> str`
(substitutes `{hours}` / `{team_size}` in anchors), `to_dict()/from_dict()`.
`DEFAULT_RUBRIC` weights: novelty .30, feasibility .25, impact .25, demoability .20. Anchors:
- novelty 1 "exists as a common product or tutorial; judges have seen it at this event before"; 3 "known pattern with one real twist or a new domain"; 5 "judges have not seen this combination; the key innovation is one sentence and it IS the demo".
- feasibility 1 "needs more than {hours}h for {team_size} people, or depends on an account, signup or hardware the team lacks"; 3 "vertical slice buildable in ~60% of {hours}h with a plausible cut list"; 5 "walking skeleton demoable by 25% of {hours}h using named APIs/datasets that need no account".
- impact 1 "no concrete user named"; 3 "a named user with a named pain; benefit plausible"; 5 "a named user, a named pain, and a measurable before/after the demo can show".
- demoability 1 "needs a slide or explanation to be understood"; 3 "works live but the aha takes more than 90 seconds"; 5 "the demo moment lands in <= 90 seconds, has a recorded fallback, and needs no login".
`Rubric.from_judging_criteria(items: list[str]) -> Rubric`: each item is `name[:weight]`; keyword
table (case-insensitive substring): `innovation|novel|original|creativ -> novelty`,
`feasib|technical|complexity|execution -> feasibility`, `impact|value|useful|potential -> impact`,
`demo|presentation|pitch|polish -> demoability`, `design|ux|usability -> design`,
`business|market|viab -> business`; unknown items -> `Criterion(slug(text), weight, generic anchors)`;
default weight 1.0; duplicates merge (weights added); if feasibility is absent it is appended with
a weight that normalises to 15% of the total; empty list -> `DEFAULT_RUBRIC`.
### 8.2 `scoring.py`
`weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float` (weights normalised; missing criteria contribute 3.0); `median(values)`; `agreement(evals: list[IdeaEvaluation]) -> float = 1 - mean(pstdev per criterion) / 2` clamped 0..1 (single eval -> 1.0); `aggregate(evals, rubric) -> IdeaEvaluation` (per-criterion median, `judge="consensus"`, lists unioned/deduped keeping order, `disqualified` by majority, `disqualify_reason` = first non-empty, `closest_existing`/`demo_break_risk` = first non-empty).
### 8.3 `judge.py`
- `LLMJudge(llm, rubric, persona: str = "hackathon judge")`. Primary: `evaluate_many(ideas: list[Idea], context: str) -> list[IdeaEvaluation]` = ONE structured call, tag `judge:{slug(persona)}`, effort light, schema
  `obj({"evaluations": arr(obj({"idea_id": enum(ids), "scores": arr(obj({"name": enum(rubric.names()), "score": num(1, 5), "rationale": str_()}), n, n), "strengths": arr(str_(), 1, 4), "weaknesses": arr(str_(), 1, 4), "suggestions": arr(str_(), 1, 4), "risks": arr(str_(), 0, 4), "closest_existing": str_(), "demo_break_risk": str_(), "disqualified": bool_(), "disqualify_reason": str_()}), len(ids), len(ids))})`.
  Post-processing: duplicate idea_ids keep the first; missing idea_ids -> `LLMBadOutput` (after the provider's own retry); unknown criterion names dropped; missing criteria filled with `CriterionScore(name, 3.0, "[missing]")`; scores clamped; `weighted_score` from rubric; `judge = persona`. `evaluate(idea, context) = evaluate_many([idea], context)[0]`.
  System prompt: persona + rubric.to_prompt(constraints) + "score relative to the other ideas in this batch; disqualify ideas that violate must-avoid, need an account the team lacks, or cannot be demoed live".
- `PanelJudge(llm, rubric, personas: list[str])`: `evaluate_many(ideas, context) -> list[PanelVerdict]` (one call per persona; consensus via `aggregate`; `agreement`); `evaluate(idea, context)`.
- `compare_ideas(panel, ideas, context) -> tuple[list[PanelVerdict], list[str]]`: ranking = tier 1 non-disqualified with consensus feasibility > 2 sorted by `(-weighted_score, title)`; tier 2 non-disqualified with feasibility <= 2; tier 3 disqualified — a permutation of all idea ids. Ideas without a feasibility criterion count as feasibility 3.

## 9. Agents
### 9.1 `context.py`
- `TracingLLM(inner: LLM, trace: list[TraceStep], settings: Settings)` implements `LLM`:
  `provider`, `model` mirror inner; `complete()` records `started_at`, times the call, on success
  appends `TraceStep(agent=request.tag, provider=resp.provider, model=resp.model, requested_model=inner.model, prompt_sha256=sha256_hex(request.system + "\n" + request.prompt), input_tokens, output_tokens, duration_ms, request_id, started_at, stop_reason, error=None)`;
  on exception appends the same step with tokens 0 and `error=f"{type(e).__name__}: {e}"` then re-raises. `settings.verbose` -> one stderr line per call.
- Canonical tags (`LLMRequest.tag` == `TraceStep.agent`): `orchestrator`, `research`, `domain_expert`, `creativity`, `judge:<persona-slug>`, `rerank`, `synthesizer`, `learn`, `probe`.
- `RunContext(llm: TracingLLM, kb: KnowledgeBase, memory: MemoryStore, rubric: Rubric, settings: Settings, trace: list[TraceStep], queries_issued: list[str] = [])`:
  `request(tag, system, prompt, json_schema=None, effort=None) -> LLMRequest` (fills `max_tokens=settings.max_tokens`, `effort=effort or settings.effort`);
  `retrieve(query, k=None, kind=None) -> list[RetrievedChunk]` (delegates to `kb.retrieve(query, k=k or settings.retrieve_k, candidates=settings.retrieve_candidates, kind=kind)`, appends `query` to `queries_issued`).
- `constraints_block(c: HackathonConstraints) -> str` with the fixed format
  `Hours: {hours} | Team: {team_size} | Judging: {', '.join(criteria) or 'default rubric'} | Prefer: {', '.join(prefs) or '-'} | Must avoid: {', '.join(avoid) or '-'} | Tracks: {', '.join(tracks) or '-'}\nNotes: {notes or '-'}`.
  EVERY agent user prompt, the judge context and the synthesizer input include it verbatim.
- `knowledge_block(chunks: list[RetrievedChunk]) -> str`: numbered snippets `[C{n}] ({chunk.id}; {kind}; {title}) {text}`.
### 9.2 `base.py` / `graph.py`
`class Agent(ABC): name: str; def run(self, state: IdeationState, ctx: RunContext) -> IdeationState` (mutate in place, return the same object).
`Graph`: `add_node(agent)` keyed by `agent.name`; `add_edge(src, dst)`; `add_conditional_edge(src, fn: Callable[[IdeationState], str])`; a node has exactly one of the two (second -> `GraphError`); `set_entry(name)`; `END = "END"`; `run(state, ctx, max_steps=50) -> IdeationState` appends the node name to `state.visited` before invoking it; unknown node or `max_steps` exceeded -> `GraphError`; `settings.verbose` -> `node_start`/`node_end` stderr lines.
### 9.3 `build_default_graph(settings) -> Graph`
`orchestrator -> research -> retrieve_more -> (cond A) -> domain_expert -> creativity -> evaluator -> (cond B) -> synthesizer -> END`
- cond A: `"research"` if `state.retrieve_more_added >= 1` AND `state.retrieval_rounds < settings.max_retrieval_rounds`, else `"domain_expert"`. (`IdeationState.retrieve_more_added: int = 0` is set by `RetrieveMoreAgent` each time it runs.)
- cond B: `strong = [v for v in state.verdicts if not v.consensus.disqualified and v.consensus.weighted_score >= settings.accept_threshold]`; `"creativity"` if `len(strong) < settings.min_strong_ideas and state.iteration < settings.max_iterations`, else `"synthesizer"`. This is the ONLY loop rule.
Conditional functions are closures over `settings`.
### 9.4 Agent contracts
- **OrchestratorAgent** (`orchestrator`): one call, effort light, schema `obj({"queries": arr(str_(), 1, 6)})`: expand the theme into search queries, one per judging criterion and per tech preference; `state.queries = [theme] + expansions` (dedup, keep order). Retrieve `ctx.retrieve(q)` for each; merge by chunk id keeping the best score; then pin all `event` chunks (`ctx.retrieve(theme, k=8, kind="event")`) and at least 4 `data-source` chunks (`ctx.retrieve(theme + " " + " ".join(tech_preferences), k=4, kind="data-source")`) regardless of score; cap at 20 by dropping lowest-score non-pinned chunks; sort by `(-score, id)`. `state.memory_context = memory_context_for(theme, ctx.memory, include_mock=ctx.llm.provider == "mock")`.
- **ResearchAgent** (`research`): increments `state.retrieval_rounds` on entry; one call, effort high, input = constraints_block + knowledge_block; schema `obj({"trends": arr(str_(), 1, 5), "case_studies": arr(str_(), 0, 5), "pitfalls": arr(str_(), 1, 5), "opportunities": arr(str_(), 1, 5), "citations": arr(enum(ids), 0, len(ids)), "coverage_gaps": arr(str_(), 0, 4)})`. Prompt rule: "If the snippets do not cover something you need, list it in coverage_gaps and write 'no evidence in knowledge base' in the relevant bullet — never invent case studies or statistics." Unknown citation ids dropped.
- **RetrieveMoreAgent** (`retrieve_more`, no LLM): for each gap in `state.research.coverage_gaps[:4]`: `ctx.retrieve(gap, k=4)`; append chunks not already in `state.knowledge`; cap total at 24 (drop lowest-score non-pinned extras); `state.coverage_gaps = gaps`; `state.retrieve_more_added = number added`.
- **DomainExpertAgent** (`domain_expert`): one call, effort high; input = constraints_block + research + data-source chunks; schema with `constraints, required_skills, challenges, breakthroughs, suggested_stack: arr(str_(), 1, 6)`, `building_blocks: arr(str_(), 1, 8)`, `hour_budget: arr(str_(), 3, 6)`.
- **CreativityAgent** (`creativity`): increments `state.iteration` on entry; ids `idea-{iteration}-{n}`; APPENDS to `state.ideas`. Schema `obj({"ideas": arr(IDEA_SCHEMA, n, n)})`, n = `settings.ideas_per_round`; `IDEA_SCHEMA` fields: title, one_liner, description, target_user, key_innovation, `technique: enum(TECHNIQUES)`, technical_approach, demo_strategy, demo_moment, `data_sources: arr(str_(), 1, 4)`, `mvp_scope: arr(str_(), 1, 5)`, `cut_first: arr(str_(), 1, 4)`, closest_existing, `build_hours_estimate: int_(1, constraints.hours)`, `risks: arr(str_(), 1, 4)`, `citations: arr(enum(ids), 0, len(ids))`, plus `parent_id: enum(top3_ids + ["new"])` in round >= 2 (`"new"` -> `None`). Prompt: cycle the techniques (idea k uses `TECHNIQUES[k % 6]`), constraints_block, memory_context (leverage/avoid), `building_blocks` as the resource menu, antipattern chunks as "do not produce unless you state the twist", require >= 4 distinct target_users and >= 3 distinct primary data_sources across the batch, each idea cites >= 1 shown chunk; ideas using anything in Must avoid are invalid. Round >= 2: also the top-3 ideas (title, one_liner, consensus weaknesses/suggestions) and `state.critiques`; roughly half refine a top-3 idea (`parent_id`, must state what changed) and half are new.
  `validate_idea(idea, constraints) -> list[str]` flags: `target_user` empty or in `GENERIC_USERS = {"users","people","businesses","everyone","companies","students","developers","consumers"}` (lowercased, stripped); `data_sources` empty; `demo_moment` fewer than 4 whitespace tokens; `build_hours_estimate > hours`; any must_avoid term (tokenized) appearing in tokenized title/description/technical_approach. On any violation: ONE retry of the whole creativity call with the violations appended; keep survivors; never loop further; fewer than 1 survivor -> `LLMBadOutput`. Diversity: token-Jaccard over `title + " " + one_liner` (mock-style tokenizer `[a-z0-9]+`) > 0.6 against ANY earlier idea (previous rounds included) -> drop the later one. Truncate to n.
- **EvaluatorAgent** (`evaluator`): `PanelJudge(ctx.llm, ctx.rubric, personas=[p.format_map(Defaulting(hours, team_size, theme)) for p in settings.judge_personas])`; judges only ideas without a verdict (verdicts keyed by `idea_id`); context = constraints_block + assessment (challenges, building_blocks, hour_budget) + top research bullets; recomputes `state.ranking` over ALL ideas via `compare_ideas` semantics; replaces `state.critiques` with, for each top-3 idea, its consensus weaknesses plus `"lowest criterion: {name}"`, deduped, <= 9 entries.
- **SynthesizerAgent** (`synthesizer`): one call, effort high; input = top-3 ideas + their consensus verdicts + assessment + constraints_block; schema = Proposal minus `idea_id`, with `alternatives: arr(obj({"idea_id": enum(ranking[1:3]), "choose_if": str_()}), 0, 2)` (or `arr(str_(),0,0)`-style empty when fewer than 2 runner-ups), `first_hour_plan: arr(str_(), 3, 8)`, `milestones: arr(str_(), 3, 6)`, `team_split: arr(str_(), 1, 6)`, `cut_list: arr(str_(), 1, 6)`, `human_dependencies: arr(str_(), 0, 6)`, `demo_script: arr(str_(), 3, 10)`. Prompt requires: first_hour_plan begins with create repo + push + confirm git-triggered deploy gives a public URL; stub the demo path end to end with fake data; hand every human dependency to a human now; milestones templated from hours (h0–1 first hour; by 25% walking skeleton with public URL; by 60% demo path end to end; at 80% feature freeze; last 10% rehearse + record fallback); team_split always names an integration owner and a demo owner; human_dependencies each prefixed with a blocker kind. Code sets `proposal.idea_id = state.ranking[0]`.

## 10. Improvement loop (`improvement/feedback.py`)
- `learn_from_outcome(outcome: Outcome, llm: LLM, memory: MemoryStore, now: Callable[[], str] | None = None) -> list[Pattern]`: one call, tag `learn`, effort light, schema `obj({"patterns": arr(obj({"kind": enum(["success","failure"]), "text": str_(), "tags": arr(str_(), 1, 5)}), 1, 6)})`; prompt asks for leverage/avoid rules about scope, demo and data sources; tags always include `outcome.hackathon`; `Pattern.provider = response.provider`, `created_at = now()`, `source_outcome_id = outcome.id`; persists outcome (if not already present by id) and patterns; returns patterns.
- `memory_context_for(theme, memory, k=5, include_mock=False) -> str`: bullets `Leverage: …` (success) / `Avoid: …` (failure) from `relevant_patterns`; `""` when none.

## 11. Pipeline facade (`pipeline.py`)
`IdeationSystem(settings: Settings | None = None, llm: LLM | None = None, now: Callable[[], str] | None = None)`.
- `ideate(theme, constraints=None) -> IdeationResult`, in order: `llm = self.llm or make_llm(settings)`; `is_mock = llm.provider == "mock"`; `kb = load_or_build_index()`; `kb.add_memory_patterns(memory.patterns(include_mock=is_mock))`; `rubric = Rubric.from_judging_criteria(constraints.judging_criteria)`; `trace = []`; `ctx = RunContext(TracingLLM(llm, trace, settings), kb, memory, rubric, settings, trace)`; if `settings.reranker == "llm"`: `kb.reranker = LLMReranker(ctx.llm)`; `"none"` -> `kb.reranker = None`; `state = IdeationState(theme, constraints)`; `build_default_graph(settings).run(state, ctx)`; `IdeationResult.from_state(state, ctx, settings, run_id=uuid4().hex[:12], created_at=now())`, `queries = ctx.queries_issued`.
- `judge(ideas, theme, constraints=None) -> tuple[list[PanelVerdict], list[str]]` (assigns `idea-0-{n}` when `id` empty).
- `learn(outcome) -> list[Pattern]`; `probe() -> dict` (touches only the llm: `LLMConfigError("probe requires a real provider; current provider is mock", kind="config-fixable", hint="set IDEATE_PROVIDER=anthropic and credentials")` under mock; otherwise one call, tag `probe`, schema `obj({"ok": bool_(), "model_self_report": str_()})`, returns `{provider, requested_model, served_model, fallback_ran, message_id, request_id, input_tokens, output_tokens, stop_reason, timestamp}`).
- `build_index(force=False) -> KnowledgeBase`; `load_or_build_index()`: load only when `meta.format_version == 1`, fingerprint matches the current corpus, embedder name/dim and chunk params match settings; otherwise rebuild, save, and print one stderr line.
- `save_run(result) -> Path`: `.ideate/runs/<run_id>/result.json` + `report.md`.
- `save_receipt(receipt) -> Path`: `.ideate/receipts/probe-<UTC timestamp>.json` (only ever called with a real-provider receipt).

## 12. Report (`report.py`)
`PLACEHOLDER_BANNER = "PROVIDER: mock — placeholder content, not evidence"`.
`render_markdown(result) -> str`: when `is_placeholder` the first line is exactly
`> **PROVIDER: mock — placeholder content, not evidence**` followed by a blank line. Sections in
order: (1) "Build this" — title, one_liner, target_user, demo_moment, why_this, closest_existing;
(2) First hour (numbered); (3) Milestones, team split, cut list, pivot trigger; (4) Human
dependencies; (5) Runner-ups with "choose instead if …"; (6) All-ideas table (title, technique,
weighted, feasibility, agreement, disqualified) in ranking order; (7) Per-idea detail;
(8) Knowledge gaps and sources cited; (9) Trace summary (calls, tokens, served models).
`render_json(result) -> str` = `json.dumps(d, indent=2, sort_keys=True)` where `d = result.to_dict()` plus `"placeholder_notice": PLACEHOLDER_BANNER` when placeholder.

## 13. CLI (`cli.py`, argparse; `main(argv=None) -> int`)
Subcommands:
- `ideate index [--corpus DIR]... [--no-bundled-corpus] [--index DIR] [--force]` — prints stats to stderr; warns "0 documents loaded" when empty.
- `ideate run THEME [--hours 24] [--team 3] [--criteria "innovation:40,impact:30,demo:30"] [--prefer a,b] [--avoid a,b] [--tracks a,b] [--notes-file event.md] [--ideas 8] [--out report.md] [--json result.json|-] [--provider mock|anthropic] [--model ID] [--reranker lexical|llm|none] [--corpus DIR]... [--no-bundled-corpus] [--index DIR] [--verbose]` — always writes the run dir; prints the markdown report to stdout only when neither `--out` nor `--json` is given.
- `ideate judge IDEAS.json --theme THEME [--hours --team --criteria --json]` — items may be full Idea dicts or `{title, description}`.
- `ideate learn OUTCOME.json [--run RUN_ID --idea IDEA_ID]` — prefills from the saved run; under mock prints to stderr "provider is mock: patterns saved with provider=mock and ignored by real runs".
- `ideate memory [--kind success|failure] [--include-mock]` — mock rows are marked `[mock]`.
- `ideate probe` — writes the receipt file and prints its path.
Exit codes: 0 ok; 1 other errors (`LLMBadOutput`, `GraphError`, IO); 2 `LLMConfigError` printed to stderr as `blocker ({kind}): {message}\n  fix: {hint}`; 3 `LLMTransientError`; 4 `LLMRefusal` printed as `blocker (genuinely human-only): refusal category={category!r}: {explanation or 'no explanation'}`.
All notices/warnings go to stderr; stdout carries only report/JSON.

## 14. Corpus seeds (`src/ideate/corpus/`) — hand-written guidance, no invented statistics or fake case studies
Front matter contract (also in `corpus/README.md`):
```
---
title: Demo strategy for hackathons
tags: demo, pitch, judging
kind: guidance          # guidance | data-source | archetype | antipattern | event | evidence
source: (required for kind: evidence)
---
```
Files: `judging-criteria.md`, `demo-strategy.md`, `scoping-24h-48h.md`, `failure-modes.md`,
`deploy-and-webhooks.md` (git-triggered deploy gives a public URL and webhook receiver early;
mocks vs real calls), `pitch-structure.md`, `idea-techniques.md`, `team-roles.md`,
`ai-agent-project-patterns.md`, `public-data-and-apis.md` (kind `data-source`; well-known free
public APIs/datasets grouped by domain, each with an `access: none | free key | account` line and
what it provides — names only, no statistics), `project-archetypes.md` (kind `archetype`),
`generic-idea-antipatterns.md` (kind `antipattern`), `event/README.md` (skipped by loader; explains
dropping event page / sponsor docs / rubric with `kind: event`).

## 15. Claude Code skill (`.claude/skills/ideate/SKILL.md`)
Front matter `name: ideate`; description: "Generate, judge and refine hackathon project ideas with the ideation system (hybrid RAG + multi-agent + LLM-judge panel + outcome memory). Use when the user asks for hackathon ideas, to evaluate ideas, or to record a hackathon outcome."
Body: (1) locate `ideation/` at the repo root, else install `pip install "ideate[anthropic] @ git+https://github.com/phazon2/hack-template@claude/hackathon-ideation-system-hlsks3#subdirectory=ideation"`; (2) parse hours/team/criteria/prefer/avoid/tracks/notes from the user's message and run `ideate run "<theme>" ... --out IDEAS.md --json .ideate/last.json`; (3) if the provider resolves to mock, say so plainly and label the output as placeholder; never present mock output as evidence; (4) offer `ideate learn` after the event; (5) never handle credentials — a missing key is a `do-it-myself` step for the user.

## 16. CI (`.github/workflows/ideation-ci.yml`)
Trigger on push/pull_request with `paths: [ideation/**, .github/workflows/ideation-ci.yml]`; matrix python 3.11 and 3.12; steps: checkout, setup-python, `pip install -e "ideation[dev]"`, `pytest ideation/tests -q`. Nothing else. Comment in the file: `# mock output is not evidence — never upload or commit anything generated here (CLAUDE.md: Evidence discipline)`. No `upload-artifact`, no `ideate probe`, no report files.

## 17. Testing standards
- No network, ever. `tests/conftest.py` inserts `<ideation>/src` at the front of `sys.path`; fixtures: `settings(tmp_path)` (mock provider, tmp index/memory/runs/receipts), `mock_llm`, `kb` (built from the bundled corpus, session-scoped).
- CLI tests: `subprocess.run([sys.executable, "-m", "ideate", ...], env={**os.environ, "PYTHONPATH": SRC, "IDEATE_PROVIDER": "mock", "IDEATE_INDEX_DIR": ..., "IDEATE_MEMORY_PATH": ..., "IDEATE_RUNS_DIR": ..., "IDEATE_RECEIPTS_DIR": ...})`.
- Determinism rules: never `hash()` on str/bytes; never iterate a `set` for ordered output (use `dict.fromkeys`/`sorted`); ranked outputs sort by `(-score, id)`; wall-clock inputs injectable (`now`).
  Tests: (a) MockLLM same input -> identical; different tag -> different; (b) pipeline run twice in-process -> identical `to_dict()` after zeroing `duration_ms`, `started_at`, `created_at`, `run_id`, `recorded_at`; (c) `python -m ideate run ... --json -` twice with different `PYTHONHASHSEED` -> identical after the same exclusions; (d) index built twice in separate processes -> identical `vectors.json` bytes.
- Anthropic fake client: `client.beta.messages.stream(**kwargs)` records kwargs and returns an object with `__enter__/__exit__` and `get_final_message()` returning `SimpleNamespace(id="msg_test", model="claude-opus-5", stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text=json_str)], usage=SimpleNamespace(input_tokens=1, output_tokens=1, iterations=None), _request_id="req_test")`. Required assertions: no `temperature/top_p/top_k/thinking` keys; `output_config["effort"]` present; `output_config["format"]["type"] == "json_schema"`; stripped keys absent from the sent schema; `betas`/`fallbacks` present iff fallbacks on; refusal fake (`stop_details=SimpleNamespace(category="cyber", explanation=None)`) raises `LLMRefusal`; a leading `fallback` block still yields the first text block; `model="claude-opus-4-8"` sets `fallback_ran` and `LLMResponse.model` to the served model; `stop_reason="max_tokens"` raises `LLMBadOutput`; missing package path raises `LLMConfigError` (monkeypatch import).
- E2E under default mock + default settings (bundled corpus): `result.iterations == settings.max_iterations`; `len(result.ideas) == settings.ideas_per_round * result.iterations`; a verdict for every idea; `ranking` is a permutation of idea ids; `result.proposal.idea_id == result.ranking[0]`; `is_placeholder` True; markdown first line is the banner and JSON has `placeholder_notice`; `len(result.trace) == 1 + result.retrieval_rounds + 1 + result.iterations * (1 + len(settings.judge_personas)) + 1`; every `TraceStep.agent` in the canonical tag set; every idea has >= 1 citation; every mock idea passes `validate_idea` and the diversity filter.
- Scripted-mock tests: accept branch (all scores 5 -> exactly one round); corrective-RAG re-run (gaps whose retrieval adds chunks -> 2 research calls) vs no re-run (empty gaps -> 1); `LLMReranker` fallback on `LLMError`; mock patterns invisible to `patterns()`/`relevant_patterns()` by default; `for_api` stripping; `save` excludes memory chunks; `Rubric.from_judging_criteria("innovation,impact")` appends feasibility at 15%; every criterion has anchors {1,3,5}; `arr(str_(), 8, 8)` mock yields 8 distinct strings.
