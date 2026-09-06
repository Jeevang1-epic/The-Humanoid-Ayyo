import unittest

from ayyo_developmental_scenarios import evaluate_production_motion_boundary


class ProductionMotionBoundaryTest(unittest.TestCase):
    def test_real_public_contract_chain_remains_deferred(self):
        result = evaluate_production_motion_boundary()
        self.assertEqual('propose', result.executive_decision)
        self.assertEqual('deferred', result.safety_disposition)
        self.assertEqual(
            'physical_movement_information_unavailable',
            result.safety_reason,
        )
        self.assertEqual('ineligible', result.skill_binding_status)
        self.assertEqual('safety_deferred', result.skill_binding_reason)
        self.assertEqual('deferred', result.runtime_eligibility)
        self.assertEqual('upstream_deferred', result.runtime_reason)
        self.assertEqual('not_eligible', result.dispatch_status)

    def test_production_request_has_zero_side_effect_counts(self):
        result = evaluate_production_motion_boundary()
        self.assertEqual(0, result.production_dispatch_count)
        self.assertEqual(0, result.development_service_call_count)
        self.assertEqual(0, result.durable_memory_write_count)

    def test_boundary_result_is_deterministic(self):
        self.assertEqual(
            evaluate_production_motion_boundary(),
            evaluate_production_motion_boundary(),
        )


if __name__ == '__main__':
    unittest.main()
