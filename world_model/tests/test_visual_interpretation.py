from __future__ import annotations

import math
import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    MAX_VISUAL_DETECTIONS,
    ObservationClock,
    ObservationIdentityError,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualEvaluationDecision,
    VisualEvaluationReference,
    VisualEvaluationRequirement,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualModelCapability,
    VisualModelFormat,
    VisualModelProvenance,
    VisualModelSourceClassification,
    VisualProducerKind,
    VisualSemanticCategory,
    WorldModelProjector,
    WorldModelValidationError,
    rebuild_observation,
    rebuild_snapshot,
)

from helpers import catalog


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.camera.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-frame.v1",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.test.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.test.adapter.v1",
    "ayyo.visual-interpretation.v1",
)
MODEL = VisualModelProvenance(
    model_id="none",
    model_version="1.0.0",
    producer_id=PRODUCER.producer_id,
    artifact_sha256="1" * 64,
    model_format=VisualModelFormat.DETERMINISTIC_FIXTURE,
    capability=VisualModelCapability.BOUNDED_DETECTION,
    configuration_sha256="2" * 64,
    label_schema_id="ayyo.visual-labels.fixture.v1",
    label_schema_version="1.0.0",
    source_classification=VisualModelSourceClassification.TEST_FIXTURE,
)


def evaluation_reference(**overrides) -> VisualEvaluationReference:
    values = {
        "producer_version": "1.0.0",
        "producer_implementation_sha256": "3" * 64,
        "producer_manifest_sha256": "4" * 64,
        "model": MODEL,
        "dataset_id": "ayyo.dataset.visual.fixture.v1",
        "dataset_version": "1.0.0",
        "dataset_manifest_sha256": "5" * 64,
        "policy_id": "ayyo.visual-evaluation.fixture.v1",
        "policy_version": "1.0.0",
        "policy_sha256": "6" * 64,
        "report_semantic_sha256": "7" * 64,
        "result_schema_version": "1.0.0",
        "decision": VisualEvaluationDecision.MEETS_MECHANICAL_POLICY,
    }
    values.update(overrides)
    return VisualEvaluationReference(**values)


def frame(*, observed_at_ns: int = 100) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA,
        width=320,
        height=240,
        encoding='rgb8',
        step=960,
        data_size_bytes=230_400,
        is_bigendian=False,
        calibration_id='camera-calibration-sha256-' + '1' * 64,
        observed_at_ns=observed_at_ns,
        provenance=PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def detection(source: VisualFrameObservation, *, label: str = "test.marker.v1", **region):
    return VisualDetection(
        source_visual_observation_id=source.observation_id,
        category=VisualSemanticCategory.TEST_PATTERN,
        label=label,
        region=ImageRegion2D(
            x_min=region.get("x_min", 0.1),
            y_min=region.get("y_min", 0.2),
            x_max=region.get("x_max", 0.8),
            y_max=region.get("y_max", 0.9),
        ),
        confidence=region.get("confidence"),
    )


