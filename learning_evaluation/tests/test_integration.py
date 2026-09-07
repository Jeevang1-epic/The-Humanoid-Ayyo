import unittest

from ayyo_developmental_scenarios import recorded_success_report
from ayyo_teach_mode import (
    DemonstrationActionAuthority,
    DemonstrationActionDisposition,
    DemonstrationOutcomeStatus,
    capture_development_scenario_report,
)
from ayyo_learning_evaluation import (
    DemonstrationEvaluationCorpus,
    OfflineEvaluationDisposition,
    evaluate_offline,
)

from helpers import fixture_candidate, matching_trial


SCENARIOS = (
    'embodied-observation-baseline',
    'visual-anonymous-semantic-observation',
    'production-physical-request-deferred',
    'development-only-neck-actuation',
    'invalid-development-command-rejected',
    'optional-visual-source-absent',
)


def stage_six_episode(scenario_id):
    return capture_development_scenario_report(recorded_success_report(scenario_id)).episode


class StageSixLearningEvaluationIntegrationTest(unittest.TestCase):
    def test_all_six_reviewed_adapters_form_an_explicit_corpus(self):
        episodes = tuple(stage_six_episode(item) for item in SCENARIOS)
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=episodes[:3],
            holdout_evaluation=episodes[3:],
            description='Reviewed Stage-6 demonstration evaluation corpus.',
        )
        self.assertEqual(3, len(corpus.candidate_evidence.episodes))
        self.assertEqual(3, len(corpus.holdout_evaluation.episodes))
        self.assertEqual(
            {item.episode_id for item in episodes[:3]},
            {item.episode_id for item in corpus.candidate_evidence.episodes},
        )

    def test_required_success_deferred_and_rejected_outcomes_remain_exact(self):
        development = stage_six_episode('development-only-neck-actuation')
        deferred = stage_six_episode('production-physical-request-deferred')
        rejected = stage_six_episode('invalid-development-command-rejected')
        self.assertIs(DemonstrationOutcomeStatus.SUCCESS, development.outcome.status)
        self.assertIs(DemonstrationOutcomeStatus.DEFERRED, deferred.outcome.status)
        self.assertIs(DemonstrationOutcomeStatus.REJECTED, rejected.outcome.status)
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=[development],
            holdout_evaluation=[deferred, rejected],
            description='Required positive and negative historical evidence.',
        )
        self.assertEqual(
            {DemonstrationOutcomeStatus.DEFERRED, DemonstrationOutcomeStatus.REJECTED},
            {item.outcome_status for item in corpus.holdout_evaluation.episodes},
        )

    def test_development_authority_and_targets_remain_historical_only(self):
        development = stage_six_episode('development-only-neck-actuation')
        actions = tuple(
            action for event in development.events for action in event.action_references
        )
        self.assertEqual((0.1, 0.1, 0.0), tuple(item.target_value for item in actions))
        self.assertTrue(
            all(item.authority is DemonstrationActionAuthority.DEVELOPMENT_ONLY for item in actions)
        )
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=[development],
            holdout_evaluation=[stage_six_episode('production-physical-request-deferred')],
            description='Development provenance remains evidence only.',
        )
        candidate = fixture_candidate(corpus)
        self.assertNotIn('authority', candidate.as_dict())

    def test_production_defer_retains_zero_dispatch_evidence(self):
        report = recorded_success_report('production-physical-request-deferred')
        episode = capture_development_scenario_report(report).episode
        self.assertEqual(0, report.production_dispatch_count)
        actions = tuple(action for event in episode.events for action in event.action_references)
        self.assertTrue(
            any(item.disposition is DemonstrationActionDisposition.NOT_DISPATCHED for item in actions)
        )
        self.assertTrue(all(item.authority is DemonstrationActionAuthority.NONE for item in actions))

    def test_stage_six_negative_holdouts_can_be_matched_without_repair(self):
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=[stage_six_episode('development-only-neck-actuation')],
            holdout_evaluation=[
                stage_six_episode('production-physical-request-deferred'),
                stage_six_episode('invalid-development-command-rejected'),
            ],
            description='Negative holdout truthfulness proof.',
        )
        candidate = fixture_candidate(corpus)
        trials = [matching_trial(candidate, item) for item in corpus.holdout_evaluation.episodes]
        evaluation = evaluate_offline(corpus=corpus, candidate=candidate, trials=trials)
        self.assertEqual(OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA, evaluation.disposition)
        self.assertEqual(
            {DemonstrationOutcomeStatus.DEFERRED, DemonstrationOutcomeStatus.REJECTED},
            {item.expected_outcome for item in trials},
        )


if __name__ == '__main__':
    unittest.main()
