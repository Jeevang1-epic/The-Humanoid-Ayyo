from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ayyo_learning_evaluation import (
    EVALUATION_REPORT_SCHEMA_ID,
    EVALUATION_REPORT_SCHEMA_VERSION,
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
