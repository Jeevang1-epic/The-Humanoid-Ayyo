import unittest

from ayyo_developmental_scenarios import (
    AssertionOutcome,
    CleanupOutcome,
    DevelopmentScenarioAssertionResult,
    DevelopmentScenarioRunner,
    DevelopmentScenarioStepResult,
    recorded_success_report,
    scenario_by_id,
    ScenarioCleanupResult,
    ScenarioExecutionError,
    ScenarioFailureReason,
    ScenarioObservedIdentity,
    ScenarioOutcome,
    ScenarioSourceSummary,
)


class Executor:
    def __init__(self, *, fail_first=False, cleanup=CleanupOutcome.CLEAN):
        self.fail_first = fail_first
        self.cleanup_outcome = cleanup
        self.calls = []
        self.cleanup_calls = 0

    def execute(self, definition, step):
        self.calls.append(step.operation)
        assertions = []
        for index, assertion_id in enumerate(step.assertion_ids):
            failed = self.fail_first and not self.calls[:-1] and index == 0
            assertions.append(
                DevelopmentScenarioAssertionResult(
                    assertion_id,
                    AssertionOutcome.FAIL if failed else AssertionOutcome.PASS,
                    'Fixed operation result.',
                    (
                        (ScenarioFailureReason.ASSERTION_FAILED,)
                        if failed
                        else ()
                    ),
                )
            )
        return DevelopmentScenarioStepResult(
            step.step_id,
            step.operation,
            tuple(assertions),
        )

    def observed_identities(self):
        return (ScenarioObservedIdentity('robot', 'ayyo.robot.v1'),)

    def policy_decisions(self):
        return ()

    def development_authority_used(self):
        return False

    def production_dispatch_count(self):
        return 0

    def source_summaries(self):
        return (ScenarioSourceSummary('source.simulation.v1', 'simulation', 'ros2.v1'),)

    def cleanup(self):
        self.cleanup_calls += 1
        remaining = 1 if self.cleanup_outcome is CleanupOutcome.INCOMPLETE else 0
        return ScenarioCleanupResult(
            self.cleanup_outcome,
            remaining,
            'Owned process cleanup result.',
        )


class BadExecutor(Executor):
    def execute(self, definition, step):
        result = super().execute(definition, step)
        return DevelopmentScenarioStepResult(
            'wrong-step',
            result.operation,
            result.assertions,
        )


class ScenarioRunnerTest(unittest.TestCase):
    def setUp(self):
        self.definition = scenario_by_id('optional-visual-source-absent')

    def test_runner_executes_typed_steps_in_definition_order(self):
        executor = Executor()
        result = DevelopmentScenarioRunner().run(self.definition, executor)
        self.assertIs(result.outcome, ScenarioOutcome.PASS)
        self.assertEqual(
            tuple(step.operation for step in self.definition.steps),
            tuple(executor.calls),
        )
        self.assertEqual(1, executor.cleanup_calls)

    def test_failed_assertion_fails_scenario(self):
        result = DevelopmentScenarioRunner().run(
            self.definition,
            Executor(fail_first=True),
        )
        self.assertIs(result.outcome, ScenarioOutcome.FAIL)
        self.assertIn(ScenarioFailureReason.ASSERTION_FAILED, result.failure_reasons)

    def test_incomplete_cleanup_fails_scenario(self):
        result = DevelopmentScenarioRunner().run(
            self.definition,
            Executor(cleanup=CleanupOutcome.INCOMPLETE),
        )
        self.assertIs(result.outcome, ScenarioOutcome.FAIL)
        self.assertIn(ScenarioFailureReason.CLEANUP_INCOMPLETE, result.failure_reasons)

    def test_mismatched_executor_result_fails_closed_and_still_cleans_up(self):
        executor = BadExecutor()
        with self.assertRaisesRegex(Exception, 'does not match'):
            DevelopmentScenarioRunner().run(self.definition, executor)
        self.assertEqual(1, executor.cleanup_calls)

    def test_batch_invocation_is_bounded(self):
        runner = DevelopmentScenarioRunner()
        with self.assertRaises(ScenarioExecutionError):
            runner.run_batch(())
        work = tuple((self.definition, Executor()) for _ in range(9))
        with self.assertRaises(ScenarioExecutionError):
            runner.run_batch(work)

    def test_recorded_reports_are_deterministic_and_dispatch_free(self):
        first = recorded_success_report('production-physical-request-deferred')
        second = recorded_success_report('production-physical-request-deferred')
        self.assertEqual(first.report_id, second.report_id)
        self.assertEqual(0, first.production_dispatch_count)
        self.assertFalse(first.development_authority_used)

    def test_recorded_development_report_marks_only_development_authority(self):
        result = recorded_success_report('development-only-neck-actuation')
        self.assertTrue(result.development_authority_used)
        self.assertEqual(0, result.production_dispatch_count)


if __name__ == '__main__':
    unittest.main()
