"""CreativityAgent, validate_idea and the diversity filter (docs/DESIGN.md §9.4)."""

from __future__ import annotations

import pytest

from ideate.agents.context import RunContext, TracingLLM, constraints_block
from ideate.agents.creativity import (
    GENERIC_USERS,
    CreativityAgent,
    batch_schema,
    diverse,
    idea_schema,
    jaccard,
    simple_tokens,
    validate_idea,
)
from ideate.config import Settings
from ideate.evaluation.rubric import DEFAULT_RUBRIC
from ideate.evaluation.scoring import aggregate
from ideate.llm.base import LLMBadOutput
from ideate.llm.mock import MockLLM
from ideate.memory.store import MemoryStore
from ideate.models import TECHNIQUES, CriterionScore, HackathonConstraints, Idea, IdeaEvaluation, IdeationState, PanelVerdict, TechnicalAssessment


def make_ctx(kb, tmp_path, llm=None, **overrides) -> RunContext:
    settings = Settings(provider="mock", memory_path=str(tmp_path / "memory.jsonl"), **overrides)
    trace = []
    return RunContext(TracingLLM(llm or MockLLM(seed=0), trace, settings), kb, MemoryStore(tmp_path / "memory.jsonl"), DEFAULT_RUBRIC, settings, trace)


def good_idea(**kw) -> Idea:
    base = dict(
        title="Flood alert for river wardens",
        description="Alerts wardens when a gauge rises",
        one_liner="gauge based alerts",
        target_user="volunteer river warden on night duty",
        demo_moment="the gauge crosses the line and the phone buzzes",
        data_sources=["USGS water — access: none — gauge readings"],
        build_hours_estimate=12,
    )
    base.update(kw)
    return Idea(**base)


def raw_idea(title: str, **kw) -> dict:
    d = dict(
        title=title, one_liner=f"{title} in a sentence", description="what it does", target_user="night nurse on a ward",
        key_innovation="k", technique="direct", technical_approach="python", demo_strategy="live", demo_moment="a b c d e",
        data_sources=["x — access: none — y"], mvp_scope=["m"], cut_first=["c"], closest_existing="", build_hours_estimate=8,
        risks=["r"], citations=[],
    )
    d.update(kw)
    return d


def prepared_state(ctx: RunContext, theme: str = "AI for climate resilience", **constraints) -> IdeationState:
    state = IdeationState(theme, HackathonConstraints(**constraints))
    state.knowledge = ctx.retrieve(theme, k=6)
    state.assessment = TechnicalAssessment(building_blocks=["Open-Meteo — access: none — forecasts"])
    return state


# --------------------------------------------------------------------------- validate_idea
def test_validate_idea_accepts_a_good_idea():
    assert validate_idea(good_idea(), HackathonConstraints()) == []


@pytest.mark.parametrize("user", ["", "  ", "Users", "developers", " Everyone "])
def test_validate_idea_flags_generic_or_empty_user(user):
    flags = validate_idea(good_idea(target_user=user), HackathonConstraints())
    assert len(flags) == 1 and "target_user" in flags[0]
    assert GENERIC_USERS == {"users", "people", "businesses", "everyone", "companies", "students", "developers", "consumers"}


def test_validate_idea_flags_data_demo_hours_and_must_avoid():
    c = HackathonConstraints(hours=10, must_avoid=["blockchain", "voice assistant"])
    flags = validate_idea(
        good_idea(data_sources=[], demo_moment="three words only", build_hours_estimate=11, technical_approach="a blockchain ledger"), c
    )
    assert len(flags) == 4
    assert any("data_sources" in f for f in flags)
    assert any("demo_moment" in f for f in flags)
    assert any("build_hours_estimate" in f for f in flags)
    assert any("'blockchain'" in f for f in flags)


