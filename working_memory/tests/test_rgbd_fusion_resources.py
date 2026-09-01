from __future__ import annotations

from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    StateKey,
    StateKeyKind,
    WorkingMemory,
    WorkingMemoryConfig,
    WorkingMemoryFreshness,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    DepthFrameObservation,
    FusedRgbdObservation,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
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


def fused(*, observed_at_ns: int = 100) -> FusedRgbdObservation:
    rgb = VisualFrameObservation(
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
    depth = DepthFrameObservation(
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
    return FusedRgbdObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=FUSION_SENSOR,
        rgb_observation=rgb,
        depth_observation=depth,
        rgb_producer_id='ayyo.rgb.test-producer.v1',
        depth_producer_id='ayyo.depth.test-producer.v1',
        rgb_source_fingerprint_sha256='7' * 64,
        depth_source_fingerprint_sha256='8' * 64,
        rgb_session_id='rgb-session-sha256-' + '9' * 64,
        depth_session_id='depth-session-sha256-' + 'a' * 64,
        rgb_camera_frame_id='head_camera_frame',
        depth_camera_frame_id='head_depth_camera_frame',
        pairing_policy_id='ayyo.rgbd.exact-source-time.v1',
        pairing_policy_version='1.0.0',
        synchronization_session_id='rgbd-session-sha256-' + 'b' * 64,
        result_at_ns=observed_at_ns,
        provenance=TEST_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def memory(*, recent_capacity: int = 4) -> WorkingMemory:
    return WorkingMemory(
        catalog(),
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=TEST_PROVENANCE.clock,
            allowed_provenance=(TEST_PROVENANCE,),
            sensors=tuple(sorted(
                (DEPTH_SENSOR, FUSION_SENSOR, RGB_SENSOR),
                key=lambda item: item.sensor_id,
            )),
            freshness_ns=10,
            retention_ttl_ns=100,
            permitted_future_skew_ns=0,
            recent_evidence_capacity=recent_capacity,
            environment_entity_capacity=1,
        ),
    )


def retain_components(store: WorkingMemory, observation, receipt: int) -> None:
    assert store.ingest(
        observation.rgb_observation,
        now_ns=observation.observed_at_ns,
        received_at_monotonic_ns=receipt,
    ).status is IngestionStatus.ACCEPTED
    assert store.ingest(
        observation.depth_observation,
        now_ns=observation.observed_at_ns,
        received_at_monotonic_ns=receipt + 1,
    ).status is IngestionStatus.ACCEPTED


def test_fused_state_requires_retained_components_and_is_query_stable() -> None:
    store = memory()
    observation = fused()
    missing = store.ingest(
        observation,
        now_ns=100,
        received_at_monotonic_ns=1,
    )
    assert missing.status is IngestionStatus.REJECTED
    assert missing.reason is IngestionReason.SOURCE_OBSERVATION_MISMATCH
    retain_components(store, observation, 2)
    accepted = store.ingest(
        observation,
        now_ns=100,
        received_at_monotonic_ns=4,
    )
    assert accepted.status is IngestionStatus.ACCEPTED
    before = store.stats(now_ns=100)
    first = store.current_snapshot(now_ns=100)
    second = store.current_snapshot(now_ns=100)
    assert first == second
    assert store.stats(now_ns=100) == before
    assert before.current_fused_rgbd_count == 1
    rejected = store.ingest(
        fused(observed_at_ns=99),
        now_ns=100,
        received_at_monotonic_ns=5,
    )
    assert rejected.status is IngestionStatus.REJECTED
    assert rejected.reason is IngestionReason.SOURCE_OBSERVATION_MISMATCH
    assert store.current_snapshot(now_ns=100) == first


def test_duplicate_fused_state_does_not_grow_and_expires() -> None:
    store = memory()
    observation = fused()
    retain_components(store, observation, 1)
    store.ingest(observation, now_ns=100, received_at_monotonic_ns=3)
    duplicate = store.ingest(
        observation,
        now_ns=100,
        received_at_monotonic_ns=4,
    )
    assert duplicate.status is IngestionStatus.DUPLICATE
    assert store.stats(now_ns=100).recent_evidence_count == 3
    key = StateKey(StateKeyKind.ROBOT_RGBD_FUSION, FUSION_SENSOR.sensor_id)
    assert store.query_freshness(
        key,
        now_ns=111,
    ).freshness is WorkingMemoryFreshness.STALE
    assert store.query_freshness(
        key,
        now_ns=201,
    ).freshness is WorkingMemoryFreshness.UNKNOWN


def test_reset_clears_fused_state_and_source_epoch() -> None:
    store = memory()
    observation = fused()
    retain_components(store, observation, 1)
    store.ingest(observation, now_ns=100, received_at_monotonic_ns=3)
    store.reset()
    assert store.current_snapshot(now_ns=1).robot.fused_rgbd_states == ()
    assert store.stats(now_ns=1).current_fused_rgbd_count == 0
