#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Lifecycle-managed fixed /joint_states observation adapter."""

from __future__ import annotations

import time

from ayyo_interfaces.srv import GetRobotBodyState
from ayyo_working_memory import (
    IngestionStatus,
    WorkingMemory,
    WorkingMemoryClockRegressionError,
    WorkingMemoryConfig,
    WorkingMemoryConfigurationError,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    JointObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotAvailability,
    RobotJointCatalog,
    RobotStateObservation,
    WorldModelFailureCode,
    WorldModelValidationError,
)
from builtin_interfaces.msg import Time
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import JointState


JOINT_STATE_TOPIC = '/joint_states'
QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'
SIMULATION_SOURCE_PROFILE = 'simulation_ros2_control_v1'
PHYSICAL_SOURCE_PROFILE = 'physical_ros2_control_v1'
SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.SIMULATION,
        source_id='ros.joint-states.simulation.ros2-control.v1',
        clock=ObservationClock.ROS_SIMULATION_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.joint-state.v1',
    ),
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.joint-states.physical.ros2-control.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.joint-state.v1',
    ),
}


def _nanoseconds(seconds: int, nanoseconds: int) -> int:
    if type(seconds) is not int or type(nanoseconds) is not int:
        raise WorldModelValidationError(
            code=WorldModelFailureCode.MALFORMED_OBSERVATION,
            detail='ROS time fields must be integers',
        )
    if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
        raise WorldModelValidationError(
            code=WorldModelFailureCode.MALFORMED_OBSERVATION,
            detail='ROS time fields are outside their canonical range',
        )
    return seconds * 1_000_000_000 + nanoseconds


def _assign_time(message, value_ns: int) -> None:
    message.sec = value_ns // 1_000_000_000
    message.nanosec = value_ns % 1_000_000_000


