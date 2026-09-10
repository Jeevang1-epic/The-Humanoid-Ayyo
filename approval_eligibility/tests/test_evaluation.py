import pytest

from ayyo_approval_eligibility import (
    ActivationEligibilityDecision,
    ActivationEligibilityDecisionError,
    ActivationEligibilityReason,
    ActivationEligibilityRequest,
    ActivationEligibilityRequestError,
    ActivationEligibilityStatus,
    ApprovalDisposition,
    AuthorityVerificationStatus,
    evaluate_activation_eligibility,
    verify_activation_eligibility_decision,
)

from helpers import (
    evidence_for,
    fingerprint,
    fixture_approval_bundle,
    rebuild_approval_request,
)


def _request_with_rebuilt_approval(bundle, approval_request):
    evidence = evidence_for(approval_request, bundle['authority'])
    return ActivationEligibilityRequest(
        registered_version=bundle['registered_version'],
        approval_request=approval_request,
        approval_evidence=evidence,
        provenance_ref='eligibility.fixture.rebuilt',
        provenance_fingerprint=fingerprint('eligibility', 'rebuilt'),
    )


def test_externally_verified_approval_is_only_eligible_for_future_activation():
    bundle = fixture_approval_bundle('eligible')
    decision = bundle['decision']

    assert decision.status is (
        ActivationEligibilityStatus.ELIGIBLE_FOR_FUTURE_ACTIVATION
    )
    assert decision.reasons == (
        ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED,
    )
    assert verify_activation_eligibility_decision(decision)
    for forbidden_claim in ('activated', 'installed', 'executing', 'authenticated'):
        assert forbidden_claim not in decision.status.value


@pytest.mark.parametrize(
    ('authority_status', 'disposition', 'expected_reason'),
    [
        (
            AuthorityVerificationStatus.UNVERIFIED,
            ApprovalDisposition.APPROVED,
            ActivationEligibilityReason.AUTHORITY_NOT_EXTERNALLY_VERIFIED,
        ),
        (
            AuthorityVerificationStatus.REVOKED,
            ApprovalDisposition.APPROVED,
            ActivationEligibilityReason.AUTHORITY_REVOKED,
        ),
        (
            AuthorityVerificationStatus.EXTERNALLY_VERIFIED,
            ApprovalDisposition.REJECTED,
            ActivationEligibilityReason.APPROVAL_REJECTED,
        ),
        (
            AuthorityVerificationStatus.EXTERNALLY_VERIFIED,
            ApprovalDisposition.REVOKED,
            ActivationEligibilityReason.APPROVAL_REVOKED,
        ),
    ],
)
def test_unverified_revoked_or_nonapproved_evidence_is_ineligible(
    authority_status, disposition, expected_reason
):
    decision = fixture_approval_bundle(
        f'denied-{authority_status.value}-{disposition.value}',
        authority_status=authority_status,
        disposition=disposition,
    )['decision']

    assert decision.status is ActivationEligibilityStatus.INELIGIBLE
    assert expected_reason in decision.reasons
    assert verify_activation_eligibility_decision(decision)


def test_contradictory_concrete_evidence_is_not_overridden_by_any_summary():
    decision = fixture_approval_bundle(
        'contradictory',
        authority_status=AuthorityVerificationStatus.REVOKED,
        disposition=ApprovalDisposition.REJECTED,
    )['decision']

    assert decision.status is ActivationEligibilityStatus.INELIGIBLE
    assert decision.reasons == (
        ActivationEligibilityReason.APPROVAL_REJECTED,
        ActivationEligibilityReason.AUTHORITY_REVOKED,
    )


@pytest.mark.parametrize(
    ('authority_status', 'disposition'),
    [
        (AuthorityVerificationStatus.UNVERIFIED, ApprovalDisposition.APPROVED),
        (
            AuthorityVerificationStatus.EXTERNALLY_VERIFIED,
            ApprovalDisposition.REJECTED,
        ),
        (AuthorityVerificationStatus.REVOKED, ApprovalDisposition.REVOKED),
    ],
)
def test_forged_eligible_decision_over_denied_evidence_fails_verification(
    authority_status, disposition
):
    request = fixture_approval_bundle(
        f'forged-{authority_status.value}-{disposition.value}',
        authority_status=authority_status,
        disposition=disposition,
    )['eligibility_request']
    forged = ActivationEligibilityDecision._create(
        request=request,
        status=ActivationEligibilityStatus.ELIGIBLE_FOR_FUTURE_ACTIVATION,
        reasons=(ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED,),
    )

    assert not verify_activation_eligibility_decision(forged)


