from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    DepthFrameObservation,
    FusedRgbdObservation,
    ObservationIdentityError,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    WorldModelProjector,
    WorldModelValidationError,
    rebuild_observation,
)

from helpers import TEST_PROVENANCE, catalog


RGB_SENSOR = SensorIdentity(
    'ayyo.camera.head.rgb.v1',
    SensorKind.RGB_CAMERA,
    'head_camera_optical_frame',
)
DEPTH_SENSOR = SensorIdentity(
    'ayyo.camera.head.depth.v1',
    SensorKind.DEPTH_CAMERA,
    'head_depth_camera_optical_frame',
)
FUSION_SENSOR = SensorIdentity(
    'ayyo.camera.head.rgbd.fusion.v1',
    SensorKind.RGBD_FUSION,
    'head_camera_frame',
)


def rgb(*, observed_at_ns: int = 100) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=RGB_SENSOR,
        width=4,
        height=2,
        encoding='rgb8',
        step=12,
        data_size_bytes=24,
        is_bigendian=False,
        calibration_id='camera-calibration-sha256-' + '1' * 64,
        observed_at_ns=observed_at_ns,
        provenance=TEST_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def depth(*, observed_at_ns: int = 100) -> DepthFrameObservation:
    return DepthFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=DEPTH_SENSOR,
        width=4,
        height=2,
        encoding='16UC1',
        step=8,
        data_size_bytes=16,
        is_bigendian=False,
        calibration_id='camera-calibration-sha256-' + '2' * 64,
        calibration_record_id='depth-camera-calibration-sha256-' + '3' * 64,
        source_manifest_id='depth-camera-source-sha256-' + '4' * 64,
        session_id='depth-camera-session-sha256-' + '5' * 64,
        valid_depth_count=8,
        invalid_depth_count=0,
        minimum_depth_m=0.5,
        maximum_depth_m=2.0,
        payload_sha256='6' * 64,
        observed_at_ns=observed_at_ns,
        provenance=TEST_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def fused(**overrides) -> FusedRgbdObservation:
    values = {
        'robot_id': AYYO_ROBOT_ID,
        'sensor': FUSION_SENSOR,
        'rgb_observation': rgb(),
        'depth_observation': depth(),
        'rgb_producer_id': 'ayyo.rgb.test-producer.v1',
        'depth_producer_id': 'ayyo.depth.test-producer.v1',
        'rgb_source_fingerprint_sha256': '7' * 64,
        'depth_source_fingerprint_sha256': '8' * 64,
        'rgb_session_id': 'rgb-session-sha256-' + '9' * 64,
        'depth_session_id': 'depth-session-sha256-' + 'a' * 64,
        'rgb_camera_frame_id': 'head_camera_frame',
        'depth_camera_frame_id': 'head_depth_camera_frame',
        'pairing_policy_id': 'ayyo.rgbd.exact-source-time.v1',
        'pairing_policy_version': '1.0.0',
        'synchronization_session_id': 'rgbd-session-sha256-' + 'b' * 64,
        'result_at_ns': 100,
        'provenance': TEST_PROVENANCE,
        'availability': SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return FusedRgbdObservation(**values)


def test_fused_observation_is_compact_immutable_and_deterministic() -> None:
    observation = fused()
    rebuilt = rebuild_observation(observation)
    assert observation == rebuilt
    assert observation.pair_id == rebuilt.pair_id
    document = observation.payload_document()
    assert document['spatial_registration_validated'] is False
    component_payloads = (
        document['rgb_observation']['payload'],
        document['depth_observation']['payload'],
    )
    assert all('data' not in payload for payload in component_payloads)
    with pytest.raises(FrozenInstanceError):
        observation.pair_id = 'rgbd-pair-sha256-' + '0' * 64


def test_fused_observation_requires_exact_acquisition_time_and_identity() -> None:
    with pytest.raises(WorldModelValidationError, match='exact source acquisition'):
        fused(depth_observation=depth(observed_at_ns=101))
    with pytest.raises(ObservationIdentityError):
        fused(pair_id='rgbd-pair-sha256-' + '0' * 64)


def test_projector_exposes_repeatable_read_only_fused_state() -> None:
    observation = fused()
    projector = WorldModelProjector(
        catalog(),
        (DEPTH_SENSOR, FUSION_SENSOR, RGB_SENSOR),
    )
    arguments = {
        'now_ns': 100,
        'fresh_for_ns': 10,
        'joint_evidence': {},
        'pose_evidence': None,
        'entity_evidence': {},
        'depth_evidence': {DEPTH_SENSOR.sensor_id: observation.depth_observation},
        'fused_rgbd_evidence': {FUSION_SENSOR.sensor_id: observation},
        'visual_evidence': {RGB_SENSOR.sensor_id: observation.rgb_observation},
    }
    first = projector.project(**arguments)
    second = projector.project(**arguments)
    assert first == second
    assert first.robot.fused_rgbd_states[0].observation == observation
    payload = first.robot.document()['fused_rgbd_states'][0]['payload']
    assert payload['pair_id'] == observation.pair_id
    assert payload['spatial_registration_validated'] is False


def test_projector_rejects_fused_sensor_key_conflict() -> None:
    alternate = SensorIdentity(
        'ayyo.camera.head.rgbd.alternate.v1',
        SensorKind.RGBD_FUSION,
        'head_camera_frame',
    )
    projector = WorldModelProjector(catalog(), (FUSION_SENSOR, alternate))
    with pytest.raises(WorldModelValidationError, match='key and sensor'):
        projector.project(
            now_ns=100,
            fresh_for_ns=10,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            fused_rgbd_evidence={alternate.sensor_id: fused()},
        )
