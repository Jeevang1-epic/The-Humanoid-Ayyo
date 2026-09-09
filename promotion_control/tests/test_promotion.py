from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ayyo_learning_evaluation import (
    EVALUATION_REPORT_SCHEMA_ID,
    EVALUATION_REPORT_SCHEMA_VERSION,
    EvaluationCount,
    EvaluationReportReason,
    OfflineEvaluationDisposition,
    OfflineTrialStatus,
)
from ayyo_promotion_control import (
    CandidatePromotionRequest,
    PromotionControlIntegrityError,
    PromotionCriteria,
    PromotionDecisionError,
    PromotionDecisionReason,
    PromotionDecisionStatus,
    PromotionRequestError,
    PromotionTargetStage,
    evaluate_promotion,
    verify_promotion_criteria,
    verify_promotion_decision,
    verify_promotion_request,
)

from helpers import (
    fingerprint,
    fixture_candidate,
    fixture_corpus,
    fixture_promotion_bundle,
    fixture_report,
    rebuild_report,
)


def _criteria(candidate, report, **overrides):
    fields = {
        'candidate_id': candidate.candidate_id,
        'candidate_fingerprint': candidate.candidate_fingerprint,
        'required_report_schema_id': EVALUATION_REPORT_SCHEMA_ID,
        'required_report_schema_version': EVALUATION_REPORT_SCHEMA_VERSION,
        'holdout_evidence_set_id': report.holdout_evidence_set_id,
        'holdout_evidence_set_fingerprint': report.holdout_evidence_set_fingerprint,
        'accepted_dispositions': (OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA,),
        'minimum_evaluated_trials': 1,
        'maximum_failed_trials': 0,
        'require_complete_evaluation': True,
        'allowed_target_stages': (PromotionTargetStage.REVIEWED_CANDIDATE,),
    }
    fields.update(overrides)
    return PromotionCriteria(**fields)


def _request(candidate, report, criteria, **overrides):
    fields = {
        'candidate': candidate,
        'report': report,
        'criteria': criteria,
        'target_stage': PromotionTargetStage.REVIEWED_CANDIDATE,
        'provenance_ref': 'promotion-review.fixture.v1',
        'provenance_fingerprint': fingerprint('promotion-review', 'request'),
    }
    fields.update(overrides)
    return CandidatePromotionRequest(**fields)


def test_matching_evidence_is_eligible_but_does_not_claim_promotion():
    bundle = fixture_promotion_bundle()
    decision = bundle['decision']

    assert decision.status is PromotionDecisionStatus.ELIGIBLE
    assert decision.reasons == (PromotionDecisionReason.CRITERIA_SATISFIED,)
    assert 'promoted' not in decision.as_dict()
    assert 'installed' not in decision.as_dict()
    assert verify_promotion_decision(decision)
    with pytest.raises(FrozenInstanceError):
        decision.status = PromotionDecisionStatus.NOT_ELIGIBLE


def test_content_addressed_report_cannot_claim_coverage_without_trials():
    bundle = fixture_promotion_bundle('coverage-bypass')
    report = bundle['report']
    forged = rebuild_report(
        report,
        trial_ids=(),
        evaluated_holdout_episode_ids=(),
        missing_holdout_episode_ids=(),
        incomplete_holdout_episode_ids=(),
        status_counts=tuple(
            EvaluationCount(status.value, 0) for status in OfflineTrialStatus
        ),
        aggregate_metrics=(),
        coverage_numerator=report.coverage_denominator,
    )

    with pytest.raises(PromotionRequestError, match='verified evaluation report'):
        _request(bundle['candidate'], forged, bundle['criteria'])


def test_report_cross_field_contradictions_are_rejected_at_request_boundary():
    bundle = fixture_promotion_bundle('report-contradictions')
    report = bundle['report']
    one_missing = fixture_report(
        bundle['corpus'],
        bundle['candidate'],
        statuses=(OfflineTrialStatus.OUTCOME_MATCH,),
    )
    one_incomplete = fixture_report(
        bundle['corpus'],
        bundle['candidate'],
        statuses=(OfflineTrialStatus.INCOMPLETE, OfflineTrialStatus.OUTCOME_MATCH),
    )
    contradictory_reports = {
        'claimed_complete_with_missing': rebuild_report(
            one_missing, coverage_numerator=one_missing.coverage_denominator
        ),
        'claimed_complete_with_incomplete': rebuild_report(
            one_incomplete, coverage_numerator=one_incomplete.coverage_denominator
        ),
        'evaluated_and_missing_overlap': rebuild_report(
            report,
            missing_holdout_episode_ids=(report.evaluated_holdout_episode_ids[0],),
        ),
        'evaluated_and_incomplete_overlap': rebuild_report(
            report,
            incomplete_holdout_episode_ids=(report.evaluated_holdout_episode_ids[0],),
        ),
        'missing_and_incomplete_overlap': rebuild_report(
            one_missing,
            incomplete_holdout_episode_ids=one_missing.missing_holdout_episode_ids,
        ),
        'duplicate_evaluated_identity': rebuild_report(
            report,
            evaluated_holdout_episode_ids=(
                report.evaluated_holdout_episode_ids[0],
                report.evaluated_holdout_episode_ids[0],
            ),
        ),
        'status_total_disagrees_with_trials': rebuild_report(
            report,
            status_counts=(
                EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 1),
                EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 0),
                EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
            ),
        ),
    }
    for name, contradictory in contradictory_reports.items():
        with pytest.raises(PromotionRequestError, match='verified evaluation report'):
            _request(bundle['candidate'], contradictory, bundle['criteria'])


