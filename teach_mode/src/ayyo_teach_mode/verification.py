"""Pure local integrity verification for completed demonstration episodes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_json, semantic_sha256
from .models import (
    AYYO_ROBOT_ID,
    CAPTURE_POLICY_ID,
    CAPTURE_POLICY_VERSION,
    MAX_ANNOTATIONS_PER_EPISODE,
    MAX_EVENTS_PER_EPISODE,
    MAX_REFERENCES_PER_EVENT,
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


class DemonstrationIntegrityReason(StrEnum):
    INVALID_TYPE = 'invalid_type'
    INVALID_SCHEMA = 'invalid_schema'
    INVALID_CAPTURE_POLICY = 'invalid_capture_policy'
    INVALID_ENUM = 'invalid_enum'
    INVALID_EVENT_ORDER = 'invalid_event_order'
    DUPLICATE_EVENT_ID = 'duplicate_event_id'
    RESOURCE_BOUND_EXCEEDED = 'resource_bound_exceeded'
    SOURCE_ROBOT_MISMATCH = 'source_robot_mismatch'
    INVALID_CLOCK_SEMANTICS = 'invalid_clock_semantics'
    INVALID_CONTENT = 'invalid_content'
    FINGERPRINT_MISMATCH = 'fingerprint_mismatch'
    EPISODE_ID_MISMATCH = 'episode_id_mismatch'


@dataclass(frozen=True, slots=True)
class DemonstrationIntegrityVerification:
    verified: bool
    reasons: tuple[DemonstrationIntegrityReason, ...]
    episode_id: str | None
    recomputed_fingerprint: str | None


def verify_episode(episode: object) -> DemonstrationIntegrityVerification:
    """Recompute v1 structure and identities without I/O or side effects."""
    if type(episode) is not DemonstrationEpisode:
        return DemonstrationIntegrityVerification(
            False,
            (DemonstrationIntegrityReason.INVALID_TYPE,),
            None,
            None,
        )
    reasons: set[DemonstrationIntegrityReason] = set()
    if (
        episode.schema_id != TEACH_MODE_SCHEMA_ID
        or episode.schema_version != TEACH_MODE_SCHEMA_VERSION
    ):
        reasons.add(DemonstrationIntegrityReason.INVALID_SCHEMA)
    policy = DemonstrationCapturePolicy()
    if (
        episode.capture_policy_id != CAPTURE_POLICY_ID
        or episode.capture_policy_version != CAPTURE_POLICY_VERSION
        or episode.capture_policy_fingerprint != policy.fingerprint
        or policy.fingerprint
        != semantic_sha256('teach-mode-capture-policy', policy.semantic_document())
    ):
        reasons.add(DemonstrationIntegrityReason.INVALID_CAPTURE_POLICY)
    source_kind = episode.source_kind
    source_time = episode.source_time
    provenance = episode.provenance
    outcome = episode.outcome
    events = episode.events
    if not isinstance(source_kind, DemonstrationSourceKind):
        reasons.add(DemonstrationIntegrityReason.INVALID_ENUM)
    if (
        source_kind is DemonstrationSourceKind.DEVELOPMENT_SCENARIO
        and episode.robot_id != AYYO_ROBOT_ID
    ):
        reasons.add(DemonstrationIntegrityReason.SOURCE_ROBOT_MISMATCH)
    if type(source_time) is not DemonstrationSourceTimeRange or not isinstance(
        getattr(source_time, 'clock_kind', None), DemonstrationClockKind
    ):
        reasons.add(DemonstrationIntegrityReason.INVALID_CLOCK_SEMANTICS)
        clock_kind = None
    else:
        clock_kind = source_time.clock_kind
    if type(events) is not tuple:
        reasons.add(DemonstrationIntegrityReason.INVALID_CONTENT)
        event_items = ()
    else:
        event_items = events
    if not 1 <= len(event_items) <= MAX_EVENTS_PER_EPISODE:
        reasons.add(DemonstrationIntegrityReason.RESOURCE_BOUND_EXCEEDED)
    try:
        indices = tuple(item.sequence_index for item in event_items)
        identifiers = tuple(item.event_id for item in event_items)
    except AttributeError:
        reasons.add(DemonstrationIntegrityReason.INVALID_CONTENT)
        indices = ()
        identifiers = ()
    if indices != tuple(range(len(event_items))):
        reasons.add(DemonstrationIntegrityReason.INVALID_EVENT_ORDER)
    if len(identifiers) != len(set(identifiers)):
        reasons.add(DemonstrationIntegrityReason.DUPLICATE_EVENT_ID)
    annotation_count = 0
    prior_time = None
    for event in event_items:
        if type(event) is not DemonstrationEvent:
            reasons.add(DemonstrationIntegrityReason.INVALID_CONTENT)
            continue
        if not isinstance(event.event_type, DemonstrationEventType):
            reasons.add(DemonstrationIntegrityReason.INVALID_ENUM)
        annotation_count += len(event.annotations)
        if (
            len(event.observation_references) + len(event.action_references)
            > MAX_REFERENCES_PER_EVENT
        ):
            reasons.add(DemonstrationIntegrityReason.RESOURCE_BOUND_EXCEEDED)
        for reference in event.observation_references:
            if type(reference) is not DemonstrationObservationReference or not isinstance(
                reference.kind, ObservationReferenceKind
            ) or not isinstance(reference.status, ReferenceEvidenceStatus):
                reasons.add(DemonstrationIntegrityReason.INVALID_ENUM)
        for action in event.action_references:
            if type(action) is not DemonstrationActionReference or not all(
                (
                    isinstance(action.kind, DemonstrationActionKind),
                    isinstance(action.authority, DemonstrationActionAuthority),
                    isinstance(action.disposition, DemonstrationActionDisposition),
                    isinstance(action.target_unit, DemonstrationActionUnit),
                )
            ):
                reasons.add(DemonstrationIntegrityReason.INVALID_ENUM)
        if not all(
            type(item) is DemonstrationAnnotation
            and isinstance(item.kind, DemonstrationAnnotationKind)
            for item in event.annotations
        ):
            reasons.add(DemonstrationIntegrityReason.INVALID_ENUM)
        if clock_kind is DemonstrationClockKind.UNAVAILABLE:
            if event.source_time_ns is not None:
                reasons.add(DemonstrationIntegrityReason.INVALID_CLOCK_SEMANTICS)
        elif clock_kind is not None and event.source_time_ns is None:
            reasons.add(DemonstrationIntegrityReason.INVALID_CLOCK_SEMANTICS)
        elif prior_time is not None and event.source_time_ns < prior_time:
            reasons.add(DemonstrationIntegrityReason.INVALID_CLOCK_SEMANTICS)
        if event.source_time_ns is not None:
            prior_time = event.source_time_ns
    if annotation_count > MAX_ANNOTATIONS_PER_EPISODE:
        reasons.add(DemonstrationIntegrityReason.RESOURCE_BOUND_EXCEEDED)
    if (
        type(source_time) is not DemonstrationSourceTimeRange
        or type(provenance) is not DemonstrationProvenance
        or type(outcome) is not DemonstrationOutcome
        or not isinstance(getattr(outcome, 'status', None), DemonstrationOutcomeStatus)
    ):
        reasons.add(DemonstrationIntegrityReason.INVALID_CONTENT)
    recomputed_fingerprint = None
    try:
        recomputed_fingerprint = episode.recompute_fingerprint()
        if episode.episode_fingerprint != recomputed_fingerprint:
            reasons.add(DemonstrationIntegrityReason.FINGERPRINT_MISMATCH)
        if episode.episode_id != episode.recompute_episode_id():
            reasons.add(DemonstrationIntegrityReason.EPISODE_ID_MISMATCH)
        if len(canonical_json(episode.as_dict()).encode('utf-8')) > MAX_SERIALIZED_EPISODE_BYTES:
            reasons.add(DemonstrationIntegrityReason.RESOURCE_BOUND_EXCEEDED)
        rebuilt = DemonstrationEpisode(
            source_kind=episode.source_kind,
            robot_id=episode.robot_id,
            source_time=episode.source_time,
            provenance=episode.provenance,
            events=episode.events,
            outcome=episode.outcome,
            capture_policy=policy,
        )
        if rebuilt.semantic_document() != episode.semantic_document():
            reasons.add(DemonstrationIntegrityReason.INVALID_CONTENT)
    except (AttributeError, TypeError, ValueError):
        reasons.add(DemonstrationIntegrityReason.INVALID_CONTENT)
    ordered_reasons = tuple(reason for reason in DemonstrationIntegrityReason if reason in reasons)
    return DemonstrationIntegrityVerification(
        not ordered_reasons,
        ordered_reasons,
        episode.episode_id if type(episode.episode_id) is str else None,
        recomputed_fingerprint,
    )
