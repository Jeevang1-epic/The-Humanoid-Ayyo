# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

from ayyo_simulation_control import (
    ControlAuthority,
    ControlAuthorityKind,
    ControlCommandType,
    ControllerLifecycle,
    ControllerSnapshot,
    DevelopmentAuthorityGate,
    JointPositionTarget,
    JointStateSample,
    SimulationControlCommand,
    UrdfJointLimitCatalog,
)


def robot_description() -> str:
    return """<?xml version="1.0"?>
<robot name="ayyo-test-contract">
  <joint name="base_to_pelvis_joint" type="fixed"/>
  <joint name="neck_yaw_joint" type="revolute">
    <limit lower="-1.2" upper="1.2" effort="8.0" velocity="1.5"/>
  </joint>
  <joint name="head_pitch_joint" type="revolute">
    <limit lower="-0.6" upper="0.6" effort="8.0" velocity="1.2"/>
  </joint>
</robot>
"""


def limit_catalog() -> UrdfJointLimitCatalog:
    return UrdfJointLimitCatalog(robot_description())


def development_command(
    position: float = 0.25,
    *,
    joint_name: str = "neck_yaw_joint",
    issued_at_ns: int = 1_000_000_000,
    expires_at_ns: int = 2_000_000_000,
    source_id: str = "development.simulation.control.v1",
) -> SimulationControlCommand:
    return SimulationControlCommand(
        command_type=ControlCommandType.SET_JOINT_POSITIONS,
        targets=(JointPositionTarget(joint_name, position),),
        issued_at_ns=issued_at_ns,
        expires_at_ns=expires_at_ns,
        authority=ControlAuthority(
            kind=ControlAuthorityKind.DEVELOPMENT_TEST,
            source_id=source_id,
        ),
    )


class FakeGateway:
    def __init__(self) -> None:
        self.controller_lifecycle = ControllerLifecycle.ACTIVE
        self.broadcaster_lifecycle = ControllerLifecycle.ACTIVE
        self.hardware_lifecycle = ControllerLifecycle.ACTIVE
        self.command_subscribers = 1
        self.snapshot_observed_at_ns = 1_450_000_000
        self.simulation_times = [1_500_000_000, 1_650_000_000]
        self.before = JointStateSample(
            joint_name="neck_yaw_joint",
            position=0.0,
            observed_at_ns=1_450_000_000,
            sequence=7,
        )
        self.accept_dispatch = True
        self.feedback: JointStateSample | None = None
        self.dispatch_calls = 0
        self.wait_calls = 0
        self.last_command_id: str | None = None

    def simulation_time_ns(self) -> int:
        if len(self.simulation_times) > 1:
            return self.simulation_times.pop(0)
        return self.simulation_times[0]

    def snapshot(self, joint_name: str) -> ControllerSnapshot:
        state = self.before if self.before.joint_name == joint_name else None
        return ControllerSnapshot(
            controller_name="ayyo_neck_position_controller",
            controller_lifecycle=self.controller_lifecycle,
            broadcaster_lifecycle=self.broadcaster_lifecycle,
            hardware_lifecycle=self.hardware_lifecycle,
            command_subscribers=self.command_subscribers,
            observed_at_ns=self.snapshot_observed_at_ns,
            joint_state=state,
        )

    def dispatch_position(
        self,
        *,
        joint_name: str,
        position: float,
        command_id: str,
    ) -> bool:
        self.dispatch_calls += 1
        self.last_command_id = command_id
        if self.feedback is None:
            self.feedback = JointStateSample(
                joint_name=joint_name,
                position=position,
                observed_at_ns=1_600_000_000,
                sequence=self.before.sequence + 1,
            )
        return self.accept_dispatch

    def wait_for_feedback(
        self,
        *,
        joint_name: str,
        after_sequence: int,
        target_position: float,
        tolerance: float,
        timeout_ns: int,
    ) -> JointStateSample | None:
        self.wait_calls += 1
        return self.feedback


def development_gate(enabled: bool = True) -> DevelopmentAuthorityGate:
    return DevelopmentAuthorityGate(enabled=enabled)