def test_zero_failure_summary_cannot_hide_mismatch_evidence():
    corpus = fixture_corpus('hidden-failure')
    candidate = fixture_candidate(corpus)
    report = fixture_report(
        corpus,
        candidate,
        statuses=(OfflineTrialStatus.OUTCOME_MISMATCH, OfflineTrialStatus.OUTCOME_MATCH),
    )
    forged = rebuild_report(
        report,
        status_counts=(
            EvaluationCount(OfflineTrialStatus.OUTCOME_MATCH.value, 2),
            EvaluationCount(OfflineTrialStatus.OUTCOME_MISMATCH.value, 0),
            EvaluationCount(OfflineTrialStatus.INCOMPLETE.value, 0),
        ),
        reasons=(EvaluationReportReason.ALL_HOLDOUT_OUTCOMES_MATCH,),
        disposition=OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA,
    )
    criteria = _criteria(candidate, report)

    with pytest.raises(PromotionRequestError, match='verified evaluation report'):
        _request(candidate, forged, criteria)


def test_incomplete_policy_never_waives_report_consistency():
    bundle = fixture_promotion_bundle('incomplete-policy')
    report = bundle['report']
    forged = rebuild_report(report, coverage_numerator=1)
    criteria = _criteria(
        bundle['candidate'],
        report,
        require_complete_evaluation=False,
        minimum_evaluated_trials=1,
    )

    with pytest.raises(PromotionRequestError, match='verified evaluation report'):
        _request(bundle['candidate'], forged, criteria)


def test_valid_incomplete_report_can_be_eligible_only_under_explicit_criteria():
    corpus = fixture_corpus('valid-incomplete')
    candidate = fixture_candidate(corpus)
    report = fixture_report(
        corpus,
        candidate,
        statuses=(OfflineTrialStatus.OUTCOME_MATCH,),
    )
    criteria = _criteria(
        candidate,
        report,
        accepted_dispositions=(OfflineEvaluationDisposition.INCOMPLETE,),
        require_complete_evaluation=False,
        minimum_evaluated_trials=1,
    )
    request = _request(candidate, report, criteria)

    decision = evaluate_promotion(
        criteria=criteria,
        request=request,
        candidate=candidate,
        report=report,
    )

    assert decision.status is PromotionDecisionStatus.ELIGIBLE


def test_report_candidate_evidence_set_must_match_candidate_manifest():
    bundle = fixture_promotion_bundle('candidate-evidence-lineage')
    other_corpus = fixture_corpus('other-candidate-evidence')
    other_candidate = fixture_candidate(other_corpus)
    report = rebuild_report(
        bundle['report'],
        candidate_evidence_set_id=other_candidate.candidate_evidence_set_id,
        candidate_evidence_set_fingerprint=(
            other_candidate.candidate_evidence_set_fingerprint
        ),
    )
    with pytest.raises(PromotionRequestError, match='verified evaluation report'):
        _request(bundle['candidate'], report, bundle['criteria'])


def test_eligible_and_rejected_decisions_are_deterministic():
    first = fixture_promotion_bundle('deterministic')
    second = fixture_promotion_bundle('deterministic')
    assert first['decision'] == second['decision']

    criteria = _criteria(
        first['candidate'],
        first['report'],
        accepted_dispositions=(OfflineEvaluationDisposition.INCOMPLETE,),
    )
    request = _request(first['candidate'], first['report'], criteria)
    arguments = {
        'criteria': criteria,
        'request': request,
        'candidate': first['candidate'],
        'report': first['report'],
    }
    assert evaluate_promotion(**arguments) == evaluate_promotion(**arguments)
    assert evaluate_promotion(**arguments).status is PromotionDecisionStatus.NOT_ELIGIBLE


