"""Immutable, bounded, deterministic Teach Mode demonstration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import re
import unicodedata

from .canonical import canonical_json, semantic_sha256
from .errors import DemonstrationValidationError


TEACH_MODE_SCHEMA_ID = 'ayyo.teach-mode.demonstration-episode.v1'
TEACH_MODE_SCHEMA_VERSION = '1.0.0'
CAPTURE_POLICY_ID = 'ayyo.teach-mode.explicit-capture-policy.v1'
CAPTURE_POLICY_VERSION = '1.0.0'
AYYO_ROBOT_ID = 'ayyo.robot.v1'

MAX_EVENTS_PER_EPISODE = 64
MAX_REFERENCES_PER_EVENT = 16
MAX_ANNOTATIONS_PER_EVENT = 8
MAX_ANNOTATIONS_PER_EPISODE = 32
MAX_ANNOTATION_TEXT_LENGTH = 512
MAX_IDENTIFIER_LENGTH = 256
MAX_OUTCOME_REASONS = 16
MAX_SERIALIZED_EPISODE_BYTES = 65_536
MAX_SOURCE_TIME_NS = 9_223_372_036_854_775_807

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
_FINGERPRINT = re.compile(
    r'^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$'
)


class DemonstrationSourceKind(StrEnum):
    DEVELOPMENT_SCENARIO = 'development_scenario'
    TEST_FIXTURE = 'test_fixture'
    RECORDED_SOURCE_REFERENCE = 'recorded_source_reference'


class DemonstrationClockKind(StrEnum):
    SIMULATION_TIME = 'simulation_time'
    TEST_TIME = 'test_time'
    RECORDED_SOURCE_TIME = 'recorded_source_time'
    MONOTONIC_TIME = 'monotonic_time'
    UNAVAILABLE = 'unavailable'


class DemonstrationEventType(StrEnum):
    OBSERVATION = 'observation'
    INTENT = 'intent'
    EXECUTIVE_PROPOSAL = 'executive_proposal'
    SAFETY_DECISION = 'safety_decision'
    SKILL_BINDING = 'skill_binding'
    RUNTIME_RESULT = 'runtime_result'
    DEVELOPMENT_ACTION = 'development_action'
    OUTCOME = 'outcome'
    ANNOTATION = 'annotation'


class ObservationReferenceKind(StrEnum):
    WORLD_SNAPSHOT = 'world_snapshot'
    WORKING_MEMORY_EVIDENCE = 'working_memory_evidence'
    ANONYMOUS_SEMANTIC_EVIDENCE = 'anonymous_semantic_evidence'
    ROBOT_BODY_STATE = 'robot_body_state'
    SCENARIO_REPORT = 'scenario_report'
    SCENARIO_ASSERTION = 'scenario_assertion'
    SENSOR_EVIDENCE = 'sensor_evidence'
    EXTERNAL_RECORDING = 'external_recording'
    PUBLIC_EVIDENCE = 'public_evidence'


class ReferenceEvidenceStatus(StrEnum):
    OBSERVED = 'observed'
    PASS = 'pass'
    FAIL = 'fail'
    NOT_APPLICABLE = 'not_applicable'


class DemonstrationActionKind(StrEnum):
    EXECUTIVE_REQUEST = 'executive_request'
    EXECUTIVE_PROPOSAL = 'executive_proposal'
    SAFETY_DECISION = 'safety_decision'
    SKILL_BINDING = 'skill_binding'
    RUNTIME_RESULT = 'runtime_result'
    DEVELOPMENT_JOINT_POSITION = 'development_joint_position'
    DEVELOPMENT_RESET = 'development_reset'


class DemonstrationActionAuthority(StrEnum):
    NONE = 'none'
    DEVELOPMENT_ONLY = 'development_only'


class DemonstrationActionDisposition(StrEnum):
    REQUESTED = 'requested'
    PROPOSED = 'proposed'
    COMPLETED = 'completed'
    DEFERRED = 'deferred'
    INELIGIBLE = 'ineligible'
    NOT_DISPATCHED = 'not_dispatched'
    REJECTED = 'rejected'
    OBSERVED = 'observed'


class DemonstrationActionUnit(StrEnum):
    NONE = 'none'
    RADIAN = 'radian'


class DemonstrationAnnotationKind(StrEnum):
    CALLER_NOTE = 'caller_note'
    EVIDENCE_NOTE = 'evidence_note'
    OUTCOME_REASON = 'outcome_reason'
    LIMITATION = 'limitation'


class DemonstrationOutcomeStatus(StrEnum):
    SUCCESS = 'success'
    FAILURE = 'failure'
    DEFERRED = 'deferred'
    REJECTED = 'rejected'
    INCOMPLETE = 'incomplete'
    UNKNOWN = 'unknown'


class DemonstrationCaptureStatus(StrEnum):
    CAPTURED = 'captured'


def _enum(value: object, enum_type: type[StrEnum], field_name: str):
    if not isinstance(value, enum_type):
        raise DemonstrationValidationError(f'{field_name} must use its closed enum')
    return value


def _identifier(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise DemonstrationValidationError(
            f'{field_name} must be a non-empty trimmed identifier'
        )
    if len(value) > MAX_IDENTIFIER_LENGTH or _IDENTIFIER.fullmatch(value) is None:
        raise DemonstrationValidationError(
            f'{field_name} must be a bounded lowercase identifier'
        )
    return value


def _optional_identifier(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field_name)


def _fingerprint(value: object, field_name: str) -> str:
    value = _identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise DemonstrationValidationError(f'{field_name} is not a SHA-256 identity')
    return value


def _optional_fingerprint(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _fingerprint(value, field_name)


def _text(value: object, field_name: str, *, limit: int) -> str:
    if type(value) is not str:
        raise DemonstrationValidationError(f'{field_name} must be text')
    normalized = unicodedata.normalize('NFC', value)
    if not normalized or normalized != normalized.strip():
        raise DemonstrationValidationError(
            f'{field_name} must be non-empty normalized trimmed text'
        )
    if len(normalized) > limit:
        raise DemonstrationValidationError(f'{field_name} exceeds its v1 bound')
    if any(unicodedata.category(character) in {'Cc', 'Cs'} for character in normalized):
        raise DemonstrationValidationError(f'{field_name} contains unsupported characters')
    return normalized


def _semantic_version(value: object, field_name: str) -> str:
    if type(value) is not str or _SEMVER.fullmatch(value) is None:
        raise DemonstrationValidationError(f'{field_name} must be a semantic version')
    return value


def _typed_tuple(
    values: object,
    *,
    item_type: type,
    field_name: str,
    limit: int,
) -> tuple:
    if isinstance(values, (str, bytes)):
        raise DemonstrationValidationError(f'{field_name} must be a bounded sequence')
    try:
        snapshot = tuple(values)
    except TypeError as error:
        raise DemonstrationValidationError(
            f'{field_name} must be a bounded sequence'
        ) from error
    if len(snapshot) > limit or not all(type(item) is item_type for item in snapshot):
        raise DemonstrationValidationError(
            f'{field_name} has an invalid item or exceeds its v1 bound'
        )
    return snapshot


@dataclass(frozen=True, slots=True)
class DemonstrationSourceTimeRange:
    clock_kind: DemonstrationClockKind
    start_ns: int | None
    end_ns: int | None

    def __post_init__(self) -> None:
        _enum(self.clock_kind, DemonstrationClockKind, 'source clock')
        if self.clock_kind is DemonstrationClockKind.UNAVAILABLE:
            if self.start_ns is not None or self.end_ns is not None:
                raise DemonstrationValidationError(
                    'unavailable source time cannot contain fabricated timestamps'
                )
            return
        if (
            type(self.start_ns) is not int
            or type(self.end_ns) is not int
            or not 0 <= self.start_ns <= self.end_ns <= MAX_SOURCE_TIME_NS
        ):
            raise DemonstrationValidationError(
                'available source time requires an ordered bounded range'
            )

    def as_dict(self) -> dict[str, object]:
        return {
            'clock_kind': self.clock_kind.value,
            'end_ns': self.end_ns,
            'start_ns': self.start_ns,
        }


@dataclass(frozen=True, slots=True)
class DemonstrationProvenance:
    source_ref: str
    source_fingerprint: str
    teacher_source_ref: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.source_ref, 'provenance source_ref')
        _fingerprint(self.source_fingerprint, 'provenance source fingerprint')
        _optional_identifier(self.teacher_source_ref, 'teacher_source_ref')

    def as_dict(self) -> dict[str, object]:
        return {
            'source_fingerprint': self.source_fingerprint,
            'source_ref': self.source_ref,
            'teacher_source_ref': self.teacher_source_ref,
        }


@dataclass(frozen=True, slots=True)
class DemonstrationAnnotation:
    kind: DemonstrationAnnotationKind
    text: str

    def __post_init__(self) -> None:
        _enum(self.kind, DemonstrationAnnotationKind, 'annotation kind')
        object.__setattr__(
            self,
            'text',
            _text(
                self.text,
                'annotation text',
                limit=MAX_ANNOTATION_TEXT_LENGTH,
            ),
        )

    def as_dict(self) -> dict[str, str]:
        return {'kind': self.kind.value, 'text': self.text}


@dataclass(frozen=True, slots=True)
class DemonstrationObservationReference:
    kind: ObservationReferenceKind
    reference_id: str
    status: ReferenceEvidenceStatus = ReferenceEvidenceStatus.OBSERVED
    fingerprint: str | None = None
    provenance_kind: str | None = None
    interface_id: str | None = None

    def __post_init__(self) -> None:
        _enum(self.kind, ObservationReferenceKind, 'observation reference kind')
        _identifier(self.reference_id, 'observation reference_id')
        _enum(self.status, ReferenceEvidenceStatus, 'observation reference status')
        _optional_fingerprint(self.fingerprint, 'observation reference fingerprint')
        _optional_identifier(self.provenance_kind, 'observation provenance kind')
        _optional_identifier(self.interface_id, 'observation interface_id')
        if self.kind is ObservationReferenceKind.SENSOR_EVIDENCE and (
            self.provenance_kind is None or self.interface_id is None
        ):
            raise DemonstrationValidationError(
                'sensor evidence requires provenance and interface identities'
            )
        if self.kind is ObservationReferenceKind.EXTERNAL_RECORDING and (
            self.fingerprint is None
        ):
            raise DemonstrationValidationError(
                'an external recording reference requires verified content identity'
            )

    def as_dict(self) -> dict[str, object]:
        return {
            'fingerprint': self.fingerprint,
            'interface_id': self.interface_id,
            'kind': self.kind.value,
            'provenance_kind': self.provenance_kind,
            'reference_id': self.reference_id,
            'status': self.status.value,
        }


@dataclass(frozen=True, slots=True)
class DemonstrationActionReference:
    action_id: str
    kind: DemonstrationActionKind
    authority: DemonstrationActionAuthority
    disposition: DemonstrationActionDisposition
    evidence_ref: str
    reason_code: str | None = None
    target_id: str | None = None
    target_value: float | None = None
    target_unit: DemonstrationActionUnit = DemonstrationActionUnit.NONE

    def __post_init__(self) -> None:
        _identifier(self.action_id, 'action_id')
        _enum(self.kind, DemonstrationActionKind, 'action kind')
        _enum(self.authority, DemonstrationActionAuthority, 'action authority')
        _enum(self.disposition, DemonstrationActionDisposition, 'action disposition')
        _identifier(self.evidence_ref, 'action evidence_ref')
        _optional_identifier(self.reason_code, 'action reason_code')
        _optional_identifier(self.target_id, 'action target_id')
        _enum(self.target_unit, DemonstrationActionUnit, 'action target unit')
        if self.target_value is not None:
            if (
                type(self.target_value) not in {int, float}
                or not math.isfinite(self.target_value)
            ):
                raise DemonstrationValidationError('action target value is invalid')
            object.__setattr__(self, 'target_value', float(self.target_value))
        target_fields = self.target_id is not None or self.target_value is not None
        if target_fields and (
            self.target_id is None
            or self.target_value is None
            or self.target_unit is DemonstrationActionUnit.NONE
        ):
            raise DemonstrationValidationError(
                'an action target requires identity, finite value, and unit'
            )
        if not target_fields and self.target_unit is not DemonstrationActionUnit.NONE:
            raise DemonstrationValidationError('an untargeted action must use no unit')
        if self.kind in {
            DemonstrationActionKind.DEVELOPMENT_JOINT_POSITION,
            DemonstrationActionKind.DEVELOPMENT_RESET,
        } and self.authority is not DemonstrationActionAuthority.DEVELOPMENT_ONLY:
            raise DemonstrationValidationError(
                'development action evidence must retain DEVELOPMENT-only authority'
            )

    def as_dict(self) -> dict[str, object]:
        return {
            'action_id': self.action_id,
            'authority': self.authority.value,
            'disposition': self.disposition.value,
            'evidence_ref': self.evidence_ref,
            'kind': self.kind.value,
            'reason_code': self.reason_code,
            'target_id': self.target_id,
            'target_unit': self.target_unit.value,
            'target_value': self.target_value,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationOutcome:
    status: DemonstrationOutcomeStatus
    reason_codes: tuple[str, ...]
    detail: str

    def __init__(
        self,
        status: DemonstrationOutcomeStatus,
        reason_codes: tuple[str, ...] | list[str],
        detail: str,
    ) -> None:
        _enum(status, DemonstrationOutcomeStatus, 'outcome status')
        reasons = _typed_tuple(
            reason_codes,
            item_type=str,
            field_name='outcome reasons',
            limit=MAX_OUTCOME_REASONS,
        )
        if not reasons:
            raise DemonstrationValidationError('an explicit outcome requires a reason')
        reasons = tuple(_identifier(item, 'outcome reason') for item in reasons)
        if len(reasons) != len(set(reasons)):
            raise DemonstrationValidationError('outcome reasons must be unique')
        object.__setattr__(self, 'status', status)
        object.__setattr__(self, 'reason_codes', reasons)
        object.__setattr__(
            self,
            'detail',
            _text(detail, 'outcome detail', limit=MAX_ANNOTATION_TEXT_LENGTH),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            'detail': self.detail,
            'reason_codes': list(self.reason_codes),
            'status': self.status.value,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationEvent:
    event_id: str
    sequence_index: int
    event_type: DemonstrationEventType
    source_time_ns: int | None
    observation_references: tuple[DemonstrationObservationReference, ...]
    action_references: tuple[DemonstrationActionReference, ...]
    annotations: tuple[DemonstrationAnnotation, ...]

    def __init__(
        self,
        *,
        event_id: str,
        sequence_index: int,
        event_type: DemonstrationEventType,
        source_time_ns: int | None = None,
        observation_references: tuple[DemonstrationObservationReference, ...]
        | list[DemonstrationObservationReference] = (),
        action_references: tuple[DemonstrationActionReference, ...]
        | list[DemonstrationActionReference] = (),
        annotations: tuple[DemonstrationAnnotation, ...]
        | list[DemonstrationAnnotation] = (),
    ) -> None:
        event_id = _identifier(event_id, 'event_id')
        if (
            type(sequence_index) is not int
            or not 0 <= sequence_index < MAX_EVENTS_PER_EPISODE
        ):
            raise DemonstrationValidationError('event sequence index is outside v1 bounds')
        _enum(event_type, DemonstrationEventType, 'event type')
        if source_time_ns is not None and (
            type(source_time_ns) is not int
            or not 0 <= source_time_ns <= MAX_SOURCE_TIME_NS
        ):
            raise DemonstrationValidationError('event source timestamp is invalid')
        observations = _typed_tuple(
            observation_references,
            item_type=DemonstrationObservationReference,
            field_name='event observation references',
            limit=MAX_REFERENCES_PER_EVENT,
        )
        actions = _typed_tuple(
            action_references,
            item_type=DemonstrationActionReference,
            field_name='event action references',
            limit=MAX_REFERENCES_PER_EVENT,
        )
        if len(observations) + len(actions) > MAX_REFERENCES_PER_EVENT:
            raise DemonstrationValidationError('event references exceed the combined bound')
        if len({(item.kind, item.reference_id) for item in observations}) != len(
            observations
        ):
            raise DemonstrationValidationError('observation references must be unique')
        if len({item.action_id for item in actions}) != len(actions):
            raise DemonstrationValidationError('action references must be unique')
        annotation_snapshot = _typed_tuple(
            annotations,
            item_type=DemonstrationAnnotation,
            field_name='event annotations',
            limit=MAX_ANNOTATIONS_PER_EVENT,
        )
        if not observations and not actions and not annotation_snapshot:
            raise DemonstrationValidationError('an event must contain explicit evidence')
        object.__setattr__(self, 'event_id', event_id)
        object.__setattr__(self, 'sequence_index', sequence_index)
        object.__setattr__(self, 'event_type', event_type)
        object.__setattr__(self, 'source_time_ns', source_time_ns)
        object.__setattr__(self, 'observation_references', observations)
        object.__setattr__(self, 'action_references', actions)
        object.__setattr__(self, 'annotations', annotation_snapshot)

    def as_dict(self) -> dict[str, object]:
        return {
            'action_references': [item.as_dict() for item in self.action_references],
            'annotations': [item.as_dict() for item in self.annotations],
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'observation_references': [
                item.as_dict() for item in self.observation_references
            ],
            'sequence_index': self.sequence_index,
            'source_time_ns': self.source_time_ns,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationCapturePolicy:
    policy_id: str
    version: str
    fingerprint: str

    def __init__(self) -> None:
        object.__setattr__(self, 'policy_id', CAPTURE_POLICY_ID)
        object.__setattr__(self, 'version', CAPTURE_POLICY_VERSION)
        object.__setattr__(
            self,
            'fingerprint',
            semantic_sha256('teach-mode-capture-policy', self.semantic_document()),
        )

    def semantic_document(self) -> dict[str, object]:
        return {
            'allowed_action_authorities': [item.value for item in DemonstrationActionAuthority],
            'allowed_action_dispositions': [
                item.value for item in DemonstrationActionDisposition
            ],
            'allowed_action_kinds': [item.value for item in DemonstrationActionKind],
            'allowed_annotation_kinds': [item.value for item in DemonstrationAnnotationKind],
            'allowed_clocks': [item.value for item in DemonstrationClockKind],
            'allowed_event_types': [item.value for item in DemonstrationEventType],
            'allowed_observation_references': [
                item.value for item in ObservationReferenceKind
            ],
            'allowed_outcomes': [item.value for item in DemonstrationOutcomeStatus],
            'allowed_source_kinds': [item.value for item in DemonstrationSourceKind],
            'bounds': {
                'annotation_text_length': MAX_ANNOTATION_TEXT_LENGTH,
                'annotations_per_episode': MAX_ANNOTATIONS_PER_EPISODE,
                'annotations_per_event': MAX_ANNOTATIONS_PER_EVENT,
                'events_per_episode': MAX_EVENTS_PER_EPISODE,
                'identifier_length': MAX_IDENTIFIER_LENGTH,
                'outcome_reasons': MAX_OUTCOME_REASONS,
                'references_per_event': MAX_REFERENCES_PER_EVENT,
                'serialized_episode_bytes': MAX_SERIALIZED_EPISODE_BYTES,
            },
            'ordering': 'contiguous-zero-based-with-nondecreasing-source-time',
            'policy_id': CAPTURE_POLICY_ID,
            'version': CAPTURE_POLICY_VERSION,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationEpisode:
    schema_id: str
    schema_version: str
    capture_policy_id: str
    capture_policy_version: str
    capture_policy_fingerprint: str
    episode_id: str
    episode_fingerprint: str
    source_kind: DemonstrationSourceKind
    robot_id: str | None
    source_time: DemonstrationSourceTimeRange
    provenance: DemonstrationProvenance
    events: tuple[DemonstrationEvent, ...]
    outcome: DemonstrationOutcome

    def __init__(
        self,
        *,
        source_kind: DemonstrationSourceKind,
        robot_id: str | None,
        source_time: DemonstrationSourceTimeRange,
        provenance: DemonstrationProvenance,
        events: tuple[DemonstrationEvent, ...] | list[DemonstrationEvent],
        outcome: DemonstrationOutcome,
        capture_policy: DemonstrationCapturePolicy | None = None,
    ) -> None:
        _enum(source_kind, DemonstrationSourceKind, 'demonstration source kind')
        robot_id = _optional_identifier(robot_id, 'robot_id')
        if (
            source_kind is DemonstrationSourceKind.DEVELOPMENT_SCENARIO
            and robot_id != AYYO_ROBOT_ID
        ):
            raise DemonstrationValidationError(
                'Stage-6 demonstration evidence requires the canonical Ayyo robot'
            )
        if type(source_time) is not DemonstrationSourceTimeRange:
            raise DemonstrationValidationError('source_time has an invalid type')
        if type(provenance) is not DemonstrationProvenance:
            raise DemonstrationValidationError('provenance has an invalid type')
        event_snapshot = _typed_tuple(
            events,
            item_type=DemonstrationEvent,
            field_name='episode events',
            limit=MAX_EVENTS_PER_EPISODE,
        )
        if not event_snapshot:
            raise DemonstrationValidationError('an episode requires at least one event')
        if tuple(item.sequence_index for item in event_snapshot) != tuple(
            range(len(event_snapshot))
        ):
            raise DemonstrationValidationError(
                'episode event sequence must be contiguous, zero-based, and caller ordered'
            )
        event_ids = tuple(item.event_id for item in event_snapshot)
        if len(event_ids) != len(set(event_ids)):
            raise DemonstrationValidationError('episode event IDs must be unique')
        event_times = tuple(item.source_time_ns for item in event_snapshot)
        if source_time.clock_kind is DemonstrationClockKind.UNAVAILABLE:
            if any(item is not None for item in event_times):
                raise DemonstrationValidationError(
                    'unavailable source clock cannot contain event timestamps'
                )
        else:
            if any(item is None for item in event_times):
                raise DemonstrationValidationError(
                    'an available source clock requires every event timestamp'
                )
            concrete_times = tuple(item for item in event_times if item is not None)
            if concrete_times != tuple(sorted(concrete_times)):
                raise DemonstrationValidationError('event source times cannot move backwards')
            if concrete_times[0] < source_time.start_ns or concrete_times[-1] > source_time.end_ns:
                raise DemonstrationValidationError(
                    'event source time falls outside the declared source range'
                )
        if sum(len(item.annotations) for item in event_snapshot) > MAX_ANNOTATIONS_PER_EPISODE:
            raise DemonstrationValidationError('episode annotations exceed the v1 bound')
        if type(outcome) is not DemonstrationOutcome:
            raise DemonstrationValidationError('episode outcome has an invalid type')
        policy = capture_policy or DemonstrationCapturePolicy()
        if type(policy) is not DemonstrationCapturePolicy:
            raise DemonstrationValidationError('capture policy has an invalid type')
        if policy.fingerprint != semantic_sha256(
            'teach-mode-capture-policy', policy.semantic_document()
        ):
            raise DemonstrationValidationError('capture policy integrity failed')

        object.__setattr__(self, 'schema_id', TEACH_MODE_SCHEMA_ID)
        object.__setattr__(self, 'schema_version', TEACH_MODE_SCHEMA_VERSION)
        object.__setattr__(self, 'capture_policy_id', policy.policy_id)
        object.__setattr__(self, 'capture_policy_version', policy.version)
        object.__setattr__(self, 'capture_policy_fingerprint', policy.fingerprint)
        object.__setattr__(self, 'source_kind', source_kind)
        object.__setattr__(self, 'robot_id', robot_id)
        object.__setattr__(self, 'source_time', source_time)
        object.__setattr__(self, 'provenance', provenance)
        object.__setattr__(self, 'events', event_snapshot)
        object.__setattr__(self, 'outcome', outcome)
        episode_fingerprint = self.recompute_fingerprint()
        episode_id = semantic_sha256(
            'demonstration-episode',
            {
                'episode_fingerprint': episode_fingerprint,
                'schema_id': TEACH_MODE_SCHEMA_ID,
                'schema_version': TEACH_MODE_SCHEMA_VERSION,
            },
        )
        object.__setattr__(self, 'episode_fingerprint', episode_fingerprint)
        object.__setattr__(self, 'episode_id', episode_id)
        if len(canonical_json(self.as_dict()).encode('utf-8')) > MAX_SERIALIZED_EPISODE_BYTES:
            raise DemonstrationValidationError('serialized episode exceeds the v1 bound')

    def semantic_document(self) -> dict[str, object]:
        """Return new JSON-ready content that alone defines episode meaning."""
        return {
            'capture_policy': {
                'fingerprint': self.capture_policy_fingerprint,
                'id': self.capture_policy_id,
                'version': self.capture_policy_version,
            },
            'events': [item.as_dict() for item in self.events],
            'outcome': self.outcome.as_dict(),
            'provenance': self.provenance.as_dict(),
            'robot_id': self.robot_id,
            'schema': {
                'id': self.schema_id,
                'version': self.schema_version,
            },
            'source_kind': self.source_kind.value,
            'source_time': self.source_time.as_dict(),
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('demonstration-episode-content', self.semantic_document())

    def recompute_episode_id(self) -> str:
        return semantic_sha256(
            'demonstration-episode',
            {
                'episode_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        document = self.semantic_document()
        return {
            **document,
            'episode_fingerprint': self.episode_fingerprint,
            'episode_id': self.episode_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class DemonstrationCaptureResult:
    status: DemonstrationCaptureStatus
    episode: DemonstrationEpisode
    result_id: str

    def __init__(self, episode: DemonstrationEpisode) -> None:
        if type(episode) is not DemonstrationEpisode:
            raise DemonstrationValidationError('capture result requires one exact episode')
        object.__setattr__(self, 'status', DemonstrationCaptureStatus.CAPTURED)
        object.__setattr__(self, 'episode', episode)
        object.__setattr__(
            self,
            'result_id',
            semantic_sha256(
                'demonstration-capture-result',
                {
                    'episode_fingerprint': episode.episode_fingerprint,
                    'episode_id': episode.episode_id,
                    'status': DemonstrationCaptureStatus.CAPTURED.value,
                },
            ),
        )
