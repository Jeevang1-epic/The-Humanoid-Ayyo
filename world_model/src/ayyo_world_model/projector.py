"""Pure projection of current accepted evidence into one World Snapshot."""

from __future__ import annotations

from collections.abc import Mapping

from .catalog import RobotJointCatalog
from .errors import WorldModelFailureCode, WorldModelValidationError
from .models import (
    BodyPoseObservation,
    EnvironmentEntityObservation,
    FreshnessState,
    ImuObservation,
    ObservedImuState,
    ObservedJointState,
    ObservedPoseState,
    RobotAvailability,
    RobotBodyState,
    RobotStateObservation,
    SensorAvailability,
    SensorAvailabilityState,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
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

    __slots__ = ("_catalog", "_sensors")

    def __init__(
        self,
        catalog: RobotJointCatalog,
        sensors: tuple[SensorIdentity, ...] = (),
    ) -> None:
        if type(catalog) is not RobotJointCatalog:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "World Model projector requires a RobotJointCatalog",
            )
        self._catalog = catalog
        if (
            type(sensors) is not tuple
            or any(type(sensor) is not SensorIdentity for sensor in sensors)
        ):
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "World Model sensors must be a typed tuple",
            )
        ordered = tuple(sorted(sensors, key=lambda item: item.sensor_id))
        if len({sensor.sensor_id for sensor in ordered}) != len(ordered):
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "World Model sensor identities must be unique",
            )
        self._sensors = ordered

    def project(
        self,
        *,
        now_ns: int,
        fresh_for_ns: int,
        joint_evidence: Mapping[str, RobotStateObservation],
        pose_evidence: RobotStateObservation | None,
        entity_evidence: Mapping[str, EnvironmentEntityObservation],
        imu_evidence: Mapping[str, ImuObservation] | None = None,
        body_pose_evidence: Mapping[str, BodyPoseObservation] | None = None,
        health_evidence: Mapping[str, SensorHealthObservation] | None = None,
    ) -> WorldSnapshot:
        imu_sources = {} if imu_evidence is None else dict(imu_evidence)
        body_pose_sources = (
            {} if body_pose_evidence is None else dict(body_pose_evidence)
        )
        health_sources = {} if health_evidence is None else dict(health_evidence)
        known_sensor_ids = {sensor.sensor_id for sensor in self._sensors}
        supplied_sensor_ids = (
            set(imu_sources) | set(body_pose_sources) | set(health_sources)
        )
        if not supplied_sensor_ids <= known_sensor_ids:
            raise WorldModelValidationError(
                WorldModelFailureCode.UNKNOWN_SENSOR,
                "projected evidence contains an unreviewed sensor identity",
            )
        joints: list[ObservedJointState] = []
        rebuilt_robot_evidence: dict[str, RobotStateObservation] = {}
        for joint_name in sorted(joint_evidence):
            source = joint_evidence[joint_name]
            observation = rebuilt_robot_evidence.get(source.observation_id)
            if observation is None:
                rebuilt = rebuild_observation(source)
                assert type(rebuilt) is RobotStateObservation
                observation = rebuilt
                rebuilt_robot_evidence[observation.observation_id] = observation
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
        if pose_evidence is not None and body_pose_sources:
            raise WorldModelValidationError(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "legacy and dedicated body-pose evidence cannot both be current",
            )
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
        sensor_states: list[SensorAvailabilityState] = []
        sensor_availability_by_id: dict[str, SensorAvailability] = {}
        for sensor in self._sensors:
            measurement = None
            if sensor.kind is SensorKind.JOINT_STATE and joint_evidence:
                measurement = max(
                    joint_evidence.values(),
                    key=lambda item: (item.observed_at_ns, item.observation_id),
                )
            elif sensor.kind is SensorKind.IMU:
                measurement = imu_sources.get(sensor.sensor_id)
            elif sensor.kind is SensorKind.BODY_POSE:
                measurement = body_pose_sources.get(sensor.sensor_id)
            health = health_sources.get(sensor.sensor_id)
            selected = (
                health
                if health is not None
                and (
                    measurement is None
                    or health.observed_at_ns >= measurement.observed_at_ns
                )
                else measurement
            )
            if selected is None:
                state = SensorAvailabilityState(
                    sensor=sensor,
                    availability=SensorAvailability.UNAVAILABLE,
                    observed_at_ns=None,
                    provenance=None,
                    observation_id=None,
                )
            else:
                selected_freshness = freshness_for(
                    observed_at_ns=selected.observed_at_ns,
                    now_ns=now_ns,
                    fresh_for_ns=fresh_for_ns,
                )
                availability = (
                    SensorAvailability.STALE
                    if selected_freshness is FreshnessState.STALE
                    else selected.availability
                    if type(selected) in {
                        ImuObservation,
                        BodyPoseObservation,
                        SensorHealthObservation,
                    }
                    else SensorAvailability.AVAILABLE
                )
                state = SensorAvailabilityState(
                    sensor=sensor,
                    availability=availability,
                    observed_at_ns=selected.observed_at_ns,
                    provenance=selected.provenance,
                    observation_id=selected.observation_id,
                )
            sensor_states.append(state)
            sensor_availability_by_id[sensor.sensor_id] = state.availability

        imu_states: list[ObservedImuState] = []
        for sensor_id in sorted(imu_sources):
            rebuilt = rebuild_observation(imu_sources[sensor_id])
            assert type(rebuilt) is ImuObservation
            if rebuilt.sensor.sensor_id != sensor_id:
                raise WorldModelValidationError(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "IMU evidence key and sensor identity disagree",
                )
            freshness = freshness_for(
                observed_at_ns=rebuilt.observed_at_ns,
                now_ns=now_ns,
                fresh_for_ns=fresh_for_ns,
            )
            imu_states.append(
                ObservedImuState(
                    observation=rebuilt,
                    freshness=freshness,
                    availability=(
                        SensorAvailability.STALE
                        if freshness is FreshnessState.STALE
                        else sensor_availability_by_id[sensor_id]
                    ),
                )
            )

        if body_pose_sources:
            if len(body_pose_sources) != 1:
                raise WorldModelValidationError(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "v1 body state can project at most one body-pose source",
                )
            sensor_id, source = next(iter(body_pose_sources.items()))
            rebuilt = rebuild_observation(source)
            assert type(rebuilt) is BodyPoseObservation
            if rebuilt.sensor.sensor_id != sensor_id:
                raise WorldModelValidationError(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "body-pose evidence key and sensor identity disagree",
                )
            pose_freshness = freshness_for(
                observed_at_ns=rebuilt.observed_at_ns,
                now_ns=now_ns,
                fresh_for_ns=fresh_for_ns,
            )
            observed_pose = ObservedPoseState(
                pose=rebuilt.pose,
                observed_at_ns=rebuilt.observed_at_ns,
                provenance=rebuilt.provenance,
                confidence=rebuilt.quality,
                freshness=pose_freshness,
                observation_id=rebuilt.observation_id,
                sensor=rebuilt.sensor,
                covariance=rebuilt.covariance,
                availability=(
                    SensorAvailability.STALE
                    if pose_freshness is FreshnessState.STALE
                    else sensor_availability_by_id[sensor_id]
                ),
                observation_fingerprint=rebuilt.fingerprint,
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
            imu_states=tuple(imu_states),
            sensor_states=tuple(sensor_states),
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
