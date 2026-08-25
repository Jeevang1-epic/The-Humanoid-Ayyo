from __future__ import annotations

import unittest

from ayyo_perception import (
    DeterministicVisualReferenceAdapter,
    REFERENCE_VISUAL_PRODUCER,
)
from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    WorkingMemory,
    WorkingMemoryConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ObservationClock,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
)

from helpers import TEST_PROVENANCE, catalog


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
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


def memory(*, recent: int = 8) -> WorkingMemory:
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
            visual_interpretation_producers=(REFERENCE_VISUAL_PRODUCER,),
        ),
    )


class VisualInterpretationMemoryTest(unittest.TestCase):
    def test_retain_project_query_without_mutation_and_duplicate_growth(self) -> None:
        store = memory()
        source = frame(100)
        result = DeterministicVisualReferenceAdapter().interpret(
            source,
            result_at_ns=101,
        )
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
        adapter = DeterministicVisualReferenceAdapter()
        receipt = 0
        for index in range(1, 1001):
            source = frame(index)
            receipt += 1
            self.assertEqual(
                IngestionStatus.ACCEPTED,
                store.ingest(source, now_ns=index, received_at_monotonic_ns=receipt).status,
            )
            receipt += 1
            result = adapter.interpret(source, result_at_ns=index)
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
