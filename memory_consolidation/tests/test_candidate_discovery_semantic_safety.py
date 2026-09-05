from __future__ import annotations

import unittest

from ayyo_memory import MemoryType, ProvenanceType
from ayyo_memory_consolidation import (
    BoundedMemoryCandidateDiscoveryPolicy,
    WorkingMemoryCandidateBridge,
)
from ayyo_world_model import SemanticEvidenceKind

from consolidation_helpers import SYSTEM_TIME_NS, semantic_chain


class CandidateDiscoverySemanticSafetyTest(unittest.TestCase):
    def discover(self, kind: SemanticEvidenceKind):
        store, _, _, semantic, item = semantic_chain(
            kind=kind,
            confidence=0.75,
        )
        result = BoundedMemoryCandidateDiscoveryPolicy().discover(
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(1, result.proposal_count)
        return store, semantic, item, result.proposals[0]

    def test_anonymous_person_remains_anonymous(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.PERSON)
        self.assertIs(proposal.request.value["anonymous"], True)
        self.assertEqual("person", proposal.request.value["kind"])
        self.assertEqual("observed_anonymous_person", proposal.request.predicate)

    def test_anonymous_object_remains_anonymous(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertIs(proposal.request.value["anonymous"], True)
        self.assertEqual("object", proposal.request.value["kind"])
        self.assertEqual("observed_anonymous_object", proposal.request.predicate)

    def test_detection_id_remains_provenance_only(self) -> None:
        store, _, item, proposal = self.discover(SemanticEvidenceKind.PERSON)
        staged = WorkingMemoryCandidateBridge(store).stage(
            proposal.request,
            now_ns=SYSTEM_TIME_NS,
        )
        candidate = staged.candidate
        assert candidate is not None
        self.assertEqual(
            item.source_detection_id,
            candidate.provenance.details["source_detection_id"],
        )
        self.assertNotIn(item.source_detection_id, str(candidate.value))

    def test_category_is_not_an_object_identity(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertEqual("cup", proposal.request.value["category"])
        self.assertEqual(
            {"anonymous", "category", "kind", "region"},
            set(proposal.request.value),
        )

    def test_no_person_identity_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.PERSON)
        self.assertNotIn("person_id", proposal.request.value)
        self.assertNotIn("identity", proposal.request.value)

    def test_no_owner_identity_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.PERSON)
        self.assertNotIn("owner", proposal.request.value)
        self.assertNotIn("owner_id", proposal.request.value)
        self.assertNotEqual("owner", proposal.request.subject)

    def test_no_object_identity_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertNotIn("object_id", proposal.request.value)
        self.assertNotIn("entity_id", proposal.request.value)

    def test_no_preference_candidate_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertIs(MemoryType.EPISODIC, proposal.request.memory_type)
        self.assertIsNot(MemoryType.PREFERENCE, proposal.request.memory_type)
        self.assertNotIn("likes", proposal.request.predicate)

    def test_no_social_candidate_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.PERSON)
        self.assertIs(MemoryType.EPISODIC, proposal.request.memory_type)
        self.assertIsNot(MemoryType.SOCIAL, proposal.request.memory_type)
        self.assertNotIn("friend", proposal.request.predicate)

    def test_no_ownership_candidate_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertNotIn("own", proposal.request.predicate)
        self.assertNotIn("owned_by", proposal.request.value)

    def test_no_scene_absence_claim_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertNotIn("absent", proposal.request.predicate)
        self.assertNotIn("scene_absent", proposal.request.value)

    def test_no_object_permanence_claim_is_generated(self) -> None:
        _, _, _, proposal = self.discover(SemanticEvidenceKind.OBJECT)
        self.assertNotIn("permanence", proposal.request.predicate)
        self.assertNotIn("object_permanence", proposal.request.value)

    def test_no_correction_request_or_authority_is_generated(self) -> None:
        store, _, _, proposal = self.discover(SemanticEvidenceKind.PERSON)
        self.assertFalse(hasattr(proposal.request, "correction_target_id"))
        staged = WorkingMemoryCandidateBridge(store).stage(
            proposal.request,
            now_ns=SYSTEM_TIME_NS,
        )
        candidate = staged.candidate
        assert candidate is not None
        self.assertIsNone(candidate.correction_target_id)
        self.assertIsNone(candidate.correction_reason)
        self.assertIs(
            ProvenanceType.DIRECT_OBSERVATION,
            candidate.provenance.provenance_type,
        )


if __name__ == "__main__":
    unittest.main()
