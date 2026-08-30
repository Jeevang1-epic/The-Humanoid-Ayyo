#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY depth trust-path, adversarial, and resource-bound proof."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
import struct
import time
import tracemalloc

from ayyo_depth_camera import (
    DepthCameraCalibration,
    DepthCameraValidationError,
    DepthCalibrationSource,
    DepthLifecycleAdapter,
    DepthSourceClassification,
    DepthSourceRegistry,
    depth_simulation_bundle,
    depth_test_fixture_bundle,
    fixture_depth_bytes,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
    summarize_depth_image,
)
from ayyo_perception import (
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_working_memory import IngestionStatus, WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
    JointContract,
    ObservationClock,
    ObservationFingerprint,
    ObservationFingerprintKind,
    ObservationIdentityError,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
    SensorIdentity,
    SensorKind,
    WorldModelValidationError,
)


CYCLE_COUNT = 5_000


def _configured_adapter(bundle, **time_bounds) -> DepthLifecycleAdapter:
    registry = DepthSourceRegistry()
    registry.register(bundle.source)
    adapter = DepthLifecycleAdapter(registry, **time_bounds)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    return adapter


def _trust(bundle) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=bundle.source.provenance.clock,
            sources=(
                PerceptionSourceContract(
                    bundle.source.sensor,
                    bundle.source.provenance,
                ),
            ),
            depth_camera_requirements=(bundle.source.requirement(),),
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
                'neck_yaw_joint',
                'revolute',
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
            source_clock=bundle.source.provenance.clock,
            allowed_provenance=(bundle.source.provenance,),
            sensors=(bundle.source.sensor,),
            freshness_ns=500_000_000,
            retention_ttl_ns=2_000_000_000,
            permitted_future_skew_ns=50_000_000,
            recent_evidence_capacity=16,
            environment_entity_capacity=1,
        ),
    )


def _admit_pair(
    adapter,
    bundle,
    session,
    trust,
    memory,
    observed_at_ns,
    receipt,
):
    adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    sealed = adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    assert sealed is not None
    assert trust.authorize_depth_camera(sealed)
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


def _image_rejected(bundle, session: str, **overrides) -> bool:
    calibration = bundle.calibration.calibration
    values = {
        'source': bundle.source,
        'session_id': session,
        'observed_at_ns': 1_000_000_000,
        'frame_id': bundle.source.sensor.frame_id,
        'width': calibration.width,
        'height': calibration.height,
        'encoding': '16UC1',
        'step': calibration.width * 2,
        'is_bigendian': False,
        'data': fixture_depth_bytes(calibration.width, calibration.height),
    }
    values.update(overrides)
    try:
        summarize_depth_image(**values)
    except (DepthCameraValidationError, TypeError, ValueError):
        return True
    return False


def _malformed_calibration_rejected(bundle) -> bool:
    calibration = bundle.calibration.calibration
    try:
        DepthCameraCalibration(
            sensor=bundle.source.sensor,
            source_id=bundle.source.source_id,
            mount_frame_id=bundle.source.mount_frame_id,
            optical_frame_id=bundle.source.sensor.frame_id,
            calibration_version='test.malformed.v1',
            calibration_source=DepthCalibrationSource.TEST_FIXTURE,
            calibration=CameraCalibration(
                width=calibration.width,
                height=calibration.height,
                distortion_model=calibration.distortion_model,
                d=calibration.d,
                k=(math.nan,) + calibration.k[1:],
                r=calibration.r,
                p=calibration.p,
            ),
        )
    except (DepthCameraValidationError, WorldModelValidationError, ValueError):
        return True
    return False


