"""Command-line interface (docs/DESIGN.md §13).

stdout carries only reports / JSON; every notice goes to stderr. Exit codes: 0 ok, 1 other
errors, 2 config blockers, 3 transient provider errors, 4 refusals.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from ideate import __version__
from ideate.agents.graph import GraphError
from ideate.config import Settings, SettingsError
from ideate.llm.base import LLMConfigError, LLMError, LLMRefusal, LLMTransientError
from ideate.llm.factory import resolve_provider
from ideate.meta.charter import DEFAULT_CHARTER, load_charter, save_charter
from ideate.meta.fetch import FetchError, fetch_arxiv, fetch_url, write_docs
from ideate.meta.gaps import collect_gaps, render_gaps
from ideate.meta.ingest import ingest_into
from ideate.meta.frames import FrameError, FramesToolMissing, extract_frames, render_index
from ideate.meta.video import VideoToolMissing, fetch_transcript
from ideate.models import (
    HUMAN_CONFIDENCE,
    HUMAN_PROVIDER,
    META_PATTERN_KINDS,
    HackathonConstraints,
    Idea,
    MetaPattern,
    Outcome,
)
from ideate.pipeline import RESULT_FILE, IdeationSystem, load_result
from ideate.report import (
    PLACEHOLDER_BANNER,
    judgement_dict,
    reflection_dict,
    render_json,
    render_judgement,
    render_markdown,
    render_reflection,
    render_strategy,
    strategy_dict,
)

MOCK_PROVIDER = "mock"
STDOUT = "-"
EXIT_OK, EXIT_ERROR, EXIT_CONFIG, EXIT_TRANSIENT, EXIT_REFUSAL = 0, 1, 2, 3, 4
LEARN_MOCK_NOTICE = "provider is mock: patterns saved with provider=mock and ignored by real runs"


def notice(message: str) -> None:
    """One ``ideate: ...`` line on stderr."""
    print(f"ideate: {message}", file=sys.stderr)


def csv(value: str | None) -> list[str]:
    """Split a comma-separated flag value into stripped, non-empty items."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def read_json(path: str) -> object:
    """Parse a JSON file (a ``ValueError`` names the file on failure)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: invalid JSON ({e.msg} at line {e.lineno})") from e


def write_text(path: str, text: str) -> None:
    """Write ``text`` to ``path`` (parent dirs created) or to stdout when ``path`` is ``-``."""
    if path == STDOUT:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    notice(f"written {target}")


# --------------------------------------------------------------------------- argument parsing
def _add_provider_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--provider", choices=["mock", "anthropic"], help="LLM provider (default: IDEATE_PROVIDER or auto)")
    p.add_argument("--model", help="model id (default: IDEATE_MODEL)")
    p.add_argument("--verbose", action="store_true", help="log every node and LLM call to stderr")


def _add_corpus_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus", action="append", metavar="DIR", help="extra corpus directory (repeatable)")
    p.add_argument("--no-bundled-corpus", action="store_true", help="do not load the bundled corpus")
    p.add_argument("--index", metavar="DIR", help="index directory (default: IDEATE_INDEX_DIR or .ideate/index)")


def _add_constraint_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--hours", type=int, default=24, help="hackathon length in hours")
    p.add_argument("--team", type=int, default=3, help="team size")
    p.add_argument("--criteria", help='judging criteria, e.g. "innovation:40,impact:30,demo:30"')


def _add_theme_options(p: argparse.ArgumentParser) -> None:
    """The free-text constraint flags shared by ``run`` and ``strategy``."""
    p.add_argument("--prefer", help="comma-separated technology preferences")
    p.add_argument("--avoid", help="comma-separated things to avoid")
    p.add_argument("--tracks", help="comma-separated event tracks")
    p.add_argument("--notes-file", help="file whose text becomes the constraints notes")


def build_parser() -> argparse.ArgumentParser:
    """The argparse parser with every subcommand and flag."""
    parser = argparse.ArgumentParser(prog="ideate", description="Hackathon ideation system.")
    parser.add_argument("--version", action="version", version=f"ideate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="build or refresh the knowledge index")
    _add_corpus_options(p_index)
    p_index.add_argument("--force", action="store_true", help="rebuild even when the saved index is still valid")
    _add_provider_options(p_index)
    p_index.set_defaults(handler=cmd_index)

    p_run = sub.add_parser("run", help="generate, judge and refine ideas for a theme")
    p_run.add_argument("theme")
    _add_constraint_options(p_run)
    _add_theme_options(p_run)
    p_run.add_argument("--ideas", type=int, help="ideas per round (default: IDEATE_IDEAS_PER_ROUND or 8)")
    p_run.add_argument("--no-strategist", action="store_true", help="skip the strategist and use the default process")
    p_run.add_argument("--no-reflector", action="store_true", help="skip the reflector and write nothing to meta memory")
    p_run.add_argument("--out", metavar="FILE", help="write the markdown report here")
    p_run.add_argument("--json", metavar="FILE", help="write the JSON result here ('-' for stdout)")
    p_run.add_argument("--reranker", choices=["lexical", "llm", "none"], help="retrieval reranker")
    _add_corpus_options(p_run)
    _add_provider_options(p_run)
    p_run.set_defaults(handler=cmd_run)

    p_judge = sub.add_parser("judge", help="judge ideas from a JSON file")
    p_judge.add_argument("ideas_file", metavar="IDEAS.json")
    p_judge.add_argument("--theme", required=True)
    _add_constraint_options(p_judge)
    p_judge.add_argument("--json", metavar="FILE", help="write the JSON verdicts here ('-' for stdout)")
    _add_provider_options(p_judge)
    p_judge.set_defaults(handler=cmd_judge)

    p_learn = sub.add_parser("learn", help="record a hackathon outcome and learn patterns from it")
    p_learn.add_argument("outcome_file", metavar="OUTCOME.json")
    p_learn.add_argument("--run", metavar="RUN_ID", help="prefill from this saved run")
    p_learn.add_argument("--idea", metavar="IDEA_ID", help="the idea of that run that was built (default: its top-ranked idea)")
    _add_provider_options(p_learn)
    p_learn.set_defaults(handler=cmd_learn)

    p_memory = sub.add_parser("memory", help="list learned patterns")
    p_memory.add_argument("--kind", choices=["success", "failure"])
    p_memory.add_argument("--include-mock", action="store_true", help="also list patterns learned under the mock")
    p_memory.add_argument("--verbose", action="store_true", help=argparse.SUPPRESS)
    p_memory.set_defaults(handler=cmd_memory)

    p_ingest = sub.add_parser("ingest", help="normalise and register an external memory source")
    p_ingest.add_argument("path", metavar="PATH")
    p_ingest.add_argument("--kind", choices=["external", "ideate"], default="external", help="how to read the source")
    p_ingest.add_argument("--title", help="title for the source (default: the file or directory name)")
    p_ingest.add_argument("--reindex", action="store_true", help="rebuild the index so the material is retrievable now")
    _add_corpus_options(p_ingest)
    p_ingest.add_argument("--verbose", action="store_true", help=argparse.SUPPRESS)
    p_ingest.set_defaults(handler=cmd_ingest)

    p_strategy = sub.add_parser("strategy", help="plan how to approach a theme (one call, no ideas)")
    p_strategy.add_argument("theme")
    _add_constraint_options(p_strategy)
    _add_theme_options(p_strategy)
    p_strategy.add_argument("--json", metavar="FILE", help="write the JSON plan here ('-' for stdout)")
    _add_corpus_options(p_strategy)
    _add_provider_options(p_strategy)
    p_strategy.set_defaults(handler=cmd_strategy)

    p_reflect = sub.add_parser("reflect", help="reflect on a saved run and record what the system learned")
    p_reflect.add_argument("--run", metavar="RUN_ID", required=True, help="the saved run to reflect on")
    p_reflect.add_argument("--json", metavar="FILE", help="write the JSON reflection here ('-' for stdout)")
    _add_corpus_options(p_reflect)
    _add_provider_options(p_reflect)
    p_reflect.set_defaults(handler=cmd_reflect)

    p_meta = sub.add_parser("meta", help="list meta-patterns or ingested memory sources")
    p_meta.add_argument("--kind", choices=["strategy", "process", "pitfall"])
    p_meta.add_argument("--scope", metavar="S", help="'global' or a problem type")
    p_meta.add_argument("--sources", action="store_true", help="list ingested memory sources instead")
    p_meta.add_argument("--include-mock", action="store_true", help="also list rows produced under the mock")
    p_meta.add_argument("--verbose", action="store_true", help=argparse.SUPPRESS)
    p_meta.set_defaults(handler=cmd_meta)

    p_note = sub.add_parser("note", help="file a correction or lesson instantly (no LLM call)")
    p_note.add_argument("text", metavar="TEXT")
    p_note.add_argument("--kind", choices=list(META_PATTERN_KINDS), default="correction")
    p_note.add_argument("--tags", default="", help="comma-separated tags")
    p_note.add_argument("--scope", default="global", help="'global' or a problem type")
    p_note.set_defaults(handler=cmd_note)

    p_charter = sub.add_parser("charter", help="show or replace the standing charter")
    p_charter.add_argument("--set", metavar="FILE", dest="set_file", help="replace the charter with this file")
    p_charter.add_argument("--init", action="store_true", help="write the bundled default charter so you can edit it")
    p_charter.set_defaults(handler=cmd_charter)

    p_fetch = sub.add_parser("fetch", help="fetch papers or a page into the corpus as cited evidence")
    p_fetch.add_argument("url", metavar="URL", nargs="?", help="an http(s) page to fetch")
    p_fetch.add_argument("--arxiv", metavar="QUERY", help="search arXiv instead of fetching a URL")
    p_fetch.add_argument("--max", type=int, default=5, metavar="N", help="arXiv results (default 5)")
    p_fetch.add_argument("--reindex", action="store_true", help="rebuild the index so it is retrievable now")
    _add_corpus_options(p_fetch)
    p_fetch.set_defaults(handler=cmd_fetch)

    p_frames = sub.add_parser("frames", help="extract frames from a local video so an agent can see it")
    p_frames.add_argument("path", metavar="VIDEO")
    p_frames.add_argument("--out", metavar="DIR", default=".ideate/frames", help="where to write frames")
    p_frames.add_argument("--max-frames", type=int, default=24, metavar="N")
    p_frames.add_argument("--start", type=float, metavar="SEC", help="only from this second")
    p_frames.add_argument("--end", type=float, metavar="SEC", help="only up to this second")
    p_frames.add_argument("--width", type=int, default=512, metavar="PX")
    p_frames.set_defaults(handler=cmd_frames)

    p_gaps = sub.add_parser("gaps", help="what the knowledge base is missing, and the command to fill it")
    p_gaps.add_argument("--max", type=int, default=5, metavar="N", help="results per suggested fetch")
    p_gaps.add_argument("--include-placeholder", action="store_true", help="also use mock runs' gaps")
    p_gaps.set_defaults(handler=cmd_gaps)

    p_watch = sub.add_parser("watch", help="pull a video's transcript into the corpus as cited evidence")
    p_watch.add_argument("url", metavar="URL")
    p_watch.add_argument("--lang", default="en", help="caption language (default en)")
    p_watch.add_argument("--reindex", action="store_true", help="rebuild the index so it is retrievable now")
    _add_corpus_options(p_watch)
    p_watch.set_defaults(handler=cmd_watch)

    p_probe = sub.add_parser("probe", help="make one real call and write a receipt")
    _add_provider_options(p_probe)
    p_probe.set_defaults(handler=cmd_probe)
    return parser


def settings_from(args: argparse.Namespace) -> Settings:
    """``Settings.from_env`` with the flags of ``args`` as overrides (flags win over env)."""
    overrides = {
        "provider": getattr(args, "provider", None),
        "model": getattr(args, "model", None),
        "verbose": True if getattr(args, "verbose", False) else None,
        "reranker": getattr(args, "reranker", None),
        "corpus_dirs": getattr(args, "corpus", None),
        "bundled_corpus": False if getattr(args, "no_bundled_corpus", False) else None,
        "index_dir": getattr(args, "index", None),
        "ideas_per_round": getattr(args, "ideas", None),
        "strategist": False if getattr(args, "no_strategist", False) else None,
        "reflector": False if getattr(args, "no_reflector", False) else None,
    }
    return Settings.from_env(overrides)


def constraints_from(args: argparse.Namespace) -> HackathonConstraints:
    """Build ``HackathonConstraints`` from the run/judge flags."""
    notes_file = getattr(args, "notes_file", None)
    return HackathonConstraints(
        hours=args.hours,
        team_size=args.team,
        judging_criteria=csv(args.criteria),
        tech_preferences=csv(getattr(args, "prefer", None)),
        must_avoid=csv(getattr(args, "avoid", None)),
        tracks=csv(getattr(args, "tracks", None)),
        notes=Path(notes_file).read_text(encoding="utf-8").strip() if notes_file else "",
    )


# --------------------------------------------------------------------------- commands
def cmd_index(args: argparse.Namespace) -> int:
    """``ideate index``: build or load the index and print its stats to stderr."""
    settings = settings_from(args)
    kb = IdeationSystem(settings).build_index(force=args.force)
    stats = kb.stats()
    if stats["n_docs"] == 0:
        notice("warning: 0 documents loaded (check --corpus / IDEATE_CORPUS_DIRS)")
    notice(
        f"index {settings.index_dir}: {stats['n_docs']} docs, {stats['n_chunks']} chunks, "
        f"embedder {stats['embedder']}/{stats['dim']}"
    )
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """``ideate run``: ideate, always save the run dir, then emit the report/JSON as requested."""
    settings = settings_from(args)
    system = IdeationSystem(settings)
    result = system.ideate(args.theme, constraints_from(args))
    run_dir = system.save_run(result)
    patterns = system.meta_patterns_for(result.run_id, include_mock=result.is_placeholder)
    notice(f"run {result.run_id} saved to {run_dir}")
    if result.reflection is not None:
        notice(f"reflection recorded in {settings.meta_path} ({len(patterns)} new meta-pattern(s))")
    if result.is_placeholder:
        notice(PLACEHOLDER_BANNER)
    if args.out:
        write_text(args.out, render_markdown(result, patterns))
    if args.json:
        write_text(args.json, render_json(result))
    if not args.out and not args.json:
        sys.stdout.write(render_markdown(result, patterns))
    return EXIT_OK


# --------------------------------------------------------------------------- meta layer (DESIGN-META §18.6)
def cmd_ingest(args: argparse.Namespace) -> int:
    """``ideate ingest``: normalise and register a memory source; the source id goes to stdout."""
    settings = settings_from(args)
    system = IdeationSystem(settings)
    path = Path(args.path)
    before = system.meta.source_for(str(path))
    source, _ = ingest_into(path, system.meta, kind=args.kind, title=args.title)
    unchanged = before is not None and before.fingerprint == source.fingerprint
    notice(
        f"{'unchanged' if unchanged else 'ingested'} {source.path}: {source.format}, "
        f"{source.n_records} record(s), {source.n_documents} document(s)"
    )
    if args.reindex:
        system.build_index(force=True)
    elif not unchanged:
        notice("run 'ideate index' (or pass --reindex) to make this retrievable")
    print(source.id)
    return EXIT_OK


def cmd_strategy(args: argparse.Namespace) -> int:
    """``ideate strategy``: run the strategist alone and print the plan."""
    settings = settings_from(args)
    strategy = IdeationSystem(settings).strategy(args.theme, constraints_from(args))
    is_placeholder = resolve_provider(settings) == MOCK_PROVIDER
    if is_placeholder:
        notice(PLACEHOLDER_BANNER)
    if args.json:
        write_text(args.json, json.dumps(strategy_dict(strategy, is_placeholder), indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_strategy(strategy, is_placeholder))
    return EXIT_OK


def cmd_reflect(args: argparse.Namespace) -> int:
    """``ideate reflect``: run the reflector alone over a saved run and record what it learned."""
    settings = settings_from(args)
    system = IdeationSystem(settings)
    reflection = system.reflect(args.run)
    is_placeholder = reflection.provider == MOCK_PROVIDER
    patterns = system.meta_patterns_for(reflection.run_id, include_mock=is_placeholder)
    notice(f"reflection for run {reflection.run_id} saved to {settings.meta_path} ({len(patterns)} new meta-pattern(s))")
    if is_placeholder:
        notice(PLACEHOLDER_BANNER)
    if args.json:
        write_text(args.json, json.dumps(reflection_dict(reflection, patterns, is_placeholder), indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_reflection(reflection, patterns, is_placeholder))
    return EXIT_OK


def cmd_meta(args: argparse.Namespace) -> int:
    """``ideate meta``: list meta-patterns, or ingested memory sources with ``--sources``."""
    settings = settings_from(args)
    store = IdeationSystem(settings).meta
    if args.sources:
        sources = store.sources()
        if not sources:
            notice(f"no ingested memory sources in {settings.meta_path}")
            return EXIT_OK
        for s in sources:
            print(f"{s.id}  {s.kind:<8}  {s.format:<13}  {s.n_documents:>4} doc(s)  {s.title}  {s.path}")
        return EXIT_OK
    patterns = store.meta_patterns(kind=args.kind, scope=args.scope, include_mock=args.include_mock)
    if not patterns:
        notice("no meta-patterns" + ("" if args.include_mock else " (pass --include-mock to list mock meta-patterns)"))
        return EXIT_OK
    for p in patterns:
        mark = "[mock] " if p.provider == MOCK_PROVIDER else ""
        print(
            f"{mark}{p.id}  {p.kind:<8}  {p.scope:<11}  conf {p.confidence:.2f}  seen {p.observations}  "
            f"{p.text}  (tags: {', '.join(p.tags)})"
        )
    return EXIT_OK


def cmd_note(args: argparse.Namespace) -> int:
    """``ideate note``: file a correction into meta memory immediately, with no model call.

    This is the cheapest write in the system and the most valuable: it is how a correction
    survives the session that produced it. It never touches the network or an LLM, so an agent
    can call it the moment it is corrected without asking anyone.
    """
    settings = settings_from(args)
    text = args.text.strip()
    if not text:
        raise SettingsError("note text is empty")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    store = IdeationSystem(settings).meta
    pattern = store.add_meta_pattern(
        MetaPattern(
            kind=args.kind,
            text=text,
            tags=tags,
            scope=args.scope,
            provider=HUMAN_PROVIDER,
            confidence=HUMAN_CONFIDENCE,
        )
    )
    notice(f"noted {pattern.kind} in {settings.meta_path} (seen {pattern.observations}x, confidence {pattern.confidence:.2f})")
    print(pattern.id)
    return EXIT_OK


def cmd_charter(args: argparse.Namespace) -> int:
    """``ideate charter``: show the standing charter, or replace it."""
    settings = settings_from(args)
    if args.set_file:
        text = Path(args.set_file).read_text(encoding="utf-8")
        path = save_charter(settings.charter_path, text)
        notice(f"charter replaced from {args.set_file}")
        print(path)
        return EXIT_OK
    if args.init:
        if Path(settings.charter_path).exists():
            raise SettingsError(f"{settings.charter_path} already exists; edit it or use --set FILE")
        path = save_charter(settings.charter_path, DEFAULT_CHARTER)
        notice(f"default charter written to {path}; edit it to fit how you work")
        print(path)
        return EXIT_OK
    text, from_file = load_charter(settings.charter_path)
    notice(f"charter: {settings.charter_path}" if from_file else "charter: bundled default (run `ideate charter --init` to edit it)")
    sys.stdout.write(text.rstrip() + "\n")
    return EXIT_OK


def cmd_fetch(args: argparse.Namespace) -> int:
    """``ideate fetch``: pull arXiv abstracts or a page into the corpus as cited evidence."""
    settings = settings_from(args)
    system = IdeationSystem(settings)
    if bool(args.arxiv) == bool(args.url):
        raise SettingsError("pass either a URL or --arxiv QUERY, not both and not neither")
    if args.arxiv:
        docs = fetch_arxiv(args.arxiv, args.max)
        what = f"arXiv {args.arxiv!r}"
    else:
        docs = [fetch_url(args.url)]
        what = args.url
    paths = write_docs(docs, settings.fetched_dir, system.now())
    notice(f"fetched {len(paths)} document(s) from {what} into {settings.fetched_dir}")
    for path in paths:
        print(path)
    if args.reindex:
        system.build_index(force=True)
    else:
        notice("run 'ideate index' (or pass --reindex) to make this retrievable")
    return EXIT_OK


def cmd_watch(args: argparse.Namespace) -> int:
    """``ideate watch``: a video's captions become a corpus document citing the video."""
    settings = settings_from(args)
    system = IdeationSystem(settings)
    doc = fetch_transcript(args.url, lang=args.lang)
    paths = write_docs([doc], settings.fetched_dir, system.now())
    notice(f"transcribed {doc.title!r} ({len(doc.text)} chars) into {settings.fetched_dir}")
    for path in paths:
        print(path)
    if args.reindex:
        system.build_index(force=True)
    else:
        notice("run 'ideate index' (or pass --reindex) to make this retrievable")
    return EXIT_OK


