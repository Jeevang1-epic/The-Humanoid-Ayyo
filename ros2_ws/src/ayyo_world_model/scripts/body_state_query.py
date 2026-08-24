#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Bounded fixed client for the read-only body-state query."""

from __future__ import annotations

import argparse
import json

from ayyo_interfaces.srv import GetRobotBodyState
from ayyo_world_model import AYYO_ROBOT_ID
import rclpy
from rclpy.node import Node


QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'


def _nanoseconds(value) -> int:
    return value.sec * 1_000_000_000 + value.nanosec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-id', default=AYYO_ROBOT_ID)
    args = parser.parse_args()
    rclpy.init()
    node = Node('ayyo_body_state_query')
    try:
        client = node.create_client(GetRobotBodyState, QUERY_SERVICE)
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('World Model query service is unavailable')
        request = GetRobotBodyState.Request()
        request.robot_id = args.robot_id
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        if not future.done() or future.cancelled() or future.exception() is not None:
            raise RuntimeError('World Model query did not complete within its bound')
        response = future.result()
        result = {
            'availability': response.availability,
            'detail': response.detail,
            'environment_entity_count': response.environment_entity_count,
            'joint_confidence': list(response.joint_confidence),
            'joint_freshness': list(response.joint_freshness),
            'joint_names': list(response.joint_names),
            'joint_observation_ids': list(response.joint_observation_ids),
            'joint_observed_at_ns': [
                _nanoseconds(value) for value in response.joint_observed_at
            ],
            'known_joint_count': response.known_joint_count,
            'positions': list(response.positions),
            'queried_at_ns': _nanoseconds(response.queried_at),
            'recent_evidence_count': response.recent_evidence_count,
            'robot_id': response.robot_id,
            'snapshot_fingerprint': response.snapshot_fingerprint,
            'snapshot_id': response.snapshot_id,
            'source_clock': response.source_clock,
            'source_id': response.source_id,
            'source_interface': response.source_interface,
            'source_kind': response.source_kind,
            'source_transport': response.source_transport,
            'status': response.status,
        }
        print(json.dumps(result, allow_nan=False, separators=(',', ':'), sort_keys=True))
        if response.status != GetRobotBodyState.Response.READY:
            raise SystemExit(2)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
