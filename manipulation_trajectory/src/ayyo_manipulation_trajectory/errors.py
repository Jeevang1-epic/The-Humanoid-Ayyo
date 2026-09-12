"""Typed fail-closed errors for Stage 9B trajectory evidence."""

from __future__ import annotations

from enum import StrEnum


class TrajectoryFailureCode(StrEnum):
    MALFORMED_ARTIFACT = "malformed_artifact"
    UPSTREAM_INTEGRITY = "upstream_integrity"
    UPSTREAM_REJECTED = "upstream_rejected"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    JOINT_ORDER_MISMATCH = "joint_order_mismatch"
    POSITION_LIMIT = "position_limit"
    TIMING_CONFIGURATION = "timing_configuration"
    TIMESTAMP = "timestamp"
    ZERO_MOVEMENT_SEGMENT = "zero_movement_segment"
    RESOURCE_LIMIT = "resource_limit"
    SAFETY_MISMATCH = "safety_mismatch"
    SKILL_MISMATCH = "skill_mismatch"
    RUNTIME_AUTHORITY_FORBIDDEN = "runtime_authority_forbidden"
    NONFINITE_VALUE = "nonfinite_value"


class ManipulationTrajectoryError(Exception):
    """Base exception for the Stage 9B package."""


class TrajectoryValidationError(ManipulationTrajectoryError, ValueError):
    """Raised when trajectory evidence violates a typed invariant."""

    def __init__(self, code: TrajectoryFailureCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class TrajectorySerializationError(ManipulationTrajectoryError, ValueError):
    """Raised when canonical trajectory serialization fails closed."""