def cmd_frames(args: argparse.Namespace) -> int:
    """``ideate frames``: stills from a video, listed with timestamps for an agent to read."""
    frames = extract_frames(
        args.path,
        args.out,
        max_frames=args.max_frames,
        start=args.start,
        end=args.end,
        width=args.width,
    )
    notice(f"extracted {len(frames)} frame(s) from {args.path} into {args.out}")
    sys.stdout.write(render_index(frames, Path(args.path).name) + "\n")
    return EXIT_OK


def cmd_gaps(args: argparse.Namespace) -> int:
    """``ideate gaps``: what runs could not answer, and the fetch command for each."""
    settings = settings_from(args)
    gaps = collect_gaps(settings.runs_dir, include_placeholder=args.include_placeholder)
    sys.stdout.write(render_gaps(gaps, args.max) + "\n")
    return EXIT_OK


def load_ideas(path: str) -> list[Idea]:
    """Ideas from a JSON list (or a saved result's ``ideas``); items may be ``{title, description}`` only."""
    data = read_json(path)
    if isinstance(data, dict) and isinstance(data.get("ideas"), list):
        data = data["ideas"]
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: expected a non-empty JSON list of ideas")
    ideas: list[Idea] = []
    for n, item in enumerate(data, 1):
        if not isinstance(item, dict) or not str(item.get("title", "")).strip():
            raise ValueError(f"{path}: item {n} needs at least a 'title'")
        ideas.append(Idea.from_dict({"description": "", **item}))
    return ideas


