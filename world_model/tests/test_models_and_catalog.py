from __future__ import annotations

from dataclasses import replace
import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    EnvironmentEntityObservation,
    JointObservation,
    ObservationClock,
    ObservationFingerprint,
    ObservationFingerprintKind,
    ObservationIdentityError,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    Pose3D,
    RobotJointCatalog,
    RobotStateObservation,
    WorldEntityIdentity,
    WorldEntityKind,
    WorldModelFailureCode,
    WorldModelValidationError,
    rebuild_observation,
)

from helpers import TEST_PROVENANCE, catalog, urdf


class ModelsAndCatalogTest(unittest.TestCase):
    def robot_observation(self, **overrides):
        values = {
            "robot_id": AYYO_ROBOT_ID,
            "joints": (JointObservation("neck_yaw_joint", 0.25, 0.1, 0.2),),
            "observed_at_ns": 1_000,
            "provenance": TEST_PROVENANCE,
            "confidence": 0.9,
        }
        values.update(overrides)
        return RobotStateObservation(**values)

    def test_robot_observation_is_canonical_and_deterministic(self) -> None:
        left = self.robot_observation(
            joints=(
                JointObservation("neck_yaw_joint", 0.25),
                JointObservation("head_pitch_joint", 0.1),
            )
        )
        right = self.robot_observation(
            joints=tuple(reversed(left.joints)),
        )
        self.assertEqual(left, right)
        self.assertEqual(left.observation_id, right.observation_id)
        self.assertTrue(left.observation_id.startswith("world-observation-"))

    def test_observation_identity_changes_with_state_or_provenance(self) -> None:
        baseline = self.robot_observation()
        changed_state = self.robot_observation(
            joints=(JointObservation("neck_yaw_joint", 0.3, 0.1, 0.2),)
        )
        changed_source = self.robot_observation(
            provenance=ObservationProvenance(
                ObservationSourceKind.TEST_FIXTURE,
                "test.world-model.other.v1",
                ObservationClock.TEST_TIME,
                ObservationTransport.DIRECT,
                "direct.robot-state.v1",
            )
        )
        self.assertNotEqual(baseline.observation_id, changed_state.observation_id)
        self.assertNotEqual(baseline.observation_id, changed_source.observation_id)

    def test_rebuild_detects_observation_and_fingerprint_substitution(self) -> None:
        observation = self.robot_observation()
        object.__setattr__(observation, "observation_id", "world-observation-" + "0" * 64)
        with self.assertRaises(ObservationIdentityError):
            rebuild_observation(observation)

        intact = self.robot_observation()
        object.__setattr__(
            intact,
            "fingerprint",
            ObservationFingerprint(ObservationFingerprintKind.ROBOT_STATE, "0" * 64),
        )
        with self.assertRaises(ObservationIdentityError):
            rebuild_observation(intact)

    def test_malformed_joint_numbers_are_rejected(self) -> None:
        for value in (True, float("nan"), float("inf"), -float("inf"), "0.1"):
            with self.subTest(value=value), self.assertRaises(WorldModelValidationError):
                JointObservation("neck_yaw_joint", value)

    def test_duplicate_and_oversized_joint_collections_are_rejected(self) -> None:
        with self.assertRaises(WorldModelValidationError):
            self.robot_observation(
                joints=(
                    JointObservation("neck_yaw_joint", 0.1),
                    JointObservation("neck_yaw_joint", 0.2),
                )
            )
        with self.assertRaises(WorldModelValidationError):
            self.robot_observation(
                joints=tuple(
                    JointObservation(f"joint_{index}", 0.0) for index in range(129)
                )
            )

    def test_provenance_source_and_clock_must_match(self) -> None:
        with self.assertRaises(WorldModelValidationError) as context:
            ObservationProvenance(
                ObservationSourceKind.SIMULATION,
                "ros.joint-states.simulation.v1",
                ObservationClock.ROS_SYSTEM_TIME,
                ObservationTransport.ROS2,
                "sensor-msgs.joint-state.v1",
            )
        self.assertEqual(WorldModelFailureCode.MALFORMED_PROVENANCE, context.exception.code)

    def test_pose_requires_distinct_frames_and_normalized_quaternion(self) -> None:
        valid = Pose3D("odom", "base_link", (1, 2, 3), (0, 0, 0, 1))
        self.assertEqual((1.0, 2.0, 3.0), valid.position_xyz)
        with self.assertRaises(WorldModelValidationError):
            Pose3D("base_link", "base_link", (0, 0, 0), (0, 0, 0, 1))
        with self.assertRaises(WorldModelValidationError):
            Pose3D("odom", "base_link", (0, 0, 0), (0, 0, 0, 2))

    def test_environment_properties_are_defensively_copied(self) -> None:
        properties = {"classification": {"labels": ["cup"]}}
        observation = EnvironmentEntityObservation(
            robot_id=AYYO_ROBOT_ID,
            entity=WorldEntityIdentity("object.cup.1", WorldEntityKind.OBJECT),
            properties=properties,
            observed_at_ns=1,
            provenance=TEST_PROVENANCE,
            confidence=0.8,
        )
        properties["classification"]["labels"].append("changed")
        returned = observation.properties
        returned["classification"]["labels"].append("also-changed")
        self.assertEqual(["cup"], observation.properties["classification"]["labels"])

    def test_environment_observation_requires_actual_evidence(self) -> None:
        with self.assertRaises(WorldModelValidationError):
            EnvironmentEntityObservation(
                robot_id=AYYO_ROBOT_ID,
                entity=WorldEntityIdentity("unknown.1", WorldEntityKind.UNKNOWN),
                properties={},
                observed_at_ns=1,
                provenance=TEST_PROVENANCE,
                confidence=0.5,
            )

    def test_json_bounds_reject_nan_infinity_boolean_cycle_and_oversize(self) -> None:
        base = {
            "robot_id": AYYO_ROBOT_ID,
            "entity": WorldEntityIdentity("object.1", WorldEntityKind.OBJECT),
            "observed_at_ns": 1,
            "provenance": TEST_PROVENANCE,
            "confidence": 0.5,
        }
        invalid_values = ({"x": float("nan")}, {"x": float("inf")}, {"x": "x" * 4097})
        for properties in invalid_values:
            with self.subTest(properties=properties), self.assertRaises(WorldModelValidationError):
                EnvironmentEntityObservation(properties=properties, **base)
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(WorldModelValidationError):
            EnvironmentEntityObservation(properties={"cycle": cycle}, **base)
        with self.assertRaises(WorldModelValidationError):
            EnvironmentEntityObservation(properties={"items": list(range(257))}, **base)
        deep = value = {}
        for index in range(18):
            child = {}
            value[str(index)] = child
            value = child
        with self.assertRaises(WorldModelValidationError):
            EnvironmentEntityObservation(properties=deep, **base)

    def test_catalog_parses_authoritative_urdf_deterministically(self) -> None:
        left = RobotJointCatalog.from_urdf(
            robot_id=AYYO_ROBOT_ID,
            robot_description=urdf(),
        )
        right = RobotJointCatalog.from_urdf(
            robot_id=AYYO_ROBOT_ID,
            robot_description=urdf(),
        )
        self.assertEqual(left.fingerprint, right.fingerprint)
        self.assertEqual(("neck_yaw_joint",), left.observable_joint_names)
        neck = left.contract_for("neck_yaw_joint")
        self.assertEqual((-1.2, 1.2, 1.5, 8.0), (
            neck.lower, neck.upper, neck.velocity_limit, neck.effort_limit
        ))

    def test_catalog_rejects_wrong_robot_unknown_fixed_and_invalid_values(self) -> None:
        cases = (
            (
                self.robot_observation(robot_id="other.robot.v1"),
                WorldModelFailureCode.WRONG_ROBOT_IDENTITY,
            ),
            (
                self.robot_observation(joints=(JointObservation("unknown_joint", 0.0),)),
                WorldModelFailureCode.UNKNOWN_JOINT,
            ),
            (
                self.robot_observation(joints=(JointObservation("fixed_sensor_joint", 0.0),)),
                WorldModelFailureCode.FIXED_JOINT,
            ),
            (
                self.robot_observation(joints=(JointObservation("neck_yaw_joint", 1.3),)),
                WorldModelFailureCode.JOINT_ABOVE_MAXIMUM,
            ),
            (
                self.robot_observation(joints=(JointObservation("neck_yaw_joint", 0, 1.6),)),
                WorldModelFailureCode.JOINT_VELOCITY_EXCEEDED,
            ),
            (
                self.robot_observation(joints=(JointObservation("neck_yaw_joint", 0, 0, 8.1),)),
                WorldModelFailureCode.JOINT_EFFORT_EXCEEDED,
            ),
        )
        for observation, code in cases:
            with self.subTest(code=code), self.assertRaises(WorldModelValidationError) as context:
                catalog().validate_observation(observation)
            self.assertEqual(code, context.exception.code)

    def test_catalog_accepts_only_bounded_numerical_feedback_tolerance(self) -> None:
        catalog().validate_observation(
            self.robot_observation(
                joints=(JointObservation("neck_yaw_joint", -1.2 - 1e-9),)
            )
        )
        with self.assertRaises(WorldModelValidationError) as context:
            catalog().validate_observation(
                self.robot_observation(
                    joints=(JointObservation("neck_yaw_joint", -1.2 - 1e-6),)
                )
            )
        self.assertEqual(WorldModelFailureCode.JOINT_BELOW_MINIMUM, context.exception.code)


if __name__ == "__main__":
    unittest.main()
