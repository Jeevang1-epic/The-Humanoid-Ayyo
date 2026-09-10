import json
from hashlib import sha256

import pytest

from ayyo_approval_eligibility import (
    MAX_SERIALIZED_ELIGIBILITY_DECISION_BYTES,
    ActivationEligibilityReason,
    ActivationEligibilityStatus,
    ApprovalEligibilityIntegrityError,
    ApprovalDisposition,
    AuthorityVerificationStatus,
    approval_eligibility_artifact_from_canonical_json,
    canonical_approval_eligibility_artifact_json,
)

from helpers import fixture_approval_bundle


def canonical(document):
    return json.dumps(
        document,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )


def semantic_sha256(prefix, document):
    digest = sha256(canonical(document).encode('utf-8')).hexdigest()
    return f'{prefix}-sha256-{digest}'


def _recompute_identity(document, prefix, fingerprint_field, id_field):
    semantic = {
        key: value
        for key, value in document.items()
        if key not in {fingerprint_field, id_field}
    }
    content_fingerprint = semantic_sha256(f'{prefix}-content', semantic)
    document[fingerprint_field] = content_fingerprint
    document[id_field] = semantic_sha256(
        prefix,
        {
            'content_fingerprint': content_fingerprint,
            'schema_id': document['schema']['id'],
            'schema_version': document['schema']['version'],
        },
    )


def test_all_public_artifacts_round_trip_strictly_as_text_and_bytes():
    bundle = fixture_approval_bundle('round-trip')
    artifacts = (
        bundle['authority'],
        bundle['approval_request'],
        bundle['approval_evidence'],
        bundle['eligibility_request'],
        bundle['decision'],
    )

    for artifact in artifacts:
        encoded = canonical_approval_eligibility_artifact_json(artifact)
        assert approval_eligibility_artifact_from_canonical_json(encoded) == artifact
        assert approval_eligibility_artifact_from_canonical_json(
            encoded.encode('utf-8')
        ) == artifact
        assert canonical_approval_eligibility_artifact_json(
            approval_eligibility_artifact_from_canonical_json(encoded)
        ) == encoded


def test_canonical_encoding_is_deterministic_and_compact():
    first = fixture_approval_bundle('canonical')['decision']
    second = fixture_approval_bundle('canonical')['decision']
    encoded = canonical_approval_eligibility_artifact_json(first)

    assert first == second
    assert encoded == canonical_approval_eligibility_artifact_json(second)
    assert '\n' not in encoded
    assert ': ' not in encoded


@pytest.mark.parametrize(
    'payload',
    ['', 'not-json', '[]', 'NaN', b'\xff', None, 1, True],
)
def test_malformed_nonobject_utf8_and_wrong_transport_inputs_fail_closed(payload):
    with pytest.raises(ApprovalEligibilityIntegrityError):
        approval_eligibility_artifact_from_canonical_json(payload)


def test_duplicate_json_key_is_rejected():
    encoded = canonical_approval_eligibility_artifact_json(
        fixture_approval_bundle('duplicate-key')['approval_request']
    )
    duplicated = encoded.replace('"note":', '"note":null,"note":', 1)

    with pytest.raises(ApprovalEligibilityIntegrityError, match='duplicate key'):
        approval_eligibility_artifact_from_canonical_json(duplicated)


def test_noncanonical_whitespace_is_rejected():
    document = fixture_approval_bundle('whitespace')['authority'].as_dict()

    with pytest.raises(ApprovalEligibilityIntegrityError, match='not canonical'):
        approval_eligibility_artifact_from_canonical_json(
            json.dumps(document, indent=2, sort_keys=True)
        )


@pytest.mark.parametrize('mutation', ['unknown', 'missing', 'schema-id', 'schema-version'])
def test_unknown_missing_and_unsupported_schema_fields_are_rejected(mutation):
    document = fixture_approval_bundle('schema')['approval_request'].as_dict()
    if mutation == 'unknown':
        document['unexpected'] = 'value'
    elif mutation == 'missing':
        del document['candidate']
    elif mutation == 'schema-id':
        document['schema']['id'] = 'ayyo.approval-eligibility.unknown.v1'
    else:
        document['schema']['version'] = '2.0.0'

    with pytest.raises(ApprovalEligibilityIntegrityError):
        approval_eligibility_artifact_from_canonical_json(canonical(document))