def interpretation(source: VisualFrameObservation, **overrides):
    values = {
        "robot_id": source.robot_id,
        "sensor": source.sensor,
        "reference_frame_id": source.sensor.frame_id,
        "source_visual_observation_id": source.observation_id,
        "source_visual_fingerprint": source.fingerprint,
        "observed_at_ns": source.observed_at_ns,
        "result_at_ns": source.observed_at_ns + 10,
        "producer": PRODUCER,
        "detections": (detection(source),),
        "provenance": source.provenance,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualInterpretationObservation(**values)


class VisualInterpretationContractTest(unittest.TestCase):
    def test_model_and_evaluation_provenance_are_canonical_and_exact(self) -> None:
        rebuilt_model = VisualModelProvenance(
            model_id=MODEL.model_id,
            model_version=MODEL.model_version,
            producer_id=MODEL.producer_id,
            artifact_sha256=MODEL.artifact_sha256,
            model_format=MODEL.model_format,
            capability=MODEL.capability,
            configuration_sha256=MODEL.configuration_sha256,
            label_schema_id=MODEL.label_schema_id,
            label_schema_version=MODEL.label_schema_version,
            source_classification=MODEL.source_classification,
            provenance_sha256=MODEL.provenance_sha256,
        )
        self.assertEqual(MODEL, rebuilt_model)
        with self.assertRaises(ObservationIdentityError):
            VisualModelProvenance(
                model_id=MODEL.model_id,
                model_version=MODEL.model_version,
                producer_id=MODEL.producer_id,
                artifact_sha256=MODEL.artifact_sha256,
                model_format=MODEL.model_format,
                capability=MODEL.capability,
                configuration_sha256=MODEL.configuration_sha256,
                label_schema_id=MODEL.label_schema_id,
                label_schema_version=MODEL.label_schema_version,
                source_classification=MODEL.source_classification,
                provenance_sha256="0" * 64,
            )
        with self.assertRaises(WorldModelValidationError):
            evaluation_reference(
                decision=VisualEvaluationDecision.DOES_NOT_MEET_MECHANICAL_POLICY
            )

    def test_evaluation_reference_changes_semantic_identity_and_matches_requirement(self) -> None:
        source = frame()
        plain = interpretation(source)
        evaluated = interpretation(
            source,
            evaluation_reference=evaluation_reference(),
        )
        self.assertNotEqual(plain.observation_id, evaluated.observation_id)
        self.assertEqual(evaluated, rebuild_observation(evaluated))
        requirement = VisualEvaluationRequirement(
            producer_id=PRODUCER.producer_id,
            producer_version='1.0.0',
            producer_implementation_sha256='3' * 64,
            producer_manifest_sha256="4" * 64,
            model_provenance_sha256=MODEL.provenance_sha256,
            model_artifact_sha256=MODEL.artifact_sha256,
            dataset_id="ayyo.dataset.visual.fixture.v1",
            dataset_version="1.0.0",
            dataset_manifest_sha256='5' * 64,
            policy_id="ayyo.visual-evaluation.fixture.v1",
            policy_version="1.0.0",
            policy_sha256="6" * 64,
            report_semantic_sha256='7' * 64,
            result_schema_version="1.0.0",
        )
        self.assertTrue(requirement.matches(PRODUCER, evaluated.evaluation_reference))
        self.assertFalse(
            requirement.matches(
                PRODUCER,
                evaluation_reference(dataset_id="ayyo.dataset.other.v1"),
            )
        )
        for changed_reference in (
            evaluation_reference(producer_version='1.0.1'),
            evaluation_reference(producer_implementation_sha256='8' * 64),
            evaluation_reference(dataset_manifest_sha256='9' * 64),
            evaluation_reference(report_semantic_sha256='a' * 64),
        ):
            self.assertFalse(requirement.matches(PRODUCER, changed_reference))

    def test_identity_is_canonical_across_order_and_negative_zero(self) -> None:
        source = frame()
        first = detection(source, label="test.a", x_min=-0.0)
        equivalent = detection(source, label="test.a", x_min=0.0)
        second = detection(source, label="test.b", x_min=0.2)
        self.assertEqual(first.detection_id, equivalent.detection_id)
        one = interpretation(source, detections=(first, second))
        two = interpretation(source, detections=(second, equivalent))
        self.assertEqual(one.observation_id, two.observation_id)
        self.assertEqual(one, rebuild_observation(one))

    def test_numeric_geometry_confidence_and_collection_bounds_fail_closed(self) -> None:
        source = frame()
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(WorldModelValidationError):
                ImageRegion2D(x_min=value, y_min=0.0, x_max=1.0, y_max=1.0)
        for bounds in (
            (-0.1, 0.0, 1.0, 1.0),
            (0.5, 0.0, 0.5, 1.0),
            (0.0, 0.8, 1.0, 0.2),
            (0.0, 0.0, 1.1, 1.0),
        ):
            with self.subTest(bounds=bounds), self.assertRaises(WorldModelValidationError):
                ImageRegion2D(
                    x_min=bounds[0],
                    y_min=bounds[1],
                    x_max=bounds[2],
                    y_max=bounds[3],
                )
        for confidence in (-0.01, 1.01, math.nan, math.inf):
            with self.subTest(confidence=confidence), self.assertRaises(
                WorldModelValidationError
            ):
                detection(source, confidence=confidence)
        oversized = tuple(
            detection(source, label=f"test.marker.{index}")
            for index in range(MAX_VISUAL_DETECTIONS + 1)
        )
        with self.assertRaises(WorldModelValidationError):
            interpretation(source, detections=oversized)
        with self.assertRaises(WorldModelValidationError):
            detection(source, label="x" * 65)

    def test_source_and_result_time_relationship_is_explicit(self) -> None:
        source = frame(observed_at_ns=100)
        with self.assertRaises(WorldModelValidationError):
            interpretation(source, result_at_ns=99)
        other = frame(observed_at_ns=101)
        with self.assertRaises(WorldModelValidationError):
            interpretation(
                source,
                detections=(detection(other),),
            )

    def test_projection_is_immutable_pixel_free_and_semantically_identified(self) -> None:
        source = frame()
        result = interpretation(source)
        projector = WorldModelProjector(catalog(), (CAMERA,))
        without = projector.project(
            now_ns=110,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            visual_evidence={CAMERA.sensor_id: source},
        )
        with_result = projector.project(
            now_ns=110,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            visual_evidence={CAMERA.sensor_id: source},
            visual_interpretation_evidence={
                (CAMERA.sensor_id, PRODUCER.producer_id): result
            },
        )
        self.assertNotEqual(without.snapshot_id, with_result.snapshot_id)
        self.assertEqual(with_result, rebuild_snapshot(with_result))
        self.assertEqual(
            result.observation_id,
            with_result.robot.visual_interpretation_states[0].observation.observation_id,
        )
        document = with_result.robot.document()
        self.assertNotIn("pixels", repr(document).lower())
        self.assertNotIn("image_data", repr(document).lower())


if __name__ == "__main__":
    unittest.main()
