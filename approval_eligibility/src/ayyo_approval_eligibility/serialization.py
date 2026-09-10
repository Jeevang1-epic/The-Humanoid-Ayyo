"""Strict canonical inspect-only serialization for approval eligibility artifacts."""

from __future__ import annotations

import json

from ayyo_policy_registry import (
    RegisteredPolicyVersion,
    registry_artifact_from_canonical_json,
)

from .canonical import MAX_SERIALIZED_ELIGIBILITY_DECISION_BYTES, canonical_json
from .errors import ApprovalEligibilityIntegrityError
from .evaluation import verify_activation_eligibility_decision
from .models import (
    ACTIVATION_ELIGIBILITY_DECISION_SCHEMA_ID,
    ACTIVATION_ELIGIBILITY_REQUEST_SCHEMA_ID,
    APPROVAL_ELIGIBILITY_SCHEMA_VERSION,
    APPROVAL_REQUEST_SCHEMA_ID,
    AUTHORITY_APPROVAL_EVIDENCE_SCHEMA_ID,
    AUTHORITY_REFERENCE_SCHEMA_ID,
    ActivationEligibilityDecision,
    ActivationEligibilityReason,
    ActivationEligibilityRequest,
    ActivationEligibilityStatus,
    ApprovalDisposition,
    ApprovalRequest,
    ApprovalScope,
    AuthorityApprovalEvidence,
    AuthorityReference,
    AuthorityVerificationStatus,
    verify_activation_eligibility_request,
    verify_approval_request,
    verify_authority_approval_evidence,
    verify_authority_reference,
)


ApprovalEligibilityArtifact = (
    AuthorityReference
    | ApprovalRequest
    | AuthorityApprovalEvidence
    | ActivationEligibilityRequest
    | ActivationEligibilityDecision
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ApprovalEligibilityIntegrityError(
                'approval eligibility JSON contains a duplicate key'
            )
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ApprovalEligibilityIntegrityError(
        f'non-finite JSON constant is forbidden: {value}'
    )


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ApprovalEligibilityIntegrityError(
            f'{field_name} has unknown or missing fields'
        )
    return value


def _sequence(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise ApprovalEligibilityIntegrityError(f'{field_name} must be a JSON array')
    return value


def _identity(value: object, field_name: str) -> dict[str, object]:
    return _mapping(value, field_name, {'fingerprint', 'id'})


def _enum(enum_type: type, value: object, field_name: str):
    if type(value) is not str:
        raise ApprovalEligibilityIntegrityError(
            f'{field_name} must use its closed enum'
        )
    try:
        return enum_type(value)
    except ValueError as error:
        raise ApprovalEligibilityIntegrityError(
            f'{field_name} uses an unsupported value'
        ) from error


def _schema(document: dict[str, object]) -> tuple[str, str]:
    schema = _mapping(
        document.get('schema'),
        'approval eligibility schema',
        {'id', 'version'},
    )
    if type(schema['id']) is not str or type(schema['version']) is not str:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility schema identity must be text'
        )
    return schema['id'], schema['version']


_VERIFY_BY_TYPE = {
    AuthorityReference: verify_authority_reference,
    ApprovalRequest: verify_approval_request,
    AuthorityApprovalEvidence: verify_authority_approval_evidence,
    ActivationEligibilityRequest: verify_activation_eligibility_request,
    ActivationEligibilityDecision: verify_activation_eligibility_decision,
}


def canonical_approval_eligibility_artifact_json(
    artifact: ApprovalEligibilityArtifact,
) -> str:
    verifier = _VERIFY_BY_TYPE.get(type(artifact))
    if verifier is None or not verifier(artifact):
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility artifact type or content failed integrity verification'
        )
    return canonical_json(artifact.as_dict())


