from dataclasses import FrozenInstanceError

import pytest

from ayyo_approval_eligibility import (
    MAX_IDENTIFIER_LENGTH,
    MAX_NOTE_LENGTH,
    ActivationEligibilityRequest,
    ActivationEligibilityRequestError,
    ApprovalDisposition,
    ApprovalEvidenceError,
    ApprovalRequest,
    ApprovalRequestError,
    ApprovalScope,
    AuthorityApprovalEvidence,
    AuthorityReference,
    AuthorityReferenceError,
    AuthorityVerificationStatus,
    verify_activation_eligibility_request,
    verify_approval_request,
    verify_authority_approval_evidence,
    verify_authority_reference,
)

from helpers import (
    evidence_for,
    fingerprint,
    fixture_approval_bundle,
    fixture_authority,
    rebuild_approval_request,
)


def test_legitimate_artifacts_preserve_the_complete_identity_chain():
    bundle = fixture_approval_bundle('complete-chain')
    record = bundle['registered_version']
    request = bundle['approval_request']
    evidence = bundle['approval_evidence']
    eligibility = bundle['eligibility_request']

    assert (
        request.candidate_id,
        request.candidate_fingerprint,
        request.candidate_semantic_version,
    ) == (record.candidate_id, record.candidate_fingerprint, record.semantic_version)
    assert (request.registry_record_id, request.registry_record_fingerprint) == (
        record.record_id,
        record.record_fingerprint,
    )
    assert (
        request.registration_request_id,
        request.registration_request_fingerprint,
    ) == (
        record.registration_request_id,
        record.registration_request_fingerprint,
    )
    assert (request.promotion_decision_id, request.promotion_decision_fingerprint) == (
        record.promotion_decision_id,
        record.promotion_decision_fingerprint,
    )
    assert evidence.approval_request == request
    assert evidence.authority == bundle['authority']
    assert eligibility.registered_version == record
    assert eligibility.approval_request == request
    assert eligibility.approval_evidence == evidence
    assert verify_authority_reference(bundle['authority'])
    assert verify_approval_request(request)
    assert verify_authority_approval_evidence(evidence)
    assert verify_activation_eligibility_request(eligibility)


def test_all_contracts_are_deterministic_for_identical_evidence():
    first = fixture_approval_bundle('deterministic')
    second = fixture_approval_bundle('deterministic')

    assert first == second
    assert first['authority'].authority_reference_fingerprint == (
        first['authority'].recompute_fingerprint()
    )
    assert first['approval_request'].approval_request_id == (
        first['approval_request'].recompute_approval_request_id()
    )
    assert first['approval_evidence'].approval_evidence_id == (
        first['approval_evidence'].recompute_approval_evidence_id()
    )
    assert first['eligibility_request'].eligibility_request_id == (
        first['eligibility_request'].recompute_eligibility_request_id()
    )


def test_all_contracts_are_frozen():
    bundle = fixture_approval_bundle('frozen')

    for artifact in (
        bundle['authority'],
        bundle['approval_request'],
        bundle['approval_evidence'],
        bundle['eligibility_request'],
        bundle['decision'],
    ):
        with pytest.raises(FrozenInstanceError):
            artifact.schema_version = 'changed'


@pytest.mark.parametrize(
    'overrides',
    [
        {
            'verification_status': AuthorityVerificationStatus.UNVERIFIED,
            'verification_provider_ref': 'provider.fixture.v1',
            'verification_provider_fingerprint': 'provider-sha256-' + '0' * 64,
        },
        {
            'verification_status': AuthorityVerificationStatus.EXTERNALLY_VERIFIED,
            'verification_provider_ref': None,
            'verification_provider_fingerprint': None,
        },
        {
            'verification_status': AuthorityVerificationStatus.REVOKED,
            'verification_evidence_ref': None,
            'verification_evidence_fingerprint': None,
        },
        {
            'verification_provider_ref': 'provider.fixture.v1',
            'verification_provider_fingerprint': None,
        },
    ],
)
def test_authority_verification_state_and_identity_pairs_fail_closed(overrides):
    arguments = {
        'authority_id': 'authority.reviewer.invalid',
        'authority_fingerprint': fingerprint('authority', 'invalid'),
        'verification_status': AuthorityVerificationStatus.EXTERNALLY_VERIFIED,
        'verification_provider_ref': 'provider.fixture.v1',
        'verification_provider_fingerprint': fingerprint('provider', 'invalid'),
        'verification_evidence_ref': 'proof.fixture.invalid',
        'verification_evidence_fingerprint': fingerprint('proof', 'invalid'),
        'provenance_ref': 'authority.fixture.invalid',
        'provenance_fingerprint': fingerprint('authority-source', 'invalid'),
    }
    arguments.update(overrides)

    with pytest.raises(AuthorityReferenceError):
        AuthorityReference(**arguments)


def test_unverified_authority_is_representable_but_never_claimed_as_verified():
    authority = fixture_authority(
        'unverified-model', AuthorityVerificationStatus.UNVERIFIED
    )

    assert verify_authority_reference(authority)
    assert authority.verification_provider_ref is None
    assert authority.verification_evidence_ref is None


def test_approval_evidence_rejects_valid_but_unrelated_authority():
    bundle = fixture_approval_bundle('authority-request')
    alternate = fixture_authority('authority-substitute')

    with pytest.raises(ApprovalEvidenceError, match='differs'):
        AuthorityApprovalEvidence(
            approval_request=bundle['approval_request'],
            authority=alternate,
            disposition=ApprovalDisposition.APPROVED,
            evidence_ref='evidence.fixture.substitution',
            evidence_fingerprint=fingerprint('evidence', 'substitution'),
        )


