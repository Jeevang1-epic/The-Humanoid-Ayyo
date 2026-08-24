from __future__ import annotations

import tracemalloc
import unittest

from helpers import entity_observation, memory


class ResourceBoundsTest(unittest.TestCase):
    def test_long_running_updates_keep_reference_slots_bounded(self) -> None:
        store = memory(entities=8, recent=16, ttl=100_000)
        for index in range(5_000):
            store.ingest(
                entity_observation(
                    f"object.{index % 32}",
                    time=index,
                    value=index,
                ),
                now_ns=index,
                received_at_monotonic_ns=index,
            )
        stats = store.stats(now_ns=4_999)
        self.assertEqual(8, stats.current_entity_count)
        self.assertEqual(16, stats.recent_evidence_count)
        self.assertLessEqual(stats.retained_unique_observation_count, 24)
        self.assertLessEqual(stats.retained_observation_reference_count, 24)

    def test_measured_peak_for_repeated_compact_updates_is_bounded(self) -> None:
        store = memory(entities=16, recent=32, ttl=100_000)
        tracemalloc.start()
        try:
            for index in range(2_000):
                store.ingest(
                    entity_observation(
                        f"object.{index % 64}",
                        time=index,
                        value={"sample": index, "label": "bounded"},
                    ),
                    now_ns=index,
                    received_at_monotonic_ns=index,
                )
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(current, 2_000_000)
        self.assertLess(peak, 8_000_000)

    def test_rapid_entity_create_cycles_do_not_grow_current_world(self) -> None:
        store = memory(entities=4, recent=5, ttl=10_000)
        for index in range(1_000):
            store.ingest(
                entity_observation(f"transient.{index}", time=index),
                now_ns=index,
                received_at_monotonic_ns=index,
            )
        stats = store.stats(now_ns=999)
        self.assertEqual(4, stats.current_entity_count)
        self.assertEqual(5, stats.recent_evidence_count)
        self.assertEqual(996, stats.eviction_count)


if __name__ == "__main__":
    unittest.main()
