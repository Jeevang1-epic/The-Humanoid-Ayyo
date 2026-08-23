"""Small canonical JSON and fingerprint helpers for control-owned models."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import TypeAlias

from .errors import ControlFailureCode, ControlValidationError


JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def canonical_json(value: JSONValue) -> str:
    """Return deterministic UTF-8 JSON after rejecting non-finite floats."""

    stack: list[JSONValue] = [value]
    nodes = 0
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > 10_000:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control fingerprint document exceeds its node limit",
            )
        if type(current) is float and not math.isfinite(current):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control fingerprint document contains a non-finite number",
            )
        if type(current) is list:
            stack.extend(reversed(current))
        elif type(current) is dict:
            if not all(type(key) is str for key in current):
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    "control fingerprint document contains a non-string key",
                )
            stack.extend(reversed(list(current.values())))
        elif type(current) not in {type(None), bool, int, float, str}:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control fingerprint document contains an unsupported value",
            )
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_document(value: JSONValue) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
