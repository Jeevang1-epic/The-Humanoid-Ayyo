from __future__ import annotations

from dataclasses import replace

import pytest

from ayyo_depth_camera import (
    MAX_DEPTH_PENDING_PAIRS,
    DepthCameraConfigurationError,
    DepthCameraLifecycleError,
    DepthDiagnosticEvent,
    DepthLifecycleAdapter,
    DepthLifecycleState,
    DepthSourceRegistry,
    depth_test_fixture_bundle,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
)


def configured_adapter():
    bundle = depth_test_fixture_bundle()
    registry = DepthSourceRegistry()
    assert registry.register(bundle.source)
    adapter = DepthLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    return bundle, registry, adapter


def test_registry_is_idempotent_but_rejects_conflict() -> None:
    bundle, registry, _ = configured_adapter()
    assert not registry.register(bundle.source)
    with pytest.raises(DepthCameraConfigurationError, match='conflicts'):
        registry.register(replace(bundle.source, producer_version='2.0.0', manifest_id=None))


def test_missing_calibration_cannot_activate() -> None:
    bundle = depth_test_fixture_bundle()
    registry = DepthSourceRegistry()
    registry.register(bundle.source)
    adapter = DepthLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id, None)
    with pytest.raises(DepthCameraLifecycleError, match='calibration'):
        adapter.activate()


def test_exact_pair_issues_compact_sealed_admission() -> None:
    bundle, _, adapter = configured_adapter()
    session = adapter.activate()
    assert adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session, 1_000),
        now_ns=1_000,
    ) is None
    admission = adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 1_000),
        now_ns=1_000,
    )
    assert admission is not None
    assert admission.session_id == session
    assert admission.frame.session_id == session
    assert admission.frame.valid_depth_count == 8
    assert adapter.diagnostics.event is DepthDiagnosticEvent.FRAME_ACCEPTED
    assert not hasattr(admission.frame, 'data')


def test_lifecycle_session_isolation_and_recovery() -> None:
    bundle, _, adapter = configured_adapter()
    first = adapter.activate()
    adapter.deactivate()
    assert adapter.state is DepthLifecycleState.INACTIVE
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, first, 1_000),
        now_ns=1_000,
    ) is None
    second = adapter.activate()
    assert second != first
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, first, 1_001),
        now_ns=1_001,
    ) is None
    adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, second, 1_002),
        now_ns=1_002,
    )
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, second, 1_002),
        now_ns=1_002,
    ) is not None


def test_wrong_frame_is_rejected_without_poisoning_recovery() -> None:
    bundle, _, adapter = configured_adapter()
    session = adapter.activate()
    assert adapter.submit_image(
        fixture_depth_image_metadata(
            bundle,
            session,
            1_000,
            frame_id='head_camera_optical_frame',
        ),
        now_ns=1_000,
    ) is None
    adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session, 1_001),
        now_ns=1_001,
    )
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 1_001),
        now_ns=1_001,
    ) is not None


def test_stale_future_out_of_order_and_duplicate_fail_closed() -> None:
    bundle = depth_test_fixture_bundle()
    registry = DepthSourceRegistry()
    registry.register(bundle.source)
    adapter = DepthLifecycleAdapter(
        registry,
        retention_ns=1_000,
        future_skew_ns=10,
        pair_wait_ns=100,
    )
    adapter.configure(bundle.source.source_id, bundle.calibration)
    session = adapter.activate()
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 1_000),
        now_ns=2_001,
    ) is None
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 2_020),
        now_ns=2_000,
    ) is None
    adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session, 2_000),
        now_ns=2_000,
    )
    admission = adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 2_000),
        now_ns=2_000,
    )
    assert admission is not None
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 2_000),
        now_ns=2_000,
    ) is None
    assert adapter.submit_image(
        fixture_depth_image_metadata(bundle, session, 1_999),
        now_ns=2_000,
    ) is None


def test_pending_pair_state_is_hard_bounded() -> None:
    bundle, _, adapter = configured_adapter()
    session = adapter.activate()
    for index in range(MAX_DEPTH_PENDING_PAIRS + 4):
        observed = 1_000 + index
        adapter.submit_image(
            fixture_depth_image_metadata(bundle, session, observed),
            now_ns=observed,
        )
    assert adapter.diagnostics.pending_image_count == MAX_DEPTH_PENDING_PAIRS
    assert adapter.diagnostics.evicted_count == 4


def test_shutdown_is_terminal() -> None:
    _, _, adapter = configured_adapter()
    adapter.shutdown()
    assert adapter.state is DepthLifecycleState.FINALIZED
    with pytest.raises(DepthCameraLifecycleError):
        adapter.activate()