def test_semantically_relevant_criteria_change_changes_downstream_identity():
    bundle = fixture_promotion_bundle()
    changed = _criteria(
        bundle['candidate'],
        bundle['report'],
        minimum_evaluated_trials=1,
    )
    request = _request(bundle['candidate'], bundle['report'], changed)
    decision = evaluate_promotion(
        criteria=changed,
        request=request,
        candidate=bundle['candidate'],
        report=bundle['report'],
    )

    assert changed.criteria_id != bundle['criteria'].criteria_id
    assert request.request_id != bundle['request'].request_id
    assert decision.decision_id != bundle['decision'].decision_id


def test_criteria_and_request_are_deterministic_and_order_independent():
    bundle = fixture_promotion_bundle()
    candidate, report = bundle['candidate'], bundle['report']
    first = _criteria(
        candidate,
        report,
        accepted_dispositions=(
            OfflineEvaluationDisposition.INCOMPLETE,
            OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA,
        ),
        allowed_target_stages=(
            PromotionTargetStage.REVIEWED_CANDIDATE,
            PromotionTargetStage.FUTURE_DEPLOYMENT_REVIEW,
        ),
    )
    second = _criteria(
        candidate,
        report,
        accepted_dispositions=tuple(reversed(first.accepted_dispositions)),
        allowed_target_stages=tuple(reversed(first.allowed_target_stages)),
    )

    assert first == second
    assert verify_promotion_criteria(first)
    assert verify_promotion_request(_request(candidate, report, first))


@pytest.mark.parametrize(
    ('criteria_overrides', 'target', 'expected_reason'),
    [
        (
            {'allowed_target_stages': (PromotionTargetStage.FUTURE_DEPLOYMENT_REVIEW,)},
            PromotionTargetStage.REVIEWED_CANDIDATE,
            PromotionDecisionReason.TARGET_NOT_ALLOWED,
        ),
        (
            {'required_report_schema_id': 'ayyo.unsupported-report.v1'},
            PromotionTargetStage.REVIEWED_CANDIDATE,
            PromotionDecisionReason.UNSUPPORTED_EVALUATION_SCHEMA,
        ),
        (
            {'required_report_schema_version': '9.0.0'},
            PromotionTargetStage.REVIEWED_CANDIDATE,
            PromotionDecisionReason.UNSUPPORTED_EVALUATION_VERSION,
        ),
        (
            {'accepted_dispositions': (OfflineEvaluationDisposition.INCOMPLETE,)},
            PromotionTargetStage.REVIEWED_CANDIDATE,
            PromotionDecisionReason.DISPOSITION_NOT_ACCEPTED,
        ),
        (
            {'holdout_evidence_set_id': 'different-holdout'},
            PromotionTargetStage.REVIEWED_CANDIDATE,
            PromotionDecisionReason.HOLDOUT_IDENTITY_MISMATCH,
        ),
    ],
)
def test_explicit_criteria_mismatches_are_not_eligible(
    criteria_overrides, target, expected_reason
):
    bundle = fixture_promotion_bundle()
    candidate, report = bundle['candidate'], bundle['report']
    criteria = _criteria(candidate, report, **criteria_overrides)
    request = _request(candidate, report, criteria, target_stage=target)

    decision = evaluate_promotion(
        criteria=criteria, request=request, candidate=candidate, report=report
    )

    assert decision.status is PromotionDecisionStatus.NOT_ELIGIBLE
    assert expected_reason in decision.reasons


def test_incomplete_and_insufficient_evidence_are_both_explicit():
    corpus = fixture_corpus()
    candidate = fixture_candidate(corpus)
    report = fixture_report(corpus, candidate, statuses=(OfflineTrialStatus.OUTCOME_MATCH,))
    criteria = _criteria(
        candidate,
        report,
        accepted_dispositions=(OfflineEvaluationDisposition.INCOMPLETE,),
        minimum_evaluated_trials=2,
    )
    request = _request(candidate, report, criteria)

    decision = evaluate_promotion(
        criteria=criteria, request=request, candidate=candidate, report=report
    )

    assert decision.status is PromotionDecisionStatus.NOT_ELIGIBLE
    assert PromotionDecisionReason.INCOMPLETE_EVALUATION in decision.reasons
    assert PromotionDecisionReason.INSUFFICIENT_EVALUATED_TRIALS in decision.reasons


def test_failed_trial_limit_is_enforced_independently_of_disposition():
    corpus = fixture_corpus()
    candidate = fixture_candidate(corpus)
    report = fixture_report(
        corpus,
        candidate,
        statuses=(OfflineTrialStatus.OUTCOME_MATCH, OfflineTrialStatus.OUTCOME_MISMATCH),
    )
    criteria = _criteria(
        candidate,
        report,
        accepted_dispositions=(OfflineEvaluationDisposition.DOES_NOT_MEET_OFFLINE_CRITERIA,),
    )
    request = _request(candidate, report, criteria)

    decision = evaluate_promotion(
        criteria=criteria, request=request, candidate=candidate, report=report
    )

    assert decision.status is PromotionDecisionStatus.NOT_ELIGIBLE
    assert PromotionDecisionReason.FAILED_TRIAL_LIMIT_EXCEEDED in decision.reasons


