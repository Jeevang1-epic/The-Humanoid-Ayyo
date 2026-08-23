"""Typed public models for deterministic memory validation decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
import json
import math
from typing import TypeAlias
from uuid import UUID

from ayyo_memory import JSONValue, MemoryRecord, MemoryType, Provenance, ProvenanceType

from .errors import (
    CandidateConfidenceError,
    CandidateProvenanceError,
    CandidateTimestampError,
    CandidateValidationError,
    InvalidCorrectionRequestError,
    NormalizationError,
    PolicyInvariantError,
)
from .normalization import canonicalize_json, normalize_identity_text


VALIDATION_METADATA_KEY = "ayyo_memory_validation"
POLICY_VERSION = 1

DecisionMetadataValue: TypeAlias = str | int | float | bool | None


class DecisionType(StrEnum):
    ACCEPT_NEW = "accept_new"
    EXACT_DUPLICATE = "exact_duplicate"
    CONFLICT_REVIEW = "conflict_review"
    APPLY_CORRECTION = "apply_correction"
    REJECT = "reject"


class DecisionReason(StrEnum):
    NO_ACTIVE_MEMORY = "no_active_memory"
    EXACT_VALUE_ALREADY_ACTIVE = "exact_value_already_active"
    EXACT_VALUE_ACTIVE_WITH_CONFLICTS = "exact_value_active_with_conflicts"
    DIFFERENT_ACTIVE_VALUE = "different_active_value"
    CANONICAL_IDENTITY_VARIANT_REQUIRES_REVIEW = (
        "canonical_identity_variant_requires_review"
    )
    EXPLICIT_CORRECTION_ALLOWED = "explicit_correction_allowed"
    CORRECTION_ALREADY_APPLIED = "correction_already_applied"
    CORRECTION_TARGET_NOT_FOUND = "correction_target_not_found"
    CORRECTION_TARGET_NOT_ACTIVE = "correction_target_not_active"
    CORRECTION_IDENTITY_MISMATCH = "correction_identity_mismatch"
    CORRECTION_AUTHORITY_FORBIDDEN = "correction_authority_forbidden"


_DECISION_REASONS = {
    DecisionType.ACCEPT_NEW: frozenset({DecisionReason.NO_ACTIVE_MEMORY}),
    DecisionType.EXACT_DUPLICATE: frozenset(
        {
            DecisionReason.EXACT_VALUE_ALREADY_ACTIVE,
            DecisionReason.EXACT_VALUE_ACTIVE_WITH_CONFLICTS,
            DecisionReason.CORRECTION_ALREADY_APPLIED,
        }
    ),
    DecisionType.CONFLICT_REVIEW: frozenset(
        {
            DecisionReason.DIFFERENT_ACTIVE_VALUE,
            DecisionReason.CANONICAL_IDENTITY_VARIANT_REQUIRES_REVIEW,
        }
    ),
    DecisionType.APPLY_CORRECTION: frozenset(
        {DecisionReason.EXPLICIT_CORRECTION_ALLOWED}
    ),
    DecisionType.REJECT: frozenset(
        {
            DecisionReason.CORRECTION_TARGET_NOT_FOUND,
            DecisionReason.CORRECTION_TARGET_NOT_ACTIVE,
            DecisionReason.CORRECTION_IDENTITY_MISMATCH,
            DecisionReason.CORRECTION_AUTHORITY_FORBIDDEN,
        }
    ),
}

_CORRECTION_AUTHORITY_TYPES = frozenset(
    {
        ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        ProvenanceType.TRUSTED_MANUAL_IMPORT,
    }
)

_CORRECTION_ONLY_REASONS = frozenset(
    {
        DecisionReason.EXPLICIT_CORRECTION_ALLOWED,
        DecisionReason.CORRECTION_ALREADY_APPLIED,
        DecisionReason.CORRECTION_TARGET_NOT_FOUND,
        DecisionReason.CORRECTION_TARGET_NOT_ACTIVE,
        DecisionReason.CORRECTION_IDENTITY_MISMATCH,
        DecisionReason.CORRECTION_AUTHORITY_FORBIDDEN,
    }
)

_DECISION_METADATA_KEYS = frozenset(
    {
        "active_memory_count",
        "correction_requested",
        "exact_duplicate_count",
        "identity_was_normalized",
        "policy_version",
        "storage_identity_variant_count",
    }
)


@dataclass(frozen=True, slots=True, init=False)
class CandidateEvidence:
    """Immutable snapshot of candidate evidence before normalization and policy."""

    memory_type: MemoryType
    subject: str
    predicate: str
    confidence: float
    observed_at: datetime
    correction_target_id: UUID | None
    correction_reason: str | None
    _value_json: str = field(repr=False)
    _metadata_json: str = field(repr=False)
    _provenance_type: ProvenanceType
    _provenance_source_id: str
    _provenance_details_json: str = field(repr=False)

    def __init__(
        self,
        *,
        memory_type: MemoryType,
        subject: str,
        predicate: str,
        value: JSONValue,
        provenance: Provenance,
        confidence: float,
        observed_at: datetime,
        metadata: Mapping[str, JSONValue] | None = None,
        correction_target_id: UUID | None = None,
        correction_reason: str | None = None,
    ) -> None:
        if not isinstance(memory_type, MemoryType):
            raise CandidateValidationError("memory_type must be a MemoryType")
        normalize_identity_text(subject, field_name="subject")
        normalize_identity_text(predicate, field_name="predicate")
        if not isinstance(provenance, Provenance):
            raise CandidateProvenanceError("provenance must be a Provenance record")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise CandidateConfidenceError(
                "confidence must be a finite number from 0.0 to 1.0"
            )
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise CandidateConfidenceError(
                "confidence must be a finite number from 0.0 to 1.0"
            )
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise CandidateTimestampError("observed_at must be timezone-aware UTC")
        if observed_at.utcoffset() != timedelta(0):
            raise CandidateTimestampError("observed_at must use UTC")

        candidate_metadata: Mapping[str, JSONValue] = (
            {} if metadata is None else metadata
        )
        if not isinstance(candidate_metadata, Mapping):
            raise CandidateValidationError("metadata must be a mapping")
        materialized_metadata = dict(candidate_metadata)
        if VALIDATION_METADATA_KEY in materialized_metadata:
            raise CandidateValidationError(
                f"metadata key {VALIDATION_METADATA_KEY!r} is reserved"
            )

        if correction_target_id is None:
            if correction_reason is not None:
                raise InvalidCorrectionRequestError(
                    "correction_reason requires correction_target_id"
                )
        else:
            if not isinstance(correction_target_id, UUID):
                raise InvalidCorrectionRequestError(
                    "correction_target_id must be a UUID"
                )
            if not isinstance(correction_reason, str) or not correction_reason.strip():
                raise InvalidCorrectionRequestError(
                    "correction_reason must be non-empty for a correction"
                )
            if correction_reason != correction_reason.strip():
                raise InvalidCorrectionRequestError(
                    "correction_reason must not have surrounding whitespace"
                )

        try:
            provenance_details_json = canonicalize_json(dict(provenance.details))
        except NormalizationError as error:
            raise CandidateProvenanceError(
                "provenance details must contain only JSON-compatible data"
            ) from error

        object.__setattr__(self, "memory_type", memory_type)
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "predicate", predicate)
        object.__setattr__(self, "confidence", float(confidence))
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "correction_target_id", correction_target_id)
        object.__setattr__(self, "correction_reason", correction_reason)
        object.__setattr__(self, "_value_json", canonicalize_json(value))
        object.__setattr__(
            self,
            "_metadata_json",
            canonicalize_json(materialized_metadata),
        )
        object.__setattr__(self, "_provenance_type", provenance.provenance_type)
        object.__setattr__(self, "_provenance_source_id", provenance.source_id)
        object.__setattr__(
            self,
            "_provenance_details_json",
            provenance_details_json,
        )

    @property
    def value(self) -> JSONValue:
        return json.loads(self._value_json)

    @property
    def canonical_value(self) -> str:
        return self._value_json

    @property
    def metadata(self) -> dict[str, JSONValue]:
        return json.loads(self._metadata_json)

    @property
    def provenance(self) -> Provenance:
        return Provenance(
            provenance_type=self._provenance_type,
            source_id=self._provenance_source_id,
            details=json.loads(self._provenance_details_json),
        )


@dataclass(frozen=True, slots=True)
class NormalizedIdentity:
    memory_type: MemoryType
    subject: str
    predicate: str

    def __post_init__(self) -> None:
        if not isinstance(self.memory_type, MemoryType):
            raise PolicyInvariantError("normalized memory_type must be a MemoryType")
        if normalize_identity_text(self.subject, field_name="subject") != self.subject:
            raise PolicyInvariantError("normalized subject is not canonical")
        if normalize_identity_text(self.predicate, field_name="predicate") != self.predicate:
            raise PolicyInvariantError("normalized predicate is not canonical")


@dataclass(frozen=True, slots=True)
class NormalizedCandidate:
    candidate: CandidateEvidence
    identity: NormalizedIdentity
    canonical_value: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateEvidence):
            raise PolicyInvariantError("normalized candidate requires candidate evidence")
        if not isinstance(self.identity, NormalizedIdentity):
            raise PolicyInvariantError("normalized candidate requires an identity")
        expected_identity = NormalizedIdentity(
            memory_type=self.candidate.memory_type,
            subject=normalize_identity_text(
                self.candidate.subject,
                field_name="subject",
            ),
            predicate=normalize_identity_text(
                self.candidate.predicate,
                field_name="predicate",
            ),
        )
        if self.identity != expected_identity:
            raise PolicyInvariantError("normalized identity does not match candidate")
        if self.canonical_value != self.candidate.canonical_value:
            raise PolicyInvariantError("normalized candidate value is inconsistent")


@dataclass(frozen=True, slots=True)
class ValidationDecision:
    decision_type: DecisionType
    reason_code: DecisionReason
    normalized_identity: NormalizedIdentity
    candidate: CandidateEvidence
    relevant_memory_ids: tuple[UUID, ...]
    conflict_ids: tuple[UUID, ...]
    persistence_permitted: bool
    explanatory_metadata: tuple[tuple[str, DecisionMetadataValue], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.decision_type, DecisionType):
            raise PolicyInvariantError("decision_type must be a DecisionType")
        if not isinstance(self.reason_code, DecisionReason):
            raise PolicyInvariantError("reason_code must be a DecisionReason")
        if not isinstance(self.normalized_identity, NormalizedIdentity):
            raise PolicyInvariantError("decision requires a normalized identity")
        if not isinstance(self.candidate, CandidateEvidence):
            raise PolicyInvariantError("decision requires candidate evidence")
        expected_identity = NormalizedIdentity(
            memory_type=self.candidate.memory_type,
            subject=normalize_identity_text(
                self.candidate.subject,
                field_name="subject",
            ),
            predicate=normalize_identity_text(
                self.candidate.predicate,
                field_name="predicate",
            ),
        )
        if self.normalized_identity != expected_identity:
            raise PolicyInvariantError("decision identity does not match candidate")
        if self.reason_code not in _DECISION_REASONS[self.decision_type]:
            raise PolicyInvariantError(
                "reason_code is incompatible with decision_type"
            )
        if not isinstance(self.persistence_permitted, bool):
            raise PolicyInvariantError("persistence_permitted must be a boolean")
        if self.decision_type in {
            DecisionType.ACCEPT_NEW,
            DecisionType.APPLY_CORRECTION,
        } and not self.persistence_permitted:
            raise PolicyInvariantError("mutating decision must permit persistence")
        if self.decision_type in {
            DecisionType.EXACT_DUPLICATE,
            DecisionType.REJECT,
        } and self.persistence_permitted:
            raise PolicyInvariantError("non-mutating decision cannot permit persistence")
        if self.decision_type is DecisionType.CONFLICT_REVIEW:
            expected_permission = self.reason_code is DecisionReason.DIFFERENT_ACTIVE_VALUE
            if self.persistence_permitted is not expected_permission:
                raise PolicyInvariantError(
                    "conflict persistence permission is inconsistent with its reason"
                )
        self._validate_uuid_tuple(self.relevant_memory_ids, "relevant_memory_ids")
        self._validate_uuid_tuple(self.conflict_ids, "conflict_ids")
        self._validate_decision_shape()
        if not isinstance(self.explanatory_metadata, tuple) or not all(
            isinstance(item, tuple) and len(item) == 2
            for item in self.explanatory_metadata
        ):
            raise PolicyInvariantError(
                "explanatory_metadata must be a tuple of key-value pairs"
            )
        for key, value in self.explanatory_metadata:
            if not isinstance(key, str) or not key:
                raise PolicyInvariantError("explanatory metadata keys must be text")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise PolicyInvariantError(
                    "explanatory metadata values must be JSON scalars"
                )
            if isinstance(value, float) and not math.isfinite(value):
                raise PolicyInvariantError(
                    "explanatory metadata numbers must be finite"
                )
        keys = tuple(key for key, _ in self.explanatory_metadata)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise PolicyInvariantError(
                "explanatory metadata keys must be unique and sorted"
            )
        self._validate_explanatory_metadata()

    @property
    def provenance(self) -> Provenance:
        return self.candidate.provenance

    @property
    def confidence(self) -> float:
        return self.candidate.confidence

    @property
    def metadata(self) -> dict[str, DecisionMetadataValue]:
        return dict(self.explanatory_metadata)

    @staticmethod
    def _validate_uuid_tuple(values: tuple[UUID, ...], field_name: str) -> None:
        if not isinstance(values, tuple) or not all(
            isinstance(value, UUID) for value in values
        ):
            raise PolicyInvariantError(f"{field_name} must be a tuple of UUIDs")
        expected = tuple(sorted(set(values), key=str))
        if values != expected:
            raise PolicyInvariantError(f"{field_name} must be unique and sorted")

    def _validate_decision_shape(self) -> None:
        target_id = self.candidate.correction_target_id
        correction_requested = target_id is not None
        if self.reason_code in _CORRECTION_ONLY_REASONS and not correction_requested:
            raise PolicyInvariantError("correction reason requires correction intent")
        if self.decision_type in {
            DecisionType.APPLY_CORRECTION,
            DecisionType.REJECT,
        } and not correction_requested:
            raise PolicyInvariantError("correction decision requires correction intent")
        if self.decision_type is DecisionType.ACCEPT_NEW:
            if correction_requested:
                raise PolicyInvariantError("a correction cannot be accepted as new evidence")
            if self.relevant_memory_ids or self.conflict_ids:
                raise PolicyInvariantError("new evidence cannot reference existing state")
        if self.decision_type is DecisionType.EXACT_DUPLICATE:
            if not self.relevant_memory_ids:
                raise PolicyInvariantError(
                    "duplicate decision requires a relevant memory"
                )
        if self.decision_type is DecisionType.CONFLICT_REVIEW:
            if not self.relevant_memory_ids:
                raise PolicyInvariantError(
                    "conflict decision requires a relevant memory"
                )
            if (
                correction_requested
                and self.reason_code
                is not DecisionReason.CANONICAL_IDENTITY_VARIANT_REQUIRES_REVIEW
            ):
                raise PolicyInvariantError(
                    "correction review requires a canonical identity variant"
                )
        if self.decision_type is DecisionType.APPLY_CORRECTION:
            if target_id not in self.relevant_memory_ids:
                raise PolicyInvariantError(
                    "correction decision must reference its target"
                )
            if (
                self.candidate.provenance.provenance_type
                not in _CORRECTION_AUTHORITY_TYPES
            ):
                raise PolicyInvariantError(
                    "correction decision requires authoritative provenance"
                )
        if (
            correction_requested
            and self.reason_code is not DecisionReason.CORRECTION_TARGET_NOT_FOUND
            and target_id not in self.relevant_memory_ids
        ):
            raise PolicyInvariantError(
                "correction decision state must reference its target"
            )

    def _validate_explanatory_metadata(self) -> None:
        metadata = self.metadata
        if set(metadata) != _DECISION_METADATA_KEYS:
            raise PolicyInvariantError(
                "explanatory metadata does not match the policy schema"
            )
        for key in (
            "active_memory_count",
            "exact_duplicate_count",
            "storage_identity_variant_count",
        ):
            value = metadata[key]
            if type(value) is not int or value < 0:
                raise PolicyInvariantError(
                    f"explanatory metadata {key} must be a non-negative integer"
                )
        active_count = metadata["active_memory_count"]
        exact_count = metadata["exact_duplicate_count"]
        variant_count = metadata["storage_identity_variant_count"]
        if exact_count > active_count or variant_count > active_count:
            raise PolicyInvariantError(
                "decision counts cannot exceed active memory count"
            )
        if metadata["policy_version"] != POLICY_VERSION or type(
            metadata["policy_version"]
        ) is not int:
            raise PolicyInvariantError("decision policy_version is invalid")
        correction_requested = metadata["correction_requested"]
        if not isinstance(correction_requested, bool) or correction_requested != (
            self.candidate.correction_target_id is not None
        ):
            raise PolicyInvariantError("correction_requested metadata is inconsistent")
        identity_was_normalized = metadata["identity_was_normalized"]
        expected_normalization = (
            self.candidate.subject != self.normalized_identity.subject
            or self.candidate.predicate != self.normalized_identity.predicate
        )
        if (
            not isinstance(identity_was_normalized, bool)
            or identity_was_normalized != expected_normalization
        ):
            raise PolicyInvariantError(
                "identity normalization metadata is inconsistent"
            )
        if self.decision_type is DecisionType.ACCEPT_NEW and active_count != 0:
            raise PolicyInvariantError("new evidence requires empty active state")
        if self.decision_type is DecisionType.EXACT_DUPLICATE and exact_count == 0:
            raise PolicyInvariantError("duplicate decision requires an exact match")
        if self.decision_type in {
            DecisionType.CONFLICT_REVIEW,
            DecisionType.APPLY_CORRECTION,
        } and active_count == 0:
            raise PolicyInvariantError("mutating decision requires active state")
        if self.conflict_ids and (
            active_count < 2 or len(self.relevant_memory_ids) < 2
        ):
            raise PolicyInvariantError(
                "unresolved conflicts require at least two active memories"
            )
        if (
            self.reason_code is DecisionReason.EXACT_VALUE_ACTIVE_WITH_CONFLICTS
            and not self.conflict_ids
        ):
            raise PolicyInvariantError(
                "duplicate-with-conflicts reason requires a conflict"
            )


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    decision: ValidationDecision
    mutation_applied: bool
    memory: MemoryRecord | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ValidationDecision):
            raise PolicyInvariantError("application result requires a decision")
        if not isinstance(self.mutation_applied, bool):
            raise PolicyInvariantError("mutation_applied must be a boolean")
        if self.mutation_applied and not isinstance(self.memory, MemoryRecord):
            raise PolicyInvariantError("a successful mutation must return its memory")
        if self.memory is not None and not isinstance(self.memory, MemoryRecord):
            raise PolicyInvariantError("application memory must be a MemoryRecord")
        if self.mutation_applied and not self.decision.persistence_permitted:
            raise PolicyInvariantError("mutation requires persistence permission")
        if not self.mutation_applied and (
            self.decision.decision_type is not DecisionType.EXACT_DUPLICATE
            or self.memory is None
        ):
            raise PolicyInvariantError(
                "a no-op result requires an equivalent active memory"
            )
        if self.memory is not None:
            memory_identity = NormalizedIdentity(
                memory_type=self.memory.memory_type,
                subject=normalize_identity_text(
                    self.memory.subject,
                    field_name="stored subject",
                ),
                predicate=normalize_identity_text(
                    self.memory.predicate,
                    field_name="stored predicate",
                ),
            )
            if memory_identity != self.decision.normalized_identity:
                raise PolicyInvariantError(
                    "application memory identity does not match decision"
                )
            if (
                canonicalize_json(self.memory.value)
                != self.decision.candidate.canonical_value
            ):
                raise PolicyInvariantError(
                    "application memory value does not match decision"
                )

    @property
    def memory_id(self) -> UUID | None:
        return self.memory.memory_id if self.memory is not None else None
