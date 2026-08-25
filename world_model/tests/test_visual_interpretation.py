from __future__ import annotations

import math
import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    MAX_VISUAL_DETECTIONS,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
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


def frame(*, observed_at_ns: int = 100) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA,
        width=320,
        height=240,
        encoding="rgb8",
        step=960,
        data_size_bytes=230_400,
        is_bigendian=False,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
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
