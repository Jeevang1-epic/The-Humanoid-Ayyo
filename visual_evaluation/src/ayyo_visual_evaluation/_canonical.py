"""Small strict canonicalization helpers for evaluation identities."""

from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import TypeAlias

from .errors import VisualEvaluationConfigurationError


CanonicalScalar: TypeAlias = None | bool | int | float | str
CanonicalValue: TypeAlias = (
    CanonicalScalar | list["CanonicalValue"] | dict[str, "CanonicalValue"]
)

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def identifier(value: object, field: str, *, maximum: int = 128) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or value.isascii() is False
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise VisualEvaluationConfigurationError(
            f"{field} must be a bounded lowercase ASCII identifier"
        )
    return value


def semver(value: object, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 64
        or value.isascii() is False
        or _SEMVER.fullmatch(value) is None
    ):
        raise VisualEvaluationConfigurationError(
            f"{field} must be one bounded canonical semantic version"
        )
    return value


def sha256_hex(value: object, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise VisualEvaluationConfigurationError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def bounded_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = (1 << 63) - 1,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise VisualEvaluationConfigurationError(
            f"{field} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def finite(value: object, field: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise VisualEvaluationConfigurationError(f"{field} must be finite")
    converted = float(value)
    return 0.0 if converted == 0.0 else converted


def canonical_json(value: CanonicalValue) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def fingerprint(value: CanonicalValue) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
