from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    BodyPoseObservation,
    CovarianceMatrix,
    ImuObservation,
    ObservationFingerprint,
    ObservationFingerprintKind,
    ObservationIdentityError,
    Pose3D,
    SensorAvailability,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
    WorldModelFailureCode,
    WorldModelValidationError,
    rebuild_observation,
)

from helpers import TEST_PROVENANCE


IMU_SENSOR = SensorIdentity("ayyo.imu.body.v1", SensorKind.IMU, "imu_link")
POSE_SENSOR = SensorIdentity(
    "ayyo.body-pose.localization.v1",
    SensorKind.BODY_POSE,
    "base_link",
)


class ProprioceptionContractTest(unittest.TestCase):
    def imu(self, **overrides) -> ImuObservation:
        values = {
            "robot_id": AYYO_ROBOT_ID,
            "sensor": IMU_SENSOR,
            "orientation_xyzw": (0.0, 0.0, 0.0, 1.0),
            "angular_velocity_xyz": (0.1, 0.2, 0.3),
            "linear_acceleration_xyz": (0.0, 0.0, 9.81),
            "observed_at_ns": 100,
            "provenance": TEST_PROVENANCE,
            "availability": SensorAvailability.AVAILABLE,
        }
        values.update(overrides)
        return ImuObservation(**values)

    def test_imu_identity_is_deterministic_and_quaternion_sign_canonical(self) -> None:
        positive = self.imu(orientation_xyzw=(0.0, 0.0, 0.0, 1.0))
        negative = self.imu(orientation_xyzw=(0.0, 0.0, 0.0, -1.0))
        near_unit = self.imu(orientation_xyzw=(0.0, 0.0, 0.0, 1.0000005))
        self.assertEqual(positive, negative)
        self.assertEqual(positive, near_unit)
        self.assertEqual(positive.observation_id, negative.observation_id)

    def test_imu_preserves_unavailable_estimates_and_unknown_covariance(self) -> None:
        observation = self.imu(
            orientation_xyzw=None,
            angular_velocity_xyz=(0.1, 0.2, 0.3),
            linear_acceleration_xyz=None,
            orientation_covariance=None,
            angular_velocity_covariance=None,
            linear_acceleration_covariance=None,
            quality=None,
        )
        self.assertIsNone(observation.orientation_xyzw)
        self.assertIsNone(observation.linear_acceleration_xyz)
        self.assertIsNone(observation.angular_velocity_covariance)
        self.assertIsNone(observation.quality)

    def test_imu_requires_actual_measurement_evidence(self) -> None:
        with self.assertRaises(WorldModelValidationError):
            self.imu(
                orientation_xyzw=None,
                angular_velocity_xyz=None,
                linear_acceleration_xyz=None,
            )

    def test_imu_rejects_nonfinite_bool_and_malformed_vectors(self) -> None:
        invalid = (True, float("nan"), float("inf"), -float("inf"))
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorldModelValidationError):
                self.imu(angular_velocity_xyz=(value, 0.0, 0.0))
        for vector in ((0.0, 0.0), [0.0, 0.0, 0.0], (0.0, 0.0, 0.0, 0.0)):
            with self.subTest(vector=vector), self.assertRaises(WorldModelValidationError):
                self.imu(angular_velocity_xyz=vector)

    def test_imu_rejects_zero_and_grossly_invalid_quaternions(self) -> None:
        for value in (
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 2.0),
            (float("nan"), 0.0, 0.0, 1.0),
        ):
            with self.subTest(value=value), self.assertRaises(WorldModelValidationError):
                self.imu(orientation_xyzw=value)

    def test_covariance_requires_finite_symmetric_nonnegative_structure(self) -> None:
        valid = CovarianceMatrix(3, (0.1, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.3))
        self.assertEqual(3, valid.dimension)
        invalid = (
            (3, (0.0,) * 8),
            (4, (0.0,) * 16),
            (3, (-0.1, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1)),
            (3, (0.1, 1.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1)),
            (3, (1.0, 2.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0, 1.0)),
            (3, (float("inf"),) + (0.0,) * 8),
            (3, (True,) + (0.0,) * 8),
        )
        for dimension, values in invalid:
            with self.subTest(dimension=dimension), self.assertRaises(
                WorldModelValidationError
            ) as context:
                CovarianceMatrix(dimension, values)
            self.assertEqual(WorldModelFailureCode.MALFORMED_COVARIANCE, context.exception.code)

    def test_covariance_cannot_exist_for_an_unavailable_estimate(self) -> None:
        covariance = CovarianceMatrix(3, (0.0,) * 9)
        with self.assertRaises(WorldModelValidationError) as context:
            self.imu(orientation_xyzw=None, orientation_covariance=covariance)
        self.assertEqual(WorldModelFailureCode.MALFORMED_COVARIANCE, context.exception.code)

    def test_measurement_status_cannot_claim_error_stale_or_unavailable(self) -> None:
        for status in (
            SensorAvailability.ERROR,
            SensorAvailability.STALE,
            SensorAvailability.UNAVAILABLE,
        ):
            with self.subTest(status=status), self.assertRaises(WorldModelValidationError):
                self.imu(availability=status)

    def test_sensor_and_observation_are_immutable(self) -> None:
        observation = self.imu()
        with self.assertRaises(FrozenInstanceError):
            observation.quality = 0.1
        with self.assertRaises(FrozenInstanceError):
            observation.sensor.frame_id = "changed"

    def test_rebuild_rejects_imu_fingerprint_and_provenance_substitution(self) -> None:
        observation = self.imu()
        object.__setattr__(
            observation,
            "fingerprint",
            ObservationFingerprint(ObservationFingerprintKind.IMU, "0" * 64),
        )
        with self.assertRaises(ObservationIdentityError):
            rebuild_observation(observation)

    def test_pose_contract_requires_exact_body_target_and_optional_6x6_covariance(self) -> None:
        covariance = CovarianceMatrix(6, (0.0,) * 36)
        observation = BodyPoseObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=POSE_SENSOR,
            pose=Pose3D("map", "base_link", (1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
            covariance=covariance,
            observed_at_ns=100,
            provenance=TEST_PROVENANCE,
            availability=SensorAvailability.DEGRADED,
            quality=None,
        )
        self.assertEqual("map", observation.pose.frame_id)
        with self.assertRaises(WorldModelValidationError):
            BodyPoseObservation(
                robot_id=AYYO_ROBOT_ID,
                sensor=POSE_SENSOR,
                pose=Pose3D("map", "pelvis_link", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
                observed_at_ns=100,
                provenance=TEST_PROVENANCE,
                availability=SensorAvailability.AVAILABLE,
            )
        with self.assertRaises(WorldModelValidationError):
            BodyPoseObservation(
                robot_id=AYYO_ROBOT_ID,
                sensor=POSE_SENSOR,
                pose=observation.pose,
                covariance=CovarianceMatrix(3, (0.0,) * 9),
                observed_at_ns=100,
                provenance=TEST_PROVENANCE,
                availability=SensorAvailability.AVAILABLE,
            )

    def test_missing_pose_is_not_represented_as_identity_transform(self) -> None:
        with self.assertRaises(TypeError):
            BodyPoseObservation(
                robot_id=AYYO_ROBOT_ID,
                sensor=POSE_SENSOR,
                observed_at_ns=100,
                provenance=TEST_PROVENANCE,
                availability=SensorAvailability.UNAVAILABLE,
            )

    def test_health_evidence_is_bounded_and_never_changes_sensor_identity(self) -> None:
        health = SensorHealthObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=IMU_SENSOR,
            availability=SensorAvailability.ERROR,
            observed_at_ns=100,
            provenance=TEST_PROVENANCE,
            evidence_detail="driver reported calibration error",
        )
        self.assertEqual(SensorAvailability.ERROR, health.availability)
        self.assertEqual(IMU_SENSOR, health.sensor)
        with self.assertRaises(WorldModelValidationError):
            SensorHealthObservation(
                robot_id=AYYO_ROBOT_ID,
                sensor=IMU_SENSOR,
                availability=SensorAvailability.ERROR,
                observed_at_ns=100,
                provenance=TEST_PROVENANCE,
                evidence_detail="x" * 1_025,
            )


if __name__ == "__main__":
    unittest.main()
