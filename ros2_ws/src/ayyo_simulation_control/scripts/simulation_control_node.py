#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Development-only typed ROS adapter for the Ayyo position controller."""

from __future__ import annotations

from threading import Condition, RLock
import time

from ayyo_interfaces.srv import SetDevelopmentJointPosition
from ayyo_simulation_control import (
    ControlAuthority,
    ControlAuthorityKind,
    ControlCommandType,
    ControlFailure,
    ControlFailureCode,
    ControllerLifecycle,
    ControllerSnapshot,
    ControlResultStatus,
    ControlValidationError,
    DevelopmentAuthorityGate,
    JointPositionTarget,
    JointStateSample,
    SimulationControlAdapter,
    SimulationControlCommand,
    UrdfJointLimitCatalog,
)
from controller_manager_msgs.srv import ListControllers, ListHardwareComponents
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray


CONTROLLER_MANAGER = '/controller_manager'
POSITION_CONTROLLER = 'ayyo_neck_position_controller'
POSITION_CONTROLLER_TYPE = 'forward_command_controller/ForwardCommandController'
STATE_BROADCASTER = 'joint_state_broadcaster'
STATE_BROADCASTER_TYPE = 'joint_state_broadcaster/JointStateBroadcaster'
HARDWARE_SYSTEM = 'AyyoSystem'
COMMAND_INTERFACE = 'neck_yaw_joint/position'
COMMAND_TOPIC = f'/{POSITION_CONTROLLER}/commands'
SERVICE_NAME = '/ayyo/development/set_joint_position'
LIFECYCLE_QUERY_TIMEOUT_SECONDS = 0.5


def _nanoseconds(seconds: int, nanoseconds: int) -> int:
    if type(seconds) is not int or type(nanoseconds) is not int:
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            'ROS time fields must be integers',
        )
    if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            'ROS time fields are outside their canonical range',
        )
    return seconds * 1_000_000_000 + nanoseconds


def _assign_time(message, value_ns: int) -> None:
    message.sec = value_ns // 1_000_000_000
    message.nanosec = value_ns % 1_000_000_000


class DrainingMultiThreadedExecutor(MultiThreadedExecutor):
    """Drain Jazzy worker tasks before its guard condition is destroyed."""

    def shutdown(self, timeout_sec: float | None = None) -> bool:
        self._executor.shutdown(wait=True)
        for future in tuple(self._futures):
            if not future.cancelled():
                future.result()
        self._futures.clear()
        return super().shutdown(timeout_sec=timeout_sec)


