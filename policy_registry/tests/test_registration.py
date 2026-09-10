import pytest

from ayyo_learning_evaluation import OfflineEvaluationDisposition
from ayyo_promotion_control import (
    CandidatePromotionRequest,
    PromotionCriteria,
    PromotionTargetStage,
    evaluate_promotion,
)
from ayyo_policy_registry import (
    CandidateRegistrationError,
    CandidateRegistrationRequest,
    RegistrationStatus,
    register_candidate,
)

from helpers import (
    fingerprint,
    fixture_registration_bundle,
    rebuild_registration_request,
    register_bundle,
)


def test_registration_rejects_target_stage_substitution():
    bundle = fixture_registration_bundle(
        registration_target_stage=PromotionTargetStage.FUTURE_DEPLOYMENT_REVIEW
    )

    with pytest.raises(CandidateRegistrationError, match='target stage'):
        register_candidate(
            previous_snapshot=bundle['snapshot'],
            request=bundle['registration_request'],
            candidate=bundle['candidate'],
            evaluation_report=bundle['report'],
            promotion_criteria=bundle['criteria'],
            promotion_request=bundle['promotion_request'],
            promotion_decision=bundle['decision'],
        )


def test_exact_duplicate_registration_is_explicitly_idempotent():
    bundle = fixture_registration_bundle('idempotent')
    first = register_bundle(bundle)
    second = register_bundle(bundle, first.updated_snapshot)

    assert second.status is RegistrationStatus.ALREADY_REGISTERED
    assert second.previous_snapshot == first.updated_snapshot
    assert second.updated_snapshot == first.updated_snapshot
    assert second.registered_version == first.registered_version


def test_same_family_semantic_version_with_different_candidate_is_rejected():
    first = fixture_registration_bundle('version-one', semantic_version='1.2.0')
    second = fixture_registration_bundle('version-two', semantic_version='1.2.0')
    snapshot = register_bundle(first).updated_snapshot

    with pytest.raises(CandidateRegistrationError, match='conflicting semantic version'):
        register_bundle(second, snapshot)


def test_same_candidate_with_different_registration_provenance_is_not_a_duplicate():
    bundle = fixture_registration_bundle('provenance-conflict')
    first = register_bundle(bundle)
    alternate = CandidateRegistrationRequest(
        candidate=bundle['candidate'],
        evaluation_report=bundle['report'],
        promotion_criteria=bundle['criteria'],
        promotion_request=bundle['promotion_request'],
        promotion_decision=bundle['decision'],
        target_stage=bundle['decision'].target_stage,
        provenance_ref='different-registry-review.fixture.v1',
        provenance_fingerprint=fingerprint('different-review', 'one'),
    )
    bundle['registration_request'] = alternate

    with pytest.raises(CandidateRegistrationError, match='conflicting semantic version'):
        register_bundle(bundle, first.updated_snapshot)


@pytest.mark.parametrize(
    'artifact_name',
    ['candidate', 'report', 'criteria', 'promotion_request', 'decision'],
)
def test_substituted_upstream_artifact_is_rejected(artifact_name):
    expected = fixture_registration_bundle('expected')
    substituted = fixture_registration_bundle('substituted')
    expected[artifact_name] = substituted[artifact_name]

    with pytest.raises(CandidateRegistrationError):
        register_bundle(expected)


@pytest.mark.parametrize(
    ('artifact_name', 'field_name', 'replacement'),
    [
        ('candidate', 'candidate_fingerprint', 'candidate-sha256-' + '0' * 64),
        ('report', 'coverage_numerator', 0),
        ('criteria', 'criteria_fingerprint', 'criteria-sha256-' + '0' * 64),
        ('promotion_request', 'request_fingerprint', 'request-sha256-' + '0' * 64),
        ('decision', 'decision_fingerprint', 'decision-sha256-' + '0' * 64),
    ],
)
def test_in_memory_artifact_tampering_fails_closed(
    artifact_name, field_name, replacement
):
    bundle = fixture_registration_bundle(f'tamper-{artifact_name}')
    object.__setattr__(bundle[artifact_name], field_name, replacement)

    with pytest.raises(CandidateRegistrationError):
        register_bundle(bundle)


def test_recomputed_but_ineligible_promotion_decision_is_rejected():
    bundle = fixture_registration_bundle('ineligible-source')
    candidate = bundle['candidate']
    report = bundle['report']
    criteria = PromotionCriteria(
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        required_report_schema_id=report.schema_id,
        required_report_schema_version=report.schema_version,
        holdout_evidence_set_id=report.holdout_evidence_set_id,
        holdout_evidence_set_fingerprint=report.holdout_evidence_set_fingerprint,
        accepted_dispositions=(
            OfflineEvaluationDisposition.DOES_NOT_MEET_OFFLINE_CRITERIA,
        ),
        minimum_evaluated_trials=2,
        maximum_failed_trials=0,
        require_complete_evaluation=True,
        allowed_target_stages=(PromotionTargetStage.REVIEWED_CANDIDATE,),
    )
    promotion_request = CandidatePromotionRequest(
        candidate=candidate,
        report=report,
        criteria=criteria,
        target_stage=PromotionTargetStage.REVIEWED_CANDIDATE,
        provenance_ref='ineligible-review.fixture.v1',
        provenance_fingerprint=fingerprint('ineligible-review', 'one'),
    )
    decision = evaluate_promotion(
        criteria=criteria,
        request=promotion_request,
        candidate=candidate,
        report=report,
    )
    request = CandidateRegistrationRequest(
        candidate=candidate,
        evaluation_report=report,
        promotion_criteria=criteria,
        promotion_request=promotion_request,
        promotion_decision=decision,
        target_stage=PromotionTargetStage.REVIEWED_CANDIDATE,
        provenance_ref='registry-review.fixture.v1',
        provenance_fingerprint=fingerprint('registry-review', 'ineligible'),
    )

    with pytest.raises(CandidateRegistrationError, match='eligible promotion decision'):
        register_candidate(
            previous_snapshot=bundle['snapshot'],
            request=request,
            candidate=candidate,
            evaluation_report=report,
            promotion_criteria=criteria,
            promotion_request=promotion_request,
            promotion_decision=decision,
        )


def test_content_addressed_request_cannot_rebind_one_identity():
    bundle = fixture_registration_bundle('request-rebind')
    alternate = fixture_registration_bundle('request-alternate')
    request = rebuild_registration_request(
        bundle['registration_request'],
        evaluation_report_id=alternate['report'].report_id,
        evaluation_report_fingerprint=alternate['report'].report_fingerprint,
    )
    bundle['registration_request'] = request

    with pytest.raises(CandidateRegistrationError, match='different evaluation report'):
        register_bundle(bundle)


def test_modified_embedded_trial_evidence_cannot_reach_registration():
    bundle = fixture_registration_bundle('report-evidence-tamper')
    object.__setattr__(bundle['report'].trial_evidence[0], 'trial_id', 'tampered-trial')

    with pytest.raises(CandidateRegistrationError, match='evaluation report'):
        register_bundle(bundle)