def _authority_reference(root: dict[str, object]) -> AuthorityReference:
    root = _mapping(
        root,
        'authority reference',
        {
            'authority',
            'authority_reference_fingerprint',
            'authority_reference_id',
            'note',
            'provenance',
            'schema',
            'verification',
        },
    )
    authority = _identity(root['authority'], 'authority identity')
    provenance = _mapping(
        root['provenance'], 'authority provenance', {'fingerprint', 'source_ref'}
    )
    verification = _mapping(
        root['verification'],
        'authority verification',
        {'evidence', 'provider', 'status'},
    )
    provider = verification['provider']
    if provider is not None:
        provider = _mapping(
            provider, 'authority verification provider', {'fingerprint', 'source_ref'}
        )
    evidence = verification['evidence']
    if evidence is not None:
        evidence = _mapping(
            evidence, 'authority verification evidence', {'fingerprint', 'source_ref'}
        )
    return AuthorityReference._from_fields(
        authority_id=authority['id'],
        authority_fingerprint=authority['fingerprint'],
        verification_status=_enum(
            AuthorityVerificationStatus,
            verification['status'],
            'authority verification status',
        ),
        verification_provider_ref=provider['source_ref'] if provider else None,
        verification_provider_fingerprint=provider['fingerprint'] if provider else None,
        verification_evidence_ref=evidence['source_ref'] if evidence else None,
        verification_evidence_fingerprint=evidence['fingerprint'] if evidence else None,
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
        note=root['note'],
    )


def _approval_request(root: dict[str, object]) -> ApprovalRequest:
    root = _mapping(
        root,
        'approval request',
        {
            'approval_request_fingerprint',
            'approval_request_id',
            'approval_scope',
            'authority',
            'candidate',
            'note',
            'promotion',
            'provenance',
            'registration_request',
            'registry_record',
            'schema',
        },
    )
    authority = _mapping(
        root['authority'], 'approval authority', {'identity', 'reference'}
    )
    authority_identity = _identity(authority['identity'], 'approval authority identity')
    authority_reference = _identity(
        authority['reference'], 'approval authority reference'
    )
    candidate = _mapping(
        root['candidate'],
        'approval candidate',
        {'fingerprint', 'id', 'semantic_version'},
    )
    promotion = _mapping(
        root['promotion'], 'approval promotion', {'decision', 'target_stage'}
    )
    promotion_decision = _identity(
        promotion['decision'], 'approval promotion decision'
    )
    registration_request = _identity(
        root['registration_request'], 'approval registration request'
    )
    registry_record = _identity(root['registry_record'], 'approval registry record')
    provenance = _mapping(
        root['provenance'], 'approval request provenance', {'fingerprint', 'source_ref'}
    )
    return ApprovalRequest._from_fields(
        candidate_id=candidate['id'],
        candidate_fingerprint=candidate['fingerprint'],
        candidate_semantic_version=candidate['semantic_version'],
        registry_record_id=registry_record['id'],
        registry_record_fingerprint=registry_record['fingerprint'],
        registration_request_id=registration_request['id'],
        registration_request_fingerprint=registration_request['fingerprint'],
        promotion_decision_id=promotion_decision['id'],
        promotion_decision_fingerprint=promotion_decision['fingerprint'],
        promotion_target_stage=promotion['target_stage'],
        authority_reference_id=authority_reference['id'],
        authority_reference_fingerprint=authority_reference['fingerprint'],
        authority_id=authority_identity['id'],
        authority_fingerprint=authority_identity['fingerprint'],
        approval_scope=_enum(ApprovalScope, root['approval_scope'], 'approval scope'),
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
        note=root['note'],
    )


def _approval_evidence(root: dict[str, object]) -> AuthorityApprovalEvidence:
    root = _mapping(
        root,
        'authority approval evidence',
        {
            'approval_evidence_fingerprint',
            'approval_evidence_id',
            'approval_request',
            'authority',
            'disposition',
            'evidence_source',
            'note',
            'schema',
        },
    )
    evidence_source = _mapping(
        root['evidence_source'],
        'approval evidence source',
        {'fingerprint', 'source_ref'},
    )
    return AuthorityApprovalEvidence._from_fields(
        approval_request=_approval_request(root['approval_request']),
        authority=_authority_reference(root['authority']),
        disposition=_enum(
            ApprovalDisposition, root['disposition'], 'approval disposition'
        ),
        evidence_ref=evidence_source['source_ref'],
        evidence_fingerprint=evidence_source['fingerprint'],
        note=root['note'],
    )


