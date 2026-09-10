from __future__ import annotations

from hashlib import sha256

from ayyo_approval_eligibility import (
    ActivationEligibilityRequest,
    ApprovalDisposition,
    ApprovalRequest,
    ApprovalScope,
    AuthorityApprovalEvidence,
    AuthorityReference,
    AuthorityVerificationStatus,
    evaluate_activation_eligibility,
)
from ayyo_learning_evaluation import (
    CandidatePolicyManifest,
    DemonstrationEvaluationCorpus,
    EVALUATION_REPORT_SCHEMA_ID,
    EVALUATION_REPORT_SCHEMA_VERSION,
    ExactMetric,
    OfflineEvaluationDisposition,
    OfflineTrialReason,
    OfflineTrialResult,
    OfflineTrialStatus,
    evaluate_offline,
)
from ayyo_policy_registry import (
    CandidateRegistrationRequest,
    PolicyRegistrySnapshot,
    register_candidate,
)
from ayyo_promotion_control import (
    CandidatePromotionRequest,
    PromotionCriteria,
    PromotionTargetStage,
    evaluate_promotion,
)
from ayyo_teach_mode import (
    AYYO_ROBOT_ID,
    DemonstrationClockKind,
    DemonstrationEpisode,
    DemonstrationEvent,
    DemonstrationEventType,
    DemonstrationObservationReference,
    DemonstrationOutcome,
    DemonstrationOutcomeStatus,
    DemonstrationProvenance,
    DemonstrationSourceKind,
    DemonstrationSourceTimeRange,
    ObservationReferenceKind,
)


def fingerprint(prefix: str, value: str) -> str:
    return f'{prefix}-sha256-{sha256(value.encode()).hexdigest()}'


def fixture_episode(
    label: str,
    outcome: DemonstrationOutcomeStatus = DemonstrationOutcomeStatus.SUCCESS,
) -> DemonstrationEpisode:
    reference = DemonstrationObservationReference(
        kind=ObservationReferenceKind.PUBLIC_EVIDENCE,
        reference_id=f'fixture-evidence-{label}',
        fingerprint=fingerprint('fixture-evidence', label),
        provenance_kind='test-fixture',
        interface_id='ayyo.fixture-evidence.v1',
    )
    return DemonstrationEpisode(
        source_kind=DemonstrationSourceKind.TEST_FIXTURE,
        robot_id=AYYO_ROBOT_ID,
        source_time=DemonstrationSourceTimeRange(
            DemonstrationClockKind.TEST_TIME, 100, 100
        ),
        provenance=DemonstrationProvenance(
            source_ref=f'fixture-source-{label}',
            source_fingerprint=fingerprint('fixture-source', label),
        ),
        events=(
            DemonstrationEvent(
                event_id=f'fixture-event-{label}',
                sequence_index=0,
                event_type=DemonstrationEventType.OBSERVATION,
                source_time_ns=100,
                observation_references=(reference,),
            ),
        ),
        outcome=DemonstrationOutcome(
            outcome,
            (f'fixture-outcome-{outcome.value}',),
            f'Explicit {outcome.value} fixture evidence.',
        ),
    )


def fixture_registration_bundle(label: str = 'one') -> dict[str, object]:
    corpus = DemonstrationEvaluationCorpus(
        candidate_evidence=(fixture_episode(f'{label}-candidate'),),
        holdout_evaluation=(
            fixture_episode(
                f'{label}-holdout-deferred', DemonstrationOutcomeStatus.DEFERRED
            ),
            fixture_episode(
                f'{label}-holdout-rejected', DemonstrationOutcomeStatus.REJECTED
            ),
        ),
        description=f'Explicit deterministic {label} approval fixture corpus.',
    )
    candidate = CandidatePolicyManifest(
        candidate_evidence=corpus.candidate_evidence,
        semantic_version='0.1.0',
        policy_family_id=f'ayyo.demonstration-policy.{label}.v1',
        input_contract_id='ayyo.demonstration-input.v1',
        input_contract_version='1.0.0',
        output_contract_id='ayyo.demonstration-output.v1',
        output_contract_version='1.0.0',
        description=f'Inert approval eligibility fixture candidate {label}.',
    )
    trials = tuple(
        OfflineTrialResult(
            candidate=candidate,
            holdout_episode=reference,
            observed_outcome=reference.outcome_status,
            status=OfflineTrialStatus.OUTCOME_MATCH,
            reasons=(OfflineTrialReason.EXPECTED_OUTCOME_OBSERVED,),
            result_source_ref='offline-runner.approval-fixture.v1',
            result_source_fingerprint=fingerprint('offline-result-source', label),
            metrics=(ExactMetric('outcome-agreement', 1, 1),),
        )
        for reference in corpus.holdout_evaluation.episodes
    )
    report = evaluate_offline(corpus=corpus, candidate=candidate, trials=trials)
    criteria = PromotionCriteria(
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        required_report_schema_id=EVALUATION_REPORT_SCHEMA_ID,
        required_report_schema_version=EVALUATION_REPORT_SCHEMA_VERSION,
        holdout_evidence_set_id=report.holdout_evidence_set_id,
        holdout_evidence_set_fingerprint=report.holdout_evidence_set_fingerprint,
        accepted_dispositions=(OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA,),
        minimum_evaluated_trials=2,
        maximum_failed_trials=0,
        require_complete_evaluation=True,
        allowed_target_stages=(PromotionTargetStage.REVIEWED_CANDIDATE,),
    )
    promotion_request = CandidatePromotionRequest(
        candidate=candidate,
        report=report,
        criteria=criteria,
        target_stage=PromotionTargetStage.REVIEWED_CANDIDATE,
        provenance_ref='promotion-review.approval-fixture.v1',
        provenance_fingerprint=fingerprint('promotion-review', label),
    )
    promotion_decision = evaluate_promotion(
        criteria=criteria,
        request=promotion_request,
        candidate=candidate,
        report=report,
    )
    registration_request = CandidateRegistrationRequest(
        candidate=candidate,
        evaluation_report=report,
        promotion_criteria=criteria,
        promotion_request=promotion_request,
        promotion_decision=promotion_decision,
        target_stage=PromotionTargetStage.REVIEWED_CANDIDATE,
        provenance_ref='policy-registry-review.approval-fixture.v1',
        provenance_fingerprint=fingerprint('policy-registry-review', label),
        note='Evidence registration only; never activation authority.',
    )
    return {
        'candidate': candidate,
        'corpus': corpus,
        'criteria': criteria,
        'promotion_decision': promotion_decision,
        'promotion_request': promotion_request,
        'registration_request': registration_request,
        'report': report,
        'snapshot': PolicyRegistrySnapshot(),
    }


