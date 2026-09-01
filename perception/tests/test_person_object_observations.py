from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError, fields

from ayyo_perception import (
    ObjectObservation,
    PerceptionObservationValidationError,
    PersonObservation,
    SemanticObservationKind,
)

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    MAX_OBSERVATION_TIME_NS,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorIdentity,
    SensorKind,
    WorldModelValidationError,
)


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.camera.person-object.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.person-object-observation.v1",
)
SOURCE_VISUAL_OBSERVATION_ID = "world-observation-" + "1" * 64
REGION = ImageRegion2D(x_min=0.1, y_min=0.2, x_max=0.7, y_max=0.9)


def person(**overrides) -> PersonObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": CAMERA,
        "reference_frame_id": CAMERA.frame_id,
        "source_visual_observation_id": SOURCE_VISUAL_OBSERVATION_ID,
        "observed_at_ns": 100,
        "result_at_ns": 110,
        "confidence": 0.75,
        "region": REGION,
        "provenance": PROVENANCE,
    }
    values.update(overrides)
    return PersonObservation(**values)


def object_observation(**overrides) -> ObjectObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": CAMERA,
        "reference_frame_id": CAMERA.frame_id,
        "source_visual_observation_id": SOURCE_VISUAL_OBSERVATION_ID,
        "observed_at_ns": 100,
        "result_at_ns": 110,
        "category": "cup",
        "confidence": 0.625,
        "region": REGION,
        "provenance": PROVENANCE,
    }
    values.update(overrides)
    return ObjectObservation(**values)


class PersonObjectObservationContractTest(unittest.TestCase):
    def test_valid_person_observation_is_compact_and_exact(self) -> None:
        observation = person()
        self.assertIs(SemanticObservationKind.PERSON, observation.kind)
        self.assertEqual(AYYO_ROBOT_ID, observation.robot_id)
        self.assertEqual(CAMERA, observation.sensor)
        self.assertEqual(CAMERA.frame_id, observation.reference_frame_id)
        self.assertEqual(PROVENANCE, observation.provenance)
        self.assertEqual(
            SOURCE_VISUAL_OBSERVATION_ID,
            observation.source_visual_observation_id,
        )
        self.assertTrue(
            observation.observation_id.startswith(
                "person-observation-sha256-"
            )
        )
        self.assertEqual("person", observation.document()["kind"])

    def test_valid_object_observation_has_one_bounded_category(self) -> None:
        observation = object_observation()
        self.assertIs(SemanticObservationKind.OBJECT, observation.kind)
        self.assertEqual("cup", observation.category)
        self.assertEqual("cup", observation.document()["category"])
        self.assertTrue(
            observation.observation_id.startswith(
                "object-observation-sha256-"
            )
        )

    def test_observations_are_immutable_and_slot_bounded(self) -> None:
        observation = person()
        with self.assertRaises(FrozenInstanceError):
            observation.confidence = 0.2  # type: ignore[misc]
        self.assertFalse(hasattr(observation, "__dict__"))

    def test_equal_content_has_equal_identity_and_representation(self) -> None:
        first = person()
        second = person(observation_id=first.observation_id)
        self.assertEqual(first, second)
        self.assertEqual(first.observation_id, second.observation_id)
        self.assertEqual(first.document(), second.document())
        self.assertNotEqual(
            first.observation_id,
            person(confidence=0.76).observation_id,
        )

    def test_supplied_identity_must_match_content(self) -> None:
        with self.assertRaisesRegex(
            PerceptionObservationValidationError,
            "identity does not match",
        ):
            object_observation(
                observation_id="object-observation-sha256-" + "0" * 64
            )

    def test_identity_source_and_frame_fail_closed(self) -> None:
        imu = SensorIdentity(
            "ayyo.imu.body.v1",
            SensorKind.IMU,
            "body_imu_frame",
        )
        invalid = (
            {"robot_id": "Ayyo Robot"},
            {"sensor": imu, "reference_frame_id": imu.frame_id},
            {"reference_frame_id": "another_optical_frame"},
            {"source_visual_observation_id": "visual-frame-1"},
            {"provenance": "test.camera.person-object.v1"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(PerceptionObservationValidationError):
                    person(**overrides)

    def test_timestamps_fail_closed(self) -> None:
        invalid = (
            {"observed_at_ns": -1},
            {"observed_at_ns": True},
            {"observed_at_ns": 101, "result_at_ns": 100},
            {"result_at_ns": MAX_OBSERVATION_TIME_NS + 1},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(
                    PerceptionObservationValidationError,
                    "timestamps",
                ):
                    object_observation(**overrides)

    def test_confidence_includes_exact_bounds(self) -> None:
        self.assertEqual(0.0, person(confidence=0).confidence)
        self.assertEqual(1.0, person(confidence=1).confidence)

    def test_invalid_confidence_fails_closed(self) -> None:
        invalid = (
            -0.01,
            1.01,
            math.nan,
            math.inf,
            -math.inf,
            True,
            "0.5",
            None,
        )
        for confidence in invalid:
            with self.subTest(confidence=confidence):
                with self.assertRaises(PerceptionObservationValidationError):
                    person(confidence=confidence)

    def test_region_must_be_typed_and_strictly_normalized(self) -> None:
        with self.assertRaisesRegex(
            PerceptionObservationValidationError,
            "region",
        ):
            person(region=(0.1, 0.2, 0.7, 0.9))
        invalid_regions = (
            (-0.1, 0.2, 0.7, 0.9),
            (0.1, 0.2, 1.1, 0.9),
            (0.5, 0.2, 0.5, 0.9),
            (0.1, math.nan, 0.7, 0.9),
        )
        for x_min, y_min, x_max, y_max in invalid_regions:
            values = {
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max,
            }
            with self.subTest(values=values):
                with self.assertRaises(WorldModelValidationError):
                    ImageRegion2D(**values)

    def test_object_category_cannot_substitute_person(self) -> None:
        for category in ("", "Cup", " person", "person", "a" * 65):
            with self.subTest(category=category):
                with self.assertRaises(PerceptionObservationValidationError):
                    object_observation(category=category)

    def test_contracts_have_no_payload_or_authority_fields(self) -> None:
        forbidden = {
            "actuator",
            "command",
            "data",
            "demographics",
            "emotion",
            "face_identity",
            "image",
            "image_buffer",
            "manipulation",
            "motor",
            "movement",
            "name",
            "navigation",
            "person_id",
            "pixels",
            "raw_image",
            "safety",
            "skill",
        }
        for observation_type, observation in (
            (PersonObservation, person()),
            (ObjectObservation, object_observation()),
        ):
            with self.subTest(observation_type=observation_type.__name__):
                field_names = {item.name for item in fields(observation_type)}
                self.assertFalse(field_names & forbidden)
                self.assertFalse(set(observation.document()) & forbidden)


if __name__ == "__main__":
    unittest.main()
