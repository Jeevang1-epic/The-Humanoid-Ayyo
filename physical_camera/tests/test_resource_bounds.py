from __future__ import annotations

import tracemalloc
import unittest

from ayyo_physical_camera import (
    PhysicalCameraLifecycleAdapter,
    PhysicalCameraSourceRegistry,
    fixture_camera_info_metadata,
    fixture_image_metadata,
    physical_camera_fixture_bundle,
)


class PhysicalCameraResourceTest(unittest.TestCase):
    def test_five_thousand_pairs_keep_only_constant_live_state(self) -> None:
        bundle = physical_camera_fixture_bundle()
        registry = PhysicalCameraSourceRegistry()
        registry.register(bundle.source)
        adapter = PhysicalCameraLifecycleAdapter(registry)
        adapter.configure(bundle.source.source_id, bundle.calibration)
        session = adapter.activate()
        tracemalloc.start()
        try:
            for index in range(5_000):
                observed_at_ns = 1_000_000_000 + index * 1_000_000
                adapter.submit_camera_info(
                    fixture_camera_info_metadata(bundle, session, observed_at_ns),
                    now_ns=observed_at_ns,
                )
                admission = adapter.submit_image(
                    fixture_image_metadata(bundle, session, observed_at_ns),
                    now_ns=observed_at_ns,
                )
                self.assertIsNotNone(admission)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        diagnostics = adapter.diagnostics
        self.assertEqual(5_000, diagnostics.accepted_count)
        self.assertEqual(0, diagnostics.rejected_count)
        self.assertEqual(0, diagnostics.pending_image_count)
        self.assertEqual(0, diagnostics.pending_camera_info_count)
        self.assertGreater(current, 0)
        self.assertLess(peak, 16 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
