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
from ideate.models import HackathonConstraints, Idea, Outcome
from ideate.pipeline import RESULT_FILE, IdeationSystem, load_result
from ideate.report import PLACEHOLDER_BANNER, judgement_dict, render_json, render_judgement, render_markdown

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
    p_run.add_argument("--prefer", help="comma-separated technology preferences")
    p_run.add_argument("--avoid", help="comma-separated things to avoid")
    p_run.add_argument("--tracks", help="comma-separated event tracks")
    p_run.add_argument("--notes-file", help="file whose text becomes the constraints notes")
    p_run.add_argument("--ideas", type=int, help="ideas per round (default: IDEATE_IDEAS_PER_ROUND or 8)")
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
    notice(f"run {result.run_id} saved to {run_dir}")
    if result.is_placeholder:
        notice(PLACEHOLDER_BANNER)
    if args.out:
        write_text(args.out, render_markdown(result))
    if args.json:
        write_text(args.json, render_json(result))
    if not args.out and not args.json:
        sys.stdout.write(render_markdown(result))
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
    except (LLMError, GraphError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv`` (default ``sys.argv[1:]``) and run the chosen subcommand."""
    args = build_parser().parse_args(argv)
    return run_command(args.handler, args)
