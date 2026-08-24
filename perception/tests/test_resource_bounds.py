from __future__ import annotations

import tracemalloc
import unittest

from ayyo_perception import AdmissionStatus

from helpers import boundary, imu


class PerceptionResourceBoundsTest(unittest.TestCase):
    def test_high_rate_evidence_retains_only_constant_source_state(self) -> None:
        trust = boundary(ttl=1_000_000, freshness=500_000)
        for index in range(10_000):
            result = trust.admit(
                imu(time=index, angular=(index / 10_000.0, 0.0, 0.0)),
                now_ns=index,
                received_at_monotonic_ns=index,
            )
            self.assertEqual(AdmissionStatus.ACCEPTED, result.status)
        stats = trust.stats()
        self.assertEqual(10_000, stats.accepted_count)
        self.assertEqual(1, stats.tracked_source_key_count)
        self.assertLessEqual(stats.tracked_source_key_count, stats.configured_source_count * 2)

    def test_measured_high_rate_boundary_memory_is_bounded(self) -> None:
        trust = boundary(ttl=1_000_000, freshness=500_000)
        tracemalloc.start()
        try:
            for index in range(3_000):
                trust.admit(
                    imu(time=index, angular=(index / 3_000.0, 0.0, 0.0)),
                    now_ns=index,
                    received_at_monotonic_ns=index,
                )
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(current, 1_000_000)
        self.assertLess(peak, 2_000_000)


if __name__ == "__main__":
    unittest.main()
