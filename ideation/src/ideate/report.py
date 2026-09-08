"""Markdown and JSON rendering of an ``IdeationResult`` (docs/DESIGN.md §12).

Imports only ``models``: the report is a pure function of the result.
"""

from __future__ import annotations

import json

from ideate.models import (
    Idea,
    IdeaEvaluation,
    IdeationResult,
    MetaPattern,
    PanelVerdict,
    Proposal,
    RetrievedChunk,
    RunReflection,
    Strategy,
    TraceStep,
)

PLACEHOLDER_BANNER = "PROVIDER: mock — placeholder content, not evidence"
FEASIBILITY = "feasibility"
NEUTRAL_SCORE = 3.0
STRATEGY_HEADING = "## 1a. Strategy"
LEARNED_HEADING = "## 10. What the system learned"
NO_NEW_PATTERNS = "none new (nothing this run observed was missing from meta memory)"
TABLE_HEADER = "| # | Idea | Technique | Beats | Weighted | Feasibility | Agreement | Disqualified |\n|---|---|---|---|---|---|---|---|"


# --------------------------------------------------------------------------- small helpers
def banner_lines(is_placeholder: bool) -> list[str]:
    """The exact placeholder blockquote (plus a blank line) when the result is mock output."""
    return [f"> **{PLACEHOLDER_BANNER}**", ""] if is_placeholder else []


def _bullets(items: list[str], empty: str = "none") -> list[str]:
    return [f"- {item}" for item in items] if items else [f"- {empty}"]


def _numbered(items: list[str], empty: str = "none") -> list[str]:
    return [f"{n}. {item}" for n, item in enumerate(items, 1)] if items else [f"1. {empty}"]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _verdict_map(verdicts: list[PanelVerdict]) -> dict[str, PanelVerdict]:
    return {v.idea_id: v for v in verdicts}


def _idea_map(ideas: list[Idea]) -> dict[str, Idea]:
    return {i.id: i for i in ideas}


def _ordered_ids(ideas: list[Idea], ranking: list[str]) -> list[str]:
    """Ranking order first, then any unranked idea in input order (defence in depth)."""
    return list(dict.fromkeys(list(ranking) + [i.id for i in ideas]))


# --------------------------------------------------------------------------- shared blocks
def render_ranking_table(
    ideas: list[Idea], verdicts: list[PanelVerdict], ranking: list[str], pairwise: dict[str, int] | None = None
) -> str:
    """The all-ideas table in ranking order.

    "Beats" is how many real hackathon winners the idea was judged to beat head to head, and it is
    what orders each tier — so without the column the ranking looks like it disagrees with the
    weighted score for no reason. It shows "-" when no winner references were available.
    """
    wins = pairwise or {}
    by_idea, by_verdict = _idea_map(ideas), _verdict_map(verdicts)
    rows = [TABLE_HEADER]
    for n, idea_id in enumerate(_ordered_ids(ideas, ranking), 1):
        idea = by_idea.get(idea_id)
        verdict = by_verdict.get(idea_id)
        title = idea.title if idea is not None else idea_id
        technique = idea.technique if idea is not None else "-"
        if verdict is None:
            weighted = feasibility = agreement = disqualified = "-"
        else:
            c = verdict.consensus
            weighted = f"{c.weighted_score:.2f}"
            feasibility = f"{c.score_for(FEASIBILITY, NEUTRAL_SCORE):.1f}"
            agreement = f"{verdict.agreement:.2f}"
            disqualified = "yes" if c.disqualified else "no"
        beats = str(wins[idea_id]) if idea_id in wins else "-"
        rows.append(
            f"| {n} | {_cell(title)} ({idea_id}) | {technique} | {beats} | {weighted} | {feasibility} | {agreement} | {disqualified} |"
        )
    return "\n".join(rows)


def render_consensus(consensus: IdeaEvaluation, agreement: float | None = None) -> list[str]:
    """Bullet lines describing a consensus evaluation."""
    scores = ", ".join(f"{s.name} {s.score:.1f}" for s in consensus.scores) or "none"
    lines = [f"- Weighted score: {consensus.weighted_score:.2f} ({scores})"]
    if agreement is not None:
        lines.append(f"- Panel agreement: {agreement:.2f}")
    if consensus.disqualified:
        lines.append(f"- Disqualified: {consensus.disqualify_reason or 'no reason given'}")
    for label, items in (("Strengths", consensus.strengths), ("Weaknesses", consensus.weaknesses), ("Suggestions", consensus.suggestions), ("Risks", consensus.risks)):
        if items:
            lines.append(f"- {label}: " + "; ".join(items))
    if consensus.closest_existing:
        lines.append(f"- Closest existing (judges): {consensus.closest_existing}")
    if consensus.demo_break_risk:
        lines.append(f"- Demo break risk: {consensus.demo_break_risk}")
    return lines


