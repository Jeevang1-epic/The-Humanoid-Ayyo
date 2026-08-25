from __future__ import annotations

import tracemalloc
import unittest

from ayyo_working_memory import IngestionStatus, WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
)

from helpers import TEST_PROVENANCE, catalog


CAMERA_SENSOR = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
CALIBRATION_ID = "camera-calibration-sha256-" + "1" * 64


def visual(observed_at_ns: int) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA_SENSOR,
        width=320,
        height=240,
        encoding="rgb8",
        step=960,
        data_size_bytes=230_400,
        is_bigendian=False,
        calibration_id=CALIBRATION_ID,
        observed_at_ns=observed_at_ns,
        provenance=TEST_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


class VisualWorkingMemoryResourceTest(unittest.TestCase):
    def test_thousands_of_frames_retain_only_compact_bounded_metadata(self) -> None:
        memory = WorkingMemory(
            catalog(),
            WorkingMemoryConfig(
                robot_id=AYYO_ROBOT_ID,
                source_clock=TEST_PROVENANCE.clock,
                allowed_provenance=(TEST_PROVENANCE,),
                sensors=(CAMERA_SENSOR,),
                freshness_ns=500_000,
                retention_ttl_ns=1_000_000,
                permitted_future_skew_ns=0,
                recent_evidence_capacity=32,
                environment_entity_capacity=1,
            ),
        )
        tracemalloc.start()
        try:
            for index in range(1, 5_001):
                result = memory.ingest(
                    visual(index),
                    now_ns=index,
                    received_at_monotonic_ns=index,
                )
                self.assertEqual(IngestionStatus.ACCEPTED, result.status)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        stats = memory.stats(now_ns=5_000)
        snapshot = memory.current_snapshot(now_ns=5_000)
        self.assertEqual(1, stats.current_visual_count)
        self.assertEqual(32, stats.recent_evidence_count)
        self.assertLessEqual(stats.retained_unique_observation_count, 33)
        self.assertLessEqual(stats.retained_observation_reference_count, 33)
        self.assertEqual(1, len(snapshot.robot.visual_states))
        self.assertFalse(hasattr(snapshot.robot.visual_states[0].observation, "data"))
        self.assertLess(current, 2_000_000)
        self.assertLess(peak, 8_000_000)

    def test_visual_source_becomes_stale_then_disappears_without_health_claim(self) -> None:
        memory = WorkingMemory(
            catalog(),
            WorkingMemoryConfig(
                robot_id=AYYO_ROBOT_ID,
                source_clock=TEST_PROVENANCE.clock,
                allowed_provenance=(TEST_PROVENANCE,),
                sensors=(CAMERA_SENSOR,),
                freshness_ns=10,
                retention_ttl_ns=20,
                permitted_future_skew_ns=0,
                recent_evidence_capacity=4,
                environment_entity_capacity=1,
            ),
        )
        memory.ingest(visual(100), now_ns=100, received_at_monotonic_ns=1)
        fresh = memory.current_snapshot(now_ns=110).robot
        stale = memory.current_snapshot(now_ns=111).robot
        expired = memory.current_snapshot(now_ns=121).robot
        self.assertEqual(SensorAvailability.AVAILABLE, fresh.sensor_states[0].availability)
        self.assertEqual(SensorAvailability.STALE, stale.sensor_states[0].availability)
        self.assertEqual(SensorAvailability.UNAVAILABLE, expired.sensor_states[0].availability)
        self.assertEqual(0, len(expired.visual_states))
        self.assertEqual(0, len(expired.sensor_health_states))


if __name__ == "__main__":
    unittest.main()
