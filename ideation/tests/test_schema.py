"""docs/DESIGN.md §4.2: builders, for_api stripping, validate, coerce."""

from __future__ import annotations

import pytest

from ideate.llm.schema import arr, bool_, coerce, enum, for_api, int_, num, obj, str_, validate

_STRIPPED = ("minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems", "pattern")


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


# --------------------------------------------------------------------------- builders
def test_obj_is_closed_and_requires_all_props_by_default():
    s = obj({"a": str_(), "b": int_()})
    assert s["type"] == "object"
    assert s["additionalProperties"] is False
    assert s["required"] == ["a", "b"]


def test_obj_honours_explicit_required_and_description():
    s = obj({"a": str_(), "b": int_()}, required=["a"], description="d")
    assert s["required"] == ["a"]
    assert s["description"] == "d"


def test_obj_copies_props_dict():
    props = {"a": str_()}
    s = obj(props)
    props["b"] = str_()
    assert "b" not in s["properties"]


def test_arr_bounds_are_optional_ints():
    assert arr(str_()) == {"type": "array", "items": {"type": "string"}}
    s = arr(str_(), 1, 4.0)
    assert s["minItems"] == 1 and s["maxItems"] == 4 and isinstance(s["maxItems"], int)


def test_scalar_builders():
    assert str_() == {"type": "string"}
    assert str_("x")["description"] == "x"
    assert num() == {"type": "number"}
    assert num(1, 5) == {"type": "number", "minimum": 1, "maximum": 5}
    assert int_(0, 24) == {"type": "integer", "minimum": 0, "maximum": 24}
    assert bool_() == {"type": "boolean"}
    assert enum(("a", "b")) == {"type": "string", "enum": ["a", "b"]}


def test_enum_rejects_empty():
    with pytest.raises(ValueError):
        enum([])


# --------------------------------------------------------------------------- for_api
NESTED = obj(
    {
        "ideas": arr(
            obj({"title": str_(), "hours": int_(1, 24), "score": num(0, 10), "tags": arr(enum(["x", "y"]), 0, 2)}),
            3,
            3,
        ),
        "ok": bool_(),
        "name": {"type": "string", "minLength": 1, "maxLength": 9, "pattern": "^a", "multipleOf": 2},
    }
)


def test_for_api_strips_constraints_at_every_depth():
    api = for_api(NESTED)
    for node in _walk(api):
        if isinstance(node, dict):
            assert not (set(node) & set(_STRIPPED)), node


def test_for_api_keeps_structure_enum_and_required():
    api = for_api(NESTED)
    idea = api["properties"]["ideas"]["items"]
    assert idea["required"] == ["title", "hours", "score", "tags"]
    assert idea["additionalProperties"] is False
    assert idea["properties"]["tags"]["items"]["enum"] == ["x", "y"]
    assert api["properties"]["ok"] == {"type": "boolean"}


def test_for_api_is_a_deep_copy():
    api = for_api(NESTED)
    api["properties"]["ideas"]["items"]["properties"]["title"]["type"] = "changed"
    assert NESTED["properties"]["ideas"]["items"]["properties"]["title"]["type"] == "string"
    assert "minItems" in NESTED["properties"]["ideas"]


# --------------------------------------------------------------------------- validate
def test_validate_ok_instance_has_no_errors():
    inst = {"ideas": [{"title": "t", "hours": 3, "score": 1.5, "tags": ["x"]}] * 3, "ok": True, "name": "abc"}
    assert validate(inst, NESTED) == []


def test_validate_reports_missing_required_and_unexpected():
    errs = validate({"ok": True, "extra": 1}, obj({"ok": bool_(), "name": str_()}))
    assert any("missing required property 'name'" in e for e in errs)
    assert any("unexpected property 'extra'" in e for e in errs)


def test_validate_type_errors_with_paths():
    errs = validate({"ok": "yes"}, obj({"ok": bool_()}))
    assert errs == ["$.ok: expected boolean, got str"]


def test_validate_integer_vs_number_and_bool_exclusion():
    assert validate(3, int_()) == []
    assert validate(3.5, int_()) != []
    assert validate(3, num()) == []
    assert validate(True, int_()) != []
    assert validate(True, num()) != []


def test_validate_enum_and_bounds():
    assert validate("z", enum(["x", "y"])) == ["$: 'z' not in enum ['x', 'y']"]
    assert validate(0, num(1, 5)) == ["$: 0 < minimum 1"]
    assert validate(6, num(1, 5)) == ["$: 6 > maximum 5"]


def test_validate_array_items_and_sizes():
    s = arr(int_(), 2, 3)
    assert validate([1], s) == ["$: 1 items < minItems 2"]
    assert validate([1, 2, 3, 4], s) == ["$: 4 items > maxItems 3"]
    assert validate([1, "a"], s) == ["$[1]: expected integer, got str"]


def test_validate_nested_paths():
    inst = {"ideas": [{"title": 1, "hours": 3, "score": 1.0, "tags": []}] * 3, "ok": True, "name": "a"}
    errs = validate(inst, NESTED)
    assert "$.ideas[0].title: expected string, got int" in errs


# --------------------------------------------------------------------------- coerce
def test_coerce_clamps_numbers_and_truncates_arrays():
    s = obj({"score": num(1, 5), "hours": int_(1, 24), "tags": arr(str_(), 0, 2)})
    out = coerce({"score": 9, "hours": 0, "tags": ["a", "b", "c"]}, s)
    assert out == {"score": 5, "hours": 1, "tags": ["a", "b"]}
    assert validate(out, s) == []


def test_coerce_recurses_into_array_items_and_does_not_mutate():
    s = obj({"scores": arr(obj({"v": num(0, 10)}), 1, 3)})
    src = {"scores": [{"v": 11}, {"v": -1}, {"v": 5}, {"v": 7}]}
    out = coerce(src, s)
    assert [x["v"] for x in out["scores"]] == [10, 0, 5]
    assert len(src["scores"]) == 4 and src["scores"][0]["v"] == 11


def test_coerce_leaves_other_errors_for_validate():
    s = obj({"n": int_(1, 5), "items": arr(str_(), 2, 4)})
    out = coerce({"n": "x", "items": ["a"]}, s)
    assert out == {"n": "x", "items": ["a"]}
    errs = validate(out, s)
    assert any("expected integer" in e for e in errs)
    assert any("minItems" in e for e in errs)


def test_coerce_keeps_bools_and_converts_whole_floats_for_integers():
    assert coerce(True, int_(0, 1)) is True
    assert coerce(3.0, int_(1, 24)) == 3 and isinstance(coerce(3.0, int_(1, 24)), int)