def registered_version(label: str = 'one'):
    bundle = fixture_registration_bundle(label)
    result = register_candidate(
        previous_snapshot=bundle['snapshot'],
        request=bundle['registration_request'],
        candidate=bundle['candidate'],
        evaluation_report=bundle['report'],
        promotion_criteria=bundle['criteria'],
        promotion_request=bundle['promotion_request'],
        promotion_decision=bundle['promotion_decision'],
    )
    return result.registered_version


def fixture_authority(
    label: str = 'one',
    status: AuthorityVerificationStatus = AuthorityVerificationStatus.EXTERNALLY_VERIFIED,
) -> AuthorityReference:
    has_external_evidence = status is not AuthorityVerificationStatus.UNVERIFIED
    return AuthorityReference(
        authority_id=f'authority.reviewer.{label}',
        authority_fingerprint=fingerprint('authority', label),
        verification_status=status,
        verification_provider_ref=(
            'authority-provider.fixture.v1' if has_external_evidence else None
        ),
        verification_provider_fingerprint=(
            fingerprint('authority-provider', label) if has_external_evidence else None
        ),
        verification_evidence_ref=(
            f'authority-proof.fixture.{label}' if has_external_evidence else None
        ),
        verification_evidence_fingerprint=(
            fingerprint('authority-proof', label) if has_external_evidence else None
        ),
        provenance_ref=f'authority-reference.fixture.{label}',
        provenance_fingerprint=fingerprint('authority-reference', label),
        note='External verification is asserted, not performed by this package.',
    )


def fixture_approval_bundle(
    label: str = 'one',
    *,
    authority_status: AuthorityVerificationStatus = (
        AuthorityVerificationStatus.EXTERNALLY_VERIFIED
    ),
    disposition: ApprovalDisposition = ApprovalDisposition.APPROVED,
) -> dict[str, object]:
    record = registered_version(label)
    authority = fixture_authority(label, authority_status)
    approval_request = ApprovalRequest(
        registered_version=record,
        authority=authority,
        approval_scope=ApprovalScope.FUTURE_ACTIVATION_REVIEW,
        provenance_ref=f'approval-request.fixture.{label}',
        provenance_fingerprint=fingerprint('approval-request-source', label),
        note='Request for evidence-only future activation review.',
    )
    approval_evidence = AuthorityApprovalEvidence(
        approval_request=approval_request,
        authority=authority,
        disposition=disposition,
        evidence_ref=f'approval-evidence.fixture.{label}',
        evidence_fingerprint=fingerprint('approval-evidence-source', label),
        note='No authentication or activation is performed here.',
    )
    eligibility_request = ActivationEligibilityRequest(
        registered_version=record,
        approval_request=approval_request,
        approval_evidence=approval_evidence,
        provenance_ref=f'eligibility-review.fixture.{label}',
        provenance_fingerprint=fingerprint('eligibility-review', label),
        note='Structural eligibility only.',
    )
    decision = evaluate_activation_eligibility(eligibility_request)
    return {
        'registered_version': record,
        'authority': authority,
        'approval_request': approval_request,
        'approval_evidence': approval_evidence,
        'eligibility_request': eligibility_request,
        'decision': decision,
    }


def rebuild_authority(authority, **overrides):
    fields = {
        name: getattr(authority, name)
        for name in AuthorityReference.__annotations__
        if name
        not in {
            'schema_id',
            'schema_version',
            'authority_reference_id',
            'authority_reference_fingerprint',
        }
    }
    fields.update(overrides)
    return AuthorityReference._from_fields(**fields)


def rebuild_approval_request(request, **overrides):
    fields = {
        name: getattr(request, name)
        for name in ApprovalRequest.__annotations__
        if name
        not in {
            'schema_id',
            'schema_version',
            'approval_request_id',
            'approval_request_fingerprint',
        }
    }
    fields.update(overrides)
    return ApprovalRequest._from_fields(**fields)


def evidence_for(request, authority, disposition=ApprovalDisposition.APPROVED):
    return AuthorityApprovalEvidence(
        approval_request=request,
        authority=authority,
        disposition=disposition,
        evidence_ref='approval-evidence.fixture.rebuilt',
        evidence_fingerprint=fingerprint('approval-evidence-source', 'rebuilt'),
    )
