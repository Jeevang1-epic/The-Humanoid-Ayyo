"""Immutable source policy, admission result, and resource records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from ayyo_world_model import (
    MAX_OBSERVATION_TIME_NS,
    Observation,
    ObservationClock,
    ObservationProvenance,
    SensorIdentity,
    SensorKind,
    rebuild_observation,
)

from .errors import PerceptionConfigurationError


MAX_PERCEPTION_SOURCES = 32
MAX_PERCEPTION_RETENTION_NS = 300_000_000_000
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")


class AdmissionStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class AdmissionReason(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    MALFORMED_OBSERVATION = "malformed_observation"
    IDENTITY_MISMATCH = "identity_mismatch"
    WRONG_ROBOT_IDENTITY = "wrong_robot_identity"
    UNKNOWN_SENSOR = "unknown_sensor"
    PROVENANCE_NOT_ALLOWED = "provenance_not_allowed"
    CLOCK_DOMAIN_MISMATCH = "clock_domain_mismatch"
    FRAME_MISMATCH = "frame_mismatch"
    FUTURE_OBSERVATION = "future_observation"
    STALE_OBSERVATION = "stale_observation"
    OUT_OF_ORDER = "out_of_order"
    TEMPORAL_CONFLICT = "temporal_conflict"
    RECEIPT_TIME_REGRESSION = "receipt_time_regression"
    FRAME_LOOKUP_UNAVAILABLE = "frame_lookup_unavailable"
    FRAME_LOOKUP_CONNECTIVITY = "frame_lookup_connectivity"
    FRAME_LOOKUP_EXTRAPOLATION = "frame_lookup_extrapolation"
    FRAME_LOOKUP_TIMEOUT = "frame_lookup_timeout"
    INVALID_FRAME_REQUEST = "invalid_frame_request"
    STALE_TRANSFORM = "stale_transform"
    REJECTED_PROVENANCE = "rejected_provenance"
    MALFORMED_NUMERIC_POSE = "malformed_numeric_pose"
    INVALID_QUATERNION = "invalid_quaternion"
    INVALID_COVARIANCE = "invalid_covariance"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ADAPTER_RESTARTED = "adapter_restarted"


class EvidenceFailureKind(StrEnum):
    FRAME_LOOKUP_UNAVAILABLE = "frame_lookup_unavailable"
    FRAME_LOOKUP_CONNECTIVITY = "frame_lookup_connectivity"
    FRAME_LOOKUP_EXTRAPOLATION = "frame_lookup_extrapolation"
    FRAME_LOOKUP_TIMEOUT = "frame_lookup_timeout"
    INVALID_FRAME_REQUEST = "invalid_frame_request"
    STALE_TRANSFORM = "stale_transform"
    REJECTED_PROVENANCE = "rejected_provenance"
    MALFORMED_NUMERIC_POSE = "malformed_numeric_pose"
    INVALID_QUATERNION = "invalid_quaternion"
    INVALID_COVARIANCE = "invalid_covariance"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ADAPTER_RESTARTED = "adapter_restarted"


@dataclass(frozen=True, slots=True)
class PerceptionSourceContract:
    sensor: SensorIdentity
    provenance: ObservationProvenance
    pose_source_frame_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.sensor) is not SensorIdentity:
            raise PerceptionConfigurationError("source contract requires a sensor identity")
        if type(self.provenance) is not ObservationProvenance:
            raise PerceptionConfigurationError("source contract requires exact provenance")
        if self.sensor.kind is SensorKind.BODY_POSE:
            if (
                type(self.pose_source_frame_id) is not str
                or not self.pose_source_frame_id
                or self.pose_source_frame_id != self.pose_source_frame_id.strip()
                or len(self.pose_source_frame_id) > 256
                or _FRAME.fullmatch(self.pose_source_frame_id) is None
                or "//" in self.pose_source_frame_id
                or self.pose_source_frame_id.endswith("/")
            ):
                raise PerceptionConfigurationError(
                    "body-pose source requires one reviewed source frame"
                )
        elif self.pose_source_frame_id is not None:
            raise PerceptionConfigurationError(
                "only body-pose sources may declare a pose source frame"
            )


@dataclass(frozen=True, slots=True)
class PerceptionTrustConfig:
    robot_id: str
    source_clock: ObservationClock
    sources: tuple[PerceptionSourceContract, ...]
    freshness_ns: int = 500_000_000
    retention_ttl_ns: int = 2_000_000_000
    permitted_future_skew_ns: int = 50_000_000

    def __post_init__(self) -> None:
        if (
            type(self.robot_id) is not str
            or not self.robot_id
            or self.robot_id != self.robot_id.strip()
        ):
            raise PerceptionConfigurationError("robot identity must be non-empty exact text")
        if not isinstance(self.source_clock, ObservationClock):
            raise PerceptionConfigurationError("source clock must be typed")
        if (
            type(self.sources) is not tuple
            or not self.sources
            or len(self.sources) > MAX_PERCEPTION_SOURCES
            or any(type(source) is not PerceptionSourceContract for source in self.sources)
        ):
            raise PerceptionConfigurationError("source contracts must be a bounded typed tuple")
        keys = tuple(
            (source.sensor.sensor_id, source.sensor.kind, source.provenance)
            for source in self.sources
        )
        if len(keys) != len(set(keys)):
            raise PerceptionConfigurationError("source contracts must be unique")
        sensor_contracts: dict[str, SensorIdentity] = {}
        for source in self.sources:
            existing = sensor_contracts.setdefault(source.sensor.sensor_id, source.sensor)
            if existing != source.sensor:
                raise PerceptionConfigurationError(
                    "one sensor ID cannot substitute kind or frame identity"
                )
            if source.provenance.clock is not self.source_clock:
                raise PerceptionConfigurationError(
                    "all source provenance must use the configured source clock"
                )
        if (
            type(self.freshness_ns) is not int
            or type(self.retention_ttl_ns) is not int
            or not 0 <= self.freshness_ns < self.retention_ttl_ns
            or self.retention_ttl_ns > MAX_PERCEPTION_RETENTION_NS
        ):
            raise PerceptionConfigurationError(
                "freshness and retention must form a positive bounded interval"
            )
        if (
            type(self.permitted_future_skew_ns) is not int
            or not 0 <= self.permitted_future_skew_ns <= 1_000_000_000
        ):
            raise PerceptionConfigurationError("future skew is outside its bound")


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    status: AdmissionStatus
    reason: AdmissionReason
    observation_id: str | None
    observation: Observation | None
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, AdmissionStatus) or not isinstance(
            self.reason, AdmissionReason
        ):
            raise PerceptionConfigurationError("admission result status is invalid")
        if type(self.detail) is not str or len(self.detail) > 1_024:
            raise PerceptionConfigurationError("admission detail must be bounded text")
        if self.status is AdmissionStatus.ACCEPTED:
            if self.observation is None:
                raise PerceptionConfigurationError("accepted evidence requires an observation")
            rebuilt = rebuild_observation(self.observation)
            if self.observation_id != rebuilt.observation_id:
                raise PerceptionConfigurationError("accepted evidence identity is inconsistent")
            object.__setattr__(self, "observation", rebuilt)
        elif self.observation is not None:
            raise PerceptionConfigurationError("non-accepted evidence cannot carry an observation")
        if self.observation_id is not None and not self.observation_id.startswith(
            "world-observation-"
        ):
            raise PerceptionConfigurationError("admission evidence identity is malformed")


@dataclass(frozen=True, slots=True)
class PerceptionStats:
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    tracked_source_key_count: int
    configured_source_count: int

    def __post_init__(self) -> None:
        values = (
            self.accepted_count,
            self.duplicate_count,
            self.rejected_count,
            self.tracked_source_key_count,
            self.configured_source_count,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise PerceptionConfigurationError("perception statistics are invalid")
        if self.configured_source_count > MAX_PERCEPTION_SOURCES:
            raise PerceptionConfigurationError("configured source count exceeds its bound")
        if self.tracked_source_key_count > self.configured_source_count * 2:
            raise PerceptionConfigurationError("tracked source keys exceed their hard bound")


def validate_time(value: object, field_name: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_OBSERVATION_TIME_NS:
        raise PerceptionConfigurationError(
            f"{field_name} must be non-negative bounded integer nanoseconds"
        )
    return value
