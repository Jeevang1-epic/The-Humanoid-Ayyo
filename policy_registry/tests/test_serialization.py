import json
from hashlib import sha256

import pytest

from ayyo_policy_registry import (
    MAX_NOTE_LENGTH,
    MAX_SERIALIZED_RESULT_BYTES,
    CandidateRegistrationRequest,
    PolicyRegistryIntegrityError,
    RegistrationRequestError,
    canonical_registry_artifact_json,
    registry_artifact_from_canonical_json,
)

from helpers import fingerprint, fixture_registration_bundle, register_bundle


def canonical(document):
    return json.dumps(
        document,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )


def semantic_sha256(prefix, document):
    return f'{prefix}-sha256-{sha256(canonical(document).encode("utf-8")).hexdigest()}'


def artifact_fixture():
    bundle = fixture_registration_bundle('serialization')
    result = register_bundle(bundle)
    return bundle, result


def test_all_public_artifacts_round_trip_strictly_as_text_and_bytes():
    bundle, result = artifact_fixture()
    artifacts = (
        bundle['registration_request'],
        result.registered_version,
        result.updated_snapshot,
        result,
    )

    for artifact in artifacts:
        encoded = canonical_registry_artifact_json(artifact)
        assert registry_artifact_from_canonical_json(encoded) == artifact
        assert registry_artifact_from_canonical_json(encoded.encode('utf-8')) == artifact
        assert canonical_registry_artifact_json(
            registry_artifact_from_canonical_json(encoded)
        ) == encoded


def test_canonical_encoding_is_deterministic_and_compact():
    first = artifact_fixture()[1]
    second = artifact_fixture()[1]
    encoded = canonical_registry_artifact_json(first)

    assert first == second
    assert encoded == canonical_registry_artifact_json(second)
    assert '\n' not in encoded
    assert ': ' not in encoded


def test_legitimate_already_registered_result_round_trip_is_byte_deterministic():
    bundle = fixture_registration_bundle('already-registered-round-trip')
    registered = register_bundle(bundle)
    result = register_bundle(bundle, registered.updated_snapshot)
    encoded = canonical_registry_artifact_json(result)

    decoded = registry_artifact_from_canonical_json(encoded)

    assert decoded == result
    assert canonical_registry_artifact_json(decoded) == encoded


def test_recomputed_outer_result_rejects_cross_composed_request_identity():
    result = register_bundle(fixture_registration_bundle('canonical-result-binding'))
    alternate = fixture_registration_bundle(
        'canonical-result-substitution'
    )['registration_request']
    document = result.as_dict()
    document['registration_request'] = {
        'fingerprint': alternate.registration_request_fingerprint,
        'id': alternate.registration_request_id,
    }
    semantic_document = {
        key: value
        for key, value in document.items()
        if key not in {'result_fingerprint', 'result_id'}
    }
    result_fingerprint = semantic_sha256(
        'registration-result-content', semantic_document
    )
    document['result_fingerprint'] = result_fingerprint
    document['result_id'] = semantic_sha256(
        'registration-result',
        {
            'content_fingerprint': result_fingerprint,
            'schema_id': document['schema']['id'],
            'schema_version': document['schema']['version'],
        },
    )

    with pytest.raises(PolicyRegistryIntegrityError, match='differs'):
        registry_artifact_from_canonical_json(canonical(document))


@pytest.mark.parametrize(
    'payload',
    [
        '',
        'not-json',
        '[]',
        'NaN',
        b'\xff',
        None,
        1,
        True,
    ],
)
def test_malformed_nonobject_utf8_and_wrong_transport_inputs_fail_closed(payload):
    with pytest.raises(PolicyRegistryIntegrityError):
        registry_artifact_from_canonical_json(payload)


def test_duplicate_json_key_is_rejected():
    request = artifact_fixture()[0]['registration_request']
    encoded = canonical_registry_artifact_json(request)
    duplicated = encoded.replace('"note":', '"note":null,"note":', 1)

    with pytest.raises(PolicyRegistryIntegrityError, match='duplicate key'):
        registry_artifact_from_canonical_json(duplicated)


