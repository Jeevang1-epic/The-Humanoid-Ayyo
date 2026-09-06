from __future__ import annotations

from ayyo_teach_mode import (
    AYYO_ROBOT_ID,
    DemonstrationActionAuthority,
    DemonstrationActionDisposition,
    DemonstrationActionKind,
    DemonstrationActionReference,
    DemonstrationActionUnit,
    DemonstrationAnnotation,
    DemonstrationAnnotationKind,
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


SOURCE_FINGERPRINT = 'fixture-source-sha256-' + '1' * 64
EVIDENCE_FINGERPRINT = 'world-snapshot-sha256-' + '2' * 64


def observation_reference(**overrides):
    arguments = {
        'kind': ObservationReferenceKind.WORLD_SNAPSHOT,
        'reference_id': 'world-snapshot.fixture.v1',
        'fingerprint': EVIDENCE_FINGERPRINT,
        'provenance_kind': 'test-fixture',
        'interface_id': 'ayyo.world-model.v1',
    }
    arguments.update(overrides)
    return DemonstrationObservationReference(**arguments)


def action_reference(**overrides):
    arguments = {
        'action_id': 'requested-neck-target',
        'kind': DemonstrationActionKind.DEVELOPMENT_JOINT_POSITION,
        'authority': DemonstrationActionAuthority.DEVELOPMENT_ONLY,
        'disposition': DemonstrationActionDisposition.REQUESTED,
        'evidence_ref': 'fixture-source.v1',
        'target_id': 'neck_yaw_joint',
        'target_value': 0.1,
        'target_unit': DemonstrationActionUnit.RADIAN,
    }
    arguments.update(overrides)
    return DemonstrationActionReference(**arguments)


def demonstration_event(index=0, **overrides):
    arguments = {
        'event_id': f'event-{index}',
        'sequence_index': index,
        'event_type': DemonstrationEventType.OBSERVATION,
        'source_time_ns': 100 + index,
        'observation_references': (observation_reference(),),
        'action_references': (),
        'annotations': (
            DemonstrationAnnotation(
                DemonstrationAnnotationKind.EVIDENCE_NOTE,
                'Caller-supplied evidence note.',
            ),
        ),
    }
    arguments.update(overrides)
    return DemonstrationEvent(**arguments)


def demonstration_outcome(**overrides):
    arguments = {
        'status': DemonstrationOutcomeStatus.UNKNOWN,
        'reason_codes': ('caller-did-not-claim-success',),
        'detail': 'The request is evidence; no success claim was supplied.',
    }
    arguments.update(overrides)
    return DemonstrationOutcome(**arguments)


def demonstration_episode(**overrides):
    arguments = {
        'source_kind': DemonstrationSourceKind.TEST_FIXTURE,
        'robot_id': AYYO_ROBOT_ID,
        'source_time': DemonstrationSourceTimeRange(
            DemonstrationClockKind.TEST_TIME,
            100,
            100,
        ),
        'provenance': DemonstrationProvenance(
            source_ref='fixture-source.v1',
            source_fingerprint=SOURCE_FINGERPRINT,
            teacher_source_ref='fixture-input.v1',
        ),
        'events': (demonstration_event(),),
        'outcome': demonstration_outcome(),
    }
    arguments.update(overrides)
    return DemonstrationEpisode(**arguments)
