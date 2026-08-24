"""Immutable Working Memory configuration, results, and resource reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_world_model import (
    Observation,
    ObservationClock,
    ObservationProvenance,
    rebuild_observation,
)

from .errors import WorkingMemoryConfigurationError


WORKING_MEMORY_SCHEMA_VERSION = 1
MAX_RECENT_EVIDENCE_CAPACITY = 4_096
MAX_ENTITY_CAPACITY = 256
MAX_RETENTION_NS = 300_000_000_000


class IngestionStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class IngestionReason(StrEnum):
    ACCEPTED_NEW = "accepted_new"
    ACCEPTED_REPLACEMENT = "accepted_replacement"
    DUPLICATE_OBSERVATION = "duplicate_observation"
    OLDER_OBSERVATION = "older_observation"
    TEMPORAL_CONFLICT = "temporal_conflict"
    FUTURE_OBSERVATION = "future_observation"
    EXPIRED_OBSERVATION = "expired_observation"
    WRONG_ROBOT_IDENTITY = "wrong_robot_identity"
    PROVENANCE_NOT_ALLOWED = "provenance_not_allowed"
    UNKNOWN_JOINT = "unknown_joint"
    FIXED_JOINT = "fixed_joint"
    INVALID_JOINT_VALUE = "invalid_joint_value"
    MALFORMED_OBSERVATION = "malformed_observation"


class WorkingMemoryFreshness(StrEnum):
    UNKNOWN = "unknown"
    FRESH = "fresh"
    STALE = "stale"


class StateKeyKind(StrEnum):
    ROBOT_JOINT = "robot_joint"
    ROBOT_BASE_POSE = "robot_base_pose"
    ENVIRONMENT_ENTITY = "environment_entity"


@dataclass(frozen=True, slots=True)
class StateKey:
    kind: StateKeyKind
    identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StateKeyKind):
            raise WorkingMemoryConfigurationError("state key kind is invalid")
        if type(self.identity) is not str or not self.identity or self.identity != self.identity.strip():
            raise WorkingMemoryConfigurationError("state key identity must be non-empty exact text")


@dataclass(frozen=True, slots=True)
class WorkingMemoryConfig:
    robot_id: str
    source_clock: ObservationClock
    allowed_provenance: tuple[ObservationProvenance, ...]
    freshness_ns: int = 500_000_000
    retention_ttl_ns: int = 2_000_000_000
    permitted_future_skew_ns: int = 50_000_000
    recent_evidence_capacity: int = 256
    environment_entity_capacity: int = 128

    def __post_init__(self) -> None:
        if type(self.robot_id) is not str or not self.robot_id or self.robot_id != self.robot_id.strip():
            raise WorkingMemoryConfigurationError("robot_id must be non-empty exact text")
        if not isinstance(self.source_clock, ObservationClock):
            raise WorkingMemoryConfigurationError("source_clock must be an ObservationClock")
        if (
            type(self.allowed_provenance) is not tuple
            or not self.allowed_provenance
            or len(self.allowed_provenance) > 16
            or any(type(item) is not ObservationProvenance for item in self.allowed_provenance)
        ):
            raise WorkingMemoryConfigurationError(
                "allowed_provenance must be a non-empty bounded tuple"
            )
        if len(set(self.allowed_provenance)) != len(self.allowed_provenance):
            raise WorkingMemoryConfigurationError("allowed provenance profiles must be unique")
        if any(item.clock is not self.source_clock for item in self.allowed_provenance):
            raise WorkingMemoryConfigurationError(
                "all allowed provenance profiles must use the configured source clock"
            )
        if (
            type(self.freshness_ns) is not int
            or type(self.retention_ttl_ns) is not int
            or not 0 <= self.freshness_ns < self.retention_ttl_ns <= MAX_RETENTION_NS
        ):
            raise WorkingMemoryConfigurationError(
                "freshness and retention TTL must form a positive bounded interval"
            )
        if (
            type(self.permitted_future_skew_ns) is not int
            or not 0 <= self.permitted_future_skew_ns <= 1_000_000_000
        ):
            raise WorkingMemoryConfigurationError("future skew is outside its bound")
        if (
            type(self.recent_evidence_capacity) is not int
            or not 1 <= self.recent_evidence_capacity <= MAX_RECENT_EVIDENCE_CAPACITY
        ):
            raise WorkingMemoryConfigurationError("recent evidence capacity is invalid")
        if (
            type(self.environment_entity_capacity) is not int
            or not 1 <= self.environment_entity_capacity <= MAX_ENTITY_CAPACITY
        ):
            raise WorkingMemoryConfigurationError("environment entity capacity is invalid")


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    observation: Observation
    received_at_monotonic_ns: int

    def __post_init__(self) -> None:
        rebuilt = rebuild_observation(self.observation)
        if type(self.received_at_monotonic_ns) is not int or self.received_at_monotonic_ns < 0:
            raise WorkingMemoryConfigurationError(
                "receipt time must be non-negative monotonic nanoseconds"
            )
        object.__setattr__(self, "observation", rebuilt)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    status: IngestionStatus
    reason: IngestionReason
    observation_id: str
    updated_keys: tuple[StateKey, ...] = ()
    evicted_keys: tuple[StateKey, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, IngestionStatus) or not isinstance(self.reason, IngestionReason):
            raise WorkingMemoryConfigurationError("ingestion result status or reason is invalid")
        if type(self.observation_id) is not str or not self.observation_id.startswith(
            "world-observation-"
        ):
            raise WorkingMemoryConfigurationError("ingestion result evidence ID is invalid")
        updated = tuple(sorted(set(self.updated_keys), key=lambda item: (item.kind.value, item.identity)))
        evicted = tuple(sorted(set(self.evicted_keys), key=lambda item: (item.kind.value, item.identity)))
        if updated != self.updated_keys or evicted != self.evicted_keys:
            raise WorkingMemoryConfigurationError("ingestion result keys must be unique and sorted")
        if self.status is IngestionStatus.ACCEPTED and not self.updated_keys:
            raise WorkingMemoryConfigurationError("accepted ingestion must update current state")
        if self.status is not IngestionStatus.ACCEPTED and (self.updated_keys or self.evicted_keys):
            raise WorkingMemoryConfigurationError("non-accepted ingestion cannot mutate state")


@dataclass(frozen=True, slots=True)
class FreshnessQueryResult:
    key: StateKey
    freshness: WorkingMemoryFreshness
    observation_id: str | None
    observed_at_ns: int | None
    age_ns: int | None

    def __post_init__(self) -> None:
        if self.freshness is WorkingMemoryFreshness.UNKNOWN:
            if any(value is not None for value in (self.observation_id, self.observed_at_ns, self.age_ns)):
                raise WorkingMemoryConfigurationError("unknown freshness cannot claim evidence")
        elif any(value is None for value in (self.observation_id, self.observed_at_ns, self.age_ns)):
            raise WorkingMemoryConfigurationError("known freshness requires complete evidence")


@dataclass(frozen=True, slots=True)
class WorkingMemoryStats:
    current_joint_count: int
    has_current_pose: bool
    current_entity_count: int
    recent_evidence_count: int
    retained_unique_observation_count: int
    retained_observation_reference_count: int
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    eviction_count: int

    def __post_init__(self) -> None:
        numeric = (
            self.current_joint_count,
            self.current_entity_count,
            self.recent_evidence_count,
            self.retained_unique_observation_count,
            self.retained_observation_reference_count,
            self.accepted_count,
            self.duplicate_count,
            self.rejected_count,
            self.eviction_count,
        )
        if any(type(item) is not int or item < 0 for item in numeric):
            raise WorkingMemoryConfigurationError("Working Memory statistics are invalid")
