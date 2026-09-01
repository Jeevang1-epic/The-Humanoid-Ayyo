from __future__ import annotations

import tracemalloc

from ayyo_head_audio import fixture_audio_observation

from helpers import configured_audio_adapter


def test_five_thousand_cycles_retain_only_compact_bounded_state() -> None:
    bundle, _, adapter = configured_audio_adapter()
    session = adapter.activate()
    last = None
    tracemalloc.start()
    try:
        for index in range(5_000):
            observed = 10_000_000_000 + index
            last = adapter.submit(
                fixture_audio_observation(bundle, session, observed),
                now_ns=observed,
            )
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert last is not None
    assert adapter.diagnostics.accepted_count == 5_000
    assert adapter.diagnostics.rejected_count == 0
    assert adapter.diagnostics.duplicate_count == 0
    assert adapter.diagnostics.retained_payload_bytes == 0
    assert not hasattr(last.frame, "data")
    assert 0 < current < 4 * 1_024 * 1_024
    assert 0 < peak < 16 * 1_024 * 1_024
    adapter.deactivate()
    adapter.shutdown()
    assert adapter.active_session_id is None
    assert adapter.source is None
