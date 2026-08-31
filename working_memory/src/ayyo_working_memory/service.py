"""Bounded deterministic current-state and recent-evidence retention."""

from __future__ import annotations

from threading import RLock

from ayyo_world_model import (
    BodyPoseObservation,
    DepthFrameObservation,
    FusedRgbdObservation,
    EnvironmentEntityObservation,
    ImuObservation,
    MAX_OBSERVATION_TIME_NS,
    RobotJointCatalog,
    RobotStateObservation,
    SensorHealthObservation,
    SensorIdentity,
    VisualFrameObservation,
    VisualInterpretationObservation,
    WorldEntity,
    WorldModelFailureCode,
    WorldModelProjector,
    WorldModelValidationError,
    WorldSnapshot,
    rebuild_observation,
)

from .errors import (
    WorkingMemoryClockRegressionError,
    WorkingMemoryConfigurationError,
)
from .models import (
    EvidenceEnvelope,
    FreshnessQueryResult,
    IngestionReason,
    IngestionResult,
    IngestionStatus,
    StateKey,
    StateKeyKind,
    WorkingMemoryConfig,
    WorkingMemoryFreshness,
    WorkingMemoryStats,
)


_WORLD_FAILURE_TO_REASON = {
    WorldModelFailureCode.WRONG_ROBOT_IDENTITY: IngestionReason.WRONG_ROBOT_IDENTITY,
    WorldModelFailureCode.UNKNOWN_JOINT: IngestionReason.UNKNOWN_JOINT,
    WorldModelFailureCode.FIXED_JOINT: IngestionReason.FIXED_JOINT,
    WorldModelFailureCode.JOINT_BELOW_MINIMUM: IngestionReason.INVALID_JOINT_VALUE,
    WorldModelFailureCode.JOINT_ABOVE_MAXIMUM: IngestionReason.INVALID_JOINT_VALUE,
    WorldModelFailureCode.JOINT_VELOCITY_EXCEEDED: IngestionReason.INVALID_JOINT_VALUE,
    WorldModelFailureCode.JOINT_EFFORT_EXCEEDED: IngestionReason.INVALID_JOINT_VALUE,
}


