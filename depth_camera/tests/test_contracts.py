from __future__ import annotations

from dataclasses import replace
import math
import struct

import pytest

from ayyo_depth_camera import (
    DEPTH_CAMERA_INFO_TOPIC,
    DEPTH_IMAGE_TOPIC,
    HEAD_DEPTH_SENSOR,
    DepthCameraCalibration,
    DepthCameraValidationError,
    DepthCalibrationSource,
    DepthSourceClassification,
    TEST_DEPTH_PROVENANCE,
    depth_simulation_bundle,
    depth_test_fixture_bundle,
    fixture_depth_bytes,
    fixture_depth_image_metadata,
    summarize_depth_image,
)
from ayyo_world_model import CameraCalibration, ObservationSourceKind, SensorKind


def test_depth_identity_and_topics_are_exact() -> None:
    assert HEAD_DEPTH_SENSOR.sensor_id == 'ayyo.camera.head.depth.v1'
    assert HEAD_DEPTH_SENSOR.kind is SensorKind.DEPTH_CAMERA
    assert HEAD_DEPTH_SENSOR.frame_id == 'head_depth_camera_optical_frame'
    assert DEPTH_IMAGE_TOPIC == '/ayyo/camera/head/depth/image_raw'
    assert DEPTH_CAMERA_INFO_TOPIC == '/ayyo/camera/head/depth/camera_info'


def test_test_and_simulation_profiles_are_distinct() -> None:
    test = depth_test_fixture_bundle()
    simulation = depth_simulation_bundle()
    assert test.source != simulation.source
    assert test.source.classification is DepthSourceClassification.TEST_FIXTURE
    assert simulation.source.classification is DepthSourceClassification.SIMULATION
    assert test.source.provenance.source_kind is ObservationSourceKind.TEST_FIXTURE
    assert simulation.source.provenance.source_kind is ObservationSourceKind.SIMULATION
    assert test.source.manifest_id != simulation.source.manifest_id


def test_manifest_and_calibration_fingerprints_are_deterministic() -> None:
    first = depth_test_fixture_bundle()
    second = depth_test_fixture_bundle()
    assert first == second
    assert first.source.manifest_id.startswith('depth-camera-source-sha256-')
    assert first.calibration.calibration_record_id.startswith(
        'depth-camera-calibration-sha256-'
    )


def test_source_classification_cannot_substitute_provenance() -> None:
    source = depth_test_fixture_bundle().source
    with pytest.raises(DepthCameraValidationError, match='cannot substitute'):
        replace(
            source,
            classification=DepthSourceClassification.SIMULATION,
            manifest_id=None,
        )


def test_nonphysical_source_cannot_claim_device_identity() -> None:
    source = depth_test_fixture_bundle().source
    with pytest.raises(DepthCameraValidationError, match='physical device identity'):
        replace(source, device_serial='spoofed', manifest_id=None)


def test_calibration_rejects_nonfinite_matrix() -> None:
    bundle = depth_test_fixture_bundle()
    calibration = bundle.calibration.calibration
    with pytest.raises(ValueError, match='finite real number'):
        DepthCameraCalibration(
            sensor=bundle.source.sensor,
            source_id=bundle.source.source_id,
            mount_frame_id=bundle.source.mount_frame_id,
            optical_frame_id=bundle.source.sensor.frame_id,
            calibration_version='bad.v1',
            calibration_source=DepthCalibrationSource.TEST_FIXTURE,
            calibration=CameraCalibration(
                width=calibration.width,
                height=calibration.height,
                distortion_model='plumb_bob',
                d=calibration.d,
                k=(math.nan,) + calibration.k[1:],
                r=calibration.r,
                p=calibration.p,
            ),
        )


def test_calibration_rejects_wrong_optical_frame() -> None:
    bundle = depth_test_fixture_bundle()
    with pytest.raises(DepthCameraValidationError, match='frames conflict'):
        replace(bundle.calibration, optical_frame_id='head_camera_optical_frame')


