from dataclasses import FrozenInstanceError
import os
import socket
import unittest

from ayyo_teach_mode import (
    AYYO_ROBOT_ID,
    MAX_ANNOTATIONS_PER_EPISODE,
    MAX_ANNOTATION_TEXT_LENGTH,
    MAX_EVENTS_PER_EPISODE,
    MAX_REFERENCES_PER_EVENT,
    DemonstrationActionAuthority,
    DemonstrationActionDisposition,
    DemonstrationActionKind,
    DemonstrationActionUnit,
    DemonstrationAnnotation,
    DemonstrationAnnotationKind,
    DemonstrationCapturePolicy,
    DemonstrationClockKind,
    DemonstrationEpisode,
    DemonstrationEvent,
    DemonstrationEventType,
    DemonstrationOutcomeStatus,
    DemonstrationSourceKind,
    DemonstrationSourceTimeRange,
    DemonstrationValidationError,
    ObservationReferenceKind,
)

from helpers import (
    action_reference,
    demonstration_episode,
    demonstration_event,
    demonstration_outcome,
    observation_reference,
)


class DemonstrationModelTest(unittest.TestCase):
    def test_completed_episode_and_nested_models_are_immutable(self):
        episode = demonstration_episode()
        for target, attribute, value in (
            (episode, 'robot_id', 'other.robot.v1'),
            (episode.events[0], 'event_id', 'changed'),
            (episode.outcome, 'status', DemonstrationOutcomeStatus.SUCCESS),
            (episode.provenance, 'source_ref', 'changed'),
        ):
            with self.subTest(target=type(target).__name__), self.assertRaises(
                (FrozenInstanceError, AttributeError)
            ):
                setattr(target, attribute, value)

    def test_equal_semantic_episodes_have_equal_ids_and_fingerprints(self):
        first = demonstration_episode()
        second = demonstration_episode()
        self.assertEqual(first.episode_id, second.episode_id)
        self.assertEqual(first.episode_fingerprint, second.episode_fingerprint)

    def test_capture_policy_fingerprint_is_deterministic(self):
        first = DemonstrationCapturePolicy()
        second = DemonstrationCapturePolicy()
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.semantic_document(), second.semantic_document())

    def test_caller_collections_are_snapshotted(self):
        references = [observation_reference()]
        annotations = [
            DemonstrationAnnotation(
                DemonstrationAnnotationKind.CALLER_NOTE,
                'Untrusted caller annotation.',
            )
        ]
        event = demonstration_event(
            observation_references=references,
            annotations=annotations,
        )
        events = [event]
        episode = demonstration_episode(events=events)
        reference_id = episode.events[0].observation_references[0].reference_id
        references.clear()
        annotations.clear()
        events.clear()
        self.assertEqual(reference_id, episode.events[0].observation_references[0].reference_id)
        self.assertEqual(1, len(episode.events))
        self.assertEqual(1, len(episode.events[0].annotations))

    def test_duplicate_event_ids_are_rejected(self):
        first = demonstration_event(0, source_time_ns=100)
        second = demonstration_event(1, event_id=first.event_id, source_time_ns=101)
        with self.assertRaisesRegex(DemonstrationValidationError, 'unique'):
            demonstration_episode(
                events=(first, second),
                source_time=DemonstrationSourceTimeRange(
                    DemonstrationClockKind.TEST_TIME, 100, 101
                ),
            )

    def test_sequence_gaps_and_reordering_are_rejected(self):
        for events in (
            (demonstration_event(1),),
            (
                demonstration_event(1, source_time_ns=101),
                demonstration_event(0, source_time_ns=100),
            ),
        ):
            with self.subTest(events=events), self.assertRaisesRegex(
                DemonstrationValidationError, 'contiguous'
            ):
                demonstration_episode(
                    events=events,
                    source_time=DemonstrationSourceTimeRange(
                        DemonstrationClockKind.TEST_TIME, 100, 101
                    ),
                )

    def test_unknown_enum_values_are_rejected(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'closed enum'):
            demonstration_event(event_type='observation')
        with self.assertRaisesRegex(DemonstrationValidationError, 'closed enum'):
            demonstration_episode(source_kind='test_fixture')

    def test_event_and_reference_bounds_are_enforced(self):
        reference = observation_reference()
        with self.assertRaisesRegex(DemonstrationValidationError, 'combined bound'):
            demonstration_event(
                observation_references=tuple(
                    observation_reference(
                        kind=ObservationReferenceKind.PUBLIC_EVIDENCE,
                        reference_id=f'evidence-{index}',
                    )
                    for index in range(MAX_REFERENCES_PER_EVENT)
                ),
                action_references=(action_reference(),),
            )
        events = tuple(
            demonstration_event(index, source_time_ns=100 + index)
            for index in range(MAX_EVENTS_PER_EPISODE)
        )
        with self.assertRaises(DemonstrationValidationError):
            demonstration_episode(
                events=events + (demonstration_event(0),),
                source_time=DemonstrationSourceTimeRange(
                    DemonstrationClockKind.TEST_TIME,
                    100,
                    100 + MAX_EVENTS_PER_EPISODE,
                ),
            )

    def test_annotation_text_and_episode_count_bounds_are_enforced(self):
        with self.assertRaises(DemonstrationValidationError):
            DemonstrationAnnotation(
                DemonstrationAnnotationKind.CALLER_NOTE,
                'x' * (MAX_ANNOTATION_TEXT_LENGTH + 1),
            )
        annotations = tuple(
            DemonstrationAnnotation(
                DemonstrationAnnotationKind.CALLER_NOTE,
                f'Note {index}.',
            )
            for index in range(8)
        )
        events = tuple(
            demonstration_event(
                index,
                source_time_ns=100 + index,
                annotations=annotations,
            )
            for index in range(MAX_ANNOTATIONS_PER_EPISODE // len(annotations) + 1)
        )
        with self.assertRaisesRegex(DemonstrationValidationError, 'annotations'):
            demonstration_episode(
                events=events,
                source_time=DemonstrationSourceTimeRange(
                    DemonstrationClockKind.TEST_TIME, 100, 100 + len(events)
                ),
            )

    def test_annotation_is_unicode_nfc_normalized(self):
        annotation = DemonstrationAnnotation(
            DemonstrationAnnotationKind.CALLER_NOTE,
            'Cafe\u0301 evidence.',
        )
        self.assertEqual('Café evidence.', annotation.text)

    def test_wrong_robot_reference_fails_closed_for_stage_six(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'canonical Ayyo'):
            demonstration_episode(
                source_kind=DemonstrationSourceKind.DEVELOPMENT_SCENARIO,
                robot_id='other.robot.v1',
            )

    def test_closed_source_kinds_are_exact(self):
        self.assertEqual(
            {
                'development_scenario',
                'test_fixture',
                'recorded_source_reference',
            },
            {item.value for item in DemonstrationSourceKind},
        )

    def test_simulation_time_remains_simulation_time(self):
        episode = demonstration_episode(
            source_time=DemonstrationSourceTimeRange(
                DemonstrationClockKind.SIMULATION_TIME, 100, 100
            )
        )
        self.assertIs(
            DemonstrationClockKind.SIMULATION_TIME,
            episode.source_time.clock_kind,
        )
        self.assertNotIn('utc', episode.source_time.clock_kind.value)

    def test_unavailable_time_cannot_fabricate_a_timestamp(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'fabricated'):
            DemonstrationSourceTimeRange(
                DemonstrationClockKind.UNAVAILABLE, 100, 100
            )
        with self.assertRaisesRegex(DemonstrationValidationError, 'cannot contain'):
            demonstration_episode(
                source_time=DemonstrationSourceTimeRange(
                    DemonstrationClockKind.UNAVAILABLE, None, None
                ),
            )

    def test_backwards_event_time_is_rejected(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'backwards'):
            demonstration_episode(
                events=(
                    demonstration_event(0, source_time_ns=101),
                    demonstration_event(1, source_time_ns=100),
                ),
                source_time=DemonstrationSourceTimeRange(
                    DemonstrationClockKind.TEST_TIME, 100, 101
                ),
            )

    def test_request_does_not_imply_success(self):
        episode = demonstration_episode(
            events=(
                demonstration_event(
                    event_type=DemonstrationEventType.INTENT,
                    observation_references=(),
                    action_references=(action_reference(),),
                ),
            ),
            outcome=demonstration_outcome(status=DemonstrationOutcomeStatus.UNKNOWN),
        )
        self.assertIs(DemonstrationActionDisposition.REQUESTED, episode.events[0].action_references[0].disposition)
        self.assertIs(DemonstrationOutcomeStatus.UNKNOWN, episode.outcome.status)

    def test_every_outcome_status_is_explicitly_constructible(self):
        for status in DemonstrationOutcomeStatus:
            with self.subTest(status=status):
                self.assertIs(status, demonstration_outcome(status=status).status)

    def test_semantic_change_changes_fingerprint(self):
        first = demonstration_episode()
        second = demonstration_episode(
            outcome=demonstration_outcome(
                status=DemonstrationOutcomeStatus.REJECTED,
                reason_codes=('request-rejected',),
                detail='The request was rejected.',
            )
        )
        self.assertNotEqual(first.episode_fingerprint, second.episode_fingerprint)
        self.assertNotEqual(first.episode_id, second.episode_id)

    def test_machine_runtime_identity_is_never_sampled(self):
        first = demonstration_episode()
        _ = (os.getpid(), socket.gethostname())
        second = demonstration_episode()
        document = second.as_dict()
        self.assertEqual(first.episode_id, second.episode_id)
        self.assertNotIn('pid', document)
        self.assertNotIn('hostname', document)
        self.assertNotIn('created_at', document)
        self.assertNotIn('current_time', document)

    def test_raw_sensor_payload_has_no_model_field(self):
        forbidden = {'data', 'payload', 'pixels', 'depth_array', 'pcm', 'ros_messages'}
        model_fields = set(DemonstrationEpisode.__annotations__)
        model_fields |= set(type(observation_reference()).__annotations__)
        model_fields |= set(type(demonstration_event()).__annotations__)
        self.assertEqual(set(), model_fields & forbidden)

    def test_external_recording_requires_content_fingerprint(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'verified content'):
            observation_reference(
                kind=ObservationReferenceKind.EXTERNAL_RECORDING,
                fingerprint=None,
            )

    def test_oversized_semantic_episode_is_rejected(self):
        references = tuple(
            observation_reference(
                kind=ObservationReferenceKind.PUBLIC_EVIDENCE,
                reference_id=f'evidence-{index}-' + 'x' * 230,
                provenance_kind='test-fixture',
                interface_id='ayyo.world-model.v1',
            )
            for index in range(MAX_REFERENCES_PER_EVENT)
        )
        events = tuple(
            demonstration_event(
                index,
                source_time_ns=100 + index,
                observation_references=references,
                annotations=(),
            )
            for index in range(MAX_EVENTS_PER_EPISODE)
        )
        with self.assertRaisesRegex(DemonstrationValidationError, 'serialized'):
            demonstration_episode(
                events=events,
                source_time=DemonstrationSourceTimeRange(
                    DemonstrationClockKind.TEST_TIME,
                    100,
                    100 + MAX_EVENTS_PER_EPISODE,
                ),
            )

    def test_development_action_cannot_gain_non_development_authority(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'DEVELOPMENT-only'):
            action_reference(authority=DemonstrationActionAuthority.NONE)

    def test_target_requires_complete_unit_semantics(self):
        with self.assertRaisesRegex(DemonstrationValidationError, 'requires identity'):
            action_reference(target_unit=DemonstrationActionUnit.NONE)


if __name__ == '__main__':
    unittest.main()