@pytest.mark.parametrize(
    ('field_name', 'alternate_field'),
    [
        ('candidate_id', 'candidate_id'),
        ('candidate_fingerprint', 'candidate_fingerprint'),
        ('candidate_semantic_version', 'semantic_version'),
        ('registry_record_id', 'record_id'),
        ('registry_record_fingerprint', 'record_fingerprint'),
        ('registration_request_id', 'registration_request_id'),
        ('registration_request_fingerprint', 'registration_request_fingerprint'),
        ('promotion_decision_id', 'promotion_decision_id'),
        ('promotion_decision_fingerprint', 'promotion_decision_fingerprint'),
    ],
)
def test_each_registered_evidence_chain_component_rejects_substitution(
    field_name, alternate_field
):
    bundle = fixture_approval_bundle(f'chain-{field_name}')
    alternate_record = fixture_approval_bundle(
        f'alternate-{field_name}'
    )['registered_version']
    replacement = (
        '9.9.9'
        if field_name == 'candidate_semantic_version'
        else getattr(alternate_record, alternate_field)
    )
    changed = rebuild_approval_request(
        bundle['approval_request'],
        **{field_name: replacement},
    )

    with pytest.raises(ActivationEligibilityRequestError, match='evidence chain'):
        _request_with_rebuilt_approval(bundle, changed)


def test_valid_alternate_promotion_stage_rejects_cross_chain_composition():
    bundle = fixture_approval_bundle('alternate-stage')
    changed = rebuild_approval_request(
        bundle['approval_request'],
        promotion_target_stage='future_deployment_review',
    )

    with pytest.raises(ActivationEligibilityRequestError, match='evidence chain'):
        _request_with_rebuilt_approval(bundle, changed)


def test_registry_record_substitution_is_rejected_even_when_both_records_verify():
    original = fixture_approval_bundle('record-original')
    alternate = fixture_approval_bundle('record-alternate')

    with pytest.raises(ActivationEligibilityRequestError, match='evidence chain'):
        ActivationEligibilityRequest(
            registered_version=alternate['registered_version'],
            approval_request=original['approval_request'],
            approval_evidence=original['approval_evidence'],
            provenance_ref='eligibility.fixture.record-substitution',
            provenance_fingerprint=fingerprint('eligibility', 'record-substitution'),
        )


def test_approval_request_substitution_is_rejected_when_both_requests_verify():
    bundle = fixture_approval_bundle('request-original')
    alternate_record = fixture_approval_bundle(
        'request-alternate'
    )['registered_version']
    alternate_request = rebuild_approval_request(
        bundle['approval_request'],
        candidate_id=alternate_record.candidate_id,
        candidate_fingerprint=alternate_record.candidate_fingerprint,
        candidate_semantic_version=alternate_record.semantic_version,
        registry_record_id=alternate_record.record_id,
        registry_record_fingerprint=alternate_record.record_fingerprint,
        registration_request_id=alternate_record.registration_request_id,
        registration_request_fingerprint=(
            alternate_record.registration_request_fingerprint
        ),
        promotion_decision_id=alternate_record.promotion_decision_id,
        promotion_decision_fingerprint=alternate_record.promotion_decision_fingerprint,
    )
    alternate_evidence = evidence_for(alternate_request, bundle['authority'])

    with pytest.raises(ActivationEligibilityRequestError, match='approval request'):
        ActivationEligibilityRequest(
            registered_version=bundle['registered_version'],
            approval_request=bundle['approval_request'],
            approval_evidence=alternate_evidence,
            provenance_ref='eligibility.fixture.request-substitution',
            provenance_fingerprint=fingerprint('eligibility', 'request-substitution'),
        )


def test_wholly_unrelated_but_individually_valid_chain_is_rejected():
    original = fixture_approval_bundle('unrelated-original')
    alternate = fixture_approval_bundle('unrelated-alternate')

    with pytest.raises(ActivationEligibilityRequestError):
        ActivationEligibilityRequest(
            registered_version=original['registered_version'],
            approval_request=alternate['approval_request'],
            approval_evidence=alternate['approval_evidence'],
            provenance_ref='eligibility.fixture.unrelated',
            provenance_fingerprint=fingerprint('eligibility', 'unrelated'),
        )


def test_evaluator_rejects_a_tampered_request_instead_of_failing_open():
    request = fixture_approval_bundle('tampered-evaluation')['eligibility_request']
    object.__setattr__(request, 'eligibility_request_id', 'tampered-request')

    with pytest.raises(ActivationEligibilityDecisionError, match='integrity'):
        evaluate_activation_eligibility(request)


@pytest.mark.parametrize(
    ('status', 'reasons'),
    [
        ('eligible_for_future_activation', (
            ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED,
        )),
        (ActivationEligibilityStatus.INELIGIBLE, ('approval_rejected',)),
        (ActivationEligibilityStatus.INELIGIBLE, ()),
        (
            ActivationEligibilityStatus.INELIGIBLE,
            (
                ActivationEligibilityReason.APPROVAL_REJECTED,
                ActivationEligibilityReason.APPROVAL_REJECTED,
            ),
        ),
    ],
)
def test_decision_requires_closed_status_and_canonical_unique_reasons(status, reasons):
    request = fixture_approval_bundle('decision-contract')['eligibility_request']

    with pytest.raises(ActivationEligibilityDecisionError):
        ActivationEligibilityDecision._create(
            request=request,
            status=status,
            reasons=reasons,
        )
