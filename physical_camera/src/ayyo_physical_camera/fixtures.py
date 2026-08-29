"""Small deterministic TEST-only physical-camera contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorIdentity,
    SensorKind,
)

from .models import (
    PhysicalCameraCalibration,
    PhysicalCameraCalibrationSource,
    PhysicalCameraImageMetadata,
    PhysicalCameraInfoMetadata,
    PhysicalCameraSourceClassification,
    PhysicalCameraSourceManifest,
)


FIXTURE_CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
FIXTURE_SOURCE_ID = "ros.camera.head.physical.test-fixture.v1"
FIXTURE_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    FIXTURE_SOURCE_ID,
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    "sensor-msgs.image-camera-info.v1",
)


@dataclass(frozen=True, slots=True)
class PhysicalCameraFixtureBundle:
    source: PhysicalCameraSourceManifest
    calibration: PhysicalCameraCalibration


def physical_camera_fixture_bundle(
    *,
    width: int = 4,
    height: int = 2,
) -> PhysicalCameraFixtureBundle:
    calibration = PhysicalCameraCalibration(
        camera=FIXTURE_CAMERA,
        source_id=FIXTURE_SOURCE_ID,
        camera_frame_id="head_camera_frame",
        optical_frame_id=FIXTURE_CAMERA.frame_id,
        calibration_version="test.calibration.v1",
        calibration_source=PhysicalCameraCalibrationSource.TEST_FIXTURE,
        import_identity="ayyo.physical-camera.programmatic-test-fixture.v1",
        calibration=CameraCalibration(
            width=width,
            height=height,
            distortion_model="plumb_bob",
            d=(0.0, 0.0, 0.0, 0.0, 0.0),
            k=(4.0, 0.0, width / 2.0, 0.0, 4.0, height / 2.0, 0.0, 0.0, 1.0),
            r=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            p=(4.0, 0.0, width / 2.0, 0.0, 0.0, 4.0, height / 2.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        ),
    )
    source = PhysicalCameraSourceManifest(
        source_id=FIXTURE_SOURCE_ID,
        robot_id=AYYO_ROBOT_ID,
        camera=FIXTURE_CAMERA,
        adapter_id="ayyo.physical-camera.test-adapter.v1",
        adapter_version="test.adapter.v1",
        adapter_implementation_sha256="a" * 64,
        provenance=FIXTURE_PROVENANCE,
        classification=PhysicalCameraSourceClassification.TEST_FIXTURE,
        camera_frame_id="head_camera_frame",
        encodings=("rgb8",),
        minimum_width=width,
        maximum_width=width,
        minimum_height=height,
        maximum_height=height,
        calibration_id=calibration.calibration.calibration_id,
        calibration_record_id=calibration.calibration_record_id,
        device_serial=None,
        device_fingerprint_sha256=None,
    )
    return PhysicalCameraFixtureBundle(source=source, calibration=calibration)


def fixture_image_metadata(
    bundle: PhysicalCameraFixtureBundle,
    session_id: str,
    observed_at_ns: int,
    **overrides,
) -> PhysicalCameraImageMetadata:
    width = bundle.calibration.calibration.width
    height = bundle.calibration.calibration.height
    values = {
        "source_id": bundle.source.source_id,
        "session_id": session_id,
        "robot_id": bundle.source.robot_id,
        "camera": bundle.source.camera,
        "frame_id": bundle.source.camera.frame_id,
        "observed_at_ns": observed_at_ns,
        "width": width,
        "height": height,
        "encoding": "rgb8",
        "step": width * 3,
        "data_size_bytes": width * height * 3,
        "is_bigendian": False,
        "provenance": bundle.source.provenance,
    }
    values.update(overrides)
    return PhysicalCameraImageMetadata(**values)


def fixture_camera_info_metadata(
    bundle: PhysicalCameraFixtureBundle,
    session_id: str,
    observed_at_ns: int,
    **overrides,
) -> PhysicalCameraInfoMetadata:
    values = {
        "source_id": bundle.source.source_id,
        "session_id": session_id,
        "robot_id": bundle.source.robot_id,
        "camera": bundle.source.camera,
        "frame_id": bundle.source.camera.frame_id,
        "observed_at_ns": observed_at_ns,
        "calibration": bundle.calibration,
        "provenance": bundle.source.provenance,
    }
    values.update(overrides)
    return PhysicalCameraInfoMetadata(**values)
