# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import unittest

from ayyo_simulation_control import (
    ControlFailureCode,
    ControlResultStatus,
    ControllerLifecycle,
    JointStateSample,
    SimulationControlAdapter,
)

from helpers import (
    FakeGateway,
    development_command,
    development_gate,
    limit_catalog,
)


class SimulationControlAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = limit_catalog()

    def adapter(self, gateway: FakeGateway, *, gate=None) -> SimulationControlAdapter:
        return SimulationControlAdapter(
            limits=self.catalog,
            authority=development_gate() if gate is None else gate,
            gateway=gateway,
        )

    def test_valid_command_proves_complete_feedback_chain(self) -> None:
        gateway = FakeGateway()
        control_command = development_command(0.25)
        result = self.adapter(gateway).execute(
            control_command,
            now_ns=1_500_000_000,
        )
        self.assertIs(ControlResultStatus.COMPLETED, result.status)
        self.assertTrue(result.boundary_accepted)
        self.assertTrue(result.controller_dispatched)
        self.assertTrue(result.feedback_observed)
        self.assertTrue(result.state_changed)
        self.assertTrue(result.target_reached)
        self.assertEqual(0.0, result.initial_position)
        self.assertEqual(0.25, result.final_position)
        self.assertEqual(control_command.command_id, gateway.last_command_id)

    def test_limits_reject_before_controller_access(self) -> None:
        gateway = FakeGateway()
        result = self.adapter(gateway).execute(
            development_command(1.3),
            now_ns=1_500_000_000,
        )
        self.assertIs(ControlResultStatus.REJECTED, result.status)
        self.assertIs(ControlFailureCode.ABOVE_MAXIMUM, result.failure.code)
        self.assertEqual(0, gateway.dispatch_calls)

    def test_stale_and_future_commands_fail_before_dispatch(self) -> None:
        cases = (
            (999_999_999, ControlFailureCode.COMMAND_FROM_FUTURE),
            (2_000_000_001, ControlFailureCode.STALE_COMMAND),
        )
        for now_ns, expected in cases:
            with self.subTest(now_ns=now_ns):
                gateway = FakeGateway()
                result = self.adapter(gateway).execute(
                    development_command(),
                    now_ns=now_ns,
                )
                self.assertIs(expected, result.failure.code)
                self.assertEqual(0, gateway.dispatch_calls)

    def test_disabled_or_changed_development_gate_fails_closed(self) -> None:
        cases = (
            development_gate(False),
            development_gate(True).__class__(
                enabled=True,
                source_id="development.simulation.another",
            ),
        )
        for gate in cases:
            with self.subTest(gate=gate):
                gateway = FakeGateway()
                result = self.adapter(gateway, gate=gate).execute(
                    development_command(),
                    now_ns=1_500_000_000,
                )
                self.assertIs(
                    ControlFailureCode.DEVELOPMENT_SESSION_CHANGED,
                    result.failure.code,
                )
                self.assertEqual(0, gateway.dispatch_calls)

    def test_controller_and_hardware_lifecycle_are_explicit(self) -> None:
        cases = (
            (
                "hardware_lifecycle",
                ControllerLifecycle.INACTIVE,
                ControlFailureCode.CONTROL_SYSTEM_INACTIVE,
            ),
            (
                "controller_lifecycle",
                ControllerLifecycle.UNAVAILABLE,
                ControlFailureCode.CONTROLLER_UNAVAILABLE,
            ),
            (
                "controller_lifecycle",
                ControllerLifecycle.INACTIVE,
                ControlFailureCode.CONTROLLER_INACTIVE,
            ),
            (
                "broadcaster_lifecycle",
                ControllerLifecycle.INACTIVE,
                ControlFailureCode.STATE_BROADCASTER_INACTIVE,
            ),
        )
        for attribute, lifecycle, expected in cases:
            with self.subTest(attribute=attribute):
                gateway = FakeGateway()
                setattr(gateway, attribute, lifecycle)
                result = self.adapter(gateway).execute(
                    development_command(),
                    now_ns=1_500_000_000,
                )
                self.assertIs(expected, result.failure.code)
                self.assertEqual(0, gateway.dispatch_calls)

    def test_missing_command_receiver_fails_closed(self) -> None:
        gateway = FakeGateway()
        gateway.command_subscribers = 0
        result = self.adapter(gateway).execute(
            development_command(),
            now_ns=1_500_000_000,
        )
        self.assertIs(
            ControlFailureCode.COMMAND_RECEIVER_UNAVAILABLE,
            result.failure.code,
        )
        self.assertEqual(0, gateway.dispatch_calls)

    def test_missing_and_stale_joint_state_fail_closed(self) -> None:
        gateway = FakeGateway()
        gateway.before = JointStateSample(
            joint_name="head_pitch_joint",
            position=0.0,
            observed_at_ns=1_450_000_000,
            sequence=1,
        )
        missing = self.adapter(gateway).execute(
            development_command(),
            now_ns=1_500_000_000,
        )
        self.assertIs(ControlFailureCode.STATE_UNAVAILABLE, missing.failure.code)

        gateway = FakeGateway()
        gateway.before = JointStateSample(
            joint_name="neck_yaw_joint",
            position=0.0,
            observed_at_ns=900_000_000,
            sequence=1,
        )
        stale = self.adapter(gateway).execute(
            development_command(),
            now_ns=1_500_000_000,
        )
        self.assertIs(ControlFailureCode.STATE_STALE, stale.failure.code)

    def test_controller_rejection_is_not_success(self) -> None:
        gateway = FakeGateway()
        gateway.accept_dispatch = False
        result = self.adapter(gateway).execute(
            development_command(),
            now_ns=1_500_000_000,
        )
        self.assertIs(ControlResultStatus.REJECTED, result.status)
        self.assertIs(ControlFailureCode.CONTROLLER_REJECTED, result.failure.code)
        self.assertTrue(result.boundary_accepted)
        self.assertFalse(result.controller_dispatched)

    def test_feedback_timeout_is_not_success(self) -> None:
        gateway = FakeGateway()
        gateway.dispatch_position = lambda **_: True  # type: ignore[method-assign]
        result = self.adapter(gateway).execute(
            development_command(),
            now_ns=1_500_000_000,
        )
        self.assertIs(ControlFailureCode.FEEDBACK_TIMEOUT, result.failure.code)
        self.assertTrue(result.controller_dispatched)
        self.assertFalse(result.feedback_observed)

    def test_feedback_must_show_change_and_target(self) -> None:
        cases = (0.0, 0.1)
        for observed in cases:
            with self.subTest(observed=observed):
                gateway = FakeGateway()
                gateway.feedback = JointStateSample(
                    joint_name="neck_yaw_joint",
                    position=observed,
                    observed_at_ns=1_600_000_000,
                    sequence=8,
                )
                result = self.adapter(gateway).execute(
                    development_command(0.25),
                    now_ns=1_500_000_000,
                )
                self.assertIs(ControlFailureCode.TARGET_NOT_REACHED, result.failure.code)
                self.assertFalse(result.target_reached)


if __name__ == "__main__":
    unittest.main()
