"""Markdown / JSON rendering of results (DESIGN §12)."""

from __future__ import annotations

import json

import pytest

from ideate.models import (
    Alternative,
    Chunk,
    CriterionScore,
    HackathonConstraints,
    Idea,
    IdeaEvaluation,
    IdeationResult,
    MetaPattern,
    PanelVerdict,
    Proposal,
    ResearchFindings,
    RetrievedChunk,
    RunReflection,
    Strategy,
    TraceStep,
)
from ideate.report import (
    NO_NEW_PATTERNS,
    PLACEHOLDER_BANNER,
    judgement_dict,
    reflection_dict,
    render_json,
    render_judgement,
    render_markdown,
    render_ranking_table,
    render_reflection,
    render_strategy,
    strategy_dict,
)

BANNER_LINE = "> **PROVIDER: mock — placeholder content, not evidence**"
SECTION_HEADINGS = [
    "## 1. Build this",
    "## 2. First hour",
    "## 3. Plan",
    "## 4. Human dependencies",
    "## 5. Runner-ups",
    "## 6. All ideas",
    "## 7. Idea details",
    "## 8. Knowledge gaps and sources cited",
    "## 9. Trace summary",
]


def make_idea(n: int, technique: str) -> Idea:
    return Idea(
        title=f"Idea {n}",
        description=f"Description {n}",
        id=f"idea-1-{n}",
        one_liner=f"One liner {n}",
        target_user=f"a nurse on shift {n}",
        demo_moment=f"the map lights up {n}",
        technique=technique,
        data_sources=[f"source {n} — access: none — data"],
        citations=["doc#0"] if n == 1 else ["doc#1"],
        closest_existing=f"Existing {n}",
        build_hours_estimate=10 + n,
    )


def make_verdict(idea_id: str, weighted: float, feasibility: float, disqualified: bool = False) -> PanelVerdict:
    consensus = IdeaEvaluation(
        idea_id=idea_id,
        scores=[CriterionScore("novelty", 4.0), CriterionScore("feasibility", feasibility)],
        weighted_score=weighted,
        strengths=["clear user"],
        weaknesses=["thin demo"],
        suggestions=["record a fallback"],
        disqualified=disqualified,
        disqualify_reason="needs an account" if disqualified else "",
        judge="consensus",
    )
    return PanelVerdict(idea_id=idea_id, evaluations=[consensus], consensus=consensus, agreement=0.9)


@pytest.fixture
def result() -> IdeationResult:
    ideas = [make_idea(1, "analogical"), make_idea(2, "reverse"), make_idea(3, "scale")]
    chunk = Chunk(id="doc#0", doc_id="doc", text="snippet", position=0, metadata={"title": "Doc title", "kind": "guidance", "source": "https://example.org"})
    return IdeationResult(
        run_id="abc123",
        created_at="2026-01-02T03:04:05+00:00",
        version="0.1.0",
        theme="AI for climate resilience",
        constraints=HackathonConstraints(hours=36, team_size=4),
        provider="mock",
        model="mock-1",
        knowledge=[RetrievedChunk(chunk=chunk, score=0.5)],
        research=ResearchFindings(trends=["t"], citations=["doc#0", "missing#9"], coverage_gaps=["no evidence on flood sensors"]),
        ideas=ideas,
        verdicts=[make_verdict("idea-1-1", 4.2, 4.0), make_verdict("idea-1-2", 3.9, 3.0), make_verdict("idea-1-3", 2.1, 1.0, disqualified=True)],
        ranking=["idea-1-2", "idea-1-1", "idea-1-3"],
        proposal=Proposal(
            idea_id="idea-1-2",
            why_this="it demos in 60 seconds",
            first_hour_plan=["create repo and push", "confirm public URL"],
            milestones=["h9 walking skeleton"],
            team_split=["A: integration owner", "B: demo owner"],
            cut_list=["auth"],
            pivot_trigger="no public URL by hour 9",
            human_dependencies=["do-it-myself: create the API key"],
            alternatives=[Alternative(idea_id="idea-1-1", choose_if="the flood data is offline")],
        ),
        iterations=1,
        retrieval_rounds=1,
        coverage_gaps=["no evidence on flood sensors"],
        trace=[
            TraceStep(agent="orchestrator", provider="mock", model="mock-1", input_tokens=10, output_tokens=5, duration_ms=3, stop_reason="end_turn"),
            TraceStep(agent="research", provider="mock", model="mock-1", input_tokens=20, output_tokens=7, duration_ms=4, error="LLMBadOutput: x"),
        ],
        is_placeholder=True,
    )


def test_markdown_first_line_is_banner_then_blank(result):
    lines = render_markdown(result).splitlines()
    assert lines[0] == BANNER_LINE and lines[0] == f"> **{PLACEHOLDER_BANNER}**"
    assert lines[1] == ""
    assert lines[2] == "# Ideation report: AI for climate resilience"


