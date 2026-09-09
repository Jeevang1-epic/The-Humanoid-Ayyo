"""Bounded canonical JSON, validation, and SHA-256 helpers."""

from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata

from .errors import PromotionControlIntegrityError


MAX_IDENTIFIER_LENGTH = 256
MAX_NOTE_LENGTH = 512
MAX_SERIALIZED_ARTIFACT_BYTES = 32_768
MAX_SEQUENCE_ITEMS = 16

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
_FINGERPRINT = re.compile(
    r'^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$'
)


def canonical_json(document: object) -> str:
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(',', ':'),
        )
    except (TypeError, ValueError) as error:
        raise PromotionControlIntegrityError(
            'control artifact is not representable as finite canonical JSON'
        ) from error


def semantic_sha256(prefix: str, document: object) -> str:
    digest = sha256(canonical_json(document).encode('utf-8')).hexdigest()
    return f'{prefix}-sha256-{digest}'


def identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise PromotionControlIntegrityError(f'{field_name} must be a bounded identifier')
    return value


def fingerprint(value: object, field_name: str) -> str:
    value = identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise PromotionControlIntegrityError(f'{field_name} must be a SHA-256 identity')
    return value


def semantic_version(value: object, field_name: str) -> str:
    if type(value) is not str or _SEMVER.fullmatch(value) is None:
        raise PromotionControlIntegrityError(f'{field_name} must be a semantic version')
    return value


def optional_note(value: object, field_name: str = 'note') -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise PromotionControlIntegrityError(f'{field_name} must be text or null')
    normalized = unicodedata.normalize('NFC', value)
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > MAX_NOTE_LENGTH
        or any(unicodedata.category(character) in {'Cc', 'Cs'} for character in normalized)
    ):
        raise PromotionControlIntegrityError(f'{field_name} violates the v1 text bound')
    return normalized


def bounded_enum_tuple(
    values: object,
    enum_type: type,
    field_name: str,
    *,
    maximum: int = MAX_SEQUENCE_ITEMS,
) -> tuple:
    if isinstance(values, (str, bytes)):
        raise PromotionControlIntegrityError(f'{field_name} must be a bounded sequence')
    try:
        snapshot = tuple(values)
    except TypeError as error:
        raise PromotionControlIntegrityError(
            f'{field_name} must be a bounded sequence'
        ) from error
    if (
        not 1 <= len(snapshot) <= maximum
        or not all(isinstance(value, enum_type) for value in snapshot)
        or len(snapshot) != len(set(snapshot))
    ):
        raise PromotionControlIntegrityError(
            f'{field_name} is empty, duplicate, invalid, or out of bounds'
        )
    return tuple(sorted(snapshot, key=lambda value: value.value))


def assert_size(document: dict[str, object]) -> None:
    if len(canonical_json(document).encode('utf-8')) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise PromotionControlIntegrityError('serialized control artifact exceeds its v1 bound')