def cmd_judge(args: argparse.Namespace) -> int:
    """``ideate judge``: judge the ideas in a JSON file with the persona panel."""
    settings = settings_from(args)
    ideas = load_ideas(args.ideas_file)
    verdicts, ranking = IdeationSystem(settings).judge(ideas, args.theme, constraints_from(args))
    is_placeholder = resolve_provider(settings) == MOCK_PROVIDER
    if is_placeholder:
        notice(PLACEHOLDER_BANNER)
    if args.json:
        write_text(args.json, json.dumps(judgement_dict(ideas, verdicts, ranking, is_placeholder), indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_judgement(ideas, verdicts, ranking, is_placeholder))
    return EXIT_OK


def prefill_outcome(raw: dict, settings: Settings, run_id: str | None, idea_id: str | None) -> dict:
    """Fill missing outcome fields from a saved run (and one of its ideas)."""
    if idea_id and not run_id:
        raise ValueError("--idea requires --run")
    if not run_id:
        return raw
    result_path = Path(settings.runs_dir) / run_id / RESULT_FILE
    if not result_path.exists():
        raise ValueError(f"run {run_id!r} not found under {settings.runs_dir}")
    result = load_result(result_path)
    chosen = idea_id or (result.ranking[0] if result.ranking else None)
    filled = dict(raw)
    filled.setdefault("run_id", result.run_id)
    filled.setdefault("hackathon", result.theme)
    if chosen:
        idea = result.idea_for(chosen)
        if idea is None:
            raise ValueError(f"idea {chosen!r} not found in run {run_id!r}")
        filled.setdefault("idea_id", idea.id)
        filled.setdefault("idea_title", idea.title)
        filled.setdefault("idea_summary", idea.one_liner or idea.description)
    return filled


def cmd_learn(args: argparse.Namespace) -> int:
    """``ideate learn``: record an outcome (optionally prefilled from a saved run) and learn patterns."""
    settings = settings_from(args)
    raw = read_json(args.outcome_file)
    if not isinstance(raw, dict):
        raise ValueError(f"{args.outcome_file}: expected a JSON object")
    raw = prefill_outcome(raw, settings, args.run, args.idea)
    for key in ("hackathon", "idea_title"):
        if not str(raw.get(key, "")).strip():
            raise ValueError(f"{args.outcome_file}: {key!r} is required (or pass --run/--idea to prefill it)")
    system = IdeationSystem(settings)
    patterns = system.learn(Outcome.from_dict(raw))
    if any(p.provider == MOCK_PROVIDER for p in patterns):
        notice(LEARN_MOCK_NOTICE)
    notice(f"{len(patterns)} pattern(s) saved to {settings.memory_path}")
    sys.stdout.write(json.dumps([p.to_dict() for p in patterns], indent=2, sort_keys=True) + "\n")
    return EXIT_OK


def cmd_memory(args: argparse.Namespace) -> int:
    """``ideate memory``: list learned patterns; mock rows are marked ``[mock]``."""
    settings = settings_from(args)
    patterns = IdeationSystem(settings).memory.patterns(kind=args.kind, include_mock=args.include_mock)
    if not patterns:
        notice("no patterns" + ("" if args.include_mock else " (pass --include-mock to list mock patterns)"))
        return EXIT_OK
    for p in patterns:
        mark = "[mock] " if p.provider == MOCK_PROVIDER else ""
        print(f"{mark}{p.id}  {p.kind:<7}  {p.text}  (tags: {', '.join(p.tags)})")
    return EXIT_OK


def cmd_probe(args: argparse.Namespace) -> int:
    """``ideate probe``: one real call, write the receipt, print its path."""
    settings = settings_from(args)
    system = IdeationSystem(settings)
    receipt = system.probe()
    path = system.save_receipt(receipt)
    notice(f"probe ok: {receipt['provider']} served {receipt['served_model']} (requested {receipt['requested_model']})")
    print(path)
    return EXIT_OK


# --------------------------------------------------------------------------- entry point
def run_command(handler: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> int:
    """Run a subcommand, mapping the error taxonomy to exit codes and stderr lines."""
    try:
        return handler(args)
    except LLMConfigError as e:
        print(f"blocker ({e.kind}): {e.message}", file=sys.stderr)
        if e.hint:
            print(f"  fix: {e.hint}", file=sys.stderr)
        return EXIT_CONFIG
    except SettingsError as e:
        print(f"blocker (config-fixable): {e}", file=sys.stderr)
        print("  fix: correct the IDEATE_* variable or flag named above", file=sys.stderr)
        return EXIT_CONFIG
    except LLMRefusal as e:
        print(f"blocker (genuinely human-only): {e}", file=sys.stderr)
        return EXIT_REFUSAL
    except LLMTransientError as e:
        print(f"transient: {e} (retry later)", file=sys.stderr)
        return EXIT_TRANSIENT
    except (VideoToolMissing, FramesToolMissing) as e:
        print(f"blocker (config-fixable): {e}", file=sys.stderr)
        print(f"  fix: {e.hint}", file=sys.stderr)
        return EXIT_CONFIG
    except FrameError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except FetchError as e:
        # Unreachable host, a rejected request or an unparseable body: worth another try, and
        # never worth writing a half-fetched document into the corpus.
        print(f"transient: {e}", file=sys.stderr)
        print("  fix: check the URL or query and retry; nothing was written", file=sys.stderr)
        return EXIT_TRANSIENT
    except (LLMError, GraphError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv`` (default ``sys.argv[1:]``) and run the chosen subcommand."""
    args = build_parser().parse_args(argv)
    return run_command(args.handler, args)
