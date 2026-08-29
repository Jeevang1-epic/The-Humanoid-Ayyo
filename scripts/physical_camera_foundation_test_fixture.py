#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY physical-camera trust path, adversarial, and resource proof."""

from __future__ import annotations

import argparse
import json
import math
import time
import tracemalloc

from ayyo_perception import (
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_physical_camera import (
    PhysicalCameraCalibration,
    PhysicalCameraCalibrationSource,
    PhysicalCameraLifecycleAdapter,
    PhysicalCameraSourceRegistry,
    PhysicalCameraValidationError,
    fixture_camera_info_metadata,
    fixture_image_metadata,
    physical_camera_fixture_bundle,
)
from ayyo_working_memory import IngestionStatus, WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
    JointContract,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
)


CYCLE_COUNT = 5_000


def _configured_adapter(bundle):
    registry = PhysicalCameraSourceRegistry()
    registry.register(bundle.source)
    adapter = PhysicalCameraLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    return adapter


def _trust(bundle) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SYSTEM_TIME,
            sources=(
                PerceptionSourceContract(
                    bundle.source.camera,
                    bundle.source.provenance,
                ),
            ),
            physical_camera_requirements=(bundle.source.requirement(),),
            freshness_ns=500_000_000,
            retention_ttl_ns=2_000_000_000,
            permitted_future_skew_ns=50_000_000,
        )
    )


def _memory(bundle) -> WorkingMemory:
    catalog = RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract(
                "neck_yaw_joint",
                "revolute",
                -1.2,
                1.2,
                1.5,
                8.0,
            ),
        ),
    )
    return WorkingMemory(
        catalog,
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SYSTEM_TIME,
            allowed_provenance=(bundle.source.provenance,),
            sensors=(bundle.source.camera,),
            freshness_ns=500_000_000,
            retention_ttl_ns=2_000_000_000,
            permitted_future_skew_ns=50_000_000,
            recent_evidence_capacity=16,
            environment_entity_capacity=1,
        ),
    )


