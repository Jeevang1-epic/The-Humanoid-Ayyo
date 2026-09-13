"""Bounded canonical primitives for Stage 9B trajectory evidence."""

from __future__ import annotations

from hashlib import sha256
import json
from math import copysign, isfinite
import re
import unicodedata
from typing import TypeAlias

from .errors import TrajectoryFailureCode, TrajectoryValidationError


JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

SCHEMA_VERSION = "1.0.0"
MAX_TEXT_LENGTH = 512
MAX_IDENTIFIER_LENGTH = 256
MAX_SERIALIZED_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_CANONICAL_JSON_NODES = 200_000
MAX_TRAJECTORY_POINTS = 129
MAX_JOINTS = 16

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._:/-][a-z0-9]+)*$")
_FINGERPRINT = re.compile(
    r"^[a-z0-9]+(?:[._:/-][a-z0-9]+)*-sha256-[0-9a-f]{64}$"
)
_TYPED_FINGERPRINT = re.compile(r"^[a-z][a-z0-9._-]*:sha256:[0-9a-f]{64}$")


def canonical_json(value: JSONValue) -> str:
    """Return the one accepted JSON spelling for a bounded value graph."""

    stack: list[object] = [value]
    nodes = 0
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > MAX_CANONICAL_JSON_NODES:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.RESOURCE_LIMIT,
                "canonical JSON exceeds its node bound",
            )
        if current is None or type(current) in {bool, int, str}:
            continue
        if type(current) is float:
            if not isfinite(current):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.NONFINITE_VALUE,
                    "canonical JSON cannot contain non-finite numbers",
                )
            if current == 0.0 and copysign(1.0, current) < 0.0:
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.MALFORMED_ARTIFACT,
                    "negative zero is not canonical JSON",
                )
            continue
        if type(current) is list:
            stack.extend(reversed(current))
            continue
        if type(current) is dict:
            if any(type(key) is not str for key in current):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.MALFORMED_ARTIFACT,
                    "canonical JSON object keys must be strings",
                )
            stack.extend(reversed(list(current.values())))
            continue
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
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
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            "value cannot be serialized canonically",
        ) from error


def content_identity(prefix: str, document: dict[str, JSONValue]) -> tuple[str, str]:
    encoded = canonical_json(document).encode("utf-8")
    digest = sha256(encoded).hexdigest()
    return f"{prefix}-sha256-{digest}", f"{prefix}-content-sha256-{digest}"


def semantic_sha256(prefix: str, value: JSONValue) -> str:
    digest = sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-sha256-{digest}"


def identifier(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be text",
        )
    normalized = unicodedata.normalize("NFC", value)
    if (
        normalized != value
        or not value
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} is not a canonical identifier",
        )
    return value


def fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} is not a content fingerprint",
        )
    return value


def typed_fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _TYPED_FINGERPRINT.fullmatch(value) is None:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} is not a typed SHA-256 fingerprint",
        )
    return value


def bounded_text(value: object, field_name: str, maximum: int = MAX_TEXT_LENGTH) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be non-empty trimmed text",
        )
    normalized = unicodedata.normalize("NFC", value)
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be valid UTF-8",
        ) from error
    if normalized != value or len(encoded) > maximum:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its canonical text bound",
        )
    return value


def finite_float(value: object, field_name: str) -> float:
    if type(value) is not float or not isfinite(value):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.NONFINITE_VALUE,
            f"{field_name} must be a finite explicit float",
        )
    return 0.0 if value == 0.0 else value


def bounded_tuple(
    value: object,
    field_name: str,
    item_type: type,
    maximum: int,
    *,
    minimum: int = 0,
) -> tuple:
    if type(value) not in {tuple, list}:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded sequence",
        )
    items = tuple(value)
    if not minimum <= len(items) <= maximum or any(type(item) is not item_type for item in items):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its item bound or type",
        )
    return items


def assert_artifact_size(document: dict[str, JSONValue], artifact_name: str) -> None:
    if len(canonical_json(document).encode("utf-8")) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.RESOURCE_LIMIT,
            f"{artifact_name} exceeds its serialized byte bound",
        )
