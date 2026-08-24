from __future__ import annotations

import unittest

from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    StateKey,
    StateKeyKind,
    WorkingMemoryClockRegressionError,
    WorkingMemoryFreshness,
)
from ayyo_world_model import (
    JointObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotAvailability,
)

from helpers import (
    OTHER_PROVENANCE,
    TEST_PROVENANCE,
    entity_observation,
    memory,
    robot_observation,
)


class WorkingMemoryTest(unittest.TestCase):
    def ingest(self, store, observation, *, now=100, receipt=1):
        return store.ingest(
            observation,
            now_ns=now,
            received_at_monotonic_ns=receipt,
        )

    def test_valid_robot_state_is_accepted_and_queryable(self) -> None:
        store = memory()
        observation = robot_observation()
        result = self.ingest(store, observation)
        self.assertEqual(IngestionStatus.ACCEPTED, result.status)
        self.assertEqual(IngestionReason.ACCEPTED_NEW, result.reason)
        robot = store.get_robot_state(now_ns=100)
        self.assertEqual(RobotAvailability.PARTIAL, robot.availability)
        self.assertEqual(0.1, robot.joints[0].joint.position)
        self.assertEqual(observation.observation_id, robot.joints[0].observation_id)

    def test_exact_duplicate_does_not_refresh_or_grow_memory(self) -> None:
        store = memory()
        observation = robot_observation()
        self.ingest(store, observation, receipt=1)
        result = self.ingest(store, observation, receipt=999)
        self.assertEqual(IngestionStatus.DUPLICATE, result.status)
        self.assertEqual(1, len(store.recent_evidence(now_ns=100)))
        stats = store.stats(now_ns=100)
        self.assertEqual((1, 1), (stats.accepted_count, stats.duplicate_count))
        self.assertEqual(1, stats.retained_unique_observation_count)

    def test_newer_observation_replaces_current_state(self) -> None:
        store = memory()
        self.ingest(store, robot_observation(time=90, position=0.1), now=100)
        result = self.ingest(store, robot_observation(time=100, position=0.2), now=100)
        self.assertEqual(IngestionReason.ACCEPTED_REPLACEMENT, result.reason)
        self.assertEqual(0.2, store.get_robot_state(now_ns=100).joints[0].joint.position)

    def test_older_observation_is_rejected_without_state_change(self) -> None:
        store = memory()
        current = robot_observation(time=100, position=0.2)
        self.ingest(store, current)
        result = self.ingest(store, robot_observation(time=99, position=0.1))
        self.assertEqual(IngestionReason.OLDER_OBSERVATION, result.reason)
        self.assertEqual(current.observation_id, store.get_robot_state(now_ns=100).joints[0].observation_id)

    def test_same_timestamp_different_state_is_rejected_as_temporal_conflict(self) -> None:
        store = memory()
        self.ingest(store, robot_observation(position=0.1))
        result = self.ingest(store, robot_observation(position=0.2))
        self.assertEqual(IngestionReason.TEMPORAL_CONFLICT, result.reason)
        self.assertEqual(0.1, store.get_robot_state(now_ns=100).joints[0].joint.position)

    def test_future_and_expired_observations_are_rejected(self) -> None:
        store = memory()
        future = self.ingest(store, robot_observation(time=106), now=100)
        expired = self.ingest(store, robot_observation(time=0), now=101)
        self.assertEqual(IngestionReason.FUTURE_OBSERVATION, future.reason)
        self.assertEqual(IngestionReason.EXPIRED_OBSERVATION, expired.reason)
        self.assertEqual(RobotAvailability.UNAVAILABLE, store.get_robot_state(now_ns=101).availability)

    def test_freshness_transitions_without_extending_ttl(self) -> None:
        store = memory(freshness=50, ttl=100)
        self.ingest(store, robot_observation(time=100), now=100)
        key = StateKey(StateKeyKind.ROBOT_JOINT, "neck_yaw_joint")
        self.assertEqual(
            WorkingMemoryFreshness.FRESH,
            store.query_freshness(key, now_ns=150).freshness,
        )
        stale = store.query_freshness(key, now_ns=151)
        self.assertEqual(WorkingMemoryFreshness.STALE, stale.freshness)
        self.assertEqual(51, stale.age_ns)
        self.assertEqual(
            WorkingMemoryFreshness.UNKNOWN,
            store.query_freshness(key, now_ns=201).freshness,
        )
        self.assertEqual((), store.recent_evidence(now_ns=201))

    def test_partial_joint_updates_merge_without_clearing_unmentioned_state(self) -> None:
        store = memory()
        first = robot_observation(
            time=90,
            joints=(
                JointObservation("neck_yaw_joint", 0.1),
                JointObservation("head_pitch_joint", 0.2),
            ),
        )
        second = robot_observation(time=100, position=0.3)
        self.ingest(store, first)
        self.ingest(store, second)
        robot = store.get_robot_state(now_ns=100)
        self.assertEqual(RobotAvailability.AVAILABLE, robot.availability)
        self.assertEqual(
            {"head_pitch_joint": 0.2, "neck_yaw_joint": 0.3},
            {item.joint.joint_name: item.joint.position for item in robot.joints},
        )

    def test_mixed_partial_update_changes_only_newer_keys(self) -> None:
        store = memory()
        self.ingest(store, robot_observation(time=100, position=0.4), now=100)
        mixed = robot_observation(
            time=95,
            joints=(
                JointObservation("neck_yaw_joint", 0.2),
                JointObservation("head_pitch_joint", 0.1),
            ),
        )
        result = self.ingest(store, mixed, now=100)
        self.assertEqual(IngestionStatus.ACCEPTED, result.status)
        self.assertEqual(
            (StateKey(StateKeyKind.ROBOT_JOINT, "head_pitch_joint"),),
            result.updated_keys,
        )
        robot = store.get_robot_state(now_ns=100)
        self.assertEqual(
            {"head_pitch_joint": 0.1, "neck_yaw_joint": 0.4},
            {item.joint.joint_name: item.joint.position for item in robot.joints},
        )

    def test_wrong_robot_unknown_fixed_and_invalid_joint_are_typed_rejections(self) -> None:
        cases = (
            (robot_observation(robot_id="other.robot.v1"), IngestionReason.WRONG_ROBOT_IDENTITY),
            (robot_observation(joint="missing_joint"), IngestionReason.UNKNOWN_JOINT),
            (robot_observation(joint="fixed_joint"), IngestionReason.FIXED_JOINT),
            (robot_observation(position=1.3), IngestionReason.INVALID_JOINT_VALUE),
        )
        for observation, reason in cases:
            store = memory()
            with self.subTest(reason=reason):
                self.assertEqual(reason, self.ingest(store, observation).reason)
                self.assertEqual(0, store.stats(now_ns=100).current_joint_count)

    def test_unreviewed_provenance_and_physical_substitution_are_rejected(self) -> None:
        store = memory()
        self.assertEqual(
            IngestionReason.PROVENANCE_NOT_ALLOWED,
            self.ingest(store, robot_observation(provenance=OTHER_PROVENANCE)).reason,
        )
        physical = ObservationProvenance(
            ObservationSourceKind.PHYSICAL_SENSOR,
            "ros.joint-states.physical.v1",
            ObservationClock.ROS_SYSTEM_TIME,
            ObservationTransport.ROS2,
            "sensor-msgs.joint-state.v1",
        )
        self.assertEqual(
            IngestionReason.PROVENANCE_NOT_ALLOWED,
            self.ingest(store, robot_observation(provenance=physical)).reason,
        )

    def test_environment_entity_is_queryable_and_unknown_is_explicit(self) -> None:
        store = memory()
        self.ingest(store, entity_observation("object.cup.1"))
        entity = store.get_entity("object.cup.1", now_ns=100)
        self.assertEqual({"value": "object.cup.1"}, entity.properties)
        self.assertIsNone(store.get_entity("object.unknown", now_ns=100))

    def test_environment_capacity_evicts_oldest_deterministically(self) -> None:
        def populate(order):
            store = memory(entities=2, recent=2)
            observations = {
                "object.1": entity_observation("object.1", time=90),
                "object.2": entity_observation("object.2", time=95),
                "object.3": entity_observation("object.3", time=100),
            }
            for entity_id in order:
                self.ingest(store, observations[entity_id], now=100)
            return store

        left = populate(("object.1", "object.2", "object.3"))
        right = populate(("object.3", "object.1", "object.2"))
        self.assertEqual(left.current_snapshot(now_ns=100), right.current_snapshot(now_ns=100))
        self.assertEqual(
            ["object.2", "object.3"],
            [item.identity.entity_id for item in left.current_snapshot(now_ns=100).entities],
        )
        self.assertEqual(2, left.stats(now_ns=100).recent_evidence_count)

    def test_replacement_does_not_count_as_entity_flooding(self) -> None:
        store = memory(entities=1, recent=3)
        for timestamp in range(100, 110):
            self.ingest(
                store,
                entity_observation("object.1", time=timestamp, value=timestamp),
                now=timestamp,
            )
        stats = store.stats(now_ns=109)
        self.assertEqual(1, stats.current_entity_count)
        self.assertEqual(3, stats.recent_evidence_count)
        self.assertEqual(0, stats.eviction_count)
        self.assertEqual(109, store.get_entity("object.1", now_ns=109).properties["value"])

    def test_clock_regression_fails_visibly_and_reset_allows_new_epoch(self) -> None:
        store = memory()
        self.ingest(store, robot_observation(time=100), now=100)
        with self.assertRaises(WorkingMemoryClockRegressionError):
            store.current_snapshot(now_ns=99)
        store.reset()
        self.ingest(store, robot_observation(time=10), now=10)
        self.assertEqual(10, store.get_robot_state(now_ns=10).joints[0].observed_at_ns)

    def test_receipt_clock_is_retained_but_not_observation_identity(self) -> None:
        store = memory()
        observation = robot_observation()
        self.ingest(store, observation, receipt=12345)
        retained = store.recent_evidence(now_ns=100)[0]
        self.assertEqual(12345, retained.received_at_monotonic_ns)
        self.assertEqual(observation.observation_id, retained.observation.observation_id)


if __name__ == "__main__":
    unittest.main()
