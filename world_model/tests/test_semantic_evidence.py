from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from hashlib import sha256
import json
import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    FreshnessState,
    ImageRegion2D,
    ObservationClock,
    ObservationFingerprint,
    ObservationFingerprintKind,
    ObservationIdentityError,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SemanticEvidenceItem,
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
    "test.semantic-world-state.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.semantic-world-state.v1",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.semantic-world-state.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.semantic-world-state.adapter.v1",
    "ayyo.visual-interpretation.v1",
)
PERSON_REGION = ImageRegion2D(
    x_min=0.05,
    y_min=0.1,
    x_max=0.45,
    y_max=0.9,
)
OBJECT_REGION = ImageRegion2D(
    x_min=0.55,
    y_min=0.4,
    x_max=0.85,
    y_max=0.8,
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


def interpretation(
    source: VisualFrameObservation,
    *,
    object_category: str = "cup",
    object_confidence: float | None = None,
    object_region: ImageRegion2D = OBJECT_REGION,
) -> VisualInterpretationObservation:
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
                region=PERSON_REGION,
                confidence=0.75,
            ),
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.OBJECT,
                label=object_category,
                region=object_region,
                confidence=object_confidence,
            ),
        ),
        provenance=source.provenance,
        availability=source.availability,
    )


def source_semantic_id(
    result: VisualInterpretationObservation,
    detection: VisualDetection,
) -> str:
    kind = (
        SemanticEvidenceKind.PERSON
        if detection.category is VisualSemanticCategory.PERSON
        else SemanticEvidenceKind.OBJECT
    )
    document = {
        "confidence": detection.confidence,
        "kind": kind.value,
        "observed_at_ns": result.observed_at_ns,
        "provenance": result.provenance.document(),
        "reference_frame_id": result.reference_frame_id,
        "region": detection.region.document(),
        "result_at_ns": result.result_at_ns,
        "robot_id": result.robot_id,
        "schema": f"ayyo.{kind.value}-observation.v1",
        "sensor": result.sensor.document(),
        "source_detection": {
            "visual_detection_id": detection.detection_id,
            "visual_interpretation_observation_id": result.observation_id,
        },
        "source_visual_observation_id": result.source_visual_observation_id,
    }
    if kind is SemanticEvidenceKind.OBJECT:
        document["category"] = detection.label
    encoded = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return f"{kind.value}-observation-sha256-{sha256(encoded).hexdigest()}"


def evidence_items(
    result: VisualInterpretationObservation,
) -> tuple[SemanticEvidenceItem, ...]:
    items = []
    for detection in result.detections:
        kind = (
            SemanticEvidenceKind.PERSON
            if detection.category is VisualSemanticCategory.PERSON
            else SemanticEvidenceKind.OBJECT
        )
        items.append(
            SemanticEvidenceItem(
                kind=kind,
                source_semantic_observation_id=source_semantic_id(
                    result,
                    detection,
                ),
                source_detection_id=detection.detection_id,
                region=detection.region,
                confidence=detection.confidence,
                category=(
                    detection.label
                    if kind is SemanticEvidenceKind.OBJECT
                    else None
                ),
            )
        )
    return tuple(items)


def semantic_evidence(
    *,
    time_ns: int = 100,
    object_category: str = "cup",
    object_confidence: float | None = None,
    object_region: ImageRegion2D = OBJECT_REGION,
    reverse: bool = False,
) -> SemanticEvidenceObservation:
    source = frame(time_ns)
    result = interpretation(
        source,
        object_category=object_category,
        object_confidence=object_confidence,
        object_region=object_region,
    )
    items = evidence_items(result)
    if reverse:
        items = tuple(reversed(items))
    return SemanticEvidenceObservation(
        robot_id=result.robot_id,
        sensor=result.sensor,
        reference_frame_id=result.reference_frame_id,
        source_visual_observation_id=result.source_visual_observation_id,
        source_visual_fingerprint=result.source_visual_fingerprint,
        source_interpretation_observation_id=result.observation_id,
        source_interpretation_fingerprint=result.fingerprint,
        observed_at_ns=result.observed_at_ns,
        result_at_ns=result.result_at_ns,
        producer=result.producer,
        evaluation_reference_sha256=None,
        items=items,
        provenance=result.provenance,
        availability=result.availability,
    )


