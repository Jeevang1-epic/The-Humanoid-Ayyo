from dataclasses import FrozenInstanceError
import unittest

from ayyo_developmental_scenarios import (
    AssertionOutcome,
    CleanupOutcome,
    DevelopmentScenarioAssertion,
    DevelopmentScenarioAssertionResult,
    DevelopmentScenarioDefinition,
    DevelopmentScenarioReport,
    DevelopmentScenarioStep,
    InvalidScenarioDefinitionError,
    InvalidScenarioResultError,
    MAX_ASSERTIONS_PER_SCENARIO,
    MAX_REASONS_PER_REPORT,
    MAX_SOURCE_SUMMARIES,
    MAX_STEPS_PER_SCENARIO,
    scenario_by_id,
    ScenarioAuthority,
    ScenarioCategory,
    ScenarioCleanupResult,
    ScenarioFailureReason,
    ScenarioLaunchProfile,
    ScenarioObservedIdentity,
    ScenarioOperation,
    ScenarioOutcome,
    ScenarioPolicyDecision,
    ScenarioSourceSummary,
)


def definition(**overrides):
    assertion = DevelopmentScenarioAssertion('assertion-one', 'One exact check.')
    arguments = {
        'scenario_id': 'bounded-scenario',
        'version': '1.0.0',
        'category': ScenarioCategory.EMBODIED_OBSERVATION,
        'description': 'A bounded scenario definition.',
        'launch_profile': ScenarioLaunchProfile.OBSERVATION,
        'expected_safe_outcome': 'The test remains inert.',
        'authority': ScenarioAuthority.NONE,
        'steps': (
            DevelopmentScenarioStep(
                'step-one',
                ScenarioOperation.WAIT_FOR_CLOCK,
                1_000,
                (assertion.assertion_id,),
            ),
        ),
        'assertions': (assertion,),
    }
    arguments.update(overrides)
    return DevelopmentScenarioDefinition(**arguments)


def passing_result(assertion_id='assertion-one'):
    return DevelopmentScenarioAssertionResult(
        assertion_id,
        AssertionOutcome.PASS,
        'The fixed check passed.',
    )


def report(**overrides):
    source_definition = overrides.pop('definition', definition())
    arguments = {
        'definition': source_definition,
        'outcome': ScenarioOutcome.PASS,
        'assertion_results': tuple(
            DevelopmentScenarioAssertionResult(
                assertion.assertion_id,
                AssertionOutcome.PASS,
                'The fixed check passed.',
            )
            for assertion in source_definition.assertions
        ),
        'failure_reasons': (),
        'observed_identities': (ScenarioObservedIdentity('robot', 'ayyo.robot.v1'),),
        'policy_decisions': (),
        'development_authority_used': False,
        'production_dispatch_count': 0,
        'sources': (
            ScenarioSourceSummary('source.simulation.v1', 'simulation', 'ros2.v1'),
        ),
        'cleanup': ScenarioCleanupResult(CleanupOutcome.CLEAN, 0, 'Owned set is empty.'),
    }
    arguments.update(overrides)
    return DevelopmentScenarioReport(**arguments)


class ScenarioDefinitionTest(unittest.TestCase):
    def test_definition_is_immutable(self):
        item = definition()
        with self.assertRaises(FrozenInstanceError):
            item.scenario_id = 'changed'

    def test_equivalent_definition_has_deterministic_fingerprint(self):
        self.assertEqual(definition().fingerprint, definition().fingerprint)

    def test_expected_outcome_changes_fingerprint(self):
        self.assertNotEqual(
            definition().fingerprint,
            definition(expected_safe_outcome='A different semantic result.').fingerprint,
        )

    def test_invalid_version_and_identifier_are_rejected(self):
        for changes in ({'version': 'v1'}, {'scenario_id': 'Bad ID'}):
            with self.subTest(changes=changes), self.assertRaises(
                InvalidScenarioDefinitionError
            ):
                definition(**changes)

    def test_duplicate_step_ids_are_rejected(self):
        first = definition().steps[0]
        with self.assertRaisesRegex(InvalidScenarioDefinitionError, 'unique'):
            definition(steps=(first, first))

    def test_duplicate_assertion_ids_are_rejected(self):
        assertion = definition().assertions[0]
        with self.assertRaisesRegex(InvalidScenarioDefinitionError, 'unique'):
            definition(assertions=(assertion, assertion))

    def test_unknown_typed_operation_is_rejected(self):
        with self.assertRaisesRegex(InvalidScenarioDefinitionError, 'unknown'):
            DevelopmentScenarioStep('step', 'shell', 1_000, ('assertion',))

    def test_arbitrary_shell_execution_is_not_an_operation(self):
        vocabulary = {item.value for item in ScenarioOperation}
        self.assertNotIn('shell', vocabulary)
        self.assertNotIn('command', vocabulary)
        self.assertFalse(any('topic-name' in item for item in vocabulary))

    def test_step_and_assertion_bounds_are_enforced(self):
        step = definition().steps[0]
        with self.assertRaises(InvalidScenarioDefinitionError):
            definition(steps=tuple(step for _ in range(MAX_STEPS_PER_SCENARIO + 1)))
        with self.assertRaises(InvalidScenarioDefinitionError):
            definition(
                assertions=tuple(
                    DevelopmentScenarioAssertion(f'a-{index}', 'Bounded check.')
                    for index in range(MAX_ASSERTIONS_PER_SCENARIO + 1)
                ),
                steps=(
                    DevelopmentScenarioStep(
                        'step',
                        ScenarioOperation.WAIT_FOR_CLOCK,
                        1_000,
                        tuple(
                            f'a-{index}'
                            for index in range(MAX_ASSERTIONS_PER_SCENARIO + 1)
                        ),
                    ),
                ),
            )

    def test_unassigned_and_reused_assertions_are_rejected(self):
        two = DevelopmentScenarioAssertion('assertion-two', 'Another check.')
        with self.assertRaises(InvalidScenarioDefinitionError):
            definition(assertions=definition().assertions + (two,))
        with self.assertRaises(InvalidScenarioDefinitionError):
            definition(
                steps=(definition().steps[0], definition().steps[0]),
            )

    def test_timeout_is_bounded(self):
        for timeout in (99, 120_001, 1.5):
            with self.subTest(timeout=timeout), self.assertRaises(
                InvalidScenarioDefinitionError
            ):
                DevelopmentScenarioStep(
                    'step',
                    ScenarioOperation.WAIT_FOR_CLOCK,
                    timeout,
                    ('assertion',),
                )


