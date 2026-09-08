"""docs/DESIGN.md §4.3: deterministic generation rules and scripted answers."""

from __future__ import annotations

import json
import re

import pytest

from ideate.llm._common import RETRY_SUFFIX
from ideate.llm.base import LLM, LLMBadOutput, LLMRequest
from ideate.llm.mock import MockLLM, salient_tokens
from ideate.llm.schema import arr, bool_, enum, int_, num, obj, str_

PROMPT = "hackathon ideas for climate data with public apis and a live demo in 24 hours"


def req(tag="creativity", schema=None, prompt=PROMPT, system="sys"):
    return LLMRequest(system=system, prompt=prompt, tag=tag, json_schema=schema)


# --------------------------------------------------------------------------- basics
def test_protocol_and_identity(mock_llm):
    assert isinstance(mock_llm, LLM)
    assert mock_llm.provider == "mock" and mock_llm.model == "mock-1"


def test_no_schema_text_and_response_fields(mock_llm):
    r = mock_llm.complete(req(tag="orchestrator"))
    assert r.text.startswith("[mock] orchestrator: ")
    assert len(r.text.split(": ", 1)[1].split()) == 4
    assert r.data is None
    assert r.provider == "mock" and r.model == "mock-1" and r.requested_model == "mock-1"
    assert r.input_tokens == len(PROMPT) // 4 and r.output_tokens == len(r.text) // 4
    assert re.fullmatch(r"mock-[0-9a-f]{12}", r.message_id)
    assert r.request_id is None and r.stop_reason == "end_turn" and r.fallback_ran is False


def test_records_every_request(mock_llm):
    a, b = req(tag="a"), req(tag="b")
    mock_llm.complete(a)
    mock_llm.complete(b)
    assert mock_llm.calls == [a, b]


# --------------------------------------------------------------------------- determinism
def test_same_input_twice_identical():
    schema = obj({"queries": arr(str_(), 1, 6), "n": int_(1, 10)})
    a = MockLLM(seed=0).complete(req(schema=schema))
    b = MockLLM(seed=0).complete(req(schema=schema))
    assert a.text == b.text and a.data == b.data and a.message_id == b.message_id


def test_different_tag_differs(mock_llm):
    schema = obj({"queries": arr(str_(), 1, 6)})
    a = mock_llm.complete(req(tag="research", schema=schema))
    b = mock_llm.complete(req(tag="creativity", schema=schema))
    assert a.data != b.data
    assert mock_llm.complete(req(tag="research")).text != mock_llm.complete(req(tag="creativity")).text


def test_different_seed_or_prompt_differs():
    schema = obj({"queries": arr(str_(), 1, 6)})
    base = MockLLM(seed=0).complete(req(schema=schema)).data
    assert MockLLM(seed=1).complete(req(schema=schema)).data != base
    assert MockLLM(seed=0).complete(req(schema=schema, prompt=PROMPT + " more")).data != base


# --------------------------------------------------------------------------- strings
def test_arr_of_8_strings_distinct_and_prefixed(mock_llm):
    r = mock_llm.complete(req(schema=obj({"items": arr(str_(), 8, 8)})))
    items = r.data["items"]
    assert len(items) == 8 and len(set(items)) == 8
    assert all(s.startswith("[mock] items#") for s in items)
    assert [s.split(":")[0] for s in items] == [f"[mock] items#{i}" for i in range(8)]


def test_string_format_leaf_idx_words(mock_llm):
    schema = obj({"ideas": arr(obj({"title": str_(), "risks": arr(str_(), 3, 3)}), 2, 2), "summary": str_()})
    d = mock_llm.complete(req(schema=schema)).data
    salient = set(salient_tokens(PROMPT))
    for i, idea in enumerate(d["ideas"]):
        head, words = idea["title"].split(": ", 1)
        assert head == f"[mock] title#{i}"
        # The trailing token is a per-path marker that keeps array siblings distinguishable.
        parts = words.split()
        assert {w for w in parts if not w.startswith("mk")} <= salient
        assert len(parts) == 5 and parts[-1].startswith("mk")
        assert [r.split(":")[0] for r in idea["risks"]] == [f"[mock] risks#{j}" for j in range(3)]
    assert d["summary"].startswith("[mock] summary: ")


