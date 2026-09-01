from dataclasses import replace

from ayyo_rgbd_fusion import (
    MAX_RGBD_PENDING_PER_STREAM,
    RgbdFusionEvent,
    RgbdFusionLifecycleState,
)
from ayyo_world_model import SensorAvailability, SensorIdentity, SensorKind

from helpers import altered_depth, configured_pair, depth_admission, rgb


def test_exact_source_time_only_and_valid_recovery() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    fusion.submit_rgb(rgb(requirement, 1_000), now_ns=1_000)
    mismatch = depth_admission(bundle, depth_adapter, session, 1_001).frame
    assert fusion.submit_depth(mismatch, now_ns=1_001) is None
    assert fusion.diagnostics.pending_rgb_count == 1
    assert fusion.diagnostics.pending_depth_count == 1
    matched = depth_admission(bundle, depth_adapter, session, 1_002).frame
    assert fusion.submit_depth(matched, now_ns=1_002) is None
    accepted = fusion.submit_rgb(rgb(requirement, 1_002), now_ns=1_002)
    assert accepted is not None
    assert accepted.observation.rgb_observation.observed_at_ns == 1_002


def test_wrong_source_frame_calibration_and_health_fail_closed() -> None:
    _, _, _, requirement, fusion = configured_pair()
    for candidate in (
        rgb(requirement, 10, robot_id="ayyo.spoof.v1"),
        rgb(
            requirement,
            11,
            calibration_id="camera-calibration-sha256-" + "0" * 64,
        ),
        rgb(requirement, 12, provenance=replace(requirement.rgb_provenance, source_id="spoof.v1")),
    ):
        assert fusion.submit_rgb(candidate, now_ns=candidate.observed_at_ns) is None
        assert fusion.diagnostics.event is RgbdFusionEvent.WRONG_COMPONENT
    assert fusion.diagnostics.pending_rgb_count == 0


def test_wrong_depth_source_sensor_frame_calibration_and_health_fail_closed() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    frame = depth_admission(bundle, depth_adapter, session, 100).frame
    alternate_sensor = SensorIdentity(
        "ayyo.camera.head.depth.alternate.v1",
        SensorKind.DEPTH_CAMERA,
        "head_depth_alternate_optical_frame",
    )
    for candidate in (
        altered_depth(frame, sensor=alternate_sensor),
        altered_depth(
            frame,
            calibration_id="camera-calibration-sha256-" + "0" * 64,
        ),
        altered_depth(
            frame,
            source_manifest_id="depth-camera-source-sha256-" + "0" * 64,
        ),
        altered_depth(
            frame,
            provenance=replace(
                requirement.depth_provenance,
                source_id="spoof.depth.v1",
            ),
        ),
        altered_depth(frame, availability=SensorAvailability.DEGRADED),
    ):
        assert fusion.submit_depth(candidate, now_ns=100) is None
        assert fusion.diagnostics.event is RgbdFusionEvent.WRONG_COMPONENT
    assert fusion.diagnostics.pending_depth_count == 0


def test_pending_state_is_hard_bounded_and_deterministically_evicted() -> None:
    _, _, _, requirement, fusion = configured_pair()
    for index in range(64):
        source_time = 1_000_000_000 + index * 1_000_000
        assert fusion.submit_rgb(
            rgb(requirement, source_time),
            now_ns=source_time,
        ) is None
    diagnostics = fusion.diagnostics
    assert diagnostics.pending_rgb_count <= MAX_RGBD_PENDING_PER_STREAM
    assert diagnostics.pending_depth_count == 0
    assert diagnostics.evicted_count > 0


def test_lifecycle_clears_pending_and_changes_sessions() -> None:
    _, _, session, requirement, fusion = configured_pair()
    first_rgb_session = fusion.active_rgb_session_id
    first_sync_session = fusion.active_synchronization_session_id
    fusion.submit_rgb(rgb(requirement, 100), now_ns=100)
    assert fusion.diagnostics.pending_rgb_count == 1
    fusion.deactivate()
    assert fusion.state is RgbdFusionLifecycleState.INACTIVE
    assert fusion.diagnostics.pending_rgb_count == 0
    fusion.activate(depth_session_id=session)
    assert fusion.active_rgb_session_id != first_rgb_session
    assert fusion.active_synchronization_session_id != first_sync_session


def test_lifecycle_rejects_inactive_callbacks_and_old_session_replay() -> None:
    bundle, depth_adapter, old_session, requirement, fusion = configured_pair()
    old_depth = depth_admission(
        bundle,
        depth_adapter,
        old_session,
        100,
    ).frame
    fusion.deactivate()
    assert fusion.submit_rgb(rgb(requirement, 100), now_ns=100) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.INACTIVE
    depth_adapter.deactivate()
    new_depth_session = depth_adapter.activate()
    fusion.activate(depth_session_id=new_depth_session)
    fusion.submit_rgb(rgb(requirement, 100), now_ns=100)
    assert fusion.submit_depth(old_depth, now_ns=100) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.SESSION_MISMATCH
    assert fusion.diagnostics.pending_depth_count == 0
    source_time = 200
    fusion.submit_rgb(rgb(requirement, source_time), now_ns=source_time)
    recovered = fusion.submit_depth(
        depth_admission(
            bundle,
            depth_adapter,
            new_depth_session,
            source_time,
        ).frame,
        now_ns=source_time,
    )
    assert recovered is not None
    assert recovered.observation.depth_session_id == new_depth_session


def test_duplicate_regressed_stale_and_future_evidence_are_rejected() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    source_time = 1_000_000_000
    frame = rgb(requirement, source_time)
    fusion.submit_rgb(frame, now_ns=source_time)
    accepted = fusion.submit_depth(
        depth_admission(bundle, depth_adapter, session, source_time).frame,
        now_ns=source_time,
    )
    assert accepted is not None
    assert fusion.submit_rgb(frame, now_ns=source_time) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.DUPLICATE_EVIDENCE
    assert fusion.submit_rgb(rgb(requirement, source_time - 1), now_ns=source_time) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.REGRESSED_EVIDENCE
    stale = source_time + 1
    assert fusion.submit_rgb(rgb(requirement, stale), now_ns=stale + 2_000_000_001) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.STALE_EVIDENCE
    future = source_time + 100_000_000
    assert fusion.submit_rgb(rgb(requirement, future), now_ns=source_time + 1) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.FUTURE_EVIDENCE


def test_each_stream_rejects_regression_before_any_pair_is_accepted() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    fusion.submit_rgb(rgb(requirement, 200), now_ns=200)
    assert fusion.submit_rgb(rgb(requirement, 199), now_ns=200) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.REGRESSED_EVIDENCE
    depth_at_300 = depth_admission(
        bundle,
        depth_adapter,
        session,
        300,
    ).frame
    fusion.submit_depth(depth_at_300, now_ns=300)
    assert fusion.submit_depth(
        altered_depth(depth_at_300, observed_at_ns=299),
        now_ns=300,
    ) is None
    assert fusion.diagnostics.event is RgbdFusionEvent.REGRESSED_EVIDENCE
