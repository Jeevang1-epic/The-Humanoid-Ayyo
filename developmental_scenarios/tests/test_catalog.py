import unittest

from ayyo_developmental_scenarios import (
    FRAMEWORK_ID,
    FRAMEWORK_VERSION,
    InvalidScenarioDefinitionError,
    MAX_SCENARIOS_PER_INVOCATION,
    scenario_by_id,
    SCENARIO_CATALOG,
    ScenarioAuthority,
    ScenarioLaunchProfile,
)


class ScenarioCatalogTest(unittest.TestCase):
    def test_framework_identity_and_catalog_are_explicit_and_bounded(self):
        self.assertEqual('ayyo.developmental-scenarios.v1', FRAMEWORK_ID)
        self.assertEqual('1.0.0', FRAMEWORK_VERSION)
        self.assertEqual(6, len(SCENARIO_CATALOG))
        self.assertLessEqual(len(SCENARIO_CATALOG), MAX_SCENARIOS_PER_INVOCATION)

    def test_mandatory_scenarios_are_present(self):
        self.assertEqual(
            {
                'development-only-neck-actuation',
                'embodied-observation-baseline',
                'invalid-development-command-rejected',
                'optional-visual-source-absent',
                'production-physical-request-deferred',
                'visual-anonymous-semantic-observation',
            },
            {item.scenario_id for item in SCENARIO_CATALOG},
        )

    def test_only_two_control_scenarios_request_development_authority(self):
        authorized = {
            item.scenario_id
            for item in SCENARIO_CATALOG
            if item.authority is ScenarioAuthority.DEVELOPMENT_NECK_CONTROL
        }
        self.assertEqual(
            {
                'development-only-neck-actuation',
                'invalid-development-command-rejected',
            },
            authorized,
        )

    def test_production_defer_uses_observation_profile(self):
        definition = scenario_by_id('production-physical-request-deferred')
        self.assertIs(definition.launch_profile, ScenarioLaunchProfile.OBSERVATION)
        self.assertIs(definition.authority, ScenarioAuthority.NONE)

    def test_sensor_absence_uses_default_off_profile(self):
        definition = scenario_by_id('optional-visual-source-absent')
        self.assertIs(
            definition.launch_profile,
            ScenarioLaunchProfile.SENSOR_ABSENCE,
        )

    def test_scenario_fingerprints_are_unique(self):
        values = tuple(item.fingerprint for item in SCENARIO_CATALOG)
        self.assertEqual(len(values), len(set(values)))

    def test_step_and_assertion_order_is_deterministic(self):
        for definition in SCENARIO_CATALOG:
            assigned = tuple(
                assertion_id
                for step in definition.steps
                for assertion_id in step.assertion_ids
            )
            self.assertEqual(
                tuple(item.assertion_id for item in definition.assertions),
                assigned,
            )

    def test_unknown_scenario_id_fails_closed(self):
        with self.assertRaises(InvalidScenarioDefinitionError):
            scenario_by_id('arbitrary-script')


if __name__ == '__main__':
    unittest.main()
