from __future__ import annotations

from ayyo_perception import (
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImuObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
)


JOINT_SENSOR = SensorIdentity(
    "ayyo.joint-state.body.v1",
    SensorKind.JOINT_STATE,
    "base_link",
)
IMU_SENSOR = SensorIdentity("ayyo.imu.body.v1", SensorKind.IMU, "imu_link")
POSE_SENSOR = SensorIdentity(
    "ayyo.body-pose.localization.v1",
    SensorKind.BODY_POSE,
    "base_link",
)
JOINT_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.joint-state.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.joint-state.v1",
)
IMU_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.imu.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.imu.v1",
)
POSE_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.pose.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.body-pose.v1",
)


def config(*, freshness=50, ttl=100, future=5) -> PerceptionTrustConfig:
    return PerceptionTrustConfig(
        robot_id=AYYO_ROBOT_ID,
        source_clock=ObservationClock.TEST_TIME,
        sources=(
            PerceptionSourceContract(JOINT_SENSOR, JOINT_PROVENANCE),
            PerceptionSourceContract(IMU_SENSOR, IMU_PROVENANCE),
            PerceptionSourceContract(POSE_SENSOR, POSE_PROVENANCE, "odom"),
        ),
        freshness_ns=freshness,
        retention_ttl_ns=ttl,
        permitted_future_skew_ns=future,
    )


def boundary(**overrides) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(config(**overrides))


def imu(*, time=100, angular=(0.1, 0.2, 0.3), **overrides) -> ImuObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": IMU_SENSOR,
        "angular_velocity_xyz": angular,
        "observed_at_ns": time,
        "provenance": IMU_PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return ImuObservation(**values)
