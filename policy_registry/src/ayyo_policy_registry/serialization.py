"""Strict canonical inspect-only serialization for registry artifacts."""

from __future__ import annotations

import json

from ayyo_promotion_control import PromotionTargetStage

from .canonical import (
    MAX_SERIALIZED_RESULT_BYTES,
    canonical_json,
)
from .errors import PolicyRegistryIntegrityError
from .models import (
    POLICY_REGISTRY_SCHEMA_VERSION,
    POLICY_REGISTRY_SNAPSHOT_SCHEMA_ID,
    REGISTERED_POLICY_VERSION_SCHEMA_ID,
    REGISTRATION_REQUEST_SCHEMA_ID,
    REGISTRATION_RESULT_SCHEMA_ID,
    CandidateRegistrationRequest,
    PolicyRegistrySnapshot,
    RegisteredPolicyVersion,
    RegistrationResult,
    RegistrationStatus,
    verify_policy_registry_snapshot,
    verify_registered_policy_version,
    verify_registration_request,
    verify_registration_result,
)


RegistryArtifact = (
    CandidateRegistrationRequest
    | RegisteredPolicyVersion
    | PolicyRegistrySnapshot
    | RegistrationResult
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyRegistryIntegrityError('registry JSON contains a duplicate key')
        result[key] = value
    return result


def _reject_constant(value: str):
    raise PolicyRegistryIntegrityError(f'non-finite JSON constant is forbidden: {value}')


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise PolicyRegistryIntegrityError(f'{field_name} has unknown or missing fields')
    return value


def _sequence(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise PolicyRegistryIntegrityError(f'{field_name} must be a JSON array')
    return value


def _identity(value: object, field_name: str) -> dict[str, object]:
    return _mapping(value, field_name, {'fingerprint', 'id'})


def _enum(enum_type: type, value: object, field_name: str):
    if type(value) is not str:
        raise PolicyRegistryIntegrityError(f'{field_name} must use its closed enum')
    try:
        return enum_type(value)
    except ValueError as error:
        raise PolicyRegistryIntegrityError(
            f'{field_name} uses an unsupported value'
        ) from error


def _schema(document: dict[str, object]) -> tuple[str, str]:
    schema = _mapping(document.get('schema'), 'registry schema', {'id', 'version'})
    if type(schema['id']) is not str or type(schema['version']) is not str:
        raise PolicyRegistryIntegrityError('registry schema identity must be text')
    return schema['id'], schema['version']


_VERIFY_BY_TYPE = {
    CandidateRegistrationRequest: verify_registration_request,
    RegisteredPolicyVersion: verify_registered_policy_version,
    PolicyRegistrySnapshot: verify_policy_registry_snapshot,
    RegistrationResult: verify_registration_result,
}


def canonical_registry_artifact_json(artifact: RegistryArtifact) -> str:
    verifier = _VERIFY_BY_TYPE.get(type(artifact))
    if verifier is None or not verifier(artifact):
        raise PolicyRegistryIntegrityError(
            'registry artifact type or content failed integrity verification'
        )
    return canonical_json(artifact.as_dict())


def _registration_request(root: dict[str, object]) -> CandidateRegistrationRequest:
    root = _mapping(
        root,
        'registration request',
        {
            'candidate',
            'evaluation_report',
            'note',
            'promotion_criteria',
            'promotion_decision',
            'promotion_request',
            'provenance',
            'registration_request_fingerprint',
            'registration_request_id',
            'schema',
            'target_stage',
        },
    )
    candidate = _identity(root['candidate'], 'registration candidate')
    report = _identity(root['evaluation_report'], 'registration evaluation report')
    criteria = _identity(root['promotion_criteria'], 'registration promotion criteria')
    promotion_request = _identity(
        root['promotion_request'], 'registration promotion request'
    )
    decision = _identity(root['promotion_decision'], 'registration promotion decision')
    provenance = _mapping(
        root['provenance'], 'registration provenance', {'fingerprint', 'source_ref'}
    )
    return CandidateRegistrationRequest._from_fields(
        candidate_id=candidate['id'],
        candidate_fingerprint=candidate['fingerprint'],
        evaluation_report_id=report['id'],
        evaluation_report_fingerprint=report['fingerprint'],
        promotion_criteria_id=criteria['id'],
        promotion_criteria_fingerprint=criteria['fingerprint'],
        promotion_request_id=promotion_request['id'],
        promotion_request_fingerprint=promotion_request['fingerprint'],
        promotion_decision_id=decision['id'],
        promotion_decision_fingerprint=decision['fingerprint'],
        target_stage=_enum(PromotionTargetStage, root['target_stage'], 'target_stage'),
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
        note=root['note'],
    )


def _registered_version(root: dict[str, object]) -> RegisteredPolicyVersion:
    root = _mapping(
        root,
        'registered policy version',
        {
            'candidate',
            'evaluation',
            'policy_contract',
            'promotion',
            'provenance',
            'record_fingerprint',
            'record_id',
            'registration_request',
            'schema',
        },
    )
    candidate = _mapping(
        root['candidate'],
        'registered candidate',
        {'evidence_set', 'fingerprint', 'id', 'parent', 'semantic_version'},
    )
    evidence = _identity(candidate['evidence_set'], 'candidate evidence set')
    parent = candidate['parent']
    if parent is not None:
        parent = _identity(parent, 'parent candidate')
    evaluation = _mapping(
        root['evaluation'],
        'registered evaluation',
        {'contract', 'holdout_evidence_set', 'report'},
    )
    evaluation_contract = _mapping(
        evaluation['contract'], 'evaluation contract', {'id', 'version'}
    )
    holdout = _identity(evaluation['holdout_evidence_set'], 'holdout evidence set')
    report = _identity(evaluation['report'], 'evaluation report')
    policy_contract = _mapping(
        root['policy_contract'],
        'registered policy contract',
        {'family_id', 'input', 'output'},
    )
    input_contract = _mapping(
        policy_contract['input'], 'input contract', {'id', 'version'}
    )
    output_contract = _mapping(
        policy_contract['output'], 'output contract', {'id', 'version'}
    )
    promotion = _mapping(
        root['promotion'],
        'registered promotion evidence',
        {'criteria', 'decision', 'request', 'target_stage'},
    )
    criteria = _identity(promotion['criteria'], 'registered promotion criteria')
    request = _identity(promotion['request'], 'registered promotion request')
    decision = _identity(promotion['decision'], 'registered promotion decision')
    registration_request = _identity(
        root['registration_request'], 'candidate registration request'
    )
    provenance = _mapping(
        root['provenance'], 'registered provenance', {'fingerprint', 'source_ref'}
    )
    return RegisteredPolicyVersion._from_fields(
        candidate_id=candidate['id'],
        candidate_fingerprint=candidate['fingerprint'],
        semantic_version=candidate['semantic_version'],
        policy_family_id=policy_contract['family_id'],
        candidate_evidence_set_id=evidence['id'],
        candidate_evidence_set_fingerprint=evidence['fingerprint'],
        input_contract_id=input_contract['id'],
        input_contract_version=input_contract['version'],
        output_contract_id=output_contract['id'],
        output_contract_version=output_contract['version'],
        parent_candidate_id=parent['id'] if parent else None,
        parent_candidate_fingerprint=parent['fingerprint'] if parent else None,
        evaluation_report_id=report['id'],
        evaluation_report_fingerprint=report['fingerprint'],
        evaluation_contract_id=evaluation_contract['id'],
        evaluation_contract_version=evaluation_contract['version'],
        holdout_evidence_set_id=holdout['id'],
        holdout_evidence_set_fingerprint=holdout['fingerprint'],
        promotion_criteria_id=criteria['id'],
        promotion_criteria_fingerprint=criteria['fingerprint'],
        promotion_request_id=request['id'],
        promotion_request_fingerprint=request['fingerprint'],
        promotion_decision_id=decision['id'],
        promotion_decision_fingerprint=decision['fingerprint'],
        target_stage=_enum(
            PromotionTargetStage, promotion['target_stage'], 'target_stage'
        ),
        registration_request_id=registration_request['id'],
        registration_request_fingerprint=registration_request['fingerprint'],
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
    )


def _snapshot(root: dict[str, object]) -> PolicyRegistrySnapshot:
    root = _mapping(
        root,
        'policy registry snapshot',
        {
            'registered_versions',
            'schema',
            'snapshot_fingerprint',
            'snapshot_id',
        },
    )
    return PolicyRegistrySnapshot._from_fields(
        registered_versions=tuple(
            _registered_version(item)
            for item in _sequence(root['registered_versions'], 'registered_versions')
        )
    )


def _registration_result(root: dict[str, object]) -> RegistrationResult:
    root = _mapping(
        root,
        'registration result',
        {
            'previous_snapshot',
            'registered_version',
            'registration_request',
            'result_fingerprint',
            'result_id',
            'schema',
            'status',
            'updated_snapshot',
        },
    )
    request = _identity(root['registration_request'], 'result registration request')
    return RegistrationResult._from_fields(
        status=_enum(RegistrationStatus, root['status'], 'registration status'),
        registration_request_id=request['id'],
        registration_request_fingerprint=request['fingerprint'],
        registered_version=_registered_version(root['registered_version']),
        previous_snapshot=_snapshot(root['previous_snapshot']),
        updated_snapshot=_snapshot(root['updated_snapshot']),
    )


_PARSERS = {
    REGISTRATION_REQUEST_SCHEMA_ID: _registration_request,
    REGISTERED_POLICY_VERSION_SCHEMA_ID: _registered_version,
    POLICY_REGISTRY_SNAPSHOT_SCHEMA_ID: _snapshot,
    REGISTRATION_RESULT_SCHEMA_ID: _registration_result,
}


def registry_artifact_from_canonical_json(payload: str | bytes) -> RegistryArtifact:
    if isinstance(payload, bytes):
        raw = payload
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise PolicyRegistryIntegrityError(
                'registry JSON is not valid UTF-8'
            ) from error
    elif type(payload) is str:
        text = payload
        raw = payload.encode('utf-8')
    else:
        raise PolicyRegistryIntegrityError('registry JSON must be text or bytes')
    if not raw or len(raw) > MAX_SERIALIZED_RESULT_BYTES:
        raise PolicyRegistryIntegrityError(
            'registry JSON is empty or exceeds the largest v1 artifact bound'
        )
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PolicyRegistryIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PolicyRegistryIntegrityError('registry JSON is malformed') from error
    if canonical_json(document).encode('utf-8') != raw:
        raise PolicyRegistryIntegrityError('registry JSON is not canonical')
    if type(document) is not dict:
        raise PolicyRegistryIntegrityError('registry JSON root must be an object')
    schema_id, schema_version = _schema(document)
    parser = _PARSERS.get(schema_id)
    if parser is None:
        raise PolicyRegistryIntegrityError('registry schema identity is unsupported')
    if schema_version != POLICY_REGISTRY_SCHEMA_VERSION:
        raise PolicyRegistryIntegrityError('registry schema version is unsupported')
    try:
        artifact = parser(document)
    except PolicyRegistryIntegrityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise PolicyRegistryIntegrityError(
            'registry JSON content violates its v1 contract'
        ) from error
    if artifact.as_dict() != document:
        raise PolicyRegistryIntegrityError(
            'registry artifact identity or content was tampered'
        )
    canonical_registry_artifact_json(artifact)
    return artifact