class SemanticEvidenceContractTest(unittest.TestCase):
    def test_person_object_projection_preserves_exact_anonymous_sources(self) -> None:
        observation = semantic_evidence()
        self.assertEqual(2, len(observation.items))
        self.assertEqual(
            {SemanticEvidenceKind.PERSON, SemanticEvidenceKind.OBJECT},
            {item.kind for item in observation.items},
        )
        self.assertEqual(CAMERA, observation.sensor)
        self.assertEqual(PRODUCER, observation.producer)
        self.assertEqual(PROVENANCE, observation.provenance)
        self.assertEqual(observation, rebuild_observation(observation))
        self.assertTrue(observation.observation_id.startswith("world-observation-"))
        self.assertTrue(
            all(
                item.source_semantic_observation_id.startswith(
                    f"{item.kind.value}-observation-sha256-"
                )
                for item in observation.items
            )
        )

    def test_order_is_canonical_and_equal_content_has_equal_identity(self) -> None:
        left = semantic_evidence()
        right = semantic_evidence(reverse=True)
        self.assertEqual(left, right)
        self.assertEqual(left.observation_id, right.observation_id)
        self.assertEqual(left.payload_document(), right.payload_document())

    def test_region_category_and_optional_confidence_change_identity(self) -> None:
        baseline = semantic_evidence()
        changed_region = semantic_evidence(
            object_region=ImageRegion2D(
                x_min=0.5,
                y_min=0.4,
                x_max=0.9,
                y_max=0.8,
            )
        )
        changed_category = semantic_evidence(object_category="bottle")
        zero_confidence = semantic_evidence(object_confidence=0.0)
        valued_confidence = semantic_evidence(object_confidence=0.5)
        identities = {
            item.observation_id
            for item in (
                baseline,
                changed_region,
                changed_category,
                zero_confidence,
                valued_confidence,
            )
        }
        self.assertEqual(5, len(identities))
        object_item = next(
            item
            for item in baseline.items
            if item.kind is SemanticEvidenceKind.OBJECT
        )
        self.assertIsNone(object_item.confidence)
        self.assertNotEqual(baseline.observation_id, zero_confidence.observation_id)

    def test_malformed_and_tampered_source_references_fail_closed(self) -> None:
        baseline = semantic_evidence()
        item = baseline.items[0]
        with self.assertRaises(WorldModelValidationError):
            SemanticEvidenceItem(
                kind=item.kind,
                source_semantic_observation_id="semantic-1",
                source_detection_id=item.source_detection_id,
                region=item.region,
                confidence=item.confidence,
                category=item.category,
            )
        forged = SemanticEvidenceItem(
            kind=item.kind,
            source_semantic_observation_id=(
                f"{item.kind.value}-observation-sha256-" + "0" * 64
            ),
            source_detection_id=item.source_detection_id,
            region=item.region,
            confidence=item.confidence,
            category=item.category,
        )
        with self.assertRaises(ObservationIdentityError):
            SemanticEvidenceObservation(
                robot_id=baseline.robot_id,
                sensor=baseline.sensor,
                reference_frame_id=baseline.reference_frame_id,
                source_visual_observation_id=(
                    baseline.source_visual_observation_id
                ),
                source_visual_fingerprint=baseline.source_visual_fingerprint,
                source_interpretation_observation_id=(
                    baseline.source_interpretation_observation_id
                ),
                source_interpretation_fingerprint=(
                    baseline.source_interpretation_fingerprint
                ),
                observed_at_ns=baseline.observed_at_ns,
                result_at_ns=baseline.result_at_ns,
                producer=baseline.producer,
                evaluation_reference_sha256=None,
                items=(forged,),
                provenance=baseline.provenance,
                availability=baseline.availability,
            )
        object.__setattr__(baseline, "fingerprint", ObservationFingerprint(
            ObservationFingerprintKind.SEMANTIC_EVIDENCE,
            "0" * 64,
        ))
        with self.assertRaises(ObservationIdentityError):
            rebuild_observation(baseline)

    def test_person_and_object_semantics_cannot_substitute_each_other(self) -> None:
        with self.assertRaises(WorldModelValidationError):
            SemanticEvidenceItem(
                kind=SemanticEvidenceKind.PERSON,
                source_semantic_observation_id=(
                    "person-observation-sha256-" + "1" * 64
                ),
                source_detection_id="visual-detection-sha256-" + "2" * 64,
                region=PERSON_REGION,
                confidence=0.5,
                category="cup",
            )
        with self.assertRaises(WorldModelValidationError):
            SemanticEvidenceItem(
                kind=SemanticEvidenceKind.OBJECT,
                source_semantic_observation_id=(
                    "object-observation-sha256-" + "1" * 64
                ),
                source_detection_id="visual-detection-sha256-" + "2" * 64,
                region=OBJECT_REGION,
                confidence=0.5,
                category="person",
            )

    def test_contract_is_immutable_pixel_free_and_has_no_entity_or_authority(self) -> None:
        observation = semantic_evidence()
        with self.assertRaises(FrozenInstanceError):
            observation.items = ()  # type: ignore[misc]
        forbidden = {
            "actuator",
            "command",
            "data",
            "entity_id",
            "image",
            "motion",
            "navigation",
            "person_id",
            "pixels",
            "raw_image",
            "safety",
            "skill",
            "track_id",
        }
        self.assertFalse({item.name for item in fields(type(observation))} & forbidden)
        self.assertFalse({item.name for item in fields(SemanticEvidenceItem)} & forbidden)
        self.assertFalse(set(observation.payload_document()) & forbidden)

    def test_snapshot_projection_is_freshness_aware_stable_and_not_an_entity(self) -> None:
        observation = semantic_evidence()
        projector = WorldModelProjector(catalog(), (CAMERA,))
        first = projector.project(
            now_ns=110,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            semantic_evidence={observation.observation_id: observation},
        )
        repeat = projector.project(
            now_ns=120,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            semantic_evidence={observation.observation_id: observation},
        )
        stale = projector.project(
            now_ns=151,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            semantic_evidence={observation.observation_id: observation},
        )
        self.assertEqual(first.snapshot_id, repeat.snapshot_id)
        self.assertEqual(FreshnessState.FRESH, first.semantic_states[0].freshness)
        self.assertEqual(FreshnessState.STALE, stale.semantic_states[0].freshness)
        self.assertNotEqual(first.snapshot_id, stale.snapshot_id)
        self.assertEqual((), first.entities)
        self.assertEqual(first, rebuild_snapshot(first))

    def test_snapshot_order_is_independent_of_mapping_insertion_order(self) -> None:
        first = semantic_evidence(time_ns=100)
        second = semantic_evidence(time_ns=102, object_category="bottle")
        projector = WorldModelProjector(catalog(), (CAMERA,))
        left = projector.project(
            now_ns=102,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            semantic_evidence={
                second.observation_id: second,
                first.observation_id: first,
            },
        )
        right = projector.project(
            now_ns=102,
            fresh_for_ns=50,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            semantic_evidence={
                first.observation_id: first,
                second.observation_id: second,
            },
        )
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
