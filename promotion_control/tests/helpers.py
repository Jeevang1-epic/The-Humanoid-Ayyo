from __future__ import annotations

from hashlib import sha256

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
from ayyo_promotion_control import (
    CandidatePromotionRequest,
    KnownGoodPolicyReference,
    PromotionCriteria,
    PromotionTargetStage,
    RollbackCriteria,
    RollbackEvidenceKind,
    RollbackEvidenceReference,
    RollbackReason,
    RollbackRequest,
    evaluate_promotion,
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
        source_time=DemonstrationSourceTimeRange(DemonstrationClockKind.TEST_TIME, 100, 100),
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


def fixture_corpus(label: str = 'one') -> DemonstrationEvaluationCorpus:
    return DemonstrationEvaluationCorpus(
        candidate_evidence=(fixture_episode(f'{label}-candidate'),),
        holdout_evaluation=(
            fixture_episode(
                f'{label}-holdout-deferred', DemonstrationOutcomeStatus.DEFERRED
            ),
            fixture_episode(
                f'{label}-holdout-rejected', DemonstrationOutcomeStatus.REJECTED
            ),
        ),
        description=f'Explicit deterministic {label} fixture corpus.',
    )


def fixture_candidate(
    corpus: DemonstrationEvaluationCorpus,
    *,
    semantic_version: str = '0.1.0',
    policy_family_id: str = 'ayyo.demonstration-policy.v1',
) -> CandidatePolicyManifest:
    return CandidatePolicyManifest(
        candidate_evidence=corpus.candidate_evidence,
        semantic_version=semantic_version,
        policy_family_id=policy_family_id,
        input_contract_id='ayyo.demonstration-input.v1',
        input_contract_version='1.0.0',
        output_contract_id='ayyo.demonstration-output.v1',
        output_contract_version='1.0.0',
        description=f'Inert fixture candidate {semantic_version}.',
    )


def fixture_report(
    corpus: DemonstrationEvaluationCorpus,
    candidate: CandidatePolicyManifest,
    *,
    statuses: tuple[OfflineTrialStatus, ...] | None = None,
):
    statuses = statuses or (
        OfflineTrialStatus.OUTCOME_MATCH,
        OfflineTrialStatus.OUTCOME_MATCH,
    )
    trials = []
    for reference, status in zip(corpus.holdout_evaluation.episodes, statuses, strict=False):
        if status is OfflineTrialStatus.OUTCOME_MATCH:
            observed = reference.outcome_status
            reasons = (OfflineTrialReason.EXPECTED_OUTCOME_OBSERVED,)
        elif status is OfflineTrialStatus.OUTCOME_MISMATCH:
            observed = DemonstrationOutcomeStatus.SUCCESS
            reasons = (OfflineTrialReason.DIFFERENT_OUTCOME_OBSERVED,)
        else:
            observed = None
            reasons = (OfflineTrialReason.RESULT_UNAVAILABLE,)
        trials.append(
            OfflineTrialResult(
                candidate=candidate,
                holdout_episode=reference,
                observed_outcome=observed,
                status=status,
                reasons=reasons,
                result_source_ref='offline-runner.fixture.v1',
                result_source_fingerprint=fingerprint('offline-result-source', 'fixture'),
                metrics=(ExactMetric('outcome-agreement', int(status is OfflineTrialStatus.OUTCOME_MATCH), 1),),
            )
        )
    return evaluate_offline(corpus=corpus, candidate=candidate, trials=tuple(trials))


def fixture_promotion_bundle(label: str = 'one') -> dict[str, object]:
    corpus = fixture_corpus(label)
    candidate = fixture_candidate(corpus)
    report = fixture_report(corpus, candidate)
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
    request = CandidatePromotionRequest(
        candidate=candidate,
        report=report,
        criteria=criteria,
        target_stage=PromotionTargetStage.REVIEWED_CANDIDATE,
        provenance_ref='promotion-review.fixture.v1',
        provenance_fingerprint=fingerprint('promotion-review', label),
        note='Human-authored review context; never authority.',
    )
    decision = evaluate_promotion(
        criteria=criteria,
        request=request,
        candidate=candidate,
        report=report,
    )
    return {
        'corpus': corpus,
        'candidate': candidate,
        'report': report,
        'criteria': criteria,
        'request': request,
        'decision': decision,
    }


def fixture_rollback_bundle(label: str = 'one') -> dict[str, object]:
    promotion = fixture_promotion_bundle(label)
    candidate = promotion['candidate']
    decision = promotion['decision']
    known_good = KnownGoodPolicyReference(
        target_candidate=candidate,
        promotion_decision=decision,
        provenance_ref='known-good-review.fixture.v1',
        provenance_fingerprint=fingerprint('known-good-review', label),
    )
    current = fixture_candidate(promotion['corpus'], semantic_version='0.2.0')
    criteria = RollbackCriteria(
        current_candidate_id=current.candidate_id,
        current_candidate_fingerprint=current.candidate_fingerprint,
        known_good_id=known_good.known_good_id,
        known_good_fingerprint=known_good.known_good_fingerprint,
        allowed_reasons=(
            RollbackReason.EVALUATION_REGRESSION,
            RollbackReason.OPERATOR_REQUEST,
        ),
        minimum_evidence_references=1,
    )
    evidence = RollbackEvidenceReference(
        evidence_kind=RollbackEvidenceKind.EVALUATION_REPORT,
        source_ref='regression-report.fixture.v1',
        source_fingerprint=fingerprint('regression-report', label),
    )
    request = RollbackRequest(
        current_candidate=current,
        known_good=known_good,
        criteria=criteria,
        reason=RollbackReason.EVALUATION_REGRESSION,
        evidence_references=(evidence,),
        provenance_ref='rollback-review.fixture.v1',
        provenance_fingerprint=fingerprint('rollback-review', label),
        note='Evidence context only; never a runtime command.',
    )
    return {
        **promotion,
        'current_candidate': current,
        'known_good': known_good,
        'rollback_criteria': criteria,
        'rollback_evidence': evidence,
        'rollback_request': request,
    }
