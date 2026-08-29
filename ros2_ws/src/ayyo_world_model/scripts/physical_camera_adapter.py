#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""ROS Image/CameraInfo normalization for the sealed physical-camera core."""

from __future__ import annotations

from ayyo_physical_camera import (
    PhysicalCameraCalibration,
    PhysicalCameraImageMetadata,
    PhysicalCameraInfoMetadata,
    PhysicalCameraSourceManifest,
)
from sensor_msgs.msg import CameraInfo, Image
from visual_camera import message_time_ns, normalize_camera_info


class PhysicalCameraRosAdapterError(ValueError):
    """A ROS message cannot satisfy the configured physical source contract."""


def normalize_physical_image_metadata(
    message: Image,
    source: PhysicalCameraSourceManifest,
    session_id: str,
) -> PhysicalCameraImageMetadata:
    """Copy bounded metadata only; raw pixel bytes remain in the callback scope."""
    if not isinstance(message, Image):
        raise PhysicalCameraRosAdapterError(
            'physical camera evidence must be sensor_msgs/Image'
        )
    if type(source) is not PhysicalCameraSourceManifest:
        raise PhysicalCameraRosAdapterError(
            'physical camera requires one configured source manifest'
        )
    observed_at_ns = message_time_ns(message)
    if message.header.frame_id != source.camera.frame_id:
        raise PhysicalCameraRosAdapterError(
            'physical Image frame does not match the reviewed optical frame'
        )
    if message.encoding != 'rgb8':
        raise PhysicalCameraRosAdapterError(
            'physical head camera v1 accepts only rgb8'
        )
    if type(message.is_bigendian) is not int or message.is_bigendian not in {0, 1}:
        raise PhysicalCameraRosAdapterError(
            'physical Image endian flag must be zero or one'
        )
    data_size = len(message.data)
    if data_size == 0:
        raise PhysicalCameraRosAdapterError(
            'physical Image must contain a nonempty pixel buffer'
        )
    return PhysicalCameraImageMetadata(
        source_id=source.source_id,
        session_id=session_id,
        robot_id=source.robot_id,
        camera=source.camera,
        frame_id=message.header.frame_id,
        observed_at_ns=observed_at_ns,
        width=message.width,
        height=message.height,
        encoding=message.encoding,
        step=message.step,
        data_size_bytes=data_size,
        is_bigendian=bool(message.is_bigendian),
        provenance=source.provenance,
    )


def normalize_physical_camera_info_metadata(
    message: CameraInfo,
    source: PhysicalCameraSourceManifest,
    session_id: str,
    configured: PhysicalCameraCalibration,
) -> PhysicalCameraInfoMetadata:
    """Validate CameraInfo and require the exact configured calibration record."""
    if not isinstance(message, CameraInfo):
        raise PhysicalCameraRosAdapterError(
            'physical calibration must be sensor_msgs/CameraInfo'
        )
    if type(source) is not PhysicalCameraSourceManifest:
        raise PhysicalCameraRosAdapterError(
            'physical camera requires one configured source manifest'
        )
    if type(configured) is not PhysicalCameraCalibration:
        raise PhysicalCameraRosAdapterError(
            'physical camera requires one configured calibration'
        )
    observed_at_ns = message_time_ns(message)
    if message.header.frame_id != source.camera.frame_id:
        raise PhysicalCameraRosAdapterError(
            'physical CameraInfo frame does not match the reviewed optical frame'
        )
    normalized = normalize_camera_info(message)
    if normalized != configured.calibration:
        raise PhysicalCameraRosAdapterError(
            'physical CameraInfo does not equal the configured calibration'
        )
    return PhysicalCameraInfoMetadata(
        source_id=source.source_id,
        session_id=session_id,
        robot_id=source.robot_id,
        camera=source.camera,
        frame_id=message.header.frame_id,
        observed_at_ns=observed_at_ns,
        calibration=configured,
        provenance=source.provenance,
    )
