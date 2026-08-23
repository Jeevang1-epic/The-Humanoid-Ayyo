"""Fail-closed controller adapter with dispatch-time revalidation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .errors import ControlFailureCode, ControlValidationError
from .limits import UrdfJointLimitCatalog
from .models import (
    ControlAuthorityKind,
    ControllerLifecycle,
    ControllerSnapshot,
    ControlFailure,
    ControlResultStatus,
    JointStateSample,
    SimulationControlCommand,
    SimulationControlResult,
    rebuild_command,
)


POSITION_CONTROLLER_NAME = "ayyo_neck_position_controller"
MAX_CONTROLLER_SNAPSHOT_AGE_NS = 1_000_000_000
MAX_JOINT_STATE_AGE_NS = 500_000_000
DEFAULT_FEEDBACK_TIMEOUT_NS = 2_000_000_000
DEFAULT_POSITION_TOLERANCE = 0.01
MINIMUM_OBSERVABLE_CHANGE = 0.001


@runtime_checkable
class AuthorityRevalidator(Protocol):
    def is_current(self, command: SimulationControlCommand) -> bool:
        ...


@runtime_checkable
class PositionControllerGateway(Protocol):
    def simulation_time_ns(self) -> int:
        ...

    def snapshot(self, joint_name: str) -> ControllerSnapshot:
        ...

    def dispatch_position(
        self,
        *,
        joint_name: str,
        position: float,
        command_id: str,
    ) -> bool:
        ...

    def wait_for_feedback(
        self,
        *,
        joint_name: str,
        after_sequence: int,
        target_position: float,
        tolerance: float,
        timeout_ns: int,
    ) -> JointStateSample | None:
        ...


@dataclass(frozen=True, slots=True)
class DevelopmentAuthorityGate:
    enabled: bool
    source_id: str = "development.simulation.control.v1"

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "development authority state must be explicit",
            )
        # Reuse the public authority constructor for identifier validation.
        from .models import ControlAuthority

        ControlAuthority(
            kind=ControlAuthorityKind.DEVELOPMENT_TEST,
            source_id=self.source_id,
        )

    def is_current(self, command: SimulationControlCommand) -> bool:
        command = rebuild_command(command)
        return (
            self.enabled
            and command.authority.kind is ControlAuthorityKind.DEVELOPMENT_TEST
            and command.authority.source_id == self.source_id
        )


def _rejected(
    command: SimulationControlCommand,
    failure: ControlFailure,
    *,
    boundary_accepted: bool = False,
    controller_dispatched: bool = False,
    feedback_observed: bool = False,
    state_changed: bool = False,
    initial_position: float | None = None,
    final_position: float | None = None,
    observed_at_ns: int | None = None,
) -> SimulationControlResult:
    return SimulationControlResult(
        status=ControlResultStatus.REJECTED,
        command=command,
        failure=failure,
        boundary_accepted=boundary_accepted,
        controller_dispatched=controller_dispatched,
        feedback_observed=feedback_observed,
        state_changed=state_changed,
        target_reached=False,
        initial_position=initial_position,
        final_position=final_position,
        observed_at_ns=observed_at_ns,
    )


def _failure(
    command: SimulationControlCommand,
    code: ControlFailureCode,
    detail: str,
) -> ControlFailure:
    return ControlFailure(code=code, detail=detail, command=command)


@dataclass(frozen=True, slots=True)
class SimulationControlAdapter:
    limits: UrdfJointLimitCatalog
    authority: AuthorityRevalidator
    gateway: PositionControllerGateway
    feedback_timeout_ns: int = DEFAULT_FEEDBACK_TIMEOUT_NS
    position_tolerance: float = DEFAULT_POSITION_TOLERANCE

    def __post_init__(self) -> None:
        if type(self.limits) is not UrdfJointLimitCatalog:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "adapter requires an authoritative URDF limit catalog",
            )
        if not isinstance(self.authority, AuthorityRevalidator):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "adapter requires an authority revalidator",
            )
        if not isinstance(self.gateway, PositionControllerGateway):
            raise ControlValidationError(
                ControlFailureCode.CONTROLLER_UNAVAILABLE,
                "adapter requires a typed position-controller gateway",
            )
        if (
            type(self.feedback_timeout_ns) is not int
            or not 1 <= self.feedback_timeout_ns <= 5_000_000_000
        ):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "feedback timeout is outside the bounded control range",
            )
        if (
            type(self.position_tolerance) not in {int, float}
            or not 0.0 < self.position_tolerance <= 0.1
        ):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "position tolerance is outside the bounded control range",
            )

    def execute(
        self,
        command: SimulationControlCommand,
        *,
        now_ns: int,
    ) -> SimulationControlResult:
        command = rebuild_command(command)
        if type(now_ns) is not int or now_ns < 0:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control evaluation requires simulation time in nanoseconds",
            )
        limit_failure = self.limits.validate(command)
        if limit_failure is not None:
            return _rejected(command, limit_failure)
        if now_ns < command.issued_at_ns:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.COMMAND_FROM_FUTURE,
                    "Command issuance is ahead of the current simulation clock.",
                ),
            )
        if now_ns > command.expires_at_ns:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.STALE_COMMAND,
                    "Command expired before entering the controller boundary.",
                ),
            )
        if not self.authority.is_current(command):
            code = (
                ControlFailureCode.DEVELOPMENT_SESSION_CHANGED
                if command.authority.kind is ControlAuthorityKind.DEVELOPMENT_TEST
                else ControlFailureCode.STALE_RUNTIME_BINDING
            )
            return _rejected(
                command,
                _failure(command, code, "Command authority is no longer current."),
            )

        target = command.targets[0]
        snapshot = self.gateway.snapshot(target.joint_name)
        if type(snapshot) is not ControllerSnapshot:
            raise ControlValidationError(
                ControlFailureCode.CONTROLLER_UNAVAILABLE,
                "controller gateway returned an invalid snapshot",
            )
        if snapshot.controller_name != POSITION_CONTROLLER_NAME:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.CONTROLLER_UNAVAILABLE,
                    "The gateway snapshot names an unreviewed controller.",
                ),
            )
        dispatch_now_ns = self.gateway.simulation_time_ns()
        if type(dispatch_now_ns) is not int or dispatch_now_ns < 0:
            raise ControlValidationError(
                ControlFailureCode.CONTROLLER_UNAVAILABLE,
                "controller gateway returned invalid simulation time",
            )
        if dispatch_now_ns < command.issued_at_ns:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.COMMAND_FROM_FUTURE,
                    "Command issuance is ahead of the dispatch simulation clock.",
                ),
            )
        if dispatch_now_ns > command.expires_at_ns:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.STALE_COMMAND,
                    "Command expired before controller dispatch.",
                ),
            )
        if snapshot.observed_at_ns > dispatch_now_ns or (
            dispatch_now_ns - snapshot.observed_at_ns
            > MAX_CONTROLLER_SNAPSHOT_AGE_NS
        ):
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.CONTROLLER_UNAVAILABLE,
                    "Controller lifecycle evidence is stale or from the future.",
                ),
            )
        if snapshot.hardware_lifecycle is not ControllerLifecycle.ACTIVE:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.CONTROL_SYSTEM_INACTIVE,
                    "The gz_ros2_control hardware system is not active.",
                ),
            )
        if snapshot.controller_lifecycle is ControllerLifecycle.UNAVAILABLE:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.CONTROLLER_UNAVAILABLE,
                    "The reviewed position controller is unavailable.",
                ),
            )
        if snapshot.controller_lifecycle is not ControllerLifecycle.ACTIVE:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.CONTROLLER_INACTIVE,
                    "The reviewed position controller is not active.",
                ),
            )
        if snapshot.broadcaster_lifecycle is not ControllerLifecycle.ACTIVE:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.STATE_BROADCASTER_INACTIVE,
                    "The authoritative joint-state broadcaster is not active.",
                ),
            )
        if snapshot.command_subscribers < 1:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.COMMAND_RECEIVER_UNAVAILABLE,
                    "The reviewed controller has no command subscription.",
                ),
            )
        before = snapshot.joint_state
        if before is None or before.joint_name != target.joint_name:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.STATE_UNAVAILABLE,
                    "Authoritative state for the requested joint is unavailable.",
                ),
            )
        if before.observed_at_ns > dispatch_now_ns or (
            dispatch_now_ns - before.observed_at_ns > MAX_JOINT_STATE_AGE_NS
        ):
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.STATE_STALE,
                    "Authoritative joint state is stale or from the future.",
                ),
            )

        # Revalidate both time and authority immediately before the controller call.
        if not self.authority.is_current(command):
            code = (
                ControlFailureCode.DEVELOPMENT_SESSION_CHANGED
                if command.authority.kind is ControlAuthorityKind.DEVELOPMENT_TEST
                else ControlFailureCode.STALE_RUNTIME_BINDING
            )
            return _rejected(
                command,
                _failure(
                    command,
                    code,
                    "Command authority changed before controller dispatch.",
                ),
                boundary_accepted=True,
                initial_position=before.position,
            )
        accepted = self.gateway.dispatch_position(
            joint_name=target.joint_name,
            position=target.position,
            command_id=command.command_id,
        )
        if accepted is not True:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.CONTROLLER_REJECTED,
                    "The typed controller gateway rejected the command.",
                ),
                boundary_accepted=True,
                initial_position=before.position,
            )
        feedback = self.gateway.wait_for_feedback(
            joint_name=target.joint_name,
            after_sequence=before.sequence,
            target_position=target.position,
            tolerance=float(self.position_tolerance),
            timeout_ns=self.feedback_timeout_ns,
        )
        if feedback is None:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.FEEDBACK_TIMEOUT,
                    "No correlated post-dispatch joint feedback arrived in time.",
                ),
                boundary_accepted=True,
                controller_dispatched=True,
                initial_position=before.position,
            )
        if type(feedback) is not JointStateSample or (
            feedback.joint_name != target.joint_name
            or feedback.sequence <= before.sequence
        ):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "controller gateway returned uncorrelated joint feedback",
            )
        feedback_now_ns = self.gateway.simulation_time_ns()
        if type(feedback_now_ns) is not int or feedback_now_ns < 0:
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "controller gateway returned invalid feedback simulation time",
            )
        if not dispatch_now_ns <= feedback.observed_at_ns <= feedback_now_ns:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.STATE_STALE,
                    "Post-dispatch feedback has incompatible simulation time.",
                ),
                boundary_accepted=True,
                controller_dispatched=True,
                initial_position=before.position,
            )
        state_changed = abs(feedback.position - before.position) >= MINIMUM_OBSERVABLE_CHANGE
        target_reached = abs(feedback.position - target.position) <= self.position_tolerance
        if not state_changed or not target_reached:
            return _rejected(
                command,
                _failure(
                    command,
                    ControlFailureCode.TARGET_NOT_REACHED,
                    "Post-dispatch state did not prove the requested bounded motion.",
                ),
                boundary_accepted=True,
                controller_dispatched=True,
                feedback_observed=True,
                state_changed=state_changed,
                initial_position=before.position,
                final_position=feedback.position,
                observed_at_ns=feedback.observed_at_ns,
            )
        return SimulationControlResult(
            status=ControlResultStatus.COMPLETED,
            command=command,
            failure=None,
            boundary_accepted=True,
            controller_dispatched=True,
            feedback_observed=True,
            state_changed=True,
            target_reached=True,
            initial_position=before.position,
            final_position=feedback.position,
            observed_at_ns=feedback.observed_at_ns,
        )
