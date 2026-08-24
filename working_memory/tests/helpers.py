from __future__ import annotations

from ayyo_working_memory import WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    EnvironmentEntityObservation,
    JointContract,
    JointObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
    RobotStateObservation,
    WorldEntityIdentity,
    WorldEntityKind,
)


TEST_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.working-memory.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.robot-state.v1",
)
OTHER_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.working-memory.other.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.robot-state.v1",
)


def catalog() -> RobotJointCatalog:
    return RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract("fixed_joint", "fixed", None, None, None, None),
            JointContract("head_pitch_joint", "revolute", -0.6, 0.6, 1.0, 4.0),
            JointContract("neck_yaw_joint", "revolute", -1.2, 1.2, 1.5, 8.0),
        ),
    )


def memory(*, recent=4, entities=3, freshness=50, ttl=100, skew=5) -> WorkingMemory:
    return WorkingMemory(
        catalog(),
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            allowed_provenance=(TEST_PROVENANCE,),
            freshness_ns=freshness,
            retention_ttl_ns=ttl,
            permitted_future_skew_ns=skew,
            recent_evidence_capacity=recent,
            environment_entity_capacity=entities,
        ),
    )


def robot_observation(
    *,
    time=100,
    position=0.1,
    joint="neck_yaw_joint",
    robot_id=AYYO_ROBOT_ID,
    provenance=TEST_PROVENANCE,
    joints=None,
):
    return RobotStateObservation(
        robot_id=robot_id,
        joints=(JointObservation(joint, position),) if joints is None else joints,
        observed_at_ns=time,
        provenance=provenance,
        confidence=1.0,
    )


def entity_observation(
    entity_id: str,
    *,
    time=100,
    value=None,
    robot_id=AYYO_ROBOT_ID,
    provenance=TEST_PROVENANCE,
):
    return EnvironmentEntityObservation(
        robot_id=robot_id,
        entity=WorldEntityIdentity(entity_id, WorldEntityKind.OBJECT),
        properties={"value": entity_id if value is None else value},
        observed_at_ns=time,
        provenance=provenance,
        confidence=0.8,
    )
