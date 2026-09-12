"""Typed fail-closed manipulation-planning failures."""

from __future__ import annotations

from enum import StrEnum


class PlanningFailureCode(StrEnum):
    MALFORMED_MODEL = "malformed_model"
    MODEL_MISMATCH = "model_mismatch"
    WRONG_MANIPULATOR_GROUP = "wrong_manipulator_group"
    UNKNOWN_JOINT = "unknown_joint"
    WRONG_ARM_JOINT = "wrong_arm_joint"
    FIXED_JOINT = "fixed_joint"
    DUPLICATE_JOINT = "duplicate_joint"
    MISSING_JOINT = "missing_joint"
    JOINT_ORDER_MISMATCH = "joint_order_mismatch"
    NONFINITE_POSITION = "nonfinite_position"
    BELOW_JOINT_LIMIT = "below_joint_limit"
    ABOVE_JOINT_LIMIT = "above_joint_limit"
    UNKNOWN_FRAME = "unknown_frame"
    INVALID_COLLISION_OBJECT = "invalid_collision_object"
    DUPLICATE_COLLISION_OBJECT = "duplicate_collision_object"
    RESOURCE_LIMIT = "resource_limit"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    MALFORMED_ARTIFACT = "malformed_artifact"


class ManipulationPlanningError(Exception):
    """Base manipulation-planning failure."""


class PlanningValidationError(ManipulationPlanningError, ValueError):
    """A planning model, request, or evidence object failed closed."""

    def __init__(self, code: PlanningFailureCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class PlanningSerializationError(ManipulationPlanningError, ValueError):
    """Canonical planning serialization or reconstruction failed closed."""
