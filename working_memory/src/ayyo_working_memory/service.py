"""Bounded deterministic current-state and recent-evidence retention."""

from __future__ import annotations

from threading import RLock

from ayyo_world_model import (
    EnvironmentEntityObservation,
    RobotJointCatalog,
    RobotStateObservation,
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
        "_entity_evidence",
        "_eviction_count",
        "_joint_evidence",
        "_last_now_ns",
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
        self._projector = WorldModelProjector(catalog)
        self._joint_evidence: dict[str, RobotStateObservation] = {}
        self._pose_evidence: RobotStateObservation | None = None
        self._entity_evidence: dict[str, EnvironmentEntityObservation] = {}
        self._recent: list[EvidenceEnvelope] = []
        self._last_now_ns: int | None = None
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
            self._entity_evidence.clear()
            self._recent.clear()
            self._last_now_ns = None
            self._accepted_count = 0
            self._duplicate_count = 0
            self._rejected_count = 0
            self._eviction_count = 0

    def _advance_time(self, now_ns: int) -> None:
        if type(now_ns) is not int or now_ns < 0:
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
            if rebuilt.observed_at_ns > now_ns + self._config.permitted_future_skew_ns:
                return self._reject(
                    rebuilt.observation_id,
                    IngestionReason.FUTURE_OBSERVATION,
                    "observation source time is beyond permitted future skew",
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
                observation = self._pose_evidence
                if observation is not None and key.identity != self._config.robot_id:
                    observation = None
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
            )
