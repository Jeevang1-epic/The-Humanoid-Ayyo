from __future__ import annotations

import unittest
from dataclasses import fields

from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    MAX_SEMANTIC_ADMISSIONS,
    ObjectObservation,
    PerceptionObservationValidationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
    PersonObservation,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    WorldModelValidationError,
)


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.camera.semantic-admission.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-frame.v1",
)
OTHER_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.camera.unreviewed.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-frame.v1",
)
REGION = ImageRegion2D(x_min=0.1, y_min=0.2, x_max=0.7, y_max=0.9)


def frame(time_ns: int = 100, **overrides) -> VisualFrameObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": CAMERA,
        "width": 32,
        "height": 24,
        "encoding": "rgb8",
        "step": 96,
        "data_size_bytes": 2_304,
        "is_bigendian": False,
        "calibration_id": "camera-calibration-sha256-" + "1" * 64,
        "observed_at_ns": time_ns,
        "provenance": PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def person(source: VisualFrameObservation, **overrides) -> PersonObservation:
    values = {
        "robot_id": source.robot_id,
        "sensor": source.sensor,
        "reference_frame_id": source.sensor.frame_id,
        "source_visual_observation_id": source.observation_id,
        "observed_at_ns": source.observed_at_ns,
        "result_at_ns": source.observed_at_ns + 1,
        "confidence": 0.75,
        "region": REGION,
        "provenance": source.provenance,
    }
    values.update(overrides)
    return PersonObservation(**values)


def object_observation(
    source: VisualFrameObservation,
    **overrides,
) -> ObjectObservation:
    values = {
        "robot_id": source.robot_id,
        "sensor": source.sensor,
        "reference_frame_id": source.sensor.frame_id,
        "source_visual_observation_id": source.observation_id,
        "observed_at_ns": source.observed_at_ns,
        "result_at_ns": source.observed_at_ns + 1,
        "category": "cup",
        "confidence": 0.625,
        "region": REGION,
        "provenance": source.provenance,
    }
    values.update(overrides)
    return ObjectObservation(**values)


def boundary(*, freshness_ns: int = 50, retention_ttl_ns: int = 100):
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(PerceptionSourceContract(CAMERA, PROVENANCE),),
            freshness_ns=freshness_ns,
            retention_ttl_ns=retention_ttl_ns,
            permitted_future_skew_ns=5,
        )
    )


def admit(trust, observation, *, now: int, receipt: int):
    return trust.admit(
        observation,
        now_ns=now,
        received_at_monotonic_ns=receipt,
    )


