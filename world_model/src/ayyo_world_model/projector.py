"""Pure projection of current accepted evidence into one World Snapshot."""

from __future__ import annotations

from collections.abc import Mapping

from .catalog import RobotJointCatalog
from .errors import WorldModelFailureCode, WorldModelValidationError
from .models import (
    EnvironmentEntityObservation,
    FreshnessState,
    ObservedJointState,
    ObservedPoseState,
    RobotAvailability,
    RobotBodyState,
    RobotStateObservation,
    WorldEntity,
    WorldSnapshot,
    rebuild_observation,
)


def freshness_for(*, observed_at_ns: int, now_ns: int, fresh_for_ns: int) -> FreshnessState:
    if type(now_ns) is not int or now_ns < 0 or type(fresh_for_ns) is not int or fresh_for_ns < 0:
        raise WorldModelValidationError(
            WorldModelFailureCode.SNAPSHOT_INVARIANT,
            "freshness requires non-negative integer source times",
        )
    return (
        FreshnessState.FRESH
        if observed_at_ns >= now_ns - fresh_for_ns
        else FreshnessState.STALE
    )


class WorldModelProjector:
    """Create immutable state from evidence selected by Working Memory."""

    __slots__ = ("_catalog",)

    def __init__(self, catalog: RobotJointCatalog) -> None:
        if type(catalog) is not RobotJointCatalog:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "World Model projector requires a RobotJointCatalog",
            )
        self._catalog = catalog

    def project(
        self,
        *,
        now_ns: int,
        fresh_for_ns: int,
        joint_evidence: Mapping[str, RobotStateObservation],
        pose_evidence: RobotStateObservation | None,
        entity_evidence: Mapping[str, EnvironmentEntityObservation],
    ) -> WorldSnapshot:
        joints: list[ObservedJointState] = []
        for joint_name in sorted(joint_evidence):
            observation = rebuild_observation(joint_evidence[joint_name])
            assert type(observation) is RobotStateObservation
            self._catalog.validate_observation(observation)
            joint = next(
                (item for item in observation.joints if item.joint_name == joint_name),
                None,
            )
            if joint is None:
                raise WorldModelValidationError(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "joint evidence key is absent from its observation",
                )
            joints.append(
                ObservedJointState(
                    joint=joint,
                    observed_at_ns=observation.observed_at_ns,
                    provenance=observation.provenance,
                    confidence=observation.confidence,
                    freshness=freshness_for(
                        observed_at_ns=observation.observed_at_ns,
                        now_ns=now_ns,
                        fresh_for_ns=fresh_for_ns,
                    ),
                    observation_id=observation.observation_id,
                    observation_fingerprint=observation.fingerprint,
                )
            )
        observed_pose = None
        if pose_evidence is not None:
            rebuilt = rebuild_observation(pose_evidence)
            assert type(rebuilt) is RobotStateObservation and rebuilt.base_pose is not None
            observed_pose = ObservedPoseState(
                pose=rebuilt.base_pose,
                observed_at_ns=rebuilt.observed_at_ns,
                provenance=rebuilt.provenance,
                confidence=rebuilt.confidence,
                freshness=freshness_for(
                    observed_at_ns=rebuilt.observed_at_ns,
                    now_ns=now_ns,
                    fresh_for_ns=fresh_for_ns,
                ),
                observation_id=rebuilt.observation_id,
            )
        known = self._catalog.observable_joint_names
        availability = (
            RobotAvailability.UNAVAILABLE
            if not joints
            else RobotAvailability.AVAILABLE
            if len(joints) == len(known)
            else RobotAvailability.PARTIAL
        )
        robot = RobotBodyState(
            robot_id=self._catalog.robot_id,
            known_joint_names=known,
            joints=tuple(joints),
            base_pose=observed_pose,
            availability=availability,
        )
        entities: list[WorldEntity] = []
        for entity_id in sorted(entity_evidence):
            observation = rebuild_observation(entity_evidence[entity_id])
            assert type(observation) is EnvironmentEntityObservation
            if observation.robot_id != self._catalog.robot_id:
                raise WorldModelValidationError(
                    WorldModelFailureCode.WRONG_ROBOT_IDENTITY,
                    "environment evidence belongs to another robot",
                )
            if observation.entity.entity_id != entity_id:
                raise WorldModelValidationError(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "entity evidence key and identity disagree",
                )
            entities.append(
                WorldEntity(
                    identity=observation.entity,
                    pose=observation.pose,
                    properties=observation.properties,
                    observed_at_ns=observation.observed_at_ns,
                    provenance=observation.provenance,
                    confidence=observation.confidence,
                    freshness=freshness_for(
                        observed_at_ns=observation.observed_at_ns,
                        now_ns=now_ns,
                        fresh_for_ns=fresh_for_ns,
                    ),
                    observation_id=observation.observation_id,
                )
            )
        return WorldSnapshot(
            captured_at_ns=now_ns,
            robot=robot,
            entities=tuple(entities),
        )