def test_16uc1_summary_uses_millimetres_and_retains_no_pixels() -> None:
    bundle = depth_test_fixture_bundle()
    image = fixture_depth_image_metadata(bundle, 'depth-camera-session-sha256-' + 'a' * 64, 1)
    assert image.valid_depth_count == 8
    assert image.invalid_depth_count == 0
    assert image.minimum_depth_m == 1.0
    assert image.maximum_depth_m == 1.7
    assert not hasattr(image, 'data')


def test_32fc1_nan_is_explicit_invalid_sentinel() -> None:
    bundle = depth_test_fixture_bundle()
    data = struct.pack('<8f', 1.0, math.nan, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7)
    image = summarize_depth_image(
        source=bundle.source,
        session_id='depth-camera-session-sha256-' + 'b' * 64,
        observed_at_ns=1,
        frame_id=bundle.source.sensor.frame_id,
        width=4,
        height=2,
        encoding='32FC1',
        step=16,
        is_bigendian=False,
        data=data,
    )
    assert image.valid_depth_count == 7
    assert image.invalid_depth_count == 1
    assert image.minimum_depth_m == 1.0


@pytest.mark.parametrize('value', [math.inf, -math.inf, -1.0])
def test_32fc1_rejects_infinite_or_negative_values(value: float) -> None:
    bundle = depth_test_fixture_bundle()
    data = struct.pack('<8f', value, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6)
    with pytest.raises(DepthCameraValidationError):
        summarize_depth_image(
            source=bundle.source,
            session_id='depth-camera-session-sha256-' + 'c' * 64,
            observed_at_ns=1,
            frame_id=bundle.source.sensor.frame_id,
            width=4,
            height=2,
            encoding='32FC1',
            step=16,
            is_bigendian=False,
            data=data,
        )


def test_all_invalid_depth_fails_closed() -> None:
    bundle = depth_test_fixture_bundle()
    with pytest.raises(DepthCameraValidationError, match='no valid'):
        fixture_depth_image_metadata(bundle, 'depth-camera-session-sha256-' + 'd' * 64, 1, data=bytes(16))


@pytest.mark.parametrize(
    ('encoding', 'step', 'data'),
    [
        ('mono8', 4, bytes(8)),
        ('16UC1', 7, bytes(14)),
        ('16UC1', 8, b''),
        ('16UC1', 8, bytes(15)),
    ],
)
def test_encoding_step_empty_and_byte_mismatch_fail_closed(
    encoding: str,
    step: int,
    data: bytes,
) -> None:
    bundle = depth_test_fixture_bundle()
    with pytest.raises(DepthCameraValidationError):
        summarize_depth_image(
            source=bundle.source,
            session_id='depth-camera-session-sha256-' + 'e' * 64,
            observed_at_ns=1,
            frame_id=bundle.source.sensor.frame_id,
            width=4,
            height=2,
            encoding=encoding,
            step=step,
            is_bigendian=False,
            data=data,
        )


def test_value_outside_reviewed_range_fails_closed() -> None:
    bundle = depth_test_fixture_bundle()
    data = struct.pack('<8H', 31_000, 1_000, 1_100, 1_200, 1_300, 1_400, 1_500, 1_600)
    with pytest.raises(DepthCameraValidationError, match='metric range'):
        fixture_depth_image_metadata(
            bundle,
            'depth-camera-session-sha256-' + 'f' * 64,
            1,
            data=data,
        )


def test_big_endian_summary_is_explicit() -> None:
    bundle = depth_test_fixture_bundle()
    data = fixture_depth_bytes(is_bigendian=True)
    image = fixture_depth_image_metadata(
        bundle,
        'depth-camera-session-sha256-' + '1' * 64,
        1,
        data=data,
        is_bigendian=True,
    )
    assert image.is_bigendian is True
    assert image.minimum_depth_m == 1.0
    assert image.maximum_depth_m == 1.7


def test_payload_fingerprint_changes_with_measurements() -> None:
    bundle = depth_test_fixture_bundle()
    first = fixture_depth_image_metadata(bundle, 'depth-camera-session-sha256-' + '2' * 64, 1)
    changed = struct.pack('<8H', 1_001, 1_100, 1_200, 1_300, 1_400, 1_500, 1_600, 1_700)
    second = fixture_depth_image_metadata(
        bundle,
        first.session_id,
        1,
        data=changed,
    )
    assert first.payload_sha256 != second.payload_sha256
