import unittest

from ayyo_teach_mode import (
    AYYO_ROBOT_ID,
    MAX_EVENTS_PER_EPISODE,
    DemonstrationClockKind,
    DemonstrationRecorder,
    DemonstrationSessionError,
    DemonstrationSourceKind,
    DemonstrationSourceTimeRange,
)

from helpers import (
    SOURCE_FINGERPRINT,
    demonstration_event,
    demonstration_outcome,
)
from ayyo_teach_mode import DemonstrationProvenance


def session():
    return DemonstrationRecorder().begin(
        source_kind=DemonstrationSourceKind.TEST_FIXTURE,
        robot_id=AYYO_ROBOT_ID,
        source_time=DemonstrationSourceTimeRange(
            DemonstrationClockKind.TEST_TIME, 100, 200
        ),
        provenance=DemonstrationProvenance(
            'fixture-source.v1', SOURCE_FINGERPRINT, 'fixture-input.v1'
        ),
    )


class DemonstrationCaptureSessionTest(unittest.TestCase):
    def test_caller_explicitly_appends_and_finishes(self):
        capture = session()
        self.assertEqual(0, capture.event_count)
        capture.append(demonstration_event())
        result = capture.finish(demonstration_outcome())
        self.assertTrue(capture.is_finished)
        self.assertEqual(1, len(result.episode.events))
        self.assertEqual(result.episode.episode_id, result.episode.episode_id)

    def test_empty_session_cannot_finish(self):
        with self.assertRaisesRegex(DemonstrationSessionError, 'empty'):
            session().finish(demonstration_outcome())

    def test_session_can_finish_only_once(self):
        capture = session()
        capture.append(demonstration_event())
        capture.finish(demonstration_outcome())
        with self.assertRaisesRegex(DemonstrationSessionError, 'only once'):
            capture.finish(demonstration_outcome())
        with self.assertRaisesRegex(DemonstrationSessionError, 'sealed'):
            capture.append(demonstration_event(1, source_time_ns=101))

    def test_append_requires_next_explicit_index(self):
        with self.assertRaisesRegex(DemonstrationSessionError, 'next explicit'):
            session().append(demonstration_event(1, source_time_ns=101))

    def test_session_rejects_duplicate_event_ids(self):
        capture = session()
        capture.append(demonstration_event())
        with self.assertRaisesRegex(DemonstrationSessionError, 'unique'):
            capture.append(
                demonstration_event(1, event_id='event-0', source_time_ns=101)
            )

    def test_session_event_count_is_hard_bounded(self):
        capture = session()
        for index in range(MAX_EVENTS_PER_EPISODE):
            capture.append(demonstration_event(index, source_time_ns=100 + index))
        with self.assertRaisesRegex(DemonstrationSessionError, 'event bound'):
            capture.append(demonstration_event(0))

    def test_recorder_exposes_no_background_controls(self):
        recorder = DemonstrationRecorder()
        for forbidden in ('start_background', 'subscribe', 'watch', 'poll', 'discover'):
            self.assertFalse(hasattr(recorder, forbidden))


if __name__ == '__main__':
    unittest.main()
