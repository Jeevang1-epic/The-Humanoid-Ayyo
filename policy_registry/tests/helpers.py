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

from ayyo_policy_registry import (
    CandidateRegistrationRequest,
    PolicyRegistrySnapshot,
    RegisteredPolicyVersion,
    register_candidate,
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
        description=f'Explicit deterministic {label} registry fixture corpus.',
    )


def fixture_candidate(
    corpus: DemonstrationEvaluationCorpus,
    *,
    semantic_version: str = '0.1.0',
    policy_family_id: str = 'ayyo.demonstration-policy.v1',
    input_contract_id: str = 'ayyo.demonstration-input.v1',
    input_contract_version: str = '1.0.0',
    output_contract_id: str = 'ayyo.demonstration-output.v1',
    output_contract_version: str = '1.0.0',
    parent_candidate_id: str | None = None,
    parent_candidate_fingerprint: str | None = None,
) -> CandidatePolicyManifest:
    return CandidatePolicyManifest(
        candidate_evidence=corpus.candidate_evidence,
        semantic_version=semantic_version,
        policy_family_id=policy_family_id,
        input_contract_id=input_contract_id,
        input_contract_version=input_contract_version,
        output_contract_id=output_contract_id,
        output_contract_version=output_contract_version,
        description=f'Inert registry fixture candidate {semantic_version}.',
        parent_candidate_id=parent_candidate_id,
        parent_candidate_fingerprint=parent_candidate_fingerprint,
    )


def fixture_report(corpus, candidate):
    trials = tuple(
        OfflineTrialResult(
            candidate=candidate,
            holdout_episode=reference,
            observed_outcome=reference.outcome_status,
            status=OfflineTrialStatus.OUTCOME_MATCH,
            reasons=(OfflineTrialReason.EXPECTED_OUTCOME_OBSERVED,),
            result_source_ref='offline-runner.registry-fixture.v1',
            result_source_fingerprint=fingerprint('offline-result-source', 'registry'),
            metrics=(ExactMetric('outcome-agreement', 1, 1),),
        )
        for reference in corpus.holdout_evaluation.episodes
    )
    return evaluate_offline(corpus=corpus, candidate=candidate, trials=trials)


def fixture_registration_bundle(
    label: str = 'one',
    *,
    semantic_version: str = '0.1.0',
    policy_family_id: str = 'ayyo.demonstration-policy.v1',
    input_contract_id: str = 'ayyo.demonstration-input.v1',
    input_contract_version: str = '1.0.0',
    output_contract_id: str = 'ayyo.demonstration-output.v1',
    output_contract_version: str = '1.0.0',
    parent_candidate_id: str | None = None,
    parent_candidate_fingerprint: str | None = None,
    registration_target_stage: PromotionTargetStage = PromotionTargetStage.REVIEWED_CANDIDATE,
) -> dict[str, object]:
    corpus = fixture_corpus(label)
    candidate = fixture_candidate(
        corpus,
        semantic_version=semantic_version,
        policy_family_id=policy_family_id,
        input_contract_id=input_contract_id,
        input_contract_version=input_contract_version,
        output_contract_id=output_contract_id,
        output_contract_version=output_contract_version,
        parent_candidate_id=parent_candidate_id,
        parent_candidate_fingerprint=parent_candidate_fingerprint,
    )
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
    promotion_request = CandidatePromotionRequest(
        candidate=candidate,
        report=report,
        criteria=criteria,
        target_stage=PromotionTargetStage.REVIEWED_CANDIDATE,
        provenance_ref='promotion-review.registry-fixture.v1',
        provenance_fingerprint=fingerprint('promotion-review', label),
    )
    decision = evaluate_promotion(
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
        promotion_decision=decision,
        target_stage=registration_target_stage,
        provenance_ref='policy-registry-review.fixture.v1',
        provenance_fingerprint=fingerprint('policy-registry-review', label),
        note='Evidence registration only; never activation authority.',
    )
    return {
        'snapshot': PolicyRegistrySnapshot(),
        'corpus': corpus,
        'candidate': candidate,
        'report': report,
        'criteria': criteria,
        'promotion_request': promotion_request,
        'decision': decision,
        'registration_request': registration_request,
    }


def register_bundle(bundle: dict[str, object], snapshot=None):
    return register_candidate(
        previous_snapshot=snapshot or bundle['snapshot'],
        request=bundle['registration_request'],
        candidate=bundle['candidate'],
        evaluation_report=bundle['report'],
        promotion_criteria=bundle['criteria'],
        promotion_request=bundle['promotion_request'],
        promotion_decision=bundle['decision'],
    )


def rebuild_registration_request(request, **overrides):
    fields = {
        name: getattr(request, name)
        for name in CandidateRegistrationRequest.__annotations__
        if name
        not in {
            'schema_id',
            'schema_version',
            'registration_request_id',
            'registration_request_fingerprint',
        }
    }
    fields.update(overrides)
    return CandidateRegistrationRequest._from_fields(**fields)


def rebuild_registered_version(record, **overrides):
    fields = {
        name: getattr(record, name)
        for name in RegisteredPolicyVersion.__annotations__
        if name not in {'schema_id', 'schema_version', 'record_id', 'record_fingerprint'}
    }
    fields.update(overrides)
    return RegisteredPolicyVersion._from_fields(**fields)
