"""Bounded canonical primitives for Stage 9D evidence."""

from __future__ import annotations

from hashlib import sha256
import json
from math import copysign, isfinite
import re
from typing import TypeAlias
import unicodedata

from .errors import GraspInteractionFailureCode, GraspInteractionValidationError


JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

SCHEMA_VERSION = "1.0.0"
MAX_IDENTIFIER_BYTES = 256
MAX_TEXT_BYTES = 512
MAX_SERIALIZED_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_CANONICAL_JSON_NODES = 500_000

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._:/-][a-z0-9]+)*$")
_FINGERPRINT = re.compile(
    r"^[a-z0-9]+(?:[._:/-][a-z0-9]+)*-sha256-[0-9a-f]{64}$"
)


def canonical_json(value: JSONValue) -> str:
    """Return the one accepted JSON spelling for a bounded value graph."""

    stack: list[object] = [value]
    nodes = 0
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > MAX_CANONICAL_JSON_NODES:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RESOURCE_LIMIT,
                "canonical JSON exceeds its node bound",
            )
        if current is None or type(current) in {bool, int, str}:
            continue
        if type(current) is float:
            if not isfinite(current):
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.NONFINITE_VALUE,
                    "canonical JSON cannot contain non-finite numbers",
                )
            if current == 0.0 and copysign(1.0, current) < 0.0:
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                    "negative zero is not canonical JSON",
                )
            continue
        if type(current) is list:
            stack.extend(reversed(current))
            continue
        if type(current) is dict:
            if any(type(key) is not str for key in current):
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                    "canonical JSON object keys must be strings",
                )
            stack.extend(reversed(tuple(current.values())))
            continue
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"unsupported canonical JSON value: {type(current).__name__}",
        )
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (OverflowError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            "value cannot be serialized canonically",
        ) from error


def content_identity(prefix: str, document: dict[str, JSONValue]) -> tuple[str, str]:
    digest = sha256(canonical_json(document).encode("utf-8")).hexdigest()
    return f"{prefix}-sha256-{digest}", f"{prefix}-content-sha256-{digest}"


def semantic_fingerprint(prefix: str, document: JSONValue) -> str:
    digest = sha256(canonical_json(document).encode("utf-8")).hexdigest()
    return f"{prefix}-sha256-{digest}"


def identifier(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be text",
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be valid UTF-8",
        ) from error
    if (
        not value
        or len(encoded) > MAX_IDENTIFIER_BYTES
        or unicodedata.normalize("NFC", value) != value
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} is not a canonical identifier",
        )
    return value


def bounded_text(value: object, field_name: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be non-empty trimmed text",
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be valid UTF-8",
        ) from error
    if len(encoded) > maximum or unicodedata.normalize("NFC", value) != value:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its text bound",
        )
    return value


def fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} is not a canonical content fingerprint",
        )
    return value


def finite_float(value: object, field_name: str) -> float:
    if type(value) is not float or not isfinite(value):
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.NONFINITE_VALUE,
            f"{field_name} must be a finite explicit float",
        )
    if value == 0.0 and copysign(1.0, value) < 0.0:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} cannot be negative zero",
        )
    return value


def bounded_integer(value: object, field_name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its integer bound",
        )
    return value


def assert_artifact_size(document: dict[str, JSONValue], artifact_name: str) -> None:
    if len(canonical_json(document).encode("utf-8")) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.RESOURCE_LIMIT,
            f"{artifact_name} exceeds its serialized byte bound",
        )
