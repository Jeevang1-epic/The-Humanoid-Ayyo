"""Deterministic TEST and simulation depth profiles; neither claims hardware."""

from __future__ import annotations

from dataclasses import dataclass
import struct

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
    DEPTH_INTERFACE,
    DepthCameraCalibration,
    DepthCalibrationSource,
    DepthCameraInfoMetadata,
    DepthImageMetadata,
    DepthSourceClassification,
    DepthSourceManifest,
    summarize_depth_image,
)


HEAD_DEPTH_SENSOR = SensorIdentity(
    "ayyo.camera.head.depth.v1",
    SensorKind.DEPTH_CAMERA,
    "head_depth_camera_optical_frame",
)
TEST_DEPTH_SOURCE_ID = "ros.camera.head.depth.test-fixture.v1"
SIMULATION_DEPTH_SOURCE_ID = "ros.camera.head.depth.simulation.gazebo.v1"
TEST_DEPTH_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    TEST_DEPTH_SOURCE_ID,
    ObservationClock.TEST_TIME,
    ObservationTransport.ROS2,
    DEPTH_INTERFACE,
)
SIMULATION_DEPTH_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.SIMULATION,
    SIMULATION_DEPTH_SOURCE_ID,
    ObservationClock.ROS_SIMULATION_TIME,
    ObservationTransport.ROS2,
    DEPTH_INTERFACE,
)


@dataclass(frozen=True, slots=True)
class DepthFixtureBundle:
    source: DepthSourceManifest
    calibration: DepthCameraCalibration


def _bundle(
    *,
    source_id: str,
    provenance: ObservationProvenance,
    classification: DepthSourceClassification,
    calibration_source: DepthCalibrationSource,
    width: int,
    height: int,
    encodings: tuple[str, ...],
) -> DepthFixtureBundle:
    calibration = DepthCameraCalibration(
        sensor=HEAD_DEPTH_SENSOR,
        source_id=source_id,
        mount_frame_id="head_depth_camera_frame",
        optical_frame_id=HEAD_DEPTH_SENSOR.frame_id,
        calibration_version=(
            "test.calibration.v1"
            if classification is DepthSourceClassification.TEST_FIXTURE
            else "gazebo.calibration.v1"
        ),
        calibration_source=calibration_source,
        import_identity=(
            "ayyo.depth.programmatic-test-fixture.v1"
            if classification is DepthSourceClassification.TEST_FIXTURE
            else "ayyo.description.gazebo-depth-model.v1"
        ),
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
    source = DepthSourceManifest(
        source_id=source_id,
        robot_id=AYYO_ROBOT_ID,
        sensor=HEAD_DEPTH_SENSOR,
        producer_id=(
            "ayyo.depth.test-adapter.v1"
            if classification is DepthSourceClassification.TEST_FIXTURE
            else "ayyo.depth.gazebo-adapter.v1"
        ),
        producer_version="1.0.0",
        producer_implementation_sha256=("d" * 64),
        provenance=provenance,
        classification=classification,
        mount_frame_id="head_depth_camera_frame",
        encodings=encodings,
        minimum_width=width,
        maximum_width=width,
        minimum_height=height,
        maximum_height=height,
        minimum_depth_m=0.1,
        maximum_depth_m=30.0,
        calibration_id=calibration.calibration.calibration_id,
        calibration_record_id=calibration.calibration_record_id,
    )
    return DepthFixtureBundle(source=source, calibration=calibration)


def depth_test_fixture_bundle(*, width: int = 4, height: int = 2) -> DepthFixtureBundle:
    return _bundle(
        source_id=TEST_DEPTH_SOURCE_ID,
        provenance=TEST_DEPTH_PROVENANCE,
        classification=DepthSourceClassification.TEST_FIXTURE,
        calibration_source=DepthCalibrationSource.TEST_FIXTURE,
        width=width,
        height=height,
        encodings=("16UC1", "32FC1"),
    )


def depth_simulation_bundle(*, width: int = 320, height: int = 240) -> DepthFixtureBundle:
    return _bundle(
        source_id=SIMULATION_DEPTH_SOURCE_ID,
        provenance=SIMULATION_DEPTH_PROVENANCE,
        classification=DepthSourceClassification.SIMULATION,
        calibration_source=DepthCalibrationSource.SIMULATION_MODEL,
        width=width,
        height=height,
        encodings=("32FC1",),
    )


def fixture_depth_bytes(
    width: int = 4,
    height: int = 2,
    *,
    encoding: str = "16UC1",
    is_bigendian: bool = False,
) -> bytes:
    count = width * height
    prefix = ">" if is_bigendian else "<"
    if encoding == "16UC1":
        values = tuple(1_000 + index * 100 for index in range(count))
        return struct.pack(f"{prefix}{count}H", *values)
    if encoding == "32FC1":
        values = tuple(1.0 + index * 0.1 for index in range(count))
        return struct.pack(f"{prefix}{count}f", *values)
    raise ValueError("fixture depth encoding is unsupported")


def fixture_depth_image_metadata(
    bundle: DepthFixtureBundle,
    session_id: str,
    observed_at_ns: int,
    *,
    encoding: str = "16UC1",
    data: bytes | None = None,
    frame_id: str | None = None,
    is_bigendian: bool = False,
) -> DepthImageMetadata:
    width = bundle.calibration.calibration.width
    height = bundle.calibration.calibration.height
    payload = (
        fixture_depth_bytes(
            width,
            height,
            encoding=encoding,
            is_bigendian=is_bigendian,
        )
        if data is None
        else data
    )
    bytes_per_pixel = 2 if encoding == "16UC1" else 4
    return summarize_depth_image(
        source=bundle.source,
        session_id=session_id,
        observed_at_ns=observed_at_ns,
        frame_id=(bundle.source.sensor.frame_id if frame_id is None else frame_id),
        width=width,
        height=height,
        encoding=encoding,
        step=width * bytes_per_pixel,
        is_bigendian=is_bigendian,
        data=payload,
    )


def fixture_depth_camera_info_metadata(
    bundle: DepthFixtureBundle,
    session_id: str,
    observed_at_ns: int,
    *,
    frame_id: str | None = None,
    calibration: DepthCameraCalibration | None = None,
) -> DepthCameraInfoMetadata:
    return DepthCameraInfoMetadata(
        source_id=bundle.source.source_id,
        session_id=session_id,
        robot_id=bundle.source.robot_id,
        sensor=bundle.source.sensor,
        frame_id=(bundle.source.sensor.frame_id if frame_id is None else frame_id),
        observed_at_ns=observed_at_ns,
        calibration=(bundle.calibration if calibration is None else calibration),
        provenance=bundle.source.provenance,
    )
