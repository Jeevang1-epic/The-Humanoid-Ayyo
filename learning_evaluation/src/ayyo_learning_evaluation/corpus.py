"""Immutable bounded corpus manifests over verified Teach Mode episodes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata

from ayyo_teach_mode import (
    CAPTURE_POLICY_ID,
    CAPTURE_POLICY_VERSION,
    DemonstrationEpisode,
    DemonstrationOutcomeStatus,
    DemonstrationSourceKind,
    verify_episode,
)

from .canonical import canonical_json, semantic_sha256
from .errors import CorpusConstructionError


CORPUS_SCHEMA_ID = 'ayyo.learning-evaluation.demonstration-corpus.v1'
CORPUS_SCHEMA_VERSION = '1.0.0'
EVIDENCE_SET_SCHEMA_ID = 'ayyo.learning-evaluation.demonstration-evidence-set.v1'
EVIDENCE_SET_SCHEMA_VERSION = '1.0.0'

MAX_EPISODES_PER_CORPUS = 32
MAX_EPISODES_PER_PARTITION = 16
MAX_IDENTIFIER_LENGTH = 256
MAX_METADATA_TEXT_LENGTH = 512
MAX_SERIALIZED_CORPUS_BYTES = 65_536

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_FINGERPRINT = re.compile(
    r'^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$'
)


class CorpusPartition(StrEnum):
    CANDIDATE_EVIDENCE = 'candidate_evidence'
    HOLDOUT_EVALUATION = 'holdout_evaluation'


def _identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise CorpusConstructionError(f'{field_name} must be a bounded identifier')
    return value


def _fingerprint(value: object, field_name: str) -> str:
    value = _identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise CorpusConstructionError(f'{field_name} must be a SHA-256 identity')
    return value


def _description(value: object) -> str:
    if type(value) is not str:
        raise CorpusConstructionError('corpus description must be text')
    normalized = unicodedata.normalize('NFC', value)
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > MAX_METADATA_TEXT_LENGTH
        or any(unicodedata.category(character) in {'Cc', 'Cs'} for character in normalized)
    ):
        raise CorpusConstructionError('corpus description violates the v1 text bound')
    return normalized


def _bounded_sequence(value: object, field_name: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)):
        raise CorpusConstructionError(f'{field_name} must be an explicit sequence')
    try:
        snapshot = tuple(value)
    except TypeError as error:
        raise CorpusConstructionError(
            f'{field_name} must be an explicit sequence'
        ) from error
    if len(snapshot) > MAX_EPISODES_PER_PARTITION:
        raise CorpusConstructionError(f'{field_name} exceeds its v1 bound')
    if not snapshot:
        raise CorpusConstructionError(f'{field_name} must not be empty')
    return snapshot


@dataclass(frozen=True, slots=True)
class DemonstrationEpisodeReference:
    episode_id: str
    episode_fingerprint: str
    partition: CorpusPartition
    robot_id: str | None
    source_kind: DemonstrationSourceKind
    outcome_status: DemonstrationOutcomeStatus
    capture_policy_id: str
    capture_policy_version: str
    capture_policy_fingerprint: str

    def __post_init__(self) -> None:
        _identifier(self.episode_id, 'episode_id')
        _fingerprint(self.episode_fingerprint, 'episode_fingerprint')
        if not isinstance(self.partition, CorpusPartition):
            raise CorpusConstructionError('partition must use its closed enum')
        if self.robot_id is not None:
            _identifier(self.robot_id, 'robot_id')
        if not isinstance(self.source_kind, DemonstrationSourceKind):
            raise CorpusConstructionError('source_kind must use the Teach Mode enum')
        if not isinstance(self.outcome_status, DemonstrationOutcomeStatus):
            raise CorpusConstructionError('outcome_status must use the Teach Mode enum')
        _identifier(self.capture_policy_id, 'capture_policy_id')
        _identifier(self.capture_policy_version, 'capture_policy_version')
        _fingerprint(self.capture_policy_fingerprint, 'capture_policy_fingerprint')
        if (
            self.capture_policy_id != CAPTURE_POLICY_ID
            or self.capture_policy_version != CAPTURE_POLICY_VERSION
        ):
            raise CorpusConstructionError('episode capture policy is incompatible')

    @classmethod
    def from_verified_episode(
        cls,
        episode: DemonstrationEpisode,
        partition: CorpusPartition,
    ) -> DemonstrationEpisodeReference:
        verification = verify_episode(episode)
        if not verification.verified:
            raise CorpusConstructionError(
                'every corpus episode must pass Teach Mode integrity verification'
            )
        return cls(
            episode_id=episode.episode_id,
            episode_fingerprint=episode.episode_fingerprint,
            partition=partition,
            robot_id=episode.robot_id,
            source_kind=episode.source_kind,
            outcome_status=episode.outcome.status,
            capture_policy_id=episode.capture_policy_id,
            capture_policy_version=episode.capture_policy_version,
            capture_policy_fingerprint=episode.capture_policy_fingerprint,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            'capture_policy': {
                'fingerprint': self.capture_policy_fingerprint,
                'id': self.capture_policy_id,
                'version': self.capture_policy_version,
            },
            'episode_fingerprint': self.episode_fingerprint,
            'episode_id': self.episode_id,
            'outcome_status': self.outcome_status.value,
            'partition': self.partition.value,
            'robot_id': self.robot_id,
            'source_kind': self.source_kind.value,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationEvidenceSet:
    schema_id: str
    schema_version: str
    partition: CorpusPartition
    evidence_set_id: str
    evidence_set_fingerprint: str
    episodes: tuple[DemonstrationEpisodeReference, ...]

    def __init__(
        self,
        partition: CorpusPartition,
        episodes: tuple[DemonstrationEpisodeReference, ...]
        | list[DemonstrationEpisodeReference],
    ) -> None:
        if not isinstance(partition, CorpusPartition):
            raise CorpusConstructionError('evidence-set partition is invalid')
        if isinstance(episodes, (str, bytes)):
            raise CorpusConstructionError('evidence-set episodes must be a sequence')
        try:
            snapshot = tuple(episodes)
        except TypeError as error:
            raise CorpusConstructionError('evidence-set episodes must be a sequence') from error
        if not 1 <= len(snapshot) <= MAX_EPISODES_PER_PARTITION:
            raise CorpusConstructionError('evidence-set episode count violates v1 bounds')
        if not all(type(item) is DemonstrationEpisodeReference for item in snapshot):
            raise CorpusConstructionError('evidence-set contains an invalid reference')
        if any(item.partition is not partition for item in snapshot):
            raise CorpusConstructionError('evidence-set reference partition mismatch')
        ordered = tuple(sorted(snapshot, key=lambda item: item.episode_id))
        identities = tuple(item.episode_id for item in ordered)
        if len(identities) != len(set(identities)):
            raise CorpusConstructionError('duplicate episode identity in partition')
        object.__setattr__(self, 'schema_id', EVIDENCE_SET_SCHEMA_ID)
        object.__setattr__(self, 'schema_version', EVIDENCE_SET_SCHEMA_VERSION)
        object.__setattr__(self, 'partition', partition)
        object.__setattr__(self, 'episodes', ordered)
        fingerprint = self.recompute_fingerprint()
        object.__setattr__(self, 'evidence_set_fingerprint', fingerprint)
        object.__setattr__(
            self,
            'evidence_set_id',
            semantic_sha256(
                'demonstration-evidence-set',
                {
                    'evidence_set_fingerprint': fingerprint,
                    'schema_id': self.schema_id,
                    'schema_version': self.schema_version,
                },
            ),
        )

    def semantic_document(self) -> dict[str, object]:
        return {
            'episodes': [item.as_dict() for item in self.episodes],
            'partition': self.partition.value,
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('demonstration-evidence-set-content', self.semantic_document())

    def recompute_evidence_set_id(self) -> str:
        return semantic_sha256(
            'demonstration-evidence-set',
            {
                'evidence_set_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'evidence_set_fingerprint': self.evidence_set_fingerprint,
            'evidence_set_id': self.evidence_set_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationEvaluationCorpus:
    schema_id: str
    schema_version: str
    corpus_id: str
    corpus_fingerprint: str
    description: str
    robot_ids: tuple[str, ...]
    source_kinds: tuple[DemonstrationSourceKind, ...]
    candidate_evidence: DemonstrationEvidenceSet
    holdout_evaluation: DemonstrationEvidenceSet

    def __init__(
        self,
        *,
        candidate_evidence: tuple[DemonstrationEpisode, ...] | list[DemonstrationEpisode],
        holdout_evaluation: tuple[DemonstrationEpisode, ...] | list[DemonstrationEpisode],
        description: str,
    ) -> None:
        candidate_items = _bounded_sequence(candidate_evidence, 'candidate evidence')
        holdout_items = _bounded_sequence(holdout_evaluation, 'holdout evaluation')
        if len(candidate_items) + len(holdout_items) > MAX_EPISODES_PER_CORPUS:
            raise CorpusConstructionError('corpus exceeds its total episode bound')
        if not all(type(item) is DemonstrationEpisode for item in candidate_items + holdout_items):
            raise CorpusConstructionError('corpus accepts only DemonstrationEpisode objects')
        candidate_references = tuple(
            DemonstrationEpisodeReference.from_verified_episode(
                item, CorpusPartition.CANDIDATE_EVIDENCE
            )
            for item in candidate_items
        )
        holdout_references = tuple(
            DemonstrationEpisodeReference.from_verified_episode(
                item, CorpusPartition.HOLDOUT_EVALUATION
            )
            for item in holdout_items
        )
        self._initialize(candidate_references, holdout_references, description)

    @classmethod
    def _from_references(
        cls,
        *,
        candidate_evidence: tuple[DemonstrationEpisodeReference, ...],
        holdout_evaluation: tuple[DemonstrationEpisodeReference, ...],
        description: str,
    ) -> DemonstrationEvaluationCorpus:
        instance = object.__new__(cls)
        instance._initialize(candidate_evidence, holdout_evaluation, description)
        return instance

    def _initialize(
        self,
        candidate_references: tuple[DemonstrationEpisodeReference, ...],
        holdout_references: tuple[DemonstrationEpisodeReference, ...],
        description: str,
    ) -> None:
        if len(candidate_references) + len(holdout_references) > MAX_EPISODES_PER_CORPUS:
            raise CorpusConstructionError('corpus exceeds its total episode bound')
        candidate_set = DemonstrationEvidenceSet(
            CorpusPartition.CANDIDATE_EVIDENCE, candidate_references
        )
        holdout_set = DemonstrationEvidenceSet(
            CorpusPartition.HOLDOUT_EVALUATION, holdout_references
        )
        candidate_ids = {item.episode_id for item in candidate_set.episodes}
        holdout_ids = {item.episode_id for item in holdout_set.episodes}
        if candidate_ids & holdout_ids:
            raise CorpusConstructionError('an episode cannot occur in both partitions')
        all_references = candidate_set.episodes + holdout_set.episodes
        robot_ids = tuple(sorted({item.robot_id for item in all_references if item.robot_id}))
        source_kinds = tuple(sorted({item.source_kind for item in all_references}, key=str))
        object.__setattr__(self, 'schema_id', CORPUS_SCHEMA_ID)
        object.__setattr__(self, 'schema_version', CORPUS_SCHEMA_VERSION)
        object.__setattr__(self, 'description', _description(description))
        object.__setattr__(self, 'robot_ids', robot_ids)
        object.__setattr__(self, 'source_kinds', source_kinds)
        object.__setattr__(self, 'candidate_evidence', candidate_set)
        object.__setattr__(self, 'holdout_evaluation', holdout_set)
        fingerprint = self.recompute_fingerprint()
        object.__setattr__(self, 'corpus_fingerprint', fingerprint)
        object.__setattr__(
            self,
            'corpus_id',
            semantic_sha256(
                'demonstration-evaluation-corpus',
                {
                    'corpus_fingerprint': fingerprint,
                    'schema_id': self.schema_id,
                    'schema_version': self.schema_version,
                },
            ),
        )
        if len(canonical_json(self.as_dict()).encode('utf-8')) > MAX_SERIALIZED_CORPUS_BYTES:
            raise CorpusConstructionError('serialized corpus exceeds its v1 bound')

    def semantic_document(self) -> dict[str, object]:
        return {
            'candidate_evidence': self.candidate_evidence.as_dict(),
            'compatibility': {
                'robot_ids': list(self.robot_ids),
                'source_kinds': [item.value for item in self.source_kinds],
            },
            'description': self.description,
            'holdout_evaluation': self.holdout_evaluation.as_dict(),
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256(
            'demonstration-evaluation-corpus-content', self.semantic_document()
        )

    def recompute_corpus_id(self) -> str:
        return semantic_sha256(
            'demonstration-evaluation-corpus',
            {
                'corpus_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'corpus_fingerprint': self.corpus_fingerprint,
            'corpus_id': self.corpus_id,
        }
