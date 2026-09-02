from __future__ import annotations

from dataclasses import fields
import unittest

from ayyo_perception import (
    AdmissionStatus,
    PerceptionObservationValidationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
    semantic_observation_from_detection,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SemanticEvidenceKind,
    SemanticEvidenceObservation,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualProducerKind,
    VisualSemanticCategory,
)


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.semantic-projection.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.semantic-projection.v1",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.semantic-projection.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.semantic-projection.adapter.v1",
    "ayyo.visual-interpretation.v1",
)


def frame(time_ns: int = 100) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA,
        width=32,
        height=24,
        encoding="rgb8",
        step=96,
        data_size_bytes=2_304,
        is_bigendian=False,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
        observed_at_ns=time_ns,
        provenance=PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def interpretation(source: VisualFrameObservation) -> VisualInterpretationObservation:
    return VisualInterpretationObservation(
        robot_id=source.robot_id,
        sensor=source.sensor,
        reference_frame_id=source.sensor.frame_id,
        source_visual_observation_id=source.observation_id,
        source_visual_fingerprint=source.fingerprint,
        observed_at_ns=source.observed_at_ns,
        result_at_ns=source.observed_at_ns + 1,
        producer=PRODUCER,
        detections=(
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.PERSON,
                label="person",
                region=ImageRegion2D(
                    x_min=0.05,
                    y_min=0.1,
                    x_max=0.45,
                    y_max=0.9,
                ),
                confidence=0.75,
            ),
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.OBJECT,
                label="cup",
                region=ImageRegion2D(
                    x_min=0.55,
                    y_min=0.4,
                    x_max=0.85,
                    y_max=0.8,
                ),
                confidence=None,
            ),
        ),
        provenance=source.provenance,
        availability=source.availability,
    )


def boundary() -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(PerceptionSourceContract(CAMERA, PROVENANCE),),
            freshness_ns=50,
            retention_ttl_ns=100,
            permitted_future_skew_ns=5,
            visual_interpretation_producers=(PRODUCER,),
        )
    )


def admit(trust, observation, now: int, receipt: int):
    return trust.admit(
        observation,
        now_ns=now,
        received_at_monotonic_ns=receipt,
    )


def admitted_chain(
    trust: PerceptionTrustBoundary,
    *,
    time_ns: int = 100,
    receipt: int = 1,
):
    source = frame(time_ns)
    result = interpretation(source)
    self_results = (
        admit(trust, source, time_ns, receipt),
        admit(trust, result, time_ns + 1, receipt + 1),
    )
    assert all(item.status is AdmissionStatus.ACCEPTED for item in self_results)
    semantics = tuple(
        semantic_observation_from_detection(
            result,
            detection_id=detection.detection_id,
        )
        for detection in result.detections
    )
    for index, semantic in enumerate(semantics, start=receipt + 2):
        assert admit(trust, semantic, time_ns + 1, index).status is AdmissionStatus.ACCEPTED
    return source, result, semantics


class SemanticWorldProjectionSeamTest(unittest.TestCase):
    def test_retained_person_and_object_admissions_project_exactly(self) -> None:
        trust = boundary()
        source, result, semantics = admitted_chain(trust)
        projected = trust.project_semantic_evidence(
            tuple(item.observation_id for item in reversed(semantics))
        )
        self.assertIsInstance(projected, SemanticEvidenceObservation)
        self.assertEqual(source.observation_id, projected.source_visual_observation_id)
        self.assertEqual(
            result.observation_id,
            projected.source_interpretation_observation_id,
        )
        self.assertEqual(result.fingerprint, projected.source_interpretation_fingerprint)
        self.assertEqual(PRODUCER, projected.producer)
        self.assertIsNone(projected.evaluation_reference_sha256)
        self.assertEqual(
            {SemanticEvidenceKind.PERSON, SemanticEvidenceKind.OBJECT},
            {item.kind for item in projected.items},
        )
        object_item = next(
            item
            for item in projected.items
            if item.kind is SemanticEvidenceKind.OBJECT
        )
        self.assertEqual("cup", object_item.category)
        self.assertIsNone(object_item.confidence)

    def test_projection_is_deterministic_across_input_order(self) -> None:
        trust = boundary()
        _, _, semantics = admitted_chain(trust)
        ids = tuple(item.observation_id for item in semantics)
        self.assertEqual(
            trust.project_semantic_evidence(ids),
            trust.project_semantic_evidence(tuple(reversed(ids))),
        )

    def test_unadmitted_semantics_cannot_use_projection_as_a_trust_bypass(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(source)
        semantic = semantic_observation_from_detection(
            result,
            detection_id=result.detections[0].detection_id,
        )
        with self.assertRaisesRegex(
            PerceptionObservationValidationError,
            "not retained",
        ):
            trust.project_semantic_evidence((semantic.observation_id,))

    def test_admissions_from_different_interpretations_cannot_be_mixed(self) -> None:
        trust = boundary()
        _, _, first = admitted_chain(trust, time_ns=100, receipt=1)
        _, _, second = admitted_chain(trust, time_ns=102, receipt=10)
        with self.assertRaisesRegex(
            PerceptionObservationValidationError,
            "one admitted interpretation",
        ):
            trust.project_semantic_evidence(
                (first[0].observation_id, second[0].observation_id)
            )

    def test_expiry_and_reset_remove_the_projection_capability(self) -> None:
        trust = boundary()
        _, _, semantics = admitted_chain(trust)
        old_ids = tuple(item.observation_id for item in semantics)
        admit(trust, frame(201), 201, 20)
        with self.assertRaises(PerceptionObservationValidationError):
            trust.project_semantic_evidence(old_ids)

        trust.reset()
        with self.assertRaises(PerceptionObservationValidationError):
            trust.project_semantic_evidence(old_ids)

    def test_projection_retains_no_pixels_identity_or_authority(self) -> None:
        trust = boundary()
        _, _, semantics = admitted_chain(trust)
        projected = trust.project_semantic_evidence(
            tuple(item.observation_id for item in semantics)
        )
        forbidden = {
            "actuator",
            "command",
            "entity_id",
            "image",
            "person_id",
            "pixels",
            "raw_image",
            "safety",
            "skill",
            "track_id",
        }
        self.assertFalse({item.name for item in fields(type(projected))} & forbidden)
        self.assertFalse(set(projected.payload_document()) & forbidden)


if __name__ == "__main__":
    unittest.main()
