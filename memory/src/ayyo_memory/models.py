"""Typed domain records and validation for the Memory OS core."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
import math
from typing import Mapping, TypeAlias
from uuid import UUID

from .errors import (
    InvalidConfidenceError,
    InvalidMemoryDataError,
    InvalidProvenanceError,
)

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PREFERENCE = "preference"
    SOCIAL = "social"
    SPATIAL = "spatial"
    PROCEDURAL = "procedural"
    FAILURE = "failure"


class ProvenanceType(StrEnum):
    EXPLICIT_OWNER_STATEMENT = "explicit_owner_statement"
    DIRECT_OBSERVATION = "direct_observation"
    DERIVED_INFERENCE = "derived_inference"
    SYSTEM_EVENT = "system_event"
    TRUSTED_MANUAL_IMPORT = "trusted_manual_import"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


def validate_nonempty_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidMemoryDataError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise InvalidMemoryDataError(f"{field_name} must not have surrounding whitespace")


def validate_confidence(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidConfidenceError("confidence must be a finite number from 0.0 to 1.0")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise InvalidConfidenceError("confidence must be a finite number from 0.0 to 1.0")


def validate_utc_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidMemoryDataError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise InvalidMemoryDataError(f"{field_name} must use UTC")


def _validate_json_value(
    value: object,
    field_name: str,
    ancestors: set[int],
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidMemoryDataError(f"{field_name} cannot contain non-finite numbers")
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in ancestors:
            raise InvalidMemoryDataError(f"{field_name} cannot contain reference cycles")
        ancestors.add(identity)
        try:
            for item in value:
                _validate_json_value(item, field_name, ancestors)
        finally:
            ancestors.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in ancestors:
            raise InvalidMemoryDataError(f"{field_name} cannot contain reference cycles")
        ancestors.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise InvalidMemoryDataError(
                        f"{field_name} object keys must be strings"
                    )
                _validate_json_value(item, field_name, ancestors)
        finally:
            ancestors.remove(identity)
        return
    raise InvalidMemoryDataError(f"{field_name} must contain only JSON-compatible values")


def validate_json_value(value: object, field_name: str) -> None:
    _validate_json_value(value, field_name, set())


def _copy_mapping(value: object, field_name: str) -> dict[str, JSONValue]:
    if not isinstance(value, Mapping):
        raise InvalidMemoryDataError(f"{field_name} must be a mapping")
    materialized = dict(value)
    validate_json_value(materialized, field_name)
    return deepcopy(materialized)


@dataclass(frozen=True, slots=True)
class Provenance:
    provenance_type: ProvenanceType
    source_id: str
    details: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.provenance_type, ProvenanceType):
            raise InvalidProvenanceError("provenance_type must be a ProvenanceType")
        try:
            validate_nonempty_text(self.source_id, "provenance source_id")
            details = _copy_mapping(self.details, "provenance details")
        except InvalidMemoryDataError as error:
            raise InvalidProvenanceError(str(error)) from error
        object.__setattr__(self, "details", details)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: UUID
    memory_type: MemoryType
    subject: str
    predicate: str
    value: JSONValue
    provenance: Provenance
    confidence: float
    observed_at: datetime
    created_at: datetime
    status: MemoryStatus
    status_changed_at: datetime
    supersedes: UUID | None = None
    revision_reason: str | None = None
    status_reason: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.memory_id, UUID):
            raise InvalidMemoryDataError("memory_id must be a UUID")
        if not isinstance(self.memory_type, MemoryType):
            raise InvalidMemoryDataError("memory_type must be a MemoryType")
        if not isinstance(self.status, MemoryStatus):
            raise InvalidMemoryDataError("status must be a MemoryStatus")
        validate_nonempty_text(self.subject, "subject")
        validate_nonempty_text(self.predicate, "predicate")
        validate_json_value(self.value, "value")
        if not isinstance(self.provenance, Provenance):
            raise InvalidProvenanceError("provenance is required")
        provenance = Provenance(
            provenance_type=self.provenance.provenance_type,
            source_id=self.provenance.source_id,
            details=self.provenance.details,
        )
        validate_confidence(self.confidence)
        validate_utc_datetime(self.observed_at, "observed_at")
        validate_utc_datetime(self.created_at, "created_at")
        validate_utc_datetime(self.status_changed_at, "status_changed_at")
        if self.status_changed_at < self.created_at:
            raise InvalidMemoryDataError("status_changed_at cannot precede created_at")
        if self.supersedes is not None and not isinstance(self.supersedes, UUID):
            raise InvalidMemoryDataError("supersedes must be a UUID when provided")
        if self.supersedes == self.memory_id:
            raise InvalidMemoryDataError("a memory cannot supersede itself")
        if self.supersedes is None and self.revision_reason is not None:
            raise InvalidMemoryDataError("revision_reason requires a superseded memory")
        if self.supersedes is not None:
            validate_nonempty_text(self.revision_reason, "revision_reason")
        if self.status is MemoryStatus.ACTIVE and self.status_reason is not None:
            raise InvalidMemoryDataError("active memories cannot have a status_reason")
        if self.status is not MemoryStatus.ACTIVE:
            validate_nonempty_text(self.status_reason, "status_reason")
        object.__setattr__(self, "value", deepcopy(self.value))
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "metadata", _copy_mapping(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    memory_type: MemoryType | None = None
    subject: str | None = None
    predicate: str | None = None
    active_only: bool = True

    def __post_init__(self) -> None:
        if self.memory_type is not None and not isinstance(self.memory_type, MemoryType):
            raise InvalidMemoryDataError("memory_type filter must be a MemoryType")
        if self.subject is not None:
            validate_nonempty_text(self.subject, "subject filter")
        if self.predicate is not None:
            validate_nonempty_text(self.predicate, "predicate filter")
        if not isinstance(self.active_only, bool):
            raise InvalidMemoryDataError("active_only must be a boolean")


@dataclass(frozen=True, slots=True)
class MemoryConflict:
    conflict_id: UUID
    left_memory: MemoryRecord
    right_memory: MemoryRecord
    created_at: datetime
    reason: str
    resolved_at: datetime | None = None
    resolution_memory_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.conflict_id, UUID):
            raise InvalidMemoryDataError("conflict_id must be a UUID")
        if not isinstance(self.left_memory, MemoryRecord) or not isinstance(
            self.right_memory, MemoryRecord
        ):
            raise InvalidMemoryDataError("conflict sides must be memory records")
        if self.left_memory.memory_id == self.right_memory.memory_id:
            raise InvalidMemoryDataError("a conflict requires two different memories")
        validate_utc_datetime(self.created_at, "conflict created_at")
        validate_nonempty_text(self.reason, "conflict reason")
        if self.resolved_at is not None:
            validate_utc_datetime(self.resolved_at, "conflict resolved_at")
            if self.resolved_at < self.created_at:
                raise InvalidMemoryDataError("conflict resolved_at cannot precede created_at")
        if self.resolution_memory_id is not None and self.resolved_at is None:
            raise InvalidMemoryDataError("resolution_memory_id requires resolved_at")
        if self.resolution_memory_id is not None and not isinstance(
            self.resolution_memory_id, UUID
        ):
            raise InvalidMemoryDataError("resolution_memory_id must be a UUID")