def test_must_avoid_matches_stemmed_tokens_and_phrases():
    c = HackathonConstraints(must_avoid=["chatbot", "voice assistant"])
    assert validate_idea(good_idea(title="Chatbots for wardens"), c) == ["uses must-avoid term 'chatbot'"]
    assert validate_idea(good_idea(description="an assistant with voice input"), c) == ["uses must-avoid term 'voice assistant'"]
    assert validate_idea(good_idea(description="a voice memo"), c) == []


# --------------------------------------------------------------------------- diversity
def test_jaccard_and_simple_tokens():
    assert simple_tokens("[mock] Title#0: Foo-bar") == {"mock", "title", "0", "foo", "bar"}
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a", "b", "c"}, {"a", "d"}) == 0.25
    assert jaccard(set(), set()) == 0.0


def test_diverse_drops_later_near_duplicates_including_previous_rounds():
    earlier = [Idea("Flood alert for river wardens", "", one_liner="gauge based alerts")]
    dup = Idea("Flood alerts for river wardens", "", one_liner="gauge based alert")
    fresh = Idea("Bus delay explainer", "", one_liner="why the bus is late")
    twin_of_fresh = Idea("Bus delay explainer", "", one_liner="why the bus is late now")
    assert diverse([dup, fresh, twin_of_fresh], earlier) == [fresh]
    assert diverse([dup], []) == [dup]


# --------------------------------------------------------------------------- schema
def test_idea_schema_shape():
    s = idea_schema(["c1", "c2"], 24)
    assert s["properties"]["technique"]["enum"] == list(TECHNIQUES)
    assert s["properties"]["build_hours_estimate"] == {"type": "integer", "minimum": 1, "maximum": 24}
    assert s["properties"]["citations"]["items"]["enum"] == ["c1", "c2"]
    assert "parent_id" not in s["properties"]
    s2 = idea_schema([], 24, ["idea-1-1", "idea-1-2"])
    assert s2["properties"]["parent_id"]["enum"] == ["idea-1-1", "idea-1-2", "new"]
    assert s2["properties"]["citations"]["maxItems"] == 0
    b = batch_schema(3, [], 24)
    assert (b["properties"]["ideas"]["minItems"], b["properties"]["ideas"]["maxItems"]) == (3, 3)


# --------------------------------------------------------------------------- agent
def test_round_one_under_mock(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock, ideas_per_round=8)
    state = prepared_state(ctx, must_avoid=["blockchain"])
    CreativityAgent().run(state, ctx)
    assert state.iteration == 1
    # Ids stay sequential; the count reflects both dedup stages, which the mock exercises.
    assert [i.id for i in state.ideas] == [f"idea-1-{k}" for k in range(1, len(state.ideas) + 1)]
    assert len(state.ideas) + state.dropped_duplicate == 8
    # Techniques still cycle in order; dedup may remove members, so this is a subsequence.
    cycle = [TECHNIQUES[k % 6] for k in range(8)]
    it = iter(cycle)
    assert all(t in it for t in [i.technique for i in state.ideas])
    assert all(i.parent_id is None for i in state.ideas)
    assert all(validate_idea(i, state.constraints) == [] for i in state.ideas)
    creativity_calls = [c for c in mock.calls if c.tag == "creativity"]
    assert len(creativity_calls) == 1
    call = creativity_calls[0]
    assert call.effort == "high"
    assert constraints_block(state.constraints) in call.prompt
    assert "Open-Meteo — access: none — forecasts" in call.prompt
    assert "technique=analogical" in call.prompt and "Antipatterns" in call.prompt
    assert "parent_id" not in call.json_schema["properties"]["ideas"]["items"]["properties"]
    shown = set(call.json_schema["properties"]["ideas"]["items"]["properties"]["citations"]["items"]["enum"])
    assert {rc.chunk.id for rc in state.knowledge} <= shown
    assert all(i.citations and set(i.citations) <= shown for i in state.ideas)
    assert ctx.queries_issued[-1] == state.theme  # the antipattern retrieval
    assert [t.agent for t in ctx.trace] == ["creativity", "dedupe"]


