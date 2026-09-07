"""Strict canonical serialization for demonstration corpus manifests."""

from __future__ import annotations

import json

from ayyo_teach_mode import DemonstrationOutcomeStatus, DemonstrationSourceKind

from .canonical import canonical_json
from .corpus import (
    CORPUS_SCHEMA_ID,
    CORPUS_SCHEMA_VERSION,
    EVIDENCE_SET_SCHEMA_ID,
    EVIDENCE_SET_SCHEMA_VERSION,
    MAX_SERIALIZED_CORPUS_BYTES,
    CorpusPartition,
    DemonstrationEpisodeReference,
    DemonstrationEvaluationCorpus,
)
from .errors import CorpusConstructionError, CorpusIntegrityError


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CorpusIntegrityError('canonical corpus JSON contains a duplicate key')
        result[key] = value
    return result


def _reject_constant(value: str):
    raise CorpusIntegrityError(f'non-finite JSON constant is forbidden: {value}')


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise CorpusIntegrityError(f'{field_name} has unknown or missing fields')
    return value


def _list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise CorpusIntegrityError(f'{field_name} must be a JSON array')
    return value


def _closed_enum(enum_type, value: object, field_name: str):
    if type(value) is not str:
        raise CorpusIntegrityError(f'{field_name} must be a string enum')
    try:
        return enum_type(value)
    except ValueError as error:
        raise CorpusIntegrityError(f'{field_name} is not a v1 enum value') from error


def canonical_corpus_json(corpus: DemonstrationEvaluationCorpus) -> str:
    if not verify_corpus(corpus):
        raise CorpusIntegrityError('corpus identity does not match its content')
    encoded = canonical_json(corpus.as_dict())
    if len(encoded.encode('utf-8')) > MAX_SERIALIZED_CORPUS_BYTES:
        raise CorpusIntegrityError('serialized corpus exceeds its v1 bound')
    return encoded


def verify_corpus(corpus: object) -> bool:
    if type(corpus) is not DemonstrationEvaluationCorpus:
        return False
    try:
        rebuilt = DemonstrationEvaluationCorpus._from_references(
            candidate_evidence=corpus.candidate_evidence.episodes,
            holdout_evaluation=corpus.holdout_evaluation.episodes,
            description=corpus.description,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == corpus


def _reference(value: object, expected_partition: CorpusPartition):
    item = _mapping(
        value,
        'episode reference',
        {
            'capture_policy',
            'episode_fingerprint',
            'episode_id',
            'outcome_status',
            'partition',
            'robot_id',
            'source_kind',
        },
    )
    policy = _mapping(item['capture_policy'], 'capture policy', {'fingerprint', 'id', 'version'})
    partition = _closed_enum(CorpusPartition, item['partition'], 'partition')
    if partition is not expected_partition:
        raise CorpusIntegrityError('episode reference is in the wrong partition')
    return DemonstrationEpisodeReference(
        episode_id=item['episode_id'],
        episode_fingerprint=item['episode_fingerprint'],
        partition=partition,
        robot_id=item['robot_id'],
        source_kind=_closed_enum(DemonstrationSourceKind, item['source_kind'], 'source kind'),
        outcome_status=_closed_enum(
            DemonstrationOutcomeStatus, item['outcome_status'], 'outcome status'
        ),
        capture_policy_id=policy['id'],
        capture_policy_version=policy['version'],
        capture_policy_fingerprint=policy['fingerprint'],
    )


def _evidence_set(value: object, expected_partition: CorpusPartition):
    document = _mapping(
        value,
        'evidence set',
        {
            'episodes',
            'evidence_set_fingerprint',
            'evidence_set_id',
            'partition',
            'schema',
        },
    )
    schema = _mapping(document['schema'], 'evidence-set schema', {'id', 'version'})
    if schema != {'id': EVIDENCE_SET_SCHEMA_ID, 'version': EVIDENCE_SET_SCHEMA_VERSION}:
        raise CorpusIntegrityError('evidence-set schema identity is incompatible')
    partition = _closed_enum(CorpusPartition, document['partition'], 'evidence-set partition')
    if partition is not expected_partition:
        raise CorpusIntegrityError('evidence-set partition is incompatible')
    references = tuple(
        _reference(item, partition) for item in _list(document['episodes'], 'episodes')
    )
    return references, document['evidence_set_id'], document['evidence_set_fingerprint']


def corpus_from_canonical_json(payload: str | bytes) -> DemonstrationEvaluationCorpus:
    if isinstance(payload, bytes):
        raw = payload
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise CorpusIntegrityError('corpus JSON is not valid UTF-8') from error
    elif type(payload) is str:
        text = payload
        raw = payload.encode('utf-8')
    else:
        raise CorpusIntegrityError('corpus JSON must be text or bytes')
    if not raw or len(raw) > MAX_SERIALIZED_CORPUS_BYTES:
        raise CorpusIntegrityError('corpus JSON is empty or exceeds the v1 bound')
    try:
        document = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except CorpusIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CorpusIntegrityError('corpus JSON is malformed') from error
    if canonical_json(document).encode('utf-8') != raw:
        raise CorpusIntegrityError('corpus JSON is not canonical')
    root = _mapping(
        document,
        'corpus document',
        {
            'candidate_evidence',
            'compatibility',
            'corpus_fingerprint',
            'corpus_id',
            'description',
            'holdout_evaluation',
            'schema',
        },
    )
    schema = _mapping(root['schema'], 'corpus schema', {'id', 'version'})
    if schema != {'id': CORPUS_SCHEMA_ID, 'version': CORPUS_SCHEMA_VERSION}:
        raise CorpusIntegrityError('corpus schema identity is incompatible')
    compatibility = _mapping(
        root['compatibility'], 'compatibility', {'robot_ids', 'source_kinds'}
    )
    candidate, candidate_id, candidate_fingerprint = _evidence_set(
        root['candidate_evidence'], CorpusPartition.CANDIDATE_EVIDENCE
    )
    holdout, holdout_id, holdout_fingerprint = _evidence_set(
        root['holdout_evaluation'], CorpusPartition.HOLDOUT_EVALUATION
    )
    try:
        corpus = DemonstrationEvaluationCorpus._from_references(
            candidate_evidence=candidate,
            holdout_evaluation=holdout,
            description=root['description'],
        )
    except CorpusConstructionError as error:
        raise CorpusIntegrityError('corpus content violates the v1 contract') from error
    expected_compatibility = {
        'robot_ids': list(corpus.robot_ids),
        'source_kinds': [item.value for item in corpus.source_kinds],
    }
    if compatibility != expected_compatibility:
        raise CorpusIntegrityError('corpus compatibility information was tampered')
    stored = (
        root['corpus_id'],
        root['corpus_fingerprint'],
        candidate_id,
        candidate_fingerprint,
        holdout_id,
        holdout_fingerprint,
    )
    rebuilt = (
        corpus.corpus_id,
        corpus.corpus_fingerprint,
        corpus.candidate_evidence.evidence_set_id,
        corpus.candidate_evidence.evidence_set_fingerprint,
        corpus.holdout_evaluation.evidence_set_id,
        corpus.holdout_evaluation.evidence_set_fingerprint,
    )
    if stored != rebuilt or corpus.as_dict() != root:
        raise CorpusIntegrityError('corpus or episode-reference identity was tampered')
    return corpus