def test_salient_tokens_frequency_then_alphabetical_and_padding():
    toks = salient_tokens("beta alpha alpha gamma gamma gamma the of BETA")
    assert toks[0] == "gamma"  # most frequent first
    assert toks[1:3] == ["alpha", "beta"]  # alpha and beta tie at 2 -> alphabetical
    assert "the" not in toks and "of" not in toks
    assert salient_tokens("") == ["mock"] * 4
    assert salient_tokens("one two") == ["one", "two", "mock", "mock"]
    long = " ".join(f"w{i:02d}" for i in range(40))
    assert len(salient_tokens(long)) == 24


def test_mock_tokenizer_is_own_and_unstemmed():
    assert "ideas" in salient_tokens("ideas ideas") and "apis" in salient_tokens("apis")


# --------------------------------------------------------------------------- numbers / booleans / enums
def test_numbers_are_midpoints(mock_llm):
    schema = obj({"score": num(1, 5), "rel": num(0, 10), "hours": int_(1, 24), "free": num(), "ifree": int_(), "lo": int_(10)})
    d = mock_llm.complete(req(schema=schema)).data
    assert d["score"] == 3.0 and isinstance(d["score"], float)
    assert d["rel"] == 5.0
    assert d["hours"] == 12 and isinstance(d["hours"], int)
    assert d["free"] == 5.0 and d["ifree"] == 5
    assert d["lo"] == 10


def test_booleans_false(mock_llm):
    assert mock_llm.complete(req(schema=obj({"disqualified": bool_()}))).data == {"disqualified": False}


def test_enum_arrays_are_permutations(mock_llm):
    ids = ["idea-1-1", "idea-1-2", "idea-1-3", "idea-1-4"]
    schema = obj({"evaluations": arr(obj({"idea_id": enum(ids), "score": num(1, 5)}), len(ids), len(ids)), "technique": enum(["a", "b"])})
    d = mock_llm.complete(req(tag="judge:x", schema=schema)).data
    assert [e["idea_id"] for e in d["evaluations"]] == ids
    assert d["technique"] == "a"  # top level -> index 0


def test_enum_cycles_when_array_longer_than_values(mock_llm):
    d = mock_llm.complete(req(schema=obj({"t": arr(enum(["a", "b", "c"]), 5, 5)}))).data
    assert d["t"] == ["a", "b", "c", "a", "b"]


def test_enum_uses_innermost_index(mock_llm):
    schema = obj({"outer": arr(obj({"inner": arr(enum(["p", "q", "r"]), 2, 2)}), 3, 3)})
    d = mock_llm.complete(req(schema=schema)).data
    assert [o["inner"] for o in d["outer"]] == [["p", "q"]] * 3


# --------------------------------------------------------------------------- arrays
@pytest.mark.parametrize(
    "min_items,max_items,expected",
    [(None, None, 2), (1, 6, 2), (0, 5, 2), (3, 6, 3), (8, 8, 8), (0, 0, 0), (0, 1, 0), (1, 1, 1), (5, None, 5)],
)
def test_array_sizes(mock_llm, min_items, max_items, expected):
    d = mock_llm.complete(req(schema=obj({"xs": arr(str_(), min_items, max_items)}))).data
    assert len(d["xs"]) == expected


def test_coverage_gaps_has_two_entries_and_everything_validates(mock_llm):
    ids = ["c1", "c2", "c3"]
    schema = obj({"trends": arr(str_(), 1, 5), "citations": arr(enum(ids), 0, len(ids)), "coverage_gaps": arr(str_(), 0, 4)})
    r = mock_llm.complete(req(tag="research", schema=schema))
    assert len(r.data["coverage_gaps"]) == 2
    assert r.data["citations"] == ["c1", "c2"]
    assert json.loads(r.text) == r.data


def test_all_strings_start_with_mock(mock_llm):
    schema = obj({"a": str_(), "b": arr(obj({"c": str_(), "d": arr(str_(), 2, 2)}), 2, 2)})
    d = mock_llm.complete(req(schema=schema)).data

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for v in node.values():
                yield from strings(v)
        elif isinstance(node, list):
            for v in node:
                yield from strings(v)

    found = list(strings(d))
    assert found and all(s.startswith("[mock]") for s in found)


