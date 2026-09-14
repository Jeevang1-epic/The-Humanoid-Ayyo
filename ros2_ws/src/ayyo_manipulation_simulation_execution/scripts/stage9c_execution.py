#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Explicitly run one reviewed Stage 9C trajectory in Gazebo simulation."""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_prefix, get_package_share_directory
from ayyo_manipulation_planning import moveit_collision_proof_from_canonical_json
from ayyo_manipulation_simulation_execution import (
    canonical_simulation_execution_artifact_json,
    create_simulation_execution_goal,
    create_simulation_execution_result,
    DEFAULT_FINAL_TOLERANCE,
    evaluate_simulation_preflight,
    evaluate_whole_body_stability,
    GoalAcceptance,
    moveit_collision_proof_from_canonical_json as stage9c_proof_from_json,
    observed_final_errors,
    preflight_input_document,
    PreflightStatus,
    SimulatedBasePose,
    SimulatedJointState,
    SimulatedWholeBodyState,
    SimulationControllerState,
    SimulationExecutionObservation,
    SimulationExecutionOutcome,
    STAGE9C_ACTION_ENDPOINT,
    STAGE9C_CONTROLLER_NAME,
    STAGE9C_CONTROLLER_TYPE,
    STAGE9C_REVIEWED_CONTROLLER_CONFIGURATION_FINGERPRINT,
    STAGE9C_REVIEWED_SIMULATION_DESCRIPTION_FINGERPRINT,
    STAGE9C_WHOLE_BODY_JOINT_NAMES,
)
from control_msgs.action import FollowJointTrajectory
from controller_manager_msgs.srv import ListControllers, ListHardwareComponents
from nav_msgs.msg import Odometry
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from stage9c_reviewed_fixture import reviewed_execution_request, reviewed_planning_request
from std_msgs.msg import String
from trajectory_msgs.msg import JointTrajectoryPoint


CONTROLLER_MANAGER = '/controller_manager'
STATE_BROADCASTER = 'joint_state_broadcaster'
STATE_BROADCASTER_TYPE = 'joint_state_broadcaster/JointStateBroadcaster'
HARDWARE_SYSTEM = 'AyyoSystem'
DESCRIPTION_FILES = (
    'ayyo.urdf.xacro',
    'ayyo_body.xacro',
    'ayyo_gazebo.xacro',
    'ayyo_geometry.xacro',
    'ayyo_materials.xacro',
    'ayyo_ros2_control.xacro',
)
MAX_WAIT_SECONDS = 10.0


