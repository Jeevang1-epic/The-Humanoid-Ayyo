from dataclasses import FrozenInstanceError
from unittest.mock import patch
import unittest

from ayyo_developmental_scenarios import recorded_success_report
from ayyo_teach_mode import (
    AYYO_ROBOT_ID,
    DemonstrationActionAuthority,
    DemonstrationActionDisposition,
    DemonstrationActionKind,
    DemonstrationClockKind,
    DemonstrationOutcomeStatus,
    ReferenceEvidenceStatus,
    DemonstrationSourceKind,
    ScenarioDemonstrationAdapterError,
    canonical_episode_json,
    capture_development_scenario_report,
    verify_episode,
)


DEVELOPMENT = 'development-only-neck-actuation'
DEFERRED = 'production-physical-request-deferred'
INVALID = 'invalid-development-command-rejected'


class StageSixDemonstrationAdapterTest(unittest.TestCase):
    def capture(self, scenario_id):
        report = recorded_success_report(scenario_id)
        return report, capture_development_scenario_report(report)

    def test_published_report_conversion_is_deterministic(self):
        for scenario_id in (DEVELOPMENT, DEFERRED, INVALID):
            with self.subTest(scenario_id=scenario_id):
                first_report, first = self.capture(scenario_id)
                second_report, second = self.capture(scenario_id)
                self.assertEqual(first_report.report_id, second_report.report_id)
                self.assertEqual(first.episode.episode_id, second.episode.episode_id)
                self.assertEqual(
                    canonical_episode_json(first.episode),
                    canonical_episode_json(second.episode),
                )

    def test_scenario_report_and_fingerprint_are_preserved(self):
        report, result = self.capture(DEVELOPMENT)
        episode = result.episode
        self.assertEqual(report.report_id, episode.provenance.source_ref)
        self.assertEqual(report.scenario_fingerprint, episode.provenance.source_fingerprint)
        self.assertEqual(report.scenario_fingerprint, episode.events[0].observation_references[0].fingerprint)
        self.assertIs(
            ReferenceEvidenceStatus.PASS,
            episode.events[0].observation_references[0].status,
        )
        self.assertTrue(verify_episode(episode).verified)

    def test_source_and_robot_provenance_are_preserved(self):
        report, result = self.capture(DEVELOPMENT)
        episode = result.episode
        self.assertIs(DemonstrationSourceKind.DEVELOPMENT_SCENARIO, episode.source_kind)
        self.assertEqual(AYYO_ROBOT_ID, episode.robot_id)
        captured_sources = {
            reference.reference_id
            for event in episode.events
            for reference in event.observation_references
        }
        self.assertTrue({item.source_id for item in report.sources} <= captured_sources)

    def test_report_without_source_time_does_not_fabricate_time(self):
        _, result = self.capture(DEVELOPMENT)
        self.assertIs(DemonstrationClockKind.UNAVAILABLE, result.episode.source_time.clock_kind)
        self.assertIsNone(result.episode.source_time.start_ns)
        self.assertIsNone(result.episode.source_time.end_ns)
        self.assertTrue(all(event.source_time_ns is None for event in result.episode.events))

    def test_development_motion_remains_development_only(self):
        _, result = self.capture(DEVELOPMENT)
        actions = tuple(
            action
            for event in result.episode.events
            for action in event.action_references
        )
        self.assertIs(DemonstrationOutcomeStatus.SUCCESS, result.episode.outcome.status)
        self.assertTrue(actions)
        self.assertTrue(
            all(
                action.authority is DemonstrationActionAuthority.DEVELOPMENT_ONLY
                for action in actions
            )
        )
        self.assertEqual(
            (0.1, 0.1, 0.0),
            tuple(action.target_value for action in actions),
        )
        self.assertIs(DemonstrationActionKind.DEVELOPMENT_RESET, actions[-1].kind)

    def test_production_defer_stays_deferred_with_zero_dispatch(self):
        report, result = self.capture(DEFERRED)
        actions = tuple(
            action
            for event in result.episode.events
            for action in event.action_references
        )
        self.assertEqual(0, report.production_dispatch_count)
        self.assertIs(DemonstrationOutcomeStatus.DEFERRED, result.episode.outcome.status)
        self.assertTrue(
            any(
                action.kind is DemonstrationActionKind.SAFETY_DECISION
                and action.disposition is DemonstrationActionDisposition.DEFERRED
                and action.reason_code == 'physical-movement-information-unavailable'
                for action in actions
            )
        )
        self.assertTrue(
            any(
                action.disposition is DemonstrationActionDisposition.NOT_DISPATCHED
                for action in actions
            )
        )
        self.assertTrue(
            all(action.authority is DemonstrationActionAuthority.NONE for action in actions)
        )

    def test_invalid_command_stays_rejected_and_state_remains_healthy(self):
        _, result = self.capture(INVALID)
        episode = result.episode
        self.assertIs(DemonstrationOutcomeStatus.REJECTED, episode.outcome.status)
        actions = tuple(
            action for event in episode.events for action in event.action_references
        )
        rejection = next(
            action
            for action in actions
            if action.disposition is DemonstrationActionDisposition.REJECTED
        )
        self.assertEqual(1.3, rejection.target_value)
        self.assertEqual('above-maximum', rejection.reason_code)
        references = {
            reference.reference_id
            for event in episode.events
            for reference in event.observation_references
        }
        self.assertIn('invalid-target-not-reached', references)
        self.assertIn('controller-remains-healthy', references)
        self.assertIn('post-rejection-query-works', references)

    def test_scenario_report_is_not_mutated(self):
        report = recorded_success_report(DEVELOPMENT)
        before = report.as_dict()
        capture_development_scenario_report(report)
        self.assertEqual(before, report.as_dict())
        with self.assertRaises(FrozenInstanceError):
            report.outcome = 'changed'

    def test_teacher_source_ref_is_provenance_not_authority(self):
        report = recorded_success_report(DEVELOPMENT)
        result = capture_development_scenario_report(
            report, teacher_source_ref='unverified-demonstrator-input.v1'
        )
        self.assertEqual(
            'unverified-demonstrator-input.v1',
            result.episode.provenance.teacher_source_ref,
        )
        self.assertNotIn('teacher', DemonstrationActionAuthority.__members__)
        self.assertNotIn('owner', DemonstrationActionAuthority.__members__)

    def test_adapter_never_launches_processes_or_writes_files(self):
        report = recorded_success_report(DEVELOPMENT)
        with (
            patch('subprocess.Popen') as popen,
            patch('subprocess.run') as run,
            patch('os.system') as system,
            patch('builtins.open') as open_file,
        ):
            result = capture_development_scenario_report(report)
        self.assertTrue(result.episode.events)
        popen.assert_not_called()
        run.assert_not_called()
        system.assert_not_called()
        open_file.assert_not_called()

    def test_tampered_report_fails_closed(self):
        report = recorded_success_report(DEVELOPMENT)
        object.__setattr__(report, 'scenario_fingerprint', 'development-scenario-sha256-' + '0' * 64)
        with self.assertRaisesRegex(ScenarioDemonstrationAdapterError, 'integrity'):
            capture_development_scenario_report(report)

    def test_all_six_published_reports_are_supported(self):
        for scenario_id in (
            'embodied-observation-baseline',
            'visual-anonymous-semantic-observation',
            DEFERRED,
            DEVELOPMENT,
            INVALID,
            'optional-visual-source-absent',
        ):
            with self.subTest(scenario_id=scenario_id):
                _, result = self.capture(scenario_id)
                self.assertTrue(verify_episode(result.episode).verified)


if __name__ == '__main__':
    unittest.main()
