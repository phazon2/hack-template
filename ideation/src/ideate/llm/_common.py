"""Validation-failure policy shared by every provider (docs/DESIGN.md §4.2).

A provider implements one raw attempt (`LLMRequest -> LLMResponse` with `data=None`);
`complete_with_validation` parses, coerces and validates the text against the request's
schema, makes ONE corrective retry with the spec'd suffix, then raises `LLMBadOutput`.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable

from ideate.llm.base import LLMBadOutput, LLMRequest, LLMResponse
from ideate.llm.schema import coerce, validate

RETRY_SUFFIX = "\n\nYour previous output failed validation: {errors}. Return only JSON matching the schema."

Attempt = Callable[[LLMRequest], LLMResponse]


def parse_structured(text: str, schema: dict) -> tuple[Any, list[str]]:
    """json.loads -> coerce -> validate. Returns (data, errors); data is None on a parse error."""
    try:
        raw = json.loads(text)
    except (ValueError, TypeError) as e:
        return None, [f"$: invalid JSON: {e}"]
    data = coerce(raw, schema)
    return data, validate(data, schema)


def retry_request(request: LLMRequest, errors: list[str]) -> LLMRequest:
    """The corrective request: same request with the validation suffix appended to the prompt."""
    suffix = RETRY_SUFFIX.format(errors="; ".join(errors))
    return dataclasses.replace(request, prompt=request.prompt + suffix)


def complete_with_validation(request: LLMRequest, attempt: Attempt) -> LLMResponse:
    """Run `attempt`, enforce `request.json_schema` with one corrective retry, else LLMBadOutput."""
    schema = request.json_schema
    response = attempt(request)
    if schema is None:
        return response
    data, errors = parse_structured(response.text, schema)
    if not errors:
        return dataclasses.replace(response, data=data)
    response = attempt(retry_request(request, errors))
    data, errors = parse_structured(response.text, schema)
    if not errors:
        return dataclasses.replace(response, data=data)
    raise LLMBadOutput(f"output failed schema validation after one retry ({request.tag}): " + "; ".join(errors))
