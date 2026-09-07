from __future__ import annotations

from hashlib import sha256

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

from ayyo_learning_evaluation import (
    CandidatePolicyManifest,
    DemonstrationEvaluationCorpus,
    ExactMetric,
    OfflineTrialReason,
    OfflineTrialResult,
    OfflineTrialStatus,
)


def fingerprint(prefix: str, value: str) -> str:
    return f'{prefix}-sha256-{sha256(value.encode()).hexdigest()}'


def fixture_episode(
    label: str = 'one',
    outcome: DemonstrationOutcomeStatus = DemonstrationOutcomeStatus.SUCCESS,
) -> DemonstrationEpisode:
    source_ref = f'fixture-source-{label}'
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
            source_ref=source_ref,
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


def fixture_corpus() -> DemonstrationEvaluationCorpus:
    return DemonstrationEvaluationCorpus(
        candidate_evidence=(fixture_episode('candidate'),),
        holdout_evaluation=(
            fixture_episode('holdout-deferred', DemonstrationOutcomeStatus.DEFERRED),
            fixture_episode('holdout-rejected', DemonstrationOutcomeStatus.REJECTED),
        ),
        description='Explicit deterministic fixture corpus.',
    )


def fixture_candidate(corpus=None, **overrides) -> CandidatePolicyManifest:
    corpus = corpus or fixture_corpus()
    arguments = {
        'candidate_evidence': corpus.candidate_evidence,
        'semantic_version': '0.1.0',
        'policy_family_id': 'ayyo.demonstration-policy.v1',
        'input_contract_id': 'ayyo.demonstration-input.v1',
        'input_contract_version': '1.0.0',
        'output_contract_id': 'ayyo.demonstration-outcome.v1',
        'output_contract_version': '1.0.0',
        'description': 'Inert candidate for offline review only.',
    }
    arguments.update(overrides)
    return CandidatePolicyManifest(**arguments)


def matching_trial(candidate, reference, **overrides) -> OfflineTrialResult:
    arguments = {
        'candidate': candidate,
        'holdout_episode': reference,
        'observed_outcome': reference.outcome_status,
        'status': OfflineTrialStatus.OUTCOME_MATCH,
        'reasons': (OfflineTrialReason.EXPECTED_OUTCOME_OBSERVED,),
        'result_source_ref': 'offline-runner.fixture.v1',
        'result_source_fingerprint': fingerprint('offline-result-source', 'fixture'),
        'metrics': (ExactMetric('outcome-agreement', 1, 1),),
    }
    arguments.update(overrides)
    return OfflineTrialResult(**arguments)
