from dataclasses import FrozenInstanceError
import math
import unittest

from ayyo_teach_mode import DemonstrationOutcomeStatus
from ayyo_learning_evaluation import (
    EVALUATION_REPORT_SCHEMA_ID,
    EVALUATION_REPORT_SCHEMA_VERSION,
    OFFLINE_EVALUATION_CONTRACT_ID,
    OFFLINE_EVALUATION_CONTRACT_VERSION,
    CandidateLineageError,
    CorpusPartition,
    DemonstrationEpisodeReference,
    EvaluationCount,
    EvaluationReportReason,
    EvaluationTrialError,
    ExactMetric,
    HoldoutPartitionError,
    OfflineEvaluationDisposition,
    OfflineEvaluationReport,
    OfflineTrialReason,
    OfflineTrialResult,
    OfflineTrialStatus,
    evaluate_offline,
    verify_evaluation_report,
    verify_trial_result,
)

from helpers import fingerprint, fixture_candidate, fixture_corpus, matching_trial


def copied_reference(reference, **overrides):
    fields = {
        'episode_id': reference.episode_id,
        'episode_fingerprint': reference.episode_fingerprint,
        'partition': reference.partition,
        'robot_id': reference.robot_id,
        'source_kind': reference.source_kind,
        'outcome_status': reference.outcome_status,
        'capture_policy_id': reference.capture_policy_id,
        'capture_policy_version': reference.capture_policy_version,
        'capture_policy_fingerprint': reference.capture_policy_fingerprint,
    }
    fields.update(overrides)
    return DemonstrationEpisodeReference(**fields)


def rebuilt_report(report, **overrides):
    fields = {
        'candidate_id': report.candidate_id,
        'candidate_fingerprint': report.candidate_fingerprint,
        'candidate_evidence_set_id': report.candidate_evidence_set_id,
        'candidate_evidence_set_fingerprint': report.candidate_evidence_set_fingerprint,
        'holdout_evidence_set_id': report.holdout_evidence_set_id,
        'holdout_evidence_set_fingerprint': report.holdout_evidence_set_fingerprint,
        'evaluation_contract_id': report.evaluation_contract_id,
        'evaluation_contract_version': report.evaluation_contract_version,
        'trial_ids': report.trial_ids,
        'evaluated_holdout_episode_ids': report.evaluated_holdout_episode_ids,
        'missing_holdout_episode_ids': report.missing_holdout_episode_ids,
        'incomplete_holdout_episode_ids': report.incomplete_holdout_episode_ids,
        'status_counts': report.status_counts,
        'historical_outcome_counts': report.historical_outcome_counts,
        'aggregate_metrics': report.aggregate_metrics,
        'coverage_numerator': report.coverage_numerator,
        'coverage_denominator': report.coverage_denominator,
        'reasons': report.reasons,
        'disposition': report.disposition,
    }
    fields.update(overrides)
    return OfflineEvaluationReport._create(**fields)


class OfflineEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.corpus = fixture_corpus()
        self.candidate = fixture_candidate(self.corpus)
        self.references = self.corpus.holdout_evaluation.episodes

    def all_matching(self):
        return [matching_trial(self.candidate, item) for item in self.references]

    def test_trial_and_report_are_immutable(self):
        trial = self.all_matching()[0]
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=self.all_matching())
        for target, name in ((trial, 'status'), (report, 'disposition')):
            with self.subTest(name=name), self.assertRaises((FrozenInstanceError, AttributeError)):
                setattr(target, name, 'changed')

    def test_matching_results_produce_deterministic_meets_report(self):
        trials = self.all_matching()
        first = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=trials)
        second = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=list(reversed(trials)))
        self.assertEqual(first, second)
        self.assertEqual(OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA, first.disposition)
        self.assertEqual((2, 2), (first.coverage_numerator, first.coverage_denominator))
        self.assertTrue(verify_evaluation_report(first))

    def test_report_contract_and_schema_are_explicit(self):
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[])
        self.assertEqual(EVALUATION_REPORT_SCHEMA_ID, report.schema_id)
        self.assertEqual(EVALUATION_REPORT_SCHEMA_VERSION, report.schema_version)
        self.assertEqual(OFFLINE_EVALUATION_CONTRACT_ID, report.evaluation_contract_id)
        self.assertEqual(OFFLINE_EVALUATION_CONTRACT_VERSION, report.evaluation_contract_version)

    def test_zero_results_is_explicitly_incomplete(self):
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[])
        self.assertEqual(OfflineEvaluationDisposition.INCOMPLETE, report.disposition)
        self.assertEqual(0, report.coverage_numerator)
        self.assertEqual(2, report.coverage_denominator)
        self.assertEqual(2, len(report.missing_holdout_episode_ids))
        self.assertIn(EvaluationReportReason.MISSING_HOLDOUT_TRIAL, report.reasons)

    def test_missing_trial_is_not_fabricated_or_dropped(self):
        trial = matching_trial(self.candidate, self.references[0])
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial])
        self.assertEqual(OfflineEvaluationDisposition.INCOMPLETE, report.disposition)
        self.assertEqual((1, 2), (report.coverage_numerator, report.coverage_denominator))
        self.assertEqual((self.references[1].episode_id,), report.missing_holdout_episode_ids)

    def test_explicit_incomplete_trial_remains_incomplete(self):
        reference = self.references[0]
        incomplete = matching_trial(
            self.candidate,
            reference,
            observed_outcome=None,
            status=OfflineTrialStatus.INCOMPLETE,
            reasons=(OfflineTrialReason.RESULT_UNAVAILABLE,),
            metrics=(),
        )
        report = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[incomplete, matching_trial(self.candidate, self.references[1])],
        )
        self.assertEqual(OfflineEvaluationDisposition.INCOMPLETE, report.disposition)
        self.assertEqual((reference.episode_id,), report.incomplete_holdout_episode_ids)
        self.assertIn(EvaluationReportReason.INCOMPLETE_HOLDOUT_TRIAL, report.reasons)

    def test_mismatch_is_counted_and_does_not_meet_criteria(self):
        reference = self.references[0]
        mismatch = matching_trial(
            self.candidate,
            reference,
            observed_outcome=DemonstrationOutcomeStatus.FAILURE,
            status=OfflineTrialStatus.OUTCOME_MISMATCH,
            reasons=(OfflineTrialReason.DIFFERENT_OUTCOME_OBSERVED,),
        )
        report = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[mismatch, matching_trial(self.candidate, self.references[1])],
        )
        self.assertEqual(OfflineEvaluationDisposition.DOES_NOT_MEET_OFFLINE_CRITERIA, report.disposition)
        counts = {item.value: item.count for item in report.status_counts}
        self.assertEqual(1, counts['outcome_mismatch'])
        self.assertEqual(1, counts['outcome_match'])
        self.assertIn(EvaluationReportReason.HOLDOUT_OUTCOME_MISMATCH, report.reasons)

    def test_negative_deferred_and_rejected_history_is_retained(self):
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=self.all_matching())
        counts = {item.value: item.count for item in report.historical_outcome_counts}
        self.assertEqual(1, counts['deferred'])
        self.assertEqual(1, counts['rejected'])
        self.assertEqual(0, counts['success'])
        self.assertEqual(
            {DemonstrationOutcomeStatus.DEFERRED, DemonstrationOutcomeStatus.REJECTED},
            {item.expected_outcome for item in self.all_matching()},
        )

    def test_exact_metrics_aggregate_as_integer_rationals(self):
        trials = [
            matching_trial(
                self.candidate,
                reference,
                metrics=(ExactMetric('outcome-agreement', index, 3),),
            )
            for index, reference in enumerate(self.references, start=1)
        ]
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=trials)
        self.assertEqual(('outcome-agreement', 3, 6), (
            report.aggregate_metrics[0].metric_id,
            report.aggregate_metrics[0].numerator,
            report.aggregate_metrics[0].denominator,
        ))

    def test_metric_rejects_float_bool_nan_and_zero_denominator(self):
        for numerator, denominator in (
            (math.nan, 1), (math.inf, 1), (True, 1), (1.0, 1), (1, 0)
        ):
            with self.subTest(value=(numerator, denominator)), self.assertRaises(EvaluationTrialError):
                ExactMetric('metric', numerator, denominator)

    def test_trial_status_cannot_reinterpret_outcomes(self):
        reference = self.references[0]
        with self.assertRaisesRegex(EvaluationTrialError, 'preserve'):
            matching_trial(
                self.candidate,
                reference,
                observed_outcome=DemonstrationOutcomeStatus.SUCCESS,
                status=OfflineTrialStatus.OUTCOME_MATCH,
            )
        with self.assertRaisesRegex(EvaluationTrialError, 'different'):
            matching_trial(
                self.candidate,
                reference,
                observed_outcome=reference.outcome_status,
                status=OfflineTrialStatus.OUTCOME_MISMATCH,
            )

    def test_duplicate_trial_is_rejected(self):
        trial = matching_trial(self.candidate, self.references[0])
        with self.assertRaisesRegex(EvaluationTrialError, 'duplicate'):
            evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial, trial])

    def test_wrong_candidate_lineage_is_rejected(self):
        other = fixture_candidate(self.corpus, semantic_version='0.2.0')
        trial = matching_trial(other, self.references[0])
        with self.assertRaisesRegex(CandidateLineageError, 'different candidate'):
            evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial])

    def test_candidate_from_wrong_corpus_is_rejected(self):
        from helpers import fixture_episode
        from ayyo_learning_evaluation import DemonstrationEvaluationCorpus

        other_corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=[fixture_episode('different-candidate')],
            holdout_evaluation=[fixture_episode('different-holdout')],
            description='Different verified corpus.',
        )
        with self.assertRaisesRegex(CandidateLineageError, 'does not belong'):
            evaluate_offline(corpus=other_corpus, candidate=self.candidate, trials=[])

    def test_unknown_episode_is_rejected(self):
        reference = copied_reference(
            self.references[0],
            episode_id='demonstration-episode-sha256-' + 'a' * 64,
            episode_fingerprint='demonstration-episode-content-sha256-' + 'b' * 64,
        )
        trial = matching_trial(self.candidate, reference)
        with self.assertRaisesRegex(EvaluationTrialError, 'unknown'):
            evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial])

    def test_wrong_episode_fingerprint_is_rejected(self):
        reference = copied_reference(
            self.references[0],
            episode_fingerprint='demonstration-episode-content-sha256-' + 'c' * 64,
        )
        trial = matching_trial(self.candidate, reference)
        with self.assertRaisesRegex(EvaluationTrialError, 'fingerprint'):
            evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial])

    def test_candidate_evidence_masquerading_as_holdout_is_rejected(self):
        candidate_reference = self.corpus.candidate_evidence.episodes[0]
        fake_holdout = copied_reference(
            candidate_reference, partition=CorpusPartition.HOLDOUT_EVALUATION
        )
        trial = matching_trial(self.candidate, fake_holdout)
        with self.assertRaisesRegex(HoldoutPartitionError, 'masquerading'):
            evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial])

    def test_public_trial_constructor_rejects_candidate_partition(self):
        with self.assertRaises(HoldoutPartitionError):
            matching_trial(self.candidate, self.corpus.candidate_evidence.episodes[0])

    def test_tampered_trial_and_wrong_contract_fail_integrity(self):
        trial = matching_trial(self.candidate, self.references[0])
        object.__setattr__(trial, 'evaluation_contract_version', '2.0.0')
        self.assertFalse(verify_trial_result(trial))
        with self.assertRaisesRegex(EvaluationTrialError, 'integrity'):
            evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=[trial])

    def test_trial_reason_and_metric_collections_are_snapshotted(self):
        reasons = [OfflineTrialReason.EXPECTED_OUTCOME_OBSERVED]
        metrics = [ExactMetric('outcome-agreement', 1, 1)]
        trial = matching_trial(self.candidate, self.references[0], reasons=reasons, metrics=metrics)
        reasons.clear()
        metrics.clear()
        self.assertEqual(1, len(trial.reasons))
        self.assertEqual(1, len(trial.metrics))

    def test_report_tampering_is_detected(self):
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=self.all_matching())
        object.__setattr__(report, 'coverage_numerator', 0)
        self.assertFalse(verify_evaluation_report(report))

    def test_genuine_trial_ids_cannot_support_rewritten_all_success_report(self):
        mismatch = matching_trial(
            self.candidate,
            self.references[0],
            observed_outcome=DemonstrationOutcomeStatus.FAILURE,
            status=OfflineTrialStatus.OUTCOME_MISMATCH,
            reasons=(OfflineTrialReason.DIFFERENT_OUTCOME_OBSERVED,),
        )
        genuine = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[mismatch, matching_trial(self.candidate, self.references[1])],
        )
        forged = rebuilt_report(
            genuine,
            status_counts=(
                EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 2),
                EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 0),
                EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
            ),
            reasons=(EvaluationReportReason.ALL_HOLDOUT_OUTCOMES_MATCH,),
            disposition=OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA,
        )

        self.assertFalse(verify_evaluation_report(forged))

    def test_report_verifier_rejects_coverage_and_partition_contradictions(self):
        complete = evaluate_offline(
            corpus=self.corpus, candidate=self.candidate, trials=self.all_matching()
        )
        one_missing = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[self.all_matching()[0]],
        )
        incomplete_trial = matching_trial(
            self.candidate,
            self.references[0],
            observed_outcome=None,
            status=OfflineTrialStatus.INCOMPLETE,
            reasons=(OfflineTrialReason.RESULT_UNAVAILABLE,),
            metrics=(),
        )
        one_incomplete = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[incomplete_trial, self.all_matching()[1]],
        )
        zero_status_counts = tuple(
            EvaluationCount(status.value, 0) for status in OfflineTrialStatus
        )
        contradictions = {
            'coverage_without_trials': rebuilt_report(
                complete,
                trial_ids=(),
                evaluated_holdout_episode_ids=(),
                missing_holdout_episode_ids=(),
                status_counts=zero_status_counts,
                aggregate_metrics=(),
                coverage_numerator=complete.coverage_denominator,
            ),
            'numerator_not_evaluated_count': rebuilt_report(
                complete, coverage_numerator=1
            ),
            'complete_claim_with_missing': rebuilt_report(
                one_missing, coverage_numerator=one_missing.coverage_denominator
            ),
            'complete_claim_with_incomplete': rebuilt_report(
                one_incomplete,
                coverage_numerator=one_incomplete.coverage_denominator,
            ),
            'duplicate_evaluated': rebuilt_report(
                complete,
                evaluated_holdout_episode_ids=(
                    complete.evaluated_holdout_episode_ids[0],
                    complete.evaluated_holdout_episode_ids[0],
                ),
            ),
            'evaluated_missing_overlap': rebuilt_report(
                complete,
                missing_holdout_episode_ids=(
                    complete.evaluated_holdout_episode_ids[0],
                ),
            ),
            'evaluated_incomplete_overlap': rebuilt_report(
                complete,
                incomplete_holdout_episode_ids=(
                    complete.evaluated_holdout_episode_ids[0],
                ),
            ),
            'missing_incomplete_overlap': rebuilt_report(
                one_missing,
                incomplete_holdout_episode_ids=one_missing.missing_holdout_episode_ids,
            ),
        }
        for name, report in contradictions.items():
            with self.subTest(name=name):
                self.assertFalse(verify_evaluation_report(report))

    def test_report_verifier_rejects_status_and_disposition_contradictions(self):
        complete = evaluate_offline(
            corpus=self.corpus, candidate=self.candidate, trials=self.all_matching()
        )
        mismatch_trial = matching_trial(
            self.candidate,
            self.references[0],
            observed_outcome=DemonstrationOutcomeStatus.FAILURE,
            status=OfflineTrialStatus.OUTCOME_MISMATCH,
            reasons=(OfflineTrialReason.DIFFERENT_OUTCOME_OBSERVED,),
        )
        mismatch = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[mismatch_trial, self.all_matching()[1]],
        )
        incomplete_trial = matching_trial(
            self.candidate,
            self.references[0],
            observed_outcome=None,
            status=OfflineTrialStatus.INCOMPLETE,
            reasons=(OfflineTrialReason.RESULT_UNAVAILABLE,),
            metrics=(),
        )
        incomplete = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[incomplete_trial, self.all_matching()[1]],
        )
        contradictions = {
            'failure_count_without_failure_disposition': rebuilt_report(
                complete,
                status_counts=(
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 1),
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 1),
                    EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
                ),
            ),
            'zero_failure_hides_failure_disposition': rebuilt_report(
                mismatch,
                status_counts=(
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 2),
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 0),
                    EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
                ),
            ),
            'status_total_exceeds_trials': rebuilt_report(
                complete,
                status_counts=(
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 2),
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 1),
                    EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
                ),
            ),
            'incomplete_count_omitted': rebuilt_report(
                incomplete,
                status_counts=(
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 2),
                    EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 0),
                    EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
                ),
            ),
            'duplicate_reason': rebuilt_report(
                complete,
                reasons=(
                    EvaluationReportReason.ALL_HOLDOUT_OUTCOMES_MATCH,
                    EvaluationReportReason.ALL_HOLDOUT_OUTCOMES_MATCH,
                ),
            ),
        }
        for name, report in contradictions.items():
            with self.subTest(name=name):
                self.assertFalse(verify_evaluation_report(report))

    def test_report_verifier_rejects_wrong_contract_malformed_ids_and_booleans(self):
        complete = evaluate_offline(
            corpus=self.corpus, candidate=self.candidate, trials=self.all_matching()
        )
        boolean_count = object.__new__(EvaluationCount)
        object.__setattr__(boolean_count, 'value', OfflineTrialStatus.OUTCOME_MATCH.value)
        object.__setattr__(boolean_count, 'count', True)
        invalid_reports = {
            'wrong_evaluation_contract': rebuilt_report(
                complete, evaluation_contract_version='2.0.0'
            ),
            'boolean_coverage': rebuilt_report(complete, coverage_numerator=True),
            'malformed_trial_identity': rebuilt_report(
                complete,
                trial_ids=('not-a-content-addressed-trial', complete.trial_ids[1]),
            ),
            'boolean_status_count': rebuilt_report(
                complete,
                status_counts=(
                    boolean_count,
                    *complete.status_counts[1:],
                ),
            ),
        }
        for name, report in invalid_reports.items():
            with self.subTest(name=name):
                self.assertFalse(verify_evaluation_report(report))

    def test_valid_complete_incomplete_and_zero_failure_reports_remain_verified(self):
        complete = evaluate_offline(
            corpus=self.corpus, candidate=self.candidate, trials=self.all_matching()
        )
        incomplete = evaluate_offline(
            corpus=self.corpus,
            candidate=self.candidate,
            trials=[self.all_matching()[0]],
        )
        counts = {item.value: item.count for item in complete.status_counts}

        self.assertEqual(0, counts[OfflineTrialStatus.OUTCOME_MISMATCH.value])
        self.assertTrue(verify_evaluation_report(complete))
        self.assertTrue(verify_evaluation_report(incomplete))

    def test_offline_disposition_grants_no_authority(self):
        report = evaluate_offline(corpus=self.corpus, candidate=self.candidate, trials=self.all_matching())
        serialized = str(report.as_dict()).lower()
        for word in ('approved', 'promoted', 'safe_for_production', 'ready_to_execute'):
            self.assertNotIn(word, serialized)


if __name__ == '__main__':
    unittest.main()
