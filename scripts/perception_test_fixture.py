#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY fixed diagnostics and invalid-localization smoke fixture."""

from __future__ import annotations

import argparse
import json
import time

from ayyo_interfaces.srv import GetRobotBodyState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter


DIAGNOSTICS_TOPIC = '/diagnostics'
LOCALIZATION_TOPIC = '/ayyo/localization/odometry'
QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'
LEVELS = {
    'ok': DiagnosticStatus.OK,
    'warn': DiagnosticStatus.WARN,
    'error': DiagnosticStatus.ERROR,
    'stale': DiagnosticStatus.STALE,
}
COMPONENTS = {
    'imu': (
        'ayyo/proprioception/body_imu_source',
        'ayyo.imu.body.v1',
    ),
    'joint': (
        'ayyo/proprioception/joint_state_source',
        'ayyo.joint-state.body.v1',
    ),
    'unknown': (
        'unreviewed/proprioception/source',
        'unreviewed.sensor.v1',
    ),
}


def _status(component: str, level: str) -> DiagnosticStatus:
    name, hardware_id = COMPONENTS[component]
    result = DiagnosticStatus()
    result.level = LEVELS[level]
    result.name = name
    result.hardware_id = hardware_id
    result.message = 'bounded test-only diagnostics fixture'
    result.values = [KeyValue(key='fixture', value='true')]
    return result


def _wait_for_simulation_time(node: Node) -> None:
    deadline = time.monotonic() + 5.0
    while node.get_clock().now().nanoseconds <= 0:
        if time.monotonic() >= deadline:
            raise RuntimeError('simulation clock did not become available within five seconds')
        rclpy.spin_once(node, timeout_sec=0.05)


def _verify_health_query(
    node: Node,
    publisher,
    message: DiagnosticArray,
    *,
    sensor_id: str,
    expected_availability: int,
) -> None:
    client = node.create_client(GetRobotBodyState, QUERY_SERVICE)
    if not client.wait_for_service(timeout_sec=5.0):
        raise RuntimeError('World Model query service is unavailable')
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        message.header.stamp = node.get_clock().now().to_msg()
        publisher.publish(message)
        rclpy.spin_once(node, timeout_sec=0.1)
        request = GetRobotBodyState.Request()
        request.robot_id = 'ayyo.robot.v1'
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=1.0)
        if not future.done() or future.cancelled() or future.exception() is not None:
            future.cancel()
            continue
        response = future.result()
        if sensor_id not in response.sensor_ids:
            continue
        index = list(response.sensor_ids).index(sensor_id)
        if (
            not response.has_sensor_health[index]
            or response.sensor_health_availability[index] != expected_availability
            or response.sensor_health_freshness[index]
            != GetRobotBodyState.Response.FRESH
            or response.sensor_health_source_ids[index]
            != 'ros.diagnostics.simulation.test-fixture.v1'
            or response.sensor_health_source_interfaces[index]
            != 'diagnostic-msgs.diagnostic-array.v1'
        ):
            continue
        result = {
            'availability': response.sensor_health_availability[index],
            'freshness': response.sensor_health_freshness[index],
            'sensor_id': sensor_id,
            'source_id': response.sensor_health_source_ids[index],
            'source_interface': response.sensor_health_source_interfaces[index],
            'status': response.status,
        }
        print(json.dumps(result, separators=(',', ':'), sort_keys=True))
        return
    raise RuntimeError('reviewed diagnostic did not reach the World Model query')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenario',
        required=True,
        choices=(
            'diagnostic',
            'unknown_diagnostic',
            'wrong_localization_frame',
        ),
    )
    parser.add_argument('--component', choices=('imu', 'joint'), default='imu')
    parser.add_argument('--level', choices=tuple(LEVELS), default='ok')
    parser.add_argument('--verify-query', action='store_true')
    args = parser.parse_args()
    if args.verify_query and args.scenario != 'diagnostic':
        parser.error('--verify-query requires the diagnostic scenario')

    rclpy.init()
    node = Node(
        f'ayyo_perception_test_fixture_{args.scenario}_{args.component}_{args.level}',
        parameter_overrides=[Parameter('use_sim_time', value=True)],
    )
    try:
        _wait_for_simulation_time(node)
        if args.scenario == 'wrong_localization_frame':
            publisher = node.create_publisher(Odometry, LOCALIZATION_TOPIC, 10)
        else:
            publisher = node.create_publisher(DiagnosticArray, DIAGNOSTICS_TOPIC, 10)
        deadline = time.monotonic() + 5.0
        while publisher.get_subscription_count() == 0:
            if time.monotonic() >= deadline:
                raise RuntimeError('fixture found no reviewed adapter subscription')
            rclpy.spin_once(node, timeout_sec=0.05)
        stamp = node.get_clock().now().to_msg()
        if args.scenario == 'wrong_localization_frame':
            message = Odometry()
            message.header.stamp = stamp
            message.header.frame_id = 'map'
            message.child_frame_id = 'base_link'
            message.pose.pose.orientation.w = 1.0
        else:
            message = DiagnosticArray()
            message.header.stamp = stamp
            component = 'unknown' if args.scenario == 'unknown_diagnostic' else args.component
            message.status = [_status(component, args.level)]
        if args.verify_query:
            _verify_health_query(
                node,
                publisher,
                message,
                sensor_id=COMPONENTS[args.component][1],
                expected_availability={
                    'ok': GetRobotBodyState.Response.SENSOR_AVAILABLE,
                    'warn': GetRobotBodyState.Response.SENSOR_DEGRADED,
                    'error': GetRobotBodyState.Response.SENSOR_ERROR,
                    'stale': GetRobotBodyState.Response.SENSOR_STALE,
                }[args.level],
            )
            return
        for _ in range(3):
            message.header.stamp = node.get_clock().now().to_msg()
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
