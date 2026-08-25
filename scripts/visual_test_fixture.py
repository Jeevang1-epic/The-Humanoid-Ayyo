#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY fixed visual source and adversarial-contract fixture."""

from __future__ import annotations

import argparse
import json
import math
import time

from ayyo_perception import (
    AdmissionReason,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    WorldModelValidationError,
)
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


IMAGE_TOPIC = '/ayyo/camera/head/image_raw'
CAMERA_INFO_TOPIC = '/ayyo/camera/head/camera_info'
CAMERA_SENSOR = SensorIdentity(
    'ayyo.camera.head.rgb.v1',
    SensorKind.RGB_CAMERA,
    'head_camera_optical_frame',
)
SIMULATION_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.SIMULATION,
    'ros.camera.head.simulation.gz-harmonic.v1',
    ObservationClock.ROS_SIMULATION_TIME,
    ObservationTransport.ROS2,
    'sensor-msgs.image-camera-info.v1',
)
PHYSICAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    'ros.camera.head.physical.standard-driver.v1',
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    'sensor-msgs.image-camera-info.v1',
)
CALIBRATION_ID = 'camera-calibration-sha256-' + '1' * 64


def _visual(provenance: ObservationProvenance, sensor: SensorIdentity) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=sensor,
        width=2,
        height=1,
        encoding='rgb8',
        step=6,
        data_size_bytes=6,
        is_bigendian=False,
        calibration_id=CALIBRATION_ID,
        observed_at_ns=100,
        provenance=provenance,
        availability=SensorAvailability.AVAILABLE,
    )


def verify_adversarial_contracts() -> None:
    trust = PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SIMULATION_TIME,
            sources=(
                PerceptionSourceContract(CAMERA_SENSOR, SIMULATION_PROVENANCE),
            ),
        )
    )
    physical = trust.admit(
        _visual(PHYSICAL_PROVENANCE, CAMERA_SENSOR),
        now_ns=100,
        received_at_monotonic_ns=1,
    )
    wrong_frame = trust.admit(
        _visual(
            SIMULATION_PROVENANCE,
            SensorIdentity(
                CAMERA_SENSOR.sensor_id,
                SensorKind.RGB_CAMERA,
                'head_camera_frame',
            ),
        ),
        now_ns=100,
        received_at_monotonic_ns=2,
    )
    malformed_rejected = False
    try:
        VisualFrameObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=CAMERA_SENSOR,
            width=2,
            height=1,
            encoding='unsupported',
            step=6,
            data_size_bytes=6,
            is_bigendian=False,
            calibration_id=CALIBRATION_ID,
            observed_at_ns=100,
            provenance=SIMULATION_PROVENANCE,
            availability=SensorAvailability.AVAILABLE,
        )
    except WorldModelValidationError:
        malformed_rejected = True
    assert physical.reason is AdmissionReason.CLOCK_DOMAIN_MISMATCH
    assert wrong_frame.reason is AdmissionReason.FRAME_MISMATCH
    assert malformed_rejected
    print(
        json.dumps(
            {
                'malformed_rejected': malformed_rejected,
                'physical_substitution': physical.reason.value,
                'wrong_frame': wrong_frame.reason.value,
            },
            separators=(',', ':'),
            sort_keys=True,
        )
    )


def publish_wrong_frame() -> None:
    rclpy.init()
    node = Node(
        'ayyo_visual_wrong_frame_fixture',
        parameter_overrides=[Parameter('use_sim_time', value=True)],
    )
    try:
        image_publisher = node.create_publisher(
            Image,
            IMAGE_TOPIC,
            qos_profile_sensor_data,
        )
        info_publisher = node.create_publisher(
            CameraInfo,
            CAMERA_INFO_TOPIC,
            qos_profile_sensor_data,
        )
        deadline = time.monotonic() + 5.0
        while node.get_clock().now().nanoseconds == 0 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        assert node.get_clock().now().nanoseconds > 0
        published = 0
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            stamp = node.get_clock().now().to_msg()
            image = Image()
            image.header.stamp = stamp
            image.header.frame_id = 'head_camera_frame'
            image.width = 2
            image.height = 1
            image.encoding = 'rgb8'
            image.step = 6
            image.data = [1, 2, 3, 4, 5, 6]
            info = CameraInfo()
            info.header.stamp = stamp
            info.header.frame_id = 'head_camera_frame'
            info.width = 2
            info.height = 1
            info.distortion_model = 'plumb_bob'
            info.k = [2.0, 0.0, 1.0, 0.0, 2.0, 0.5, 0.0, 0.0, 1.0]
            info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0]
            info.p = [
                2.0,
                0.0,
                1.0,
                0.0,
                0.0,
                2.0,
                0.5,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
            ]
            image_publisher.publish(image)
            info_publisher.publish(info)
            published += 1
            rclpy.spin_once(node, timeout_sec=0.05)
        print(json.dumps({'published_wrong_frame_pairs': published}))
    finally:
        node.destroy_node()
        rclpy.shutdown()


def verify_stream() -> None:
    rclpy.init()
    node = Node(
        'ayyo_visual_stream_verifier',
        parameter_overrides=[Parameter('use_sim_time', value=True)],
    )
    latest_image = None
    latest_info = None

    def on_image(message):
        nonlocal latest_image
        latest_image = message

    def on_info(message):
        nonlocal latest_info
        latest_info = message

    try:
        node.create_subscription(Image, IMAGE_TOPIC, on_image, qos_profile_sensor_data)
        node.create_subscription(
            CameraInfo,
            CAMERA_INFO_TOPIC,
            on_info,
            qos_profile_sensor_data,
        )
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if latest_image is None or latest_info is None:
                continue
            image_stamp = (
                latest_image.header.stamp.sec * 1_000_000_000
                + latest_image.header.stamp.nanosec
            )
            info_stamp = (
                latest_info.header.stamp.sec * 1_000_000_000
                + latest_info.header.stamp.nanosec
            )
            if image_stamp != info_stamp:
                continue
            assert image_stamp > 0
            assert latest_image.header.frame_id == 'head_camera_optical_frame'
            assert latest_info.header.frame_id == 'head_camera_optical_frame'
            assert (latest_image.width, latest_image.height) == (320, 240)
            assert (latest_info.width, latest_info.height) == (320, 240)
            assert latest_image.encoding == 'rgb8'
            assert latest_image.step == 960
            assert len(latest_image.data) == 230_400
            assert latest_info.distortion_model == 'plumb_bob'
            calibration_values = (
                tuple(latest_info.d)
                + tuple(latest_info.k)
                + tuple(latest_info.r)
                + tuple(latest_info.p)
            )
            assert calibration_values
            assert all(math.isfinite(value) for value in calibration_values)
            assert latest_info.k[0] > 0.0 and latest_info.k[4] > 0.0
            print(
                json.dumps(
                    {
                        'data_size_bytes': len(latest_image.data),
                        'encoding': latest_image.encoding,
                        'frame_id': latest_image.header.frame_id,
                        'height': latest_image.height,
                        'source_timestamp_ns': image_stamp,
                        'width': latest_image.width,
                    },
                    separators=(',', ':'),
                    sort_keys=True,
                )
            )
            return
        raise RuntimeError('timed out waiting for one exact Image/CameraInfo pair')
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenario',
        required=True,
        choices=('adversarial_contracts', 'verify_stream', 'wrong_frame'),
    )
    args = parser.parse_args()
    if args.scenario == 'adversarial_contracts':
        verify_adversarial_contracts()
    elif args.scenario == 'wrong_frame':
        publish_wrong_frame()
    else:
        verify_stream()


if __name__ == '__main__':
    main()