def _admit_pair(adapter, bundle, session, trust, memory, observed_at_ns, receipt):
    adapter.submit_camera_info(
        fixture_camera_info_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    sealed = adapter.submit_image(
        fixture_image_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    assert sealed is not None
    assert trust.authorize_physical_camera(sealed)
    for offset, observation in enumerate((sealed.frame, sealed.health)):
        admitted = trust.admit(
            observation,
            now_ns=observed_at_ns,
            received_at_monotonic_ns=receipt + offset,
        )
        assert admitted.status is AdmissionStatus.ACCEPTED
        retained = memory.ingest(
            admitted.observation,
            now_ns=observed_at_ns,
            received_at_monotonic_ns=receipt + offset,
        )
        assert retained.status is IngestionStatus.ACCEPTED
    return sealed


def run_offline() -> None:
    bundle = physical_camera_fixture_bundle()

    malformed_calibration_rejected = False
    try:
        PhysicalCameraCalibration(
            camera=bundle.source.camera,
            source_id=bundle.source.source_id,
            camera_frame_id=bundle.source.camera_frame_id,
            optical_frame_id=bundle.source.camera.frame_id,
            calibration_version="test.malformed.v1",
            calibration_source=PhysicalCameraCalibrationSource.TEST_FIXTURE,
            calibration=CameraCalibration(
                width=4,
                height=2,
                distortion_model="plumb_bob",
                d=(0.0,) * 5,
                k=(math.nan,) + bundle.calibration.calibration.k[1:],
                r=bundle.calibration.calibration.r,
                p=bundle.calibration.calibration.p,
            ),
        )
    except (PhysicalCameraValidationError, ValueError):
        malformed_calibration_rejected = True

    adversarial = _configured_adapter(bundle)
    first_session = adversarial.activate()
    wrong_frame_rejected = adversarial.submit_image(
        fixture_image_metadata(
            bundle,
            first_session,
            1_000_000_000,
            frame_id="head_camera_frame",
        ),
        now_ns=1_000_000_000,
    ) is None
    simulation_provenance = ObservationProvenance(
        ObservationSourceKind.SIMULATION,
        "ros.camera.head.simulation.spoof.v1",
        ObservationClock.ROS_SIMULATION_TIME,
        ObservationTransport.ROS2,
        "sensor-msgs.image-camera-info.v1",
    )
    simulation_spoof_rejected = adversarial.submit_image(
        fixture_image_metadata(
            bundle,
            first_session,
            1_000_000_001,
            source_id="ros.camera.head.simulation.spoof.v1",
            provenance=simulation_provenance,
        ),
        now_ns=1_000_000_001,
    ) is None
    adversarial.deactivate()
    inactive_evidence_rejected = adversarial.submit_image(
        fixture_image_metadata(bundle, first_session, 1_000_000_002),
        now_ns=1_000_000_002,
    ) is None
    second_session = adversarial.activate()
    old_session_rejected = adversarial.submit_image(
        fixture_image_metadata(bundle, first_session, 1_000_000_003),
        now_ns=1_000_000_003,
    ) is None
    recovery_trust = _trust(bundle)
    recovery_memory = _memory(bundle)
    recovered = _admit_pair(
        adversarial,
        bundle,
        second_session,
        recovery_trust,
        recovery_memory,
        1_000_000_004,
        1,
    )
    bare_trust = _trust(bundle)
    bare_bypass_rejected = bare_trust.admit(
        recovered.frame,
        now_ns=recovered.frame.observed_at_ns,
        received_at_monotonic_ns=1,
    ).status is AdmissionStatus.REJECTED

    adapter = _configured_adapter(bundle)
    session = adapter.activate()
    trust = _trust(bundle)
    memory = _memory(bundle)
    tracemalloc.start()
    try:
        for index in range(CYCLE_COUNT):
            observed_at_ns = 10_000_000_000 + index * 1_000_000
            _admit_pair(
                adapter,
                bundle,
                session,
                trust,
                memory,
                observed_at_ns,
                index * 2 + 1,
            )
        traced_current, traced_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    final_now_ns = 10_000_000_000 + (CYCLE_COUNT - 1) * 1_000_000
    first_snapshot = memory.current_snapshot(now_ns=final_now_ns)
    first_stats = memory.stats(now_ns=final_now_ns)
    second_snapshot = memory.current_snapshot(now_ns=final_now_ns)
    second_stats = memory.stats(now_ns=final_now_ns)
    camera_health = next(
        item
        for item in first_snapshot.robot.sensor_health_states
        if item.observation.sensor == bundle.source.camera
    )
    result = {
        "accepted_count": trust.stats().accepted_count,
        "adapter_accepted_pair_count": adapter.diagnostics.accepted_count,
        "adapter_rejected_count": adapter.diagnostics.rejected_count,
        "bare_perception_bypass_rejected": bare_bypass_rejected,
        "calibration_id": bundle.calibration.calibration.calibration_id,
        "calibration_record_id": bundle.calibration.calibration_record_id,
        "current_health_count": first_stats.current_sensor_health_count,
        "current_visual_count": first_stats.current_visual_count,
        "cycle_count": CYCLE_COUNT,
        "diagnostic_available": camera_health.availability.value,
        "diagnostic_detail": camera_health.observation.evidence_detail,
        "fixture_classification": bundle.source.classification.value,
        "inactive_evidence_rejected": inactive_evidence_rejected,
        "malformed_calibration_rejected": malformed_calibration_rejected,
        "old_session_rejected": old_session_rejected,
        "pending_camera_info_count": adapter.diagnostics.pending_camera_info_count,
        "pending_image_count": adapter.diagnostics.pending_image_count,
        "physical_authorization_count": trust.stats().tracked_physical_camera_count,
        "query_immutable": first_snapshot == second_snapshot and first_stats == second_stats,
        "recent_bounded_state_size": first_stats.recent_evidence_count,
        "retained_unique_state_count": (
            first_stats.retained_unique_observation_count
        ),
        "session_changed_on_reactivation": first_session != second_session,
        "simulation_spoof_rejected": simulation_spoof_rejected,
        "source_manifest_id": bundle.source.manifest_id,
        "source_reference_count": trust.stats().tracked_visual_source_count,
        "traced_python_current_bytes": traced_current,
        "traced_python_peak_bytes": traced_peak,
        "wrong_frame_rejected": wrong_frame_rejected,
    }
    print(
        "PHYSICAL_CAMERA_FOUNDATION_FIXTURE_RESULT="
        + json.dumps(result, separators=(",", ":"), sort_keys=True)
    )


def publish_ros_adversarial(scenario: str) -> None:
    """Publish bounded malformed ROS evidence into an isolated TEST graph."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image

    bundle = physical_camera_fixture_bundle()
    calibration = bundle.calibration.calibration
    rclpy.init()
    node = Node(f'ayyo_physical_camera_{scenario}_test_fixture')
    try:
        image_publisher = node.create_publisher(
            Image,
            '/ayyo/camera/head/image_raw',
            qos_profile_sensor_data,
        )
        info_publisher = node.create_publisher(
            CameraInfo,
            '/ayyo/camera/head/camera_info',
            qos_profile_sensor_data,
        )
        discovery_deadline = time.monotonic() + 5.0
        while time.monotonic() < discovery_deadline:
            if (
                image_publisher.get_subscription_count() > 0
                and info_publisher.get_subscription_count() > 0
            ):
                break
            rclpy.spin_once(node, timeout_sec=0.05)
        else:
            raise RuntimeError(
                'physical-camera adversarial fixture found no subscribers'
            )
        published = 0
        for _ in range(128):
            stamp = node.get_clock().now().to_msg()
            frame_id = (
                'head_camera_frame'
                if scenario == 'wrong_frame'
                else bundle.source.camera.frame_id
            )
            image = Image()
            image.header.stamp = stamp
            image.header.frame_id = frame_id
            image.width = calibration.width
            image.height = calibration.height
            image.encoding = 'rgb8'
            image.step = calibration.width * 3
            image.data = bytes(image.step * image.height)
            info = CameraInfo()
            info.header.stamp = stamp
            info.header.frame_id = frame_id
            info.width = calibration.width
            info.height = calibration.height
            info.distortion_model = calibration.distortion_model
            info.d = list(calibration.d)
            info.k = list(calibration.k)
            info.r = list(calibration.r)
            info.p = list(calibration.p)
            if scenario == 'malformed_calibration':
                info.k[0] = float('nan')
            info_publisher.publish(info)
            image_publisher.publish(image)
            published += 1
            rclpy.spin_once(node, timeout_sec=0.01)
        print(json.dumps({'published': published, 'scenario': scenario}))
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenario',
        choices=('offline', 'wrong_frame', 'malformed_calibration'),
        default='offline',
    )
    arguments = parser.parse_args()
    if arguments.scenario == 'offline':
        run_offline()
    else:
        publish_ros_adversarial(arguments.scenario)


if __name__ == "__main__":
    main()
