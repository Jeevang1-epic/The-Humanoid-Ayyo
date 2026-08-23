#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Send one explicit development command through the typed control service."""

from __future__ import annotations

import argparse
import json
import sys
import time

from ayyo_interfaces.srv import SetDevelopmentJointPosition
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter


SERVICE_NAME = '/ayyo/development/set_joint_position'
INJECTION_ID = 'development.simulation.control.v1'


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Development-only bounded Ayyo joint-position request.'
    )
    parser.add_argument('--joint', default='neck_yaw_joint')
    parser.add_argument('--position', required=True, type=float)
    parser.add_argument('--valid-for-ms', default=1000, type=int)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(sys.argv[1:] if arguments is None else arguments)
    rclpy.init()
    node = Node(
        'ayyo_development_control_client',
        parameter_overrides=[Parameter('use_sim_time', value=True)],
    )
    try:
        client = node.create_client(SetDevelopmentJointPosition, SERVICE_NAME)
        if not client.wait_for_service(timeout_sec=5.0):
            print('FAIL: development control service is unavailable', file=sys.stderr)
            return 1
        deadline = time.monotonic() + 5.0
        while node.get_clock().now().nanoseconds <= 0 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        now_ns = node.get_clock().now().nanoseconds
        if now_ns <= 0:
            print('FAIL: simulation clock is unavailable', file=sys.stderr)
            return 1
        request = SetDevelopmentJointPosition.Request()
        request.command_type = SetDevelopmentJointPosition.Request.SET_POSITION
        request.joint_names = [options.joint]
        request.positions = [options.position]
        request.issued_at.sec = now_ns // 1_000_000_000
        request.issued_at.nanosec = now_ns % 1_000_000_000
        valid_for_ns = options.valid_for_ms * 1_000_000
        request.valid_for.sec = valid_for_ns // 1_000_000_000
        request.valid_for.nanosec = valid_for_ns % 1_000_000_000
        request.injection_id = INJECTION_ID
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
        if not future.done() or future.result() is None:
            print('FAIL: development control request timed out', file=sys.stderr)
            return 1
        response = future.result()
        output = {
            'command_fingerprint': response.command_fingerprint,
            'command_id': response.command_id,
            'detail': response.detail,
            'failure_code': response.failure_code,
            'final_position': response.final_position,
            'has_state_feedback': response.has_state_feedback,
            'initial_position': response.initial_position,
            'result_fingerprint': response.result_fingerprint,
            'result_id': response.result_id,
            'status': response.status,
        }
        print(json.dumps(output, sort_keys=True, separators=(',', ':')))
        return (
            0
            if response.status == SetDevelopmentJointPosition.Response.COMPLETED
            else 2
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
