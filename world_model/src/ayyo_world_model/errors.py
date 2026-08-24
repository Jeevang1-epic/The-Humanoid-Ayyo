"""Typed World Model failures."""

from __future__ import annotations

from enum import StrEnum


class WorldModelError(Exception):
    """Base error for the standalone World Model contract."""


class WorldModelFailureCode(StrEnum):
    MALFORMED_OBSERVATION = "malformed_observation"
    MALFORMED_PROVENANCE = "malformed_provenance"
    IDENTITY_MISMATCH = "identity_mismatch"
    WRONG_ROBOT_IDENTITY = "wrong_robot_identity"
    UNKNOWN_JOINT = "unknown_joint"
    FIXED_JOINT = "fixed_joint"
    JOINT_BELOW_MINIMUM = "joint_below_minimum"
    JOINT_ABOVE_MAXIMUM = "joint_above_maximum"
    JOINT_VELOCITY_EXCEEDED = "joint_velocity_exceeded"
    JOINT_EFFORT_EXCEEDED = "joint_effort_exceeded"
    MALFORMED_CATALOG = "malformed_catalog"
    SNAPSHOT_INVARIANT = "snapshot_invariant"


class WorldModelValidationError(WorldModelError, ValueError):
    """A bounded World Model value is malformed."""

    def __init__(self, code: WorldModelFailureCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class ObservationIdentityError(WorldModelValidationError):
    """An observation's derived identity does not match its content."""


class SnapshotIdentityError(WorldModelValidationError):
    """A snapshot's derived identity does not match its content."""
