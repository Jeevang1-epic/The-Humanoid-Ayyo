"""Canonical identity and resource-validation helpers for policy registry v1."""

from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata

from .errors import PolicyRegistryIntegrityError


MAX_IDENTIFIER_LENGTH = 256
MAX_NOTE_LENGTH = 512
MAX_REGISTERED_VERSIONS = 64
MAX_POLICY_FAMILIES = 16
MAX_SERIALIZED_REQUEST_BYTES = 16_384
MAX_SERIALIZED_RECORD_BYTES = 16_384
MAX_SERIALIZED_SNAPSHOT_BYTES = 262_144
MAX_SERIALIZED_RESULT_BYTES = 524_288

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
_FINGERPRINT = re.compile(
    r'^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$'
)


def canonical_json(document: object) -> str:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )


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
        raise PolicyRegistryIntegrityError(f'{field_name} must be a bounded identifier')
    return value


def fingerprint(value: object, field_name: str) -> str:
    value = identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise PolicyRegistryIntegrityError(f'{field_name} must be a SHA-256 identity')
    return value


def semantic_version(value: object, field_name: str) -> str:
    if type(value) is not str or _SEMVER.fullmatch(value) is None:
        raise PolicyRegistryIntegrityError(f'{field_name} must be a semantic version')
    return value


def optional_note(value: object, field_name: str = 'note') -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise PolicyRegistryIntegrityError(f'{field_name} must be text or null')
    normalized = unicodedata.normalize('NFC', value)
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > MAX_NOTE_LENGTH
        or any(unicodedata.category(character) in {'Cc', 'Cs'} for character in normalized)
    ):
        raise PolicyRegistryIntegrityError(f'{field_name} violates the v1 text bound')
    return normalized


def assert_size(document: object, maximum: int, artifact_name: str) -> None:
    if len(canonical_json(document).encode('utf-8')) > maximum:
        raise PolicyRegistryIntegrityError(
            f'serialized {artifact_name} exceeds its v1 bound'
        )