def render_idea_detail(idea: Idea, verdict: PanelVerdict | None) -> list[str]:
    """The per-idea detail block: every idea field plus its consensus verdict."""
    lines = [f"### {idea.id}: {idea.title}", ""]
    if idea.one_liner:
        lines.append(f"*{idea.one_liner}*")
        lines.append("")
    rows = [
        ("Technique", idea.technique + (f" (refines {idea.parent_id})" if idea.parent_id else "")),
        ("Target user", idea.target_user),
        ("Key innovation", idea.key_innovation),
        ("Description", idea.description),
        ("Technical approach", idea.technical_approach),
        ("Demo strategy", idea.demo_strategy),
        ("Demo moment", idea.demo_moment),
        ("Data sources", "; ".join(idea.data_sources)),
        ("MVP scope", "; ".join(idea.mvp_scope)),
        ("Cut first", "; ".join(idea.cut_first)),
        ("Closest existing", idea.closest_existing),
        ("Build hours estimate", str(idea.build_hours_estimate) if idea.build_hours_estimate else ""),
        ("Risks", "; ".join(idea.risks)),
        ("Citations", ", ".join(f"`{c}`" for c in idea.citations)),
    ]
    lines.extend(f"- {label}: {value}" for label, value in rows if value)
    if verdict is not None:
        lines.append("")
        lines.append("Panel consensus:")
        lines.extend(render_consensus(verdict.consensus, verdict.agreement))
    return lines


def render_judgement(ideas: list[Idea], verdicts: list[PanelVerdict], ranking: list[str], is_placeholder: bool) -> str:
    """Markdown for ``ideate judge``: banner, ranking table and per-idea consensus."""
    by_idea, by_verdict = _idea_map(ideas), _verdict_map(verdicts)
    lines = banner_lines(is_placeholder) + ["# Judgement", "", render_ranking_table(ideas, verdicts, ranking), ""]
    for idea_id in _ordered_ids(ideas, ranking):
        idea = by_idea.get(idea_id)
        if idea is None:
            continue
        lines.extend(render_idea_detail(idea, by_verdict.get(idea_id)))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def judgement_dict(ideas: list[Idea], verdicts: list[PanelVerdict], ranking: list[str], is_placeholder: bool) -> dict:
    """JSON-ready dict for ``ideate judge`` (with ``placeholder_notice`` under the mock)."""
    d = {
        "ideas": [i.to_dict() for i in ideas],
        "verdicts": [v.to_dict() for v in verdicts],
        "ranking": list(ranking),
        "is_placeholder": is_placeholder,
    }
    if is_placeholder:
        d["placeholder_notice"] = PLACEHOLDER_BANNER
    return d


# --------------------------------------------------------------------------- meta layer (DESIGN-META §18.7)
def strategy_rows(strategy: Strategy) -> list[tuple[str, str]]:
    """The label/value rows of the Strategy section; a row with an empty value is not rendered."""
    emphasis = ", ".join(f"{name} x{multiplier:g}" for name, multiplier in sorted(strategy.rubric_emphasis.items()))
    return [
        ("Problem type", strategy.problem_type or "unclear"),
        ("Framing", strategy.framing or "none stated"),
        ("Emphasised techniques", ", ".join(strategy.emphasis_techniques) or "none"),
        ("Retrieval angles", ", ".join(strategy.retrieval_angles)),
        ("Rubric emphasis", emphasis),
        ("Planned rounds", str(strategy.rounds) if strategy.rounds else "the settings default"),
        ("Watching for", ", ".join(strategy.watch_for) or "none"),
        ("Why", strategy.rationale or "none given"),
    ]


def strategy_section(strategy: Strategy | None) -> list[str]:
    """Section 1a, or no lines at all when no strategist ran."""
    if strategy is None:
        return []
    return [STRATEGY_HEADING, ""] + [f"- {label}: {value}" for label, value in strategy_rows(strategy) if value]


def pattern_lines(patterns: list[MetaPattern]) -> list[str]:
    """One bullet per meta-pattern written, with its scope, confidence and observation count."""
    if not patterns:
        return [f"- {NO_NEW_PATTERNS}"]
    return [
        f"- [{p.kind}|{p.scope}] {p.text} (confidence {p.confidence:.2f}, observations {p.observations}"
        + (f", tags: {', '.join(p.tags)}" if p.tags else "")
        + ")"
        for p in patterns
    ]