@pytest.mark.parametrize(
    'field_name',
    [
        'authority_id',
        'authority_fingerprint',
        'authority_reference_id',
        'authority_reference_fingerprint',
    ],
)
def test_approval_evidence_rejects_each_authority_identity_component(field_name):
    bundle = fixture_approval_bundle('authority-component')
    alternate = fixture_authority('authority-component-alternate')
    changed_request = rebuild_approval_request(
        bundle['approval_request'], **{field_name: getattr(alternate, field_name)}
    )

    with pytest.raises(ApprovalEvidenceError, match='differs'):
        evidence_for(changed_request, bundle['authority'])


def test_approval_request_rejects_unknown_registry_promotion_stage():
    request = fixture_approval_bundle('unknown-stage')['approval_request']

    with pytest.raises(ApprovalRequestError, match='unsupported'):
        rebuild_approval_request(request, promotion_target_stage='unknown_stage')


@pytest.mark.parametrize(
    ('field_name', 'value'),
    [
        ('approval_scope', 'future_activation_review'),
        ('approval_scope', object()),
    ],
)
def test_approval_request_requires_the_closed_scope_enum(field_name, value):
    request = fixture_approval_bundle('scope-enum')['approval_request']

    with pytest.raises(ApprovalRequestError):
        rebuild_approval_request(request, **{field_name: value})


def test_approval_evidence_requires_the_closed_disposition_enum():
    bundle = fixture_approval_bundle('disposition-enum')

    with pytest.raises(ApprovalEvidenceError):
        AuthorityApprovalEvidence(
            approval_request=bundle['approval_request'],
            authority=bundle['authority'],
            disposition='approved',
            evidence_ref='evidence.fixture.enum',
            evidence_fingerprint=fingerprint('evidence', 'enum'),
        )


@pytest.mark.parametrize('collection_type', [tuple, list])
def test_eligibility_request_accepts_exactly_one_approval_evidence(collection_type):
    bundle = fixture_approval_bundle('single-evidence')

    with pytest.raises(ActivationEligibilityRequestError, match='one verified'):
        ActivationEligibilityRequest(
            registered_version=bundle['registered_version'],
            approval_request=bundle['approval_request'],
            approval_evidence=collection_type(
                [bundle['approval_evidence'], bundle['approval_evidence']]
            ),
            provenance_ref='eligibility.fixture.duplicates',
            provenance_fingerprint=fingerprint('eligibility', 'duplicates'),
        )


def test_conflicting_approval_collection_cannot_be_aggregated_into_eligibility():
    bundle = fixture_approval_bundle('conflicting-evidence')
    rejection = evidence_for(
        bundle['approval_request'],
        bundle['authority'],
        ApprovalDisposition.REJECTED,
    )

    with pytest.raises(ActivationEligibilityRequestError, match='one verified'):
        ActivationEligibilityRequest(
            registered_version=bundle['registered_version'],
            approval_request=bundle['approval_request'],
            approval_evidence=(bundle['approval_evidence'], rejection),
            provenance_ref='eligibility.fixture.conflict',
            provenance_fingerprint=fingerprint('eligibility', 'conflict'),
        )


@pytest.mark.parametrize(
    ('artifact_key', 'identity_field', 'verifier'),
    [
        ('authority', 'authority_reference_id', verify_authority_reference),
        ('approval_request', 'approval_request_id', verify_approval_request),
        ('approval_evidence', 'approval_evidence_id', verify_authority_approval_evidence),
        (
            'eligibility_request',
            'eligibility_request_id',
            verify_activation_eligibility_request,
        ),
    ],
)
def test_verifiers_reject_in_memory_identity_tampering(
    artifact_key, identity_field, verifier
):
    artifact = fixture_approval_bundle(f'tamper-{artifact_key}')[artifact_key]
    object.__setattr__(artifact, identity_field, 'tampered-identity')

    assert not verifier(artifact)


@pytest.mark.parametrize('note', ['x' * (MAX_NOTE_LENGTH + 1), 'unsafe\ntext'])
def test_notes_are_bounded_and_reject_control_characters(note):
    bundle = fixture_approval_bundle('note-bound')

    with pytest.raises(ApprovalRequestError):
        ApprovalRequest(
            registered_version=bundle['registered_version'],
            authority=bundle['authority'],
            approval_scope=ApprovalScope.FUTURE_ACTIVATION_REVIEW,
            provenance_ref='approval.fixture.note',
            provenance_fingerprint=fingerprint('approval', 'note'),
            note=note,
        )


def test_identifiers_are_bounded():
    bundle = fixture_approval_bundle('identifier-bound')

    with pytest.raises(ApprovalRequestError):
        ApprovalRequest(
            registered_version=bundle['registered_version'],
            authority=bundle['authority'],
            approval_scope=ApprovalScope.FUTURE_ACTIVATION_REVIEW,
            provenance_ref='a' * (MAX_IDENTIFIER_LENGTH + 1),
            provenance_fingerprint=fingerprint('approval', 'identifier'),
        )


def test_contracts_expose_no_active_installed_or_executing_state():
    bundle = fixture_approval_bundle('no-active-state')

    for artifact in bundle.values():
        for attribute in (
            'active_policy',
            'current_policy',
            'installed_policy',
            'loaded_model',
            'runtime_handle',
        ):
            assert not hasattr(artifact, attribute)
