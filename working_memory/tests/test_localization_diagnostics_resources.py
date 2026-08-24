from __future__ import annotations

import tracemalloc
import unittest

from ayyo_working_memory import IngestionStatus
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    BodyPoseObservation,
    Pose3D,
    SensorAvailability,
    SensorHealthObservation,
)

from helpers import POSE_SENSOR, TEST_PROVENANCE, memory


class LocalizationDiagnosticsResourceTest(unittest.TestCase):
    def test_high_rate_pose_and_health_retention_stays_bounded(self) -> None:
        store = memory(
            sensors=(POSE_SENSOR,),
            recent=32,
            freshness=500_000,
            ttl=1_000_000,
        )
        tracemalloc.start()
        try:
            for index in range(3_000):
                pose = BodyPoseObservation(
                    robot_id=AYYO_ROBOT_ID,
                    sensor=POSE_SENSOR,
                    pose=Pose3D(
                        'odom',
                        'base_link',
                        (index / 3_000.0, 0.0, 0.95),
                        (0.0, 0.0, 0.0, 1.0),
                    ),
                    observed_at_ns=index,
                    provenance=TEST_PROVENANCE,
                    availability=SensorAvailability.AVAILABLE,
                )
                health = SensorHealthObservation(
                    robot_id=AYYO_ROBOT_ID,
                    sensor=POSE_SENSOR,
                    availability=(
                        SensorAvailability.AVAILABLE
                        if index % 2 == 0
                        else SensorAvailability.DEGRADED
                    ),
                    observed_at_ns=index,
                    provenance=TEST_PROVENANCE,
                    evidence_detail='bounded fixture health',
                )
                pose_result = store.ingest(
                    pose,
                    now_ns=index,
                    received_at_monotonic_ns=index * 2,
                )
                health_result = store.ingest(
                    health,
                    now_ns=index,
                    received_at_monotonic_ns=index * 2 + 1,
                )
                self.assertEqual(IngestionStatus.ACCEPTED, pose_result.status)
                self.assertEqual(IngestionStatus.ACCEPTED, health_result.status)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        stats = store.stats(now_ns=2_999)
        robot = store.get_robot_state(now_ns=2_999)
        self.assertEqual(1, stats.current_body_pose_count)
        self.assertEqual(1, stats.current_sensor_health_count)
        self.assertEqual(32, stats.recent_evidence_count)
        self.assertLessEqual(stats.retained_unique_observation_count, 34)
        self.assertLessEqual(stats.retained_observation_reference_count, 34)
        self.assertIsNotNone(robot.base_pose)
        self.assertEqual(1, len(robot.sensor_health_states))
        self.assertLess(current, 2_000_000)
        self.assertLess(peak, 8_000_000)


if __name__ == '__main__':
    unittest.main()