def test_markdown_without_banner_for_real_provider(result):
    result.is_placeholder = False
    result.provider = "anthropic"
    md = render_markdown(result)
    assert PLACEHOLDER_BANNER not in md
    assert md.splitlines()[0] == "# Ideation report: AI for climate resilience"


def test_sections_in_order(result):
    md = render_markdown(result)
    positions = [md.index(h) for h in SECTION_HEADINGS]
    assert positions == sorted(positions)


def test_build_this_section_uses_top_ranked_idea(result):
    md = render_markdown(result)
    build = md[md.index("## 1. Build this"): md.index("## 2. First hour")]
    assert "**Idea 2** (idea-1-2)" in build
    assert "- One-liner: One liner 2" in build
    assert "- Target user: a nurse on shift 2" in build
    assert "- Demo moment: the map lights up 2" in build
    assert "- Why this: it demos in 60 seconds" in build
    assert "- Closest existing: Existing 2" in build


def test_first_hour_numbered_and_plan_sections(result):
    md = render_markdown(result)
    assert "1. create repo and push\n2. confirm public URL" in md
    assert "- h9 walking skeleton" in md and "- A: integration owner" in md and "- auth" in md
    assert "- no public URL by hour 9" in md
    assert "- do-it-myself: create the API key" in md


def test_runner_ups_choose_instead_if(result):
    md = render_markdown(result)
    section = md[md.index("## 5. Runner-ups"): md.index("## 6. All ideas")]
    assert "**Idea 1** (idea-1-1) — choose instead if the flood data is offline" in section
    assert "**Idea 3** (idea-1-3) — choose instead if" in section


def test_all_ideas_table_in_ranking_order(result):
    table = render_ranking_table(result.ideas, result.verdicts, result.ranking).splitlines()
    assert table[0].startswith("| # | Idea | Technique | Beats | Weighted | Feasibility | Agreement | Disqualified |")
    rows = table[2:]
    assert [r.split("|")[2].strip() for r in rows] == ["Idea 2 (idea-1-2)", "Idea 1 (idea-1-1)", "Idea 3 (idea-1-3)"]
    assert rows[0].split("|")[3:9] == [" reverse ", " - ", " 3.90 ", " 3.0 ", " 0.90 ", " no "]
    assert rows[2].split("|")[8].strip() == "yes"
    assert render_ranking_table(result.ideas, result.verdicts, result.ranking) in render_markdown(result)


def test_table_shows_wins_against_real_winners(result):
    """Pairwise wins order each tier, so the report has to show them or the order looks arbitrary."""
    wins = {"idea-1-2": 4, "idea-1-1": 0}
    rows = render_ranking_table(result.ideas, result.verdicts, result.ranking, wins).splitlines()[2:]
    assert [r.split("|")[4].strip() for r in rows] == ["4", "0", "-"]  # idea-1-3 was not compared
    result.pairwise_wins = wins
    assert render_ranking_table(result.ideas, result.verdicts, result.ranking, wins) in render_markdown(result)


def test_table_handles_unjudged_ideas():
    ideas = [make_idea(1, "direct")]
    rows = render_ranking_table(ideas, [], []).splitlines()
    assert rows[2] == "| 1 | Idea 1 (idea-1-1) | direct | - | - | - | - | - |"


def test_per_idea_detail_and_consensus(result):
    md = render_markdown(result)
    details = md[md.index("## 7. Idea details"): md.index("## 8. Knowledge gaps")]
    assert details.index("### idea-1-2: Idea 2") < details.index("### idea-1-1: Idea 1") < details.index("### idea-1-3: Idea 3")
    assert "- Weighted score: 2.10 (novelty 4.0, feasibility 1.0)" in details
    assert "- Disqualified: needs an account" in details
    assert "- Weaknesses: thin demo" in details and "- Citations: `doc#0`" in details


def test_knowledge_gaps_and_sources(result):
    md = render_markdown(result)
    section = md[md.index("## 8. Knowledge gaps"): md.index("## 9. Trace summary")]
    assert "- no evidence on flood sensors" in section
    assert "- `doc#0` — Doc title (guidance) — https://example.org" in section
    assert "- `missing#9`" in section and "- `doc#1`" in section
    assert section.index("`doc#0`") < section.index("`missing#9`") < section.index("`doc#1`")


def test_trace_summary(result):
    md = render_markdown(result)
    section = md[md.index("## 9. Trace summary"):]
    assert "- Calls: 2 (1 failed)" in section
    assert "- Tokens: 30 in / 12 out" in section
    assert "- Served models: mock/mock-1" in section
    assert "| research | mock/mock-1 | 20 | 7 | 4 | error: LLMBadOutput: x |" in section


