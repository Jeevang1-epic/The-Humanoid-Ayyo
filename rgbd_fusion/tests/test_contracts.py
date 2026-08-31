from dataclasses import replace

import pytest

from ayyo_rgbd_fusion import (
    HEAD_RGBD_FUSION_SENSOR,
    RGBD_PAIRING_POLICY_ID,
    RgbdFusionAdmission,
    RgbdFusionConfigurationError,
)
from ayyo_world_model import ObservationIdentityError, rebuild_observation

from helpers import configured_pair, depth_admission, rgb


def test_exact_pair_is_immutable_deterministic_and_compact() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    source_time = 1_000_000_000
    rgb_frame = rgb(requirement, source_time)
    depth_frame = depth_admission(
        bundle, depth_adapter, session, source_time
    ).frame
    assert fusion.submit_rgb(rgb_frame, now_ns=source_time) is None
    admission = fusion.submit_depth(depth_frame, now_ns=source_time)
    assert admission is not None
    observation = admission.observation
    rebuilt = rebuild_observation(observation)
    assert rebuilt == observation
    assert observation.sensor == HEAD_RGBD_FUSION_SENSOR
    assert observation.rgb_observation == rgb_frame
    assert observation.depth_observation == depth_frame
    assert observation.observed_at_ns == source_time
    assert observation.pairing_policy_id == RGBD_PAIRING_POLICY_ID
    assert observation.pair_id.startswith("rgbd-pair-sha256-")
    assert observation.observation_id.startswith("world-observation-")
    document = observation.payload_document()
    assert document["spatial_registration_validated"] is False
    assert "data" not in document["rgb_observation"]["payload"]
    assert "data" not in document["depth_observation"]["payload"]


def test_pair_identity_rejects_conflict() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    source_time = 2_000_000_000
    fusion.submit_rgb(rgb(requirement, source_time), now_ns=source_time)
    admission = fusion.submit_depth(
        depth_admission(bundle, depth_adapter, session, source_time).frame,
        now_ns=source_time,
    )
    assert admission is not None
    with pytest.raises(ObservationIdentityError):
        observation = admission.observation
        observation.__class__(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            rgb_observation=observation.rgb_observation,
            depth_observation=observation.depth_observation,
            rgb_producer_id=observation.rgb_producer_id,
            depth_producer_id=observation.depth_producer_id,
            rgb_source_fingerprint_sha256=(
                observation.rgb_source_fingerprint_sha256
            ),
            depth_source_fingerprint_sha256=(
                observation.depth_source_fingerprint_sha256
            ),
            rgb_session_id=observation.rgb_session_id,
            depth_session_id=observation.depth_session_id,
            rgb_camera_frame_id=observation.rgb_camera_frame_id,
            depth_camera_frame_id=observation.depth_camera_frame_id,
            pairing_policy_id=observation.pairing_policy_id,
            pairing_policy_version=observation.pairing_policy_version,
            synchronization_session_id=observation.synchronization_session_id,
            result_at_ns=observation.result_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            pair_id="rgbd-pair-sha256-" + "0" * 64,
        )


def test_admission_cannot_be_constructed_without_private_seal() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    source_time = 3_000_000_000
    fusion.submit_rgb(rgb(requirement, source_time), now_ns=source_time)
    valid = fusion.submit_depth(
        depth_admission(bundle, depth_adapter, session, source_time).frame,
        now_ns=source_time,
    )
    assert valid is not None
    with pytest.raises(RgbdFusionConfigurationError):
        RgbdFusionAdmission(
            observation=valid.observation,
            requirement=requirement,
            diagnostics=valid.diagnostics,
            _seal=object(),
        )


@pytest.mark.parametrize(
    "field,value",
    (
        ("rgb_producer_id", "UNKNOWN"),
        ("depth_source_fingerprint_sha256", "0" * 63),
        ("rgb_camera_frame_id", "bad frame"),
        ("rgb_calibration_id", "invalid"),
    ),
)
def test_requirement_rejects_malformed_identity(field, value) -> None:
    _, _, _, requirement, _ = configured_pair()
    with pytest.raises(RgbdFusionConfigurationError):
        replace(requirement, **{field: value})
