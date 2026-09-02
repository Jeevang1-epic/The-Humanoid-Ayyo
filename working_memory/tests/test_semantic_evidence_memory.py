from __future__ import annotations

from hashlib import sha256
import json
import unittest

from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    StateKey,
    StateKeyKind,
    WorkingMemory,
    WorkingMemoryClockRegressionError,
    WorkingMemoryConfig,
    WorkingMemoryFreshness,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    FreshnessState,
    ImageRegion2D,
    ObservationClock,
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
)

from helpers import OTHER_PROVENANCE, TEST_PROVENANCE, catalog


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
OTHER_CAMERA = SensorIdentity(
    "ayyo.camera.other.rgb.v1",
    SensorKind.RGB_CAMERA,
    "other_camera_optical_frame",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.semantic-memory.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.semantic-memory.adapter.v1",
    "ayyo.visual-interpretation.v1",
)
REGIONS = (
    ImageRegion2D(x_min=0.05, y_min=0.1, x_max=0.45, y_max=0.9),
    ImageRegion2D(x_min=0.55, y_min=0.4, x_max=0.85, y_max=0.8),
)


def frame(
    time_ns: int,
    *,
    robot_id: str = AYYO_ROBOT_ID,
    sensor: SensorIdentity = CAMERA,
    provenance: ObservationProvenance = TEST_PROVENANCE,
) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=robot_id,
        sensor=sensor,
        width=32,
        height=24,
        encoding="rgb8",
        step=96,
        data_size_bytes=2_304,
        is_bigendian=False,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
        observed_at_ns=time_ns,
        provenance=provenance,
        availability=SensorAvailability.AVAILABLE,
    )


def interpretation(
    source: VisualFrameObservation,
    *,
    result_at_ns: int | None = None,
    test_pattern: bool = False,
    object_category: str = "cup",
) -> VisualInterpretationObservation:
    detections = (
        (
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.TEST_PATTERN,
                label="test.marker.v1",
                region=REGIONS[0],
                confidence=None,
            ),
        )
        if test_pattern
        else (
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.PERSON,
                label="person",
                region=REGIONS[0],
                confidence=0.75,
            ),
            VisualDetection(
                source_visual_observation_id=source.observation_id,
                category=VisualSemanticCategory.OBJECT,
                label=object_category,
                region=REGIONS[1],
                confidence=None,
            ),
        )
    )
    return VisualInterpretationObservation(
        robot_id=source.robot_id,
        sensor=source.sensor,
        reference_frame_id=source.sensor.frame_id,
        source_visual_observation_id=source.observation_id,
        source_visual_fingerprint=source.fingerprint,
        observed_at_ns=source.observed_at_ns,
        result_at_ns=(
            source.observed_at_ns
            if result_at_ns is None
            else result_at_ns
        ),
        producer=PRODUCER,
        detections=detections,
        provenance=source.provenance,
        availability=source.availability,
    )


def semantic_id(
    result: VisualInterpretationObservation,
    detection: VisualDetection,
    *,
    kind: SemanticEvidenceKind,
    category: str | None,
) -> str:
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
        document["category"] = category
    encoded = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return f"{kind.value}-observation-sha256-{sha256(encoded).hexdigest()}"


def semantic_evidence(
    result: VisualInterpretationObservation,
    *,
    person_only: bool = False,
    force_object_from_test_pattern: bool = False,
) -> SemanticEvidenceObservation:
    items = []
    for detection in result.detections:
        if force_object_from_test_pattern:
            kind = SemanticEvidenceKind.OBJECT
            category = "cup"
        elif detection.category is VisualSemanticCategory.PERSON:
            kind = SemanticEvidenceKind.PERSON
            category = None
        else:
            kind = SemanticEvidenceKind.OBJECT
            category = detection.label
        if person_only and kind is not SemanticEvidenceKind.PERSON:
            continue
        items.append(
            SemanticEvidenceItem(
                kind=kind,
                source_semantic_observation_id=semantic_id(
                    result,
                    detection,
                    kind=kind,
                    category=category,
                ),
                source_detection_id=detection.detection_id,
                region=detection.region,
                confidence=detection.confidence,
                category=category,
            )
        )
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
        items=tuple(items),
        provenance=result.provenance,
        availability=result.availability,
    )


