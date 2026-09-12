"""Canonical identity, scalar, and resource helpers for Stage 9A."""

from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import TypeAlias
import unicodedata

from .errors import PlanningFailureCode, PlanningValidationError


SCHEMA_VERSION = "1.0.0"
MAX_IDENTIFIER_LENGTH = 256
MAX_TEXT_LENGTH = 768
MAX_DESCRIPTION_BYTES = 1_048_576
MAX_LINKS = 64
MAX_ROBOT_JOINTS = 64
MAX_CHAIN_JOINTS = 16
MAX_PLANNING_JOINTS = 8
MAX_COLLISION_OBJECTS = 16
MAX_WAYPOINTS = 129
MAX_JSON_NODES = 40_000
MAX_SERIALIZED_ARTIFACT_BYTES = 2_097_152

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._:/-][a-z0-9]+)*$")
_FINGERPRINT = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$"
)


def canonical_json(value: JSONValue) -> str:
    stack: list[JSONValue] = [value]
    nodes = 0
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise PlanningValidationError(
                PlanningFailureCode.RESOURCE_LIMIT,
                "canonical planning document exceeds its node bound",
            )
        if type(current) is float and not math.isfinite(current):
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_ARTIFACT,
                "canonical planning document contains a non-finite number",
            )
        if type(current) is list:
            stack.extend(reversed(current))
        elif type(current) is dict:
            if not all(type(key) is str for key in current):
                raise PlanningValidationError(
                    PlanningFailureCode.MALFORMED_ARTIFACT,
                    "canonical planning document contains a non-text key",
                )
            stack.extend(reversed(list(current.values())))
        elif type(current) not in {type(None), bool, int, float, str}:
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_ARTIFACT,
                "canonical planning document contains an unsupported value",
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
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            "planning document is not canonical JSON",
        ) from error


def semantic_sha256(prefix: str, value: JSONValue) -> str:
    digest = sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-sha256-{digest}"


def content_identity(prefix: str, document: dict[str, JSONValue]) -> tuple[str, str]:
    content_fingerprint = semantic_sha256(f"{prefix}-content", document)
    identity = semantic_sha256(prefix, {"content_fingerprint": content_fingerprint})
    return identity, content_fingerprint


def identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded identifier",
        )
    return value


def fingerprint(value: object, field_name: str) -> str:
    value = identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a typed SHA-256 fingerprint",
        )
    return value


def bounded_text(value: object, field_name: str, maximum: int = MAX_TEXT_LENGTH) -> str:
    if type(value) is not str:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be text",
        )
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > maximum
        or any(unicodedata.category(character) in {"Cc", "Cs"} for character in normalized)
    ):
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} violates its text bound",
        )
    return normalized


def finite_float(value: object, field_name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise PlanningValidationError(
            PlanningFailureCode.NONFINITE_POSITION,
            f"{field_name} must be an explicit finite float",
        )
    return value


def finite_vector(value: object, field_name: str, length: int) -> tuple[float, ...]:
    if type(value) not in {tuple, list} or len(value) != length:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must contain exactly {length} floats",
        )
    return tuple(finite_float(item, field_name) for item in value)


def bounded_items(
    value: object,
    field_name: str,
    item_type: type,
    maximum: int,
    *,
    allow_empty: bool = False,
) -> tuple:
    if type(value) not in {tuple, list}:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded sequence",
        )
    items = tuple(value)
    if (not allow_empty and not items) or len(items) > maximum:
        raise PlanningValidationError(
            PlanningFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its resource bound",
        )
    if any(type(item) is not item_type for item in items):
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} contains an invalid item",
        )
    return items


def assert_artifact_size(document: dict[str, JSONValue], artifact_name: str) -> None:
    try:
        size = len(canonical_json(document).encode("utf-8"))
    except (UnicodeError, RecursionError) as error:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{artifact_name} is not canonical UTF-8 JSON",
        ) from error
    if size > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise PlanningValidationError(
            PlanningFailureCode.RESOURCE_LIMIT,
            f"{artifact_name} exceeds the serialized v1 bound",
        )
