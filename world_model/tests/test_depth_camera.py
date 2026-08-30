from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    DepthFrameObservation,
    ObservationIdentityError,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    WorldModelProjector,
    WorldModelValidationError,
    rebuild_observation,
)

from helpers import TEST_PROVENANCE, catalog


DEPTH_SENSOR = SensorIdentity(
    'ayyo.camera.head.depth.v1',
    SensorKind.DEPTH_CAMERA,
    'head_depth_camera_optical_frame',
)


def depth(**overrides) -> DepthFrameObservation:
    values = {
        'robot_id': AYYO_ROBOT_ID,
        'sensor': DEPTH_SENSOR,
        'width': 4,
        'height': 2,
        'encoding': '16UC1',
        'step': 8,
        'data_size_bytes': 16,
        'is_bigendian': False,
        'calibration_id': 'camera-calibration-sha256-' + '1' * 64,
        'calibration_record_id': 'depth-camera-calibration-sha256-' + '2' * 64,
        'source_manifest_id': 'depth-camera-source-sha256-' + '3' * 64,
        'session_id': 'depth-camera-session-sha256-' + '4' * 64,
        'valid_depth_count': 7,
        'invalid_depth_count': 1,
        'minimum_depth_m': 0.5,
        'maximum_depth_m': 2.0,
        'payload_sha256': '5' * 64,
        'observed_at_ns': 100,
        'provenance': TEST_PROVENANCE,
        'availability': SensorAvailability.DEGRADED,
    }
    values.update(overrides)
    return DepthFrameObservation(**values)


def test_depth_observation_is_compact_immutable_and_rebuildable() -> None:
    observation = depth()
    assert not hasattr(observation, 'data')
    assert observation == rebuild_observation(observation)
    assert observation.payload_document()['valid_depth_count'] == 7
    with pytest.raises(FrozenInstanceError):
        observation.width = 8


@pytest.mark.parametrize(
    'overrides',
    [
        {'sensor': SensorIdentity('bad.depth.v1', SensorKind.RGB_CAMERA, 'bad_frame')},
        {'width': 0},
        {'encoding': 'mono16'},
        {'step': 7},
        {'data_size_bytes': 15},
        {'valid_depth_count': 0, 'invalid_depth_count': 8},
        {'valid_depth_count': 7, 'invalid_depth_count': 0},
        {'minimum_depth_m': float('nan')},
        {'maximum_depth_m': float('inf')},
        {'minimum_depth_m': 3.0, 'maximum_depth_m': 2.0},
        {'payload_sha256': 'bad'},
        {'session_id': 'depth-camera-session-sha256-' + 'g' * 64},
    ],
)
def test_depth_observation_rejects_malformed_compact_state(overrides) -> None:
    with pytest.raises(WorldModelValidationError):
        depth(**overrides)


def test_depth_identity_substitution_is_rejected() -> None:
    with pytest.raises(ObservationIdentityError):
        depth(observation_id='world-observation-' + '0' * 64)


def test_projector_exposes_one_immutable_depth_state() -> None:
    observation = depth()
    projector = WorldModelProjector(catalog(), (DEPTH_SENSOR,))
    first = projector.project(
        now_ns=100,
        fresh_for_ns=10,
        joint_evidence={},
        pose_evidence=None,
        entity_evidence={},
        depth_evidence={DEPTH_SENSOR.sensor_id: observation},
    )
    second = projector.project(
        now_ns=100,
        fresh_for_ns=10,
        joint_evidence={},
        pose_evidence=None,
        entity_evidence={},
        depth_evidence={DEPTH_SENSOR.sensor_id: observation},
    )
    assert first == second
    assert len(first.robot.depth_states) == 1
    document = first.robot.document()
    assert document['depth_states'][0]['payload']['payload_sha256'] == '5' * 64
    assert 'data' not in document['depth_states'][0]['payload']


def test_projector_rejects_depth_key_identity_conflict() -> None:
    alternate = SensorIdentity(
        'ayyo.camera.head.depth.alternate.v1',
        SensorKind.DEPTH_CAMERA,
        'head_depth_camera_alternate_optical_frame',
    )
    projector = WorldModelProjector(catalog(), (DEPTH_SENSOR, alternate))
    with pytest.raises(WorldModelValidationError, match='key and sensor'):
        projector.project(
            now_ns=100,
            fresh_for_ns=10,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            depth_evidence={alternate.sensor_id: depth()},
        )
