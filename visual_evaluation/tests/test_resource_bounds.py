from __future__ import annotations

import tracemalloc
import unittest

from ayyo_visual_evaluation import (
    DeterministicFixtureInvoker,
    VisualProducerEvaluator,
    VisualProducerRegistry,
    fixture_bundle,
)
from ayyo_world_model import VisualEvaluationDecision


class VisualEvaluationResourceTest(unittest.TestCase):
    def test_five_thousand_cycles_are_bounded_and_measured_as_python_allocations(self) -> None:
        tracemalloc.start()
        try:
            bundle = fixture_bundle(sample_count=5_000)
            registry = VisualProducerRegistry()
            registry.register(bundle.registration)
            outcome = VisualProducerEvaluator(
                registry,
                DeterministicFixtureInvoker(1_000),
            ).evaluate(
                producer_id=bundle.manifest.producer.producer_id,
                dataset=bundle.dataset,
                source=bundle.source,
                policy=bundle.policy,
                run_id="fixture.resource-five-thousand.v1",
            )
            metrics = outcome.report.metrics
            self.assertIs(
                VisualEvaluationDecision.MEETS_MECHANICAL_POLICY,
                outcome.report.decision,
            )
            self.assertEqual(5_000, metrics.attempted_count)
            self.assertEqual(5_000, metrics.admitted_count)
            self.assertEqual(0, metrics.rejected_count)
            self.assertEqual(5_000, len(outcome.admissions))
            self.assertEqual(5_000, len(outcome.report.records))
            self.assertIsNotNone(metrics.traced_python_current_bytes)
            self.assertIsNotNone(metrics.traced_python_peak_bytes)
            self.assertLess(metrics.traced_python_peak_bytes, 256 * 1_024 * 1_024)
            self.assertEqual(
                1,
                len({item.reference for item in outcome.admissions}),
            )
            self.assertEqual(
                1,
                len({item.requirement for item in outcome.admissions}),
            )
        finally:
            tracemalloc.stop()


if __name__ == "__main__":
    unittest.main()