def test_generate_direct_and_unknown_type_raises(mock_llm):
    assert mock_llm.generate(int_(1, 3), "x", "t", "p") == 2
    assert mock_llm.generate(str_(), "", "t", "p").startswith("[mock] value: ")
    with pytest.raises(ValueError):
        mock_llm.generate({"type": "date"}, "d")


# --------------------------------------------------------------------------- scripted
def test_scripted_dict_entries_consumed_fifo_then_synthesized():
    schema = obj({"queries": arr(str_(), 1, 6)})
    first, second = {"queries": ["one"]}, {"queries": ["two", "three"]}
    m = MockLLM(scripted={"orchestrator": [first, second]})
    r1 = m.complete(req(tag="orchestrator", schema=schema))
    r2 = m.complete(req(tag="orchestrator", schema=schema))
    r3 = m.complete(req(tag="orchestrator", schema=schema))
    assert r1.data == first and r1.text == json.dumps(first)
    assert r2.data == second
    assert r3.data["queries"][0].startswith("[mock] queries#0")
    assert m.remaining_scripts() == {"orchestrator": 0}


def test_scripted_str_entry_is_plain_text():
    m = MockLLM(scripted={"probe": ["hello there"]})
    r = m.complete(req(tag="probe"))
    assert r.text == "hello there" and r.data is None
    assert r.output_tokens == len("hello there") // 4


def test_scripted_prefix_lookup_for_judge_tags():
    ids = ["idea-1-1"]
    schema = obj({"evaluations": arr(obj({"idea_id": enum(ids)}), 1, 1)})
    entry = {"evaluations": [{"idea_id": "idea-1-1"}]}
    exact = {"evaluations": [{"idea_id": "idea-1-1"}]}
    m = MockLLM(scripted={"judge": [entry], "judge:special": [exact]})
    assert m.complete(req(tag="judge:x", schema=schema)).data == entry
    assert m.complete(req(tag="judge:special", schema=schema)).data == exact
    assert m.remaining_scripts() == {"judge": 0, "judge:special": 0}
    # exhausted -> synthesized, still valid
    assert m.complete(req(tag="judge:x", schema=schema)).data == entry


def test_scripted_does_not_mutate_caller_list():
    entries = [{"queries": ["a"]}]
    m = MockLLM(scripted={"orchestrator": entries})
    m.complete(req(tag="orchestrator", schema=obj({"queries": arr(str_(), 1, 6)})))
    assert entries == [{"queries": ["a"]}]


def test_scripted_dict_is_coerced():
    schema = obj({"score": num(1, 5), "tags": arr(str_(), 0, 1)})
    m = MockLLM(scripted={"judge": [{"score": 9, "tags": ["a", "b"]}]})
    assert m.complete(req(tag="judge:p", schema=schema)).data == {"score": 5, "tags": ["a"]}


def test_scripted_invalid_entry_triggers_one_retry_with_suffix_then_ok():
    schema = obj({"queries": arr(str_(), 1, 6)})
    good = {"queries": ["fixed"]}
    m = MockLLM(scripted={"orchestrator": [{"wrong": 1}, good]})
    r = m.complete(req(tag="orchestrator", schema=schema))
    assert r.data == good
    assert len(m.calls) == 2
    assert m.calls[0].prompt == PROMPT
    assert m.calls[1].prompt.startswith(PROMPT + "\n\nYour previous output failed validation: ")
    assert m.calls[1].prompt.endswith("Return only JSON matching the schema.")
    assert "missing required property 'queries'" in m.calls[1].prompt
    assert RETRY_SUFFIX.split("{errors}")[0] in m.calls[1].prompt


def test_two_invalid_entries_raise_bad_output():
    schema = obj({"queries": arr(str_(), 1, 6)})
    m = MockLLM(scripted={"orchestrator": ["not json", {"queries": []}]})
    with pytest.raises(LLMBadOutput) as ei:
        m.complete(req(tag="orchestrator", schema=schema))
    assert "minItems" in str(ei.value)
    assert len(m.calls) == 2
    assert "invalid JSON" in m.calls[1].prompt


def test_invalid_scripted_then_synthesized_retry_recovers():
    schema = obj({"queries": arr(str_(), 1, 6)})
    m = MockLLM(scripted={"orchestrator": [{"queries": "not-a-list"}]})
    r = m.complete(req(tag="orchestrator", schema=schema))
    assert r.data["queries"][0].startswith("[mock] queries#0")
    assert len(m.calls) == 2
