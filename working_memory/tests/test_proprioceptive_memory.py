from __future__ import annotations

import tracemalloc
import unittest

from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    StateKey,
    StateKeyKind,
    WorkingMemoryFreshness,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    BodyPoseObservation,
    Pose3D,
    SensorAvailability,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
)

from helpers import (
    IMU_SENSOR,
    POSE_SENSOR,
    TEST_PROVENANCE,
    imu_observation,
    memory,
)


class ProprioceptiveWorkingMemoryTest(unittest.TestCase):
    def ingest(self, store, observation, *, now=100, receipt=1):
        return store.ingest(
            observation,
            now_ns=now,
            received_at_monotonic_ns=receipt,
        )

    def test_imu_is_bounded_queryable_and_provenance_preserving(self) -> None:
        store = memory(sensors=(IMU_SENSOR, POSE_SENSOR))
        observation = imu_observation()
        result = self.ingest(store, observation)
        self.assertEqual(IngestionStatus.ACCEPTED, result.status)
        self.assertEqual(
            (StateKey(StateKeyKind.ROBOT_IMU, IMU_SENSOR.sensor_id),),
            result.updated_keys,
        )
        robot = store.get_robot_state(now_ns=100)
        self.assertEqual(1, len(robot.imu_states))
        self.assertEqual(observation, robot.imu_states[0].observation)
        self.assertEqual(SensorAvailability.AVAILABLE, robot.imu_states[0].availability)
        self.assertEqual(
            SensorAvailability.UNAVAILABLE,
            next(
                state.availability
                for state in robot.sensor_states
                if state.sensor == POSE_SENSOR
            ),
        )

    def test_unknown_or_substituted_sensor_contract_is_rejected(self) -> None:
        store = memory(sensors=(IMU_SENSOR,))
        unknown = SensorIdentity("ayyo.imu.unknown.v1", SensorKind.IMU, "imu_link")
        substituted_frame = SensorIdentity(
            IMU_SENSOR.sensor_id,
            SensorKind.IMU,
            "head_link",
        )
        for sensor in (unknown, substituted_frame):
            with self.subTest(sensor=sensor):
                result = self.ingest(store, imu_observation(sensor=sensor))
                self.assertEqual(IngestionReason.UNKNOWN_SENSOR, result.reason)

    def test_health_error_overrides_older_measurement_without_erasing_it(self) -> None:
        store = memory(sensors=(IMU_SENSOR,))
        self.ingest(store, imu_observation(time=90), now=100)
        health = SensorHealthObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=IMU_SENSOR,
            availability=SensorAvailability.ERROR,
            observed_at_ns=100,
            provenance=TEST_PROVENANCE,
            evidence_detail="driver error",
        )
        self.ingest(store, health, now=100, receipt=2)
        robot = store.get_robot_state(now_ns=100)
        self.assertEqual(1, len(robot.imu_states))
        self.assertEqual(SensorAvailability.ERROR, robot.imu_states[0].availability)
        self.assertEqual(SensorAvailability.ERROR, robot.sensor_states[0].availability)

    def test_newer_measurement_supersedes_older_degraded_health(self) -> None:
        store = memory(sensors=(IMU_SENSOR,))
        health = SensorHealthObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=IMU_SENSOR,
            availability=SensorAvailability.DEGRADED,
            observed_at_ns=90,
            provenance=TEST_PROVENANCE,
            evidence_detail="calibrating",
        )
        self.ingest(store, health, now=100)
        self.ingest(store, imu_observation(time=100), now=100, receipt=2)
        robot = store.get_robot_state(now_ns=100)
        self.assertEqual(SensorAvailability.AVAILABLE, robot.imu_states[0].availability)
        self.assertEqual(SensorAvailability.AVAILABLE, robot.sensor_states[0].availability)

    def test_fresh_to_stale_to_unavailable_disappearance_is_deterministic(self) -> None:
        store = memory(sensors=(IMU_SENSOR,), freshness=50, ttl=100)
        self.ingest(store, imu_observation(time=100), now=100)
        fresh = store.current_snapshot(now_ns=150)
        stale = store.current_snapshot(now_ns=151)
        unavailable = store.current_snapshot(now_ns=201)
        self.assertEqual(SensorAvailability.AVAILABLE, fresh.robot.sensor_states[0].availability)
        self.assertEqual(SensorAvailability.STALE, stale.robot.sensor_states[0].availability)
        self.assertEqual(1, len(stale.robot.imu_states))
        self.assertEqual(SensorAvailability.UNAVAILABLE, unavailable.robot.sensor_states[0].availability)
        self.assertEqual((), unavailable.robot.imu_states)
        self.assertNotEqual(fresh.snapshot_id, stale.snapshot_id)
        self.assertNotEqual(stale.snapshot_id, unavailable.snapshot_id)

    def test_query_time_inside_one_freshness_state_does_not_change_identity(self) -> None:
        store = memory(sensors=(IMU_SENSOR,), freshness=50, ttl=100)
        self.ingest(store, imu_observation(time=100), now=100)
        first = store.current_snapshot(now_ns=110)
        second = store.current_snapshot(now_ns=120)
        self.assertNotEqual(first.captured_at_ns, second.captured_at_ns)
        self.assertEqual(first.snapshot_id, second.snapshot_id)

    def test_pose_remains_missing_until_actual_body_pose_evidence_arrives(self) -> None:
        store = memory(sensors=(POSE_SENSOR,))
        empty = store.get_robot_state(now_ns=100)
        self.assertIsNone(empty.base_pose)
        self.assertEqual(SensorAvailability.UNAVAILABLE, empty.sensor_states[0].availability)
        pose = BodyPoseObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=POSE_SENSOR,
            pose=Pose3D("map", "base_link", (1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
            observed_at_ns=100,
            provenance=TEST_PROVENANCE,
            availability=SensorAvailability.AVAILABLE,
            quality=None,
        )
        self.ingest(store, pose)
        observed = store.get_robot_state(now_ns=100)
        self.assertEqual((1.0, 2.0, 3.0), observed.base_pose.pose.position_xyz)
        self.assertIsNone(observed.base_pose.confidence)

    def test_sensor_freshness_query_and_expiry_are_explicit(self) -> None:
        store = memory(sensors=(IMU_SENSOR,), freshness=50, ttl=100)
        self.ingest(store, imu_observation(time=100), now=100)
        key = StateKey(StateKeyKind.ROBOT_IMU, IMU_SENSOR.sensor_id)
        self.assertEqual(
            WorkingMemoryFreshness.STALE,
            store.query_freshness(key, now_ns=151).freshness,
        )
        self.assertEqual(
            WorkingMemoryFreshness.UNKNOWN,
            store.query_freshness(key, now_ns=201).freshness,
        )

    def test_high_rate_imu_updates_bound_references_and_memory(self) -> None:
        store = memory(
            sensors=(IMU_SENSOR,),
            recent=16,
            freshness=500_000,
            ttl=1_000_000,
        )
        tracemalloc.start()
        try:
            for index in range(3_000):
                self.ingest(
                    store,
                    imu_observation(
                        time=index,
                        angular=(index / 3_000.0, 0.0, 0.0),
                    ),
                    now=index,
                    receipt=index,
                )
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        stats = store.stats(now_ns=2_999)
        self.assertEqual(1, stats.current_imu_count)
        self.assertEqual(16, stats.recent_evidence_count)
        self.assertLessEqual(stats.retained_unique_observation_count, 17)
        self.assertLessEqual(stats.retained_observation_reference_count, 17)
        self.assertLess(current, 2_000_000)
        self.assertLess(peak, 8_000_000)


if __name__ == "__main__":
    unittest.main()
