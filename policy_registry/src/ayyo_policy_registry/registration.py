"""Pure candidate registration and read-only exact-version resolution."""

from __future__ import annotations

from ayyo_promotion_control import (
    CandidatePromotionRequest,
    PromotionCriteria,
    PromotionDecision,
    PromotionDecisionStatus,
    evaluate_promotion,
    verify_promotion_criteria,
    verify_promotion_decision,
    verify_promotion_request,
)

from .canonical import fingerprint, identifier, semantic_version
from .errors import CandidateRegistrationError, PolicyResolutionError, VersionLineageError
from .models import (
    CandidateRegistrationRequest,
    PolicyRegistrySnapshot,
    RegisteredPolicyVersion,
    RegistrationResult,
    RegistrationStatus,
    verify_policy_registry_snapshot,
    verify_registration_request,
)


def _identity(value: object, identifier_name: str, fingerprint_name: str) -> tuple[object, object]:
    return getattr(value, identifier_name), getattr(value, fingerprint_name)


def _authoritative_decision(
    *,
    candidate: object,
    evaluation_report: object,
    promotion_criteria: object,
    promotion_request: object,
    promotion_decision: object,
) -> PromotionDecision:
    checks = (
        (verify_promotion_criteria(promotion_criteria), 'promotion criteria'),
        (verify_promotion_request(promotion_request), 'promotion request'),
        (verify_promotion_decision(promotion_decision), 'promotion decision'),
    )
    for verified, label in checks:
        if not verified:
            raise CandidateRegistrationError(f'{label} failed integrity verification')
    try:
        return evaluate_promotion(
            criteria=promotion_criteria,
            request=promotion_request,
            candidate=candidate,
            report=evaluation_report,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CandidateRegistrationError(
            'candidate or evaluation report failed authoritative verification'
        ) from error


def _require_request_bindings(
    *,
    request: CandidateRegistrationRequest,
    candidate: object,
    evaluation_report: object,
    promotion_criteria: PromotionCriteria,
    promotion_request: CandidatePromotionRequest,
    promotion_decision: PromotionDecision,
) -> None:
    bindings = (
        (
            (request.candidate_id, request.candidate_fingerprint),
            _identity(candidate, 'candidate_id', 'candidate_fingerprint'),
            'candidate',
        ),
        (
            (request.evaluation_report_id, request.evaluation_report_fingerprint),
            _identity(evaluation_report, 'report_id', 'report_fingerprint'),
            'evaluation report',
        ),
        (
            (request.promotion_criteria_id, request.promotion_criteria_fingerprint),
            _identity(promotion_criteria, 'criteria_id', 'criteria_fingerprint'),
            'promotion criteria',
        ),
        (
            (request.promotion_request_id, request.promotion_request_fingerprint),
            _identity(promotion_request, 'request_id', 'request_fingerprint'),
            'promotion request',
        ),
        (
            (request.promotion_decision_id, request.promotion_decision_fingerprint),
            _identity(promotion_decision, 'decision_id', 'decision_fingerprint'),
            'promotion decision',
        ),
    )
    for requested, supplied, label in bindings:
        if requested != supplied:
            raise CandidateRegistrationError(
                f'registration request binds a different {label}'
            )


def _record_from_evidence(
    *,
    request: CandidateRegistrationRequest,
    candidate: object,
    evaluation_report: object,
    promotion_criteria: PromotionCriteria,
    promotion_request: CandidatePromotionRequest,
    promotion_decision: PromotionDecision,
) -> RegisteredPolicyVersion:
    return RegisteredPolicyVersion._from_fields(
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        semantic_version=candidate.semantic_version,
        policy_family_id=candidate.policy_family_id,
        candidate_evidence_set_id=candidate.candidate_evidence_set_id,
        candidate_evidence_set_fingerprint=candidate.candidate_evidence_set_fingerprint,
        input_contract_id=candidate.input_contract_id,
        input_contract_version=candidate.input_contract_version,
        output_contract_id=candidate.output_contract_id,
        output_contract_version=candidate.output_contract_version,
        parent_candidate_id=candidate.parent_candidate_id,
        parent_candidate_fingerprint=candidate.parent_candidate_fingerprint,
        evaluation_report_id=evaluation_report.report_id,
        evaluation_report_fingerprint=evaluation_report.report_fingerprint,
        evaluation_contract_id=evaluation_report.evaluation_contract_id,
        evaluation_contract_version=evaluation_report.evaluation_contract_version,
        holdout_evidence_set_id=evaluation_report.holdout_evidence_set_id,
        holdout_evidence_set_fingerprint=evaluation_report.holdout_evidence_set_fingerprint,
        promotion_criteria_id=promotion_criteria.criteria_id,
        promotion_criteria_fingerprint=promotion_criteria.criteria_fingerprint,
        promotion_request_id=promotion_request.request_id,
        promotion_request_fingerprint=promotion_request.request_fingerprint,
        promotion_decision_id=promotion_decision.decision_id,
        promotion_decision_fingerprint=promotion_decision.decision_fingerprint,
        target_stage=promotion_decision.target_stage,
        registration_request_id=request.registration_request_id,
        registration_request_fingerprint=request.registration_request_fingerprint,
        provenance_ref=request.provenance_ref,
        provenance_fingerprint=request.provenance_fingerprint,
    )


def _require_resolvable_parent(
    snapshot: PolicyRegistrySnapshot,
    record: RegisteredPolicyVersion,
) -> None:
    if record.parent_candidate_id is None:
        return
    if (record.parent_candidate_id, record.parent_candidate_fingerprint) == (
        record.candidate_id,
        record.candidate_fingerprint,
    ):
        raise VersionLineageError('a candidate cannot be its own parent')
    parent = next(
        (
            item
            for item in snapshot.registered_versions
            if (item.candidate_id, item.candidate_fingerprint)
            == (record.parent_candidate_id, record.parent_candidate_fingerprint)
        ),
        None,
    )
    if parent is None:
        raise VersionLineageError('the exact parent candidate is not registered')
    if parent.policy_family_id != record.policy_family_id:
        raise VersionLineageError('parent belongs to a different policy family')
    if (
        parent.input_contract_id,
        parent.input_contract_version,
        parent.output_contract_id,
        parent.output_contract_version,
    ) != (
        record.input_contract_id,
        record.input_contract_version,
        record.output_contract_id,
        record.output_contract_version,
    ):
        raise VersionLineageError('parent uses incompatible policy contracts')


def register_candidate(
    *,
    previous_snapshot: PolicyRegistrySnapshot,
    request: CandidateRegistrationRequest,
    candidate: object,
    evaluation_report: object,
    promotion_criteria: PromotionCriteria,
    promotion_request: CandidatePromotionRequest,
    promotion_decision: PromotionDecision,
) -> RegistrationResult:
    """Register verified evidence into a new immutable snapshot; execute nothing."""
    if not verify_policy_registry_snapshot(previous_snapshot):
        raise CandidateRegistrationError('previous snapshot failed integrity verification')
    if not verify_registration_request(request):
        raise CandidateRegistrationError('registration request failed integrity verification')
    expected_decision = _authoritative_decision(
        candidate=candidate,
        evaluation_report=evaluation_report,
        promotion_criteria=promotion_criteria,
        promotion_request=promotion_request,
        promotion_decision=promotion_decision,
    )
    _require_request_bindings(
        request=request,
        candidate=candidate,
        evaluation_report=evaluation_report,
        promotion_criteria=promotion_criteria,
        promotion_request=promotion_request,
        promotion_decision=promotion_decision,
    )
    if expected_decision != promotion_decision:
        raise CandidateRegistrationError(
            'promotion decision is not the authoritative result for the supplied evidence'
        )
    if promotion_decision.status is not PromotionDecisionStatus.ELIGIBLE:
        raise CandidateRegistrationError('only an eligible promotion decision may register')
    if request.target_stage != promotion_request.target_stage or request.target_stage != (
        promotion_decision.target_stage
    ):
        raise CandidateRegistrationError(
            'registration target stage differs from the verified promotion chain'
        )

    record = _record_from_evidence(
        request=request,
        candidate=candidate,
        evaluation_report=evaluation_report,
        promotion_criteria=promotion_criteria,
        promotion_request=promotion_request,
        promotion_decision=promotion_decision,
    )
    same_version = next(
        (
            item
            for item in previous_snapshot.registered_versions
            if (item.policy_family_id, item.semantic_version)
            == (record.policy_family_id, record.semantic_version)
        ),
        None,
    )
    if same_version is not None:
        if same_version == record:
            return RegistrationResult._from_fields(
                status=RegistrationStatus.ALREADY_REGISTERED,
                registration_request_id=request.registration_request_id,
                registration_request_fingerprint=request.registration_request_fingerprint,
                registered_version=record,
                previous_snapshot=previous_snapshot,
                updated_snapshot=previous_snapshot,
            )
        raise CandidateRegistrationError(
            'policy family already contains a conflicting semantic version'
        )
    if any(
        item.candidate_id == record.candidate_id
        for item in previous_snapshot.registered_versions
    ):
        raise CandidateRegistrationError('candidate identity is already registered differently')

    _require_resolvable_parent(previous_snapshot, record)
    updated_snapshot = PolicyRegistrySnapshot(
        (*previous_snapshot.registered_versions, record)
    )
    return RegistrationResult._from_fields(
        status=RegistrationStatus.REGISTERED,
        registration_request_id=request.registration_request_id,
        registration_request_fingerprint=request.registration_request_fingerprint,
        registered_version=record,
        previous_snapshot=previous_snapshot,
        updated_snapshot=updated_snapshot,
    )


def resolve_registered_policy(
    snapshot: PolicyRegistrySnapshot,
    *,
    record_id: str,
    record_fingerprint: str,
) -> RegisteredPolicyVersion | None:
    """Resolve one exact content-addressed record without aliases or mutation."""
    if not verify_policy_registry_snapshot(snapshot):
        raise PolicyResolutionError('snapshot failed integrity verification')
    try:
        record_id = identifier(record_id, 'record_id')
        record_fingerprint = fingerprint(record_fingerprint, 'record_fingerprint')
    except ValueError as error:
        raise PolicyResolutionError('record identity is malformed') from error
    return next(
        (
            item
            for item in snapshot.registered_versions
            if (item.record_id, item.record_fingerprint)
            == (record_id, record_fingerprint)
        ),
        None,
    )


def resolve_policy_version(
    snapshot: PolicyRegistrySnapshot,
    *,
    policy_family_id: str,
    semantic_version_value: str,
) -> RegisteredPolicyVersion | None:
    """Resolve one explicit family/version pair; never infer a latest version."""
    if not verify_policy_registry_snapshot(snapshot):
        raise PolicyResolutionError('snapshot failed integrity verification')
    try:
        policy_family_id = identifier(policy_family_id, 'policy_family_id')
        semantic_version_value = semantic_version(
            semantic_version_value, 'semantic_version'
        )
    except ValueError as error:
        raise PolicyResolutionError('policy version lookup is malformed') from error
    return next(
        (
            item
            for item in snapshot.registered_versions
            if (item.policy_family_id, item.semantic_version)
            == (policy_family_id, semantic_version_value)
        ),
        None,
    )
