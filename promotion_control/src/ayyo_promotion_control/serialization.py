"""Strict canonical serialization for all public promotion-control artifacts."""

from __future__ import annotations

import json

from ayyo_learning_evaluation import OfflineEvaluationDisposition

from .canonical import MAX_SERIALIZED_ARTIFACT_BYTES, canonical_json
from .errors import PromotionControlIntegrityError
from .promotion import (
    PROMOTION_CRITERIA_SCHEMA_ID,
    PROMOTION_DECISION_SCHEMA_ID,
    PROMOTION_REQUEST_SCHEMA_ID,
    PROMOTION_SCHEMA_VERSION,
    CandidatePromotionRequest,
    PromotionCriteria,
    PromotionDecision,
    PromotionDecisionReason,
    PromotionDecisionStatus,
    PromotionTargetStage,
    verify_promotion_criteria,
    verify_promotion_decision,
    verify_promotion_request,
)
from .rollback import (
    KNOWN_GOOD_POLICY_SCHEMA_ID,
    ROLLBACK_CRITERIA_SCHEMA_ID,
    ROLLBACK_DECISION_SCHEMA_ID,
    ROLLBACK_EVIDENCE_SCHEMA_ID,
    ROLLBACK_REQUEST_SCHEMA_ID,
    ROLLBACK_SCHEMA_VERSION,
    KnownGoodPolicyReference,
    RollbackCriteria,
    RollbackDecision,
    RollbackDecisionReason,
    RollbackDecisionStatus,
    RollbackEvidenceKind,
    RollbackEvidenceReference,
    RollbackReason,
    RollbackRequest,
    verify_known_good_policy,
    verify_rollback_criteria,
    verify_rollback_decision,
    verify_rollback_evidence,
    verify_rollback_request,
)


