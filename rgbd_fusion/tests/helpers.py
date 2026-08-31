"""Deterministic compact RGB-D evidence helpers."""

from ayyo_depth_camera import (
    DepthLifecycleAdapter,
    DepthSourceRegistry,
    depth_test_fixture_bundle,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
)
from ayyo_physical_camera import physical_camera_fixture_bundle
from ayyo_rgbd_fusion import RgbdFusionLifecycleAdapter, rgbd_test_requirement
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    VisualFrameObservation,
)


RGB_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "ros.camera.head.rgb.depth.test-fixture.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.ROS2,
    "sensor-msgs.image-camera-info.v1",
)


def configured_pair():
    depth_bundle = depth_test_fixture_bundle()
    depth_registry = DepthSourceRegistry()
    depth_registry.register(depth_bundle.source)
    depth_adapter = DepthLifecycleAdapter(depth_registry)
    depth_adapter.configure(depth_bundle.source.source_id, depth_bundle.calibration)
    depth_session = depth_adapter.activate()
    rgb_calibration = physical_camera_fixture_bundle().calibration.calibration
    requirement = rgbd_test_requirement(
        rgb_sensor=physical_camera_fixture_bundle().source.camera,
        rgb_provenance=RGB_PROVENANCE,
        rgb_calibration_id=rgb_calibration.calibration_id,
        depth_sensor=depth_bundle.source.sensor,
        depth_provenance=depth_bundle.source.provenance,
        depth_calibration_id=depth_bundle.calibration.calibration.calibration_id,
        depth_producer_id=depth_bundle.source.producer_id,
        depth_producer_implementation_sha256=(
            depth_bundle.source.producer_implementation_sha256
        ),
        depth_source_fingerprint_sha256=(
            depth_bundle.source.manifest_id.removeprefix(
                "depth-camera-source-sha256-"
            )
        ),
    )
    fusion = RgbdFusionLifecycleAdapter()
    fusion.configure(requirement)
    fusion.activate(depth_session_id=depth_session)
    return depth_bundle, depth_adapter, depth_session, requirement, fusion


def rgb(requirement, observed_at_ns: int, **overrides):
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": requirement.rgb_sensor,
        "width": 4,
        "height": 2,
        "encoding": "rgb8",
        "step": 12,
        "data_size_bytes": 24,
        "is_bigendian": False,
        "calibration_id": requirement.rgb_calibration_id,
        "observed_at_ns": observed_at_ns,
        "provenance": requirement.rgb_provenance,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def depth_admission(bundle, adapter, session_id: str, observed_at_ns: int):
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, session_id, observed_at_ns),
        now_ns=observed_at_ns,
    ) is None
    admission = adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session_id, observed_at_ns),
        now_ns=observed_at_ns,
    )
    assert admission is not None
    return admission
