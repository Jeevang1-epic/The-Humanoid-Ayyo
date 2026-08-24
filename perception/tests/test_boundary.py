from __future__ import annotations

import unittest

from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    EvidenceFailureKind,
    PerceptionClockRegressionError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    BodyPoseObservation,
    ImuObservation,
    JointObservation,
    ObservationClock,
    ObservationFingerprint,
    ObservationFingerprintKind,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    Pose3D,
    RobotStateObservation,
    SensorAvailability,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
)

from helpers import (
    IMU_PROVENANCE,
    IMU_SENSOR,
    JOINT_PROVENANCE,
    POSE_PROVENANCE,
    POSE_SENSOR,
    boundary,
    config,
    imu,
)


class PerceptionTrustBoundaryTest(unittest.TestCase):
    def admit(self, trust, observation, *, now=100, receipt=1):
        return trust.admit(
            observation,
            now_ns=now,
            received_at_monotonic_ns=receipt,
        )

    def test_valid_imu_is_reconstructed_and_admitted(self) -> None:
        trust = boundary()
        observation = imu()
        result = self.admit(trust, observation)
        self.assertEqual(AdmissionStatus.ACCEPTED, result.status)
        self.assertEqual(observation, result.observation)
        self.assertEqual(observation.observation_id, result.observation_id)
        self.assertEqual((1, 1), (trust.stats().accepted_count, trust.stats().tracked_source_key_count))

    def test_exact_duplicate_is_a_noop(self) -> None:
        trust = boundary()
        observation = imu()
        self.admit(trust, observation, receipt=1)
        result = self.admit(trust, observation, receipt=2)
        self.assertEqual(AdmissionStatus.DUPLICATE, result.status)
        self.assertEqual(AdmissionReason.DUPLICATE, result.reason)
        self.assertEqual((1, 1), (trust.stats().accepted_count, trust.stats().duplicate_count))

    def test_out_of_order_and_same_time_conflict_are_rejected(self) -> None:
        trust = boundary()
        self.admit(trust, imu(time=100))
        conflict = self.admit(trust, imu(time=100, angular=(0.4, 0.5, 0.6)), receipt=2)
        older = self.admit(trust, imu(time=99), receipt=3)
        self.assertEqual(AdmissionReason.TEMPORAL_CONFLICT, conflict.reason)
        self.assertEqual(AdmissionReason.OUT_OF_ORDER, older.reason)

    def test_future_stale_and_receipt_regression_are_explicit(self) -> None:
        trust = boundary()
        future = self.admit(trust, imu(time=106), now=100, receipt=10)
        stale = self.admit(trust, imu(time=0), now=101, receipt=11)
        regressed = self.admit(trust, imu(time=100), now=101, receipt=9)
        self.assertEqual(AdmissionReason.FUTURE_OBSERVATION, future.reason)
        self.assertEqual(AdmissionReason.STALE_OBSERVATION, stale.reason)
        self.assertEqual(AdmissionReason.RECEIPT_TIME_REGRESSION, regressed.reason)

    def test_source_clock_regression_requires_explicit_reset(self) -> None:
        trust = boundary()
        self.admit(trust, imu(time=100), now=100)
        with self.assertRaises(PerceptionClockRegressionError):
            self.admit(trust, imu(time=10), now=10, receipt=2)
        trust.reset()
        self.assertEqual(AdmissionStatus.ACCEPTED, self.admit(trust, imu(time=10), now=10).status)

    def test_wrong_robot_and_unknown_sensor_are_rejected(self) -> None:
        trust = boundary()
        wrong_robot = self.admit(trust, imu(robot_id="other.robot.v1"))
        unknown_sensor = SensorIdentity("ayyo.imu.unknown.v1", SensorKind.IMU, "imu_link")
        unknown = self.admit(trust, imu(sensor=unknown_sensor), receipt=2)
        self.assertEqual(AdmissionReason.WRONG_ROBOT_IDENTITY, wrong_robot.reason)
        self.assertEqual(AdmissionReason.UNKNOWN_SENSOR, unknown.reason)

    def test_provenance_substitution_cannot_relabel_simulation_as_physical(self) -> None:
        simulation = ObservationProvenance(
            ObservationSourceKind.SIMULATION,
            "ros.imu.simulation.v1",
            ObservationClock.ROS_SIMULATION_TIME,
            ObservationTransport.ROS2,
            "sensor-msgs.imu.v1",
        )
        physical = ObservationProvenance(
            ObservationSourceKind.PHYSICAL_SENSOR,
            "ros.imu.physical.v1",
            ObservationClock.ROS_SYSTEM_TIME,
            ObservationTransport.ROS2,
            "sensor-msgs.imu.v1",
        )
        trust = PerceptionTrustBoundary(
            PerceptionTrustConfig(
                robot_id=AYYO_ROBOT_ID,
                source_clock=ObservationClock.ROS_SIMULATION_TIME,
                sources=(PerceptionSourceContract(IMU_SENSOR, simulation),),
            )
        )
        observation = ImuObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=IMU_SENSOR,
            angular_velocity_xyz=(0.0, 0.0, 0.0),
            observed_at_ns=100,
            provenance=physical,
            availability=SensorAvailability.AVAILABLE,
        )
        result = self.admit(trust, observation)
        self.assertEqual(AdmissionReason.CLOCK_DOMAIN_MISMATCH, result.reason)
        self.assertNotEqual(
            imu(provenance=simulation).observation_id,
            observation.observation_id,
        )

    def test_pose_frames_are_exact_and_failure_never_fabricates_identity_pose(self) -> None:
        trust = boundary()
        valid = BodyPoseObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=POSE_SENSOR,
            pose=Pose3D("map", "base_link", (1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
            observed_at_ns=100,
            provenance=POSE_PROVENANCE,
            availability=SensorAvailability.AVAILABLE,
        )
        self.assertEqual(AdmissionStatus.ACCEPTED, self.admit(trust, valid).status)

        wrong_source = BodyPoseObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=POSE_SENSOR,
            pose=Pose3D("odom", "base_link", (1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
            observed_at_ns=101,
            provenance=POSE_PROVENANCE,
            availability=SensorAvailability.AVAILABLE,
        )
        self.assertEqual(
            AdmissionReason.FRAME_MISMATCH,
            self.admit(trust, wrong_source, now=101, receipt=2).reason,
        )

        trust.reset()
        unavailable = trust.report_failure(
            sensor_id=POSE_SENSOR.sensor_id,
            failure=EvidenceFailureKind.FRAME_LOOKUP_UNAVAILABLE,
            observed_at_ns=100,
            now_ns=100,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(AdmissionReason.FRAME_LOOKUP_UNAVAILABLE, unavailable.reason)
        self.assertIsInstance(unavailable.observation, SensorHealthObservation)
        self.assertEqual(SensorAvailability.UNAVAILABLE, unavailable.observation.availability)
        self.assertNotIsInstance(unavailable.observation, BodyPoseObservation)

    def test_frame_extrapolation_is_error_health_not_latest_or_identity_pose(self) -> None:
        result = boundary().report_failure(
            sensor_id=POSE_SENSOR.sensor_id,
            failure=EvidenceFailureKind.FRAME_LOOKUP_EXTRAPOLATION,
            observed_at_ns=100,
            now_ns=100,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(AdmissionReason.FRAME_LOOKUP_EXTRAPOLATION, result.reason)
        self.assertEqual(SensorAvailability.ERROR, result.observation.availability)

    def test_joint_state_uses_the_same_trust_boundary(self) -> None:
        observation = RobotStateObservation(
            robot_id=AYYO_ROBOT_ID,
            joints=(JointObservation("neck_yaw_joint", 0.1),),
            observed_at_ns=100,
            provenance=JOINT_PROVENANCE,
            confidence=1.0,
        )
        result = self.admit(boundary(), observation)
        self.assertEqual(AdmissionStatus.ACCEPTED, result.status)

    def test_health_and_measurement_have_separate_bounded_ordering_keys(self) -> None:
        trust = boundary()
        self.admit(trust, imu(time=100))
        health = SensorHealthObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=IMU_SENSOR,
            availability=SensorAvailability.DEGRADED,
            observed_at_ns=100,
            provenance=IMU_PROVENANCE,
            evidence_detail="calibration pending",
        )
        result = self.admit(trust, health, receipt=2)
        self.assertEqual(AdmissionStatus.ACCEPTED, result.status)
        self.assertEqual(2, trust.stats().tracked_source_key_count)

    def test_fingerprint_tampering_is_rejected_before_admission(self) -> None:
        observation = imu()
        object.__setattr__(
            observation,
            "fingerprint",
            ObservationFingerprint(ObservationFingerprintKind.IMU, "0" * 64),
        )
        result = self.admit(boundary(), observation)
        self.assertEqual(AdmissionReason.IDENTITY_MISMATCH, result.reason)
        self.assertIsNone(result.observation)

    def test_reset_discards_ordering_identity_and_counters(self) -> None:
        trust = boundary()
        self.admit(trust, imu())
        trust.reset()
        self.assertEqual((0, 0, 0), (
            trust.stats().accepted_count,
            trust.stats().tracked_source_key_count,
            trust.stats().rejected_count,
        ))
        self.assertEqual(AdmissionStatus.ACCEPTED, self.admit(trust, imu()).status)


if __name__ == "__main__":
    unittest.main()