def memory(
    *,
    freshness: int = 50,
    ttl: int = 100,
    recent: int = 32,
    semantic_capacity: int = 8,
) -> WorkingMemory:
    return WorkingMemory(
        catalog(),
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            allowed_provenance=(TEST_PROVENANCE,),
            sensors=(CAMERA,),
            freshness_ns=freshness,
            retention_ttl_ns=ttl,
            permitted_future_skew_ns=5,
            recent_evidence_capacity=recent,
            environment_entity_capacity=1,
            semantic_evidence_capacity=semantic_capacity,
            visual_interpretation_producers=(PRODUCER,),
        ),
    )


def ingest_chain(
    store: WorkingMemory,
    source: VisualFrameObservation,
    result: VisualInterpretationObservation,
    semantic: SemanticEvidenceObservation,
    *,
    receipt: int = 1,
):
    now_ns = result.result_at_ns
    source_result = store.ingest(
        source,
        now_ns=now_ns,
        received_at_monotonic_ns=receipt,
    )
    interpretation_result = store.ingest(
        result,
        now_ns=now_ns,
        received_at_monotonic_ns=receipt + 1,
    )
    semantic_result = store.ingest(
        semantic,
        now_ns=now_ns,
        received_at_monotonic_ns=receipt + 2,
    )
    return source_result, interpretation_result, semantic_result