def learned_body(reflection: RunReflection, patterns: list[MetaPattern]) -> list[str]:
    """The body of the "What the system learned" block, shared by the report and ``ideate reflect``."""
    lines = ["### What worked", ""] + _bullets(reflection.what_worked)
    lines += ["", "### What failed", ""] + _bullets(reflection.what_failed)
    lines += ["", "### Process changes", ""] + _bullets(reflection.process_changes)
    rows = [
        ("Signal quality", reflection.signal_quality),
        ("Winning technique", reflection.winning_technique),
        ("Judge disagreement", reflection.judge_disagreement),
        ("Wasted effort", "; ".join(reflection.wasted_effort)),
    ]
    stated = [f"- {label}: {value}" for label, value in rows if value]
    if stated:
        lines += ["", "### Signals", ""] + stated
    return lines + ["", "### Meta-patterns written", ""] + pattern_lines(patterns)


def learned_section(reflection: RunReflection | None, patterns: list[MetaPattern] | None) -> list[str]:
    """Section 10, or no lines at all when no reflector ran."""
    if reflection is None:
        return []
    return [LEARNED_HEADING, ""] + learned_body(reflection, list(patterns or []))


def render_strategy(strategy: Strategy, is_placeholder: bool) -> str:
    """Standalone markdown for ``ideate strategy``: banner, heading and the plan rows."""
    lines = banner_lines(is_placeholder) + ["# Strategy", ""]
    lines += [f"- {label}: {value}" for label, value in strategy_rows(strategy) if value]
    return "\n".join(lines).rstrip("\n") + "\n"


def strategy_dict(strategy: Strategy, is_placeholder: bool) -> dict:
    """JSON-ready dict for ``ideate strategy --json`` (with ``placeholder_notice`` under the mock)."""
    d = {"strategy": strategy.to_dict(), "is_placeholder": is_placeholder}
    if is_placeholder:
        d["placeholder_notice"] = PLACEHOLDER_BANNER
    return d


def render_reflection(reflection: RunReflection, patterns: list[MetaPattern], is_placeholder: bool) -> str:
    """Standalone markdown for ``ideate reflect``: banner, run line and the learned block."""
    lines = banner_lines(is_placeholder) + [
        f"# What the system learned: {reflection.theme}",
        "",
        f"Run `{reflection.run_id}` · {reflection.created_at} · provider {reflection.provider}",
        "",
    ]
    lines += learned_body(reflection, list(patterns))
    return "\n".join(lines).rstrip("\n") + "\n"


def reflection_dict(reflection: RunReflection, patterns: list[MetaPattern], is_placeholder: bool) -> dict:
    """JSON-ready dict for ``ideate reflect --json`` (with ``placeholder_notice`` under the mock)."""
    d = {
        "reflection": reflection.to_dict(),
        "meta_patterns": [p.to_dict() for p in patterns],
        "is_placeholder": is_placeholder,
    }
    if is_placeholder:
        d["placeholder_notice"] = PLACEHOLDER_BANNER
    return d


# --------------------------------------------------------------------------- the report
def _build_this(result: IdeationResult, proposal: Proposal, top: Idea | None) -> list[str]:
    lines = ["## 1. Build this", ""]
    if top is None:
        lines.append("- No idea was ranked.")
        return lines
    lines.append(f"**{top.title}** ({top.id})")
    lines.append("")
    rows = [
        ("One-liner", top.one_liner),
        ("Target user", top.target_user),
        ("Demo moment", top.demo_moment),
        ("Why this", proposal.why_this),
        ("Closest existing", top.closest_existing),
        ("Executive summary", proposal.executive_summary),
        ("Value proposition", proposal.value_proposition),
        ("Impact", proposal.impact),
    ]
    lines.extend(f"- {label}: {value}" for label, value in rows if value)
    return lines


def _runner_ups(result: IdeationResult, proposal: Proposal) -> list[str]:
    lines = ["## 5. Runner-ups", ""]
    by_idea = _idea_map(result.ideas)
    conditions = {a.idea_id: a.choose_if for a in proposal.alternatives}
    runner_ups = result.ranking[1:3]
    if not runner_ups:
        lines.append("- none")
        return lines
    for idea_id in runner_ups:
        idea = by_idea.get(idea_id)
        title = idea.title if idea is not None else idea_id
        condition = conditions.get(idea_id) or "the panel's stated weaknesses of the top idea prove real"
        lines.append(f"- **{title}** ({idea_id}) — choose instead if {condition}")
    return lines


