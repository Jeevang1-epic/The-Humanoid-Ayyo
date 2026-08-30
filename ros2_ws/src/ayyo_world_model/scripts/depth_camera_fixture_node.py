#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY standard ROS publisher for the head-depth adapter fixture."""

from __future__ import annotations

from ayyo_depth_camera import (
    DEPTH_CAMERA_INFO_TOPIC,
    DEPTH_IMAGE_TOPIC,
    depth_test_fixture_bundle,
    fixture_depth_bytes,
)
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


class DepthCameraFixtureNode(Node):
    """Publish tiny deterministic depth pairs; this is not a device driver."""

    def __init__(self) -> None:
        super().__init__('ayyo_head_depth_test_fixture')
        self._bundle = depth_test_fixture_bundle()
        self._image_publisher = self.create_publisher(
            Image,
            DEPTH_IMAGE_TOPIC,
            qos_profile_sensor_data,
        )
        self._camera_info_publisher = self.create_publisher(
            CameraInfo,
            DEPTH_CAMERA_INFO_TOPIC,
            qos_profile_sensor_data,
        )
        self._timer = self.create_timer(0.1, self._publish_pair)

    def _publish_pair(self) -> None:
        calibration = self._bundle.calibration.calibration
        stamp = self.get_clock().now().to_msg()
        image = Image()
        image.header.stamp = stamp
        image.header.frame_id = self._bundle.source.sensor.frame_id
        image.width = calibration.width
        image.height = calibration.height
        image.encoding = '16UC1'
        image.is_bigendian = 0
        image.step = calibration.width * 2
        image.data = fixture_depth_bytes(calibration.width, calibration.height)
        camera_info = CameraInfo()
        camera_info.header.stamp = stamp
        camera_info.header.frame_id = self._bundle.source.sensor.frame_id
        camera_info.width = calibration.width
        camera_info.height = calibration.height
        camera_info.distortion_model = calibration.distortion_model
        camera_info.d = list(calibration.d)
        camera_info.k = list(calibration.k)
        camera_info.r = list(calibration.r)
        camera_info.p = list(calibration.p)
        camera_info.binning_x = calibration.binning_x
        camera_info.binning_y = calibration.binning_y
        (
            camera_info.roi.x_offset,
            camera_info.roi.y_offset,
            camera_info.roi.width,
            camera_info.roi.height,
            camera_info.roi.do_rectify,
        ) = calibration.roi
        self._camera_info_publisher.publish(camera_info)
        self._image_publisher.publish(image)


def main() -> None:
    rclpy.init()
    node = DepthCameraFixtureNode()
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