class SemanticEvidenceMemoryTest(unittest.TestCase):
    def test_valid_multiple_semantics_are_ingested_and_projected_anonymously(self) -> None:
        store = memory()
        source = frame(100)
        result = interpretation(source)
        semantic = semantic_evidence(result)
        outcomes = ingest_chain(store, source, result, semantic)
        self.assertTrue(
            all(outcome.status is IngestionStatus.ACCEPTED for outcome in outcomes)
        )
        snapshot = store.current_snapshot(now_ns=100)
        self.assertEqual(1, len(snapshot.semantic_states))
        self.assertEqual(2, len(snapshot.semantic_states[0].observation.items))
        self.assertEqual((), snapshot.entities)
        key = StateKey(
            StateKeyKind.ROBOT_SEMANTIC_EVIDENCE,
            semantic.observation_id,
        )
        self.assertEqual(
            WorkingMemoryFreshness.FRESH,
            store.query_freshness(key, now_ns=100).freshness,
        )

    def test_duplicate_is_a_noop_and_does_not_refresh_ttl(self) -> None:
        store = memory(ttl=100)
        source = frame(100)
        result = interpretation(source)
        semantic = semantic_evidence(result)
        ingest_chain(store, source, result, semantic)
        before = store.stats(now_ns=150)
        duplicate = store.ingest(
            semantic,
            now_ns=150,
            received_at_monotonic_ns=999,
        )
        self.assertEqual(IngestionReason.DUPLICATE_OBSERVATION, duplicate.reason)
        after = store.stats(now_ns=150)
        self.assertEqual(before.recent_evidence_count, after.recent_evidence_count)
        self.assertEqual(0, len(store.current_snapshot(now_ns=201).semantic_states))

    def test_older_and_same_result_time_conflicts_do_not_mutate_state(self) -> None:
        store = memory(ttl=1_000)
        old_source = frame(99)
        old_result = interpretation(old_source)
        old_semantic = semantic_evidence(old_result)
        store.ingest(old_source, now_ns=100, received_at_monotonic_ns=1)
        store.ingest(old_result, now_ns=100, received_at_monotonic_ns=2)

        source = frame(100)
        result = interpretation(source)
        full = semantic_evidence(result)
        ingest_chain(store, source, result, full, receipt=3)
        before = store.current_snapshot(now_ns=100)
        older = store.ingest(
            old_semantic,
            now_ns=100,
            received_at_monotonic_ns=6,
        )
        conflict = store.ingest(
            semantic_evidence(result, person_only=True),
            now_ns=100,
            received_at_monotonic_ns=7,
        )
        self.assertEqual(IngestionReason.OLDER_OBSERVATION, older.reason)
        self.assertEqual(IngestionReason.TEMPORAL_CONFLICT, conflict.reason)
        self.assertEqual(before, store.current_snapshot(now_ns=100))

    def test_future_expired_wrong_robot_sensor_and_provenance_fail_closed(self) -> None:
        cases = []
        future_source = frame(106)
        future_result = interpretation(future_source)
        cases.append(
            (
                semantic_evidence(future_result),
                100,
                IngestionReason.FUTURE_OBSERVATION,
            )
        )
        expired_source = frame(1)
        expired_result = interpretation(expired_source)
        cases.append(
            (
                semantic_evidence(expired_result),
                102,
                IngestionReason.EXPIRED_OBSERVATION,
            )
        )
        wrong_robot_source = frame(100, robot_id="other.robot.v1")
        cases.append(
            (
                semantic_evidence(interpretation(wrong_robot_source)),
                100,
                IngestionReason.WRONG_ROBOT_IDENTITY,
            )
        )
        wrong_sensor_source = frame(100, sensor=OTHER_CAMERA)
        cases.append(
            (
                semantic_evidence(interpretation(wrong_sensor_source)),
                100,
                IngestionReason.UNKNOWN_SENSOR,
            )
        )
        wrong_provenance_source = frame(100, provenance=OTHER_PROVENANCE)
        cases.append(
            (
                semantic_evidence(interpretation(wrong_provenance_source)),
                100,
                IngestionReason.PROVENANCE_NOT_ALLOWED,
            )
        )
        for semantic, now_ns, expected in cases:
            with self.subTest(reason=expected):
                store = memory()
                outcome = store.ingest(
                    semantic,
                    now_ns=now_ns,
                    received_at_monotonic_ns=1,
                )
                self.assertEqual(expected, outcome.reason)
                self.assertEqual(
                    0,
                    store.stats(now_ns=now_ns).current_semantic_evidence_count,
                )

    def test_missing_tampered_and_test_pattern_sources_cannot_enter_state(self) -> None:
        store = memory()
        source = frame(100)
        result = interpretation(source)
        semantic = semantic_evidence(result)
        missing = store.ingest(
            semantic,
            now_ns=100,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(IngestionReason.SOURCE_OBSERVATION_MISMATCH, missing.reason)

        store.ingest(source, now_ns=100, received_at_monotonic_ns=2)
        store.ingest(result, now_ns=100, received_at_monotonic_ns=3)
        wrong_evaluation = SemanticEvidenceObservation(
            robot_id=semantic.robot_id,
            sensor=semantic.sensor,
            reference_frame_id=semantic.reference_frame_id,
            source_visual_observation_id=semantic.source_visual_observation_id,
            source_visual_fingerprint=semantic.source_visual_fingerprint,
            source_interpretation_observation_id=(
                semantic.source_interpretation_observation_id
            ),
            source_interpretation_fingerprint=(
                semantic.source_interpretation_fingerprint
            ),
            observed_at_ns=semantic.observed_at_ns,
            result_at_ns=semantic.result_at_ns,
            producer=semantic.producer,
            evaluation_reference_sha256="0" * 64,
            items=semantic.items,
            provenance=semantic.provenance,
            availability=semantic.availability,
        )
        mismatch = store.ingest(
            wrong_evaluation,
            now_ns=100,
            received_at_monotonic_ns=4,
        )
        self.assertEqual(
            IngestionReason.SOURCE_OBSERVATION_MISMATCH,
            mismatch.reason,
        )
        object.__setattr__(semantic.items[0], "region", REGIONS[1])
        with self.assertRaises(ObservationIdentityError):
            store.ingest(
                semantic,
                now_ns=100,
                received_at_monotonic_ns=5,
            )

        test_store = memory()
        test_source = frame(100)
        test_result = interpretation(test_source, test_pattern=True)
        forged = semantic_evidence(
            test_result,
            force_object_from_test_pattern=True,
        )
        test_store.ingest(test_source, now_ns=100, received_at_monotonic_ns=1)
        test_store.ingest(test_result, now_ns=100, received_at_monotonic_ns=2)
        rejected = test_store.ingest(
            forged,
            now_ns=100,
            received_at_monotonic_ns=3,
        )
        self.assertEqual(
            IngestionReason.SOURCE_OBSERVATION_MISMATCH,
            rejected.reason,
        )

    def test_fresh_stale_and_ttl_transitions_change_snapshot_semantics(self) -> None:
        store = memory(freshness=50, ttl=100)
        source = frame(100)
        result = interpretation(source)
        semantic = semantic_evidence(result)
        ingest_chain(store, source, result, semantic)
        repeat = store.current_snapshot(now_ns=149)
        fresh = store.current_snapshot(now_ns=150)
        stale = store.current_snapshot(now_ns=151)
        expired = store.current_snapshot(now_ns=201)
        self.assertEqual(FreshnessState.FRESH, fresh.semantic_states[0].freshness)
        self.assertEqual(fresh.snapshot_id, repeat.snapshot_id)
        self.assertEqual(FreshnessState.STALE, stale.semantic_states[0].freshness)
        self.assertNotEqual(fresh.snapshot_id, stale.snapshot_id)
        self.assertEqual((), expired.semantic_states)
        self.assertNotEqual(stale.snapshot_id, expired.snapshot_id)

    def test_conservative_model_retains_recent_batches_without_claiming_absence(self) -> None:
        store = memory(ttl=1_000, recent=32)
        first_source = frame(100)
        first_result = interpretation(first_source)
        first = semantic_evidence(first_result)
        ingest_chain(store, first_source, first_result, first, receipt=1)

        second_source = frame(102)
        second_result = interpretation(second_source, object_category="bottle")
        second = semantic_evidence(second_result, person_only=True)
        ingest_chain(store, second_source, second_result, second, receipt=4)
        snapshot = store.current_snapshot(now_ns=102)
        self.assertEqual(2, len(snapshot.semantic_states))
        self.assertEqual((), snapshot.entities)
        self.assertFalse(hasattr(snapshot, "scene_is_empty"))

    def test_source_reference_eviction_removes_dependent_semantic_state(self) -> None:
        store = memory(ttl=1_000, recent=2)
        first_source = frame(100)
        first_result = interpretation(first_source)
        first = semantic_evidence(first_result)
        ingest_chain(store, first_source, first_result, first, receipt=1)
        self.assertEqual(1, len(store.current_snapshot(now_ns=100).semantic_states))

        second_source = frame(102)
        second_result = interpretation(second_source)
        store.ingest(second_source, now_ns=102, received_at_monotonic_ns=4)
        store.ingest(second_result, now_ns=102, received_at_monotonic_ns=5)
        self.assertEqual(0, len(store.current_snapshot(now_ns=102).semantic_states))

    def test_semantic_capacity_and_rejected_traffic_cannot_evict_valid_state(self) -> None:
        store = memory(ttl=1_000, recent=64, semantic_capacity=2)
        semantics = []
        receipt = 0
        for timestamp in (100, 101, 102):
            source = frame(timestamp)
            result = interpretation(source, object_category=f"object-{timestamp}")
            semantic = semantic_evidence(result)
            semantics.append(semantic)
            ingest_chain(store, source, result, semantic, receipt=receipt + 1)
            receipt += 3
        snapshot = store.current_snapshot(now_ns=102)
        self.assertEqual(2, len(snapshot.semantic_states))
        self.assertNotIn(
            semantics[0].observation_id,
            {item.observation.observation_id for item in snapshot.semantic_states},
        )
        before = snapshot.snapshot_id
        rejected = store.ingest(
            semantics[0],
            now_ns=102,
            received_at_monotonic_ns=receipt + 1,
        )
        self.assertEqual(
            IngestionReason.DUPLICATE_OBSERVATION,
            rejected.reason,
        )
        self.assertEqual(before, store.current_snapshot(now_ns=102).snapshot_id)

    def test_reset_clears_semantic_state_and_clock_epoch(self) -> None:
        store = memory()
        source = frame(100)
        result = interpretation(source)
        semantic = semantic_evidence(result)
        ingest_chain(store, source, result, semantic)
        with self.assertRaises(WorkingMemoryClockRegressionError):
            store.current_snapshot(now_ns=99)
        store.reset()
        self.assertEqual((), store.current_snapshot(now_ns=10).semantic_states)
        self.assertEqual(0, store.stats(now_ns=10).semantic_source_watermark_count)
        replay = store.ingest(
            semantic,
            now_ns=100,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(
            IngestionReason.SOURCE_OBSERVATION_MISMATCH,
            replay.reason,
        )

    def test_thousands_of_updates_keep_all_semantic_references_bounded(self) -> None:
        store = memory(
            ttl=10_000,
            recent=32,
            semantic_capacity=8,
        )
        receipt = 0
        for timestamp in range(1, 2_001):
            source = frame(timestamp)
            result = interpretation(
                source,
                object_category=f"object-{timestamp % 16}",
            )
            semantic = semantic_evidence(result)
            ingest_chain(store, source, result, semantic, receipt=receipt + 1)
            receipt += 3
        stats = store.stats(now_ns=2_000)
        self.assertLessEqual(stats.current_semantic_evidence_count, 8)
        self.assertEqual(32, stats.recent_evidence_count)
        self.assertLessEqual(stats.retained_unique_observation_count, 42)
        self.assertLessEqual(stats.retained_observation_reference_count, 42)
        self.assertEqual(1, stats.semantic_source_watermark_count)


if __name__ == "__main__":
    unittest.main()
