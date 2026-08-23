# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
import unittest

from ayyo_simulation_control import (
    ControlAuthority,
    ControlAuthorityKind,
    ControlCommandType,
    ControlFailure,
    ControlFailureCode,
    ControlResultStatus,
    ControlValidationError,
    JointPositionTarget,
    SimulationControlCommand,
    SimulationControlResult,
    rebuild_command,
)


def development_authority() -> ControlAuthority:
    return ControlAuthority(
        kind=ControlAuthorityKind.DEVELOPMENT_TEST,
        source_id="development.control.test",
    )


def command(position: float = 0.25) -> SimulationControlCommand:
    return SimulationControlCommand(
        command_type=ControlCommandType.SET_JOINT_POSITIONS,
        targets=(JointPositionTarget("neck_yaw_joint", position),),
        issued_at_ns=1_000_000_000,
        expires_at_ns=2_000_000_000,
        authority=development_authority(),
    )


class SimulationControlModelTests(unittest.TestCase):
    def test_command_identity_is_deterministic(self) -> None:
        first = command()
        second = command()
        self.assertEqual(first, second)
        self.assertEqual(first.command_id, second.command_id)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(
            first.command_id,
            f"control-command-{first.fingerprint.digest}",
        )

    def test_command_is_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            command().issued_at_ns = 0  # type: ignore[misc]

    def test_target_order_is_canonical(self) -> None:
        authority = development_authority()
        forward = SimulationControlCommand(
            command_type=ControlCommandType.SET_JOINT_POSITIONS,
            targets=(
                JointPositionTarget("neck_yaw_joint", 0.1),
                JointPositionTarget("head_pitch_joint", 0.2),
            ),
            issued_at_ns=1,
            expires_at_ns=2,
            authority=authority,
        )
        reverse = SimulationControlCommand(
            command_type=ControlCommandType.SET_JOINT_POSITIONS,
            targets=tuple(reversed(forward.targets)),
            issued_at_ns=1,
            expires_at_ns=2,
            authority=authority,
        )
        self.assertEqual(forward, reverse)

    def test_duplicate_target_is_rejected(self) -> None:
        with self.assertRaises(ControlValidationError) as raised:
            SimulationControlCommand(
                command_type=ControlCommandType.SET_JOINT_POSITIONS,
                targets=(
                    JointPositionTarget("neck_yaw_joint", 0.1),
                    JointPositionTarget("neck_yaw_joint", 0.2),
                ),
                issued_at_ns=1,
                expires_at_ns=2,
                authority=development_authority(),
            )
        self.assertIs(ControlFailureCode.DUPLICATE_TARGET, raised.exception.code)

    def test_non_finite_and_malformed_numeric_targets_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf, True, "0.2", None):
            with self.subTest(value=value):
                with self.assertRaises(ControlValidationError) as raised:
                    JointPositionTarget("neck_yaw_joint", value)  # type: ignore[arg-type]
                self.assertIs(
                    ControlFailureCode.MALFORMED_COMMAND,
                    raised.exception.code,
                )

    def test_command_window_uses_bounded_simulation_nanoseconds(self) -> None:
        cases = ((-1, 1), (1, 1), (2, 1), (0, 5_000_000_001))
        for issued_at_ns, expires_at_ns in cases:
            with self.subTest(issued=issued_at_ns, expires=expires_at_ns):
                with self.assertRaises(ControlValidationError):
                    SimulationControlCommand(
                        command_type=ControlCommandType.SET_JOINT_POSITIONS,
                        targets=(JointPositionTarget("neck_yaw_joint", 0.0),),
                        issued_at_ns=issued_at_ns,
                        expires_at_ns=expires_at_ns,
                        authority=development_authority(),
                    )

    def test_unsupported_command_type_is_rejected(self) -> None:
        with self.assertRaises(ControlValidationError) as raised:
            SimulationControlCommand(
                command_type="position",  # type: ignore[arg-type]
                targets=(JointPositionTarget("neck_yaw_joint", 0.0),),
                issued_at_ns=1,
                expires_at_ns=2,
                authority=development_authority(),
            )
        self.assertIs(
            ControlFailureCode.UNSUPPORTED_COMMAND_TYPE,
            raised.exception.code,
        )

    def test_development_authority_cannot_claim_runtime_identity(self) -> None:
        with self.assertRaises(ControlValidationError) as raised:
            ControlAuthority(
                kind=ControlAuthorityKind.DEVELOPMENT_TEST,
                source_id="development.control.test",
                runtime_request_id="runtime-request-" + "a" * 64,
            )
        self.assertIs(
            ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
            raised.exception.code,
        )

    def test_runtime_authority_requires_complete_matching_identity(self) -> None:
        digest = "a" * 64
        authority = ControlAuthority(
            kind=ControlAuthorityKind.RUNTIME_ELIGIBLE,
            source_id="runtime.bridge",
            runtime_request_id=f"runtime-request-{digest}",
            runtime_request_fingerprint=f"request:sha256:{digest}",
            invocation_fingerprint=f"invocation:sha256:{'b' * 64}",
            endpoint_binding_fingerprint=f"endpoint_binding:sha256:{'c' * 64}",
            runtime_registry_fingerprint=f"registry:sha256:{'d' * 64}",
        )
        self.assertIs(ControlAuthorityKind.RUNTIME_ELIGIBLE, authority.kind)
        with self.assertRaises(ControlValidationError):
            ControlAuthority(
                kind=ControlAuthorityKind.RUNTIME_ELIGIBLE,
                source_id="runtime.bridge",
                runtime_request_id=f"runtime-request-{digest}",
                runtime_request_fingerprint=f"request:sha256:{'e' * 64}",
                invocation_fingerprint=f"invocation:sha256:{'b' * 64}",
                endpoint_binding_fingerprint=(
                    f"endpoint_binding:sha256:{'c' * 64}"
                ),
                runtime_registry_fingerprint=f"registry:sha256:{'d' * 64}",
            )

    def test_rebuild_detects_tampered_command_identity(self) -> None:
        control_command = command()
        object.__setattr__(control_command, "command_id", "tampered")
        with self.assertRaisesRegex(ControlValidationError, "identity is stale"):
            rebuild_command(control_command)

    def test_failure_identity_is_deterministic(self) -> None:
        first = ControlFailure(
            code=ControlFailureCode.STALE_COMMAND,
            detail="The command expired in simulation time.",
            command=command(),
        )
        second = ControlFailure(
            code=ControlFailureCode.STALE_COMMAND,
            detail="The command expired in simulation time.",
            command=command(),
        )
        self.assertEqual(first, second)
        self.assertEqual(first.failure_id, f"control-failure-{first.fingerprint.digest}")

    def test_completed_result_requires_full_feedback_chain(self) -> None:
        completed = SimulationControlResult(
            status=ControlResultStatus.COMPLETED,
            command=command(),
            failure=None,
            boundary_accepted=True,
            controller_dispatched=True,
            feedback_observed=True,
            state_changed=True,
            target_reached=True,
            initial_position=0.0,
            final_position=0.25,
            observed_at_ns=1_500_000_000,
        )
        self.assertEqual(
            completed.result_id,
            f"control-result-{completed.fingerprint.digest}",
        )
        with self.assertRaises(ControlValidationError):
            SimulationControlResult(
                status=ControlResultStatus.COMPLETED,
                command=command(),
                failure=None,
                boundary_accepted=True,
                controller_dispatched=True,
                feedback_observed=False,
                state_changed=False,
                target_reached=False,
                initial_position=0.0,
                final_position=None,
                observed_at_ns=None,
            )

    def test_rejected_result_retains_typed_failure(self) -> None:
        control_command = command()
        failure = ControlFailure(
            code=ControlFailureCode.CONTROLLER_INACTIVE,
            detail="The reviewed position controller is not active.",
            command=control_command,
        )
        result = SimulationControlResult(
            status=ControlResultStatus.REJECTED,
            command=control_command,
            failure=failure,
            boundary_accepted=True,
            controller_dispatched=False,
            feedback_observed=False,
            state_changed=False,
            target_reached=False,
            initial_position=None,
            final_position=None,
            observed_at_ns=None,
        )
        self.assertIs(ControlFailureCode.CONTROLLER_INACTIVE, result.failure.code)


if __name__ == "__main__":
    unittest.main()
