#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Fixed client for the read-only anonymous semantic-state query."""

from __future__ import annotations

import argparse
import json

from ayyo_interfaces.srv import GetAnonymousSemanticState
from ayyo_world_model import AYYO_ROBOT_ID
import rclpy
from rclpy.node import Node
from semantic_state_transport import semantic_response_document


QUERY_SERVICE = '/ayyo/world_model/get_anonymous_semantic_state'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-id', default=AYYO_ROBOT_ID)
    args = parser.parse_args()
    rclpy.init()
    node = Node('ayyo_anonymous_semantic_state_query')
    try:
        client = node.create_client(GetAnonymousSemanticState, QUERY_SERVICE)
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('anonymous semantic query service is unavailable')
        request = GetAnonymousSemanticState.Request()
        request.robot_id = args.robot_id
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        if not future.done() or future.cancelled() or future.exception() is not None:
            raise RuntimeError('anonymous semantic query did not complete within its bound')
        response = future.result()
        print(
            json.dumps(
                semantic_response_document(response),
                allow_nan=False,
                separators=(',', ':'),
                sort_keys=True,
            )
        )
        if response.status != GetAnonymousSemanticState.Response.READY:
            raise SystemExit(2)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
