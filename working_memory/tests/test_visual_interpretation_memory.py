from __future__ import annotations

import unittest

from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    WorkingMemory,
    WorkingMemoryConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    ObservationClock,
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
    VisualProducerKind,
    VisualModelCapability,
    VisualModelFormat,
    VisualModelProvenance,
    VisualModelSourceClassification,
    VisualSemanticCategory,
)

from helpers import TEST_PROVENANCE, catalog


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.test.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.test.adapter.v1",
    "ayyo.visual-interpretation.v1",
)
MODEL = VisualModelProvenance(
    model_id=PRODUCER.model_id,
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
REFERENCE = VisualEvaluationReference(
    producer_version="1.0.0",
    producer_implementation_sha256="3" * 64,
    producer_manifest_sha256="4" * 64,
    model=MODEL,
    dataset_id="ayyo.dataset.visual.fixture.v1",
    dataset_version="1.0.0",
    dataset_manifest_sha256="5" * 64,
    policy_id="ayyo.visual-evaluation.fixture.v1",
    policy_version="1.0.0",
    policy_sha256="6" * 64,
    report_semantic_sha256="7" * 64,
    result_schema_version="1.0.0",
    decision=VisualEvaluationDecision.MEETS_MECHANICAL_POLICY,
)
REQUIREMENT = VisualEvaluationRequirement(
    producer_id=PRODUCER.producer_id,
    producer_version=REFERENCE.producer_version,
    producer_implementation_sha256=(
        REFERENCE.producer_implementation_sha256
    ),
    producer_manifest_sha256=REFERENCE.producer_manifest_sha256,
    model_provenance_sha256=MODEL.provenance_sha256,
    model_artifact_sha256=MODEL.artifact_sha256,
    dataset_id=REFERENCE.dataset_id,
    dataset_version=REFERENCE.dataset_version,
    dataset_manifest_sha256=REFERENCE.dataset_manifest_sha256,
    policy_id=REFERENCE.policy_id,
    policy_version=REFERENCE.policy_version,
    policy_sha256=REFERENCE.policy_sha256,
    report_semantic_sha256=REFERENCE.report_semantic_sha256,
    result_schema_version=REFERENCE.result_schema_version,
)


def frame(time_ns: int) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA,
        width=32,
        height=24,
        encoding="rgb8",
        step=96,
        data_size_bytes=2304,
        is_bigendian=False,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
        observed_at_ns=time_ns,
        provenance=TEST_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def interpretation(
    source: VisualFrameObservation,
    *,
    evaluated: bool = False,
) -> VisualInterpretationObservation:
    return VisualInterpretationObservation(
        robot_id=source.robot_id,
        sensor=source.sensor,
        reference_frame_id=source.sensor.frame_id,
        source_visual_observation_id=source.observation_id,
        source_visual_fingerprint=source.fingerprint,
        observed_at_ns=source.observed_at_ns,
        result_at_ns=source.observed_at_ns,
        producer=PRODUCER,
        detections=(
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.TEST_PATTERN,
                label="test.marker.v1",
                region=ImageRegion2D(
                    x_min=0.25,
                    y_min=0.25,
                    x_max=0.75,
                    y_max=0.75,
                ),
                confidence=None,
            ),
        ),
        provenance=source.provenance,
        availability=SensorAvailability.AVAILABLE,
        evaluation_reference=REFERENCE if evaluated else None,
    )


def memory(*, recent: int = 8, evaluated: bool = False) -> WorkingMemory:
    return WorkingMemory(
        catalog(),
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            allowed_provenance=(TEST_PROVENANCE,),
            sensors=(CAMERA,),
            freshness_ns=50,
            retention_ttl_ns=2000,
            permitted_future_skew_ns=5,
            recent_evidence_capacity=recent,
            visual_interpretation_producers=(PRODUCER,),
            visual_evaluation_requirements=(REQUIREMENT,) if evaluated else (),
        ),
    )


class VisualInterpretationMemoryTest(unittest.TestCase):
    def test_evaluated_producer_requires_exact_compact_reference(self) -> None:
        store = memory(evaluated=True)
        source = frame(100)
        self.assertEqual(
            IngestionStatus.ACCEPTED,
            store.ingest(source, now_ns=100, received_at_monotonic_ns=1).status,
        )
        missing = store.ingest(
            interpretation(source),
            now_ns=100,
            received_at_monotonic_ns=2,
        )
        self.assertEqual(IngestionReason.EVALUATION_REQUIRED, missing.reason)
        accepted = store.ingest(
            interpretation(source, evaluated=True),
            now_ns=100,
            received_at_monotonic_ns=3,
        )
        self.assertEqual(IngestionStatus.ACCEPTED, accepted.status)

    def test_retain_project_query_without_mutation_and_duplicate_growth(self) -> None:
        store = memory()
        source = frame(100)
        result = interpretation(source)
        self.assertEqual(
            IngestionStatus.REJECTED,
            store.ingest(result, now_ns=101, received_at_monotonic_ns=1).status,
        )
        self.assertEqual(
            IngestionStatus.ACCEPTED,
            store.ingest(source, now_ns=101, received_at_monotonic_ns=2).status,
        )
        self.assertEqual(
            IngestionStatus.ACCEPTED,
            store.ingest(result, now_ns=101, received_at_monotonic_ns=3).status,
        )
        before = store.stats(now_ns=101)
        duplicate = store.ingest(result, now_ns=101, received_at_monotonic_ns=4)
        self.assertEqual(IngestionReason.DUPLICATE_OBSERVATION, duplicate.reason)
        first = store.current_snapshot(now_ns=101)
        second = store.current_snapshot(now_ns=101)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(1, len(first.robot.visual_interpretation_states))
        after = store.stats(now_ns=101)
        self.assertEqual(before.recent_evidence_count, after.recent_evidence_count)
        self.assertEqual(1, after.current_visual_interpretation_count)

    def test_high_rate_replacement_retains_one_current_result_and_bounded_recent(self) -> None:
        store = memory(recent=8)
        receipt = 0
        for index in range(1, 1001):
            source = frame(index)
            receipt += 1
            self.assertEqual(
                IngestionStatus.ACCEPTED,
                store.ingest(source, now_ns=index, received_at_monotonic_ns=receipt).status,
            )
            receipt += 1
            result = interpretation(source)
            self.assertEqual(
                IngestionStatus.ACCEPTED,
                store.ingest(result, now_ns=index, received_at_monotonic_ns=receipt).status,
            )
        stats = store.stats(now_ns=1000)
        self.assertEqual(1, stats.current_visual_count)
        self.assertEqual(1, stats.current_visual_interpretation_count)
        self.assertEqual(8, stats.recent_evidence_count)
        self.assertLessEqual(stats.retained_unique_observation_count, 10)
        state = store.get_robot_state(now_ns=1000)
        self.assertEqual(
            frame(1000).observation_id,
            state.visual_interpretation_states[0]
            .observation.source_visual_observation_id,
        )


if __name__ == "__main__":
    unittest.main()
