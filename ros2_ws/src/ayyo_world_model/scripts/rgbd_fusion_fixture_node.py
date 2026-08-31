#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY publisher for exact-time canonical RGB and depth pairs."""

from __future__ import annotations

from ayyo_depth_camera import (
    DEPTH_CAMERA_INFO_TOPIC,
    DEPTH_IMAGE_TOPIC,
    depth_test_fixture_bundle,
    fixture_depth_bytes,
)
from ayyo_physical_camera import physical_camera_fixture_bundle
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from visual_camera import CAMERA_INFO_TOPIC, IMAGE_TOPIC


def _camera_info(stamp, frame_id: str, calibration) -> CameraInfo:
    message = CameraInfo()
    message.header.stamp = stamp
    message.header.frame_id = frame_id
    message.width = calibration.width
    message.height = calibration.height
    message.distortion_model = calibration.distortion_model
    message.d = list(calibration.d)
    message.k = list(calibration.k)
    message.r = list(calibration.r)
    message.p = list(calibration.p)
    message.binning_x = calibration.binning_x
    message.binning_y = calibration.binning_y
    (
        message.roi.x_offset,
        message.roi.y_offset,
        message.roi.width,
        message.roi.height,
        message.roi.do_rectify,
    ) = calibration.roi
    return message


class RgbdFusionFixtureNode(Node):
    """Publish tiny deterministic TEST data with one shared source timestamp."""

    def __init__(self) -> None:
        super().__init__('ayyo_head_rgbd_fusion_test_fixture')
        self._rgb = physical_camera_fixture_bundle()
        self._depth = depth_test_fixture_bundle()
        self._rgb_image_publisher = self.create_publisher(
            Image,
            IMAGE_TOPIC,
            qos_profile_sensor_data,
        )
        self._rgb_info_publisher = self.create_publisher(
            CameraInfo,
            CAMERA_INFO_TOPIC,
            qos_profile_sensor_data,
        )
        self._depth_image_publisher = self.create_publisher(
            Image,
            DEPTH_IMAGE_TOPIC,
            qos_profile_sensor_data,
        )
        self._depth_info_publisher = self.create_publisher(
            CameraInfo,
            DEPTH_CAMERA_INFO_TOPIC,
            qos_profile_sensor_data,
        )
        self._timer = self.create_timer(0.1, self._publish_pair)

    def _publish_pair(self) -> None:
        stamp = self.get_clock().now().to_msg()
        rgb_calibration = self._rgb.calibration.calibration
        rgb_image = Image()
        rgb_image.header.stamp = stamp
        rgb_image.header.frame_id = self._rgb.source.camera.frame_id
        rgb_image.width = rgb_calibration.width
        rgb_image.height = rgb_calibration.height
        rgb_image.encoding = 'rgb8'
        rgb_image.is_bigendian = 0
        rgb_image.step = rgb_calibration.width * 3
        rgb_image.data = bytes(
            index % 251
            for index in range(rgb_image.step * rgb_image.height)
        )
        rgb_info = _camera_info(
            stamp,
            self._rgb.source.camera.frame_id,
            rgb_calibration,
        )

        depth_calibration = self._depth.calibration.calibration
        depth_image = Image()
        depth_image.header.stamp = stamp
        depth_image.header.frame_id = self._depth.source.sensor.frame_id
        depth_image.width = depth_calibration.width
        depth_image.height = depth_calibration.height
        depth_image.encoding = '16UC1'
        depth_image.is_bigendian = 0
        depth_image.step = depth_calibration.width * 2
        depth_image.data = fixture_depth_bytes(
            depth_calibration.width,
            depth_calibration.height,
        )
        depth_info = _camera_info(
            stamp,
            self._depth.source.sensor.frame_id,
            depth_calibration,
        )

        self._rgb_info_publisher.publish(rgb_info)
        self._depth_info_publisher.publish(depth_info)
        self._rgb_image_publisher.publish(rgb_image)
        self._depth_image_publisher.publish(depth_image)


def main() -> None:
    rclpy.init()
    node = RgbdFusionFixtureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
