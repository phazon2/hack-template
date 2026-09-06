"""Turn the system's own coverage gaps into commands that fill them.

The research agent already names what the knowledge base could not answer (`coverage_gaps`),
and the reflector already judges whether retrieval helped (`signal_quality`). Both were, until
now, written to disk and read by nobody. This module collects them across saved runs and emits
the exact `ideate fetch` command for each.

That inversion is the point: deciding *whether a source is needed and where it belongs* is the
judgement call this system's owner cannot make cheaply, so the system makes it and hands over a
command to run. Nothing here needs an LLM or a network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ideate.models import slug

# Words that carry no retrieval signal in a gap phrase ("no data on X" -> "X").
_GAP_NOISE = {
    "a", "an", "the", "no", "not", "any", "about", "on", "for", "of", "in", "to", "and", "or",
    "data", "evidence", "information", "info", "detail", "details", "knowledge", "base",
    "missing", "lacks", "lacking", "nothing", "none", "coverage", "gap", "snippets", "snippet",
    "there", "is", "are", "was", "were", "how", "what", "which", "specific", "specifics",
}


@dataclass
class Gap:
    """One thing the knowledge base could not answer, and how often it came up."""

    text: str
    runs: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return slug(self.text)

    @property
    def count(self) -> int:
        return len(self.runs)

    def query(self) -> str:
        """A search query: the gap phrase stripped of words that carry no retrieval signal."""
        words = [w for w in _split(self.text) if w.lower() not in _GAP_NOISE]
        return " ".join(words[:12]) or self.text.strip()

    def fetch_command(self, max_results: int = 5) -> str:
        """The command that would fill this gap."""
        return f'ideate fetch --arxiv "{self.query()}" --max {max_results}'


def _split(text: str) -> list[str]:
    return [w for w in "".join(c if c.isalnum() or c in "-'" else " " for c in text).split() if w]


def _iter_results(runs_dir: str | Path) -> list[dict]:
    """Every saved run result, newest directory last (mtime order, then name for stability)."""
    directory = Path(runs_dir)
    if not directory.is_dir():
        return []
    paths = sorted(directory.glob("*/result.json"), key=lambda p: (p.parent.stat().st_mtime, p.parent.name))
    results = []
    for path in paths:
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return results


def collect_gaps(runs_dir: str | Path, include_placeholder: bool = False) -> list[Gap]:
    """Coverage gaps across saved runs, most frequent first.

    Placeholder (mock) runs are excluded by default: their gaps are generated text, and acting
    on them would mean fetching real papers to answer a question nobody actually asked.
    """
    merged: dict[str, Gap] = {}
    for result in _iter_results(runs_dir):
        if result.get("is_placeholder") and not include_placeholder:
            continue
        run_id = str(result.get("run_id", ""))
        theme = str(result.get("theme", ""))
        gaps = result.get("coverage_gaps") or []
        research = result.get("research") or {}
        if isinstance(research, dict):
            gaps = list(gaps) + list(research.get("coverage_gaps") or [])
        for raw in gaps:
            text = str(raw).strip()
            if not text:
                continue
            gap = merged.setdefault(slug(text) or text, Gap(text=text))
            if run_id and run_id not in gap.runs:
                gap.runs.append(run_id)
            if theme and theme not in gap.themes:
                gap.themes.append(theme)
    return sorted(merged.values(), key=lambda g: (-g.count, g.key))


def render_gaps(gaps: list[Gap], max_results: int = 5) -> str:
    """A plain report: each gap, where it came from, and the command that fills it."""
    if not gaps:
        return "No coverage gaps recorded. Run `ideate run` first, or pass --include-placeholder."
    lines = [f"{len(gaps)} coverage gap(s) the knowledge base could not answer:", ""]
    for gap in gaps:
        seen = f"seen in {gap.count} run(s)" + (f", e.g. {gap.themes[0]!r}" if gap.themes else "")
        lines += [f"- {gap.text}", f"    {seen}", f"    {gap.fetch_command(max_results)}", ""]
    return "\n".join(lines).rstrip()
