from __future__ import annotations

import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    EnvironmentEntityObservation,
    FreshnessState,
    JointObservation,
    RobotAvailability,
    RobotStateObservation,
    SnapshotIdentityError,
    WorldEntityIdentity,
    WorldEntityKind,
    WorldModelProjector,
    rebuild_snapshot,
)

from helpers import TEST_PROVENANCE, catalog


class ProjectorTest(unittest.TestCase):
    def robot_observation(self, *, position=0.1, time=100):
        return RobotStateObservation(
            robot_id=AYYO_ROBOT_ID,
            joints=(JointObservation("neck_yaw_joint", position),),
            observed_at_ns=time,
            provenance=TEST_PROVENANCE,
            confidence=1.0,
        )

    def entity_observation(self, entity_id, *, time=100):
        return EnvironmentEntityObservation(
            robot_id=AYYO_ROBOT_ID,
            entity=WorldEntityIdentity(entity_id, WorldEntityKind.OBJECT),
            properties={"label": entity_id},
            observed_at_ns=time,
            provenance=TEST_PROVENANCE,
            confidence=0.75,
        )

    def project(self, *, now=100, joint=None, entities=None):
        return WorldModelProjector(catalog()).project(
            now_ns=now,
            fresh_for_ns=50,
            joint_evidence={} if joint is None else {"neck_yaw_joint": joint},
            pose_evidence=None,
            entity_evidence={} if entities is None else entities,
        )

    def test_empty_world_has_known_robot_identity_without_fabricated_state(self) -> None:
        snapshot = self.project()
        self.assertEqual(AYYO_ROBOT_ID, snapshot.robot.robot_id)
        self.assertEqual(RobotAvailability.UNAVAILABLE, snapshot.robot.availability)
        self.assertEqual((), snapshot.robot.joints)
        self.assertEqual((), snapshot.entities)

    def test_partial_body_state_preserves_provenance_and_freshness(self) -> None:
        observation = self.robot_observation()
        snapshot = self.project(joint=observation)
        self.assertEqual(RobotAvailability.PARTIAL, snapshot.robot.availability)
        joint = snapshot.robot.joints[0]
        self.assertEqual(0.1, joint.joint.position)
        self.assertEqual(observation.observation_id, joint.observation_id)
        self.assertEqual(TEST_PROVENANCE, joint.provenance)
        self.assertEqual(FreshnessState.FRESH, joint.freshness)

    def test_snapshot_becomes_stale_at_a_discrete_boundary(self) -> None:
        observation = self.robot_observation()
        fresh = self.project(now=150, joint=observation)
        stale = self.project(now=151, joint=observation)
        self.assertEqual(FreshnessState.FRESH, fresh.robot.joints[0].freshness)
        self.assertEqual(FreshnessState.STALE, stale.robot.joints[0].freshness)
        self.assertNotEqual(fresh.snapshot_id, stale.snapshot_id)

    def test_snapshot_identity_ignores_capture_timing_noise_with_same_semantics(self) -> None:
        observation = self.robot_observation()
        left = self.project(now=110, joint=observation)
        right = self.project(now=120, joint=observation)
        self.assertNotEqual(left.captured_at_ns, right.captured_at_ns)
        self.assertEqual(left.snapshot_id, right.snapshot_id)
        self.assertEqual(left.version, right.version)

    def test_snapshot_entity_order_is_canonical_and_query_is_narrow(self) -> None:
        one = self.entity_observation("object.1")
        two = self.entity_observation("object.2")
        left = self.project(entities={"object.2": two, "object.1": one})
        right = self.project(entities={"object.1": one, "object.2": two})
        self.assertEqual(left, right)
        self.assertEqual("object.1", left.get_entity("object.1").identity.entity_id)
        self.assertIsNone(left.get_entity("object.missing"))

    def test_rebuild_detects_snapshot_result_substitution(self) -> None:
        snapshot = self.project(joint=self.robot_observation())
        object.__setattr__(snapshot, "snapshot_id", "world-snapshot-" + "0" * 64)
        with self.assertRaises(SnapshotIdentityError):
            rebuild_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
