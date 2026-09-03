"""JSON-schema builders, API stripping, validation and coercion (docs/DESIGN.md §4.2).

Builders always produce closed objects (additionalProperties=False, required=all props).
`for_api` strips constraint keywords the structured-output API does not accept; providers
validate against the FULL schema client-side.
"""

from __future__ import annotations

import copy
from typing import Any

_STRIP_FOR_API = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "minItems", "maxItems", "pattern"}
_KEEP_FOR_API = {"type", "properties", "required", "additionalProperties", "items", "enum", "const", "description"}


# --------------------------------------------------------------------------- builders
def obj(props: dict[str, dict], required: list[str] | None = None, description: str | None = None) -> dict:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(props),
        "required": list(props.keys()) if required is None else list(required),
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def arr(items: dict, min_items: int | None = None, max_items: int | None = None, description: str | None = None) -> dict:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if min_items is not None:
        schema["minItems"] = int(min_items)
    if max_items is not None:
        schema["maxItems"] = int(max_items)
    if description:
        schema["description"] = description
    return schema


def str_(description: str | None = None) -> dict:
    return {"type": "string", **({"description": description} if description else {})}


def num(minimum: float | None = None, maximum: float | None = None, description: str | None = None) -> dict:
    schema: dict[str, Any] = {"type": "number"}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    if description:
        schema["description"] = description
    return schema


def int_(minimum: int | None = None, maximum: int | None = None, description: str | None = None) -> dict:
    schema: dict[str, Any] = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = int(minimum)
    if maximum is not None:
        schema["maximum"] = int(maximum)
    if description:
        schema["description"] = description
    return schema


def bool_(description: str | None = None) -> dict:
    return {"type": "boolean", **({"description": description} if description else {})}


def enum(values: list[str] | tuple[str, ...], description: str | None = None) -> dict:
    vals = list(values)
    if not vals:
        raise ValueError("enum() needs at least one value; use arr(str_(), 0, 0) for an empty reference list")
    return {"type": "string", "enum": vals, **({"description": description} if description else {})}


# --------------------------------------------------------------------------- API form
def for_api(schema: dict) -> dict:
    """Deep copy with numeric/length/array-size/pattern constraints removed at every depth."""

    def _strip(node: Any) -> Any:
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in _STRIP_FOR_API:
                    continue
                if k == "properties" and isinstance(v, dict):
                    out[k] = {pk: _strip(pv) for pk, pv in v.items()}
                elif k == "items":
                    out[k] = _strip(v)
                elif k in _KEEP_FOR_API:
                    out[k] = copy.deepcopy(v)
                else:
                    out[k] = copy.deepcopy(v)
            return out
        return copy.deepcopy(node)

    return _strip(schema)


# --------------------------------------------------------------------------- validation
def _type_ok(value: Any, tp: str) -> bool:
    if tp == "object":
        return isinstance(value, dict)
    if tp == "array":
        return isinstance(value, list)
    if tp == "string":
        return isinstance(value, str)
    if tp == "boolean":
        return isinstance(value, bool)
    if tp == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if tp == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if tp == "null":
        return value is None
    return True


def validate(instance: Any, schema: dict, path: str = "$") -> list[str]:
    """Return a list of human-readable error strings (empty when valid)."""
    errors: list[str] = []
    tp = schema.get("type")
    if tp is not None:
        types = tp if isinstance(tp, list) else [tp]
        if not any(_type_ok(instance, t) for t in types):
            errors.append(f"{path}: expected {tp}, got {type(instance).__name__}")
            return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: {instance!r} != const {schema['const']!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} > maximum {schema['maximum']}")
    if isinstance(instance, dict) and (tp == "object" or "properties" in schema):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property {req!r}")
        if schema.get("additionalProperties") is False:
            for k in instance:
                if k not in props:
                    errors.append(f"{path}: unexpected property {k!r}")
        for k, sub in props.items():
            if k in instance:
                errors.extend(validate(instance[k], sub, f"{path}.{k}"))
    if isinstance(instance, list) and (tp == "array" or "items" in schema):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: {len(instance)} items < minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: {len(instance)} items > maxItems {schema['maxItems']}")
        items = schema.get("items")
        if isinstance(items, dict):
            for i, v in enumerate(instance):
                errors.extend(validate(v, items, f"{path}[{i}]"))
    return errors


def coerce(instance: Any, schema: dict) -> Any:
    """Deep copy with numbers clamped into [minimum, maximum] and arrays truncated to maxItems."""
    return _coerce(copy.deepcopy(instance), schema)


def _coerce(value: Any, schema: dict) -> Any:
    tp = schema.get("type")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if "minimum" in schema and value < schema["minimum"]:
            value = schema["minimum"]
        if "maximum" in schema and value > schema["maximum"]:
            value = schema["maximum"]
        if tp == "integer" and isinstance(value, float) and value.is_integer():
            value = int(value)
        return value
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            value = value[: schema["maxItems"]]
        items = schema.get("items")
        if isinstance(items, dict):
            return [_coerce(v, items) for v in value]
        return value
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k, sub in props.items():
            if k in value:
                value[k] = _coerce(value[k], sub)
        return value
    return value
