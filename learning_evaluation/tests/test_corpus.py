from dataclasses import FrozenInstanceError
import json
import unittest

from ayyo_learning_evaluation import (
    CORPUS_SCHEMA_ID,
    CORPUS_SCHEMA_VERSION,
    MAX_EPISODES_PER_CORPUS,
    MAX_EPISODES_PER_PARTITION,
    MAX_METADATA_TEXT_LENGTH,
    MAX_SERIALIZED_CORPUS_BYTES,
    CorpusConstructionError,
    CorpusIntegrityError,
    CorpusPartition,
    DemonstrationEvaluationCorpus,
    canonical_corpus_json,
    corpus_from_canonical_json,
    verify_corpus,
)

from helpers import fixture_corpus, fixture_episode


def canonical(document):
    return json.dumps(
        document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')
    )


class DemonstrationCorpusTest(unittest.TestCase):
    def test_corpus_and_nested_sets_are_immutable(self):
        corpus = fixture_corpus()
        for target, name, value in (
            (corpus, 'description', 'changed'),
            (corpus.candidate_evidence, 'partition', CorpusPartition.HOLDOUT_EVALUATION),
            (corpus.candidate_evidence.episodes[0], 'episode_id', 'changed'),
        ):
            with self.subTest(name=name), self.assertRaises((FrozenInstanceError, AttributeError)):
                setattr(target, name, value)

    def test_caller_sequence_mutation_cannot_change_corpus(self):
        candidates = [fixture_episode('candidate')]
        holdouts = [fixture_episode('holdout')]
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=candidates,
            holdout_evaluation=holdouts,
            description='Caller mutation isolation.',
        )
        identity = corpus.corpus_id
        candidates.clear()
        holdouts.append(fixture_episode('extra'))
        self.assertEqual(identity, corpus.corpus_id)
        self.assertEqual(1, len(corpus.candidate_evidence.episodes))
        self.assertEqual(1, len(corpus.holdout_evaluation.episodes))

    def test_equal_semantics_have_equal_identity_and_canonical_bytes(self):
        first = fixture_corpus()
        second = fixture_corpus()
        self.assertEqual(first.corpus_id, second.corpus_id)
        self.assertEqual(first.corpus_fingerprint, second.corpus_fingerprint)
        self.assertEqual(canonical_corpus_json(first), canonical_corpus_json(second))

    def test_nonsemantic_input_order_is_canonicalized(self):
        a = fixture_episode('a')
        b = fixture_episode('b')
        h = fixture_episode('h')
        first = DemonstrationEvaluationCorpus(
            candidate_evidence=[a, b], holdout_evaluation=[h], description='Order proof.'
        )
        second = DemonstrationEvaluationCorpus(
            candidate_evidence=[b, a], holdout_evaluation=[h], description='Order proof.'
        )
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(sorted((a.episode_id, b.episode_id))),
            tuple(item.episode_id for item in first.candidate_evidence.episodes),
        )

    def test_schema_and_partition_vocabularies_are_exact(self):
        self.assertEqual('ayyo.learning-evaluation.demonstration-corpus.v1', CORPUS_SCHEMA_ID)
        self.assertEqual('1.0.0', CORPUS_SCHEMA_VERSION)
        self.assertEqual(
            {'candidate_evidence', 'holdout_evaluation'},
            {item.value for item in CorpusPartition},
        )

    def test_duplicate_episode_in_one_partition_is_rejected(self):
        episode = fixture_episode('duplicate')
        with self.assertRaisesRegex(CorpusConstructionError, 'duplicate'):
            DemonstrationEvaluationCorpus(
                candidate_evidence=[episode, episode],
                holdout_evaluation=[fixture_episode('holdout')],
                description='Duplicate proof.',
            )

    def test_same_episode_across_partitions_is_rejected(self):
        episode = fixture_episode('overlap')
        with self.assertRaisesRegex(CorpusConstructionError, 'both partitions'):
            DemonstrationEvaluationCorpus(
                candidate_evidence=[episode],
                holdout_evaluation=[episode],
                description='Overlap proof.',
            )

    def test_empty_partitions_fail_closed(self):
        for candidates, holdouts in (([], [fixture_episode()]), ([fixture_episode()], [])):
            with self.subTest(candidates=bool(candidates)), self.assertRaises(CorpusConstructionError):
                DemonstrationEvaluationCorpus(
                    candidate_evidence=candidates,
                    holdout_evaluation=holdouts,
                    description='Empty partition proof.',
                )

    def test_only_exact_verified_demonstration_episodes_are_accepted(self):
        with self.assertRaisesRegex(CorpusConstructionError, 'only DemonstrationEpisode'):
            DemonstrationEvaluationCorpus(
                candidate_evidence=[object()],
                holdout_evaluation=[fixture_episode('holdout')],
                description='Type proof.',
            )
        episode = fixture_episode('tampered')
        object.__setattr__(episode, 'episode_fingerprint', 'demonstration-episode-content-sha256-' + '0' * 64)
        with self.assertRaisesRegex(CorpusConstructionError, 'integrity'):
            DemonstrationEvaluationCorpus(
                candidate_evidence=[episode],
                holdout_evaluation=[fixture_episode('holdout-two')],
                description='Integrity proof.',
            )

    def test_partition_and_total_resource_bounds_are_explicit(self):
        candidates = [fixture_episode(f'candidate-{index}') for index in range(MAX_EPISODES_PER_PARTITION)]
        holdouts = [fixture_episode(f'holdout-{index}') for index in range(MAX_EPISODES_PER_PARTITION)]
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=candidates,
            holdout_evaluation=holdouts,
            description='Maximum bounded corpus.',
        )
        self.assertEqual(MAX_EPISODES_PER_CORPUS, len(candidates) + len(holdouts))
        self.assertTrue(verify_corpus(corpus))
        with self.assertRaisesRegex(CorpusConstructionError, 'bound'):
            DemonstrationEvaluationCorpus(
                candidate_evidence=candidates + [fixture_episode('one-too-many')],
                holdout_evaluation=[fixture_episode('single-holdout')],
                description='Overflow corpus.',
            )

    def test_metadata_text_bound_is_enforced_and_nfc_normalized(self):
        with self.assertRaisesRegex(CorpusConstructionError, 'text bound'):
            DemonstrationEvaluationCorpus(
                candidate_evidence=[fixture_episode('candidate')],
                holdout_evaluation=[fixture_episode('holdout')],
                description='x' * (MAX_METADATA_TEXT_LENGTH + 1),
            )
        corpus = DemonstrationEvaluationCorpus(
            candidate_evidence=[fixture_episode('candidate')],
            holdout_evaluation=[fixture_episode('holdout')],
            description='Cafe\u0301 corpus.',
        )
        self.assertEqual('Café corpus.', corpus.description)

    def test_canonical_round_trip_preserves_manifest(self):
        corpus = fixture_corpus()
        self.assertEqual(corpus, corpus_from_canonical_json(canonical_corpus_json(corpus)))

    def test_tampered_episode_fingerprint_is_rejected(self):
        document = json.loads(canonical_corpus_json(fixture_corpus()))
        document['candidate_evidence']['episodes'][0]['episode_fingerprint'] = (
            'demonstration-episode-content-sha256-' + '0' * 64
        )
        with self.assertRaisesRegex(CorpusIntegrityError, 'tampered'):
            corpus_from_canonical_json(canonical(document))

    def test_tampered_corpus_identity_is_rejected(self):
        document = json.loads(canonical_corpus_json(fixture_corpus()))
        document['corpus_fingerprint'] = 'demonstration-evaluation-corpus-content-sha256-' + '0' * 64
        with self.assertRaisesRegex(CorpusIntegrityError, 'tampered'):
            corpus_from_canonical_json(canonical(document))

    def test_unsupported_schema_and_unknown_partition_are_rejected(self):
        for field, value in (
            (('schema', 'version'), '2.0.0'),
            (('candidate_evidence', 'partition'), 'train'),
        ):
            document = json.loads(canonical_corpus_json(fixture_corpus()))
            document[field[0]][field[1]] = value
            with self.subTest(value=value), self.assertRaises(CorpusIntegrityError):
                corpus_from_canonical_json(canonical(document))

    def test_duplicate_json_key_noncanonical_json_and_unknown_field_are_rejected(self):
        payload = canonical_corpus_json(fixture_corpus())
        with self.assertRaisesRegex(CorpusIntegrityError, 'duplicate key'):
            corpus_from_canonical_json('{"schema":{},"schema":{}}')
        with self.assertRaisesRegex(CorpusIntegrityError, 'not canonical'):
            corpus_from_canonical_json(' ' + payload)
        document = json.loads(payload)
        document['unexpected'] = True
        with self.assertRaisesRegex(CorpusIntegrityError, 'unknown or missing'):
            corpus_from_canonical_json(canonical(document))

    def test_nonfinite_and_oversized_json_are_rejected_before_reconstruction(self):
        with self.assertRaises(CorpusIntegrityError):
            corpus_from_canonical_json('{"value":NaN}')
        with self.assertRaisesRegex(CorpusIntegrityError, 'exceeds'):
            corpus_from_canonical_json('x' * (MAX_SERIALIZED_CORPUS_BYTES + 1))

    def test_manifest_has_no_raw_sensor_payload_field(self):
        forbidden = {'audio', 'data', 'depth', 'image', 'payload', 'pixels', 'samples'}
        document = json.loads(canonical_corpus_json(fixture_corpus()))

        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value), set())
            return set()

        self.assertEqual(set(), forbidden & keys(document))


if __name__ == '__main__':
    unittest.main()
