"""Conservative identity and JSON normalization for validation policy version 1."""

from __future__ import annotations

import json
import math
import unicodedata

from ayyo_memory import JSONValue

from .errors import CyclicValueError, NormalizationError, UnsupportedValueError


def normalize_identity_text(value: object, *, field_name: str = "identity") -> str:
    """Normalize identity text with NFC and collapsed Unicode whitespace."""

    if not isinstance(value, str):
        raise NormalizationError(f"{field_name} must be a string")
    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise NormalizationError(f"{field_name} must contain non-whitespace text")
    return normalized


def _validate_json_tree(value: object) -> None:
    stack: list[tuple[object, bool]] = [(value, False)]
    active_container_ids: set[int] = set()

    while stack:
        current, leaving = stack.pop()
        if leaving:
            active_container_ids.remove(id(current))
            continue

        if current is None or isinstance(current, (str, bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise UnsupportedValueError("JSON values cannot contain non-finite numbers")
            continue
        if isinstance(current, list):
            identity = id(current)
            if identity in active_container_ids:
                raise CyclicValueError("JSON values cannot contain reference cycles")
            active_container_ids.add(identity)
            stack.append((current, True))
            stack.extend((item, False) for item in reversed(current))
            continue
        if isinstance(current, dict):
            identity = id(current)
            if identity in active_container_ids:
                raise CyclicValueError("JSON values cannot contain reference cycles")
            for key in current:
                if not isinstance(key, str):
                    raise UnsupportedValueError("JSON object keys must be strings")
            active_container_ids.add(identity)
            stack.append((current, True))
            stack.extend((item, False) for item in reversed(tuple(current.values())))
            continue
        raise UnsupportedValueError("values must contain only JSON-compatible data")


def canonicalize_json(value: object) -> str:
    """Return a stable JSON representation without changing value semantics."""

    _validate_json_tree(value)
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (OverflowError, RecursionError, TypeError, ValueError) as error:
        raise UnsupportedValueError(
            "value cannot be represented as deterministic JSON"
        ) from error


def copy_json(value: object) -> JSONValue:
    """Validate and return an independent JSON-compatible copy."""

    canonical = canonicalize_json(value)
    try:
        return json.loads(canonical)
    except (RecursionError, ValueError) as error:
        raise UnsupportedValueError("value is too deeply nested to copy safely") from error