def _wait_future(node: Node, future, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while rclpy.ok() and not future.done() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    return future.done() and not future.cancelled()


def _duration(message, nanoseconds: int) -> None:
    message.sec = nanoseconds // 1_000_000_000
    message.nanosec = nanoseconds % 1_000_000_000


def _goal_message(goal):
    message = FollowJointTrajectory.Goal()
    message.trajectory.joint_names = list(goal.joint_names)
    for item in goal.points:
        point = JointTrajectoryPoint()
        point.positions = list(item.positions)
        _duration(point.time_from_start, round(item.time_from_start * 1_000_000_000))
        message.trajectory.points.append(point)
    return message


def _profile_fingerprints() -> tuple[str, str]:
    description_root = Path(get_package_share_directory('ayyo_description')) / 'urdf'
    description = b''.join(
        name.encode() + b'\0' + (description_root / name).read_bytes() + b'\0'
        for name in DESCRIPTION_FILES
    )
    controller = (
        Path(get_package_share_directory('ayyo_simulation'))
        / 'config/manipulation_controllers.yaml'
    ).read_bytes()
    return (
        'ayyo-stage9c-simulation-description-sha256-'
        + sha256(description).hexdigest(),
        'ayyo-stage9c-controller-configuration-sha256-'
        + sha256(controller).hexdigest(),
    )


def _reviewed_descriptions() -> tuple[str, str, Path]:
    description = Path(get_package_share_directory('ayyo_description'))
    planning = Path(get_package_share_directory('ayyo_manipulation_planning'))
    xacro = description / 'urdf/ayyo.urdf.xacro'
    srdf_path = planning / 'config/ayyo_left_arm.srdf'
    urdf = subprocess.run(
        ['xacro', str(xacro), 'use_meshes:=false', 'simulation_mode:=false'],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    return urdf, srdf_path.read_text(encoding='utf-8'), srdf_path


def _moveit_reports(urdf: str, srdf_path: Path, planning_request):
    stage9a_executable = (
        Path(get_package_prefix('ayyo_manipulation_planning'))
        / 'lib/ayyo_manipulation_planning/moveit_planning_scene_proof'
    )
    stage9a = subprocess.run(
        [str(stage9a_executable), str(srdf_path)],
        input=urdf,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    stage9a_proof = moveit_collision_proof_from_canonical_json(
        planning_request,
        stage9a,
    )
    request = reviewed_execution_request(planning_request, stage9a_proof)
    preflight_payload = json.dumps(
        preflight_input_document(request),
        allow_nan=False,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    )
    stage9c_executable = (
        Path(get_package_prefix('ayyo_manipulation_simulation_execution'))
        / 'lib/ayyo_manipulation_simulation_execution/stage9c_moveit_preflight'
    )
    input_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            prefix='ayyo-stage9c-preflight-',
            suffix='.json',
            delete=False,
        ) as stream:
            stream.write(preflight_payload)
            input_path = Path(stream.name)
        stage9c = subprocess.run(
            [str(stage9c_executable), str(srdf_path), str(input_path)],
            input=urdf,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
    finally:
        if input_path is not None:
            input_path.unlink(missing_ok=True)
    return request, stage9c_proof_from_json(request, stage9c)


class Stage9CClient(Node):
    """Observe one fixed controller/action surface without retries or replanning."""

    def __init__(self) -> None:
        super().__init__(
            'ayyo_stage9c_execution_client',
            parameter_overrides=[Parameter('use_sim_time', value=True)],
        )
        self._state = None
        self._whole_joint_observation = None
        self._base_pose = None
        self._sequence = 0
        self._base_sequence = 0
        self._support_fixture_active = False
        self._feedback_count = 0
        self._feedback_malformed = False
        self._feedback_positions = None
        self.create_subscription(JointState, '/joint_states', self._on_state, 10)
        self.create_subscription(
            Odometry,
            '/ayyo/localization/odometry',
            self._on_base_pose,
            10,
        )
        self.create_subscription(
            String,
            '/robot_description',
            self._on_description,
            QoSProfile(
                depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
                reliability=ReliabilityPolicy.RELIABLE,
            ),
        )
        self._controllers = self.create_client(
            ListControllers,
            f'{CONTROLLER_MANAGER}/list_controllers',
        )
        self._hardware = self.create_client(
            ListHardwareComponents,
            f'{CONTROLLER_MANAGER}/list_hardware_components',
        )
        self._action = ActionClient(
            self,
            FollowJointTrajectory,
            STAGE9C_ACTION_ENDPOINT,
        )

    def _on_state(self, message: JointState) -> None:
        try:
            names = tuple(message.name)
            expected = self._expected_names
            indices = tuple(names.index(name) for name in expected)
            positions = tuple(float(message.position[index]) for index in indices)
            if len(positions) != 4 or not all(isfinite(item) for item in positions):
                return
            stamp = (
                message.header.stamp.sec * 1_000_000_000
                + message.header.stamp.nanosec
            )
            if stamp < 0:
                return
            self._sequence += 1
            self._state = SimulatedJointState(
                joint_names=expected,
                positions=positions,
                observed_at_ns=stamp,
                sequence=self._sequence,
            )
            whole_indices = tuple(
                names.index(name) for name in STAGE9C_WHOLE_BODY_JOINT_NAMES
            )
            whole_positions = tuple(
                float(message.position[index]) for index in whole_indices
            )
            if not all(isfinite(item) for item in whole_positions):
                return
            self._whole_joint_observation = (
                whole_positions,
                stamp,
                self._sequence,
            )
        except (AttributeError, IndexError, TypeError, ValueError):
            return

    def _on_base_pose(self, message: Odometry) -> None:
        try:
            pose = message.pose.pose
            stamp = (
                message.header.stamp.sec * 1_000_000_000
                + message.header.stamp.nanosec
            )
            if stamp < 0:
                return
            self._base_sequence += 1
            self._base_pose = SimulatedBasePose(
                position_xyz=(
                    float(pose.position.x),
                    float(pose.position.y),
                    float(pose.position.z),
                ),
                orientation_xyzw=(
                    float(pose.orientation.x),
                    float(pose.orientation.y),
                    float(pose.orientation.z),
                    float(pose.orientation.w),
                ),
                observed_at_ns=stamp,
                sequence=self._base_sequence,
            )
        except (AttributeError, ArithmeticError, TypeError, ValueError):
            return

    def _on_description(self, message: String) -> None:
        try:
            robot = ET.fromstring(message.data)
            fixture = robot.find("./joint[@name='stage9c_manipulation_fixture_joint']")
            self._support_fixture_active = bool(
                fixture is not None
                and fixture.get('type') == 'fixed'
                and fixture.find('parent') is not None
                and fixture.find('parent').get('link') == 'world'
                and fixture.find('child') is not None
                and fixture.find('child').get('link') == 'base_link'
            )
        except (AttributeError, ET.ParseError, TypeError, ValueError):
            self._support_fixture_active = False

    @property
    def _expected_names(self):
        return (
            'left_shoulder_yaw_joint',
            'left_shoulder_pitch_joint',
            'left_elbow_flex_joint',
            'left_wrist_yaw_joint',
        )

    def wait_for_state(self) -> SimulatedJointState | None:
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            now = self.get_clock().now().nanoseconds
            if (
                self._state is not None
                and 0 <= now - self._state.observed_at_ns <= 250_000_000
            ):
                return self._state
        return None

    def wait_for_support_fixture(self) -> bool:
        """Wait for transient running-description fixture attestation."""
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self._support_fixture_active:
                return True
        return False

    def _current_whole_body_state(self) -> SimulatedWholeBodyState | None:
        if self._whole_joint_observation is None or self._base_pose is None:
            return None
        positions, observed_at_ns, sequence = self._whole_joint_observation
        return SimulatedWholeBodyState(
            joint_names=STAGE9C_WHOLE_BODY_JOINT_NAMES,
            positions=positions,
            observed_at_ns=observed_at_ns,
            sequence=sequence,
            base_pose=self._base_pose,
        )

    def wait_for_whole_body_state(
        self,
        *,
        after_joint_sequence: int = 0,
        after_base_sequence: int = 0,
        target: tuple[float, ...] | None = None,
        timeout_seconds: float = MAX_WAIT_SECONDS,
    ) -> SimulatedWholeBodyState | None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        latest = None
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            state = self._current_whole_body_state()
            now = self.get_clock().now().nanoseconds
            if state is None:
                continue
            latest = state
            fresh = all(
                0 <= now - timestamp <= 250_000_000
                for timestamp in (
                    state.observed_at_ns,
                    state.base_pose.observed_at_ns,
                )
            )
            newer = (
                state.sequence > after_joint_sequence
                and state.base_pose.sequence > after_base_sequence
            )
            target_matched = target is None or all(
                error <= DEFAULT_FINAL_TOLERANCE
                for error in observed_final_errors(
                    state.positions_for(self._expected_names),
                    target,
                )
            )
            if fresh and newer and target_matched:
                return state
        return latest

    def wait_for_final_state(
        self,
        sequence: int,
        target: tuple[float, ...],
        timeout_seconds: float,
    ) -> SimulatedJointState | None:
        """Observe bounded post-result settling without retrying the action."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        latest = None
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if self._state is not None and self._state.sequence > sequence:
                latest = self._state
                errors = observed_final_errors(latest.positions, target)
                if all(error <= DEFAULT_FINAL_TOLERANCE for error in errors):
                    return latest
        return latest

    def controller_state(self, contract) -> SimulationControllerState:
        controller_active = False
        broadcaster_active = False
        hardware_active = False
        claimed = ()
        if self._controllers.wait_for_service(timeout_sec=2.0):
            future = self._controllers.call_async(ListControllers.Request())
            if _wait_future(self, future, 2.0) and future.exception() is None:
                for controller in future.result().controller:
                    if (
                        controller.name == STAGE9C_CONTROLLER_NAME
                        and controller.type == STAGE9C_CONTROLLER_TYPE
                        and controller.state == 'active'
                    ):
                        controller_active = True
                        claimed = tuple(controller.claimed_interfaces)
                    elif (
                        controller.name == STATE_BROADCASTER
                        and controller.type == STATE_BROADCASTER_TYPE
                        and controller.state == 'active'
                    ):
                        broadcaster_active = True
        if self._hardware.wait_for_service(timeout_sec=2.0):
            future = self._hardware.call_async(ListHardwareComponents.Request())
            if _wait_future(self, future, 2.0) and future.exception() is None:
                for component in future.result().component:
                    if component.name != HARDWARE_SYSTEM:
                        continue
                    interfaces = tuple(
                        item.name
                        for item in component.command_interfaces
                        if item.is_available and item.is_claimed
                    )
                    hardware_active = component.state.id == 3 and interfaces == tuple(
                        f'{name}/position' for name in self._expected_names
                    )
        expected_claimed = tuple(f'{name}/position' for name in self._expected_names)
        if claimed != expected_claimed:
            claimed = ()
            controller_active = False
        action_available = self._action.wait_for_server(timeout_sec=2.0)
        now = self.get_clock().now().nanoseconds
        base_pose_observable = bool(
            self._base_pose is not None
            and 0 <= now - self._base_pose.observed_at_ns <= 250_000_000
        )
        return SimulationControllerState(
            controller_contract_id=contract.controller_contract_id,
            controller_contract_fingerprint=contract.controller_contract_fingerprint,
            controller_active=controller_active,
            hardware_active=hardware_active,
            state_broadcaster_active=broadcaster_active,
            action_server_available=action_available,
            support_fixture_active=self._support_fixture_active,
            base_pose_observable=base_pose_observable,
            claimed_command_interfaces=claimed,
            observed_at_ns=max(0, now),
        )

    def _feedback(self, message) -> None:
        try:
            feedback = message.feedback
            if tuple(feedback.joint_names) != self._expected_names:
                raise ValueError('feedback joint order differs')
            positions = tuple(float(item) for item in feedback.actual.positions)
            if len(positions) != 4 or not all(isfinite(item) for item in positions):
                raise ValueError('feedback positions are malformed')
            self._feedback_positions = positions
            self._feedback_count += 1
        except (AttributeError, TypeError, ValueError):
            self._feedback_malformed = True

    def execute(self, goal, initial_whole_body_state):
        message = _goal_message(goal)
        started = max(0, self.get_clock().now().nanoseconds)
        send = self._action.send_goal_async(message, feedback_callback=self._feedback)
        if not _wait_future(self, send, 5.0) or send.exception() is not None:
            return self._observation(
                goal,
                GoalAcceptance.NOT_SENT,
                SimulationExecutionOutcome.CONTROLLER_UNAVAILABLE,
                0,
                started,
                'FollowJointTrajectory action became unavailable before dispatch.',
            )
        handle = send.result()
        if not handle.accepted:
            return self._observation(
                goal,
                GoalAcceptance.REJECTED,
                SimulationExecutionOutcome.GOAL_REJECTED,
                0,
                started,
                'FollowJointTrajectory goal was explicitly rejected.',
            )
        result_future = handle.get_result_async()
        timeout_seconds = goal.execution_timeout_ns / 1_000_000_000
        execution_deadline = time.monotonic() + timeout_seconds
        if not _wait_future(self, result_future, timeout_seconds):
            cancel = handle.cancel_goal_async()
            confirmed = (
                _wait_future(self, cancel, 3.0)
                and cancel.exception() is None
                and bool(cancel.result().goals_canceling)
            )
            return self._observation(
                goal,
                GoalAcceptance.ACCEPTED,
                SimulationExecutionOutcome.TIMED_OUT,
                0,
                started,
                'Execution deadline expired; cancellation was requested.',
                cancellation_requested=True,
                cancellation_confirmed=confirmed,
                timed_out=True,
            )
        if result_future.exception() is not None:
            return self._observation(
                goal,
                GoalAcceptance.ACCEPTED,
                SimulationExecutionOutcome.SIMULATOR_SHUTDOWN,
                0,
                started,
                'Simulation action terminated without a result.',
            )
        wrapped = result_future.result()
        code = int(wrapped.result.error_code)
        result_sequence = self._sequence
        result_base_sequence = self._base_sequence
        final_whole_body_state = self.wait_for_whole_body_state(
            after_joint_sequence=result_sequence,
            after_base_sequence=result_base_sequence,
            target=goal.points[-1].positions,
            timeout_seconds=execution_deadline - time.monotonic(),
        )
        stability = None
        if final_whole_body_state is not None:
            self._feedback_positions = final_whole_body_state.positions_for(
                self._expected_names
            )
            post_controller = self.controller_state(
                goal.preflight_evidence.execution_request.controller_contract
            )
            evaluated_at = max(0, self.get_clock().now().nanoseconds)
            stability = evaluate_whole_body_stability(
                initial_whole_body_state,
                final_whole_body_state,
                post_controller,
                evaluated_at_ns=evaluated_at,
            )
        if self._feedback_malformed:
            outcome = SimulationExecutionOutcome.MALFORMED_FEEDBACK
        elif wrapped.status == GoalStatus.STATUS_CANCELED:
            outcome = SimulationExecutionOutcome.ABORTED
        elif code == FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED:
            outcome = SimulationExecutionOutcome.PATH_TOLERANCE_VIOLATED
        elif code == FollowJointTrajectory.Result.GOAL_TOLERANCE_VIOLATED:
            outcome = SimulationExecutionOutcome.GOAL_TOLERANCE_VIOLATED
        elif (
            wrapped.status == GoalStatus.STATUS_SUCCEEDED
            and code == FollowJointTrajectory.Result.SUCCESSFUL
            and self._feedback_positions is not None
            and stability is not None
            and stability.stable
            and all(
                error <= DEFAULT_FINAL_TOLERANCE
                for error in observed_final_errors(
                    self._feedback_positions,
                    goal.points[-1].positions,
                )
            )
        ):
            outcome = SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
        elif (
            wrapped.status == GoalStatus.STATUS_SUCCEEDED
            and code == FollowJointTrajectory.Result.SUCCESSFUL
            and stability is not None
            and not stability.stable
        ):
            outcome = SimulationExecutionOutcome.WHOLE_BODY_STABILITY_VIOLATED
        elif (
            wrapped.status == GoalStatus.STATUS_SUCCEEDED
            and code == FollowJointTrajectory.Result.SUCCESSFUL
        ):
            outcome = SimulationExecutionOutcome.GOAL_TOLERANCE_VIOLATED
        else:
            outcome = SimulationExecutionOutcome.ABORTED
        return self._observation(
            goal,
            GoalAcceptance.ACCEPTED,
            outcome,
            code,
            started,
            'Observed bounded action result, fresh whole-body state, and post-controller state.',
            stability_observation=stability,
        )

    def _observation(
        self,
        goal,
        acceptance,
        outcome,
        error_code,
        started,
        detail,
        *,
        cancellation_requested=False,
        cancellation_confirmed=False,
        timed_out=False,
        stability_observation=None,
    ):
        ending = self._feedback_positions
        target = goal.points[-1].positions
        return SimulationExecutionObservation(
            execution_goal_id=goal.execution_goal_id,
            execution_goal_fingerprint=goal.execution_goal_fingerprint,
            acceptance=acceptance,
            outcome=outcome,
            controller_error_code=error_code,
            started_at_ns=started,
            completed_at_ns=(
                max(started, self.get_clock().now().nanoseconds)
                if stability_observation is None
                else stability_observation.evaluated_at_ns
            ),
            starting_positions=goal.preflight_evidence.start_state.positions,
            ending_positions=ending,
            final_target_positions=target,
            final_joint_errors=(
                None if ending is None else observed_final_errors(ending, target)
            ),
            feedback_samples_observed=self._feedback_count,
            cancellation_requested=cancellation_requested,
            cancellation_confirmed=cancellation_confirmed,
            timed_out=timed_out,
            detail=detail,
            stability_observation=stability_observation,
        )


def main() -> int:
    try:
        profile = _profile_fingerprints()
        if profile != (
            STAGE9C_REVIEWED_SIMULATION_DESCRIPTION_FINGERPRINT,
            STAGE9C_REVIEWED_CONTROLLER_CONFIGURATION_FINGERPRINT,
        ):
            print('FAIL: installed Stage 9C simulation profile is not reviewed', file=sys.stderr)
            return 2
        urdf, srdf, srdf_path = _reviewed_descriptions()
        planning_request = reviewed_planning_request(urdf, srdf)
        request, collision_proof = _moveit_reports(
            urdf,
            srdf_path,
            planning_request,
        )
        rclpy.init()
        node = Stage9CClient()
        try:
            if node.wait_for_whole_body_state() is None:
                print(
                    'FAIL: fresh simulated whole-body/base state is unavailable',
                    file=sys.stderr,
                )
                return 2
            if not node.wait_for_support_fixture():
                print(
                    'FAIL: running Stage 9C support fixture is not attested',
                    file=sys.stderr,
                )
                return 2
            controller = node.controller_state(request.controller_contract)
            initial_whole_body_state = node.wait_for_whole_body_state()
            if initial_whole_body_state is None:
                print('FAIL: fresh simulated support state expired', file=sys.stderr)
                return 2
            start = SimulatedJointState(
                joint_names=node._expected_names,
                positions=initial_whole_body_state.positions_for(node._expected_names),
                observed_at_ns=initial_whole_body_state.observed_at_ns,
                sequence=initial_whole_body_state.sequence,
            )
            evaluated_at = max(0, node.get_clock().now().nanoseconds)
            preflight = evaluate_simulation_preflight(
                collision_proof,
                start,
                controller,
                evaluated_at_ns=evaluated_at,
            )
            if preflight.status is not PreflightStatus.READY_FOR_SIMULATION_EXECUTION:
                print(canonical_simulation_execution_artifact_json(preflight))
                return 2
            goal = create_simulation_execution_goal(preflight)
            observation = node.execute(goal, initial_whole_body_state)
            result = create_simulation_execution_result(goal, observation)
            print(canonical_simulation_execution_artifact_json(result))
            if observation.outcome is not (
                SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
            ):
                stability_reasons = (
                    None
                    if observation.stability_observation is None
                    else [
                        reason.value
                        for reason in observation.stability_observation.reasons
                    ]
                )
                print(
                    'FAIL: observed action outcome '
                    f'{observation.outcome.value}; final errors '
                    f'{observation.final_joint_errors}; stability '
                    f'{stability_reasons}',
                    file=sys.stderr,
                )
            return (
                0
                if observation.outcome
                is SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
                else 2
            )
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f'FAIL: Stage 9C execution rejected: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
