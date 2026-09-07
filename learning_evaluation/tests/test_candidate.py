from dataclasses import FrozenInstanceError
import json
import unittest

from ayyo_learning_evaluation import (
    CANDIDATE_POLICY_SCHEMA_ID,
    CANDIDATE_POLICY_SCHEMA_VERSION,
    CandidatePolicyIntegrityError,
    CandidatePolicyManifest,
    InertArtifactReference,
    candidate_policy_from_canonical_json,
    canonical_candidate_policy_json,
    verify_candidate_policy,
)

from helpers import fingerprint, fixture_candidate, fixture_corpus, fixture_episode


class CandidatePolicyTest(unittest.TestCase):
    def test_candidate_is_immutable_and_deterministic(self):
        first = fixture_candidate()
        second = fixture_candidate()
        self.assertEqual(first, second)
        self.assertEqual(first.candidate_id, second.candidate_id)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            first.semantic_version = '9.0.0'

    def test_explicit_semantic_version_changes_identity_not_authority(self):
        corpus = fixture_corpus()
        first = fixture_candidate(corpus)
        second = fixture_candidate(corpus, semantic_version='0.2.0')
        self.assertNotEqual(first.candidate_id, second.candidate_id)
        self.assertNotIn('approved', second.as_dict())
        self.assertNotIn('promoted', second.as_dict())
        self.assertNotIn('eligible', second.as_dict())

    def test_candidate_stores_only_candidate_evidence_identity(self):
        candidate = fixture_candidate()
        fields = set(candidate.__annotations__)
        self.assertIn('candidate_evidence_set_id', fields)
        self.assertNotIn('holdout_evidence_set_id', fields)
        self.assertNotIn('holdout_episode_ids', fields)
        self.assertEqual(candidate.candidate_evidence_set_id, candidate.provenance_ref)
        self.assertEqual(
            candidate.candidate_evidence_set_fingerprint,
            candidate.provenance_fingerprint,
        )

    def test_holdout_set_cannot_construct_candidate(self):
        corpus = fixture_corpus()
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'holdout'):
            CandidatePolicyManifest(
                candidate_evidence=corpus.holdout_evaluation,
                semantic_version='0.1.0',
                policy_family_id='ayyo.policy.v1',
                input_contract_id='ayyo.input.v1',
                input_contract_version='1.0.0',
                output_contract_id='ayyo.output.v1',
                output_contract_version='1.0.0',
                description='Must fail.',
            )

    def test_changing_only_holdout_does_not_change_candidate_identity(self):
        candidate_episode = fixture_episode('same-candidate')
        first_corpus = type(fixture_corpus())(
            candidate_evidence=[candidate_episode],
            holdout_evaluation=[fixture_episode('holdout-one')],
            description='Same corpus label.',
        )
        second_corpus = type(fixture_corpus())(
            candidate_evidence=[candidate_episode],
            holdout_evaluation=[fixture_episode('holdout-two')],
            description='Same corpus label.',
        )
        first = fixture_candidate(first_corpus)
        second = fixture_candidate(second_corpus)
        self.assertNotEqual(first_corpus.holdout_evaluation.evidence_set_id, second_corpus.holdout_evaluation.evidence_set_id)
        self.assertEqual(first_corpus.candidate_evidence.evidence_set_id, second_corpus.candidate_evidence.evidence_set_id)
        self.assertEqual(first.candidate_id, second.candidate_id)
        self.assertEqual(first.candidate_fingerprint, second.candidate_fingerprint)

    def test_changing_candidate_evidence_changes_source_and_candidate_identity(self):
        first_corpus = type(fixture_corpus())(
            candidate_evidence=[fixture_episode('candidate-one')],
            holdout_evaluation=[fixture_episode('same-holdout')],
            description='Same corpus label.',
        )
        second_corpus = type(fixture_corpus())(
            candidate_evidence=[fixture_episode('candidate-two')],
            holdout_evaluation=[fixture_episode('same-holdout')],
            description='Same corpus label.',
        )
        first = fixture_candidate(first_corpus)
        second = fixture_candidate(second_corpus)
        self.assertNotEqual(first.provenance_ref, second.provenance_ref)
        self.assertNotEqual(first.provenance_fingerprint, second.provenance_fingerprint)
        self.assertNotEqual(first.candidate_id, second.candidate_id)

    def test_candidate_has_no_execution_or_model_loading_surface(self):
        forbidden = {
            'act', 'apply', 'dispatch', 'execute', 'fit', 'infer', 'learn',
            'load', 'load_model', 'predict', 'promote', 'rollback', 'run', 'step', 'train',
        }
        self.assertEqual(set(), forbidden & set(dir(CandidatePolicyManifest)))

    def test_candidate_has_no_executable_or_raw_payload_fields(self):
        forbidden = {
            'bytecode', 'callable', 'command', 'executable', 'model_weights', 'path',
            'payload', 'pixels', 'python_source', 'raw_sensor_data', 'shell', 'url',
        }
        self.assertEqual(set(), forbidden & set(CandidatePolicyManifest.__annotations__))
        self.assertEqual(set(), forbidden & set(InertArtifactReference.__annotations__))

    def test_external_artifact_is_only_an_inert_content_reference(self):
        artifact = InertArtifactReference(
            artifact_id='future-model-artifact.v1',
            artifact_kind='opaque-model-content',
            content_fingerprint=fingerprint('future-model-content', 'one'),
        )
        candidate = fixture_candidate(artifact=artifact)
        self.assertEqual(artifact, candidate.artifact)
        with self.assertRaises(CandidatePolicyIntegrityError):
            InertArtifactReference(
                artifact_id='/tmp/model.pkl',
                artifact_kind='pickle',
                content_fingerprint=fingerprint('future-model-content', 'two'),
            )

    def test_parent_lineage_is_structural_and_pairwise(self):
        parent = fixture_candidate()
        child = fixture_candidate(
            semantic_version='0.2.0',
            parent_candidate_id=parent.candidate_id,
            parent_candidate_fingerprint=parent.candidate_fingerprint,
        )
        self.assertEqual(parent.candidate_id, child.parent_candidate_id)
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'together'):
            fixture_candidate(parent_candidate_id=parent.candidate_id)

    def test_semantic_versions_and_text_are_bounded(self):
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'semantic version'):
            fixture_candidate(semantic_version='latest')
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'text bound'):
            fixture_candidate(description='x' * 513)

    def test_canonical_serialization_round_trip_is_byte_deterministic(self):
        candidate = fixture_candidate()
        payload = canonical_candidate_policy_json(candidate)
        self.assertEqual(payload, canonical_candidate_policy_json(fixture_candidate()))
        self.assertEqual(candidate, candidate_policy_from_canonical_json(payload))

    def test_candidate_serialization_rejects_tampering_duplicates_and_noncanonical_json(self):
        payload = canonical_candidate_policy_json(fixture_candidate())
        document = json.loads(payload)
        document['candidate_id'] = 'candidate-policy-sha256-' + '0' * 64
        tampered = json.dumps(document, sort_keys=True, separators=(',', ':'))
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'tampered'):
            candidate_policy_from_canonical_json(tampered)
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'duplicate'):
            candidate_policy_from_canonical_json('{"schema":{},"schema":{}}')
        with self.assertRaisesRegex(CandidatePolicyIntegrityError, 'not canonical'):
            candidate_policy_from_canonical_json(' ' + payload)

    def test_tampered_in_memory_candidate_fails_verification(self):
        candidate = fixture_candidate()
        object.__setattr__(candidate, 'candidate_fingerprint', 'candidate-policy-content-sha256-' + '0' * 64)
        self.assertFalse(verify_candidate_policy(candidate))
        with self.assertRaises(CandidatePolicyIntegrityError):
            canonical_candidate_policy_json(candidate)

    def test_schema_is_explicit_and_versioned(self):
        candidate = fixture_candidate()
        self.assertEqual(CANDIDATE_POLICY_SCHEMA_ID, candidate.schema_id)
        self.assertEqual(CANDIDATE_POLICY_SCHEMA_VERSION, candidate.schema_version)
        self.assertEqual('0.1.0', candidate.semantic_version)


if __name__ == '__main__':
    unittest.main()
