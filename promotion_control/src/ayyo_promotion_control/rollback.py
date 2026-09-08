"""Pure rollback eligibility over explicit known-good and regression evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_learning_evaluation import CandidatePolicyManifest, verify_candidate_policy

from .canonical import (
    assert_size,
    bounded_enum_tuple,
    fingerprint,
    identifier,
    optional_note,
    semantic_sha256,
    semantic_version,
)
from .errors import RollbackControlError
from .promotion import (
    PromotionDecision,
    PromotionDecisionStatus,
    PromotionTargetStage,
    verify_promotion_decision,
)


ROLLBACK_EVIDENCE_SCHEMA_ID = 'ayyo.promotion-control.rollback-evidence-reference.v1'
KNOWN_GOOD_POLICY_SCHEMA_ID = 'ayyo.promotion-control.known-good-policy.v1'
ROLLBACK_CRITERIA_SCHEMA_ID = 'ayyo.promotion-control.rollback-criteria.v1'
ROLLBACK_REQUEST_SCHEMA_ID = 'ayyo.promotion-control.rollback-request.v1'
ROLLBACK_DECISION_SCHEMA_ID = 'ayyo.promotion-control.rollback-decision.v1'
ROLLBACK_SCHEMA_VERSION = '1.0.0'
MAX_ROLLBACK_EVIDENCE_REFERENCES = 8


class RollbackReason(StrEnum):
    EVALUATION_REGRESSION = 'evaluation_regression'
    SAFETY_REGRESSION = 'safety_regression'
    RUNTIME_REGRESSION = 'runtime_regression'
    OPERATOR_REQUEST = 'operator_request'
    INTEGRITY_FAILURE = 'integrity_failure'


class RollbackEvidenceKind(StrEnum):
    EVALUATION_REPORT = 'evaluation_report'
    SAFETY_REVIEW = 'safety_review'
    RUNTIME_OBSERVATION = 'runtime_observation'
    OPERATOR_INSTRUCTION = 'operator_instruction'
    INTEGRITY_REPORT = 'integrity_report'


class RollbackDecisionStatus(StrEnum):
    ROLLBACK_ELIGIBLE = 'rollback_eligible'
    ROLLBACK_REJECTED = 'rollback_rejected'


class RollbackDecisionReason(StrEnum):
    ROLLBACK_CRITERIA_SATISFIED = 'rollback_criteria_satisfied'
    REQUEST_CRITERIA_MISMATCH = 'request_criteria_mismatch'
    REQUEST_CURRENT_CANDIDATE_MISMATCH = 'request_current_candidate_mismatch'
    REQUEST_KNOWN_GOOD_MISMATCH = 'request_known_good_mismatch'
    CRITERIA_CURRENT_CANDIDATE_MISMATCH = 'criteria_current_candidate_mismatch'
    CRITERIA_KNOWN_GOOD_MISMATCH = 'criteria_known_good_mismatch'
    KNOWN_GOOD_TARGET_MISMATCH = 'known_good_target_mismatch'
    PROMOTION_DECISION_MISMATCH = 'promotion_decision_mismatch'
    SELF_ROLLBACK = 'self_rollback'
    TARGET_LINEAGE_MISMATCH = 'target_lineage_mismatch'
    REASON_NOT_ALLOWED = 'reason_not_allowed'
    INSUFFICIENT_REASON_EVIDENCE = 'insufficient_reason_evidence'
    EVIDENCE_KIND_MISMATCH = 'evidence_kind_mismatch'


_REQUIRED_EVIDENCE_KIND = {
    RollbackReason.EVALUATION_REGRESSION: RollbackEvidenceKind.EVALUATION_REPORT,
    RollbackReason.SAFETY_REGRESSION: RollbackEvidenceKind.SAFETY_REVIEW,
    RollbackReason.RUNTIME_REGRESSION: RollbackEvidenceKind.RUNTIME_OBSERVATION,
    RollbackReason.OPERATOR_REQUEST: RollbackEvidenceKind.OPERATOR_INSTRUCTION,
    RollbackReason.INTEGRITY_FAILURE: RollbackEvidenceKind.INTEGRITY_REPORT,
}


def _set_identity(instance: object, prefix: str, fingerprint_name: str, id_name: str) -> None:
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
    assert_size(instance.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class RollbackEvidenceReference:
    schema_id: str
    schema_version: str
    evidence_id: str
    evidence_fingerprint: str
    evidence_kind: RollbackEvidenceKind
    source_ref: str
    source_fingerprint: str

    def __init__(
        self,
        *,
        evidence_kind: RollbackEvidenceKind,
        source_ref: str,
        source_fingerprint: str,
    ) -> None:
        self._initialize(
            evidence_kind=evidence_kind,
            source_ref=source_ref,
            source_fingerprint=source_fingerprint,
        )

    @classmethod
    def _from_fields(cls, **fields) -> RollbackEvidenceReference:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', ROLLBACK_EVIDENCE_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', ROLLBACK_SCHEMA_VERSION)
            if not isinstance(fields['evidence_kind'], RollbackEvidenceKind):
                raise RollbackControlError('evidence_kind must use its closed enum')
            object.__setattr__(self, 'evidence_kind', fields['evidence_kind'])
            object.__setattr__(self, 'source_ref', identifier(fields['source_ref'], 'source_ref'))
            object.__setattr__(
                self,
                'source_fingerprint',
                fingerprint(fields['source_fingerprint'], 'source_fingerprint'),
            )
            _set_identity(self, 'rollback-evidence', 'evidence_fingerprint', 'evidence_id')
        except RollbackControlError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RollbackControlError('rollback evidence violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'evidence_kind': self.evidence_kind.value,
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'source': {
                'fingerprint': self.source_fingerprint,
                'source_ref': self.source_ref,
            },
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('rollback-evidence-content', self.semantic_document())

    def recompute_evidence_id(self) -> str:
        return semantic_sha256(
            'rollback-evidence',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'evidence_fingerprint': self.evidence_fingerprint,
            'evidence_id': self.evidence_id,
        }


def verify_rollback_evidence(reference: object) -> bool:
    if type(reference) is not RollbackEvidenceReference:
        return False
    try:
        rebuilt = RollbackEvidenceReference._from_fields(
            evidence_kind=reference.evidence_kind,
            source_ref=reference.source_ref,
            source_fingerprint=reference.source_fingerprint,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == reference


@dataclass(frozen=True, slots=True, init=False)
class KnownGoodPolicyReference:
    schema_id: str
    schema_version: str
    known_good_id: str
    known_good_fingerprint: str
    target_candidate_id: str
    target_candidate_fingerprint: str
    target_candidate_semantic_version: str
    target_candidate_evidence_set_id: str
    target_candidate_evidence_set_fingerprint: str
    policy_family_id: str
    input_contract_id: str
    input_contract_version: str
    output_contract_id: str
    output_contract_version: str
    promotion_decision_id: str
    promotion_decision_fingerprint: str
    target_stage: PromotionTargetStage
    provenance_ref: str
    provenance_fingerprint: str

    def __init__(
        self,
        *,
        target_candidate: CandidatePolicyManifest,
        promotion_decision: PromotionDecision,
        provenance_ref: str,
        provenance_fingerprint: str,
    ) -> None:
        if not verify_candidate_policy(target_candidate):
            raise RollbackControlError('known-good reference requires a verified candidate')
        if not verify_promotion_decision(promotion_decision):
            raise RollbackControlError('known-good reference requires a verified decision')
        if promotion_decision.status is not PromotionDecisionStatus.ELIGIBLE:
            raise RollbackControlError('known-good reference requires an eligible decision')
        if (promotion_decision.candidate_id, promotion_decision.candidate_fingerprint) != (
            target_candidate.candidate_id,
            target_candidate.candidate_fingerprint,
        ):
            raise RollbackControlError('promotion decision belongs to another candidate')
        self._initialize(
            target_candidate_id=target_candidate.candidate_id,
            target_candidate_fingerprint=target_candidate.candidate_fingerprint,
            target_candidate_semantic_version=target_candidate.semantic_version,
            target_candidate_evidence_set_id=target_candidate.candidate_evidence_set_id,
            target_candidate_evidence_set_fingerprint=(
                target_candidate.candidate_evidence_set_fingerprint
            ),
            policy_family_id=target_candidate.policy_family_id,
            input_contract_id=target_candidate.input_contract_id,
            input_contract_version=target_candidate.input_contract_version,
            output_contract_id=target_candidate.output_contract_id,
            output_contract_version=target_candidate.output_contract_version,
            promotion_decision_id=promotion_decision.decision_id,
            promotion_decision_fingerprint=promotion_decision.decision_fingerprint,
            target_stage=promotion_decision.target_stage,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
        )

    @classmethod
    def _from_fields(cls, **fields) -> KnownGoodPolicyReference:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', KNOWN_GOOD_POLICY_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', ROLLBACK_SCHEMA_VERSION)
            for name in (
                'target_candidate_id',
                'target_candidate_evidence_set_id',
                'policy_family_id',
                'input_contract_id',
                'output_contract_id',
                'promotion_decision_id',
                'provenance_ref',
            ):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'target_candidate_fingerprint',
                'target_candidate_evidence_set_fingerprint',
                'promotion_decision_fingerprint',
                'provenance_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            for name in (
                'target_candidate_semantic_version',
                'input_contract_version',
                'output_contract_version',
            ):
                object.__setattr__(self, name, semantic_version(fields[name], name))
            if not isinstance(fields['target_stage'], PromotionTargetStage):
                raise RollbackControlError('target_stage must use its closed enum')
            object.__setattr__(self, 'target_stage', fields['target_stage'])
            _set_identity(self, 'known-good-policy', 'known_good_fingerprint', 'known_good_id')
        except RollbackControlError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RollbackControlError('known-good reference violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'policy_contract': {
                'family_id': self.policy_family_id,
                'input': {'id': self.input_contract_id, 'version': self.input_contract_version},
                'output': {
                    'id': self.output_contract_id,
                    'version': self.output_contract_version,
                },
            },
            'promotion_decision': {
                'fingerprint': self.promotion_decision_fingerprint,
                'id': self.promotion_decision_id,
            },
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'target_candidate': {
                'evidence_set': {
                    'fingerprint': self.target_candidate_evidence_set_fingerprint,
                    'id': self.target_candidate_evidence_set_id,
                },
                'fingerprint': self.target_candidate_fingerprint,
                'id': self.target_candidate_id,
                'semantic_version': self.target_candidate_semantic_version,
            },
            'target_stage': self.target_stage.value,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('known-good-policy-content', self.semantic_document())

    def recompute_known_good_id(self) -> str:
        return semantic_sha256(
            'known-good-policy',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'known_good_fingerprint': self.known_good_fingerprint,
            'known_good_id': self.known_good_id,
        }


def verify_known_good_policy(reference: object) -> bool:
    if type(reference) is not KnownGoodPolicyReference:
        return False
    try:
        rebuilt = KnownGoodPolicyReference._from_fields(
            target_candidate_id=reference.target_candidate_id,
            target_candidate_fingerprint=reference.target_candidate_fingerprint,
            target_candidate_semantic_version=reference.target_candidate_semantic_version,
            target_candidate_evidence_set_id=reference.target_candidate_evidence_set_id,
            target_candidate_evidence_set_fingerprint=(
                reference.target_candidate_evidence_set_fingerprint
            ),
            policy_family_id=reference.policy_family_id,
            input_contract_id=reference.input_contract_id,
            input_contract_version=reference.input_contract_version,
            output_contract_id=reference.output_contract_id,
            output_contract_version=reference.output_contract_version,
            promotion_decision_id=reference.promotion_decision_id,
            promotion_decision_fingerprint=reference.promotion_decision_fingerprint,
            target_stage=reference.target_stage,
            provenance_ref=reference.provenance_ref,
            provenance_fingerprint=reference.provenance_fingerprint,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == reference


@dataclass(frozen=True, slots=True, init=False)
class RollbackCriteria:
    schema_id: str
    schema_version: str
    criteria_id: str
    criteria_fingerprint: str
    current_candidate_id: str
    current_candidate_fingerprint: str
    known_good_id: str
    known_good_fingerprint: str
    allowed_reasons: tuple[RollbackReason, ...]
    minimum_evidence_references: int

    def __init__(
        self,
        *,
        current_candidate_id: str,
        current_candidate_fingerprint: str,
        known_good_id: str,
        known_good_fingerprint: str,
        allowed_reasons: tuple[RollbackReason, ...] | list[RollbackReason],
        minimum_evidence_references: int,
    ) -> None:
        self._initialize(
            current_candidate_id=current_candidate_id,
            current_candidate_fingerprint=current_candidate_fingerprint,
            known_good_id=known_good_id,
            known_good_fingerprint=known_good_fingerprint,
            allowed_reasons=allowed_reasons,
            minimum_evidence_references=minimum_evidence_references,
        )

    @classmethod
    def _from_fields(cls, **fields) -> RollbackCriteria:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', ROLLBACK_CRITERIA_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', ROLLBACK_SCHEMA_VERSION)
            object.__setattr__(
                self,
                'current_candidate_id',
                identifier(fields['current_candidate_id'], 'current_candidate_id'),
            )
            object.__setattr__(
                self,
                'current_candidate_fingerprint',
                fingerprint(
                    fields['current_candidate_fingerprint'],
                    'current_candidate_fingerprint',
                ),
            )
            object.__setattr__(
                self, 'known_good_id', identifier(fields['known_good_id'], 'known_good_id')
            )
            object.__setattr__(
                self,
                'known_good_fingerprint',
                fingerprint(fields['known_good_fingerprint'], 'known_good_fingerprint'),
            )
            object.__setattr__(
                self,
                'allowed_reasons',
                bounded_enum_tuple(fields['allowed_reasons'], RollbackReason, 'allowed_reasons'),
            )
            minimum = fields['minimum_evidence_references']
            if (
                type(minimum) is not int
                or not 1 <= minimum <= MAX_ROLLBACK_EVIDENCE_REFERENCES
            ):
                raise RollbackControlError('minimum_evidence_references is outside v1 bounds')
            object.__setattr__(self, 'minimum_evidence_references', minimum)
            _set_identity(self, 'rollback-criteria', 'criteria_fingerprint', 'criteria_id')
        except RollbackControlError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RollbackControlError('rollback criteria violate the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'allowed_reasons': [item.value for item in self.allowed_reasons],
            'current_candidate': {
                'fingerprint': self.current_candidate_fingerprint,
                'id': self.current_candidate_id,
            },
            'known_good': {
                'fingerprint': self.known_good_fingerprint,
                'id': self.known_good_id,
            },
            'minimum_evidence_references': self.minimum_evidence_references,
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('rollback-criteria-content', self.semantic_document())

    def recompute_criteria_id(self) -> str:
        return semantic_sha256(
            'rollback-criteria',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'criteria_fingerprint': self.criteria_fingerprint,
            'criteria_id': self.criteria_id,
        }


def verify_rollback_criteria(criteria: object) -> bool:
    if type(criteria) is not RollbackCriteria:
        return False
    try:
        rebuilt = RollbackCriteria._from_fields(
            current_candidate_id=criteria.current_candidate_id,
            current_candidate_fingerprint=criteria.current_candidate_fingerprint,
            known_good_id=criteria.known_good_id,
            known_good_fingerprint=criteria.known_good_fingerprint,
            allowed_reasons=criteria.allowed_reasons,
            minimum_evidence_references=criteria.minimum_evidence_references,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == criteria


@dataclass(frozen=True, slots=True, init=False)
class RollbackRequest:
    schema_id: str
    schema_version: str
    request_id: str
    request_fingerprint: str
    current_candidate_id: str
    current_candidate_fingerprint: str
    known_good_id: str
    known_good_fingerprint: str
    criteria_id: str
    criteria_fingerprint: str
    reason: RollbackReason
    evidence_references: tuple[RollbackEvidenceReference, ...]
    provenance_ref: str
    provenance_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        current_candidate: CandidatePolicyManifest,
        known_good: KnownGoodPolicyReference,
        criteria: RollbackCriteria,
        reason: RollbackReason,
        evidence_references: tuple[RollbackEvidenceReference, ...]
        | list[RollbackEvidenceReference],
        provenance_ref: str,
        provenance_fingerprint: str,
        note: str | None = None,
    ) -> None:
        if not verify_candidate_policy(current_candidate):
            raise RollbackControlError('rollback request requires a verified current candidate')
        if not verify_known_good_policy(known_good):
            raise RollbackControlError('rollback request requires a verified known-good reference')
        if not verify_rollback_criteria(criteria):
            raise RollbackControlError('rollback request requires verified criteria')
        self._initialize(
            current_candidate_id=current_candidate.candidate_id,
            current_candidate_fingerprint=current_candidate.candidate_fingerprint,
            known_good_id=known_good.known_good_id,
            known_good_fingerprint=known_good.known_good_fingerprint,
            criteria_id=criteria.criteria_id,
            criteria_fingerprint=criteria.criteria_fingerprint,
            reason=reason,
            evidence_references=evidence_references,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> RollbackRequest:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', ROLLBACK_REQUEST_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', ROLLBACK_SCHEMA_VERSION)
            for name in (
                'current_candidate_id',
                'known_good_id',
                'criteria_id',
                'provenance_ref',
            ):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'current_candidate_fingerprint',
                'known_good_fingerprint',
                'criteria_fingerprint',
                'provenance_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            if not isinstance(fields['reason'], RollbackReason):
                raise RollbackControlError('rollback reason must use its closed enum')
            object.__setattr__(self, 'reason', fields['reason'])
            references = fields['evidence_references']
            if isinstance(references, (str, bytes)):
                raise RollbackControlError('evidence_references must be a bounded sequence')
            try:
                references = tuple(references)
            except TypeError as error:
                raise RollbackControlError(
                    'evidence_references must be a bounded sequence'
                ) from error
            if (
                not 1 <= len(references) <= MAX_ROLLBACK_EVIDENCE_REFERENCES
                or not all(verify_rollback_evidence(item) for item in references)
                or len({item.evidence_id for item in references}) != len(references)
            ):
                raise RollbackControlError(
                    'evidence_references are invalid, duplicate, or out of bounds'
                )
            object.__setattr__(
                self,
                'evidence_references',
                tuple(sorted(references, key=lambda item: item.evidence_id)),
            )
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(self, 'rollback-request', 'request_fingerprint', 'request_id')
        except RollbackControlError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RollbackControlError('rollback request violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'criteria': {'fingerprint': self.criteria_fingerprint, 'id': self.criteria_id},
            'current_candidate': {
                'fingerprint': self.current_candidate_fingerprint,
                'id': self.current_candidate_id,
            },
            'evidence_references': [item.as_dict() for item in self.evidence_references],
            'known_good': {
                'fingerprint': self.known_good_fingerprint,
                'id': self.known_good_id,
            },
            'note': self.note,
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'reason': self.reason.value,
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('rollback-request-content', self.semantic_document())

    def recompute_request_id(self) -> str:
        return semantic_sha256(
            'rollback-request',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'request_fingerprint': self.request_fingerprint,
            'request_id': self.request_id,
        }


def verify_rollback_request(request: object) -> bool:
    if type(request) is not RollbackRequest:
        return False
    try:
        rebuilt = RollbackRequest._from_fields(
            current_candidate_id=request.current_candidate_id,
            current_candidate_fingerprint=request.current_candidate_fingerprint,
            known_good_id=request.known_good_id,
            known_good_fingerprint=request.known_good_fingerprint,
            criteria_id=request.criteria_id,
            criteria_fingerprint=request.criteria_fingerprint,
            reason=request.reason,
            evidence_references=request.evidence_references,
            provenance_ref=request.provenance_ref,
            provenance_fingerprint=request.provenance_fingerprint,
            note=request.note,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == request


@dataclass(frozen=True, slots=True, init=False)
class RollbackDecision:
    schema_id: str
    schema_version: str
    decision_id: str
    decision_fingerprint: str
    request_id: str
    request_fingerprint: str
    criteria_id: str
    criteria_fingerprint: str
    current_candidate_id: str
    current_candidate_fingerprint: str
    target_candidate_id: str
    target_candidate_fingerprint: str
    known_good_id: str
    known_good_fingerprint: str
    status: RollbackDecisionStatus
    reasons: tuple[RollbackDecisionReason, ...]

    @classmethod
    def _create(cls, **fields) -> RollbackDecision:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', ROLLBACK_DECISION_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', ROLLBACK_SCHEMA_VERSION)
            for name in (
                'request_id',
                'criteria_id',
                'current_candidate_id',
                'target_candidate_id',
                'known_good_id',
            ):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'request_fingerprint',
                'criteria_fingerprint',
                'current_candidate_fingerprint',
                'target_candidate_fingerprint',
                'known_good_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            if not isinstance(fields['status'], RollbackDecisionStatus):
                raise RollbackControlError('rollback decision status must use its closed enum')
            reasons = bounded_enum_tuple(
                fields['reasons'], RollbackDecisionReason, 'rollback decision reasons'
            )
            if fields['status'] is RollbackDecisionStatus.ROLLBACK_ELIGIBLE:
                if reasons != (RollbackDecisionReason.ROLLBACK_CRITERIA_SATISFIED,):
                    raise RollbackControlError(
                        'rollback-eligible decision requires only criteria_satisfied'
                    )
            elif RollbackDecisionReason.ROLLBACK_CRITERIA_SATISFIED in reasons:
                raise RollbackControlError(
                    'rollback-rejected decision cannot claim criteria_satisfied'
                )
            object.__setattr__(self, 'status', fields['status'])
            object.__setattr__(self, 'reasons', reasons)
            _set_identity(self, 'rollback-decision', 'decision_fingerprint', 'decision_id')
        except RollbackControlError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise RollbackControlError('rollback decision violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'criteria': {'fingerprint': self.criteria_fingerprint, 'id': self.criteria_id},
            'current_candidate': {
                'fingerprint': self.current_candidate_fingerprint,
                'id': self.current_candidate_id,
            },
            'known_good': {
                'fingerprint': self.known_good_fingerprint,
                'id': self.known_good_id,
            },
            'reasons': [item.value for item in self.reasons],
            'request': {'fingerprint': self.request_fingerprint, 'id': self.request_id},
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'status': self.status.value,
            'target_candidate': {
                'fingerprint': self.target_candidate_fingerprint,
                'id': self.target_candidate_id,
            },
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('rollback-decision-content', self.semantic_document())

    def recompute_decision_id(self) -> str:
        return semantic_sha256(
            'rollback-decision',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'decision_fingerprint': self.decision_fingerprint,
            'decision_id': self.decision_id,
        }


def verify_rollback_decision(decision: object) -> bool:
    if type(decision) is not RollbackDecision:
        return False
    try:
        rebuilt = RollbackDecision._create(
            request_id=decision.request_id,
            request_fingerprint=decision.request_fingerprint,
            criteria_id=decision.criteria_id,
            criteria_fingerprint=decision.criteria_fingerprint,
            current_candidate_id=decision.current_candidate_id,
            current_candidate_fingerprint=decision.current_candidate_fingerprint,
            target_candidate_id=decision.target_candidate_id,
            target_candidate_fingerprint=decision.target_candidate_fingerprint,
            known_good_id=decision.known_good_id,
            known_good_fingerprint=decision.known_good_fingerprint,
            status=decision.status,
            reasons=decision.reasons,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == decision


def evaluate_rollback(
    *,
    criteria: RollbackCriteria,
    request: RollbackRequest,
    current_candidate: CandidatePolicyManifest,
    target_candidate: CandidatePolicyManifest,
    known_good: KnownGoodPolicyReference,
    promotion_decision: PromotionDecision,
) -> RollbackDecision:
    """Evaluate rollback evidence only; this never mutates a policy or runtime."""
    if not verify_rollback_criteria(criteria):
        raise RollbackControlError('rollback criteria failed integrity verification')
    if not verify_rollback_request(request):
        raise RollbackControlError('rollback request failed integrity verification')
    if not verify_candidate_policy(current_candidate):
        raise RollbackControlError('current candidate failed integrity verification')
    if not verify_candidate_policy(target_candidate):
        raise RollbackControlError('target candidate failed integrity verification')
    if not verify_known_good_policy(known_good):
        raise RollbackControlError('known-good reference failed integrity verification')
    if not verify_promotion_decision(promotion_decision):
        raise RollbackControlError('promotion decision failed integrity verification')

    reasons: list[RollbackDecisionReason] = []
    if (request.criteria_id, request.criteria_fingerprint) != (
        criteria.criteria_id,
        criteria.criteria_fingerprint,
    ):
        reasons.append(RollbackDecisionReason.REQUEST_CRITERIA_MISMATCH)
    if (request.current_candidate_id, request.current_candidate_fingerprint) != (
        current_candidate.candidate_id,
        current_candidate.candidate_fingerprint,
    ):
        reasons.append(RollbackDecisionReason.REQUEST_CURRENT_CANDIDATE_MISMATCH)
    if (request.known_good_id, request.known_good_fingerprint) != (
        known_good.known_good_id,
        known_good.known_good_fingerprint,
    ):
        reasons.append(RollbackDecisionReason.REQUEST_KNOWN_GOOD_MISMATCH)
    if (criteria.current_candidate_id, criteria.current_candidate_fingerprint) != (
        current_candidate.candidate_id,
        current_candidate.candidate_fingerprint,
    ):
        reasons.append(RollbackDecisionReason.CRITERIA_CURRENT_CANDIDATE_MISMATCH)
    if (criteria.known_good_id, criteria.known_good_fingerprint) != (
        known_good.known_good_id,
        known_good.known_good_fingerprint,
    ):
        reasons.append(RollbackDecisionReason.CRITERIA_KNOWN_GOOD_MISMATCH)
    if (known_good.target_candidate_id, known_good.target_candidate_fingerprint) != (
        target_candidate.candidate_id,
        target_candidate.candidate_fingerprint,
    ):
        reasons.append(RollbackDecisionReason.KNOWN_GOOD_TARGET_MISMATCH)
    if (
        promotion_decision.status is not PromotionDecisionStatus.ELIGIBLE
        or (
            known_good.promotion_decision_id,
            known_good.promotion_decision_fingerprint,
        )
        != (promotion_decision.decision_id, promotion_decision.decision_fingerprint)
        or (promotion_decision.candidate_id, promotion_decision.candidate_fingerprint)
        != (target_candidate.candidate_id, target_candidate.candidate_fingerprint)
    ):
        reasons.append(RollbackDecisionReason.PROMOTION_DECISION_MISMATCH)
    if current_candidate.candidate_id == target_candidate.candidate_id:
        reasons.append(RollbackDecisionReason.SELF_ROLLBACK)
    if (
        current_candidate.policy_family_id != known_good.policy_family_id
        or current_candidate.input_contract_id != known_good.input_contract_id
        or current_candidate.input_contract_version != known_good.input_contract_version
        or current_candidate.output_contract_id != known_good.output_contract_id
        or current_candidate.output_contract_version != known_good.output_contract_version
        or target_candidate.policy_family_id != known_good.policy_family_id
        or target_candidate.input_contract_id != known_good.input_contract_id
        or target_candidate.input_contract_version != known_good.input_contract_version
        or target_candidate.output_contract_id != known_good.output_contract_id
        or target_candidate.output_contract_version != known_good.output_contract_version
    ):
        reasons.append(RollbackDecisionReason.TARGET_LINEAGE_MISMATCH)
    if request.reason not in criteria.allowed_reasons:
        reasons.append(RollbackDecisionReason.REASON_NOT_ALLOWED)
    if len(request.evidence_references) < criteria.minimum_evidence_references:
        reasons.append(RollbackDecisionReason.INSUFFICIENT_REASON_EVIDENCE)
    required_kind = _REQUIRED_EVIDENCE_KIND[request.reason]
    if not any(item.evidence_kind is required_kind for item in request.evidence_references):
        reasons.append(RollbackDecisionReason.EVIDENCE_KIND_MISMATCH)

    status = (
        RollbackDecisionStatus.ROLLBACK_REJECTED
        if reasons
        else RollbackDecisionStatus.ROLLBACK_ELIGIBLE
    )
    if not reasons:
        reasons.append(RollbackDecisionReason.ROLLBACK_CRITERIA_SATISFIED)
    return RollbackDecision._create(
        request_id=request.request_id,
        request_fingerprint=request.request_fingerprint,
        criteria_id=criteria.criteria_id,
        criteria_fingerprint=criteria.criteria_fingerprint,
        current_candidate_id=current_candidate.candidate_id,
        current_candidate_fingerprint=current_candidate.candidate_fingerprint,
        target_candidate_id=target_candidate.candidate_id,
        target_candidate_fingerprint=target_candidate.candidate_fingerprint,
        known_good_id=known_good.known_good_id,
        known_good_fingerprint=known_good.known_good_fingerprint,
        status=status,
        reasons=tuple(reasons),
    )
