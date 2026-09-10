"""Canonical identity and resource helpers for software showcase v1."""

from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata

from .errors import ShowcaseIntegrityError


MAX_IDENTIFIER_LENGTH = 256
MAX_TITLE_LENGTH = 160
MAX_SUMMARY_LENGTH = 768
MAX_CAPABILITIES = 32
MAX_EVIDENCE_REFERENCES = 64
MAX_EVIDENCE_PER_CAPABILITY = 16
MAX_CLASSIFICATIONS_PER_CAPABILITY = 8
MAX_NON_CLAIMS_PER_CAPABILITY = 16
MAX_SERIALIZED_EVIDENCE_BYTES = 4_096
MAX_SERIALIZED_CAPABILITY_BYTES = 16_384
MAX_SERIALIZED_MANIFEST_BYTES = 262_144
MAX_SERIALIZED_CHECK_BYTES = 16_384
MAX_SERIALIZED_REPORT_BYTES = 524_288

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FINGERPRINT = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$"
)
_MODULE = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$")
_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def canonical_json(document: object) -> str:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def semantic_sha256(prefix: str, document: object) -> str:
    digest = sha256(canonical_json(document).encode("utf-8")).hexdigest()
    return f"{prefix}-sha256-{digest}"


def identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise ShowcaseIntegrityError(f"{field_name} must be a bounded identifier")
    return value


def fingerprint(value: object, field_name: str) -> str:
    value = identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise ShowcaseIntegrityError(f"{field_name} must be a SHA-256 identity")
    return value


def bounded_text(value: object, field_name: str, maximum: int) -> str:
    if type(value) is not str:
        raise ShowcaseIntegrityError(f"{field_name} must be text")
    normalized = unicodedata.normalize("NFC", value)
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > maximum
        or any(
            unicodedata.category(character) in {"Cc", "Cs"}
            for character in normalized
        )
    ):
        raise ShowcaseIntegrityError(f"{field_name} violates its text bound")
    return normalized


def module_name(value: object, field_name: str) -> str:
    value = bounded_text(value, field_name, MAX_IDENTIFIER_LENGTH)
    if _MODULE.fullmatch(value) is None:
        raise ShowcaseIntegrityError(f"{field_name} must be a Python module name")
    return value


def symbol_name(value: object, field_name: str) -> str:
    value = bounded_text(value, field_name, MAX_IDENTIFIER_LENGTH)
    if _SYMBOL.fullmatch(value) is None:
        raise ShowcaseIntegrityError(f"{field_name} must be a public symbol name")
    return value


def optional_contract_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return bounded_text(value, field_name, MAX_IDENTIFIER_LENGTH)


def assert_size(document: object, maximum: int, artifact_name: str) -> None:
    try:
        size = len(canonical_json(document).encode("utf-8"))
    except (UnicodeError, TypeError, ValueError, RecursionError) as error:
        raise ShowcaseIntegrityError(
            f"serialized {artifact_name} is not canonical JSON"
        ) from error
    if size > maximum:
        raise ShowcaseIntegrityError(
            f"serialized {artifact_name} exceeds its v1 bound"
        )