@pytest.mark.parametrize(
    ('artifact_key', 'path', 'replacement'),
    [
        (
            'authority',
            ('authority_reference_fingerprint',),
            'authority-reference-sha256-' + '0' * 64,
        ),
        (
            'approval_request',
            ('candidate', 'fingerprint'),
            'candidate-sha256-' + '0' * 64,
        ),
        ('approval_request', ('promotion', 'target_stage'), 'unknown_stage'),
        ('approval_request', ('approval_scope',), 'unknown_scope'),
        ('authority', ('verification', 'status'), 'authenticated'),
        ('approval_evidence', ('disposition',), 'unknown_disposition'),
        ('decision', ('status',), 'activated'),
        ('decision', ('reasons',), ['unknown_reason']),
    ],
)
def test_identity_and_closed_enum_tampering_is_rejected(
    artifact_key, path, replacement
):
    document = fixture_approval_bundle(f'tamper-{artifact_key}')[artifact_key].as_dict()
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(ApprovalEligibilityIntegrityError):
        approval_eligibility_artifact_from_canonical_json(canonical(document))


def test_altered_nested_canonical_approval_evidence_is_rejected():
    document = fixture_approval_bundle('nested-tamper')['eligibility_request'].as_dict()
    document['approval_evidence']['evidence_source']['fingerprint'] = (
        'approval-evidence-source-sha256-' + '0' * 64
    )

    with pytest.raises(ApprovalEligibilityIntegrityError):
        approval_eligibility_artifact_from_canonical_json(canonical(document))


def test_recomputed_outer_request_rejects_internally_unrelated_evidence_chain():
    original = fixture_approval_bundle('outer-original')['eligibility_request']
    alternate = fixture_approval_bundle('outer-alternate')['eligibility_request']
    document = original.as_dict()
    document['approval_request'] = alternate.approval_request.as_dict()
    document['approval_evidence'] = alternate.approval_evidence.as_dict()
    _recompute_identity(
        document,
        'activation-eligibility-request',
        'eligibility_request_fingerprint',
        'eligibility_request_id',
    )

    with pytest.raises(ApprovalEligibilityIntegrityError):
        approval_eligibility_artifact_from_canonical_json(canonical(document))


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
def test_recomputed_outer_decision_cannot_present_denied_evidence_as_eligible(
    authority_status, disposition
):
    decision = fixture_approval_bundle(
        f'outer-forgery-{authority_status.value}-{disposition.value}',
        authority_status=authority_status,
        disposition=disposition,
    )['decision']
    document = decision.as_dict()
    document['status'] = (
        ActivationEligibilityStatus.ELIGIBLE_FOR_FUTURE_ACTIVATION.value
    )
    document['reasons'] = [
        ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED.value
    ]
    _recompute_identity(
        document,
        'activation-eligibility-decision',
        'eligibility_decision_fingerprint',
        'eligibility_decision_id',
    )

    with pytest.raises(ApprovalEligibilityIntegrityError):
        approval_eligibility_artifact_from_canonical_json(canonical(document))


def test_nonfinite_constant_is_rejected_before_schema_dispatch():
    with pytest.raises(ApprovalEligibilityIntegrityError, match='non-finite'):
        approval_eligibility_artifact_from_canonical_json(
            '{"schema":{"id":"x","version":NaN}}'
        )


def test_largest_transport_bound_is_enforced_before_parsing():
    payload = b'{' + b' ' * MAX_SERIALIZED_ELIGIBILITY_DECISION_BYTES + b'}'

    with pytest.raises(ApprovalEligibilityIntegrityError, match='largest v1 artifact bound'):
        approval_eligibility_artifact_from_canonical_json(payload)


def test_serializer_rejects_unrecognized_or_tampered_in_memory_artifact():
    request = fixture_approval_bundle('serializer-tamper')['eligibility_request']
    object.__setattr__(request, 'eligibility_request_id', 'tampered-request')

    with pytest.raises(ApprovalEligibilityIntegrityError):
        canonical_approval_eligibility_artifact_json(request)
    with pytest.raises(ApprovalEligibilityIntegrityError):
        canonical_approval_eligibility_artifact_json(object())