class AyyoWorldModelNode(LifecycleNode):
    """Own reviewed ROS normalization while cores remain transport-neutral."""

    def __init__(self) -> None:
        super().__init__('ayyo_world_model')
        self.declare_parameter('robot_description', '')
        self.declare_parameter('source_profile', 'unconfigured')
        self.declare_parameter('freshness_ms', 500)
        self.declare_parameter('retention_ttl_ms', 2000)
        self.declare_parameter('permitted_future_skew_ms', 50)
        self.declare_parameter('recent_evidence_capacity', 256)
        self.declare_parameter('environment_entity_capacity', 128)
        self._memory: WorkingMemory | None = None
        self._provenance: ObservationProvenance | None = None
        self._subscription = None
        self._query_service = None
        self._active = False
        self._invalid_message_count = 0
        self._rejected_message_count = 0

    def _destroy_runtime_interfaces(self) -> None:
        if self._subscription is not None:
            self.destroy_subscription(self._subscription)
            self._subscription = None
        if self._query_service is not None:
            self.destroy_service(self._query_service)
            self._query_service = None

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        del state
        try:
            profile_name = self.get_parameter('source_profile').value
            provenance = SOURCE_PROFILES.get(profile_name)
            if provenance is None:
                raise WorkingMemoryConfigurationError(
                    'source_profile must select one reviewed observation profile'
                )
            use_sim_time = bool(self.get_parameter('use_sim_time').value)
            if (
                provenance.clock is ObservationClock.ROS_SIMULATION_TIME
                and not use_sim_time
            ) or (
                provenance.clock is ObservationClock.ROS_SYSTEM_TIME
                and use_sim_time
            ):
                raise WorkingMemoryConfigurationError(
                    'source profile and ROS clock configuration disagree'
                )
            description = self.get_parameter('robot_description').value
            catalog = RobotJointCatalog.from_urdf(
                robot_id=AYYO_ROBOT_ID,
                robot_description=description,
            )
            self._memory = WorkingMemory(
                catalog,
                WorkingMemoryConfig(
                    robot_id=AYYO_ROBOT_ID,
                    source_clock=provenance.clock,
                    allowed_provenance=(provenance,),
                    freshness_ns=int(self.get_parameter('freshness_ms').value)
                    * 1_000_000,
                    retention_ttl_ns=int(
                        self.get_parameter('retention_ttl_ms').value
                    )
                    * 1_000_000,
                    permitted_future_skew_ns=int(
                        self.get_parameter('permitted_future_skew_ms').value
                    )
                    * 1_000_000,
                    recent_evidence_capacity=int(
                        self.get_parameter('recent_evidence_capacity').value
                    ),
                    environment_entity_capacity=int(
                        self.get_parameter('environment_entity_capacity').value
                    ),
                ),
            )
            self._provenance = provenance
            self._query_service = self.create_service(
                GetRobotBodyState,
                QUERY_SERVICE,
                self._handle_query,
            )
            self._invalid_message_count = 0
            self._rejected_message_count = 0
            return TransitionCallbackReturn.SUCCESS
        except (WorldModelValidationError, WorkingMemoryConfigurationError) as error:
            self.get_logger().error(f'World Model configure failed: {error}')
            self._memory = None
            self._provenance = None
            self._destroy_runtime_interfaces()
            return TransitionCallbackReturn.FAILURE

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        del state
        if self._memory is None or self._provenance is None:
            return TransitionCallbackReturn.FAILURE
        self._subscription = self.create_subscription(
            JointState,
            JOINT_STATE_TOPIC,
            self._on_joint_state,
            qos_profile_sensor_data,
        )
        self._active = True
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        if self._subscription is not None:
            self.destroy_subscription(self._subscription)
            self._subscription = None
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        self._destroy_runtime_interfaces()
        if self._memory is not None:
            self._memory.reset()
        self._memory = None
        self._provenance = None
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        self._destroy_runtime_interfaces()
        if self._memory is not None:
            self._memory.reset()
        self._memory = None
        self._provenance = None
        return TransitionCallbackReturn.SUCCESS

    def on_error(self, state: State) -> TransitionCallbackReturn:
        return self.on_cleanup(state)

    def _warn_bounded(self, category: str, detail: str) -> None:
        if category == 'invalid':
            self._invalid_message_count += 1
            count = self._invalid_message_count
        else:
            self._rejected_message_count += 1
            count = self._rejected_message_count
        if count == 1 or count % 100 == 0:
            self.get_logger().warning(
                f'{category} joint-state evidence count={count}: {detail}'
            )

    def _on_joint_state(self, message: JointState) -> None:
        if not self._active or self._memory is None or self._provenance is None:
            return
        try:
            names = tuple(message.name)
            positions = tuple(message.position)
            velocities = tuple(message.velocity)
            efforts = tuple(message.effort)
            if not names or len(names) != len(positions):
                raise ValueError('joint names and positions must be non-empty and equal')
            if velocities and len(velocities) != len(names):
                raise ValueError('velocity array must be empty or match joint names')
            if efforts and len(efforts) != len(names):
                raise ValueError('effort array must be empty or match joint names')
            observed_at_ns = _nanoseconds(
                message.header.stamp.sec,
                message.header.stamp.nanosec,
            )
            observation = RobotStateObservation(
                robot_id=AYYO_ROBOT_ID,
                joints=tuple(
                    JointObservation(
                        joint_name=name,
                        position=positions[index],
                        velocity=None if not velocities else velocities[index],
                        effort=None if not efforts else efforts[index],
                    )
                    for index, name in enumerate(names)
                ),
                observed_at_ns=observed_at_ns,
                provenance=self._provenance,
                confidence=1.0,
            )
            now_ns = self.get_clock().now().nanoseconds
            try:
                result = self._memory.ingest(
                    observation,
                    now_ns=now_ns,
                    received_at_monotonic_ns=time.monotonic_ns(),
                )
            except WorkingMemoryClockRegressionError:
                self.get_logger().warning(
                    'ROS source clock regressed; discarded temporary World Model state'
                )
                self._memory.reset()
                result = self._memory.ingest(
                    observation,
                    now_ns=now_ns,
                    received_at_monotonic_ns=time.monotonic_ns(),
                )
            if result.status is IngestionStatus.REJECTED:
                self._warn_bounded('rejected', f'{result.reason.value}: {result.detail}')
        except (ValueError, WorldModelValidationError, WorkingMemoryConfigurationError) as error:
            self._warn_bounded('invalid', str(error))

    @staticmethod
    def _not_ready(response, detail: str):
        response.status = GetRobotBodyState.Response.NOT_READY
        response.detail = detail
        response.robot_id = AYYO_ROBOT_ID
        response.availability = GetRobotBodyState.Response.UNAVAILABLE
        return response

    def _handle_query(self, request, response):
        if request.robot_id != AYYO_ROBOT_ID:
            return self._not_ready(response, 'query robot identity is not canonical Ayyo')
        if not self._active or self._memory is None or self._provenance is None:
            return self._not_ready(response, 'World Model observation adapter is not active')
        now_ns = self.get_clock().now().nanoseconds
        try:
            snapshot = self._memory.current_snapshot(now_ns=now_ns)
            stats = self._memory.stats(now_ns=now_ns)
        except WorkingMemoryClockRegressionError:
            self._memory.reset()
            return self._not_ready(response, 'source clock regressed; temporary state reset')
        response.robot_id = snapshot.robot.robot_id
        _assign_time(response.queried_at, now_ns)
        response.known_joint_count = len(snapshot.robot.known_joint_names)
        response.environment_entity_count = len(snapshot.entities)
        response.recent_evidence_count = stats.recent_evidence_count
        if snapshot.robot.availability is RobotAvailability.UNAVAILABLE:
            return self._not_ready(response, 'no unexpired robot joint evidence is available')
        response.status = GetRobotBodyState.Response.READY
        response.detail = 'current body state projected from accepted observations'
        response.snapshot_id = snapshot.snapshot_id
        response.snapshot_fingerprint = str(snapshot.version)
        response.availability = (
            GetRobotBodyState.Response.AVAILABLE
            if snapshot.robot.availability is RobotAvailability.AVAILABLE
            else GetRobotBodyState.Response.PARTIAL
        )
        response.source_kind = self._provenance.source_kind.value
        response.source_id = self._provenance.source_id
        response.source_clock = self._provenance.clock.value
        response.source_transport = self._provenance.transport.value
        response.source_interface = self._provenance.interface
        for joint in snapshot.robot.joints:
            response.joint_names.append(joint.joint.joint_name)
            response.positions.append(joint.joint.position)
            response.has_velocity.append(joint.joint.velocity is not None)
            response.velocities.append(
                0.0 if joint.joint.velocity is None else joint.joint.velocity
            )
            response.has_effort.append(joint.joint.effort is not None)
            response.efforts.append(0.0 if joint.joint.effort is None else joint.joint.effort)
            time_message = Time()
            _assign_time(time_message, joint.observed_at_ns)
            response.joint_observed_at.append(time_message)
            response.joint_confidence.append(joint.confidence)
            response.joint_freshness.append(
                GetRobotBodyState.Response.FRESH
                if joint.freshness.value == 'fresh'
                else GetRobotBodyState.Response.STALE
            )
            response.joint_observation_ids.append(joint.observation_id)
        return response


def main() -> None:
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = AyyoWorldModelNode()
    executor = SingleThreadedExecutor()
    exit_code = 0
    configured = False
    try:
        if node.trigger_configure() is not TransitionCallbackReturn.SUCCESS:
            raise RuntimeError('World Model lifecycle configure transition failed')
        configured = True
        if node.trigger_activate() is not TransitionCallbackReturn.SUCCESS:
            raise RuntimeError('World Model lifecycle activate transition failed')
        executor.add_node(node)
        executor.spin()
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    except RuntimeError as error:
        node.get_logger().error(str(error))
        exit_code = 1
    finally:
        if node._active:
            node.trigger_deactivate()
        if configured:
            node.trigger_cleanup()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