def test_noncanonical_whitespace_is_rejected():
    request = artifact_fixture()[0]['registration_request']
    pretty = json.dumps(request.as_dict(), indent=2, sort_keys=True)

    with pytest.raises(PolicyRegistryIntegrityError, match='not canonical'):
        registry_artifact_from_canonical_json(pretty)


@pytest.mark.parametrize('mutation', ['unknown', 'missing', 'schema-id', 'schema-version'])
def test_unknown_missing_and_unsupported_schema_fields_are_rejected(mutation):
    request = artifact_fixture()[0]['registration_request']
    document = request.as_dict()
    if mutation == 'unknown':
        document['unexpected'] = 'value'
    elif mutation == 'missing':
        del document['candidate']
    elif mutation == 'schema-id':
        document['schema']['id'] = 'ayyo.policy-registry.unknown.v1'
    else:
        document['schema']['version'] = '2.0.0'

    with pytest.raises(PolicyRegistryIntegrityError):
        registry_artifact_from_canonical_json(canonical(document))


@pytest.mark.parametrize(
    ('path', 'replacement'),
    [
        (('registration_request_fingerprint',), 'request-sha256-' + '0' * 64),
        (('candidate', 'fingerprint'), 'candidate-sha256-' + '0' * 64),
        (('promotion_decision', 'id'), 'wrong-decision'),
        (('target_stage',), 'production'),
    ],
)
def test_identity_and_enum_tampering_is_rejected(path, replacement):
    request = artifact_fixture()[0]['registration_request']
    document = request.as_dict()
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(PolicyRegistryIntegrityError):
        registry_artifact_from_canonical_json(canonical(document))


def test_nested_snapshot_record_tampering_is_rejected():
    result = artifact_fixture()[1]
    document = result.as_dict()
    document['updated_snapshot']['registered_versions'][0]['candidate'][
        'semantic_version'
    ] = '9.9.9'

    with pytest.raises(PolicyRegistryIntegrityError):
        registry_artifact_from_canonical_json(canonical(document))


def test_nonfinite_constant_is_rejected_before_schema_dispatch():
    with pytest.raises(PolicyRegistryIntegrityError, match='non-finite'):
        registry_artifact_from_canonical_json(
            '{"schema":{"id":"x","version":NaN}}'
        )


def test_largest_transport_bound_is_enforced_before_parsing():
    payload = b'{' + b' ' * MAX_SERIALIZED_RESULT_BYTES + b'}'

    with pytest.raises(PolicyRegistryIntegrityError, match='largest v1 artifact bound'):
        registry_artifact_from_canonical_json(payload)


def test_optional_note_bound_and_control_characters_are_rejected():
    bundle = fixture_registration_bundle('note-bound')
    arguments = {
        'candidate': bundle['candidate'],
        'evaluation_report': bundle['report'],
        'promotion_criteria': bundle['criteria'],
        'promotion_request': bundle['promotion_request'],
        'promotion_decision': bundle['decision'],
        'target_stage': bundle['decision'].target_stage,
        'provenance_ref': 'registry-review.fixture.v1',
        'provenance_fingerprint': fingerprint('registry-review', 'note'),
    }

    with pytest.raises(RegistrationRequestError):
        CandidateRegistrationRequest(**arguments, note='x' * (MAX_NOTE_LENGTH + 1))
    with pytest.raises(RegistrationRequestError):
        CandidateRegistrationRequest(**arguments, note='unsafe\ntext')


def test_serializer_rejects_unrecognized_or_tampered_in_memory_artifact():
    request = artifact_fixture()[0]['registration_request']
    object.__setattr__(request, 'registration_request_id', 'tampered-request')

    with pytest.raises(PolicyRegistryIntegrityError):
        canonical_registry_artifact_json(request)
    with pytest.raises(PolicyRegistryIntegrityError):
        canonical_registry_artifact_json(object())
