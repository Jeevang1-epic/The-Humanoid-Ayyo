"""Typed fail-closed errors for Stage 9C simulation execution."""

from __future__ import annotations

from enum import StrEnum


class SimulationExecutionFailureCode(StrEnum):
    MALFORMED_ARTIFACT = "malformed_artifact"
    UPSTREAM_INTEGRITY = "upstream_integrity"
    UPSTREAM_INELIGIBLE = "upstream_ineligible"
    TRAJECTORY_MISMATCH = "trajectory_mismatch"
    CONTROLLER_MISMATCH = "controller_mismatch"
    SIMULATION_BOUNDARY = "simulation_boundary"
    COLLISION_PREFLIGHT = "collision_preflight"
    START_STATE_MISMATCH = "start_state_mismatch"
    STATE_STALE = "state_stale"
    ACTION_UNAVAILABLE = "action_unavailable"
    GOAL_REJECTED = "goal_rejected"
    PATH_TOLERANCE = "path_tolerance"
    GOAL_TOLERANCE = "goal_tolerance"
    EXECUTION_TIMEOUT = "execution_timeout"
    EXECUTION_CANCELED = "execution_canceled"
    EXECUTION_ABORTED = "execution_aborted"
    SIMULATOR_SHUTDOWN = "simulator_shutdown"
    FEEDBACK_INVALID = "feedback_invalid"
    PHYSICAL_OBSERVATION = "physical_observation"
    WHOLE_BODY_STABILITY = "whole_body_stability"
    NONFINITE_VALUE = "nonfinite_value"
    RESOURCE_LIMIT = "resource_limit"


class ManipulationSimulationExecutionError(Exception):
    """Base exception for the Stage 9C package."""


class SimulationExecutionValidationError(
    ManipulationSimulationExecutionError,
    ValueError,
):
    """Raised when Stage 9C evidence violates a typed invariant."""

    def __init__(
        self,
        code: SimulationExecutionFailureCode,
        detail: str,
    ) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class SimulationExecutionSerializationError(
    ManipulationSimulationExecutionError,
    ValueError,
):
    """Raised when canonical Stage 9C reconstruction fails closed."""
