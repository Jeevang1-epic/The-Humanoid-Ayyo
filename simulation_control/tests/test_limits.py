# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import unittest

from ayyo_simulation_control import (
    CONTROLLED_JOINT_ALLOWLIST,
    ControlFailureCode,
    ControlValidationError,
    UrdfJointLimitCatalog,
)

from helpers import development_command, limit_catalog, robot_description


class UrdfLimitCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = limit_catalog()

    def test_exact_allowlist_and_authoritative_neck_limits(self) -> None:
        self.assertEqual(("neck_yaw_joint",), CONTROLLED_JOINT_ALLOWLIST)
        self.assertEqual(CONTROLLED_JOINT_ALLOWLIST, self.catalog.allowlist)
        neck = self.catalog.contract_for("neck_yaw_joint")
        self.assertIsNotNone(neck)
        assert neck is not None
        self.assertEqual("revolute", neck.joint_type)
        self.assertEqual(-1.2, neck.lower)
        self.assertEqual(1.2, neck.upper)
        self.assertEqual(3, len(self.catalog.joints))

    def test_boundary_minimum_and_maximum_are_inclusive(self) -> None:
        self.assertIsNone(self.catalog.validate(development_command(-1.2)))
        self.assertIsNone(self.catalog.validate(development_command(1.2)))

    def test_below_and_above_limits_are_rejected(self) -> None:
        below = self.catalog.validate(development_command(-1.2000001))
        above = self.catalog.validate(development_command(1.2000001))
        assert below is not None and above is not None
        self.assertIs(ControlFailureCode.BELOW_MINIMUM, below.code)
        self.assertIs(ControlFailureCode.ABOVE_MAXIMUM, above.code)

    def test_unknown_fixed_and_non_allowlisted_joints_are_distinct(self) -> None:
        cases = (
            ("unknown_joint", ControlFailureCode.UNKNOWN_JOINT),
            ("base_to_pelvis_joint", ControlFailureCode.FIXED_JOINT),
            ("head_pitch_joint", ControlFailureCode.JOINT_NOT_ALLOWLISTED),
        )
        for name, expected in cases:
            with self.subTest(joint=name):
                failure = self.catalog.validate(
                    development_command(0.0, joint_name=name)
                )
                assert failure is not None
                self.assertIs(expected, failure.code)

    def test_catalog_fingerprint_changes_with_authoritative_limit(self) -> None:
        original = robot_description()
        changed = original.replace(
            'lower="-1.2" upper="1.2"',
            'lower="-1.1" upper="1.2"',
            1,
        )
        other = UrdfJointLimitCatalog(changed)
        self.assertNotEqual(self.catalog.fingerprint, other.fingerprint)
        self.assertEqual(-1.1, other.contract_for("neck_yaw_joint").lower)

    def test_malformed_urdf_fails_closed(self) -> None:
        for description in ("", "<robot>", "<not_robot/>"):
            with self.subTest(description=description):
                with self.assertRaises(ControlValidationError):
                    UrdfJointLimitCatalog(description)


if __name__ == "__main__":
    unittest.main()