def test_markdown_survives_an_empty_result():
    empty = IdeationResult(run_id="r", created_at="t", version="0.1.0", theme="x", constraints=HackathonConstraints(), provider="mock", model="mock-1", is_placeholder=True)
    md = render_markdown(empty)
    assert md.splitlines()[0] == BANNER_LINE
    assert all(h in md for h in SECTION_HEADINGS)
    assert "- No idea was ranked." in md and "- Calls: 0 (0 failed)" in md
    assert md.endswith("\n") and not md.endswith("\n\n")


def test_render_json_sorted_with_placeholder_notice(result):
    text = render_json(result)
    data = json.loads(text)
    assert data["placeholder_notice"] == PLACEHOLDER_BANNER
    assert data["run_id"] == "abc123" and data["ranking"] == ["idea-1-2", "idea-1-1", "idea-1-3"]
    assert text == json.dumps(data, indent=2, sort_keys=True)
    assert IdeationResult.from_dict(data).to_dict() == result.to_dict()


def test_render_json_without_notice_for_real_provider(result):
    result.is_placeholder = False
    data = json.loads(render_json(result))
    assert "placeholder_notice" not in data and data["is_placeholder"] is False


def test_render_judgement_and_dict(result):
    md = render_judgement(result.ideas, result.verdicts, result.ranking, True)
    assert md.splitlines()[0] == BANNER_LINE and "# Judgement" in md
    assert "| 1 | Idea 2 (idea-1-2) |" in md and "### idea-1-2: Idea 2" in md
    assert PLACEHOLDER_BANNER not in render_judgement(result.ideas, result.verdicts, result.ranking, False)
    d = judgement_dict(result.ideas, result.verdicts, result.ranking, True)
    assert d["ranking"] == result.ranking and d["placeholder_notice"] == PLACEHOLDER_BANNER
    assert [v["idea_id"] for v in d["verdicts"]] == ["idea-1-1", "idea-1-2", "idea-1-3"]
    assert "placeholder_notice" not in judgement_dict(result.ideas, result.verdicts, result.ranking, False)


# --------------------------------------------------------------------------- meta layer (DESIGN-META §18.7)
def make_strategy() -> Strategy:
    return Strategy(
        framing="Treat this as a sensing problem: the data exists, the reading of it does not.",
        problem_type="data",
        emphasis_techniques=["analogical", "constraint_removal"],
        retrieval_angles=["river gauge feeds", "flood insurance payouts"],
        rubric_emphasis={"novelty": 1.5, "feasibility": 0.5},
        rounds=2,
        watch_for=["a dashboard with no decision", "a demo that needs live weather"],
        rationale="the corpus has three data-source documents and no archetype for sensing",
        source_patterns=["meta-abc123456789"],
    )


def make_reflection() -> RunReflection:
    return RunReflection(
        run_id="abc123",
        theme="AI for climate resilience",
        created_at="2026-01-02T03:04:05+00:00",
        provider="mock",
        what_worked=["the pinned data-source chunks reached every idea"],
        what_failed=["the second creativity round added no strong idea"],
        process_changes=["stop at one round when round one already has three strong ideas"],
        signal_quality="retrieval changed the ideas: every idea cites a data source",
        winning_technique="analogical",
        judge_disagreement="agreement was 0.90 on every idea, so the panel added little spread",
        wasted_effort=["the second retrieval round added four chunks nobody cited"],
    )


def make_patterns() -> list[MetaPattern]:
    return [
        MetaPattern(kind="process", text="one creativity round is enough when three ideas clear the bar",
                    tags=["loop", "cost"], scope="global", source_run_id="abc123", provider="mock",
                    confidence=0.7, observations=2),
        MetaPattern(kind="pitfall", text="a dashboard without a decision scores low on demoability",
                    scope="data", source_run_id="abc123", provider="mock"),
    ]


def test_strategy_section_sits_between_the_header_and_build_this(result):
    result.strategy = make_strategy()
    md = render_markdown(result)
    assert md.index(BANNER_LINE) < md.index("## 1a. Strategy") < md.index("## 1. Build this")
    section = md[md.index("## 1a. Strategy"): md.index("## 1. Build this")]
    assert "- Problem type: data" in section
    assert "- Framing: Treat this as a sensing problem" in section
    assert "- Emphasised techniques: analogical, constraint_removal" in section
    assert "- Retrieval angles: river gauge feeds, flood insurance payouts" in section
    assert "- Rubric emphasis: feasibility x0.5, novelty x1.5" in section
    assert "- Planned rounds: 2" in section
    assert "- Watching for: a dashboard with no decision, a demo that needs live weather" in section
    assert "- Why: the corpus has three data-source documents" in section


