#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""ROS Image/CameraInfo normalization for the sealed depth-camera core."""

from __future__ import annotations

from ayyo_depth_camera import (
    DepthCameraCalibration,
    DepthCameraInfoMetadata,
    DepthImageMetadata,
    DepthSourceManifest,
    summarize_depth_image,
)
from sensor_msgs.msg import CameraInfo, Image
from visual_camera import (
    message_time_ns,
    normalize_camera_info,
    VisualCameraAdapterError,
)


class DepthCameraRosAdapterError(ValueError):
    """A ROS message cannot satisfy the reviewed head-depth contract."""


def normalize_depth_image(
    message: Image,
    source: DepthSourceManifest,
    session_id: str,
) -> DepthImageMetadata:
    """Validate raw callback bytes and return only compact immutable metadata."""
    if not isinstance(message, Image):
        raise DepthCameraRosAdapterError(
            'depth evidence must be sensor_msgs/Image'
        )
    if type(message.is_bigendian) is not int or message.is_bigendian not in {0, 1}:
        raise DepthCameraRosAdapterError(
            'depth Image endian flag must be zero or one'
        )
    if message.header.frame_id != source.sensor.frame_id:
        raise DepthCameraRosAdapterError(
            'depth Image frame does not match the reviewed optical frame'
        )
    try:
        return summarize_depth_image(
            source=source,
            session_id=session_id,
            observed_at_ns=message_time_ns(message),
            frame_id=message.header.frame_id,
            width=message.width,
            height=message.height,
            encoding=message.encoding,
            step=message.step,
            is_bigendian=bool(message.is_bigendian),
            data=bytes(message.data),
        )
    except (TypeError, ValueError) as error:
        raise DepthCameraRosAdapterError(str(error)) from error


def normalize_depth_camera_info(
    message: CameraInfo,
    source: DepthSourceManifest,
    session_id: str,
    configured: DepthCameraCalibration,
) -> DepthCameraInfoMetadata:
    """Require exact source frame, source session, and configured calibration."""
    if not isinstance(message, CameraInfo):
        raise DepthCameraRosAdapterError(
            'depth calibration must be sensor_msgs/CameraInfo'
        )
    if message.header.frame_id != source.sensor.frame_id:
        raise DepthCameraRosAdapterError(
            'depth CameraInfo frame does not match the reviewed optical frame'
        )
    try:
        normalized = normalize_camera_info(
            message,
            expected_frame_id=source.sensor.frame_id,
        )
        if normalized != configured.calibration:
            raise DepthCameraRosAdapterError(
                'depth CameraInfo does not equal the configured calibration'
            )
        return DepthCameraInfoMetadata(
            source_id=source.source_id,
            session_id=session_id,
            robot_id=source.robot_id,
            sensor=source.sensor,
            frame_id=message.header.frame_id,
            observed_at_ns=message_time_ns(message),
            calibration=configured,
            provenance=source.provenance,
        )
    except (TypeError, ValueError, VisualCameraAdapterError) as error:
        if isinstance(error, DepthCameraRosAdapterError):
            raise
        raise DepthCameraRosAdapterError(str(error)) from error
