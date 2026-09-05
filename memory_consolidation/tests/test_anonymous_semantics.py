from __future__ import annotations

import unittest

from ayyo_memory import MemoryType, ProvenanceType
from ayyo_memory_consolidation import (
    CandidateStagingReason,
    CandidateStagingStatus,
    WorkingMemoryCandidateBridge,
)
from ayyo_world_model import AYYO_ROBOT_ID, SemanticEvidenceKind

from consolidation_helpers import (
    SYSTEM_TIME_NS,
    semantic_chain,
    semantic_request,
)


class AnonymousSemanticCandidateTest(unittest.TestCase):
    def test_anonymous_person_stays_anonymous_and_traceable(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        result = WorkingMemoryCandidateBridge(store).stage(
            semantic_request(semantic, item),
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(CandidateStagingStatus.ELIGIBLE, result.status)
        candidate = result.candidate
        assert candidate is not None
        self.assertEqual(MemoryType.EPISODIC, candidate.memory_type)
        self.assertEqual(AYYO_ROBOT_ID, candidate.subject)
        self.assertEqual("observed_anonymous_person", candidate.predicate)
        self.assertEqual(
            {
                "anonymous": True,
                "kind": "person",
                "region": item.region.document(),
            },
            candidate.value,
        )
        self.assertEqual(0.75, candidate.confidence)
        self.assertEqual(ProvenanceType.DIRECT_OBSERVATION, candidate.provenance.provenance_type)
        self.assertEqual(item.source_semantic_observation_id, candidate.provenance.source_id)
        self.assertEqual(
            item.source_detection_id,
            candidate.provenance.details["source_detection_id"],
        )
        self.assertEqual(
            semantic.observation_id,
            candidate.provenance.details["source_observation_id"],
        )
        self.assertEqual(
            str(semantic.fingerprint),
            candidate.provenance.details["source_observation_fingerprint"],
        )
        self.assertEqual(
            semantic.sensor.document(),
            candidate.provenance.details["sensor"],
        )
        self.assertEqual(
            semantic.producer.document(),
            candidate.provenance.details["producer"],
        )
        self.assertNotIn("source_detection_id", candidate.value)
        self.assertNotIn("person_id", candidate.value)
        self.assertNotIn("owner_id", candidate.value)

    def test_anonymous_object_category_is_not_a_stable_object_identity(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.0,
            category="cup",
        )
        candidate = WorkingMemoryCandidateBridge(store).stage(
            semantic_request(semantic, item),
            now_ns=SYSTEM_TIME_NS,
        ).candidate
        assert candidate is not None
        self.assertEqual(
            {
                "anonymous": True,
                "category": "cup",
                "kind": "object",
                "region": item.region.document(),
            },
            candidate.value,
        )
        self.assertEqual(0.0, candidate.confidence)
        self.assertNotIn("object_id", candidate.value)
        self.assertNotIn("owner", candidate.value)
        self.assertFalse(hasattr(candidate, "entity_id"))

    def test_missing_semantic_confidence_is_never_synthesized(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=None,
        )
        result = WorkingMemoryCandidateBridge(store).stage(
            semantic_request(semantic, item),
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(
            CandidateStagingReason.MISSING_REQUIRED_CONFIDENCE,
            result.reason,
        )
        self.assertIsNone(result.candidate)

    def test_anonymous_evidence_cannot_expand_into_identity_or_relationship_claims(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.8,
        )
        bridge = WorkingMemoryCandidateBridge(store)
        cases = (
            semantic_request(semantic, item, subject="owner"),
            semantic_request(semantic, item, predicate="recognized_person"),
            semantic_request(semantic, item, memory_type=MemoryType.SOCIAL),
            semantic_request(semantic, item, memory_type=MemoryType.PREFERENCE),
            semantic_request(semantic, item, value={"person_id": "owner"}),
            semantic_request(semantic, item, value={"owner_id": "jeevan"}),
            semantic_request(semantic, item, value={"scene_absent": True}),
            semantic_request(semantic, item, value={"object_permanence": True}),
        )
        for staging_request in cases:
            with self.subTest(request=staging_request):
                result = bridge.stage(staging_request, now_ns=SYSTEM_TIME_NS)
                self.assertIn(
                    result.reason,
                    {
                        CandidateStagingReason.MEMORY_TYPE_NOT_ALLOWED,
                        CandidateStagingReason.SEMANTIC_CLAIM_EXCEEDS_EVIDENCE,
                    },
                )
                self.assertIsNone(result.candidate)

    def test_semantic_item_and_full_source_chain_must_be_exactly_retained(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.8,
        )
        missing_item = semantic_request(
            semantic,
            item,
        )
        object.__setattr__(
            missing_item.supporting_evidence[0],
            "semantic_item_id",
            "person-observation-sha256-" + "0" * 64,
        )
        result = WorkingMemoryCandidateBridge(store).stage(
            missing_item,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(CandidateStagingReason.SOURCE_MISMATCH, result.reason)
        self.assertIsNone(result.candidate)

    def test_bridge_never_generates_candidates_without_an_explicit_request(self) -> None:
        store, _, _, _, _ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.8,
        )
        bridge = WorkingMemoryCandidateBridge(store)
        public_methods = {
            name for name in dir(bridge) if not name.startswith("_")
        }
        self.assertEqual({"stage"}, public_methods)
        self.assertEqual(3, store.stats(now_ns=SYSTEM_TIME_NS).recent_evidence_count)


if __name__ == "__main__":
    unittest.main()