def test_strategy_section_is_omitted_without_a_strategy(result):
    assert result.strategy is None
    md = render_markdown(result)
    assert "## 1a. Strategy" not in md and md.index("# Ideation report") < md.index("## 1. Build this")


def test_strategy_section_falls_back_for_empty_fields(result):
    result.strategy = Strategy()
    section = render_markdown(result)
    section = section[section.index("## 1a. Strategy"): section.index("## 1. Build this")]
    assert "- Problem type: unclear" in section and "- Framing: none stated" in section
    assert "- Emphasised techniques: none" in section and "- Watching for: none" in section
    assert "- Planned rounds: the settings default" in section and "- Why: none given" in section
    assert "- Retrieval angles:" not in section and "- Rubric emphasis:" not in section


def test_learned_section_is_last_and_lists_the_patterns_written(result):
    result.reflection = make_reflection()
    md = render_markdown(result, make_patterns())
    assert md.index("## 9. Trace summary") < md.index("## 10. What the system learned")
    section = md[md.index("## 10. What the system learned"):]
    assert "- the pinned data-source chunks reached every idea" in section
    assert "- the second creativity round added no strong idea" in section
    assert "- stop at one round when round one already has three strong ideas" in section
    assert "- Signal quality: retrieval changed the ideas" in section
    assert "- Winning technique: analogical" in section
    assert "- Wasted effort: the second retrieval round added four chunks nobody cited" in section
    assert (
        "- [process|global] one creativity round is enough when three ideas clear the bar "
        "(confidence 0.70, observations 2, tags: loop, cost)"
    ) in section
    assert "- [pitfall|data] a dashboard without a decision scores low on demoability (confidence 0.50, observations 1)" in section


def test_learned_section_is_omitted_without_a_reflection(result):
    assert result.reflection is None
    assert "## 10. What the system learned" not in render_markdown(result, make_patterns())


def test_learned_section_says_none_new_when_nothing_was_written(result):
    result.reflection = make_reflection()
    md = render_markdown(result)
    assert NO_NEW_PATTERNS in md[md.index("### Meta-patterns written"):]


def test_learned_section_survives_an_empty_reflection(result):
    result.reflection = RunReflection(run_id="abc123")
    section = render_markdown(result, [])[render_markdown(result, []).index("## 10."):]
    assert "### What worked\n\n- none" in section and "### Signals" not in section
    assert section.endswith("\n") and not section.endswith("\n\n")


def test_render_strategy_standalone_is_watermarked_under_the_mock():
    strategy = make_strategy()
    md = render_strategy(strategy, True)
    assert md.splitlines()[0] == BANNER_LINE and md.splitlines()[2] == "# Strategy"
    assert "- Problem type: data" in md and md.endswith("\n")
    assert PLACEHOLDER_BANNER not in render_strategy(strategy, False)
    assert render_strategy(strategy, False).splitlines()[0] == "# Strategy"


def test_strategy_dict_round_trips_with_the_notice():
    strategy = make_strategy()
    d = strategy_dict(strategy, True)
    assert d["placeholder_notice"] == PLACEHOLDER_BANNER and d["is_placeholder"] is True
    assert Strategy.from_dict(d["strategy"]).to_dict() == strategy.to_dict()
    assert "placeholder_notice" not in strategy_dict(strategy, False)


def test_render_reflection_standalone():
    reflection, patterns = make_reflection(), make_patterns()
    md = render_reflection(reflection, patterns, True)
    lines = md.splitlines()
    assert lines[0] == BANNER_LINE
    assert lines[2] == "# What the system learned: AI for climate resilience"
    assert lines[4] == "Run `abc123` · 2026-01-02T03:04:05+00:00 · provider mock"
    assert "### Meta-patterns written" in md and "- [pitfall|data]" in md
    assert PLACEHOLDER_BANNER not in render_reflection(reflection, patterns, False)


def test_reflection_dict_round_trips_with_the_notice():
    reflection, patterns = make_reflection(), make_patterns()
    d = reflection_dict(reflection, patterns, True)
    assert d["placeholder_notice"] == PLACEHOLDER_BANNER
    assert RunReflection.from_dict(d["reflection"]).to_dict() == reflection.to_dict()
    assert [MetaPattern.from_dict(p).id for p in d["meta_patterns"]] == [p.id for p in patterns]
    assert "placeholder_notice" not in reflection_dict(reflection, patterns, False)


def test_both_meta_sections_together_keep_the_baseline_headings(result):
    result.strategy = make_strategy()
    result.reflection = make_reflection()
    md = render_markdown(result, make_patterns())
    positions = [md.index(h) for h in ["## 1a. Strategy", *SECTION_HEADINGS, "## 10. What the system learned"]]
    assert positions == sorted(positions)
    assert md.endswith("\n") and not md.endswith("\n\n")
