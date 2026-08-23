"""Typed failures for the Ayyo simulation-control boundary."""

from __future__ import annotations

from enum import StrEnum


class ControlFailureCode(StrEnum):
    MALFORMED_COMMAND = "malformed_command"
    UNSUPPORTED_COMMAND_TYPE = "unsupported_command_type"
    DUPLICATE_TARGET = "duplicate_target"
    UNKNOWN_JOINT = "unknown_joint"
    FIXED_JOINT = "fixed_joint"
    JOINT_NOT_ALLOWLISTED = "joint_not_allowlisted"
    BELOW_MINIMUM = "below_minimum"
    ABOVE_MAXIMUM = "above_maximum"
    STALE_COMMAND = "stale_command"
    COMMAND_FROM_FUTURE = "command_from_future"
    MALFORMED_UPSTREAM_IDENTITY = "malformed_upstream_identity"
    UPSTREAM_NOT_ELIGIBLE = "upstream_not_eligible"
    STALE_RUNTIME_BINDING = "stale_runtime_binding"
    RUNTIME_ENDPOINT_MISMATCH = "runtime_endpoint_mismatch"
    DEVELOPMENT_INJECTION_DISABLED = "development_injection_disabled"
    DEVELOPMENT_SESSION_CHANGED = "development_session_changed"
    CONTROL_SYSTEM_INACTIVE = "control_system_inactive"
    CONTROLLER_UNAVAILABLE = "controller_unavailable"
    CONTROLLER_INACTIVE = "controller_inactive"
    STATE_BROADCASTER_INACTIVE = "state_broadcaster_inactive"
    COMMAND_RECEIVER_UNAVAILABLE = "command_receiver_unavailable"
    STATE_UNAVAILABLE = "state_unavailable"
    STATE_STALE = "state_stale"
    CONTROLLER_REJECTED = "controller_rejected"
    FEEDBACK_TIMEOUT = "feedback_timeout"
    TARGET_NOT_REACHED = "target_not_reached"


class SimulationControlError(Exception):
    """Base class for expected simulation-control failures."""


class ControlValidationError(SimulationControlError, ValueError):
    """Raised when untrusted command or contract data is malformed."""

    def __init__(self, code: ControlFailureCode, message: str) -> None:
        if not isinstance(code, ControlFailureCode):
            raise TypeError("control validation failures require a typed code")
        super().__init__(message)
        self.code = code


class RuntimeControlRejectedError(SimulationControlError):
    """Raised when Runtime Bridge evidence cannot enter the control boundary."""

    def __init__(self, code: ControlFailureCode, message: str) -> None:
        if not isinstance(code, ControlFailureCode):
            raise TypeError("runtime control failures require a typed code")
        super().__init__(message)
        self.code = code