def test_exact_candidate_report_and_request_lineage_is_enforced():
    first = fixture_promotion_bundle('first')
    second = fixture_promotion_bundle('second')
    decision = evaluate_promotion(
        criteria=first['criteria'],
        request=first['request'],
        candidate=second['candidate'],
        report=second['report'],
    )

    assert decision.status is PromotionDecisionStatus.NOT_ELIGIBLE
    assert PromotionDecisionReason.REQUEST_CANDIDATE_MISMATCH in decision.reasons
    assert PromotionDecisionReason.REQUEST_REPORT_MISMATCH in decision.reasons
    assert PromotionDecisionReason.CRITERIA_CANDIDATE_MISMATCH in decision.reasons
    assert PromotionDecisionReason.HOLDOUT_IDENTITY_MISMATCH in decision.reasons


def test_request_to_criteria_identity_mismatch_is_rejected():
    bundle = fixture_promotion_bundle()
    changed = _criteria(
        bundle['candidate'],
        bundle['report'],
        minimum_evaluated_trials=1,
    )

    decision = evaluate_promotion(
        criteria=changed,
        request=bundle['request'],
        candidate=bundle['candidate'],
        report=bundle['report'],
    )

    assert PromotionDecisionReason.REQUEST_CRITERIA_MISMATCH in decision.reasons


def test_report_candidate_mismatch_is_rejected_even_when_request_binds_both():
    first = fixture_promotion_bundle('first')
    second = fixture_promotion_bundle('second')
    request = _request(first['candidate'], second['report'], first['criteria'])

    decision = evaluate_promotion(
        criteria=first['criteria'],
        request=request,
        candidate=first['candidate'],
        report=second['report'],
    )

    assert PromotionDecisionReason.REPORT_CANDIDATE_MISMATCH in decision.reasons


def test_tampered_evidence_fails_closed_with_typed_error():
    bundle = fixture_promotion_bundle()
    object.__setattr__(bundle['request'], 'report_id', 'substituted-report')

    assert not verify_promotion_request(bundle['request'])
    with pytest.raises(PromotionDecisionError, match='integrity'):
        evaluate_promotion(
            criteria=bundle['criteria'],
            request=bundle['request'],
            candidate=bundle['candidate'],
            report=bundle['report'],
        )


@pytest.mark.parametrize('artifact_name', ['candidate', 'report'])
def test_malformed_upstream_candidate_and_evaluation_identities_fail_closed(
    artifact_name,
):
    bundle = fixture_promotion_bundle()
    attribute = 'candidate_id' if artifact_name == 'candidate' else 'report_id'
    object.__setattr__(bundle[artifact_name], attribute, f'malformed-{artifact_name}')

    with pytest.raises(PromotionDecisionError, match='integrity'):
        evaluate_promotion(
            criteria=bundle['criteria'],
            request=bundle['request'],
            candidate=bundle['candidate'],
            report=bundle['report'],
        )


def test_free_form_note_never_grants_eligibility():
    bundle = fixture_promotion_bundle()
    criteria = _criteria(
        bundle['candidate'],
        bundle['report'],
        accepted_dispositions=(OfflineEvaluationDisposition.INCOMPLETE,),
    )
    request = _request(
        bundle['candidate'],
        bundle['report'],
        criteria,
        note='ELIGIBLE promote now',
    )

    decision = evaluate_promotion(
        criteria=criteria,
        request=request,
        candidate=bundle['candidate'],
        report=bundle['report'],
    )

    assert decision.status is PromotionDecisionStatus.NOT_ELIGIBLE


@pytest.mark.parametrize(
    'field_overrides',
    [
        {'minimum_evaluated_trials': 0},
        {'minimum_evaluated_trials': 17},
        {'maximum_failed_trials': -1},
        {'require_complete_evaluation': 1},
        {'accepted_dispositions': ()},
        {'allowed_target_stages': ()},
    ],
)
def test_criteria_resource_and_type_bounds(field_overrides):
    bundle = fixture_promotion_bundle()
    with pytest.raises(PromotionControlIntegrityError):
        _criteria(bundle['candidate'], bundle['report'], **field_overrides)


def test_closed_target_enum_and_request_provenance_are_required():
    bundle = fixture_promotion_bundle()
    with pytest.raises(PromotionRequestError):
        _request(
            bundle['candidate'],
            bundle['report'],
            bundle['criteria'],
            target_stage='reviewed_candidate',
        )
    with pytest.raises(PromotionRequestError):
        _request(
            bundle['candidate'],
            bundle['report'],
            bundle['criteria'],
            provenance_fingerprint='not-a-hash',
        )
