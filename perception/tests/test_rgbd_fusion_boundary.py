from dataclasses import replace

from ayyo_depth_camera import (
    DepthLifecycleAdapter,
    DepthSourceRegistry,
    depth_test_fixture_bundle,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
)
from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
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


def pipeline():
    depth_bundle = depth_test_fixture_bundle()
    registry = DepthSourceRegistry()
    registry.register(depth_bundle.source)
    depth_adapter = DepthLifecycleAdapter(registry)
    depth_adapter.configure(depth_bundle.source.source_id, depth_bundle.calibration)
    depth_session = depth_adapter.activate()
    rgb_bundle = physical_camera_fixture_bundle()
    requirement = rgbd_test_requirement(
        rgb_sensor=rgb_bundle.source.camera,
        rgb_provenance=RGB_PROVENANCE,
        rgb_calibration_id=rgb_bundle.calibration.calibration.calibration_id,
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
    boundary = PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(
                PerceptionSourceContract(requirement.rgb_sensor, RGB_PROVENANCE),
                PerceptionSourceContract(
                    requirement.depth_sensor,
                    depth_bundle.source.provenance,
                ),
                PerceptionSourceContract(
                    requirement.fusion_sensor,
                    requirement.fusion_provenance,
                ),
            ),
            depth_camera_requirements=(depth_bundle.source.requirement(),),
            rgbd_fusion_requirements=(requirement,),
        )
    )
    return depth_bundle, depth_adapter, depth_session, requirement, fusion, boundary


def rgb(requirement, source_time: int, **overrides) -> VisualFrameObservation:
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
        "observed_at_ns": source_time,
        "provenance": requirement.rgb_provenance,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def depth_admission(bundle, adapter, session, source_time):
    adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, source_time),
        now_ns=source_time,
    )
    result = adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session, source_time),
        now_ns=source_time,
    )
    assert result is not None
    return result


def test_fused_evidence_requires_both_admitted_components_and_seal() -> None:
    bundle, depth_adapter, session, requirement, fusion, boundary = pipeline()
    source_time = 1_000
    rgb_frame = rgb(requirement, source_time)
    sealed_depth = depth_admission(bundle, depth_adapter, session, source_time)
    fusion.submit_rgb(rgb_frame, now_ns=source_time)
    sealed_fusion = fusion.submit_depth(
        sealed_depth.frame,
        now_ns=source_time,
    )
    assert sealed_fusion is not None
    bare = boundary.admit(
        sealed_fusion.observation,
        now_ns=source_time,
        received_at_monotonic_ns=1,
    )
    assert bare.status is AdmissionStatus.REJECTED
    assert bare.reason is AdmissionReason.SOURCE_FRAME_NOT_ADMITTED
    assert boundary.admit(
        rgb_frame,
        now_ns=source_time,
        received_at_monotonic_ns=2,
    ).status is AdmissionStatus.ACCEPTED
    assert boundary.authorize_depth_camera(sealed_depth)
    assert boundary.admit(
        sealed_depth.frame,
        now_ns=source_time,
        received_at_monotonic_ns=3,
    ).status is AdmissionStatus.ACCEPTED
    assert boundary.authorize_rgbd_fusion(sealed_fusion)
    fused = boundary.admit(
        sealed_fusion.observation,
        now_ns=source_time,
        received_at_monotonic_ns=4,
    )
    assert fused.status is AdmissionStatus.ACCEPTED
    assert boundary.stats().tracked_rgbd_fusion_count == 0


def test_wrong_component_and_reset_cannot_authorize_fusion() -> None:
    bundle, depth_adapter, session, requirement, fusion, boundary = pipeline()
    source_time = 2_000
    rgb_frame = rgb(requirement, source_time)
    sealed_depth = depth_admission(bundle, depth_adapter, session, source_time)
    fusion.submit_rgb(rgb_frame, now_ns=source_time)
    sealed_fusion = fusion.submit_depth(sealed_depth.frame, now_ns=source_time)
    assert sealed_fusion is not None
    boundary.admit(rgb_frame, now_ns=source_time, received_at_monotonic_ns=1)
    boundary.authorize_depth_camera(sealed_depth)
    boundary.admit(
        sealed_depth.frame,
        now_ns=source_time,
        received_at_monotonic_ns=2,
    )
    assert boundary.authorize_rgbd_fusion(sealed_fusion)
    boundary.reset()
    rejected = boundary.admit(
        sealed_fusion.observation,
        now_ns=source_time,
        received_at_monotonic_ns=3,
    )
    assert rejected.status is AdmissionStatus.REJECTED
    forged = rgb(
        requirement,
        source_time,
        provenance=replace(RGB_PROVENANCE, source_id="forged.rgb.v1"),
    )
    assert boundary.admit(
        forged,
        now_ns=source_time,
        received_at_monotonic_ns=4,
    ).status is AdmissionStatus.REJECTED
