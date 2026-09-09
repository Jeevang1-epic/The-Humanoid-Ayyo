"""Pure aggregation of explicit offline results; no candidate is ever executed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from ayyo_teach_mode import DemonstrationOutcomeStatus

from .candidate import CandidatePolicyManifest, verify_candidate_policy
from .canonical import canonical_json, semantic_sha256
from .corpus import (
    MAX_IDENTIFIER_LENGTH,
    MAX_METADATA_TEXT_LENGTH,
    MAX_EPISODES_PER_PARTITION,
    CorpusPartition,
    DemonstrationEpisodeReference,
    DemonstrationEvaluationCorpus,
)
from .corpus_serialization import verify_corpus
from .errors import (
    CandidateLineageError,
    EvaluationReportIntegrityError,
    EvaluationTrialError,
    HoldoutPartitionError,
)


OFFLINE_EVALUATION_CONTRACT_ID = 'ayyo.learning-evaluation.offline-trial.v1'
OFFLINE_EVALUATION_CONTRACT_VERSION = '1.0.0'
EVALUATION_REPORT_SCHEMA_ID = 'ayyo.learning-evaluation.offline-report.v1'
EVALUATION_REPORT_SCHEMA_VERSION = '1.0.0'

MAX_TRIALS_PER_EVALUATION = MAX_EPISODES_PER_PARTITION
MAX_TRIAL_REASONS = 8
MAX_METRICS_PER_TRIAL = 8
MAX_METRIC_COMPONENT = 1_000_000_000
MAX_SERIALIZED_REPORT_BYTES = 131_072

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_FINGERPRINT = re.compile(
    r'^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$'
)


class OfflineTrialStatus(StrEnum):
    OUTCOME_MATCH = 'outcome_match'
    OUTCOME_MISMATCH = 'outcome_mismatch'
    INCOMPLETE = 'incomplete'


class OfflineTrialReason(StrEnum):
    EXPECTED_OUTCOME_OBSERVED = 'expected_outcome_observed'
    DIFFERENT_OUTCOME_OBSERVED = 'different_outcome_observed'
    RESULT_UNAVAILABLE = 'result_unavailable'
    RESULT_REJECTED = 'result_rejected'
    UNSUPPORTED_RESULT = 'unsupported_result'


class OfflineEvaluationDisposition(StrEnum):
    MEETS_OFFLINE_CRITERIA = 'meets_offline_criteria'
    DOES_NOT_MEET_OFFLINE_CRITERIA = 'does_not_meet_offline_criteria'
    INCOMPLETE = 'incomplete'


class EvaluationReportReason(StrEnum):
    ALL_HOLDOUT_OUTCOMES_MATCH = 'all_holdout_outcomes_match'
    HOLDOUT_OUTCOME_MISMATCH = 'holdout_outcome_mismatch'
    MISSING_HOLDOUT_TRIAL = 'missing_holdout_trial'
    INCOMPLETE_HOLDOUT_TRIAL = 'incomplete_holdout_trial'


def _identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise EvaluationTrialError(f'{field_name} must be a bounded identifier')
    return value


def _fingerprint(value: object, field_name: str) -> str:
    value = _identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise EvaluationTrialError(f'{field_name} must be a SHA-256 identity')
    return value


@dataclass(frozen=True, slots=True)
class ExactMetric:
    metric_id: str
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _identifier(self.metric_id, 'metric_id')
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or not 0 <= self.numerator <= MAX_METRIC_COMPONENT
            or not 1 <= self.denominator <= MAX_METRIC_COMPONENT
        ):
            raise EvaluationTrialError('metric must use bounded exact integer components')

    def as_dict(self) -> dict[str, object]:
        return {
            'denominator': self.denominator,
            'metric_id': self.metric_id,
            'numerator': self.numerator,
        }


@dataclass(frozen=True, slots=True, init=False)
class OfflineTrialResult:
    evaluation_contract_id: str
    evaluation_contract_version: str
    trial_id: str
    trial_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    holdout_episode_id: str
    holdout_episode_fingerprint: str
    expected_outcome: DemonstrationOutcomeStatus
    observed_outcome: DemonstrationOutcomeStatus | None
    status: OfflineTrialStatus
    reasons: tuple[OfflineTrialReason, ...]
    metrics: tuple[ExactMetric, ...]
    result_source_ref: str
    result_source_fingerprint: str

    def __init__(
        self,
        *,
        candidate: CandidatePolicyManifest,
        holdout_episode: DemonstrationEpisodeReference,
        observed_outcome: DemonstrationOutcomeStatus | None,
        status: OfflineTrialStatus,
        reasons: tuple[OfflineTrialReason, ...] | list[OfflineTrialReason],
        result_source_ref: str,
        result_source_fingerprint: str,
        metrics: tuple[ExactMetric, ...] | list[ExactMetric] = (),
    ) -> None:
        if not verify_candidate_policy(candidate):
            raise EvaluationTrialError('trial requires a verified candidate manifest')
        if type(holdout_episode) is not DemonstrationEpisodeReference:
            raise EvaluationTrialError('trial requires one typed episode reference')
        if holdout_episode.partition is not CorpusPartition.HOLDOUT_EVALUATION:
            raise HoldoutPartitionError('candidate evidence cannot be used as a holdout trial')
        self._initialize(
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.candidate_fingerprint,
            holdout_episode_id=holdout_episode.episode_id,
            holdout_episode_fingerprint=holdout_episode.episode_fingerprint,
            expected_outcome=holdout_episode.outcome_status,
            observed_outcome=observed_outcome,
            status=status,
            reasons=reasons,
            metrics=metrics,
            result_source_ref=result_source_ref,
            result_source_fingerprint=result_source_fingerprint,
        )

    @classmethod
    def _from_fields(cls, **fields) -> OfflineTrialResult:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(
        self,
        *,
        candidate_id: str,
        candidate_fingerprint: str,
        holdout_episode_id: str,
        holdout_episode_fingerprint: str,
        expected_outcome: DemonstrationOutcomeStatus,
        observed_outcome: DemonstrationOutcomeStatus | None,
        status: OfflineTrialStatus,
        reasons: tuple[OfflineTrialReason, ...] | list[OfflineTrialReason],
        metrics: tuple[ExactMetric, ...] | list[ExactMetric],
        result_source_ref: str,
        result_source_fingerprint: str,
    ) -> None:
        candidate_id = _identifier(candidate_id, 'candidate_id')
        candidate_fingerprint = _fingerprint(candidate_fingerprint, 'candidate_fingerprint')
        holdout_episode_id = _identifier(holdout_episode_id, 'holdout_episode_id')
        holdout_episode_fingerprint = _fingerprint(
            holdout_episode_fingerprint, 'holdout_episode_fingerprint'
        )
        if not isinstance(expected_outcome, DemonstrationOutcomeStatus):
            raise EvaluationTrialError('expected outcome must use the Teach Mode enum')
        if observed_outcome is not None and not isinstance(
            observed_outcome, DemonstrationOutcomeStatus
        ):
            raise EvaluationTrialError('observed outcome must use the Teach Mode enum')
        if not isinstance(status, OfflineTrialStatus):
            raise EvaluationTrialError('trial status must use its closed enum')
        if isinstance(reasons, (str, bytes)):
            raise EvaluationTrialError('trial reasons must be a bounded sequence')
        try:
            reason_snapshot = tuple(reasons)
        except TypeError as error:
            raise EvaluationTrialError('trial reasons must be a bounded sequence') from error
        if (
            not 1 <= len(reason_snapshot) <= MAX_TRIAL_REASONS
            or not all(isinstance(item, OfflineTrialReason) for item in reason_snapshot)
            or len(reason_snapshot) != len(set(reason_snapshot))
        ):
            raise EvaluationTrialError('trial reasons are invalid, duplicate, or out of bounds')
        reason_snapshot = tuple(sorted(reason_snapshot, key=str))
        if isinstance(metrics, (str, bytes)):
            raise EvaluationTrialError('trial metrics must be a bounded sequence')
        try:
            metric_snapshot = tuple(metrics)
        except TypeError as error:
            raise EvaluationTrialError('trial metrics must be a bounded sequence') from error
        if (
            len(metric_snapshot) > MAX_METRICS_PER_TRIAL
            or not all(type(item) is ExactMetric for item in metric_snapshot)
            or len({item.metric_id for item in metric_snapshot}) != len(metric_snapshot)
        ):
            raise EvaluationTrialError('trial metrics are invalid, duplicate, or out of bounds')
        metric_snapshot = tuple(sorted(metric_snapshot, key=lambda item: item.metric_id))
        if status is OfflineTrialStatus.OUTCOME_MATCH and observed_outcome is not expected_outcome:
            raise EvaluationTrialError('OUTCOME_MATCH must preserve the expected outcome')
        if status is OfflineTrialStatus.OUTCOME_MISMATCH and (
            observed_outcome is None or observed_outcome is expected_outcome
        ):
            raise EvaluationTrialError('OUTCOME_MISMATCH requires a different observed outcome')
        if status is OfflineTrialStatus.INCOMPLETE and observed_outcome is not None:
            raise EvaluationTrialError('INCOMPLETE cannot fabricate an observed outcome')
        expected_reasons = {
            OfflineTrialStatus.OUTCOME_MATCH: {
                OfflineTrialReason.EXPECTED_OUTCOME_OBSERVED,
            },
            OfflineTrialStatus.OUTCOME_MISMATCH: {
                OfflineTrialReason.DIFFERENT_OUTCOME_OBSERVED,
            },
            OfflineTrialStatus.INCOMPLETE: {
                OfflineTrialReason.RESULT_UNAVAILABLE,
                OfflineTrialReason.RESULT_REJECTED,
                OfflineTrialReason.UNSUPPORTED_RESULT,
            },
        }
        if not set(reason_snapshot) <= expected_reasons[status]:
            raise EvaluationTrialError('trial reasons do not correspond to its status')
        result_source_ref = _identifier(result_source_ref, 'result_source_ref')
        result_source_fingerprint = _fingerprint(
            result_source_fingerprint, 'result_source_fingerprint'
        )
        object.__setattr__(self, 'evaluation_contract_id', OFFLINE_EVALUATION_CONTRACT_ID)
        object.__setattr__(self, 'evaluation_contract_version', OFFLINE_EVALUATION_CONTRACT_VERSION)
        object.__setattr__(self, 'candidate_id', candidate_id)
        object.__setattr__(self, 'candidate_fingerprint', candidate_fingerprint)
        object.__setattr__(self, 'holdout_episode_id', holdout_episode_id)
        object.__setattr__(self, 'holdout_episode_fingerprint', holdout_episode_fingerprint)
        object.__setattr__(self, 'expected_outcome', expected_outcome)
        object.__setattr__(self, 'observed_outcome', observed_outcome)
        object.__setattr__(self, 'status', status)
        object.__setattr__(self, 'reasons', reason_snapshot)
        object.__setattr__(self, 'metrics', metric_snapshot)
        object.__setattr__(self, 'result_source_ref', result_source_ref)
        object.__setattr__(self, 'result_source_fingerprint', result_source_fingerprint)
        fingerprint = self.recompute_fingerprint()
        object.__setattr__(self, 'trial_fingerprint', fingerprint)
        object.__setattr__(
            self,
            'trial_id',
            semantic_sha256(
                'offline-evaluation-trial',
                {
                    'evaluation_contract_id': self.evaluation_contract_id,
                    'evaluation_contract_version': self.evaluation_contract_version,
                    'trial_fingerprint': fingerprint,
                },
            ),
        )

    def semantic_document(self) -> dict[str, object]:
        return {
            'candidate': {
                'fingerprint': self.candidate_fingerprint,
                'id': self.candidate_id,
            },
            'evaluation_contract': {
                'id': self.evaluation_contract_id,
                'version': self.evaluation_contract_version,
            },
            'expected_outcome': self.expected_outcome.value,
            'holdout_episode': {
                'fingerprint': self.holdout_episode_fingerprint,
                'id': self.holdout_episode_id,
            },
            'metrics': [item.as_dict() for item in self.metrics],
            'observed_outcome': (
                self.observed_outcome.value if self.observed_outcome is not None else None
            ),
            'provenance': {
                'source_fingerprint': self.result_source_fingerprint,
                'source_ref': self.result_source_ref,
            },
            'reasons': [item.value for item in self.reasons],
            'status': self.status.value,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('offline-evaluation-trial-content', self.semantic_document())

    def recompute_trial_id(self) -> str:
        return semantic_sha256(
            'offline-evaluation-trial',
            {
                'evaluation_contract_id': self.evaluation_contract_id,
                'evaluation_contract_version': self.evaluation_contract_version,
                'trial_fingerprint': self.recompute_fingerprint(),
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'trial_fingerprint': self.trial_fingerprint,
            'trial_id': self.trial_id,
        }


def verify_trial_result(trial: object) -> bool:
    if type(trial) is not OfflineTrialResult:
        return False
    try:
        rebuilt = OfflineTrialResult._from_fields(
            candidate_id=trial.candidate_id,
            candidate_fingerprint=trial.candidate_fingerprint,
            holdout_episode_id=trial.holdout_episode_id,
            holdout_episode_fingerprint=trial.holdout_episode_fingerprint,
            expected_outcome=trial.expected_outcome,
            observed_outcome=trial.observed_outcome,
            status=trial.status,
            reasons=trial.reasons,
            metrics=trial.metrics,
            result_source_ref=trial.result_source_ref,
            result_source_fingerprint=trial.result_source_fingerprint,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == trial


@dataclass(frozen=True, slots=True)
class EvaluationCount:
    value: str
    count: int

    def __post_init__(self) -> None:
        _identifier(self.value, 'count value')
        if type(self.count) is not int or not 0 <= self.count <= MAX_TRIALS_PER_EVALUATION:
            raise EvaluationReportIntegrityError('evaluation count is outside v1 bounds')

    def as_dict(self) -> dict[str, object]:
        return {'count': self.count, 'value': self.value}


@dataclass(frozen=True, slots=True)
class AggregateExactMetric:
    metric_id: str
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _identifier(self.metric_id, 'aggregate metric_id')
        maximum = MAX_METRIC_COMPONENT * MAX_TRIALS_PER_EVALUATION
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or not 0 <= self.numerator <= maximum
            or not 1 <= self.denominator <= maximum
        ):
            raise EvaluationReportIntegrityError('aggregate metric is outside v1 bounds')

    def as_dict(self) -> dict[str, object]:
        return {
            'denominator': self.denominator,
            'metric_id': self.metric_id,
            'numerator': self.numerator,
        }


@dataclass(frozen=True, slots=True, init=False)
class OfflineEvaluationReport:
    schema_id: str
    schema_version: str
    report_id: str
    report_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    candidate_evidence_set_id: str
    candidate_evidence_set_fingerprint: str
    holdout_evidence_set_id: str
    holdout_evidence_set_fingerprint: str
    evaluation_contract_id: str
    evaluation_contract_version: str
    corpus: DemonstrationEvaluationCorpus
    trial_evidence: tuple[OfflineTrialResult, ...]
    trial_ids: tuple[str, ...]
    evaluated_holdout_episode_ids: tuple[str, ...]
    missing_holdout_episode_ids: tuple[str, ...]
    incomplete_holdout_episode_ids: tuple[str, ...]
    status_counts: tuple[EvaluationCount, ...]
    historical_outcome_counts: tuple[EvaluationCount, ...]
    aggregate_metrics: tuple[AggregateExactMetric, ...]
    coverage_numerator: int
    coverage_denominator: int
    reasons: tuple[EvaluationReportReason, ...]
    disposition: OfflineEvaluationDisposition

    @classmethod
    def _create(cls, **fields) -> OfflineEvaluationReport:
        instance = object.__new__(cls)
        object.__setattr__(instance, 'schema_id', EVALUATION_REPORT_SCHEMA_ID)
        object.__setattr__(instance, 'schema_version', EVALUATION_REPORT_SCHEMA_VERSION)
        for name, value in fields.items():
            object.__setattr__(instance, name, value)
        fingerprint = instance.recompute_fingerprint()
        object.__setattr__(instance, 'report_fingerprint', fingerprint)
        object.__setattr__(
            instance,
            'report_id',
            semantic_sha256(
                'offline-evaluation-report',
                {
                    'report_fingerprint': fingerprint,
                    'schema_id': instance.schema_id,
                    'schema_version': instance.schema_version,
                },
            ),
        )
        if len(canonical_json(instance.as_dict()).encode('utf-8')) > MAX_SERIALIZED_REPORT_BYTES:
            raise EvaluationReportIntegrityError('serialized report exceeds its v1 bound')
        return instance

    def semantic_document(self) -> dict[str, object]:
        return {
            'aggregate_metrics': [item.as_dict() for item in self.aggregate_metrics],
            'candidate': {'fingerprint': self.candidate_fingerprint, 'id': self.candidate_id},
            'candidate_evidence_set': {
                'fingerprint': self.candidate_evidence_set_fingerprint,
                'id': self.candidate_evidence_set_id,
            },
            'corpus': self.corpus.as_dict(),
            'coverage': {
                'denominator': self.coverage_denominator,
                'numerator': self.coverage_numerator,
            },
            'disposition': self.disposition.value,
            'evaluated_holdout_episode_ids': list(self.evaluated_holdout_episode_ids),
            'evaluation_contract': {
                'id': self.evaluation_contract_id,
                'version': self.evaluation_contract_version,
            },
            'historical_outcome_counts': [
                item.as_dict() for item in self.historical_outcome_counts
            ],
            'holdout_evidence_set': {
                'fingerprint': self.holdout_evidence_set_fingerprint,
                'id': self.holdout_evidence_set_id,
            },
            'incomplete_holdout_episode_ids': list(self.incomplete_holdout_episode_ids),
            'missing_holdout_episode_ids': list(self.missing_holdout_episode_ids),
            'reasons': [item.value for item in self.reasons],
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'status_counts': [item.as_dict() for item in self.status_counts],
            'trial_evidence': [item.as_dict() for item in self.trial_evidence],
            'trial_ids': list(self.trial_ids),
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('offline-evaluation-report-content', self.semantic_document())

    def recompute_report_id(self) -> str:
        return semantic_sha256(
            'offline-evaluation-report',
            {
                'report_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'report_fingerprint': self.report_fingerprint,
            'report_id': self.report_id,
        }


def _verified_ordered_trials(
    *,
    corpus: DemonstrationEvaluationCorpus,
    candidate_id: str,
    candidate_fingerprint: str,
    trials: object,
) -> tuple[OfflineTrialResult, ...]:
    _fingerprint(candidate_id, 'candidate_id')
    _fingerprint(candidate_fingerprint, 'candidate_fingerprint')
    if isinstance(trials, (str, bytes)):
        raise EvaluationTrialError('trials must be an explicit bounded sequence')
    try:
        trial_snapshot = tuple(trials)
    except TypeError as error:
        raise EvaluationTrialError('trials must be an explicit bounded sequence') from error
    if len(trial_snapshot) > MAX_TRIALS_PER_EVALUATION:
        raise EvaluationTrialError('trial count exceeds its v1 bound')
    if not all(type(item) is OfflineTrialResult for item in trial_snapshot):
        raise EvaluationTrialError('evaluation accepts only typed trial results')
    if not all(verify_trial_result(item) for item in trial_snapshot):
        raise EvaluationTrialError('a trial result failed integrity verification')
    episode_ids = tuple(item.holdout_episode_id for item in trial_snapshot)
    trial_ids = tuple(item.trial_id for item in trial_snapshot)
    if len(episode_ids) != len(set(episode_ids)) or len(trial_ids) != len(set(trial_ids)):
        raise EvaluationTrialError('duplicate trial or holdout episode result')

    candidate_episode_ids = {
        item.episode_id for item in corpus.candidate_evidence.episodes
    }
    holdout_by_id = {
        item.episode_id: item for item in corpus.holdout_evaluation.episodes
    }
    for trial in trial_snapshot:
        if (
            trial.candidate_id != candidate_id
            or trial.candidate_fingerprint != candidate_fingerprint
        ):
            raise CandidateLineageError('trial belongs to a different candidate')
        if (
            trial.evaluation_contract_id != OFFLINE_EVALUATION_CONTRACT_ID
            or trial.evaluation_contract_version != OFFLINE_EVALUATION_CONTRACT_VERSION
        ):
            raise EvaluationTrialError('trial uses an incompatible evaluation contract')
        if trial.holdout_episode_id in candidate_episode_ids:
            raise HoldoutPartitionError('candidate evidence is masquerading as holdout')
        reference = holdout_by_id.get(trial.holdout_episode_id)
        if reference is None:
            raise EvaluationTrialError('trial references an unknown holdout episode')
        if trial.holdout_episode_fingerprint != reference.episode_fingerprint:
            raise EvaluationTrialError('trial holdout episode fingerprint is wrong')
        if trial.expected_outcome is not reference.outcome_status:
            raise EvaluationTrialError('trial reinterprets the historical episode outcome')

    return tuple(sorted(trial_snapshot, key=lambda item: item.holdout_episode_id))


def _report_from_evidence(
    *,
    corpus: DemonstrationEvaluationCorpus,
    candidate_id: str,
    candidate_fingerprint: str,
    trials: object,
) -> OfflineEvaluationReport:
    ordered_trials = _verified_ordered_trials(
        corpus=corpus,
        candidate_id=candidate_id,
        candidate_fingerprint=candidate_fingerprint,
        trials=trials,
    )

    supplied_by_id = {item.holdout_episode_id: item for item in ordered_trials}
    holdout_by_id = {
        item.episode_id: item for item in corpus.holdout_evaluation.episodes
    }
    evaluated_ids = tuple(
        item.holdout_episode_id
        for item in ordered_trials
        if item.status is not OfflineTrialStatus.INCOMPLETE
    )
    incomplete_ids = tuple(
        item.holdout_episode_id
        for item in ordered_trials
        if item.status is OfflineTrialStatus.INCOMPLETE
    )
    missing_ids = tuple(sorted(set(holdout_by_id) - set(supplied_by_id)))
    status_counts = tuple(
        EvaluationCount(status.value, sum(item.status is status for item in ordered_trials))
        for status in OfflineTrialStatus
    )
    historical_counts = tuple(
        EvaluationCount(
            outcome.value,
            sum(item.outcome_status is outcome for item in corpus.holdout_evaluation.episodes),
        )
        for outcome in DemonstrationOutcomeStatus
    )
    metric_values: dict[str, list[int]] = {}
    for trial in ordered_trials:
        for metric in trial.metrics:
            totals = metric_values.setdefault(metric.metric_id, [0, 0])
            totals[0] += metric.numerator
            totals[1] += metric.denominator
    aggregate_metrics = tuple(
        AggregateExactMetric(metric_id, values[0], values[1])
        for metric_id, values in sorted(metric_values.items())
    )
    reasons = []
    if missing_ids:
        reasons.append(EvaluationReportReason.MISSING_HOLDOUT_TRIAL)
    if incomplete_ids:
        reasons.append(EvaluationReportReason.INCOMPLETE_HOLDOUT_TRIAL)
    if missing_ids or incomplete_ids:
        disposition = OfflineEvaluationDisposition.INCOMPLETE
    elif any(item.status is OfflineTrialStatus.OUTCOME_MISMATCH for item in ordered_trials):
        reasons.append(EvaluationReportReason.HOLDOUT_OUTCOME_MISMATCH)
        disposition = OfflineEvaluationDisposition.DOES_NOT_MEET_OFFLINE_CRITERIA
    else:
        reasons.append(EvaluationReportReason.ALL_HOLDOUT_OUTCOMES_MATCH)
        disposition = OfflineEvaluationDisposition.MEETS_OFFLINE_CRITERIA
    report = OfflineEvaluationReport._create(
        candidate_id=candidate_id,
        candidate_fingerprint=candidate_fingerprint,
        candidate_evidence_set_id=corpus.candidate_evidence.evidence_set_id,
        candidate_evidence_set_fingerprint=corpus.candidate_evidence.evidence_set_fingerprint,
        holdout_evidence_set_id=corpus.holdout_evaluation.evidence_set_id,
        holdout_evidence_set_fingerprint=corpus.holdout_evaluation.evidence_set_fingerprint,
        evaluation_contract_id=OFFLINE_EVALUATION_CONTRACT_ID,
        evaluation_contract_version=OFFLINE_EVALUATION_CONTRACT_VERSION,
        corpus=corpus,
        trial_evidence=ordered_trials,
        trial_ids=tuple(sorted(item.trial_id for item in ordered_trials)),
        evaluated_holdout_episode_ids=evaluated_ids,
        missing_holdout_episode_ids=missing_ids,
        incomplete_holdout_episode_ids=incomplete_ids,
        status_counts=status_counts,
        historical_outcome_counts=historical_counts,
        aggregate_metrics=aggregate_metrics,
        coverage_numerator=len(evaluated_ids),
        coverage_denominator=len(holdout_by_id),
        reasons=tuple(reasons),
        disposition=disposition,
    )
    return report


def verify_evaluation_report(report: object) -> bool:
    """Verify a report by rebuilding every summary from its concrete evidence."""
    if type(report) is not OfflineEvaluationReport:
        return False
    try:
        if (
            type(report.corpus) is not DemonstrationEvaluationCorpus
            or type(report.trial_evidence) is not tuple
            or not verify_corpus(report.corpus)
        ):
            return False
        rebuilt = _report_from_evidence(
            corpus=report.corpus,
            candidate_id=report.candidate_id,
            candidate_fingerprint=report.candidate_fingerprint,
            trials=report.trial_evidence,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == report


def evaluate_offline(
    *,
    corpus: DemonstrationEvaluationCorpus,
    candidate: CandidatePolicyManifest,
    trials: tuple[OfflineTrialResult, ...] | list[OfflineTrialResult],
) -> OfflineEvaluationReport:
    """Purely verify and aggregate explicit results; this never executes a policy."""
    if not verify_corpus(corpus):
        raise CandidateLineageError('evaluation requires a verified corpus')
    if not verify_candidate_policy(candidate):
        raise CandidateLineageError('evaluation requires a verified candidate')
    if (
        candidate.candidate_evidence_set_id
        != corpus.candidate_evidence.evidence_set_id
        or candidate.candidate_evidence_set_fingerprint
        != corpus.candidate_evidence.evidence_set_fingerprint
    ):
        raise CandidateLineageError('candidate does not belong to this corpus evidence set')
    report = _report_from_evidence(
        corpus=corpus,
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        trials=trials,
    )
    if not verify_evaluation_report(report):
        raise EvaluationReportIntegrityError('constructed report failed integrity verification')
    return report
