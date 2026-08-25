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
        imu_orientation = (
            list(response.imu_orientation_xyzw)
            if response.has_imu_orientation
            else None
        )
        imu_angular_velocity = (
            list(response.imu_angular_velocity_xyz)
            if response.has_imu_angular_velocity
            else None
        )
        imu_linear_acceleration = (
            list(response.imu_linear_acceleration_xyz)
            if response.has_imu_linear_acceleration
            else None
        )
        result = {
            'availability': response.availability,
            'base_pose': (
                {
                    'availability': response.base_pose_availability,
                    'covariance': (
                        list(response.base_pose_covariance)
                        if response.has_base_pose_covariance
                        else None
                    ),
                    'observation_fingerprint': (
                        response.base_pose_observation_fingerprint
                    ),
                    'observation_id': response.base_pose_observation_id,
                    'observed_at_ns': _nanoseconds(response.base_pose_observed_at),
                    'orientation_xyzw': list(response.base_pose_orientation_xyzw),
                    'sensor_id': response.base_pose_sensor_id,
                    'source_frame_id': response.base_pose_source_frame_id,
                    'target_frame_id': response.base_pose_target_frame_id,
                    'translation_xyz': list(response.base_pose_translation_xyz),
                    'quality': (
                        response.base_pose_quality
                        if response.has_base_pose_quality
                        else None
                    ),
                    'source_clock': response.base_pose_source_clock,
                    'source_id': response.base_pose_source_id,
                    'source_interface': response.base_pose_source_interface,
                    'source_kind': response.base_pose_source_kind,
                    'source_transport': response.base_pose_source_transport,
                }
                if response.has_base_pose
                else None
            ),
            'base_pose_availability': response.base_pose_availability,
            'detail': response.detail,
            'current_visual_count': response.current_visual_count,
            'environment_entity_count': response.environment_entity_count,
            'joint_confidence': list(response.joint_confidence),
            'joint_freshness': list(response.joint_freshness),
            'joint_names': list(response.joint_names),
            'joint_observation_ids': list(response.joint_observation_ids),
            'joint_observed_at_ns': [
                _nanoseconds(value) for value in response.joint_observed_at
            ],
            'known_joint_count': response.known_joint_count,
            'imu': (
                {
                    'angular_velocity_covariance': (
                        list(response.imu_angular_velocity_covariance)
                        if response.has_imu_angular_velocity_covariance
                        else None
                    ),
                    'angular_velocity_xyz': imu_angular_velocity,
                    'availability': response.imu_availability,
                    'frame_id': response.imu_frame_id,
                    'freshness': response.imu_freshness,
                    'linear_acceleration_covariance': (
                        list(response.imu_linear_acceleration_covariance)
                        if response.has_imu_linear_acceleration_covariance
                        else None
                    ),
                    'linear_acceleration_xyz': imu_linear_acceleration,
                    'observation_fingerprint': response.imu_observation_fingerprint,
                    'observation_id': response.imu_observation_id,
                    'observed_at_ns': _nanoseconds(response.imu_observed_at),
                    'orientation_covariance': (
                        list(response.imu_orientation_covariance)
                        if response.has_imu_orientation_covariance
                        else None
                    ),
                    'orientation_xyzw': imu_orientation,
                    'quality': response.imu_quality if response.has_imu_quality else None,
                    'sensor_id': response.imu_sensor_id,
                    'source_clock': response.imu_source_clock,
                    'source_id': response.imu_source_id,
                    'source_interface': response.imu_source_interface,
                    'source_kind': response.imu_source_kind,
                    'source_transport': response.imu_source_transport,
                }
                if response.has_imu
                else None
            ),
            'positions': list(response.positions),
            'perception_accepted_count': response.perception_accepted_count,
            'perception_duplicate_count': response.perception_duplicate_count,
            'perception_rejected_count': response.perception_rejected_count,
            'queried_at_ns': _nanoseconds(response.queried_at),
            'recent_evidence_count': response.recent_evidence_count,
            'robot_id': response.robot_id,
            'sensors': [
                {
                    'availability': availability,
                    'frame_id': frame_id,
                    'health': (
                        {
                            'availability': health_availability,
                            'detail': health_detail,
                            'freshness': health_freshness,
                            'observation_fingerprint': health_fingerprint,
                            'observation_id': health_observation_id,
                            'observed_at_ns': _nanoseconds(health_observed_at),
                            'source_clock': health_source_clock,
                            'source_id': health_source_id,
                            'source_interface': health_source_interface,
                            'source_kind': health_source_kind,
                            'source_transport': health_source_transport,
                        }
                        if has_health
                        else None
                    ),
                    'kind': kind,
                    'sensor_id': sensor_id,
                }
                for (
                    sensor_id,
                    kind,
                    frame_id,
                    availability,
                    has_health,
                    health_availability,
                    health_freshness,
                    health_observed_at,
                    health_observation_id,
                    health_fingerprint,
                    health_source_kind,
                    health_source_id,
                    health_source_clock,
                    health_source_transport,
                    health_source_interface,
                    health_detail,
                ) in zip(
                    response.sensor_ids,
                    response.sensor_kinds,
                    response.sensor_frame_ids,
                    response.sensor_availability,
                    response.has_sensor_health,
                    response.sensor_health_availability,
                    response.sensor_health_freshness,
                    response.sensor_health_observed_at,
                    response.sensor_health_observation_ids,
                    response.sensor_health_observation_fingerprints,
                    response.sensor_health_source_kinds,
                    response.sensor_health_source_ids,
                    response.sensor_health_source_clocks,
                    response.sensor_health_source_transports,
                    response.sensor_health_source_interfaces,
                    response.sensor_health_details,
                    strict=True,
                )
            ],
            'snapshot_fingerprint': response.snapshot_fingerprint,
            'snapshot_id': response.snapshot_id,
            'source_clock': response.source_clock,
            'source_id': response.source_id,
            'source_interface': response.source_interface,
            'source_kind': response.source_kind,
            'source_transport': response.source_transport,
            'status': response.status,
            'visual_frame': (
                {
                    'availability': response.visual_availability,
                    'calibration_id': response.visual_calibration_id,
                    'data_size_bytes': response.visual_data_size_bytes,
                    'encoding': response.visual_encoding,
                    'frame_id': response.visual_frame_id,
                    'freshness': response.visual_freshness,
                    'height': response.visual_height,
                    'is_bigendian': response.visual_is_bigendian,
                    'observation_fingerprint': (
                        response.visual_observation_fingerprint
                    ),
                    'observation_id': response.visual_observation_id,
                    'observed_at_ns': _nanoseconds(response.visual_observed_at),
                    'sensor_id': response.visual_sensor_id,
                    'source_clock': response.visual_source_clock,
                    'source_id': response.visual_source_id,
                    'source_interface': response.visual_source_interface,
                    'source_kind': response.visual_source_kind,
                    'source_transport': response.visual_source_transport,
                    'step': response.visual_step,
                    'width': response.visual_width,
                }
                if response.has_visual_frame
                else None
            ),
            'visual_availability': response.visual_availability,
        }
        print(json.dumps(result, allow_nan=False, separators=(',', ':'), sort_keys=True))
        if response.status != GetRobotBodyState.Response.READY:
            raise SystemExit(2)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