class SemanticAdmissionBoundaryTest(unittest.TestCase):
    def test_legitimate_person_and_object_evidence_are_admitted(self) -> None:
        trust = boundary()
        source = frame()
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, source, now=100, receipt=1).status,
        )
        admitted_person = admit(
            trust,
            person(source),
            now=101,
            receipt=2,
        )
        admitted_object = admit(
            trust,
            object_observation(source),
            now=101,
            receipt=3,
        )
        self.assertIs(AdmissionStatus.ACCEPTED, admitted_person.status)
        self.assertIsInstance(admitted_person.observation, PersonObservation)
        self.assertIs(AdmissionStatus.ACCEPTED, admitted_object.status)
        self.assertIsInstance(admitted_object.observation, ObjectObservation)
        self.assertIs(
            ObservationSourceKind.TEST_FIXTURE,
            admitted_person.observation.provenance.source_kind,
        )
        self.assertEqual(2, trust.stats().tracked_semantic_admission_count)

    def test_unadmitted_source_visual_frame_is_rejected(self) -> None:
        source = frame()
        result = admit(boundary(), person(source), now=101, receipt=1)
        self.assertIs(AdmissionStatus.REJECTED, result.status)
        self.assertIs(AdmissionReason.SOURCE_FRAME_NOT_ADMITTED, result.reason)

    def test_wrong_robot_identity_is_rejected(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        result = admit(
            trust,
            person(source, robot_id="other.robot.v1"),
            now=101,
            receipt=2,
        )
        self.assertIs(AdmissionReason.WRONG_ROBOT_IDENTITY, result.reason)

    def test_wrong_sensor_and_unreviewed_provenance_are_rejected(self) -> None:
        source = frame()
        other_camera = SensorIdentity(
            "ayyo.camera.other.rgb.v1",
            SensorKind.RGB_CAMERA,
            CAMERA.frame_id,
        )
        cases = (
            (
                person(
                    source,
                    sensor=other_camera,
                    reference_frame_id=other_camera.frame_id,
                ),
                AdmissionReason.UNKNOWN_SENSOR,
            ),
            (
                person(source, provenance=OTHER_PROVENANCE),
                AdmissionReason.PROVENANCE_NOT_ALLOWED,
            ),
        )
        for observation, reason in cases:
            with self.subTest(reason=reason):
                trust = boundary()
                admit(trust, source, now=100, receipt=1)
                self.assertIs(
                    reason,
                    admit(trust, observation, now=101, receipt=2).reason,
                )

    def test_wrong_camera_reference_frame_is_rejected(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        wrong_frame_camera = SensorIdentity(
            CAMERA.sensor_id,
            SensorKind.RGB_CAMERA,
            "head_camera_frame",
        )
        observation = person(
            source,
            sensor=wrong_frame_camera,
            reference_frame_id=wrong_frame_camera.frame_id,
        )
        self.assertIs(
            AdmissionReason.FRAME_MISMATCH,
            admit(trust, observation, now=101, receipt=2).reason,
        )

    def test_source_visual_identity_must_match_its_exact_frame(self) -> None:
        trust = boundary()
        first = frame(100)
        second = frame(101)
        admit(trust, first, now=100, receipt=1)
        admit(trust, second, now=101, receipt=2)
        mismatched = person(
            first,
            source_visual_observation_id=second.observation_id,
            result_at_ns=102,
        )
        self.assertIs(
            AdmissionReason.SOURCE_FRAME_MISMATCH,
            admit(trust, mismatched, now=102, receipt=3).reason,
        )

    def test_reversed_time_tampering_fails_closed(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        observation = person(source)
        object.__setattr__(observation, "result_at_ns", 99)
        result = admit(trust, observation, now=101, receipt=2)
        self.assertIs(AdmissionReason.MALFORMED_OBSERVATION, result.reason)
        self.assertIsNone(result.observation)

    def test_future_semantic_result_time_is_rejected(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        observation = person(source, result_at_ns=107)
        self.assertIs(
            AdmissionReason.RESULT_TIME_INVALID,
            admit(trust, observation, now=101, receipt=2).reason,
        )

    def test_stale_or_unavailable_source_evidence_is_rejected(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        self.assertIs(
            AdmissionReason.STALE_OBSERVATION,
            admit(trust, person(source), now=151, receipt=2).reason,
        )

        with self.assertRaises(WorldModelValidationError):
            frame(availability=SensorAvailability.UNAVAILABLE)

    def test_duplicate_and_replay_behavior_is_deterministic(self) -> None:
        trust = boundary()
        source = frame()
        observation = person(source)
        admit(trust, source, now=100, receipt=1)
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, observation, now=101, receipt=2).status,
        )
        replay = admit(trust, observation, now=101, receipt=3)
        self.assertIs(AdmissionStatus.DUPLICATE, replay.status)
        self.assertIs(AdmissionReason.DUPLICATE, replay.reason)
        self.assertIsNone(replay.observation)
        self.assertEqual(1, trust.stats().tracked_semantic_admission_count)

    def test_content_and_identity_tampering_is_rejected(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        observation = object_observation(source)
        object.__setattr__(observation, "confidence", 0.9)
        result = admit(trust, observation, now=101, receipt=2)
        self.assertIs(AdmissionStatus.REJECTED, result.status)
        self.assertIs(AdmissionReason.IDENTITY_MISMATCH, result.reason)
        self.assertIsNone(result.observation)

    def test_object_category_cannot_represent_a_person(self) -> None:
        with self.assertRaises(PerceptionObservationValidationError):
            object_observation(frame(), category="person")

    def test_expiry_and_reset_remove_semantic_admission_state(self) -> None:
        trust = boundary()
        first = frame(100)
        admit(trust, first, now=100, receipt=1)
        admit(trust, person(first), now=101, receipt=2)
        self.assertEqual(1, trust.stats().tracked_semantic_admission_count)

        current = frame(201)
        admit(trust, current, now=201, receipt=3)
        self.assertEqual(0, trust.stats().tracked_semantic_admission_count)

        trust.reset()
        self.assertEqual(0, trust.stats().tracked_semantic_admission_count)
        self.assertIs(
            AdmissionReason.SOURCE_FRAME_NOT_ADMITTED,
            admit(trust, person(current), now=202, receipt=1).reason,
        )

    def test_admission_retains_no_pixels_and_grants_no_authority(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        accepted = admit(trust, person(source), now=101, receipt=2)
        observation = accepted.observation
        self.assertIsInstance(observation, PersonObservation)
        forbidden = {
            "actuator",
            "command",
            "data",
            "executive",
            "image",
            "image_buffer",
            "memory",
            "motor",
            "movement",
            "permission",
            "pixels",
            "raw_image",
            "safety",
            "skill",
        }
        self.assertFalse(
            {item.name for item in fields(PersonObservation)} & forbidden
        )
        self.assertFalse(set(observation.document()) & forbidden)

    def test_semantic_admission_capacity_is_hard_bounded(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        admitted = []
        for index in range(MAX_SEMANTIC_ADMISSIONS):
            observation = object_observation(
                source,
                category=f"object-{index:03d}",
            )
            admitted.append(observation)
            self.assertIs(
                AdmissionStatus.ACCEPTED,
                admit(
                    trust,
                    observation,
                    now=101,
                    receipt=index + 2,
                ).status,
            )
        self.assertEqual(
            MAX_SEMANTIC_ADMISSIONS,
            trust.stats().tracked_semantic_admission_count,
        )
        overflow = object_observation(source, category="overflow")
        self.assertIs(
            AdmissionReason.SEMANTIC_CAPACITY_REACHED,
            admit(
                trust,
                overflow,
                now=101,
                receipt=MAX_SEMANTIC_ADMISSIONS + 2,
            ).reason,
        )
        self.assertIs(
            AdmissionReason.DUPLICATE,
            admit(
                trust,
                admitted[0],
                now=101,
                receipt=MAX_SEMANTIC_ADMISSIONS + 3,
            ).reason,
        )


if __name__ == "__main__":
    unittest.main()