def _registered_version(value: object) -> RegisteredPolicyVersion:
    if type(value) is not dict:
        raise ApprovalEligibilityIntegrityError(
            'registered policy version must be an object'
        )
    try:
        artifact = registry_artifact_from_canonical_json(canonical_json(value))
    except ValueError as error:
        raise ApprovalEligibilityIntegrityError(
            'registered policy version failed registry verification'
        ) from error
    if type(artifact) is not RegisteredPolicyVersion:
        raise ApprovalEligibilityIntegrityError(
            'eligibility request requires a registered policy version'
        )
    return artifact


def _eligibility_request(root: dict[str, object]) -> ActivationEligibilityRequest:
    root = _mapping(
        root,
        'activation eligibility request',
        {
            'approval_evidence',
            'approval_request',
            'eligibility_request_fingerprint',
            'eligibility_request_id',
            'note',
            'provenance',
            'registered_version',
            'schema',
        },
    )
    provenance = _mapping(
        root['provenance'],
        'eligibility request provenance',
        {'fingerprint', 'source_ref'},
    )
    return ActivationEligibilityRequest._from_fields(
        registered_version=_registered_version(root['registered_version']),
        approval_request=_approval_request(root['approval_request']),
        approval_evidence=_approval_evidence(root['approval_evidence']),
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
        note=root['note'],
    )


def _eligibility_decision(root: dict[str, object]) -> ActivationEligibilityDecision:
    root = _mapping(
        root,
        'activation eligibility decision',
        {
            'eligibility_decision_fingerprint',
            'eligibility_decision_id',
            'reasons',
            'request',
            'schema',
            'status',
        },
    )
    reasons = tuple(
        _enum(ActivationEligibilityReason, item, 'activation eligibility reason')
        for item in _sequence(root['reasons'], 'activation eligibility reasons')
    )
    return ActivationEligibilityDecision._create(
        request=_eligibility_request(root['request']),
        status=_enum(
            ActivationEligibilityStatus,
            root['status'],
            'activation eligibility status',
        ),
        reasons=reasons,
    )


_PARSERS = {
    AUTHORITY_REFERENCE_SCHEMA_ID: _authority_reference,
    APPROVAL_REQUEST_SCHEMA_ID: _approval_request,
    AUTHORITY_APPROVAL_EVIDENCE_SCHEMA_ID: _approval_evidence,
    ACTIVATION_ELIGIBILITY_REQUEST_SCHEMA_ID: _eligibility_request,
    ACTIVATION_ELIGIBILITY_DECISION_SCHEMA_ID: _eligibility_decision,
}


def approval_eligibility_artifact_from_canonical_json(
    payload: str | bytes,
) -> ApprovalEligibilityArtifact:
    if isinstance(payload, bytes):
        raw = payload
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise ApprovalEligibilityIntegrityError(
                'approval eligibility JSON is not valid UTF-8'
            ) from error
    elif type(payload) is str:
        text = payload
        raw = payload.encode('utf-8')
    else:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility JSON must be text or bytes'
        )
    if not raw or len(raw) > MAX_SERIALIZED_ELIGIBILITY_DECISION_BYTES:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility JSON is empty or exceeds the largest v1 artifact bound'
        )
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ApprovalEligibilityIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility JSON is malformed'
        ) from error
    if canonical_json(document).encode('utf-8') != raw:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility JSON is not canonical'
        )
    if type(document) is not dict:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility JSON root must be an object'
        )
    schema_id, schema_version = _schema(document)
    parser = _PARSERS.get(schema_id)
    if parser is None:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility schema identity is unsupported'
        )
    if schema_version != APPROVAL_ELIGIBILITY_SCHEMA_VERSION:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility schema version is unsupported'
        )
    try:
        artifact = parser(document)
    except ApprovalEligibilityIntegrityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility JSON content violates its v1 contract'
        ) from error
    if artifact.as_dict() != document:
        raise ApprovalEligibilityIntegrityError(
            'approval eligibility artifact identity or content was tampered'
        )
    canonical_approval_eligibility_artifact_json(artifact)
    return artifact
