from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from ayyo_memory import MemoryService, SQLiteMemoryStore
from ayyo_memory_consolidation import (
    BoundedMemoryCandidateDiscoveryPolicy,
    CandidateReviewItem,
    CandidateSelectionOutcome,
    ReviewedMemoryCandidateSelectionPolicy,
    WorkingMemoryCandidateBridge,
)
from ayyo_memory_validation import DecisionType, MemoryValidationService
from ayyo_world_model import SemanticEvidenceKind

from consolidation_helpers import SYSTEM_TIME_NS, semantic_chain


class CandidateDiscoveryIntegrationTest(unittest.TestCase):
    def test_typed_visual_evidence_reaches_validation_only_by_explicit_calls(self) -> None:
        working_memory, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        discovery = BoundedMemoryCandidateDiscoveryPolicy().discover(
            working_memory,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(1, discovery.proposal_count)
        proposal = discovery.proposals[0]
        self.assertEqual(
            item.source_semantic_observation_id,
            proposal.request.supporting_evidence[0].semantic_item_id,
        )

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "memory.sqlite3")
            try:
                memory = MemoryService(
                    store,
                    clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
                    id_factory=lambda: UUID(int=1),
                )
                validation = MemoryValidationService(memory)
                self.assertEqual([], memory.query_memories(active_only=False))

                staged = WorkingMemoryCandidateBridge(working_memory).stage(
                    proposal.request,
                    now_ns=SYSTEM_TIME_NS,
                )
                candidate = staged.candidate
                assert candidate is not None
                self.assertEqual(
                    semantic.observation_id,
                    candidate.provenance.details["source_observation_id"],
                )
                self.assertEqual([], memory.query_memories(active_only=False))

                selection = ReviewedMemoryCandidateSelectionPolicy().select(
                    (CandidateReviewItem.from_staging(staged),)
                )
                self.assertEqual(
                    CandidateSelectionOutcome.SELECT_FOR_REVIEW,
                    selection.outcome,
                )
                self.assertEqual([], memory.query_memories(active_only=False))

                decision = validation.evaluate(selection.selected_candidates[0])
                self.assertEqual(DecisionType.ACCEPT_NEW, decision.decision_type)
                self.assertEqual([], memory.query_memories(active_only=False))

                applied = validation.apply(decision)
                self.assertTrue(applied.mutation_applied)
                self.assertEqual(1, len(memory.query_memories(active_only=False)))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
