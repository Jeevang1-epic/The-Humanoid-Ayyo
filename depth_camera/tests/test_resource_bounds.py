from __future__ import annotations

import tracemalloc

from ayyo_depth_camera import (
    DepthLifecycleAdapter,
    DepthSourceRegistry,
    depth_test_fixture_bundle,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
)


def test_five_thousand_cycles_retain_only_compact_bounded_state() -> None:
    bundle = depth_test_fixture_bundle()
    registry = DepthSourceRegistry()
    registry.register(bundle.source)
    adapter = DepthLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    session = adapter.activate()
    last = None
    tracemalloc.start()
    try:
        for index in range(5_000):
            observed = 10_000_000_000 + index
            adapter.submit_camera_info(
                fixture_depth_camera_info_metadata(bundle, session, observed),
                now_ns=observed,
            )
            last = adapter.submit_image(
                fixture_depth_image_metadata(bundle, session, observed),
                now_ns=observed,
            )
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert last is not None
    assert adapter.diagnostics.accepted_count == 5_000
    assert adapter.diagnostics.rejected_count == 0
    assert adapter.diagnostics.pending_image_count == 0
    assert adapter.diagnostics.pending_camera_info_count == 0
    assert not hasattr(last.frame, 'data')
    assert 0 < current < 8 * 1024 * 1024
    assert 0 < peak < 16 * 1024 * 1024
