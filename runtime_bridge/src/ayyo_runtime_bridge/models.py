"""Shared immutable contracts for Runtime Bridge v1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import re

from .canonical import JSONValue, canonicalize_json
from .errors import InvalidRuntimeContractError


RUNTIME_SCHEMA_VERSION = 1
MAX_RUNTIME_IDENTIFIER_LENGTH = 256
MAX_RUNTIME_TEXT_LENGTH = 16_384

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def validate_text(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception] = InvalidRuntimeContractError,
) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise error_type(f"{field_name} must be a non-empty trimmed string")
    if len(value) > MAX_RUNTIME_TEXT_LENGTH:
        raise error_type(f"{field_name} exceeds the text length limit")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise error_type(f"{field_name} contains invalid Unicode") from error
    return value


def validate_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception] = InvalidRuntimeContractError,
) -> str:
    text = validate_text(value, field_name=field_name, error_type=error_type)
    if (
        len(text) > MAX_RUNTIME_IDENTIFIER_LENGTH
        or _IDENTIFIER_PATTERN.fullmatch(text) is None
    ):
        raise error_type(
            f"{field_name} must be a lowercase ASCII identifier using '.', '-', or '_'"
        )
    return text


class RuntimeFingerprintKind(StrEnum):
    ENDPOINT = "endpoint"
    ENDPOINT_BINDING = "endpoint_binding"
    REGISTRY = "registry"
    REQUEST = "request"
    DECISION = "decision"


@dataclass(frozen=True, slots=True)
class RuntimeFingerprint:
    kind: RuntimeFingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RuntimeFingerprintKind):
            raise InvalidRuntimeContractError("runtime fingerprint kind is invalid")
        if self.algorithm != "sha256" or self.schema_version != RUNTIME_SCHEMA_VERSION:
            raise InvalidRuntimeContractError("runtime fingerprint format is unsupported")
        if (
            type(self.digest) is not str
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise InvalidRuntimeContractError(
                "runtime fingerprint digest must be lowercase SHA-256 hexadecimal"
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:sha256:{self.digest}"


def fingerprint_document(
    kind: RuntimeFingerprintKind,
    document: JSONValue,
    *,
    error_type: type[Exception] = InvalidRuntimeContractError,
) -> RuntimeFingerprint:
    if not isinstance(kind, RuntimeFingerprintKind):
        raise error_type("runtime fingerprint kind is invalid")
    canonical = canonicalize_json(
        document,
        field_name=f"{kind.value} fingerprint document",
        error_type=error_type,
    )
    return RuntimeFingerprint(
        kind=kind,
        digest=sha256(canonical.encode("utf-8")).hexdigest(),
    )