def _sources_cited(result: IdeationResult) -> list[str]:
    cited: list[str] = list(result.research.citations) if result.research is not None else []
    for idea in result.ideas:
        cited.extend(idea.citations)
    cited = list(dict.fromkeys(cited))
    chunks: dict[str, RetrievedChunk] = {rc.chunk.id: rc for rc in result.knowledge}
    lines = ["### Sources cited", ""]
    if not cited:
        lines.append("- none")
        return lines
    for chunk_id in cited:
        rc = chunks.get(chunk_id)
        if rc is None:
            lines.append(f"- `{chunk_id}`")
            continue
        meta = rc.chunk.metadata
        source = f" — {meta['source']}" if meta.get("source") else ""
        lines.append(f"- `{chunk_id}` — {meta.get('title', rc.chunk.doc_id)} ({meta.get('kind', 'guidance')}){source}")
    return lines


def _trace_summary(trace: list[TraceStep]) -> list[str]:
    served = list(dict.fromkeys(f"{t.provider}/{t.model}" for t in trace))
    errors = [t for t in trace if t.error]
    lines = [
        "## 9. Trace summary",
        "",
        f"- Calls: {len(trace)} ({len(errors)} failed)",
        f"- Tokens: {sum(t.input_tokens for t in trace)} in / {sum(t.output_tokens for t in trace)} out",
        f"- Served models: {', '.join(served) or 'none'}",
        f"- Wall time in LLM calls: {sum(t.duration_ms for t in trace)} ms",
    ]
    if trace:
        lines.extend(["", "| Agent | Served | In | Out | ms | Status |", "|---|---|---|---|---|---|"])
        for t in trace:
            status = f"error: {_cell(t.error)}" if t.error else (t.stop_reason or "ok")
            lines.append(f"| {t.agent} | {t.provider}/{t.model} | {t.input_tokens} | {t.output_tokens} | {t.duration_ms} | {status} |")
    return lines


def render_markdown(result: IdeationResult, meta_patterns: list[MetaPattern] | None = None) -> str:
    """The full markdown report; under the mock the first line is the placeholder banner.

    ``meta_patterns`` are the meta-patterns this run wrote (the result does not carry them); they
    appear in section 10, which is omitted entirely when no reflector ran.
    """
    proposal = result.proposal if result.proposal is not None else Proposal()
    by_idea, by_verdict = _idea_map(result.ideas), _verdict_map(result.verdicts)
    top = by_idea.get(result.ranking[0]) if result.ranking else None
    c = result.constraints
    lines = banner_lines(result.is_placeholder)
    lines += [
        f"# Ideation report: {result.theme}",
        "",
        f"Run `{result.run_id}` · {result.created_at} · provider {result.provider} · model {result.model} · "
        f"{c.hours}h · team of {c.team_size} · {result.iterations} idea round(s) · {result.retrieval_rounds} retrieval round(s)",
        "",
    ]
    strategy = strategy_section(result.strategy)
    if strategy:
        lines += strategy + [""]
    lines += _build_this(result, proposal, top) + [""]
    lines += ["## 2. First hour", ""] + _numbered(proposal.first_hour_plan) + [""]
    lines += ["## 3. Plan", "", "### Milestones", ""] + _bullets(proposal.milestones) + [""]
    lines += ["### Team split", ""] + _bullets(proposal.team_split) + [""]
    lines += ["### Cut list", ""] + _bullets(proposal.cut_list) + [""]
    lines += ["### Pivot trigger", "", f"- {proposal.pivot_trigger or 'none stated'}", ""]
    lines += ["## 4. Human dependencies", ""] + _bullets(proposal.human_dependencies) + [""]
    lines += _runner_ups(result, proposal) + [""]
    lines += [
        "## 6. All ideas",
        "",
        render_ranking_table(result.ideas, result.verdicts, result.ranking, result.pairwise_wins),
        "",
    ]
    lines += ["## 7. Idea details", ""]
    for idea_id in _ordered_ids(result.ideas, result.ranking):
        idea = by_idea.get(idea_id)
        if idea is None:
            continue
        lines += render_idea_detail(idea, by_verdict.get(idea_id)) + [""]
    lines += ["## 8. Knowledge gaps and sources cited", "", "### Knowledge gaps", ""] + _bullets(result.coverage_gaps) + [""]
    lines += _sources_cited(result) + [""]
    lines += _trace_summary(result.trace)
    learned = learned_section(result.reflection, meta_patterns)
    if learned:
        lines += [""] + learned
    return "\n".join(lines).rstrip("\n") + "\n"


def render_json(result: IdeationResult) -> str:
    """``result.to_dict()`` as sorted, indented JSON, plus ``placeholder_notice`` under the mock."""
    d = result.to_dict()
    if result.is_placeholder:
        d["placeholder_notice"] = PLACEHOLDER_BANNER
    return json.dumps(d, indent=2, sort_keys=True)