class ScenarioResultTest(unittest.TestCase):
    def test_assertion_and_report_are_immutable(self):
        result = passing_result()
        scenario_report = report()
        with self.assertRaises(FrozenInstanceError):
            result.detail = 'changed'
        with self.assertRaises(FrozenInstanceError):
            scenario_report.outcome = ScenarioOutcome.FAIL

    def test_report_identity_is_deterministic(self):
        self.assertEqual(report().report_id, report().report_id)

    def test_report_identity_excludes_runtime_timing_and_process_fields(self):
        document = report().as_dict()
        self.assertNotIn('pid', repr(document).lower())
        self.assertNotIn('started_at', document)
        self.assertNotIn('duration', document)

    def test_result_input_mutation_is_isolated_by_immutable_tuples(self):
        identities = (ScenarioObservedIdentity('robot', 'ayyo.robot.v1'),)
        scenario_report = report(observed_identities=identities)
        identities += (ScenarioObservedIdentity('sensor', 'sensor.v1'),)
        self.assertEqual(1, len(scenario_report.observed_identities))

    def test_passing_assertion_cannot_carry_failure_reason(self):
        with self.assertRaises(InvalidScenarioResultError):
            DevelopmentScenarioAssertionResult(
                'assertion',
                AssertionOutcome.PASS,
                'Contradictory result.',
                (ScenarioFailureReason.ASSERTION_FAILED,),
            )

    def test_failed_assertion_requires_reason(self):
        with self.assertRaises(InvalidScenarioResultError):
            DevelopmentScenarioAssertionResult(
                'assertion',
                AssertionOutcome.FAIL,
                'Missing typed reason.',
            )

    def test_one_failed_required_assertion_fails_scenario(self):
        failed = DevelopmentScenarioAssertionResult(
            'assertion-one',
            AssertionOutcome.FAIL,
            'The exact check failed.',
            (ScenarioFailureReason.ASSERTION_FAILED,),
        )
        result = report(
            outcome=ScenarioOutcome.FAIL,
            assertion_results=(failed,),
            failure_reasons=(ScenarioFailureReason.ASSERTION_FAILED,),
        )
        self.assertIs(result.outcome, ScenarioOutcome.FAIL)
        with self.assertRaises(InvalidScenarioResultError):
            report(assertion_results=(failed,))

    def test_report_reason_source_and_policy_bounds_are_enforced(self):
        repeated_reasons = tuple(
            ScenarioFailureReason.ASSERTION_FAILED
            for _ in range(MAX_REASONS_PER_REPORT + 1)
        )
        with self.assertRaises(InvalidScenarioResultError):
            report(failure_reasons=repeated_reasons)
        sources = tuple(
            ScenarioSourceSummary(f'source.{index}', 'simulation', 'ros2.v1')
            for index in range(MAX_SOURCE_SUMMARIES + 1)
        )
        with self.assertRaises(InvalidScenarioResultError):
            report(sources=sources)

    def test_cleanup_representation_is_fail_closed(self):
        clean = ScenarioCleanupResult(CleanupOutcome.CLEAN, 0, 'Owned set is empty.')
        self.assertEqual(0, clean.owned_processes_remaining)
        with self.assertRaises(InvalidScenarioResultError):
            ScenarioCleanupResult(CleanupOutcome.CLEAN, 1, 'One child remains.')

    def test_machine_local_identity_is_rejected_from_semantic_text(self):
        with self.assertRaises(InvalidScenarioResultError):
            ScenarioCleanupResult(
                CleanupOutcome.INCOMPLETE,
                1,
                'Process pid=123 remained under /home/example.',
            )

    def test_production_and_development_authority_are_distinct(self):
        production = scenario_by_id('production-physical-request-deferred')
        development = scenario_by_id('development-only-neck-actuation')
        self.assertIs(production.authority, ScenarioAuthority.NONE)
        self.assertIs(
            development.authority,
            ScenarioAuthority.DEVELOPMENT_NECK_CONTROL,
        )
        with self.assertRaises(InvalidScenarioResultError):
            report(definition=production, development_authority_used=True)

    def test_observed_and_policy_identities_must_be_unique(self):
        identity = ScenarioObservedIdentity('robot', 'ayyo.robot.v1')
        with self.assertRaises(InvalidScenarioResultError):
            report(observed_identities=(identity, identity))
        decision = ScenarioPolicyDecision('safety', 'deferred', 'policy-boundary')
        with self.assertRaises(InvalidScenarioResultError):
            report(policy_decisions=(decision, decision))


if __name__ == '__main__':
    unittest.main()
