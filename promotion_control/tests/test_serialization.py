from __future__ import annotations

import json

import pytest

from ayyo_promotion_control import (
    MAX_SERIALIZED_ARTIFACT_BYTES,
    PromotionControlIntegrityError,
    canonical_control_artifact_json,
    control_artifact_from_canonical_json,
    evaluate_rollback,
)

from helpers import fixture_rollback_bundle


def _artifacts():
    bundle = fixture_rollback_bundle()
    rollback_decision = evaluate_rollback(
        criteria=bundle['rollback_criteria'],
        request=bundle['rollback_request'],
        current_candidate=bundle['current_candidate'],
        target_candidate=bundle['candidate'],
        known_good=bundle['known_good'],
        promotion_decision=bundle['decision'],
    )
    return (
        bundle['criteria'],
        bundle['request'],
        bundle['decision'],
        bundle['rollback_evidence'],
        bundle['known_good'],
        bundle['rollback_criteria'],
        bundle['rollback_request'],
        rollback_decision,
    )


@pytest.mark.parametrize('artifact_index', range(8))
def test_every_public_artifact_round_trips_with_stable_identity(artifact_index):
    artifact = _artifacts()[artifact_index]
    payload = canonical_control_artifact_json(artifact)

    restored_from_text = control_artifact_from_canonical_json(payload)
    restored_from_bytes = control_artifact_from_canonical_json(payload.encode('utf-8'))

    assert restored_from_text == artifact
    assert restored_from_bytes == artifact
    assert canonical_control_artifact_json(restored_from_text) == payload


def test_unknown_and_missing_fields_are_rejected():
    artifact = _artifacts()[0]
    document = json.loads(canonical_control_artifact_json(artifact))
    document['unknown'] = 'field'
    with pytest.raises(PromotionControlIntegrityError, match='unknown or missing'):
        control_artifact_from_canonical_json(_canonical(document))

    document.pop('unknown')
    document.pop('candidate')
    with pytest.raises(PromotionControlIntegrityError, match='unknown or missing'):
        control_artifact_from_canonical_json(_canonical(document))


def test_duplicate_keys_are_rejected_before_identity_checks():
    payload = canonical_control_artifact_json(_artifacts()[0])
    duplicate = payload.replace('"schema":', '"schema":{},"schema":', 1)

    with pytest.raises(PromotionControlIntegrityError, match='duplicate key'):
        control_artifact_from_canonical_json(duplicate)


@pytest.mark.parametrize(
    ('schema_field', 'replacement', 'message'),
    [
        ('id', 'ayyo.promotion-control.unknown.v1', 'identity is unsupported'),
        ('version', '2.0.0', 'version is unsupported'),
    ],
)
def test_unknown_schema_identity_and_version_are_rejected(
    schema_field, replacement, message
):
    document = json.loads(canonical_control_artifact_json(_artifacts()[0]))
    document['schema'][schema_field] = replacement

    with pytest.raises(PromotionControlIntegrityError, match=message):
        control_artifact_from_canonical_json(_canonical(document))


def test_content_identity_tampering_is_rejected():
    document = json.loads(canonical_control_artifact_json(_artifacts()[0]))
    document['minimum_evaluated_trials'] = 1 + document['minimum_evaluated_trials']

    with pytest.raises(PromotionControlIntegrityError, match='tampered'):
        control_artifact_from_canonical_json(_canonical(document))


def test_sha256_identity_shape_is_validated_before_tamper_comparison():
    document = json.loads(canonical_control_artifact_json(_artifacts()[0]))
    document['candidate']['fingerprint'] = 'not-a-sha256-identity'

    with pytest.raises(PromotionControlIntegrityError):
        control_artifact_from_canonical_json(_canonical(document))


def test_embedded_rollback_evidence_tampering_is_rejected():
    document = json.loads(canonical_control_artifact_json(_artifacts()[6]))
    document['evidence_references'][0]['source']['source_ref'] = 'substituted-source'

    with pytest.raises(PromotionControlIntegrityError, match='tampered'):
        control_artifact_from_canonical_json(_canonical(document))


@pytest.mark.parametrize(
    'payload',
    [
        '',
        '{',
        '[]',
        '{"schema":NaN}',
        b'\xff',
        12,
    ],
)
def test_malformed_nonfinite_nonobject_and_wrong_transport_inputs_fail_closed(payload):
    with pytest.raises(PromotionControlIntegrityError):
        control_artifact_from_canonical_json(payload)


def test_noncanonical_json_is_rejected():
    document = json.loads(canonical_control_artifact_json(_artifacts()[0]))
    noncanonical = json.dumps(document, indent=2, sort_keys=True)

    with pytest.raises(PromotionControlIntegrityError, match='not canonical'):
        control_artifact_from_canonical_json(noncanonical)


def test_oversized_payload_is_rejected_before_parsing():
    payload = '{"padding":"' + ('x' * MAX_SERIALIZED_ARTIFACT_BYTES) + '"}'

    with pytest.raises(PromotionControlIntegrityError, match='exceeds'):
        control_artifact_from_canonical_json(payload)


def test_serializer_rejects_an_in_memory_tampered_artifact():
    artifact = _artifacts()[2]
    object.__setattr__(artifact, 'decision_id', 'substituted-decision')

    with pytest.raises(PromotionControlIntegrityError, match='integrity'):
        canonical_control_artifact_json(artifact)


def _canonical(document) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(',', ':'),
    )