class RosPositionControllerGateway:
    """Map one reviewed controller topic and state surface to the core port."""

    def __init__(self, node: Node, callback_group: ReentrantCallbackGroup) -> None:
        self._node = node
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._controller_lifecycle = ControllerLifecycle.UNAVAILABLE
        self._broadcaster_lifecycle = ControllerLifecycle.UNAVAILABLE
        self._hardware_lifecycle = ControllerLifecycle.UNAVAILABLE
        self._lifecycle_observed_at_ns = 0
        self._joint_state: JointStateSample | None = None
        self._sequence = 0
        self._controller_future = None
        self._hardware_future = None
        self._closing = False
        self._publisher = node.create_publisher(
            Float64MultiArray,
            COMMAND_TOPIC,
            1,
        )
        node.create_subscription(
            JointState,
            '/joint_states',
            self._on_joint_state,
            10,
            callback_group=callback_group,
        )
        self._controller_client = node.create_client(
            ListControllers,
            f'{CONTROLLER_MANAGER}/list_controllers',
            callback_group=callback_group,
        )
        self._hardware_client = node.create_client(
            ListHardwareComponents,
            f'{CONTROLLER_MANAGER}/list_hardware_components',
            callback_group=callback_group,
        )

    def close(self) -> None:
        """Settle any command-scoped lifecycle service futures."""
        with self._condition:
            if self._closing:
                return
            self._closing = True
            pending = (
                (self._controller_future, self._on_controllers),
                (self._hardware_future, self._on_hardware),
            )
            self._controller_future = None
            self._hardware_future = None
            self._condition.notify_all()
        for future, callback in pending:
            if future is None:
                continue
            future.remove_done_callback(callback)
            if future.done() and not future.cancelled():
                future.exception()
            elif not future.done():
                future.cancel()

    def _now_ns(self) -> int:
        return self._node.get_clock().now().nanoseconds

    def _on_joint_state(self, message: JointState) -> None:
        try:
            index = list(message.name).index('neck_yaw_joint')
            position = message.position[index]
            observed_at_ns = _nanoseconds(
                message.header.stamp.sec,
                message.header.stamp.nanosec,
            )
            with self._condition:
                self._sequence += 1
                self._joint_state = JointStateSample(
                    joint_name='neck_yaw_joint',
                    position=position,
                    observed_at_ns=observed_at_ns,
                    sequence=self._sequence,
                )
                self._condition.notify_all()
        except (ControlValidationError, IndexError, ValueError):
            return

    def _refresh_lifecycle(self) -> None:
        deadline = time.monotonic() + LIFECYCLE_QUERY_TIMEOUT_SECONDS
        with self._condition:
            if self._closing:
                return
            if not (
                self._controller_client.service_is_ready()
                and self._hardware_client.service_is_ready()
            ):
                return
            if self._controller_future is None:
                self._controller_future = self._controller_client.call_async(
                    ListControllers.Request()
                )
                self._controller_future.add_done_callback(self._on_controllers)
            if self._hardware_future is None:
                self._hardware_future = self._hardware_client.call_async(
                    ListHardwareComponents.Request()
                )
                self._hardware_future.add_done_callback(self._on_hardware)
            while not self._closing and (
                self._controller_future is not None
                or self._hardware_future is not None
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._condition.wait(remaining)

    def _on_controllers(self, future) -> None:
        controller_lifecycle = ControllerLifecycle.UNAVAILABLE
        broadcaster_lifecycle = ControllerLifecycle.UNAVAILABLE
        if future.cancelled() or future.exception() is not None:
            self._node.get_logger().warning('Controller lifecycle query failed')
        else:
            response = future.result()
            for controller in response.controller:
                if (
                    controller.name == POSITION_CONTROLLER
                    and controller.type == POSITION_CONTROLLER_TYPE
                ):
                    controller_lifecycle = (
                        ControllerLifecycle.ACTIVE
                        if controller.state == 'active'
                        else ControllerLifecycle.INACTIVE
                    )
                if (
                    controller.name == STATE_BROADCASTER
                    and controller.type == STATE_BROADCASTER_TYPE
                ):
                    broadcaster_lifecycle = (
                        ControllerLifecycle.ACTIVE
                        if controller.state == 'active'
                        else ControllerLifecycle.INACTIVE
                    )
        with self._condition:
            if self._closing:
                return
            self._controller_lifecycle = controller_lifecycle
            self._broadcaster_lifecycle = broadcaster_lifecycle
            self._lifecycle_observed_at_ns = self._now_ns()
            self._controller_future = None
            self._condition.notify_all()

    def _on_hardware(self, future) -> None:
        lifecycle = ControllerLifecycle.UNAVAILABLE
        if future.cancelled() or future.exception() is not None:
            self._node.get_logger().warning('Hardware lifecycle query failed')
        else:
            response = future.result()
            for component in response.component:
                if component.name != HARDWARE_SYSTEM:
                    continue
                command_interface_ready = any(
                    interface.name == COMMAND_INTERFACE
                    and interface.is_available
                    and interface.is_claimed
                    for interface in component.command_interfaces
                )
                lifecycle = (
                    ControllerLifecycle.ACTIVE
                    if component.state.id == 3 and command_interface_ready
                    else ControllerLifecycle.INACTIVE
                )
        with self._condition:
            if self._closing:
                return
            self._hardware_lifecycle = lifecycle
            self._lifecycle_observed_at_ns = self._now_ns()
            self._hardware_future = None
            self._condition.notify_all()

    def snapshot(self, joint_name: str) -> ControllerSnapshot:
        self._refresh_lifecycle()
        with self._lock:
            state = self._joint_state if joint_name == 'neck_yaw_joint' else None
            return ControllerSnapshot(
                controller_name=POSITION_CONTROLLER,
                controller_lifecycle=self._controller_lifecycle,
                broadcaster_lifecycle=self._broadcaster_lifecycle,
                hardware_lifecycle=self._hardware_lifecycle,
                command_subscribers=self._publisher.get_subscription_count(),
                observed_at_ns=self._lifecycle_observed_at_ns,
                joint_state=state,
            )

    def dispatch_position(
        self,
        *,
        joint_name: str,
        position: float,
        command_id: str,
    ) -> bool:
        if joint_name != 'neck_yaw_joint' or not command_id.startswith(
            'control-command-'
        ):
            return False
        if self._publisher.get_subscription_count() < 1:
            return False
        message = Float64MultiArray()
        message.data = [position]
        self._publisher.publish(message)
        return True

    def wait_for_feedback(
        self,
        *,
        joint_name: str,
        after_sequence: int,
        target_position: float,
        tolerance: float,
        timeout_ns: int,
    ) -> JointStateSample | None:
        deadline = time.monotonic_ns() + timeout_ns
        latest: JointStateSample | None = None
        with self._condition:
            while True:
                state = self._joint_state
                if (
                    state is not None
                    and state.joint_name == joint_name
                    and state.sequence > after_sequence
                ):
                    latest = state
                    if abs(state.position - target_position) <= tolerance:
                        return state
                remaining_ns = deadline - time.monotonic_ns()
                if remaining_ns <= 0:
                    return latest
                self._condition.wait(remaining_ns / 1_000_000_000)


class SimulationControlNode(Node):
    """Own the explicitly enabled development service and reviewed ROS port."""

    def __init__(self) -> None:
        super().__init__('ayyo_simulation_control')
        self.declare_parameter('development_injection_enabled', False)
        self.declare_parameter('robot_description', '')
        enabled = self.get_parameter('development_injection_enabled').value
        description = self.get_parameter('robot_description').value
        self._gate = DevelopmentAuthorityGate(enabled=enabled)
        self._callback_group = ReentrantCallbackGroup()
        self._gateway = RosPositionControllerGateway(self, self._callback_group)
        self.context.on_shutdown(self._gateway.close)
        self._adapter = SimulationControlAdapter(
            limits=UrdfJointLimitCatalog(description),
            authority=self._gate,
            gateway=self._gateway,
        )
        self.create_service(
            SetDevelopmentJointPosition,
            SERVICE_NAME,
            self._handle_command,
            callback_group=self._callback_group,
        )

    def close(self) -> None:
        """Settle gateway activity before node destruction."""
        self._gateway.close()

    @staticmethod
    def _write_failure(response, failure: ControlFailure) -> None:
        response.status = SetDevelopmentJointPosition.Response.REJECTED
        response.failure_code = failure.code.value
        response.detail = failure.detail
        response.result_id = failure.failure_id
        response.result_fingerprint = str(failure.fingerprint)
        response.has_state_feedback = False

    def _handle_command(self, request, response):
        if not self._gate.enabled:
            failure = ControlFailure(
                code=ControlFailureCode.DEVELOPMENT_INJECTION_DISABLED,
                detail='Development control injection is not enabled.',
            )
            self._write_failure(response, failure)
            return response
        try:
            if request.command_type != SetDevelopmentJointPosition.Request.SET_POSITION:
                raise ControlValidationError(
                    ControlFailureCode.UNSUPPORTED_COMMAND_TYPE,
                    'Only the reviewed set-position command type is supported.',
                )
            if len(request.joint_names) != len(request.positions):
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    'Joint and position arrays must have equal lengths.',
                )
            issued_at_ns = _nanoseconds(
                request.issued_at.sec,
                request.issued_at.nanosec,
            )
            valid_for_ns = _nanoseconds(
                request.valid_for.sec,
                request.valid_for.nanosec,
            )
            command = SimulationControlCommand(
                command_type=ControlCommandType.SET_JOINT_POSITIONS,
                targets=tuple(
                    JointPositionTarget(name, position)
                    for name, position in zip(
                        request.joint_names,
                        request.positions,
                        strict=True,
                    )
                ),
                issued_at_ns=issued_at_ns,
                expires_at_ns=issued_at_ns + valid_for_ns,
                authority=ControlAuthority(
                    kind=ControlAuthorityKind.DEVELOPMENT_TEST,
                    source_id=request.injection_id,
                ),
            )
            result = self._adapter.execute(
                command,
                now_ns=self.get_clock().now().nanoseconds,
            )
        except ControlValidationError as error:
            failure = ControlFailure(code=error.code, detail=str(error))
            self._write_failure(response, failure)
            return response

        response.command_id = result.command.command_id
        response.command_fingerprint = str(result.command.fingerprint)
        response.result_id = result.result_id
        response.result_fingerprint = str(result.fingerprint)
        response.has_state_feedback = result.feedback_observed
        if result.initial_position is not None:
            response.initial_position = result.initial_position
        if result.final_position is not None:
            response.final_position = result.final_position
        if result.observed_at_ns is not None:
            _assign_time(response.observed_at, result.observed_at_ns)
        if result.status is ControlResultStatus.COMPLETED:
            response.status = SetDevelopmentJointPosition.Response.COMPLETED
            response.detail = 'Bounded motion completed with authoritative feedback.'
        else:
            assert result.failure is not None
            response.status = SetDevelopmentJointPosition.Response.REJECTED
            response.failure_code = result.failure.code.value
            response.detail = result.failure.detail
        return response


def main() -> None:
    # Keep the context valid until executor callbacks have drained on SIGINT.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = SimulationControlNode()
    executor = DrainingMultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        node.close()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
