"""Pure, inert candidate promotion criteria and evidence decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_learning_evaluation import (
    MAX_TRIALS_PER_EVALUATION,
    CandidatePolicyManifest,
    OfflineEvaluationDisposition,
    OfflineEvaluationReport,
    OfflineTrialStatus,
    verify_candidate_policy,
    verify_evaluation_report,
)

from .canonical import (
    assert_size,
    bounded_enum_tuple,
    fingerprint,
    identifier,
    optional_note,
    semantic_sha256,
    semantic_version,
)
from .errors import PromotionCriteriaError, PromotionDecisionError, PromotionRequestError


PROMOTION_CRITERIA_SCHEMA_ID = 'ayyo.promotion-control.promotion-criteria.v1'
PROMOTION_REQUEST_SCHEMA_ID = 'ayyo.promotion-control.promotion-request.v1'
PROMOTION_DECISION_SCHEMA_ID = 'ayyo.promotion-control.promotion-decision.v1'
PROMOTION_SCHEMA_VERSION = '1.0.0'


class PromotionTargetStage(StrEnum):
    REVIEWED_CANDIDATE = 'reviewed_candidate'
    FUTURE_DEPLOYMENT_REVIEW = 'future_deployment_review'


class PromotionDecisionStatus(StrEnum):
    ELIGIBLE = 'eligible'
    NOT_ELIGIBLE = 'not_eligible'


class PromotionDecisionReason(StrEnum):
    CRITERIA_SATISFIED = 'criteria_satisfied'
    REQUEST_CRITERIA_MISMATCH = 'request_criteria_mismatch'
    REQUEST_CANDIDATE_MISMATCH = 'request_candidate_mismatch'
    REQUEST_REPORT_MISMATCH = 'request_report_mismatch'
    REPORT_CANDIDATE_MISMATCH = 'report_candidate_mismatch'
    CRITERIA_CANDIDATE_MISMATCH = 'criteria_candidate_mismatch'
    TARGET_NOT_ALLOWED = 'target_not_allowed'
    UNSUPPORTED_EVALUATION_SCHEMA = 'unsupported_evaluation_schema'
    UNSUPPORTED_EVALUATION_VERSION = 'unsupported_evaluation_version'
    DISPOSITION_NOT_ACCEPTED = 'disposition_not_accepted'
    INCOMPLETE_EVALUATION = 'incomplete_evaluation'
    INSUFFICIENT_EVALUATED_TRIALS = 'insufficient_evaluated_trials'
    FAILED_TRIAL_LIMIT_EXCEEDED = 'failed_trial_limit_exceeded'
    HOLDOUT_IDENTITY_MISMATCH = 'holdout_identity_mismatch'


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
class PromotionCriteria:
    schema_id: str
    schema_version: str
    criteria_id: str
    criteria_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    required_report_schema_id: str
    required_report_schema_version: str
    holdout_evidence_set_id: str
    holdout_evidence_set_fingerprint: str
    accepted_dispositions: tuple[OfflineEvaluationDisposition, ...]
    minimum_evaluated_trials: int
    maximum_failed_trials: int
    require_complete_evaluation: bool
    allowed_target_stages: tuple[PromotionTargetStage, ...]

    def __init__(
        self,
        *,
        candidate_id: str,
        candidate_fingerprint: str,
        required_report_schema_id: str,
        required_report_schema_version: str,
        holdout_evidence_set_id: str,
        holdout_evidence_set_fingerprint: str,
        accepted_dispositions: tuple[OfflineEvaluationDisposition, ...]
        | list[OfflineEvaluationDisposition],
        minimum_evaluated_trials: int,
        maximum_failed_trials: int,
        require_complete_evaluation: bool,
        allowed_target_stages: tuple[PromotionTargetStage, ...]
        | list[PromotionTargetStage],
    ) -> None:
        self._initialize(
            candidate_id=candidate_id,
            candidate_fingerprint=candidate_fingerprint,
            required_report_schema_id=required_report_schema_id,
            required_report_schema_version=required_report_schema_version,
            holdout_evidence_set_id=holdout_evidence_set_id,
            holdout_evidence_set_fingerprint=holdout_evidence_set_fingerprint,
            accepted_dispositions=accepted_dispositions,
            minimum_evaluated_trials=minimum_evaluated_trials,
            maximum_failed_trials=maximum_failed_trials,
            require_complete_evaluation=require_complete_evaluation,
            allowed_target_stages=allowed_target_stages,
        )

    @classmethod
    def _from_fields(cls, **fields) -> PromotionCriteria:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', PROMOTION_CRITERIA_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', PROMOTION_SCHEMA_VERSION)
            object.__setattr__(self, 'candidate_id', identifier(fields['candidate_id'], 'candidate_id'))
            object.__setattr__(
                self,
                'candidate_fingerprint',
                fingerprint(fields['candidate_fingerprint'], 'candidate_fingerprint'),
            )
            object.__setattr__(
                self,
                'required_report_schema_id',
                identifier(fields['required_report_schema_id'], 'required_report_schema_id'),
            )
            object.__setattr__(
                self,
                'required_report_schema_version',
                semantic_version(
                    fields['required_report_schema_version'],
                    'required_report_schema_version',
                ),
            )
            object.__setattr__(
                self,
                'holdout_evidence_set_id',
                identifier(fields['holdout_evidence_set_id'], 'holdout_evidence_set_id'),
            )
            object.__setattr__(
                self,
                'holdout_evidence_set_fingerprint',
                fingerprint(
                    fields['holdout_evidence_set_fingerprint'],
                    'holdout_evidence_set_fingerprint',
                ),
            )
            object.__setattr__(
                self,
                'accepted_dispositions',
                bounded_enum_tuple(
                    fields['accepted_dispositions'],
                    OfflineEvaluationDisposition,
                    'accepted_dispositions',
                ),
            )
            minimum = fields['minimum_evaluated_trials']
            maximum = fields['maximum_failed_trials']
            if type(minimum) is not int or not 1 <= minimum <= MAX_TRIALS_PER_EVALUATION:
                raise PromotionCriteriaError('minimum_evaluated_trials is outside v1 bounds')
            if type(maximum) is not int or not 0 <= maximum <= MAX_TRIALS_PER_EVALUATION:
                raise PromotionCriteriaError('maximum_failed_trials is outside v1 bounds')
            if type(fields['require_complete_evaluation']) is not bool:
                raise PromotionCriteriaError('require_complete_evaluation must be boolean')
            object.__setattr__(self, 'minimum_evaluated_trials', minimum)
            object.__setattr__(self, 'maximum_failed_trials', maximum)
            object.__setattr__(
                self, 'require_complete_evaluation', fields['require_complete_evaluation']
            )
            object.__setattr__(
                self,
                'allowed_target_stages',
                bounded_enum_tuple(
                    fields['allowed_target_stages'],
                    PromotionTargetStage,
                    'allowed_target_stages',
                ),
            )
            _set_identity(self, 'promotion-criteria', 'criteria_fingerprint', 'criteria_id')
        except PromotionCriteriaError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise PromotionCriteriaError('promotion criteria violate the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'accepted_dispositions': [item.value for item in self.accepted_dispositions],
            'allowed_target_stages': [item.value for item in self.allowed_target_stages],
            'candidate': {'fingerprint': self.candidate_fingerprint, 'id': self.candidate_id},
            'holdout_evidence_set': {
                'fingerprint': self.holdout_evidence_set_fingerprint,
                'id': self.holdout_evidence_set_id,
            },
            'maximum_failed_trials': self.maximum_failed_trials,
            'minimum_evaluated_trials': self.minimum_evaluated_trials,
            'require_complete_evaluation': self.require_complete_evaluation,
            'required_report_schema': {
                'id': self.required_report_schema_id,
                'version': self.required_report_schema_version,
            },
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('promotion-criteria-content', self.semantic_document())

    def recompute_criteria_id(self) -> str:
        return semantic_sha256(
            'promotion-criteria',
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


def verify_promotion_criteria(criteria: object) -> bool:
    if type(criteria) is not PromotionCriteria:
        return False
    try:
        rebuilt = PromotionCriteria._from_fields(
            candidate_id=criteria.candidate_id,
            candidate_fingerprint=criteria.candidate_fingerprint,
            required_report_schema_id=criteria.required_report_schema_id,
            required_report_schema_version=criteria.required_report_schema_version,
            holdout_evidence_set_id=criteria.holdout_evidence_set_id,
            holdout_evidence_set_fingerprint=criteria.holdout_evidence_set_fingerprint,
            accepted_dispositions=criteria.accepted_dispositions,
            minimum_evaluated_trials=criteria.minimum_evaluated_trials,
            maximum_failed_trials=criteria.maximum_failed_trials,
            require_complete_evaluation=criteria.require_complete_evaluation,
            allowed_target_stages=criteria.allowed_target_stages,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == criteria


@dataclass(frozen=True, slots=True, init=False)
class CandidatePromotionRequest:
    schema_id: str
    schema_version: str
    request_id: str
    request_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    report_id: str
    report_fingerprint: str
    criteria_id: str
    criteria_fingerprint: str
    target_stage: PromotionTargetStage
    provenance_ref: str
    provenance_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        candidate: CandidatePolicyManifest,
        report: OfflineEvaluationReport,
        criteria: PromotionCriteria,
        target_stage: PromotionTargetStage,
        provenance_ref: str,
        provenance_fingerprint: str,
        note: str | None = None,
    ) -> None:
        if not verify_candidate_policy(candidate):
            raise PromotionRequestError('request requires a verified candidate')
        if not verify_evaluation_report(report):
            raise PromotionRequestError('request requires a verified evaluation report')
        if not verify_promotion_criteria(criteria):
            raise PromotionRequestError('request requires verified promotion criteria')
        self._initialize(
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.candidate_fingerprint,
            report_id=report.report_id,
            report_fingerprint=report.report_fingerprint,
            criteria_id=criteria.criteria_id,
            criteria_fingerprint=criteria.criteria_fingerprint,
            target_stage=target_stage,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> CandidatePromotionRequest:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', PROMOTION_REQUEST_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', PROMOTION_SCHEMA_VERSION)
            for name in ('candidate_id', 'report_id', 'criteria_id', 'provenance_ref'):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'candidate_fingerprint',
                'report_fingerprint',
                'criteria_fingerprint',
                'provenance_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            if not isinstance(fields['target_stage'], PromotionTargetStage):
                raise PromotionRequestError('target_stage must use its closed enum')
            object.__setattr__(self, 'target_stage', fields['target_stage'])
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(self, 'promotion-request', 'request_fingerprint', 'request_id')
        except PromotionRequestError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise PromotionRequestError('promotion request violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'candidate': {'fingerprint': self.candidate_fingerprint, 'id': self.candidate_id},
            'criteria': {'fingerprint': self.criteria_fingerprint, 'id': self.criteria_id},
            'note': self.note,
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'report': {'fingerprint': self.report_fingerprint, 'id': self.report_id},
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'target_stage': self.target_stage.value,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('promotion-request-content', self.semantic_document())

    def recompute_request_id(self) -> str:
        return semantic_sha256(
            'promotion-request',
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


def verify_promotion_request(request: object) -> bool:
    if type(request) is not CandidatePromotionRequest:
        return False
    try:
        rebuilt = CandidatePromotionRequest._from_fields(
            candidate_id=request.candidate_id,
            candidate_fingerprint=request.candidate_fingerprint,
            report_id=request.report_id,
            report_fingerprint=request.report_fingerprint,
            criteria_id=request.criteria_id,
            criteria_fingerprint=request.criteria_fingerprint,
            target_stage=request.target_stage,
            provenance_ref=request.provenance_ref,
            provenance_fingerprint=request.provenance_fingerprint,
            note=request.note,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == request


@dataclass(frozen=True, slots=True, init=False)
class PromotionDecision:
    schema_id: str
    schema_version: str
    decision_id: str
    decision_fingerprint: str
    request_id: str
    request_fingerprint: str
    criteria_id: str
    criteria_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    report_id: str
    report_fingerprint: str
    target_stage: PromotionTargetStage
    status: PromotionDecisionStatus
    reasons: tuple[PromotionDecisionReason, ...]

    @classmethod
    def _create(cls, **fields) -> PromotionDecision:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', PROMOTION_DECISION_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', PROMOTION_SCHEMA_VERSION)
            for name in ('request_id', 'criteria_id', 'candidate_id', 'report_id'):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'request_fingerprint',
                'criteria_fingerprint',
                'candidate_fingerprint',
                'report_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            if not isinstance(fields['target_stage'], PromotionTargetStage):
                raise PromotionDecisionError('target_stage must use its closed enum')
            if not isinstance(fields['status'], PromotionDecisionStatus):
                raise PromotionDecisionError('status must use its closed enum')
            reasons = bounded_enum_tuple(
                fields['reasons'], PromotionDecisionReason, 'promotion decision reasons'
            )
            if fields['status'] is PromotionDecisionStatus.ELIGIBLE:
                if reasons != (PromotionDecisionReason.CRITERIA_SATISFIED,):
                    raise PromotionDecisionError('eligible decision requires only criteria_satisfied')
            elif PromotionDecisionReason.CRITERIA_SATISFIED in reasons:
                raise PromotionDecisionError('not-eligible decision cannot claim criteria_satisfied')
            object.__setattr__(self, 'target_stage', fields['target_stage'])
            object.__setattr__(self, 'status', fields['status'])
            object.__setattr__(self, 'reasons', reasons)
            _set_identity(self, 'promotion-decision', 'decision_fingerprint', 'decision_id')
        except PromotionDecisionError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise PromotionDecisionError('promotion decision violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'candidate': {'fingerprint': self.candidate_fingerprint, 'id': self.candidate_id},
            'criteria': {'fingerprint': self.criteria_fingerprint, 'id': self.criteria_id},
            'reasons': [item.value for item in self.reasons],
            'report': {'fingerprint': self.report_fingerprint, 'id': self.report_id},
            'request': {'fingerprint': self.request_fingerprint, 'id': self.request_id},
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'status': self.status.value,
            'target_stage': self.target_stage.value,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('promotion-decision-content', self.semantic_document())

    def recompute_decision_id(self) -> str:
        return semantic_sha256(
            'promotion-decision',
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


def verify_promotion_decision(decision: object) -> bool:
    if type(decision) is not PromotionDecision:
        return False
    try:
        rebuilt = PromotionDecision._create(
            request_id=decision.request_id,
            request_fingerprint=decision.request_fingerprint,
            criteria_id=decision.criteria_id,
            criteria_fingerprint=decision.criteria_fingerprint,
            candidate_id=decision.candidate_id,
            candidate_fingerprint=decision.candidate_fingerprint,
            report_id=decision.report_id,
            report_fingerprint=decision.report_fingerprint,
            target_stage=decision.target_stage,
            status=decision.status,
            reasons=decision.reasons,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == decision


def evaluate_promotion(
    *,
    criteria: PromotionCriteria,
    request: CandidatePromotionRequest,
    candidate: CandidatePolicyManifest,
    report: OfflineEvaluationReport,
) -> PromotionDecision:
    """Evaluate explicit evidence only; this never installs or executes a policy."""
    if not verify_promotion_criteria(criteria):
        raise PromotionDecisionError('promotion criteria failed integrity verification')
    if not verify_promotion_request(request):
        raise PromotionDecisionError('promotion request failed integrity verification')
    if not verify_candidate_policy(candidate):
        raise PromotionDecisionError('candidate failed integrity verification')
    if not verify_evaluation_report(report):
        raise PromotionDecisionError('evaluation report failed integrity verification')

    reasons: list[PromotionDecisionReason] = []
    if (request.criteria_id, request.criteria_fingerprint) != (
        criteria.criteria_id,
        criteria.criteria_fingerprint,
    ):
        reasons.append(PromotionDecisionReason.REQUEST_CRITERIA_MISMATCH)
    if (request.candidate_id, request.candidate_fingerprint) != (
        candidate.candidate_id,
        candidate.candidate_fingerprint,
    ):
        reasons.append(PromotionDecisionReason.REQUEST_CANDIDATE_MISMATCH)
    if (request.report_id, request.report_fingerprint) != (
        report.report_id,
        report.report_fingerprint,
    ):
        reasons.append(PromotionDecisionReason.REQUEST_REPORT_MISMATCH)
    if (report.candidate_id, report.candidate_fingerprint) != (
        candidate.candidate_id,
        candidate.candidate_fingerprint,
    ):
        reasons.append(PromotionDecisionReason.REPORT_CANDIDATE_MISMATCH)
    if (criteria.candidate_id, criteria.candidate_fingerprint) != (
        candidate.candidate_id,
        candidate.candidate_fingerprint,
    ):
        reasons.append(PromotionDecisionReason.CRITERIA_CANDIDATE_MISMATCH)
    if request.target_stage not in criteria.allowed_target_stages:
        reasons.append(PromotionDecisionReason.TARGET_NOT_ALLOWED)
    if report.schema_id != criteria.required_report_schema_id:
        reasons.append(PromotionDecisionReason.UNSUPPORTED_EVALUATION_SCHEMA)
    if report.schema_version != criteria.required_report_schema_version:
        reasons.append(PromotionDecisionReason.UNSUPPORTED_EVALUATION_VERSION)
    if report.disposition not in criteria.accepted_dispositions:
        reasons.append(PromotionDecisionReason.DISPOSITION_NOT_ACCEPTED)
    if criteria.require_complete_evaluation and (
        report.coverage_numerator != report.coverage_denominator
        or report.missing_holdout_episode_ids
        or report.incomplete_holdout_episode_ids
    ):
        reasons.append(PromotionDecisionReason.INCOMPLETE_EVALUATION)
    if report.coverage_numerator < criteria.minimum_evaluated_trials:
        reasons.append(PromotionDecisionReason.INSUFFICIENT_EVALUATED_TRIALS)
    status_counts = {item.value: item.count for item in report.status_counts}
    if status_counts.get(OfflineTrialStatus.OUTCOME_MISMATCH.value, 0) > (
        criteria.maximum_failed_trials
    ):
        reasons.append(PromotionDecisionReason.FAILED_TRIAL_LIMIT_EXCEEDED)
    if (
        report.holdout_evidence_set_id != criteria.holdout_evidence_set_id
        or report.holdout_evidence_set_fingerprint
        != criteria.holdout_evidence_set_fingerprint
    ):
        reasons.append(PromotionDecisionReason.HOLDOUT_IDENTITY_MISMATCH)

    status = (
        PromotionDecisionStatus.NOT_ELIGIBLE
        if reasons
        else PromotionDecisionStatus.ELIGIBLE
    )
    if not reasons:
        reasons.append(PromotionDecisionReason.CRITERIA_SATISFIED)
    return PromotionDecision._create(
        request_id=request.request_id,
        request_fingerprint=request.request_fingerprint,
        criteria_id=criteria.criteria_id,
        criteria_fingerprint=criteria.criteria_fingerprint,
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        report_id=report.report_id,
        report_fingerprint=report.report_fingerprint,
        target_stage=request.target_stage,
        status=status,
        reasons=tuple(reasons),
    )
