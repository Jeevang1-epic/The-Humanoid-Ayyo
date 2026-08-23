"""Immutable public models for owner-centric personal context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from ayyo_memory import JSONValue, ProvenanceType

from .errors import (
    ContextInvariantError,
    InvalidContextQueryError,
    InvalidOwnerError,
)
from .json_value import canonicalize_json, copy_json


SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_VERSION_ALGORITHM = "sha256"


class ContextState(StrEnum):
    UNKNOWN = "unknown"
    RESOLVED = "resolved"
    CONFLICTED = "conflicted"


class ContextDomain(StrEnum):
    SEMANTIC = "semantic"
    PREFERENCE = "preference"
    SOCIAL = "social"
    SPATIAL = "spatial"
    PROCEDURAL = "procedural"


def _validate_exact_text(
    value: object,
    *,
    field_name: str,
    error_type: type[ValueError] | type[ContextInvariantError],
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise error_type(f"{field_name} must not have surrounding whitespace")


def validate_owner_subject(owner_subject: object) -> None:
    _validate_exact_text(
        owner_subject,
        field_name="owner_subject",
        error_type=InvalidOwnerError,
    )


def _validate_utc(value: object, *, field_name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ContextInvariantError(f"{field_name} must be timezone-aware UTC")


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ContextIdentity:
    domain: ContextDomain
    subject: str
    predicate: str

    def __post_init__(self) -> None:
        if not isinstance(self.domain, ContextDomain):
            raise ContextInvariantError("context domain must be a ContextDomain")
        _validate_exact_text(
            self.subject,
            field_name="context subject",
            error_type=ContextInvariantError,
        )
        _validate_exact_text(
            self.predicate,
            field_name="context predicate",
            error_type=ContextInvariantError,
        )


@dataclass(frozen=True, slots=True, init=False)
class EvidenceReference:
    memory_id: UUID
    provenance_type: ProvenanceType
    provenance_source_id: str
    confidence: float
    observed_at: datetime
    recorded_at: datetime
    supersedes: UUID | None
    revision_reason: str | None
    _provenance_details: JSONValue = field(repr=False, compare=False)
    _canonical_provenance_details: str = field(repr=False)
    _metadata: JSONValue = field(repr=False, compare=False)
    _canonical_metadata: str = field(repr=False)

    def __init__(
        self,
        *,
        memory_id: UUID,
        provenance_type: ProvenanceType,
        provenance_source_id: str,
        provenance_details: Mapping[str, JSONValue],
        metadata: Mapping[str, JSONValue],
        confidence: float,
        observed_at: datetime,
        recorded_at: datetime,
        supersedes: UUID | None = None,
        revision_reason: str | None = None,
    ) -> None:
        if not isinstance(memory_id, UUID):
            raise ContextInvariantError("evidence memory_id must be a UUID")
        if not isinstance(provenance_type, ProvenanceType):
            raise ContextInvariantError(
                "evidence provenance_type must be a ProvenanceType"
            )
        _validate_exact_text(
            provenance_source_id,
            field_name="evidence provenance_source_id",
            error_type=ContextInvariantError,
        )
        if not isinstance(provenance_details, Mapping):
            raise ContextInvariantError("evidence provenance_details must be a mapping")
        details = copy_json(
            dict(provenance_details),
            field_name="evidence provenance_details",
        )
        canonical_details = canonicalize_json(
            details,
            field_name="evidence provenance_details",
        )
        if not isinstance(metadata, Mapping):
            raise ContextInvariantError("evidence metadata must be a mapping")
        metadata_copy = copy_json(dict(metadata), field_name="evidence metadata")
        canonical_metadata = canonicalize_json(
            metadata_copy,
            field_name="evidence metadata",
        )
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0
        ):
            raise ContextInvariantError(
                "evidence confidence must be a number from 0.0 to 1.0"
            )
        _validate_utc(observed_at, field_name="evidence observed_at")
        _validate_utc(recorded_at, field_name="evidence recorded_at")
        if supersedes is not None and not isinstance(supersedes, UUID):
            raise ContextInvariantError("evidence supersedes must be a UUID")
        if supersedes == memory_id:
            raise ContextInvariantError("evidence cannot supersede itself")
        if supersedes is None and revision_reason is not None:
            raise ContextInvariantError(
                "evidence revision_reason requires a superseded memory"
            )
        if supersedes is not None:
            _validate_exact_text(
                revision_reason,
                field_name="evidence revision_reason",
                error_type=ContextInvariantError,
            )
        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "provenance_type", provenance_type)
        object.__setattr__(self, "provenance_source_id", provenance_source_id)
        object.__setattr__(self, "confidence", float(confidence))
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "recorded_at", recorded_at)
        object.__setattr__(self, "supersedes", supersedes)
        object.__setattr__(self, "revision_reason", revision_reason)
        object.__setattr__(self, "_provenance_details", details)
        object.__setattr__(self, "_canonical_provenance_details", canonical_details)
        object.__setattr__(self, "_metadata", metadata_copy)
        object.__setattr__(self, "_canonical_metadata", canonical_metadata)

    @property
    def provenance_details(self) -> dict[str, JSONValue]:
        details = copy_json(
            self._provenance_details,
            field_name="evidence provenance details",
        )
        assert isinstance(details, dict)
        return details

    @property
    def metadata(self) -> dict[str, JSONValue]:
        metadata = copy_json(self._metadata, field_name="evidence metadata")
        assert isinstance(metadata, dict)
        return metadata


@dataclass(frozen=True, slots=True, init=False)
class ContextValue:
    evidence: tuple[EvidenceReference, ...]
    _value: JSONValue = field(repr=False, compare=False)
    _canonical_value: str = field(repr=False)

    def __init__(
        self,
        *,
        value: JSONValue,
        evidence: tuple[EvidenceReference, ...],
    ) -> None:
        canonical_value = canonicalize_json(value, field_name="context value")
        value_copy = copy_json(value, field_name="context value")
        if not isinstance(evidence, tuple) or not all(
            isinstance(reference, EvidenceReference) for reference in evidence
        ):
            raise ContextInvariantError(
                "context value evidence must be a tuple of EvidenceReference objects"
            )
        expected = tuple(sorted(evidence, key=lambda item: str(item.memory_id)))
        if not evidence or evidence != expected:
            raise ContextInvariantError(
                "context value evidence must be non-empty and sorted by memory_id"
            )
        if len({reference.memory_id for reference in evidence}) != len(evidence):
            raise ContextInvariantError("context value evidence IDs must be unique")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "_value", value_copy)
        object.__setattr__(self, "_canonical_value", canonical_value)

    @property
    def value(self) -> JSONValue:
        return copy_json(self._value, field_name="context value")

    @property
    def canonical_value(self) -> str:
        return self._canonical_value


@dataclass(frozen=True, slots=True)
class ContextEntry:
    identity: ContextIdentity
    state: ContextState
    values: tuple[ContextValue, ...]
    conflict_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ContextIdentity):
            raise ContextInvariantError("context entry requires a ContextIdentity")
        if not isinstance(self.state, ContextState) or self.state not in {
            ContextState.RESOLVED,
            ContextState.CONFLICTED,
        }:
            raise ContextInvariantError(
                "context entries must be resolved or conflicted; absence is unknown"
            )
        if not isinstance(self.values, tuple) or not all(
            isinstance(value, ContextValue) for value in self.values
        ):
            raise ContextInvariantError(
                "context entry values must be a tuple of ContextValue objects"
            )
        expected_values = tuple(
            sorted(self.values, key=lambda value: value.canonical_value)
        )
        if self.values != expected_values:
            raise ContextInvariantError(
                "context entry values must be sorted canonically"
            )
        canonical_values = tuple(value.canonical_value for value in self.values)
        if len(canonical_values) != len(set(canonical_values)):
            raise ContextInvariantError("context entry values must be distinct")
        evidence_ids = tuple(
            reference.memory_id
            for value in self.values
            for reference in value.evidence
        )
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ContextInvariantError(
                "a memory cannot support multiple values in one context entry"
            )
        if not isinstance(self.conflict_ids, tuple) or not all(
            isinstance(conflict_id, UUID) for conflict_id in self.conflict_ids
        ):
            raise ContextInvariantError("conflict_ids must be a tuple of UUIDs")
        expected_conflicts = tuple(sorted(set(self.conflict_ids), key=str))
        if self.conflict_ids != expected_conflicts:
            raise ContextInvariantError("conflict_ids must be unique and sorted")
        if self.state is ContextState.RESOLVED and (
            len(self.values) != 1 or self.conflict_ids
        ):
            raise ContextInvariantError(
                "resolved context requires exactly one value and no conflicts"
            )
        if self.state is ContextState.CONFLICTED and (
            len(self.values) < 2 or not self.conflict_ids
        ):
            raise ContextInvariantError(
                "conflicted context requires distinct values and unresolved conflicts"
            )
        if self.state is ContextState.CONFLICTED:
            expected_conflict_count = sum(
                len(left.evidence) * len(right.evidence)
                for index, left in enumerate(self.values)
                for right in self.values[index + 1 :]
            )
            if len(self.conflict_ids) != expected_conflict_count:
                raise ContextInvariantError(
                    "conflict IDs must cover every contradictory evidence pair"
                )


@dataclass(frozen=True, slots=True)
class ContextSnapshotVersion:
    digest: str
    algorithm: str = SNAPSHOT_VERSION_ALGORITHM
    schema_version: int = SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.algorithm != SNAPSHOT_VERSION_ALGORITHM:
            raise ContextInvariantError("snapshot version algorithm must be sha256")
        if self.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise ContextInvariantError("snapshot schema version is unsupported")
        if (
            not isinstance(self.digest, str)
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise ContextInvariantError(
                "snapshot version digest must be lowercase SHA-256 hexadecimal"
            )

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.digest}"


def _entry_document(entry: ContextEntry) -> dict[str, JSONValue]:
    return {
        "conflict_ids": [str(conflict_id) for conflict_id in entry.conflict_ids],
        "domain": entry.identity.domain.value,
        "predicate": entry.identity.predicate,
        "state": entry.state.value,
        "subject": entry.identity.subject,
        "values": [
            {
                "evidence": [
                    {
                        "confidence": reference.confidence,
                        "memory_id": str(reference.memory_id),
                        "metadata": reference.metadata,
                        "observed_at": _utc_text(reference.observed_at),
                        "provenance_details": reference.provenance_details,
                        "provenance_source_id": reference.provenance_source_id,
                        "provenance_type": reference.provenance_type.value,
                        "recorded_at": _utc_text(reference.recorded_at),
                        "revision_reason": reference.revision_reason,
                        "supersedes": (
                            str(reference.supersedes)
                            if reference.supersedes is not None
                            else None
                        ),
                    }
                    for reference in value.evidence
                ],
                "value": value.value,
            }
            for value in entry.values
        ],
    }


def compute_snapshot_version(
    owner_subject: str,
    entries: tuple[ContextEntry, ...],
) -> ContextSnapshotVersion:
    document: dict[str, JSONValue] = {
        "entries": [_entry_document(entry) for entry in entries],
        "owner_subject": owner_subject,
        "schema": "ayyo.personal_context.snapshot.v1",
    }
    canonical = canonicalize_json(document, field_name="snapshot document")
    return ContextSnapshotVersion(digest=sha256(canonical.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True)
class PersonalContextSnapshot:
    owner_subject: str
    entries: tuple[ContextEntry, ...]
    version: ContextSnapshotVersion
    _entries_by_identity: Mapping[ContextIdentity, ContextEntry] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        validate_owner_subject(self.owner_subject)
        if not isinstance(self.entries, tuple) or not all(
            isinstance(entry, ContextEntry) for entry in self.entries
        ):
            raise ContextInvariantError(
                "snapshot entries must be a tuple of ContextEntry objects"
            )
        expected_entries = tuple(
            sorted(
                self.entries,
                key=lambda entry: (
                    entry.identity.domain.value,
                    entry.identity.subject,
                    entry.identity.predicate,
                ),
            )
        )
        if self.entries != expected_entries:
            raise ContextInvariantError("snapshot entries must be sorted by identity")
        identities = tuple(entry.identity for entry in self.entries)
        if len(identities) != len(set(identities)):
            raise ContextInvariantError("snapshot context identities must be unique")
        if any(identity.subject != self.owner_subject for identity in identities):
            raise ContextInvariantError(
                "snapshot entries must belong to the configured owner"
            )
        if not isinstance(self.version, ContextSnapshotVersion):
            raise ContextInvariantError(
                "snapshot version must be a ContextSnapshotVersion"
            )
        if self.version != compute_snapshot_version(self.owner_subject, self.entries):
            raise ContextInvariantError(
                "snapshot version does not match its projected context"
            )
        object.__setattr__(
            self,
            "_entries_by_identity",
            MappingProxyType({entry.identity: entry for entry in self.entries}),
        )

    def get_context(
        self,
        domain: ContextDomain,
        predicate: str,
    ) -> ContextQueryResult:
        if not isinstance(domain, ContextDomain):
            raise InvalidContextQueryError("domain must be a ContextDomain")
        _validate_exact_text(
            predicate,
            field_name="predicate",
            error_type=InvalidContextQueryError,
        )
        identity = ContextIdentity(domain, self.owner_subject, predicate)
        entry = self._entries_by_identity.get(identity)
        return ContextQueryResult(
            identity=identity,
            state=ContextState.UNKNOWN if entry is None else entry.state,
            snapshot_version=self.version,
            entry=entry,
        )


@dataclass(frozen=True, slots=True)
class ContextQueryResult:
    identity: ContextIdentity
    state: ContextState
    snapshot_version: ContextSnapshotVersion
    entry: ContextEntry | None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ContextIdentity):
            raise ContextInvariantError("query result requires a ContextIdentity")
        if not isinstance(self.state, ContextState):
            raise ContextInvariantError("query result state must be a ContextState")
        if not isinstance(self.snapshot_version, ContextSnapshotVersion):
            raise ContextInvariantError(
                "query result requires a ContextSnapshotVersion"
            )
        if self.state is ContextState.UNKNOWN:
            if self.entry is not None:
                raise ContextInvariantError("unknown context cannot contain an entry")
            return
        if not isinstance(self.entry, ContextEntry):
            raise ContextInvariantError("known context requires an entry")
        if self.entry.identity != self.identity or self.entry.state is not self.state:
            raise ContextInvariantError(
                "query result does not match its context entry"
            )
