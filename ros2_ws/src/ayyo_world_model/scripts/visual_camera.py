#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Fixed ROS Image/CameraInfo decoder for compact visual evidence."""

from __future__ import annotations

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
    ObservationProvenance,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
)
from sensor_msgs.msg import CameraInfo, Image


IMAGE_TOPIC = '/ayyo/camera/head/image_raw'
CAMERA_INFO_TOPIC = '/ayyo/camera/head/camera_info'
HEAD_CAMERA_SENSOR = SensorIdentity(
    'ayyo.camera.head.rgb.v1',
    SensorKind.RGB_CAMERA,
    'head_camera_optical_frame',
)


class VisualCameraAdapterError(ValueError):
    """Raised when a standard ROS camera pair violates the reviewed contract."""


def message_time_ns(message) -> int:
    """Read one canonical ROS header timestamp without receipt-time fallback."""
    seconds = message.header.stamp.sec
    nanoseconds = message.header.stamp.nanosec
    if type(seconds) is not int or type(nanoseconds) is not int:
        raise VisualCameraAdapterError('camera source time fields must be integers')
    if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
        raise VisualCameraAdapterError('camera source time is outside its canonical range')
    value = seconds * 1_000_000_000 + nanoseconds
    if value == 0:
        raise VisualCameraAdapterError('camera acquisition time must be nonzero')
    return value


def normalize_camera_info(
    message: CameraInfo,
    *,
    expected_frame_id: str = HEAD_CAMERA_SENSOR.frame_id,
) -> CameraCalibration:
    """Validate bounded calibration metadata and derive its immutable identity."""
    if not isinstance(message, CameraInfo):
        raise VisualCameraAdapterError(
            'camera calibration must be sensor_msgs/CameraInfo'
        )
    message_time_ns(message)
    if message.header.frame_id != expected_frame_id:
        raise VisualCameraAdapterError(
            'CameraInfo frame does not match the reviewed optical frame'
        )
    roi = message.roi
    return CameraCalibration(
        width=message.width,
        height=message.height,
        distortion_model=message.distortion_model,
        d=tuple(float(value) for value in message.d),
        k=tuple(float(value) for value in message.k),
        r=tuple(float(value) for value in message.r),
        p=tuple(float(value) for value in message.p),
        binning_x=message.binning_x,
        binning_y=message.binning_y,
        roi=(
            roi.x_offset,
            roi.y_offset,
            roi.width,
            roi.height,
            roi.do_rectify,
        ),
    )


def normalize_visual_pair(
    image: Image,
    camera_info: CameraInfo,
    provenance: ObservationProvenance,
) -> VisualFrameObservation:
    """Validate one exact-time pair, then discard pixels from semantic state."""
    if not isinstance(image, Image):
        raise VisualCameraAdapterError('visual evidence must be sensor_msgs/Image')
    if type(provenance) is not ObservationProvenance:
        raise VisualCameraAdapterError('visual evidence requires reviewed provenance')
    image_time = message_time_ns(image)
    info_time = message_time_ns(camera_info)
    if image_time != info_time:
        raise VisualCameraAdapterError(
            'Image and CameraInfo acquisition timestamps must match exactly'
        )
    if image.header.frame_id != HEAD_CAMERA_SENSOR.frame_id:
        raise VisualCameraAdapterError(
            'Image frame does not match the reviewed optical frame'
        )
    calibration = normalize_camera_info(camera_info)
    if image.width != calibration.width or image.height != calibration.height:
        raise VisualCameraAdapterError(
            'Image and CameraInfo dimensions must match exactly'
        )
    if image.encoding != 'rgb8':
        raise VisualCameraAdapterError('head RGB camera encoding must be rgb8')
    if type(image.is_bigendian) is not int or image.is_bigendian not in {0, 1}:
        raise VisualCameraAdapterError('Image endian flag must be zero or one')
    data_size = len(image.data)
    if data_size == 0:
        raise VisualCameraAdapterError('Image must contain a nonempty pixel buffer')
    if image.step < image.width * 3 or data_size != image.step * image.height:
        raise VisualCameraAdapterError(
            'Image stride and pixel-buffer size are inconsistent'
        )
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=HEAD_CAMERA_SENSOR,
        width=image.width,
        height=image.height,
        encoding=image.encoding,
        step=image.step,
        data_size_bytes=data_size,
        is_bigendian=bool(image.is_bigendian),
        calibration_id=calibration.calibration_id,
        observed_at_ns=image_time,
        provenance=provenance,
        availability=SensorAvailability.AVAILABLE,
    )
