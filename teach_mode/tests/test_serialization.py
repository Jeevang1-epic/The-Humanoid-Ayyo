import json
import unittest

from ayyo_teach_mode import (
    MAX_SERIALIZED_EPISODE_BYTES,
    DemonstrationIntegrityError,
    DemonstrationIntegrityReason,
    canonical_episode_json,
    episode_from_canonical_json,
    verify_episode,
)

from helpers import demonstration_episode


class DemonstrationSerializationTest(unittest.TestCase):
    def test_same_episode_produces_byte_identical_canonical_json(self):
        first = canonical_episode_json(demonstration_episode())
        second = canonical_episode_json(demonstration_episode())
        self.assertEqual(first.encode('utf-8'), second.encode('utf-8'))
        self.assertEqual(first, json.dumps(json.loads(first), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')))

    def test_canonical_json_round_trip_preserves_episode(self):
        episode = demonstration_episode()
        rebuilt = episode_from_canonical_json(canonical_episode_json(episode))
        self.assertEqual(episode, rebuilt)
        self.assertEqual(episode.episode_id, rebuilt.episode_id)

    def test_noncanonical_json_fails_closed(self):
        canonical = canonical_episode_json(demonstration_episode())
        with self.assertRaisesRegex(DemonstrationIntegrityError, 'not canonical'):
            episode_from_canonical_json(' ' + canonical)

    def test_duplicate_json_key_fails_closed(self):
        with self.assertRaisesRegex(DemonstrationIntegrityError, 'duplicate key'):
            episode_from_canonical_json('{"a":1,"a":1}')

    def test_wrong_schema_fails_closed(self):
        document = json.loads(canonical_episode_json(demonstration_episode()))
        document['schema']['version'] = '2.0.0'
        tampered = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
        with self.assertRaisesRegex(DemonstrationIntegrityError, 'schema'):
            episode_from_canonical_json(tampered)

    def test_tampered_fingerprint_fails_closed(self):
        document = json.loads(canonical_episode_json(demonstration_episode()))
        document['episode_fingerprint'] = 'demonstration-episode-content-sha256-' + '0' * 64
        tampered = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
        with self.assertRaisesRegex(DemonstrationIntegrityError, 'fingerprint'):
            episode_from_canonical_json(tampered)

    def test_tampered_episode_id_fails_closed(self):
        document = json.loads(canonical_episode_json(demonstration_episode()))
        document['episode_id'] = 'demonstration-episode-sha256-' + '0' * 64
        tampered = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
        with self.assertRaisesRegex(DemonstrationIntegrityError, 'ID'):
            episode_from_canonical_json(tampered)

    def test_oversized_serialized_episode_is_rejected_before_parsing(self):
        with self.assertRaisesRegex(DemonstrationIntegrityError, 'exceeds'):
            episode_from_canonical_json(b'x' * (MAX_SERIALIZED_EPISODE_BYTES + 1))

    def test_verifier_accepts_valid_episode(self):
        result = verify_episode(demonstration_episode())
        self.assertTrue(result.verified)
        self.assertEqual((), result.reasons)
        self.assertIsNotNone(result.recomputed_fingerprint)

    def test_verifier_rejects_tampered_fingerprint(self):
        episode = demonstration_episode()
        object.__setattr__(
            episode,
            'episode_fingerprint',
            'demonstration-episode-content-sha256-' + '0' * 64,
        )
        result = verify_episode(episode)
        self.assertFalse(result.verified)
        self.assertIn(DemonstrationIntegrityReason.FINGERPRINT_MISMATCH, result.reasons)
        with self.assertRaises(DemonstrationIntegrityError):
            canonical_episode_json(episode)

    def test_verifier_rejects_tampered_order(self):
        episode = demonstration_episode()
        object.__setattr__(episode.events[0], 'sequence_index', 1)
        result = verify_episode(episode)
        self.assertFalse(result.verified)
        self.assertIn(DemonstrationIntegrityReason.INVALID_EVENT_ORDER, result.reasons)

    def test_verifier_rejects_wrong_object_type(self):
        result = verify_episode({'episode': 'not-a-contract'})
        self.assertFalse(result.verified)
        self.assertEqual((DemonstrationIntegrityReason.INVALID_TYPE,), result.reasons)

    def test_verifier_fails_closed_on_tampered_nested_type(self):
        episode = demonstration_episode()
        object.__setattr__(episode, 'source_time', 'not-a-source-time-contract')
        result = verify_episode(episode)
        self.assertFalse(result.verified)
        self.assertIn(
            DemonstrationIntegrityReason.INVALID_CLOCK_SEMANTICS,
            result.reasons,
        )


if __name__ == '__main__':
    unittest.main()