def test_round_two_sets_parent_ids_and_appends(kb, tmp_path):
    mock = MockLLM(seed=0)
    ctx = make_ctx(kb, tmp_path, llm=mock, ideas_per_round=8)
    state = prepared_state(ctx)
    CreativityAgent().run(state, ctx)
    first = list(state.ideas)
    for idea in first:
        ev = IdeaEvaluation(idea.id, scores=[CriterionScore(n, 3.0) for n in DEFAULT_RUBRIC.names()], weaknesses=[f"weak {idea.id}"], suggestions=["sug"])
        state.verdicts.append(PanelVerdict(idea.id, [ev], aggregate([ev], DEFAULT_RUBRIC), 1.0))
    state.ranking = [i.id for i in first]
    state.critiques = ["critique alpha", "lowest criterion: novelty"]
    CreativityAgent().run(state, ctx)
    assert state.iteration == 2
    assert state.ideas[: len(first)] == first  # append semantics; dedup sets the count
    new = state.ideas[8:]
    assert new and all(i.id.startswith("idea-2-") for i in new)
    top3 = state.ranking[:3]
    assert all(i.parent_id is None or i.parent_id in top3 for i in new)
    assert any(i.parent_id is not None for i in new) and any(i.parent_id is None for i in new)
    call = [c for c in mock.calls if c.tag == "creativity"][1]
    assert call.json_schema["properties"]["ideas"]["items"]["properties"]["parent_id"]["enum"] == top3 + ["new"]
    assert "critique alpha" in call.prompt and f"weak {top3[0]}" in call.prompt and first[0].title in call.prompt


def test_one_whole_call_retry_keeps_survivors_of_both_calls(kb, tmp_path):
    scripted = {"creativity": [{"ideas": [raw_idea("Good one"), raw_idea("Bad one", target_user="users")]}]}
    mock = MockLLM(seed=0, scripted=scripted)
    ctx = make_ctx(kb, tmp_path, llm=mock, ideas_per_round=2)
    state = prepared_state(ctx)
    CreativityAgent().run(state, ctx)
    creativity_calls = [c for c in mock.calls if c.tag == "creativity"]
    assert len(creativity_calls) == 2
    assert "Bad one" in creativity_calls[1].prompt and "target_user" in creativity_calls[1].prompt
    assert creativity_calls[1].prompt.startswith(creativity_calls[0].prompt)
    assert [i.id for i in state.ideas] == ["idea-1-1", "idea-1-2"]
    assert state.ideas[0].title == "Good one"
    assert state.ideas[1].title.startswith("[mock]")  # a survivor of the retried (synthesised) batch


def test_no_survivors_after_retry_raises(kb, tmp_path):
    bad = {"ideas": [raw_idea("Bad", target_user="people")]}
    mock = MockLLM(seed=0, scripted={"creativity": [bad, bad]})
    ctx = make_ctx(kb, tmp_path, llm=mock, ideas_per_round=1)
    state = prepared_state(ctx)
    with pytest.raises(LLMBadOutput):
        CreativityAgent().run(state, ctx)
    assert len([c for c in mock.calls if c.tag == "creativity"]) == 2
    assert state.ideas == []


def test_diversity_filter_applies_to_scripted_batch(kb, tmp_path):
    scripted = {"creativity": [{"ideas": [raw_idea("Bus delay explainer"), raw_idea("Bus delay explainer", one_liner="Bus delay explainer in a sentence")]}]}
    mock = MockLLM(seed=0, scripted=scripted)
    ctx = make_ctx(kb, tmp_path, llm=mock, ideas_per_round=2)
    state = prepared_state(ctx)
    CreativityAgent().run(state, ctx)
    assert [i.title for i in state.ideas] == ["Bus delay explainer"]
    assert state.ideas[0].id == "idea-1-1"
