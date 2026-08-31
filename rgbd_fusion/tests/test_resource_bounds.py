import tracemalloc

from helpers import configured_pair, depth_admission, rgb


def test_five_thousand_exact_pairs_remain_bounded() -> None:
    bundle, depth_adapter, session, requirement, fusion = configured_pair()
    tracemalloc.start()
    last_pair = None
    for index in range(5_000):
        source_time = 1_000_000_000 + index * 1_000_000
        assert fusion.submit_rgb(
            rgb(requirement, source_time),
            now_ns=source_time,
        ) is None
        admission = fusion.submit_depth(
            depth_admission(bundle, depth_adapter, session, source_time).frame,
            now_ns=source_time,
        )
        assert admission is not None
        last_pair = admission.observation
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    diagnostics = fusion.diagnostics
    assert last_pair is not None
    assert diagnostics.accepted_count == 5_000
    assert diagnostics.pending_rgb_count == 0
    assert diagnostics.pending_depth_count == 0
    assert current < 4 * 1024 * 1024
    assert peak < 16 * 1024 * 1024
