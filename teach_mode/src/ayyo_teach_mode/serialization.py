"""Canonical in-memory JSON export and import for completed episodes."""

from __future__ import annotations

import json

from .canonical import canonical_json
from .errors import DemonstrationIntegrityError, DemonstrationValidationError
from .models import (
    CAPTURE_POLICY_ID,
    CAPTURE_POLICY_VERSION,
    MAX_SERIALIZED_EPISODE_BYTES,
    TEACH_MODE_SCHEMA_ID,
    TEACH_MODE_SCHEMA_VERSION,
    DemonstrationActionAuthority,
    DemonstrationActionDisposition,
    DemonstrationActionKind,
    DemonstrationActionReference,
    DemonstrationActionUnit,
    DemonstrationAnnotation,
    DemonstrationAnnotationKind,
    DemonstrationCapturePolicy,
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
    ReferenceEvidenceStatus,
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DemonstrationIntegrityError('canonical JSON contains a duplicate key')
        result[key] = value
    return result


def _reject_constant(value: str):
    raise DemonstrationIntegrityError(f'non-finite JSON constant is forbidden: {value}')


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise DemonstrationIntegrityError(f'{field_name} has unknown or missing fields')
    return value


def _list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise DemonstrationIntegrityError(f'{field_name} must be a JSON array')
    return value


def _enum(enum_type, value: object, field_name: str):
    if type(value) is not str:
        raise DemonstrationIntegrityError(f'{field_name} must be a string enum')
    try:
        return enum_type(value)
    except ValueError as error:
        raise DemonstrationIntegrityError(f'{field_name} is not a v1 enum value') from error


def canonical_episode_json(episode: DemonstrationEpisode) -> str:
    """Return byte-deterministic canonical JSON without writing it anywhere."""
    if type(episode) is not DemonstrationEpisode:
        raise DemonstrationIntegrityError('canonical export requires an episode')
    if (
        episode.episode_fingerprint != episode.recompute_fingerprint()
        or episode.episode_id != episode.recompute_episode_id()
    ):
        raise DemonstrationIntegrityError('episode identity does not match its content')
    encoded = canonical_json(episode.as_dict())
    if len(encoded.encode('utf-8')) > MAX_SERIALIZED_EPISODE_BYTES:
        raise DemonstrationIntegrityError('serialized episode exceeds the v1 bound')
    return encoded


def episode_from_canonical_json(payload: str | bytes) -> DemonstrationEpisode:
    """Deserialize only exact canonical v1 JSON and verify every stored identity."""
    if isinstance(payload, bytes):
        raw = payload
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise DemonstrationIntegrityError('episode JSON is not valid UTF-8') from error
    elif type(payload) is str:
        text = payload
        raw = text.encode('utf-8')
    else:
        raise DemonstrationIntegrityError('episode JSON must be text or bytes')
    if not raw or len(raw) > MAX_SERIALIZED_EPISODE_BYTES:
        raise DemonstrationIntegrityError('episode JSON is empty or exceeds the v1 bound')
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except DemonstrationIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DemonstrationIntegrityError('episode JSON is malformed') from error
    if canonical_json(document).encode('utf-8') != raw:
        raise DemonstrationIntegrityError('episode JSON is not canonical')
    root = _mapping(
        document,
        'episode document',
        {
            'capture_policy',
            'episode_fingerprint',
            'episode_id',
            'events',
            'outcome',
            'provenance',
            'robot_id',
            'schema',
            'source_kind',
            'source_time',
        },
    )
    schema = _mapping(root['schema'], 'schema', {'id', 'version'})
    if schema != {'id': TEACH_MODE_SCHEMA_ID, 'version': TEACH_MODE_SCHEMA_VERSION}:
        raise DemonstrationIntegrityError('episode schema identity is incompatible')
    policy_document = _mapping(
        root['capture_policy'], 'capture policy', {'fingerprint', 'id', 'version'}
    )
    policy = DemonstrationCapturePolicy()
    if policy_document != {
        'fingerprint': policy.fingerprint,
        'id': CAPTURE_POLICY_ID,
        'version': CAPTURE_POLICY_VERSION,
    }:
        raise DemonstrationIntegrityError('capture policy identity is incompatible')
    source_time_document = _mapping(
        root['source_time'], 'source time', {'clock_kind', 'end_ns', 'start_ns'}
    )
    provenance_document = _mapping(
        root['provenance'],
        'provenance',
        {'source_fingerprint', 'source_ref', 'teacher_source_ref'},
    )
    events = []
    for event_value in _list(root['events'], 'events'):
        event_document = _mapping(
            event_value,
            'event',
            {
                'action_references',
                'annotations',
                'event_id',
                'event_type',
                'observation_references',
                'sequence_index',
                'source_time_ns',
            },
        )
        observations = []
        for reference_value in _list(
            event_document['observation_references'], 'observation references'
        ):
            reference = _mapping(
                reference_value,
                'observation reference',
                {
                    'fingerprint',
                    'interface_id',
                    'kind',
                    'provenance_kind',
                    'reference_id',
                    'status',
                },
            )
            observations.append(
                DemonstrationObservationReference(
                    kind=_enum(
                        ObservationReferenceKind,
                        reference['kind'],
                        'observation reference kind',
                    ),
                    reference_id=reference['reference_id'],
                    status=_enum(
                        ReferenceEvidenceStatus,
                        reference['status'],
                        'observation reference status',
                    ),
                    fingerprint=reference['fingerprint'],
                    provenance_kind=reference['provenance_kind'],
                    interface_id=reference['interface_id'],
                )
            )
        actions = []
        for action_value in _list(
            event_document['action_references'], 'action references'
        ):
            action = _mapping(
                action_value,
                'action reference',
                {
                    'action_id',
                    'authority',
                    'disposition',
                    'evidence_ref',
                    'kind',
                    'reason_code',
                    'target_id',
                    'target_unit',
                    'target_value',
                },
            )
            actions.append(
                DemonstrationActionReference(
                    action_id=action['action_id'],
                    kind=_enum(
                        DemonstrationActionKind, action['kind'], 'action kind'
                    ),
                    authority=_enum(
                        DemonstrationActionAuthority,
                        action['authority'],
                        'action authority',
                    ),
                    disposition=_enum(
                        DemonstrationActionDisposition,
                        action['disposition'],
                        'action disposition',
                    ),
                    evidence_ref=action['evidence_ref'],
                    reason_code=action['reason_code'],
                    target_id=action['target_id'],
                    target_value=action['target_value'],
                    target_unit=_enum(
                        DemonstrationActionUnit,
                        action['target_unit'],
                        'action target unit',
                    ),
                )
            )
        annotations = []
        for annotation_value in _list(event_document['annotations'], 'annotations'):
            annotation = _mapping(annotation_value, 'annotation', {'kind', 'text'})
            annotations.append(
                DemonstrationAnnotation(
                    kind=_enum(
                        DemonstrationAnnotationKind,
                        annotation['kind'],
                        'annotation kind',
                    ),
                    text=annotation['text'],
                )
            )
        events.append(
            DemonstrationEvent(
                event_id=event_document['event_id'],
                sequence_index=event_document['sequence_index'],
                event_type=_enum(
                    DemonstrationEventType,
                    event_document['event_type'],
                    'event type',
                ),
                source_time_ns=event_document['source_time_ns'],
                observation_references=observations,
                action_references=actions,
                annotations=annotations,
            )
        )
    outcome_document = _mapping(
        root['outcome'], 'outcome', {'detail', 'reason_codes', 'status'}
    )
    try:
        episode = DemonstrationEpisode(
            source_kind=_enum(
                DemonstrationSourceKind, root['source_kind'], 'source kind'
            ),
            robot_id=root['robot_id'],
            source_time=DemonstrationSourceTimeRange(
                clock_kind=_enum(
                    DemonstrationClockKind,
                    source_time_document['clock_kind'],
                    'source clock',
                ),
                start_ns=source_time_document['start_ns'],
                end_ns=source_time_document['end_ns'],
            ),
            provenance=DemonstrationProvenance(
                source_ref=provenance_document['source_ref'],
                source_fingerprint=provenance_document['source_fingerprint'],
                teacher_source_ref=provenance_document['teacher_source_ref'],
            ),
            events=events,
            outcome=DemonstrationOutcome(
                status=_enum(
                    DemonstrationOutcomeStatus,
                    outcome_document['status'],
                    'outcome status',
                ),
                reason_codes=_list(outcome_document['reason_codes'], 'outcome reasons'),
                detail=outcome_document['detail'],
            ),
            capture_policy=policy,
        )
    except DemonstrationValidationError as error:
        raise DemonstrationIntegrityError('episode content violates the v1 contract') from error
    if root['episode_fingerprint'] != episode.episode_fingerprint:
        raise DemonstrationIntegrityError('episode fingerprint was tampered')
    if root['episode_id'] != episode.episode_id:
        raise DemonstrationIntegrityError('episode ID was tampered')
    if episode.as_dict() != root:
        raise DemonstrationIntegrityError('episode canonical content did not reconstruct')
    return episode