def run_offline() -> None:
    bundle = depth_test_fixture_bundle()
    fake_session = 'depth-camera-session-sha256-' + '9' * 64
    invalid_payload_checks = {
        'empty_payload_rejected': _image_rejected(bundle, fake_session, data=b''),
        'unsupported_encoding_rejected': _image_rejected(
            bundle,
            fake_session,
            encoding='mono16',
        ),
        'impossible_step_rejected': _image_rejected(
            bundle,
            fake_session,
            step=7,
        ),
        'byte_mismatch_rejected': _image_rejected(
            bundle,
            fake_session,
            data=bytes(15),
        ),
        'invalid_range_rejected': _image_rejected(
            bundle,
            fake_session,
            data=struct.pack('<8H', 31_000, 1_000, 1_100, 1_200, 1_300, 1_400, 1_500, 1_600),
        ),
        'infinite_depth_rejected': _image_rejected(
            bundle,
            fake_session,
            encoding='32FC1',
            step=16,
            data=struct.pack('<8f', math.inf, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6),
        ),
        'negative_depth_rejected': _image_rejected(
            bundle,
            fake_session,
            encoding='32FC1',
            step=16,
            data=struct.pack('<8f', -1.0, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6),
        ),
        'all_invalid_rejected': _image_rejected(
            bundle,
            fake_session,
            data=bytes(16),
        ),
    }
    nan_summary = summarize_depth_image(
        source=bundle.source,
        session_id=fake_session,
        observed_at_ns=1_000_000_000,
        frame_id=bundle.source.sensor.frame_id,
        width=4,
        height=2,
        encoding='32FC1',
        step=16,
        is_bigendian=False,
        data=struct.pack('<8f', math.nan, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6),
    )

    classification_substitution_rejected = False
    try:
        replace(
            bundle.source,
            classification=DepthSourceClassification.SIMULATION,
            manifest_id=None,
        )
    except DepthCameraValidationError:
        classification_substitution_rejected = True
    recorded_live_substitution_rejected = False
    try:
        replace(
            bundle.source,
            classification=DepthSourceClassification.RECORDED_FIXTURE,
            manifest_id=None,
        )
    except DepthCameraValidationError:
        recorded_live_substitution_rejected = True

    adversarial = _configured_adapter(bundle)
    first_session = adversarial.activate()
    template = fixture_depth_image_metadata(
        bundle,
        first_session,
        1_000_000_000,
    )
    wrong_frame_rejected = adversarial.submit_image(
        replace(template, frame_id='head_camera_optical_frame'),
        now_ns=1_000_000_000,
    ) is None
    wrong_robot_rejected = adversarial.submit_image(
        replace(template, robot_id='ayyo.spoof.v1'),
        now_ns=1_000_000_000,
    ) is None
    wrong_sensor_rejected = adversarial.submit_image(
        replace(
            template,
            sensor=SensorIdentity(
                'ayyo.camera.head.depth.spoof.v1',
                SensorKind.DEPTH_CAMERA,
                'head_depth_camera_spoof_optical_frame',
            ),
        ),
        now_ns=1_000_000_000,
    ) is None
    unknown_source_rejected = adversarial.submit_image(
        replace(template, source_id='ros.camera.head.depth.unknown.v1'),
        now_ns=1_000_000_000,
    ) is None
    physical_spoof = ObservationProvenance(
        ObservationSourceKind.PHYSICAL_SENSOR,
        'ros.camera.head.depth.physical.spoof.v1',
        ObservationClock.ROS_SYSTEM_TIME,
        ObservationTransport.ROS2,
        bundle.source.provenance.interface,
    )
    spoofed_physical_rejected = adversarial.submit_image(
        replace(
            template,
            source_id=physical_spoof.source_id,
            provenance=physical_spoof,
        ),
        now_ns=1_000_000_000,
    ) is None
    recorded_spoof = ObservationProvenance(
        ObservationSourceKind.RECORDED_DATA,
        'recording.camera.head.depth.spoof.v1',
        ObservationClock.RECORDED_TIME,
        ObservationTransport.RECORDED,
        bundle.source.provenance.interface,
    )
    recorded_evidence_rejected = adversarial.submit_image(
        replace(
            template,
            source_id=recorded_spoof.source_id,
            provenance=recorded_spoof,
        ),
        now_ns=1_000_000_000,
    ) is None
    wrong_camera_identity_rejected = False
    try:
        replace(
            template,
            sensor=SensorIdentity(
                'ayyo.camera.head.rgb.v1',
                SensorKind.RGB_CAMERA,
                'head_camera_optical_frame',
            ),
        )
    except (DepthCameraValidationError, WorldModelValidationError):
        wrong_camera_identity_rejected = True

    original_core = bundle.calibration.calibration
    changed_core = CameraCalibration(
        width=original_core.width,
        height=original_core.height,
        distortion_model=original_core.distortion_model,
        d=original_core.d,
        k=(5.0,) + original_core.k[1:],
        r=original_core.r,
        p=original_core.p,
        binning_x=original_core.binning_x,
        binning_y=original_core.binning_y,
        roi=original_core.roi,
    )
    changed_calibration = DepthCameraCalibration(
        sensor=bundle.source.sensor,
        source_id=bundle.source.source_id,
        mount_frame_id=bundle.source.mount_frame_id,
        optical_frame_id=bundle.source.sensor.frame_id,
        calibration_version='test.changed.v1',
        calibration_source=DepthCalibrationSource.TEST_FIXTURE,
        calibration=changed_core,
    )
    calibration_mismatch_rejected = adversarial.submit_camera_info(
        fixture_depth_camera_info_metadata(
            bundle,
            first_session,
            1_000_000_000,
            calibration=changed_calibration,
        ),
        now_ns=1_000_000_000,
    ) is None

    adversarial.deactivate()
    inactive_evidence_rejected = adversarial.submit_image(
        fixture_depth_image_metadata(bundle, first_session, 1_000_000_001),
        now_ns=1_000_000_001,
    ) is None
    second_session = adversarial.activate()
    old_session_rejected = adversarial.submit_image(
        fixture_depth_image_metadata(bundle, first_session, 1_000_000_002),
        now_ns=1_000_000_002,
    ) is None
    recovery_trust = _trust(bundle)
    recovery_memory = _memory(bundle)
    recovered = _admit_pair(
        adversarial,
        bundle,
        second_session,
        recovery_trust,
        recovery_memory,
        1_000_000_003,
        1,
    )
    bare_trust = _trust(bundle)
    bare_bypass_rejected = bare_trust.admit(
        recovered.frame,
        now_ns=recovered.frame.observed_at_ns,
        received_at_monotonic_ns=1,
    ).status is AdmissionStatus.REJECTED
    reset_trust = _trust(bundle)
    assert reset_trust.authorize_depth_camera(recovered)
    reset_trust.reset()
    reset_clears_authorization = reset_trust.admit(
        recovered.frame,
        now_ns=recovered.frame.observed_at_ns,
        received_at_monotonic_ns=1,
    ).status is AdmissionStatus.REJECTED

    simulation = depth_simulation_bundle(width=4, height=2)
    simulation_adapter = _configured_adapter(simulation)
    simulation_session = simulation_adapter.activate()
    simulation_adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(
            simulation,
            simulation_session,
            1_000_000_004,
        ),
        now_ns=1_000_000_004,
    )
    simulation_sealed = simulation_adapter.submit_image(
        fixture_depth_image_metadata(
            simulation,
            simulation_session,
            1_000_000_004,
            encoding='32FC1',
        ),
        now_ns=1_000_000_004,
    )
    assert simulation_sealed is not None
    simulation_spoof_rejected = not _trust(bundle).authorize_depth_camera(
        simulation_sealed
    )

    forged = _configured_adapter(bundle)
    forged_session = forged.activate()
    forged.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, forged_session, 1_000_000_005),
        now_ns=1_000_000_005,
    )
    forged_sealed = forged.submit_image(
        fixture_depth_image_metadata(bundle, forged_session, 1_000_000_005),
        now_ns=1_000_000_005,
    )
    assert forged_sealed is not None
    object.__setattr__(
        forged_sealed,
        'requirement',
        replace(
            forged_sealed.requirement,
            producer_id='unknown.depth.producer.v1',
        ),
    )
    unknown_producer_rejected = not _trust(bundle).authorize_depth_camera(
        forged_sealed
    )

    temporal = _configured_adapter(
        bundle,
        retention_ns=1_000,
        future_skew_ns=10,
        pair_wait_ns=100,
    )
    temporal_session = temporal.activate()
    stale_rejected = temporal.submit_image(
        fixture_depth_image_metadata(bundle, temporal_session, 1_000),
        now_ns=2_001,
    ) is None
    future_rejected = temporal.submit_image(
        fixture_depth_image_metadata(bundle, temporal_session, 2_020),
        now_ns=2_000,
    ) is None
    temporal.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, temporal_session, 2_000),
        now_ns=2_000,
    )
    temporal_valid = temporal.submit_image(
        fixture_depth_image_metadata(bundle, temporal_session, 2_000),
        now_ns=2_000,
    )
    assert temporal_valid is not None
    duplicate_rejected = temporal.submit_image(
        fixture_depth_image_metadata(bundle, temporal_session, 2_000),
        now_ns=2_000,
    ) is None
    out_of_order_rejected = temporal.submit_image(
        fixture_depth_image_metadata(bundle, temporal_session, 1_999),
        now_ns=2_000,
    ) is None

    conflicting_identity_rejected = False
    try:
        replace(
            recovered.frame,
            observation_id='world-observation-' + '0' * 64,
        )
    except ObservationIdentityError:
        conflicting_identity_rejected = True
    conflicting_fingerprint_rejected = False
    try:
        replace(
            recovered.frame,
            fingerprint=ObservationFingerprint(
                ObservationFingerprintKind.DEPTH_FRAME,
                '0' * 64,
            ),
        )
    except ObservationIdentityError:
        conflicting_fingerprint_rejected = True

    adapter = _configured_adapter(bundle)
    session = adapter.activate()
    trust = _trust(bundle)
    memory = _memory(bundle)
    last = None
    tracemalloc.start()
    try:
        for index in range(CYCLE_COUNT):
            observed_at_ns = 10_000_000_000 + index * 1_000_000
            last = _admit_pair(
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
    assert last is not None
    final_now_ns = 10_000_000_000 + (CYCLE_COUNT - 1) * 1_000_000
    first_snapshot = memory.current_snapshot(now_ns=final_now_ns)
    first_stats = memory.stats(now_ns=final_now_ns)
    second_snapshot = memory.current_snapshot(now_ns=final_now_ns)
    second_stats = memory.stats(now_ns=final_now_ns)
    depth_state = first_snapshot.robot.depth_states[0]
    depth_health = next(
        item
        for item in first_snapshot.robot.sensor_health_states
        if item.observation.sensor == bundle.source.sensor
    )

    result = {
        'accepted_count': trust.stats().accepted_count,
        'adapter_accepted_pair_count': adapter.diagnostics.accepted_count,
        'adapter_rejected_count': adapter.diagnostics.rejected_count,
        'bare_perception_bypass_rejected': bare_bypass_rejected,
        'calibration_id': bundle.calibration.calibration.calibration_id,
        'calibration_mismatch_rejected': calibration_mismatch_rejected,
        'calibration_record_id': bundle.calibration.calibration_record_id,
        'classification_substitution_rejected': classification_substitution_rejected,
        'conflicting_fingerprint_rejected': conflicting_fingerprint_rejected,
        'conflicting_identity_rejected': conflicting_identity_rejected,
        'current_depth_count': first_stats.current_depth_count,
        'current_health_count': first_stats.current_sensor_health_count,
        'cycle_count': CYCLE_COUNT,
        'depth_authorization_count': trust.stats().tracked_depth_camera_count,
        'diagnostic_available': depth_health.availability.value,
        'diagnostic_detail': depth_health.observation.evidence_detail,
        'duplicate_rejected': duplicate_rejected,
        'fixture_classification': bundle.source.classification.value,
        'inactive_evidence_rejected': inactive_evidence_rejected,
        'malformed_calibration_rejected': _malformed_calibration_rejected(bundle),
        'nan_sentinel_counted_invalid': nan_summary.invalid_depth_count == 1,
        'no_raw_depth_retained': not hasattr(depth_state.observation, 'data'),
        'old_session_rejected': old_session_rejected,
        'out_of_order_rejected': out_of_order_rejected,
        'pending_camera_info_count': adapter.diagnostics.pending_camera_info_count,
        'pending_image_count': adapter.diagnostics.pending_image_count,
        'query_immutable': first_snapshot == second_snapshot and first_stats == second_stats,
        'recent_bounded_state_size': first_stats.recent_evidence_count,
        'recorded_evidence_rejected': recorded_evidence_rejected,
        'recorded_live_substitution_rejected': recorded_live_substitution_rejected,
        'reset_clears_authorization': reset_clears_authorization,
        'retained_reference_count': first_stats.retained_observation_reference_count,
        'retained_unique_state_count': first_stats.retained_unique_observation_count,
        'session_changed_on_reactivation': first_session != second_session,
        'simulation_spoof_rejected': simulation_spoof_rejected,
        'source_manifest_id': bundle.source.manifest_id,
        'spoofed_physical_rejected': spoofed_physical_rejected,
        'stale_rejected': stale_rejected,
        'future_rejected': future_rejected,
        'traced_python_current_bytes': traced_current,
        'traced_python_peak_bytes': traced_peak,
        'unknown_producer_rejected': unknown_producer_rejected,
        'unknown_source_rejected': unknown_source_rejected,
        'valid_recovery_after_adversarial': recovered is not None,
        'wrong_camera_identity_rejected': wrong_camera_identity_rejected,
        'wrong_frame_rejected': wrong_frame_rejected,
        'wrong_robot_rejected': wrong_robot_rejected,
        'wrong_sensor_rejected': wrong_sensor_rejected,
        **invalid_payload_checks,
    }
    print(
        'HEAD_DEPTH_RGBD_FIXTURE_RESULT='
        + json.dumps(result, separators=(',', ':'), sort_keys=True)
    )


def publish_ros_adversarial(scenario: str) -> None:
    """Publish bounded malformed standard ROS evidence into an isolated graph."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image

    bundle = depth_test_fixture_bundle()
    calibration = bundle.calibration.calibration
    rclpy.init()
    node = Node(f'ayyo_head_depth_{scenario}_test_fixture')
    try:
        image_publisher = node.create_publisher(
            Image,
            '/ayyo/camera/head/depth/image_raw',
            qos_profile_sensor_data,
        )
        info_publisher = node.create_publisher(
            CameraInfo,
            '/ayyo/camera/head/depth/camera_info',
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
            raise RuntimeError('depth adversarial fixture found no subscribers')
        published = 0
        for _ in range(64):
            stamp = node.get_clock().now().to_msg()
            frame_id = (
                'head_camera_optical_frame'
                if scenario == 'wrong_frame'
                else bundle.source.sensor.frame_id
            )
            image = Image()
            image.header.stamp = stamp
            image.header.frame_id = frame_id
            image.width = calibration.width
            image.height = calibration.height
            image.encoding = '16UC1'
            image.is_bigendian = 0
            image.step = calibration.width * 2
            image.data = fixture_depth_bytes(calibration.width, calibration.height)
            if scenario == 'malformed_payload':
                image.data = image.data[:-1]
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
            info.binning_x = calibration.binning_x
            info.binning_y = calibration.binning_y
            (
                info.roi.x_offset,
                info.roi.y_offset,
                info.roi.width,
                info.roi.height,
                info.roi.do_rectify,
            ) = calibration.roi
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
        choices=('offline', 'wrong_frame', 'malformed_payload'),
        default='offline',
    )
    arguments = parser.parse_args()
    if arguments.scenario == 'offline':
        run_offline()
    else:
        publish_ros_adversarial(arguments.scenario)


if __name__ == '__main__':
    main()