ControlArtifact = (
    PromotionCriteria
    | CandidatePromotionRequest
    | PromotionDecision
    | RollbackEvidenceReference
    | KnownGoodPolicyReference
    | RollbackCriteria
    | RollbackRequest
    | RollbackDecision
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PromotionControlIntegrityError('control JSON contains a duplicate key')
        result[key] = value
    return result


def _reject_constant(value: str):
    raise PromotionControlIntegrityError(f'non-finite JSON constant is forbidden: {value}')


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise PromotionControlIntegrityError(f'{field_name} has unknown or missing fields')
    return value


def _sequence(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise PromotionControlIntegrityError(f'{field_name} must be a JSON array')
    return value


def _enum(enum_type: type, value: object, field_name: str):
    if type(value) is not str:
        raise PromotionControlIntegrityError(f'{field_name} must use its closed enum')
    try:
        return enum_type(value)
    except ValueError as error:
        raise PromotionControlIntegrityError(f'{field_name} uses an unsupported value') from error


def _identity(value: object, field_name: str) -> dict[str, object]:
    return _mapping(value, field_name, {'fingerprint', 'id'})


def _schema(document: dict[str, object]) -> tuple[str, str]:
    schema = _mapping(document.get('schema'), 'control schema', {'id', 'version'})
    if type(schema['id']) is not str or type(schema['version']) is not str:
        raise PromotionControlIntegrityError('control schema identity must be text')
    return schema['id'], schema['version']


_VERIFY_BY_TYPE = {
    PromotionCriteria: verify_promotion_criteria,
    CandidatePromotionRequest: verify_promotion_request,
    PromotionDecision: verify_promotion_decision,
    RollbackEvidenceReference: verify_rollback_evidence,
    KnownGoodPolicyReference: verify_known_good_policy,
    RollbackCriteria: verify_rollback_criteria,
    RollbackRequest: verify_rollback_request,
    RollbackDecision: verify_rollback_decision,
}


def canonical_control_artifact_json(artifact: ControlArtifact) -> str:
    verifier = _VERIFY_BY_TYPE.get(type(artifact))
    if verifier is None or not verifier(artifact):
        raise PromotionControlIntegrityError(
            'control artifact type or content failed integrity verification'
        )
    encoded = canonical_json(artifact.as_dict())
    if len(encoded.encode('utf-8')) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise PromotionControlIntegrityError('serialized control artifact exceeds its v1 bound')
    return encoded


def _promotion_criteria(root: dict[str, object]) -> PromotionCriteria:
    root = _mapping(
        root,
        'promotion criteria',
        {
            'accepted_dispositions',
            'allowed_target_stages',
            'candidate',
            'criteria_fingerprint',
            'criteria_id',
            'holdout_evidence_set',
            'maximum_failed_trials',
            'minimum_evaluated_trials',
            'require_complete_evaluation',
            'required_report_schema',
            'schema',
        },
    )
    candidate = _identity(root['candidate'], 'criteria candidate')
    holdout = _identity(root['holdout_evidence_set'], 'criteria holdout')
    report_schema = _mapping(
        root['required_report_schema'], 'required report schema', {'id', 'version'}
    )
    return PromotionCriteria._from_fields(
        candidate_id=candidate['id'],
        candidate_fingerprint=candidate['fingerprint'],
        required_report_schema_id=report_schema['id'],
        required_report_schema_version=report_schema['version'],
        holdout_evidence_set_id=holdout['id'],
        holdout_evidence_set_fingerprint=holdout['fingerprint'],
        accepted_dispositions=tuple(
            _enum(OfflineEvaluationDisposition, item, 'accepted disposition')
            for item in _sequence(root['accepted_dispositions'], 'accepted_dispositions')
        ),
        minimum_evaluated_trials=root['minimum_evaluated_trials'],
        maximum_failed_trials=root['maximum_failed_trials'],
        require_complete_evaluation=root['require_complete_evaluation'],
        allowed_target_stages=tuple(
            _enum(PromotionTargetStage, item, 'allowed target stage')
            for item in _sequence(root['allowed_target_stages'], 'allowed_target_stages')
        ),
    )


def _promotion_request(root: dict[str, object]) -> CandidatePromotionRequest:
    root = _mapping(
        root,
        'promotion request',
        {
            'candidate',
            'criteria',
            'note',
            'provenance',
            'report',
            'request_fingerprint',
            'request_id',
            'schema',
            'target_stage',
        },
    )
    candidate = _identity(root['candidate'], 'request candidate')
    criteria = _identity(root['criteria'], 'request criteria')
    report = _identity(root['report'], 'request report')
    provenance = _mapping(root['provenance'], 'request provenance', {'fingerprint', 'source_ref'})
    return CandidatePromotionRequest._from_fields(
        candidate_id=candidate['id'],
        candidate_fingerprint=candidate['fingerprint'],
        report_id=report['id'],
        report_fingerprint=report['fingerprint'],
        criteria_id=criteria['id'],
        criteria_fingerprint=criteria['fingerprint'],
        target_stage=_enum(PromotionTargetStage, root['target_stage'], 'target_stage'),
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
        note=root['note'],
    )


def _promotion_decision(root: dict[str, object]) -> PromotionDecision:
    root = _mapping(
        root,
        'promotion decision',
        {
            'candidate',
            'criteria',
            'decision_fingerprint',
            'decision_id',
            'reasons',
            'report',
            'request',
            'schema',
            'status',
            'target_stage',
        },
    )
    candidate = _identity(root['candidate'], 'decision candidate')
    criteria = _identity(root['criteria'], 'decision criteria')
    report = _identity(root['report'], 'decision report')
    request = _identity(root['request'], 'decision request')
    return PromotionDecision._create(
        request_id=request['id'],
        request_fingerprint=request['fingerprint'],
        criteria_id=criteria['id'],
        criteria_fingerprint=criteria['fingerprint'],
        candidate_id=candidate['id'],
        candidate_fingerprint=candidate['fingerprint'],
        report_id=report['id'],
        report_fingerprint=report['fingerprint'],
        target_stage=_enum(PromotionTargetStage, root['target_stage'], 'target_stage'),
        status=_enum(PromotionDecisionStatus, root['status'], 'promotion status'),
        reasons=tuple(
            _enum(PromotionDecisionReason, item, 'promotion decision reason')
            for item in _sequence(root['reasons'], 'promotion decision reasons')
        ),
    )


def _rollback_evidence(root: dict[str, object]) -> RollbackEvidenceReference:
    root = _mapping(
        root,
        'rollback evidence',
        {
            'evidence_fingerprint',
            'evidence_id',
            'evidence_kind',
            'schema',
            'source',
        },
    )
    source = _mapping(root['source'], 'evidence source', {'fingerprint', 'source_ref'})
    return RollbackEvidenceReference._from_fields(
        evidence_kind=_enum(RollbackEvidenceKind, root['evidence_kind'], 'evidence_kind'),
        source_ref=source['source_ref'],
        source_fingerprint=source['fingerprint'],
    )


def _known_good(root: dict[str, object]) -> KnownGoodPolicyReference:
    root = _mapping(
        root,
        'known-good policy',
        {
            'known_good_fingerprint',
            'known_good_id',
            'policy_contract',
            'promotion_decision',
            'provenance',
            'schema',
            'target_candidate',
            'target_stage',
        },
    )
    contract = _mapping(root['policy_contract'], 'known-good policy contract', {'family_id', 'input', 'output'})
    input_contract = _mapping(contract['input'], 'known-good input contract', {'id', 'version'})
    output_contract = _mapping(contract['output'], 'known-good output contract', {'id', 'version'})
    decision = _identity(root['promotion_decision'], 'known-good promotion decision')
    provenance = _mapping(root['provenance'], 'known-good provenance', {'fingerprint', 'source_ref'})
    candidate = _mapping(
        root['target_candidate'],
        'known-good target candidate',
        {'evidence_set', 'fingerprint', 'id', 'semantic_version'},
    )
    evidence_set = _identity(candidate['evidence_set'], 'known-good candidate evidence set')
    return KnownGoodPolicyReference._from_fields(
        target_candidate_id=candidate['id'],
        target_candidate_fingerprint=candidate['fingerprint'],
        target_candidate_semantic_version=candidate['semantic_version'],
        target_candidate_evidence_set_id=evidence_set['id'],
        target_candidate_evidence_set_fingerprint=evidence_set['fingerprint'],
        policy_family_id=contract['family_id'],
        input_contract_id=input_contract['id'],
        input_contract_version=input_contract['version'],
        output_contract_id=output_contract['id'],
        output_contract_version=output_contract['version'],
        promotion_decision_id=decision['id'],
        promotion_decision_fingerprint=decision['fingerprint'],
        target_stage=_enum(PromotionTargetStage, root['target_stage'], 'target_stage'),
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
    )


def _rollback_criteria(root: dict[str, object]) -> RollbackCriteria:
    root = _mapping(
        root,
        'rollback criteria',
        {
            'allowed_reasons',
            'criteria_fingerprint',
            'criteria_id',
            'current_candidate',
            'known_good',
            'minimum_evidence_references',
            'schema',
        },
    )
    current = _identity(root['current_candidate'], 'criteria current candidate')
    known_good = _identity(root['known_good'], 'criteria known-good reference')
    return RollbackCriteria._from_fields(
        current_candidate_id=current['id'],
        current_candidate_fingerprint=current['fingerprint'],
        known_good_id=known_good['id'],
        known_good_fingerprint=known_good['fingerprint'],
        allowed_reasons=tuple(
            _enum(RollbackReason, item, 'allowed rollback reason')
            for item in _sequence(root['allowed_reasons'], 'allowed rollback reasons')
        ),
        minimum_evidence_references=root['minimum_evidence_references'],
    )


def _rollback_request(root: dict[str, object]) -> RollbackRequest:
    root = _mapping(
        root,
        'rollback request',
        {
            'criteria',
            'current_candidate',
            'evidence_references',
            'known_good',
            'note',
            'provenance',
            'reason',
            'request_fingerprint',
            'request_id',
            'schema',
        },
    )
    current = _identity(root['current_candidate'], 'request current candidate')
    criteria = _identity(root['criteria'], 'request criteria')
    known_good = _identity(root['known_good'], 'request known-good reference')
    provenance = _mapping(root['provenance'], 'request provenance', {'fingerprint', 'source_ref'})
    references = tuple(
        _rollback_evidence(item)
        for item in _sequence(root['evidence_references'], 'evidence_references')
    )
    return RollbackRequest._from_fields(
        current_candidate_id=current['id'],
        current_candidate_fingerprint=current['fingerprint'],
        known_good_id=known_good['id'],
        known_good_fingerprint=known_good['fingerprint'],
        criteria_id=criteria['id'],
        criteria_fingerprint=criteria['fingerprint'],
        reason=_enum(RollbackReason, root['reason'], 'rollback reason'),
        evidence_references=references,
        provenance_ref=provenance['source_ref'],
        provenance_fingerprint=provenance['fingerprint'],
        note=root['note'],
    )


def _rollback_decision(root: dict[str, object]) -> RollbackDecision:
    root = _mapping(
        root,
        'rollback decision',
        {
            'criteria',
            'current_candidate',
            'decision_fingerprint',
            'decision_id',
            'known_good',
            'reasons',
            'request',
            'schema',
            'status',
            'target_candidate',
        },
    )
    current = _identity(root['current_candidate'], 'decision current candidate')
    target = _identity(root['target_candidate'], 'decision target candidate')
    criteria = _identity(root['criteria'], 'decision criteria')
    known_good = _identity(root['known_good'], 'decision known-good reference')
    request = _identity(root['request'], 'decision request')
    return RollbackDecision._create(
        request_id=request['id'],
        request_fingerprint=request['fingerprint'],
        criteria_id=criteria['id'],
        criteria_fingerprint=criteria['fingerprint'],
        current_candidate_id=current['id'],
        current_candidate_fingerprint=current['fingerprint'],
        target_candidate_id=target['id'],
        target_candidate_fingerprint=target['fingerprint'],
        known_good_id=known_good['id'],
        known_good_fingerprint=known_good['fingerprint'],
        status=_enum(RollbackDecisionStatus, root['status'], 'rollback status'),
        reasons=tuple(
            _enum(RollbackDecisionReason, item, 'rollback decision reason')
            for item in _sequence(root['reasons'], 'rollback decision reasons')
        ),
    )


_PARSERS = {
    PROMOTION_CRITERIA_SCHEMA_ID: (PROMOTION_SCHEMA_VERSION, _promotion_criteria),
    PROMOTION_REQUEST_SCHEMA_ID: (PROMOTION_SCHEMA_VERSION, _promotion_request),
    PROMOTION_DECISION_SCHEMA_ID: (PROMOTION_SCHEMA_VERSION, _promotion_decision),
    ROLLBACK_EVIDENCE_SCHEMA_ID: (ROLLBACK_SCHEMA_VERSION, _rollback_evidence),
    KNOWN_GOOD_POLICY_SCHEMA_ID: (ROLLBACK_SCHEMA_VERSION, _known_good),
    ROLLBACK_CRITERIA_SCHEMA_ID: (ROLLBACK_SCHEMA_VERSION, _rollback_criteria),
    ROLLBACK_REQUEST_SCHEMA_ID: (ROLLBACK_SCHEMA_VERSION, _rollback_request),
    ROLLBACK_DECISION_SCHEMA_ID: (ROLLBACK_SCHEMA_VERSION, _rollback_decision),
}


def control_artifact_from_canonical_json(payload: str | bytes) -> ControlArtifact:
    if isinstance(payload, bytes):
        raw = payload
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise PromotionControlIntegrityError('control JSON is not valid UTF-8') from error
    elif type(payload) is str:
        text = payload
        raw = payload.encode('utf-8')
    else:
        raise PromotionControlIntegrityError('control JSON must be text or bytes')
    if not raw or len(raw) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise PromotionControlIntegrityError('control JSON is empty or exceeds its v1 bound')
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except PromotionControlIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PromotionControlIntegrityError('control JSON is malformed') from error
    if canonical_json(document).encode('utf-8') != raw:
        raise PromotionControlIntegrityError('control JSON is not canonical')
    if type(document) is not dict:
        raise PromotionControlIntegrityError('control JSON root must be an object')
    schema_id, schema_version = _schema(document)
    parser_entry = _PARSERS.get(schema_id)
    if parser_entry is None:
        raise PromotionControlIntegrityError('control schema identity is unsupported')
    expected_version, parser = parser_entry
    if schema_version != expected_version:
        raise PromotionControlIntegrityError('control schema version is unsupported')
    try:
        artifact = parser(document)
    except PromotionControlIntegrityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise PromotionControlIntegrityError(
            'control JSON content violates its v1 contract'
        ) from error
    if artifact.as_dict() != document:
        raise PromotionControlIntegrityError('control artifact identity or content was tampered')
    return artifact