class WorkingMemory:
    """No-background-thread, bounded retention for current/recent evidence."""

    __slots__ = (
        "_accepted_count",
        "_catalog",
        "_config",
        "_duplicate_count",
        "_depth_evidence",
        "_entity_evidence",
        "_eviction_count",
        "_fused_rgbd_evidence",
        "_body_pose_evidence",
        "_health_evidence",
        "_imu_evidence",
        "_joint_evidence",
        "_visual_evidence",
        "_visual_interpretation_evidence",
        "_last_now_ns",
        "_last_receipt_monotonic_ns",
        "_lock",
        "_pose_evidence",
        "_projector",
        "_recent",
        "_rejected_count",
    )

    def __init__(self, catalog: RobotJointCatalog, config: WorkingMemoryConfig) -> None:
        if type(catalog) is not RobotJointCatalog:
            raise WorkingMemoryConfigurationError(
                "Working Memory requires an authoritative RobotJointCatalog"
            )
        if type(config) is not WorkingMemoryConfig:
            raise WorkingMemoryConfigurationError("Working Memory config is invalid")
        if catalog.robot_id != config.robot_id:
            raise WorkingMemoryConfigurationError(
                "Working Memory robot identity and joint catalog disagree"
            )
        self._catalog = catalog
        self._config = config
        self._projector = WorldModelProjector(catalog, config.sensors)
        self._joint_evidence: dict[str, RobotStateObservation] = {}
        self._pose_evidence: RobotStateObservation | None = None
        self._imu_evidence: dict[str, ImuObservation] = {}
        self._depth_evidence: dict[str, DepthFrameObservation] = {}
        self._fused_rgbd_evidence: dict[str, FusedRgbdObservation] = {}
        self._visual_evidence: dict[str, VisualFrameObservation] = {}
        self._visual_interpretation_evidence: dict[
            tuple[str, str], VisualInterpretationObservation
        ] = {}
        self._body_pose_evidence: dict[str, BodyPoseObservation] = {}
        self._health_evidence: dict[str, SensorHealthObservation] = {}
        self._entity_evidence: dict[str, EnvironmentEntityObservation] = {}
        self._recent: list[EvidenceEnvelope] = []
        self._last_now_ns: int | None = None
        self._last_receipt_monotonic_ns: int | None = None
        self._accepted_count = 0
        self._duplicate_count = 0
        self._rejected_count = 0
        self._eviction_count = 0
        self._lock = RLock()

    @property
    def config(self) -> WorkingMemoryConfig:
        return self._config

    def reset(self) -> None:
        """Discard all temporary evidence, including time and counters."""
        with self._lock:
            self._joint_evidence.clear()
            self._pose_evidence = None
            self._imu_evidence.clear()
            self._depth_evidence.clear()
            self._fused_rgbd_evidence.clear()
            self._visual_evidence.clear()
            self._visual_interpretation_evidence.clear()
            self._body_pose_evidence.clear()
            self._health_evidence.clear()
            self._entity_evidence.clear()
            self._recent.clear()
            self._last_now_ns = None
            self._last_receipt_monotonic_ns = None
            self._accepted_count = 0
            self._duplicate_count = 0
            self._rejected_count = 0
            self._eviction_count = 0

    def _advance_time(self, now_ns: int) -> None:
        if (
            type(now_ns) is not int
            or not 0 <= now_ns <= MAX_OBSERVATION_TIME_NS
        ):
            raise WorkingMemoryConfigurationError(
                "Working Memory requires non-negative integer source time"
            )
        if self._last_now_ns is not None and now_ns < self._last_now_ns:
            raise WorkingMemoryClockRegressionError(
                "source clock regressed; reset temporary state before reuse"
            )
        self._last_now_ns = now_ns
        self._purge_expired(now_ns)

    def _purge_expired(self, now_ns: int) -> None:
        threshold = now_ns - self._config.retention_ttl_ns
        expired_joint_names = [
            name
            for name, observation in self._joint_evidence.items()
            if observation.observed_at_ns < threshold
        ]
        for name in expired_joint_names:
            del self._joint_evidence[name]
        if (
            self._pose_evidence is not None
            and self._pose_evidence.observed_at_ns < threshold
        ):
            self._pose_evidence = None
        self._imu_evidence = {
            sensor_id: observation
            for sensor_id, observation in self._imu_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        self._depth_evidence = {
            sensor_id: observation
            for sensor_id, observation in self._depth_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        self._fused_rgbd_evidence = {
            sensor_id: observation
            for sensor_id, observation in self._fused_rgbd_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        self._visual_evidence = {
            sensor_id: observation
            for sensor_id, observation in self._visual_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        self._visual_interpretation_evidence = {
            key: observation
            for key, observation in self._visual_interpretation_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        self._body_pose_evidence = {
            sensor_id: observation
            for sensor_id, observation in self._body_pose_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        self._health_evidence = {
            sensor_id: observation
            for sensor_id, observation in self._health_evidence.items()
            if observation.observed_at_ns >= threshold
        }
        expired_entities = [
            entity_id
            for entity_id, observation in self._entity_evidence.items()
            if observation.observed_at_ns < threshold
        ]
        for entity_id in expired_entities:
            del self._entity_evidence[entity_id]
        self._recent = [
            item
            for item in self._recent
            if item.observation.observed_at_ns >= threshold
        ]

    def _current_observation_ids(self) -> set[str]:
        identities = {item.observation_id for item in self._joint_evidence.values()}
        identities.update(item.observation_id for item in self._entity_evidence.values())
        if self._pose_evidence is not None:
            identities.add(self._pose_evidence.observation_id)
        identities.update(item.observation_id for item in self._imu_evidence.values())
        identities.update(
            item.observation_id for item in self._depth_evidence.values()
        )
        identities.update(
            item.observation_id for item in self._fused_rgbd_evidence.values()
        )
        identities.update(
            item.observation_id for item in self._visual_evidence.values()
        )
        identities.update(
            item.observation_id
            for item in self._visual_interpretation_evidence.values()
        )
        identities.update(
            item.observation_id for item in self._body_pose_evidence.values()
        )
        identities.update(item.observation_id for item in self._health_evidence.values())
        return identities

    def _reject(
        self,
        observation_id: str,
        reason: IngestionReason,
        detail: str,
    ) -> IngestionResult:
        self._rejected_count += 1
        return IngestionResult(
            status=IngestionStatus.REJECTED,
            reason=reason,
            observation_id=observation_id,
            detail=detail,
        )

    def ingest(
        self,
        observation,
        *,
        now_ns: int,
        received_at_monotonic_ns: int,
    ) -> IngestionResult:
        """Validate and atomically retain relevant state from one observation."""
        rebuilt = rebuild_observation(observation)
        envelope = EvidenceEnvelope(
            observation=rebuilt,
            received_at_monotonic_ns=received_at_monotonic_ns,
        )
        with self._lock:
            self._advance_time(now_ns)
            if (
                self._last_receipt_monotonic_ns is not None
                and received_at_monotonic_ns < self._last_receipt_monotonic_ns
            ):
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.RECEIPT_TIME_REGRESSION,
                    "monotonic receipt time regressed",
                )
            self._last_receipt_monotonic_ns = received_at_monotonic_ns
            if rebuilt.robot_id != self._config.robot_id:
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.WRONG_ROBOT_IDENTITY,
                    "observation robot identity does not match Working Memory",
                )
            if rebuilt.provenance not in self._config.allowed_provenance:
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.PROVENANCE_NOT_ALLOWED,
                    "observation provenance is outside the reviewed source profiles",
                )
            if type(rebuilt) in {
                ImuObservation,
                BodyPoseObservation,
                DepthFrameObservation,
                FusedRgbdObservation,
                VisualFrameObservation,
                VisualInterpretationObservation,
                SensorHealthObservation,
            }:
                known_sensors = {
                    sensor.sensor_id: sensor for sensor in self._config.sensors
                }
                if known_sensors.get(rebuilt.sensor.sensor_id) != rebuilt.sensor:
                    return self._reject(
                        rebuilt.observation_id,
                        IngestionReason.UNKNOWN_SENSOR,
                        "observation sensor is outside the reviewed sensor catalog",
                    )
            if rebuilt.observed_at_ns > now_ns + self._config.permitted_future_skew_ns:
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.FUTURE_OBSERVATION,
                    "observation source time is beyond permitted future skew",
                )
            if (
                type(rebuilt) in {
                    VisualInterpretationObservation,
                    FusedRgbdObservation,
                }
                and rebuilt.result_at_ns
                > now_ns + self._config.permitted_future_skew_ns
            ):
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.FUTURE_OBSERVATION,
                    "visual result time is beyond permitted future skew",
                )
            if rebuilt.observed_at_ns < now_ns - self._config.retention_ttl_ns:
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.EXPIRED_OBSERVATION,
                    "observation expired before ingestion",
                )
            known_ids = self._current_observation_ids()
            known_ids.update(item.observation.observation_id for item in self._recent)
            if rebuilt.observation_id in known_ids:
                self._duplicate_count += 1
                return IngestionResult(
                    status=IngestionStatus.DUPLICATE,
                    reason=IngestionReason.DUPLICATE_OBSERVATION,
                    observation_id=rebuilt.observation_id,
                    detail="equivalent evidence is already retained",
                )
            if type(rebuilt) is RobotStateObservation:
                try:
                    self._catalog.validate_observation(rebuilt)
                except WorldModelValidationError as error:
                    return self._reject(
                        rebuilt.observation_id,
                        _WORLD_FAILURE_TO_REASON.get(
                            error.code,
                            IngestionReason.MALFORMED_OBSERVATION,
                        ),
                        error.detail,
                    )
                return self._ingest_robot(rebuilt, envelope)
            if type(rebuilt) in {
                ImuObservation,
                BodyPoseObservation,
                DepthFrameObservation,
                FusedRgbdObservation,
                VisualFrameObservation,
                SensorHealthObservation,
                VisualInterpretationObservation,
            }:
                return self._ingest_sensor(rebuilt, envelope)
            assert type(rebuilt) is EnvironmentEntityObservation
            return self._ingest_entity(rebuilt, envelope)

    @staticmethod
    def _compare_current(current, incoming) -> str:
        if current is None:
            return "new"
        if incoming.observed_at_ns < current.observed_at_ns:
            return "older"
        if incoming.observed_at_ns == current.observed_at_ns:
            return "same_time_conflict"
        return "newer"

    def _ingest_robot(
        self,
        observation: RobotStateObservation,
        envelope: EvidenceEnvelope,
    ) -> IngestionResult:
        decisions: list[tuple[StateKey, str]] = []
        for joint in observation.joints:
            decisions.append(
                (
                    StateKey(StateKeyKind.ROBOT_JOINT, joint.joint_name),
                    self._compare_current(
                        self._joint_evidence.get(joint.joint_name),
                        observation,
                    ),
                )
            )
        if observation.base_pose is not None:
            decisions.append(
                (
                    StateKey(StateKeyKind.ROBOT_BASE_POSE, observation.robot_id),
                    self._compare_current(self._pose_evidence, observation),
                )
            )
        if any(decision == "same_time_conflict" for _, decision in decisions):
            return self._reject(
                observation.observation_id,
                IngestionReason.TEMPORAL_CONFLICT,
                "same state key and source time carry different evidence",
            )
        updated = tuple(
            sorted(
                (key for key, decision in decisions if decision in {"new", "newer"}),
                key=lambda item: (item.kind.value, item.identity),
            )
        )
        if not updated:
            return self._reject(
                observation.observation_id,
                IngestionReason.OLDER_OBSERVATION,
                "all affected robot state is newer than this observation",
            )
        for key in updated:
            if key.kind is StateKeyKind.ROBOT_JOINT:
                self._joint_evidence[key.identity] = observation
            else:
                self._pose_evidence = observation
        return self._accept(
            observation,
            envelope,
            updated,
            replaced=any(decision == "newer" for _, decision in decisions),
        )

    def _ingest_entity(
        self,
        observation: EnvironmentEntityObservation,
        envelope: EvidenceEnvelope,
    ) -> IngestionResult:
        entity_id = observation.entity.entity_id
        decision = self._compare_current(self._entity_evidence.get(entity_id), observation)
        if decision == "same_time_conflict":
            return self._reject(
                observation.observation_id,
                IngestionReason.TEMPORAL_CONFLICT,
                "same entity and source time carry different evidence",
            )
        if decision == "older":
            return self._reject(
                observation.observation_id,
                IngestionReason.OLDER_OBSERVATION,
                "a newer environment observation is already current",
            )
        self._entity_evidence[entity_id] = observation
        key = StateKey(StateKeyKind.ENVIRONMENT_ENTITY, entity_id)
        return self._accept(
            observation,
            envelope,
            (key,),
            replaced=decision == "newer",
        )

    def _ingest_sensor(
        self,
        observation: (
            ImuObservation
            | BodyPoseObservation
            | DepthFrameObservation
            | FusedRgbdObservation
            | VisualFrameObservation
            | VisualInterpretationObservation
            | SensorHealthObservation
        ),
        envelope: EvidenceEnvelope,
    ) -> IngestionResult:
        sensor_id = observation.sensor.sensor_id
        if type(observation) is ImuObservation:
            collection = self._imu_evidence
            key = StateKey(StateKeyKind.ROBOT_IMU, sensor_id)
        elif type(observation) is DepthFrameObservation:
            collection = self._depth_evidence
            key = StateKey(StateKeyKind.ROBOT_DEPTH, sensor_id)
        elif type(observation) is FusedRgbdObservation:
            rgb_candidates = tuple(self._visual_evidence.values()) + tuple(
                item.observation
                for item in self._recent
                if type(item.observation) is VisualFrameObservation
            )
            depth_candidates = tuple(self._depth_evidence.values()) + tuple(
                item.observation
                for item in self._recent
                if type(item.observation) is DepthFrameObservation
            )
            if observation.rgb_observation not in rgb_candidates or (
                observation.depth_observation not in depth_candidates
            ):
                return self._reject(
                    observation.observation_id,
                    IngestionReason.SOURCE_OBSERVATION_MISMATCH,
                    "fused RGB-D evidence does not match retained trusted components",
                )
            collection = self._fused_rgbd_evidence
            key = StateKey(StateKeyKind.ROBOT_RGBD_FUSION, sensor_id)
        elif type(observation) is VisualFrameObservation:
            collection = self._visual_evidence
            key = StateKey(StateKeyKind.ROBOT_VISUAL, sensor_id)
        elif type(observation) is VisualInterpretationObservation:
            producer = next(
                (
                    candidate
                    for candidate in self._config.visual_interpretation_producers
                    if candidate.producer_id == observation.producer.producer_id
                ),
                None,
            )
            if producer is None or producer != observation.producer:
                return self._reject(
                    observation.observation_id,
                    IngestionReason.UNKNOWN_PRODUCER,
                    "visual result producer is outside the reviewed producer catalog",
                )
            requirement = next(
                (
                    item
                    for item in self._config.visual_evaluation_requirements
                    if item.producer_id == observation.producer.producer_id
                ),
                None,
            )
            if observation.evaluation_reference is None:
                if requirement is not None:
                    return self._reject(
                        observation.observation_id,
                        IngestionReason.EVALUATION_REQUIRED,
                        "visual producer requires evaluated provenance",
                    )
            elif requirement is None or not requirement.matches(
                observation.producer,
                observation.evaluation_reference,
            ):
                return self._reject(
                    observation.observation_id,
                    IngestionReason.EVALUATION_MISMATCH,
                    "visual evaluation provenance differs from the allowlist",
                )
            source_frames = tuple(
                frame
                for frame in (
                    tuple(self._visual_evidence.values())
                    + tuple(
                        item.observation
                        for item in self._recent
                        if type(item.observation) is VisualFrameObservation
                    )
                )
                if frame.observation_id
                == observation.source_visual_observation_id
            )
            if not source_frames or any(
                frame.robot_id != observation.robot_id
                or frame.sensor != observation.sensor
                or frame.observed_at_ns != observation.observed_at_ns
                or frame.provenance != observation.provenance
                or frame.fingerprint != observation.source_visual_fingerprint
                for frame in source_frames
            ):
                return self._reject(
                    observation.observation_id,
                    IngestionReason.SOURCE_OBSERVATION_MISMATCH,
                    "visual result does not match retained trusted frame metadata",
                )
            interpretation_key = (
                sensor_id,
                observation.producer.producer_id,
            )
            collection = self._visual_interpretation_evidence
            key = StateKey(
                StateKeyKind.ROBOT_VISUAL_INTERPRETATION,
                "|".join(interpretation_key),
            )
        elif type(observation) is BodyPoseObservation:
            collection = self._body_pose_evidence
            key = StateKey(StateKeyKind.ROBOT_BASE_POSE, sensor_id)
        else:
            collection = self._health_evidence
            key = StateKey(StateKeyKind.SENSOR_HEALTH, sensor_id)
        collection_key = (
            interpretation_key
            if type(observation) is VisualInterpretationObservation
            else sensor_id
        )
        current = collection.get(collection_key)
        if type(observation) is VisualInterpretationObservation and current is not None:
            if observation.result_at_ns < current.result_at_ns:
                decision = "older"
            elif observation.result_at_ns == current.result_at_ns:
                decision = "same_time_conflict"
            else:
                decision = "newer"
        else:
            decision = self._compare_current(current, observation)
        if decision == "same_time_conflict":
            return self._reject(
                observation.observation_id,
                IngestionReason.TEMPORAL_CONFLICT,
                "same sensor state key and source time carry different evidence",
            )
        if decision == "older":
            return self._reject(
                observation.observation_id,
                IngestionReason.OLDER_OBSERVATION,
                "newer evidence for this sensor state key is already current",
            )
        collection[collection_key] = observation
        return self._accept(
            observation,
            envelope,
            (key,),
            replaced=decision == "newer",
        )

    def _accept(
        self,
        observation,
        envelope: EvidenceEnvelope,
        updated: tuple[StateKey, ...],
        *,
        replaced: bool,
    ) -> IngestionResult:
        self._recent.append(envelope)
        self._recent.sort(
            key=lambda item: (
                item.observation.observed_at_ns,
                item.observation.observation_id,
            )
        )
        if len(self._recent) > self._config.recent_evidence_capacity:
            del self._recent[: len(self._recent) - self._config.recent_evidence_capacity]
        evicted: list[StateKey] = []
        if len(self._entity_evidence) > self._config.environment_entity_capacity:
            victims = sorted(
                self._entity_evidence.items(),
                key=lambda item: (
                    item[1].observed_at_ns,
                    item[1].observation_id,
                    item[0],
                ),
            )[: len(self._entity_evidence) - self._config.environment_entity_capacity]
            for entity_id, _ in victims:
                del self._entity_evidence[entity_id]
                evicted.append(StateKey(StateKeyKind.ENVIRONMENT_ENTITY, entity_id))
        self._accepted_count += 1
        self._eviction_count += len(evicted)
        return IngestionResult(
            status=IngestionStatus.ACCEPTED,
            reason=(
                IngestionReason.ACCEPTED_REPLACEMENT
                if replaced
                else IngestionReason.ACCEPTED_NEW
            ),
            observation_id=observation.observation_id,
            updated_keys=updated,
            evicted_keys=tuple(
                sorted(evicted, key=lambda item: (item.kind.value, item.identity))
            ),
            detail="observation retained within configured bounds",
        )

    def current_snapshot(self, *, now_ns: int) -> WorldSnapshot:
        with self._lock:
            self._advance_time(now_ns)
            return self._projector.project(
                now_ns=now_ns,
                fresh_for_ns=self._config.freshness_ns,
                joint_evidence=dict(self._joint_evidence),
                pose_evidence=self._pose_evidence,
                entity_evidence=dict(self._entity_evidence),
                imu_evidence=dict(self._imu_evidence),
                body_pose_evidence=dict(self._body_pose_evidence),
                health_evidence=dict(self._health_evidence),
                depth_evidence=dict(self._depth_evidence),
                fused_rgbd_evidence=dict(self._fused_rgbd_evidence),
                visual_evidence=dict(self._visual_evidence),
                visual_interpretation_evidence=dict(
                    self._visual_interpretation_evidence
                ),
            )

    def get_robot_state(self, *, now_ns: int):
        return self.current_snapshot(now_ns=now_ns).robot

    def get_entity(self, entity_id: str, *, now_ns: int) -> WorldEntity | None:
        return self.current_snapshot(now_ns=now_ns).get_entity(entity_id)

    def recent_evidence(self, *, now_ns: int) -> tuple[EvidenceEnvelope, ...]:
        with self._lock:
            self._advance_time(now_ns)
            return tuple(self._recent)

    def query_freshness(
        self,
        key: StateKey,
        *,
        now_ns: int,
    ) -> FreshnessQueryResult:
        if type(key) is not StateKey:
            raise WorkingMemoryConfigurationError("freshness query requires a StateKey")
        with self._lock:
            self._advance_time(now_ns)
            if key.kind is StateKeyKind.ROBOT_JOINT:
                observation = self._joint_evidence.get(key.identity)
            elif key.kind is StateKeyKind.ROBOT_BASE_POSE:
                observation = self._body_pose_evidence.get(key.identity)
                if observation is None and key.identity == self._config.robot_id:
                    observation = self._pose_evidence
            elif key.kind is StateKeyKind.ROBOT_IMU:
                observation = self._imu_evidence.get(key.identity)
            elif key.kind is StateKeyKind.ROBOT_DEPTH:
                observation = self._depth_evidence.get(key.identity)
            elif key.kind is StateKeyKind.ROBOT_RGBD_FUSION:
                observation = self._fused_rgbd_evidence.get(key.identity)
            elif key.kind is StateKeyKind.ROBOT_VISUAL:
                observation = self._visual_evidence.get(key.identity)
            elif key.kind is StateKeyKind.ROBOT_VISUAL_INTERPRETATION:
                parts = key.identity.split("|", 1)
                observation = (
                    self._visual_interpretation_evidence.get((parts[0], parts[1]))
                    if len(parts) == 2
                    else None
                )
            elif key.kind is StateKeyKind.SENSOR_HEALTH:
                observation = self._health_evidence.get(key.identity)
            else:
                observation = self._entity_evidence.get(key.identity)
            if observation is None:
                return FreshnessQueryResult(
                    key=key,
                    freshness=WorkingMemoryFreshness.UNKNOWN,
                    observation_id=None,
                    observed_at_ns=None,
                    age_ns=None,
                )
            age = max(0, now_ns - observation.observed_at_ns)
            return FreshnessQueryResult(
                key=key,
                freshness=(
                    WorkingMemoryFreshness.FRESH
                    if age <= self._config.freshness_ns
                    else WorkingMemoryFreshness.STALE
                ),
                observation_id=observation.observation_id,
                observed_at_ns=observation.observed_at_ns,
                age_ns=age,
            )

    def stats(self, *, now_ns: int) -> WorkingMemoryStats:
        with self._lock:
            self._advance_time(now_ns)
            ids = self._current_observation_ids()
            ids.update(item.observation.observation_id for item in self._recent)
            references = (
                len(self._joint_evidence)
                + int(self._pose_evidence is not None)
                + len(self._imu_evidence)
                + len(self._depth_evidence)
                + len(self._fused_rgbd_evidence)
                + len(self._visual_evidence)
                + len(self._visual_interpretation_evidence)
                + len(self._body_pose_evidence)
                + len(self._health_evidence)
                + len(self._entity_evidence)
                + len(self._recent)
            )
            return WorkingMemoryStats(
                current_joint_count=len(self._joint_evidence),
                has_current_pose=self._pose_evidence is not None,
                current_entity_count=len(self._entity_evidence),
                recent_evidence_count=len(self._recent),
                retained_unique_observation_count=len(ids),
                retained_observation_reference_count=references,
                accepted_count=self._accepted_count,
                duplicate_count=self._duplicate_count,
                rejected_count=self._rejected_count,
                eviction_count=self._eviction_count,
                current_imu_count=len(self._imu_evidence),
                current_body_pose_count=len(self._body_pose_evidence),
                current_sensor_health_count=len(self._health_evidence),
                current_visual_count=len(self._visual_evidence),
                current_depth_count=len(self._depth_evidence),
                current_fused_rgbd_count=len(self._fused_rgbd_evidence),
                current_visual_interpretation_count=len(
                    self._visual_interpretation_evidence
                ),
            )
