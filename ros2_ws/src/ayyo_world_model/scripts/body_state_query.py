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
            'current_audio_count': response.current_audio_count,
            'current_depth_count': response.current_depth_count,
            'current_fused_rgbd_count': response.current_fused_rgbd_count,
            'current_visual_count': response.current_visual_count,
            'current_visual_interpretation_count': (
                response.current_visual_interpretation_count
            ),
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
            'audio_frame': (
                {
                    'availability': response.audio_availability,
                    'channel_count': response.audio_channel_count,
                    'data_size_bytes': response.audio_data_size_bytes,
                    'duration_ns': response.audio_duration_ns,
                    'encoding': response.audio_encoding,
                    'frame_count': response.audio_frame_count,
                    'frame_id': response.audio_frame_id,
                    'freshness': response.audio_freshness,
                    'observation_fingerprint': (
                        response.audio_observation_fingerprint
                    ),
                    'observation_id': response.audio_observation_id,
                    'observed_at_ns': _nanoseconds(response.audio_observed_at),
                    'payload_sha256': response.audio_payload_sha256,
                    'peak_amplitude': response.audio_peak_amplitude,
                    'producer_id': response.audio_producer_id,
                    'result_at_ns': _nanoseconds(response.audio_result_at),
                    'rms_amplitude': response.audio_rms_amplitude,
                    'sample_count': response.audio_sample_count,
                    'sample_rate_hz': response.audio_sample_rate_hz,
                    'sensor_id': response.audio_sensor_id,
                    'session_id': response.audio_session_id,
                    'source_clock': response.audio_source_clock,
                    'source_id': response.audio_source_id,
                    'source_interface': response.audio_source_interface,
                    'source_kind': response.audio_source_kind,
                    'source_manifest_id': response.audio_source_manifest_id,
                    'source_transport': response.audio_source_transport,
                }
                if response.has_audio_frame
                else None
            ),
            'audio_diagnostics': (
                {
                    'accepted_count': response.audio_accepted_count,
                    'diagnostic_event': response.audio_diagnostic_event,
                    'duplicate_count': response.audio_duplicate_count,
                    'error_count': response.audio_error_count,
                    'lifecycle_state': response.audio_lifecycle_state,
                    'rejected_count': response.audio_rejected_count,
                    'retained_payload_bytes': (
                        response.audio_retained_payload_bytes
                    ),
                    'transport_invalid_count': (
                        response.audio_transport_invalid_count
                    ),
                }
                if response.has_audio_diagnostics
                else None
            ),
            'depth_frame': (
                {
                    'availability': response.depth_availability,
                    'calibration_id': response.depth_calibration_id,
                    'calibration_record_id': response.depth_calibration_record_id,
                    'data_size_bytes': response.depth_data_size_bytes,
                    'encoding': response.depth_encoding,
                    'frame_id': response.depth_frame_id,
                    'freshness': response.depth_freshness,
                    'height': response.depth_height,
                    'invalid_count': response.depth_invalid_count,
                    'is_bigendian': response.depth_is_bigendian,
                    'maximum_m': response.depth_maximum_m,
                    'minimum_m': response.depth_minimum_m,
                    'observation_fingerprint': (
                        response.depth_observation_fingerprint
                    ),
                    'observation_id': response.depth_observation_id,
                    'observed_at_ns': _nanoseconds(response.depth_observed_at),
                    'payload_sha256': response.depth_payload_sha256,
                    'sensor_id': response.depth_sensor_id,
                    'session_id': response.depth_session_id,
                    'source_clock': response.depth_source_clock,
                    'source_id': response.depth_source_id,
                    'source_interface': response.depth_source_interface,
                    'source_kind': response.depth_source_kind,
                    'source_manifest_id': response.depth_source_manifest_id,
                    'source_transport': response.depth_source_transport,
                    'step': response.depth_step,
                    'valid_count': response.depth_valid_count,
                    'width': response.depth_width,
                }
                if response.has_depth_frame
                else None
            ),
            'fused_rgbd': (
                {
                    'availability': response.rgbd_availability,
                    'depth': {
                        'calibration_id': response.rgbd_depth_calibration_id,
                        'camera_frame_id': response.rgbd_depth_camera_frame_id,
                        'observation_fingerprint': (
                            response.rgbd_depth_observation_fingerprint
                        ),
                        'observation_id': response.rgbd_depth_observation_id,
                        'optical_frame_id': response.rgbd_depth_optical_frame_id,
                        'producer_id': response.rgbd_depth_producer_id,
                        'sensor_id': response.rgbd_depth_sensor_id,
                        'session_id': response.rgbd_depth_session_id,
                        'source_clock': response.rgbd_depth_source_clock,
                        'source_fingerprint_sha256': (
                            response.rgbd_depth_source_fingerprint_sha256
                        ),
                        'source_id': response.rgbd_depth_source_id,
                        'source_interface': response.rgbd_depth_source_interface,
                        'source_kind': response.rgbd_depth_source_kind,
                        'source_transport': response.rgbd_depth_source_transport,
                    },
                    'frame_id': response.rgbd_frame_id,
                    'freshness': response.rgbd_freshness,
                    'observation_fingerprint': (
                        response.rgbd_observation_fingerprint
                    ),
                    'observation_id': response.rgbd_observation_id,
                    'observed_at_ns': _nanoseconds(response.rgbd_observed_at),
                    'pair_id': response.rgbd_pair_id,
                    'pairing_policy_id': response.rgbd_pairing_policy_id,
                    'pairing_policy_version': (
                        response.rgbd_pairing_policy_version
                    ),
                    'result_at_ns': _nanoseconds(response.rgbd_result_at),
                    'rgb': {
                        'calibration_id': response.rgbd_rgb_calibration_id,
                        'camera_frame_id': response.rgbd_rgb_camera_frame_id,
                        'observation_fingerprint': (
                            response.rgbd_rgb_observation_fingerprint
                        ),
                        'observation_id': response.rgbd_rgb_observation_id,
                        'optical_frame_id': response.rgbd_rgb_optical_frame_id,
                        'producer_id': response.rgbd_rgb_producer_id,
                        'sensor_id': response.rgbd_rgb_sensor_id,
                        'session_id': response.rgbd_rgb_session_id,
                        'source_clock': response.rgbd_rgb_source_clock,
                        'source_fingerprint_sha256': (
                            response.rgbd_rgb_source_fingerprint_sha256
                        ),
                        'source_id': response.rgbd_rgb_source_id,
                        'source_interface': response.rgbd_rgb_source_interface,
                        'source_kind': response.rgbd_rgb_source_kind,
                        'source_transport': response.rgbd_rgb_source_transport,
                    },
                    'sensor_id': response.rgbd_sensor_id,
                    'source_clock': response.rgbd_source_clock,
                    'source_id': response.rgbd_source_id,
                    'source_interface': response.rgbd_source_interface,
                    'source_kind': response.rgbd_source_kind,
                    'source_transport': response.rgbd_source_transport,
                    'spatial_registration_validated': (
                        response.rgbd_spatial_registration_validated
                    ),
                    'synchronization_session_id': (
                        response.rgbd_synchronization_session_id
                    ),
                }
                if response.has_fused_rgbd
                else None
            ),
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
            'visual_interpretation': (
                {
                    'adapter_id': response.visual_interpretation_adapter_id,
                    'availability': response.visual_interpretation_availability,
                    'detections': [
                        {
                            'category': category,
                            'confidence': confidence if has_confidence else None,
                            'coordinate_space': coordinate_space,
                            'detection_id': detection_id,
                            'label': label,
                            'region': {
                                'x_max': x_max,
                                'x_min': x_min,
                                'y_max': y_max,
                                'y_min': y_min,
                            },
                        }
                        for (
                            detection_id,
                            category,
                            label,
                            coordinate_space,
                            x_min,
                            y_min,
                            x_max,
                            y_max,
                            has_confidence,
                            confidence,
                        ) in zip(
                            response.visual_detection_ids,
                            response.visual_detection_categories,
                            response.visual_detection_labels,
                            response.visual_detection_coordinate_spaces,
                            response.visual_detection_x_min,
                            response.visual_detection_y_min,
                            response.visual_detection_x_max,
                            response.visual_detection_y_max,
                            response.visual_detection_has_confidence,
                            response.visual_detection_confidence,
                            strict=True,
                        )
                    ],
                    'freshness': response.visual_interpretation_freshness,
                    'interface': response.visual_interpretation_interface,
                    'model_id': response.visual_interpretation_model_id,
                    'model': (
                        {
                            'artifact_sha256': (
                                response.visual_interpretation_model_artifact_sha256
                            ),
                            'build_export_id': (
                                response.visual_interpretation_model_build_export_id
                                if response.visual_interpretation_model_has_build_export_id
                                else None
                            ),
                            'capability': (
                                response.visual_interpretation_model_capability
                            ),
                            'configuration_sha256': (
                                response.visual_interpretation_model_configuration_sha256
                            ),
                            'format': response.visual_interpretation_model_format,
                            'id': response.visual_interpretation_model_id,
                            'label_schema_id': (
                                response.visual_interpretation_model_label_schema_id
                            ),
                            'label_schema_version': (
                                response.visual_interpretation_model_label_schema_version
                            ),
                            'provenance_sha256': (
                                response.visual_interpretation_model_provenance_sha256
                            ),
                            'source_classification': (
                                response.visual_interpretation_model_source_classification
                            ),
                            'version': (
                                response.visual_interpretation_model_version
                            ),
                        }
                        if response.has_visual_evaluation
                        else None
                    ),
                    'observation_fingerprint': (
                        response.visual_interpretation_observation_fingerprint
                    ),
                    'observation_id': (
                        response.visual_interpretation_observation_id
                    ),
                    'producer_id': response.visual_interpretation_producer_id,
                    'producer_kind': response.visual_interpretation_producer_kind,
                    'evaluation': (
                        {
                            'dataset_id': (
                                response.visual_interpretation_dataset_id
                            ),
                            'dataset_manifest_sha256': (
                                response.visual_interpretation_dataset_manifest_sha256
                            ),
                            'dataset_version': (
                                response.visual_interpretation_dataset_version
                            ),
                            'decision': (
                                response.visual_interpretation_mechanical_decision
                            ),
                            'policy_id': response.visual_interpretation_policy_id,
                            'policy_sha256': (
                                response.visual_interpretation_policy_sha256
                            ),
                            'policy_version': (
                                response.visual_interpretation_policy_version
                            ),
                            'producer_implementation_sha256': (
                                response.visual_interpretation_producer_implementation_sha256
                            ),
                            'producer_manifest_sha256': (
                                response.visual_interpretation_producer_manifest_sha256
                            ),
                            'producer_version': (
                                response.visual_interpretation_producer_version
                            ),
                            'report_semantic_sha256': (
                                response.visual_interpretation_report_semantic_sha256
                            ),
                            'result_schema_version': (
                                response.visual_interpretation_result_schema_version
                            ),
                        }
                        if response.has_visual_evaluation
                        else None
                    ),
                    'reference_frame_id': (
                        response.visual_interpretation_reference_frame_id
                    ),
                    'result_at_ns': _nanoseconds(
                        response.visual_interpretation_result_at
                    ),
                    'sensor_id': response.visual_interpretation_sensor_id,
                    'source_clock': response.visual_interpretation_source_clock,
                    'source_id': response.visual_interpretation_source_id,
                    'source_interface': (
                        response.visual_interpretation_source_interface
                    ),
                    'source_kind': response.visual_interpretation_source_kind,
                    'source_observed_at_ns': _nanoseconds(
                        response.visual_interpretation_source_observed_at
                    ),
                    'source_transport': (
                        response.visual_interpretation_source_transport
                    ),
                    'source_visual_fingerprint': (
                        response.visual_interpretation_source_visual_fingerprint
                    ),
                    'source_visual_observation_id': (
                        response.visual_interpretation_source_visual_observation_id
                    ),
                }
                if response.has_visual_interpretation
                else None
            ),
        }
        print(json.dumps(result, allow_nan=False, separators=(',', ':'), sort_keys=True))
        if response.status != GetRobotBodyState.Response.READY:
            raise SystemExit(2)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
