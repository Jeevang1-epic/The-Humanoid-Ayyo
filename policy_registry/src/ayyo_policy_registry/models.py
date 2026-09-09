"""Immutable candidate-registration, version, snapshot, and update contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_promotion_control import (
    CandidatePromotionRequest,
    PromotionCriteria,
    PromotionDecision,
    PromotionTargetStage,
    evaluate_promotion,
    verify_promotion_criteria,
    verify_promotion_decision,
    verify_promotion_request,
)

from .canonical import (
    MAX_POLICY_FAMILIES,
    MAX_REGISTERED_VERSIONS,
    MAX_SERIALIZED_RECORD_BYTES,
    MAX_SERIALIZED_REQUEST_BYTES,
    MAX_SERIALIZED_RESULT_BYTES,
    MAX_SERIALIZED_SNAPSHOT_BYTES,
    assert_size,
    fingerprint,
    identifier,
    optional_note,
    semantic_sha256,
    semantic_version,
)
from .errors import (
    PolicyRegistryIntegrityError,
    PolicyRegistrySnapshotError,
    RegisteredPolicyVersionError,
    RegistrationRequestError,
)


REGISTRATION_REQUEST_SCHEMA_ID = 'ayyo.policy-registry.registration-request.v1'
REGISTERED_POLICY_VERSION_SCHEMA_ID = 'ayyo.policy-registry.registered-policy-version.v1'
POLICY_REGISTRY_SNAPSHOT_SCHEMA_ID = 'ayyo.policy-registry.snapshot.v1'
REGISTRATION_RESULT_SCHEMA_ID = 'ayyo.policy-registry.registration-result.v1'
POLICY_REGISTRY_SCHEMA_VERSION = '1.0.0'


class RegistrationStatus(StrEnum):
    REGISTERED = 'registered'
    ALREADY_REGISTERED = 'already_registered'


def _set_identity(
    instance: object,
    *,
    prefix: str,
    fingerprint_name: str,
    id_name: str,
    maximum_bytes: int,
    artifact_name: str,
) -> None:
    content_fingerprint = semantic_sha256(f'{prefix}-content', instance.semantic_document())
    object.__setattr__(instance, fingerprint_name, content_fingerprint)
    object.__setattr__(
        instance,
        id_name,
        semantic_sha256(
            prefix,
            {
                'content_fingerprint': content_fingerprint,
                'schema_id': instance.schema_id,
                'schema_version': instance.schema_version,
            },
        ),
    )
    assert_size(instance.as_dict(), maximum_bytes, artifact_name)


def _identity(identifier_value: str, fingerprint_value: str) -> dict[str, str]:
    return {'fingerprint': fingerprint_value, 'id': identifier_value}


@dataclass(frozen=True, slots=True, init=False)
class CandidateRegistrationRequest:
    schema_id: str
    schema_version: str
    registration_request_id: str
    registration_request_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    evaluation_report_id: str
    evaluation_report_fingerprint: str
    promotion_criteria_id: str
    promotion_criteria_fingerprint: str
    promotion_request_id: str
    promotion_request_fingerprint: str
    promotion_decision_id: str
    promotion_decision_fingerprint: str
    target_stage: PromotionTargetStage
    provenance_ref: str
    provenance_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        candidate: object,
        evaluation_report: object,
        promotion_criteria: PromotionCriteria,
        promotion_request: CandidatePromotionRequest,
        promotion_decision: PromotionDecision,
        target_stage: PromotionTargetStage,
        provenance_ref: str,
        provenance_fingerprint: str,
        note: str | None = None,
    ) -> None:
        if not verify_promotion_criteria(promotion_criteria):
            raise RegistrationRequestError('request requires verified promotion criteria')
        if not verify_promotion_request(promotion_request):
            raise RegistrationRequestError('request requires a verified promotion request')
        if not verify_promotion_decision(promotion_decision):
            raise RegistrationRequestError('request requires a verified promotion decision')
        try:
            evaluate_promotion(
                criteria=promotion_criteria,
                request=promotion_request,
                candidate=candidate,
                report=evaluation_report,
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise RegistrationRequestError(
                'request requires verified candidate and evaluation artifacts'
            ) from error
        self._initialize(
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.candidate_fingerprint,
            evaluation_report_id=evaluation_report.report_id,
            evaluation_report_fingerprint=evaluation_report.report_fingerprint,
            promotion_criteria_id=promotion_criteria.criteria_id,
            promotion_criteria_fingerprint=promotion_criteria.criteria_fingerprint,
            promotion_request_id=promotion_request.request_id,
            promotion_request_fingerprint=promotion_request.request_fingerprint,
            promotion_decision_id=promotion_decision.decision_id,
            promotion_decision_fingerprint=promotion_decision.decision_fingerprint,
            target_stage=target_stage,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> CandidateRegistrationRequest:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', REGISTRATION_REQUEST_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', POLICY_REGISTRY_SCHEMA_VERSION)
            for name in (
                'candidate_id',
                'evaluation_report_id',
                'promotion_criteria_id',
                'promotion_request_id',
                'promotion_decision_id',
                'provenance_ref',
            ):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'candidate_fingerprint',
                'evaluation_report_fingerprint',
                'promotion_criteria_fingerprint',
                'promotion_request_fingerprint',
                'promotion_decision_fingerprint',
                'provenance_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            if not isinstance(fields['target_stage'], PromotionTargetStage):
                raise RegistrationRequestError('target_stage must use its closed enum')
            object.__setattr__(self, 'target_stage', fields['target_stage'])
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(
                self,
                prefix='candidate-registration-request',
                fingerprint_name='registration_request_fingerprint',
                id_name='registration_request_id',
                maximum_bytes=MAX_SERIALIZED_REQUEST_BYTES,
                artifact_name='registration request',
            )
        except RegistrationRequestError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RegistrationRequestError(
                'candidate registration request violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'candidate': _identity(self.candidate_id, self.candidate_fingerprint),
            'evaluation_report': _identity(
                self.evaluation_report_id, self.evaluation_report_fingerprint
            ),
            'note': self.note,
            'promotion_criteria': _identity(
                self.promotion_criteria_id, self.promotion_criteria_fingerprint
            ),
            'promotion_decision': _identity(
                self.promotion_decision_id, self.promotion_decision_fingerprint
            ),
            'promotion_request': _identity(
                self.promotion_request_id, self.promotion_request_fingerprint
            ),
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'target_stage': self.target_stage.value,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256(
            'candidate-registration-request-content', self.semantic_document()
        )

    def recompute_registration_request_id(self) -> str:
        return semantic_sha256(
            'candidate-registration-request',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'registration_request_fingerprint': self.registration_request_fingerprint,
            'registration_request_id': self.registration_request_id,
        }


def verify_registration_request(request: object) -> bool:
    if type(request) is not CandidateRegistrationRequest:
        return False
    try:
        rebuilt = CandidateRegistrationRequest._from_fields(
            candidate_id=request.candidate_id,
            candidate_fingerprint=request.candidate_fingerprint,
            evaluation_report_id=request.evaluation_report_id,
            evaluation_report_fingerprint=request.evaluation_report_fingerprint,
            promotion_criteria_id=request.promotion_criteria_id,
            promotion_criteria_fingerprint=request.promotion_criteria_fingerprint,
            promotion_request_id=request.promotion_request_id,
            promotion_request_fingerprint=request.promotion_request_fingerprint,
            promotion_decision_id=request.promotion_decision_id,
            promotion_decision_fingerprint=request.promotion_decision_fingerprint,
            target_stage=request.target_stage,
            provenance_ref=request.provenance_ref,
            provenance_fingerprint=request.provenance_fingerprint,
            note=request.note,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == request


@dataclass(frozen=True, slots=True, init=False)
class RegisteredPolicyVersion:
    schema_id: str
    schema_version: str
    record_id: str
    record_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    semantic_version: str
    policy_family_id: str
    candidate_evidence_set_id: str
    candidate_evidence_set_fingerprint: str
    input_contract_id: str
    input_contract_version: str
    output_contract_id: str
    output_contract_version: str
    parent_candidate_id: str | None
    parent_candidate_fingerprint: str | None
    evaluation_report_id: str
    evaluation_report_fingerprint: str
    evaluation_contract_id: str
    evaluation_contract_version: str
    holdout_evidence_set_id: str
    holdout_evidence_set_fingerprint: str
    promotion_criteria_id: str
    promotion_criteria_fingerprint: str
    promotion_request_id: str
    promotion_request_fingerprint: str
    promotion_decision_id: str
    promotion_decision_fingerprint: str
    target_stage: PromotionTargetStage
    registration_request_id: str
    registration_request_fingerprint: str
    provenance_ref: str
    provenance_fingerprint: str

    @classmethod
    def _from_fields(cls, **fields) -> RegisteredPolicyVersion:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', REGISTERED_POLICY_VERSION_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', POLICY_REGISTRY_SCHEMA_VERSION)
            for name in (
                'candidate_id',
                'policy_family_id',
                'candidate_evidence_set_id',
                'input_contract_id',
                'output_contract_id',
                'evaluation_report_id',
                'evaluation_contract_id',
                'holdout_evidence_set_id',
                'promotion_criteria_id',
                'promotion_request_id',
                'promotion_decision_id',
                'registration_request_id',
                'provenance_ref',
            ):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'candidate_fingerprint',
                'candidate_evidence_set_fingerprint',
                'evaluation_report_fingerprint',
                'holdout_evidence_set_fingerprint',
                'promotion_criteria_fingerprint',
                'promotion_request_fingerprint',
                'promotion_decision_fingerprint',
                'registration_request_fingerprint',
                'provenance_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            for name in (
                'semantic_version',
                'input_contract_version',
                'output_contract_version',
                'evaluation_contract_version',
            ):
                object.__setattr__(self, name, semantic_version(fields[name], name))
            parent_id = fields['parent_candidate_id']
            parent_fingerprint = fields['parent_candidate_fingerprint']
            if (parent_id is None) != (parent_fingerprint is None):
                raise RegisteredPolicyVersionError(
                    'parent candidate ID and fingerprint must be supplied together'
                )
            if parent_id is not None:
                parent_id = identifier(parent_id, 'parent_candidate_id')
                parent_fingerprint = fingerprint(
                    parent_fingerprint, 'parent_candidate_fingerprint'
                )
                if (parent_id, parent_fingerprint) == (
                    fields['candidate_id'],
                    fields['candidate_fingerprint'],
                ):
                    raise RegisteredPolicyVersionError('a policy version cannot parent itself')
            object.__setattr__(self, 'parent_candidate_id', parent_id)
            object.__setattr__(self, 'parent_candidate_fingerprint', parent_fingerprint)
            if not isinstance(fields['target_stage'], PromotionTargetStage):
                raise RegisteredPolicyVersionError('target_stage must use its closed enum')
            object.__setattr__(self, 'target_stage', fields['target_stage'])
            _set_identity(
                self,
                prefix='registered-policy-version',
                fingerprint_name='record_fingerprint',
                id_name='record_id',
                maximum_bytes=MAX_SERIALIZED_RECORD_BYTES,
                artifact_name='registered policy version',
            )
        except RegisteredPolicyVersionError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RegisteredPolicyVersionError(
                'registered policy version violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'candidate': {
                'evidence_set': _identity(
                    self.candidate_evidence_set_id,
                    self.candidate_evidence_set_fingerprint,
                ),
                'fingerprint': self.candidate_fingerprint,
                'id': self.candidate_id,
                'parent': (
                    _identity(
                        self.parent_candidate_id,
                        self.parent_candidate_fingerprint,
                    )
                    if self.parent_candidate_id is not None
                    else None
                ),
                'semantic_version': self.semantic_version,
            },
            'evaluation': {
                'contract': {
                    'id': self.evaluation_contract_id,
                    'version': self.evaluation_contract_version,
                },
                'holdout_evidence_set': _identity(
                    self.holdout_evidence_set_id,
                    self.holdout_evidence_set_fingerprint,
                ),
                'report': _identity(
                    self.evaluation_report_id,
                    self.evaluation_report_fingerprint,
                ),
            },
            'policy_contract': {
                'family_id': self.policy_family_id,
                'input': {
                    'id': self.input_contract_id,
                    'version': self.input_contract_version,
                },
                'output': {
                    'id': self.output_contract_id,
                    'version': self.output_contract_version,
                },
            },
            'promotion': {
                'criteria': _identity(
                    self.promotion_criteria_id, self.promotion_criteria_fingerprint
                ),
                'decision': _identity(
                    self.promotion_decision_id, self.promotion_decision_fingerprint
                ),
                'request': _identity(
                    self.promotion_request_id, self.promotion_request_fingerprint
                ),
                'target_stage': self.target_stage.value,
            },
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'registration_request': _identity(
                self.registration_request_id, self.registration_request_fingerprint
            ),
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('registered-policy-version-content', self.semantic_document())

    def recompute_record_id(self) -> str:
        return semantic_sha256(
            'registered-policy-version',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'record_fingerprint': self.record_fingerprint,
            'record_id': self.record_id,
        }


def verify_registered_policy_version(record: object) -> bool:
    if type(record) is not RegisteredPolicyVersion:
        return False
    try:
        rebuilt = RegisteredPolicyVersion._from_fields(
            **{
                name: getattr(record, name)
                for name in RegisteredPolicyVersion.__annotations__
                if name not in {'schema_id', 'schema_version', 'record_id', 'record_fingerprint'}
            }
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == record


def _validate_snapshot_versions(versions: object) -> tuple[RegisteredPolicyVersion, ...]:
    if isinstance(versions, (str, bytes)):
        raise PolicyRegistrySnapshotError('registered_versions must be a bounded sequence')
    try:
        snapshot = tuple(versions)
    except TypeError as error:
        raise PolicyRegistrySnapshotError(
            'registered_versions must be a bounded sequence'
        ) from error
    if len(snapshot) > MAX_REGISTERED_VERSIONS:
        raise PolicyRegistrySnapshotError('registered version count exceeds its v1 bound')
    if not all(type(item) is RegisteredPolicyVersion for item in snapshot):
        raise PolicyRegistrySnapshotError('snapshot accepts only registered policy versions')
    if not all(verify_registered_policy_version(item) for item in snapshot):
        raise PolicyRegistrySnapshotError('a registered version failed integrity verification')
    record_ids = [item.record_id for item in snapshot]
    candidate_ids = [item.candidate_id for item in snapshot]
    version_keys = [(item.policy_family_id, item.semantic_version) for item in snapshot]
    if len(record_ids) != len(set(record_ids)):
        raise PolicyRegistrySnapshotError('duplicate registry record identity')
    if len(candidate_ids) != len(set(candidate_ids)):
        raise PolicyRegistrySnapshotError('duplicate candidate identity')
    if len(version_keys) != len(set(version_keys)):
        raise PolicyRegistrySnapshotError('conflicting semantic version within policy family')
    if len({item.policy_family_id for item in snapshot}) > MAX_POLICY_FAMILIES:
        raise PolicyRegistrySnapshotError('policy-family count exceeds its v1 bound')

    by_candidate = {
        (item.candidate_id, item.candidate_fingerprint): item for item in snapshot
    }
    parent_of: dict[tuple[str, str], tuple[str, str] | None] = {}
    for item in snapshot:
        key = (item.candidate_id, item.candidate_fingerprint)
        if item.parent_candidate_id is None:
            parent_of[key] = None
            continue
        parent_key = (item.parent_candidate_id, item.parent_candidate_fingerprint)
        parent = by_candidate.get(parent_key)
        if parent is None:
            raise PolicyRegistrySnapshotError(
                'parent candidate is not present with its exact identity'
            )
        if parent.policy_family_id != item.policy_family_id:
            raise PolicyRegistrySnapshotError('parent belongs to a different policy family')
        if (
            parent.input_contract_id,
            parent.input_contract_version,
            parent.output_contract_id,
            parent.output_contract_version,
        ) != (
            item.input_contract_id,
            item.input_contract_version,
            item.output_contract_id,
            item.output_contract_version,
        ):
            raise PolicyRegistrySnapshotError('parent uses incompatible policy contracts')
        parent_of[key] = parent_key

    for start in parent_of:
        seen = set()
        current: tuple[str, str] | None = start
        while current is not None:
            if current in seen:
                raise PolicyRegistrySnapshotError('candidate lineage contains a cycle')
            seen.add(current)
            current = parent_of[current]
    return tuple(sorted(snapshot, key=lambda item: (item.policy_family_id, item.record_id)))


@dataclass(frozen=True, slots=True, init=False)
class PolicyRegistrySnapshot:
    schema_id: str
    schema_version: str
    snapshot_id: str
    snapshot_fingerprint: str
    registered_versions: tuple[RegisteredPolicyVersion, ...]

    def __init__(self, registered_versions: object = ()) -> None:
        self._initialize(registered_versions=registered_versions)

    @classmethod
    def _from_fields(cls, **fields) -> PolicyRegistrySnapshot:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, *, registered_versions: object) -> None:
        object.__setattr__(self, 'schema_id', POLICY_REGISTRY_SNAPSHOT_SCHEMA_ID)
        object.__setattr__(self, 'schema_version', POLICY_REGISTRY_SCHEMA_VERSION)
        object.__setattr__(
            self,
            'registered_versions',
            _validate_snapshot_versions(registered_versions),
        )
        _set_identity(
            self,
            prefix='policy-registry-snapshot',
            fingerprint_name='snapshot_fingerprint',
            id_name='snapshot_id',
            maximum_bytes=MAX_SERIALIZED_SNAPSHOT_BYTES,
            artifact_name='policy registry snapshot',
        )

    def semantic_document(self) -> dict[str, object]:
        return {
            'registered_versions': [item.as_dict() for item in self.registered_versions],
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('policy-registry-snapshot-content', self.semantic_document())

    def recompute_snapshot_id(self) -> str:
        return semantic_sha256(
            'policy-registry-snapshot',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'snapshot_fingerprint': self.snapshot_fingerprint,
            'snapshot_id': self.snapshot_id,
        }


def verify_policy_registry_snapshot(snapshot: object) -> bool:
    if type(snapshot) is not PolicyRegistrySnapshot:
        return False
    try:
        rebuilt = PolicyRegistrySnapshot(snapshot.registered_versions)
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == snapshot


@dataclass(frozen=True, slots=True, init=False)
class RegistrationResult:
    schema_id: str
    schema_version: str
    result_id: str
    result_fingerprint: str
    status: RegistrationStatus
    registration_request_id: str
    registration_request_fingerprint: str
    registered_version: RegisteredPolicyVersion
    previous_snapshot: PolicyRegistrySnapshot
    updated_snapshot: PolicyRegistrySnapshot

    @classmethod
    def _from_fields(cls, **fields) -> RegistrationResult:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', REGISTRATION_RESULT_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', POLICY_REGISTRY_SCHEMA_VERSION)
            if not isinstance(fields['status'], RegistrationStatus):
                raise PolicyRegistryIntegrityError('registration status must use its closed enum')
            object.__setattr__(self, 'status', fields['status'])
            object.__setattr__(
                self,
                'registration_request_id',
                identifier(fields['registration_request_id'], 'registration_request_id'),
            )
            object.__setattr__(
                self,
                'registration_request_fingerprint',
                fingerprint(
                    fields['registration_request_fingerprint'],
                    'registration_request_fingerprint',
                ),
            )
            record = fields['registered_version']
            previous = fields['previous_snapshot']
            updated = fields['updated_snapshot']
            if not verify_registered_policy_version(record):
                raise PolicyRegistryIntegrityError(
                    'registration result requires a verified registered version'
                )
            if not verify_policy_registry_snapshot(previous) or not verify_policy_registry_snapshot(
                updated
            ):
                raise PolicyRegistryIntegrityError(
                    'registration result requires verified registry snapshots'
                )
            previous_records = previous.registered_versions
            updated_records = updated.registered_versions
            if fields['status'] is RegistrationStatus.REGISTERED:
                if (
                    record in previous_records
                    or len(updated_records) != len(previous_records) + 1
                    or set(updated_records) != set(previous_records) | {record}
                ):
                    raise PolicyRegistryIntegrityError(
                        'registered result must add exactly its bound record'
                    )
            elif previous != updated or record not in updated_records:
                raise PolicyRegistryIntegrityError(
                    'already-registered result must preserve its exact snapshot'
                )
            object.__setattr__(self, 'registered_version', record)
            object.__setattr__(self, 'previous_snapshot', previous)
            object.__setattr__(self, 'updated_snapshot', updated)
            _set_identity(
                self,
                prefix='registration-result',
                fingerprint_name='result_fingerprint',
                id_name='result_id',
                maximum_bytes=MAX_SERIALIZED_RESULT_BYTES,
                artifact_name='registration result',
            )
        except PolicyRegistryIntegrityError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise PolicyRegistryIntegrityError(
                'registration result violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'previous_snapshot': self.previous_snapshot.as_dict(),
            'registered_version': self.registered_version.as_dict(),
            'registration_request': _identity(
                self.registration_request_id, self.registration_request_fingerprint
            ),
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'status': self.status.value,
            'updated_snapshot': self.updated_snapshot.as_dict(),
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('registration-result-content', self.semantic_document())

    def recompute_result_id(self) -> str:
        return semantic_sha256(
            'registration-result',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'result_fingerprint': self.result_fingerprint,
            'result_id': self.result_id,
        }


def verify_registration_result(result: object) -> bool:
    if type(result) is not RegistrationResult:
        return False
    try:
        rebuilt = RegistrationResult._from_fields(
            status=result.status,
            registration_request_id=result.registration_request_id,
            registration_request_fingerprint=result.registration_request_fingerprint,
            registered_version=result.registered_version,
            previous_snapshot=result.previous_snapshot,
            updated_snapshot=result.updated_snapshot,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == result
