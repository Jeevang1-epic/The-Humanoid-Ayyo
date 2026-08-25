"""Deterministic admission of normalized evidence at the perception boundary."""

from __future__ import annotations

from threading import RLock

from ayyo_world_model import (
    BodyPoseObservation,
    EnvironmentEntityObservation,
    ImuObservation,
    ObservationIdentityError,
    RobotStateObservation,
    SensorAvailability,
    SensorHealthObservation,
    SensorKind,
    VisualFrameObservation,
    VisualInterpretationObservation,
    MAX_VISUAL_SOURCE_REFERENCES,
    WorldModelValidationError,
    rebuild_observation,
)

from .errors import PerceptionClockRegressionError, PerceptionConfigurationError
from .models import (
    AdmissionReason,
    AdmissionResult,
    AdmissionStatus,
    EvidenceFailureKind,
    PerceptionSourceContract,
    PerceptionStats,
    PerceptionTrustConfig,
    validate_time,
)


class PerceptionTrustBoundary:
    """Validate admissibility without claiming measurement truth or authority."""

    __slots__ = (
        "_accepted_count",
        "_config",
        "_duplicate_count",
        "_last_by_key",
        "_last_now_ns",
        "_last_receipt_monotonic_ns",
        "_lock",
        "_rejected_count",
        "_visual_sources",
    )

    def __init__(self, config: PerceptionTrustConfig) -> None:
        if type(config) is not PerceptionTrustConfig:
            raise PerceptionConfigurationError("trust boundary config is invalid")
        self._config = config
        self._last_by_key: dict[tuple[str, str], tuple[int, str]] = {}
        self._last_now_ns: int | None = None
        self._last_receipt_monotonic_ns: int | None = None
        self._accepted_count = 0
        self._duplicate_count = 0
        self._rejected_count = 0
        self._visual_sources: dict[str, VisualFrameObservation] = {}
        self._lock = RLock()

    @property
    def config(self) -> PerceptionTrustConfig:
        return self._config

    def reset(self) -> None:
        with self._lock:
            self._last_by_key.clear()
            self._last_now_ns = None
            self._last_receipt_monotonic_ns = None
            self._accepted_count = 0
            self._duplicate_count = 0
            self._rejected_count = 0
            self._visual_sources.clear()

    def _reject(
        self,
        reason: AdmissionReason,
        detail: str,
        observation_id: str | None = None,
    ) -> AdmissionResult:
        self._rejected_count += 1
        return AdmissionResult(
            status=AdmissionStatus.REJECTED,
            reason=reason,
            observation_id=observation_id,
            observation=None,
            detail=detail,
        )

    def _source_for(self, observation) -> PerceptionSourceContract | None:
        if type(observation) is RobotStateObservation:
            matches = tuple(
                source
                for source in self._config.sources
                if source.sensor.kind is SensorKind.JOINT_STATE
                and source.provenance == observation.provenance
            )
        elif type(observation) in {
            ImuObservation,
            BodyPoseObservation,
            VisualFrameObservation,
            VisualInterpretationObservation,
            SensorHealthObservation,
        }:
            matches = tuple(
                source
                for source in self._config.sources
                if source.sensor == observation.sensor
                and source.provenance == observation.provenance
            )
        else:
            matches = ()
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _state_key(observation, source: PerceptionSourceContract) -> tuple[str, str]:
        if type(observation) is SensorHealthObservation:
            return (f"health:{source.sensor.kind.value}", source.sensor.sensor_id)
        if type(observation) is VisualInterpretationObservation:
            return (
                f"visual_interpretation:{source.sensor.sensor_id}",
                observation.producer.producer_id,
            )
        return (source.sensor.kind.value, source.sensor.sensor_id)

    def _purge_visual_sources(self, *, now_ns: int) -> None:
        cutoff = now_ns - self._config.retention_ttl_ns
        expired = tuple(
            observation_id
            for observation_id, frame in self._visual_sources.items()
            if frame.observed_at_ns < cutoff
        )
        for observation_id in expired:
            del self._visual_sources[observation_id]

    def _remember_visual_source(self, frame: VisualFrameObservation) -> None:
        self._visual_sources[frame.observation_id] = frame
        while len(self._visual_sources) > MAX_VISUAL_SOURCE_REFERENCES:
            oldest_id = min(
                self._visual_sources,
                key=lambda observation_id: (
                    self._visual_sources[observation_id].observed_at_ns,
                    observation_id,
                ),
            )
            del self._visual_sources[oldest_id]

    def admit(
        self,
        observation,
        *,
        now_ns: int,
        received_at_monotonic_ns: int,
    ) -> AdmissionResult:
        """Reconstruct then admit one canonical observation under exact policy."""
        try:
            rebuilt = rebuild_observation(observation)
        except ObservationIdentityError as error:
            with self._lock:
                return self._reject(AdmissionReason.IDENTITY_MISMATCH, error.detail)
        except WorldModelValidationError as error:
            with self._lock:
                return self._reject(AdmissionReason.MALFORMED_OBSERVATION, error.detail)
        if type(rebuilt) is EnvironmentEntityObservation:
            with self._lock:
                return self._reject(
                    AdmissionReason.MALFORMED_OBSERVATION,
                    "v1 perception admits proprioceptive evidence only",
                    rebuilt.observation_id,
                )
        now = validate_time(now_ns, "source now")
        receipt = validate_time(received_at_monotonic_ns, "monotonic receipt")
        with self._lock:
            if self._last_now_ns is not None and now < self._last_now_ns:
                raise PerceptionClockRegressionError(
                    "source clock regressed; reset the evidence epoch before reuse"
                )
            self._last_now_ns = now
            if (
                self._last_receipt_monotonic_ns is not None
                and receipt < self._last_receipt_monotonic_ns
            ):
                return self._reject(
                    AdmissionReason.RECEIPT_TIME_REGRESSION,
                    "monotonic receipt time regressed",
                    rebuilt.observation_id,
                )
            self._last_receipt_monotonic_ns = receipt
            if rebuilt.robot_id != self._config.robot_id:
                return self._reject(
                    AdmissionReason.WRONG_ROBOT_IDENTITY,
                    "observation robot identity does not match the trust boundary",
                    rebuilt.observation_id,
                )
            if rebuilt.provenance.clock is not self._config.source_clock:
                return self._reject(
                    AdmissionReason.CLOCK_DOMAIN_MISMATCH,
                    "observation clock is not the configured evidence clock",
                    rebuilt.observation_id,
                )
            source = self._source_for(rebuilt)
            if source is None:
                sensor_id = getattr(getattr(rebuilt, "sensor", None), "sensor_id", None)
                matching_identities = tuple(
                    item.sensor
                    for item in self._config.sources
                    if item.sensor.sensor_id == sensor_id
                )
                if sensor_id is not None and not matching_identities:
                    reason = AdmissionReason.UNKNOWN_SENSOR
                elif any(
                    identity.kind == getattr(rebuilt, "sensor", None).kind
                    and identity.frame_id
                    != getattr(rebuilt, "sensor", None).frame_id
                    for identity in matching_identities
                ):
                    reason = AdmissionReason.FRAME_MISMATCH
                else:
                    reason = AdmissionReason.PROVENANCE_NOT_ALLOWED
                return self._reject(
                    reason,
                    "observation does not match one exact reviewed source contract",
                    rebuilt.observation_id,
                )
            if type(rebuilt) is VisualInterpretationObservation:
                producer = next(
                    (
                        configured
                        for configured in self._config.visual_interpretation_producers
                        if configured.producer_id == rebuilt.producer.producer_id
                    ),
                    None,
                )
                if producer is None or producer != rebuilt.producer:
                    return self._reject(
                        AdmissionReason.UNKNOWN_PRODUCER,
                        "visual result producer is not one exact reviewed producer",
                        rebuilt.observation_id,
                    )
                source_frame = self._visual_sources.get(
                    rebuilt.source_visual_observation_id
                )
                if source_frame is None:
                    return self._reject(
                        AdmissionReason.SOURCE_FRAME_NOT_ADMITTED,
                        "visual result does not reference a retained admitted frame",
                        rebuilt.observation_id,
                    )
                if (
                    source_frame.robot_id != rebuilt.robot_id
                    or source_frame.sensor != rebuilt.sensor
                    or source_frame.sensor.frame_id != rebuilt.reference_frame_id
                    or source_frame.observed_at_ns != rebuilt.observed_at_ns
                    or source_frame.provenance != rebuilt.provenance
                    or source_frame.fingerprint != rebuilt.source_visual_fingerprint
                ):
                    return self._reject(
                        AdmissionReason.SOURCE_FRAME_MISMATCH,
                        "visual result source metadata differs from its admitted frame",
                        rebuilt.observation_id,
                    )
                if rebuilt.result_at_ns > now + self._config.permitted_future_skew_ns:
                    return self._reject(
                        AdmissionReason.RESULT_TIME_INVALID,
                        "visual result time is beyond permitted future skew",
                        rebuilt.observation_id,
                    )
            if type(rebuilt) is BodyPoseObservation and (
                rebuilt.pose.frame_id != source.pose_source_frame_id
                or rebuilt.pose.child_frame_id != source.sensor.frame_id
            ):
                return self._reject(
                    AdmissionReason.FRAME_MISMATCH,
                    "body pose does not match the reviewed source/target frames",
                    rebuilt.observation_id,
                )
            if rebuilt.observed_at_ns > now + self._config.permitted_future_skew_ns:
                return self._reject(
                    AdmissionReason.FUTURE_OBSERVATION,
                    "observation time is beyond permitted future skew",
                    rebuilt.observation_id,
                )
            if rebuilt.observed_at_ns < now - self._config.retention_ttl_ns:
                return self._reject(
                    AdmissionReason.STALE_OBSERVATION,
                    "observation was already beyond retention at admission",
                    rebuilt.observation_id,
                )
            key = self._state_key(rebuilt, source)
            current = self._last_by_key.get(key)
            ordering_time = (
                rebuilt.result_at_ns
                if type(rebuilt) is VisualInterpretationObservation
                else rebuilt.observed_at_ns
            )
            if current is not None:
                current_time, current_id = current
                if rebuilt.observation_id == current_id:
                    self._duplicate_count += 1
                    return AdmissionResult(
                        status=AdmissionStatus.DUPLICATE,
                        reason=AdmissionReason.DUPLICATE,
                        observation_id=rebuilt.observation_id,
                        observation=None,
                        detail="equivalent evidence is already admitted",
                    )
                if ordering_time < current_time:
                    return self._reject(
                        AdmissionReason.OUT_OF_ORDER,
                        "newer evidence for this source key is already admitted",
                        rebuilt.observation_id,
                    )
                if ordering_time == current_time:
                    return self._reject(
                        AdmissionReason.TEMPORAL_CONFLICT,
                        "same source key and time carry conflicting evidence",
                        rebuilt.observation_id,
                    )
            self._last_by_key[key] = (ordering_time, rebuilt.observation_id)
            self._purge_visual_sources(now_ns=now)
            if type(rebuilt) is VisualFrameObservation:
                self._remember_visual_source(rebuilt)
            self._accepted_count += 1
            return AdmissionResult(
                status=AdmissionStatus.ACCEPTED,
                reason=AdmissionReason.ACCEPTED,
                observation_id=rebuilt.observation_id,
                observation=rebuilt,
                detail="evidence admitted under the exact reviewed source contract",
            )

    def report_failure(
        self,
        *,
        sensor_id: str,
        failure: EvidenceFailureKind,
        observed_at_ns: int,
        now_ns: int,
        received_at_monotonic_ns: int,
    ) -> AdmissionResult:
        """Convert a typed adapter/source failure into explicit health evidence."""
        if not isinstance(failure, EvidenceFailureKind):
            raise PerceptionConfigurationError("evidence failure kind is invalid")
        matches = tuple(
            source for source in self._config.sources if source.sensor.sensor_id == sensor_id
        )
        if len(matches) != 1:
            with self._lock:
                return self._reject(
                    AdmissionReason.UNKNOWN_SENSOR,
                    "failure report does not identify one reviewed source",
                )
        source = matches[0]
        availability_by_failure = {
            EvidenceFailureKind.FRAME_LOOKUP_UNAVAILABLE: SensorAvailability.UNAVAILABLE,
            EvidenceFailureKind.FRAME_LOOKUP_CONNECTIVITY: SensorAvailability.ERROR,
            EvidenceFailureKind.FRAME_LOOKUP_EXTRAPOLATION: SensorAvailability.ERROR,
            EvidenceFailureKind.FRAME_LOOKUP_TIMEOUT: SensorAvailability.UNAVAILABLE,
            EvidenceFailureKind.INVALID_FRAME_REQUEST: SensorAvailability.ERROR,
            EvidenceFailureKind.STALE_TRANSFORM: SensorAvailability.STALE,
            EvidenceFailureKind.REJECTED_PROVENANCE: SensorAvailability.ERROR,
            EvidenceFailureKind.MALFORMED_NUMERIC_POSE: SensorAvailability.ERROR,
            EvidenceFailureKind.INVALID_QUATERNION: SensorAvailability.ERROR,
            EvidenceFailureKind.INVALID_COVARIANCE: SensorAvailability.ERROR,
            EvidenceFailureKind.SOURCE_UNAVAILABLE: SensorAvailability.UNAVAILABLE,
            EvidenceFailureKind.ADAPTER_RESTARTED: SensorAvailability.UNAVAILABLE,
        }
        observation = SensorHealthObservation(
            robot_id=self._config.robot_id,
            sensor=source.sensor,
            availability=availability_by_failure[failure],
            observed_at_ns=observed_at_ns,
            provenance=source.provenance,
            evidence_detail=failure.value,
        )
        result = self.admit(
            observation,
            now_ns=now_ns,
            received_at_monotonic_ns=received_at_monotonic_ns,
        )
        if result.status is not AdmissionStatus.ACCEPTED:
            return result
        return AdmissionResult(
            status=result.status,
            reason=AdmissionReason(failure.value),
            observation_id=result.observation_id,
            observation=result.observation,
            detail=f"typed failure retained as {observation.availability.value} evidence",
        )

    def stats(self) -> PerceptionStats:
        with self._lock:
            return PerceptionStats(
                accepted_count=self._accepted_count,
                duplicate_count=self._duplicate_count,
                rejected_count=self._rejected_count,
                tracked_source_key_count=len(self._last_by_key),
                configured_source_count=len(self._config.sources),
                tracked_visual_source_count=len(self._visual_sources),
            )
