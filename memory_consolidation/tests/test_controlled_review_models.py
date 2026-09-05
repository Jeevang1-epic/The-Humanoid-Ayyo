from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from ayyo_memory import MemoryService, SQLiteMemoryStore
from ayyo_memory_consolidation import (
    CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
    ControlledMemoryCandidateReviewPipeline,
    ControlledMemoryReviewError,
    MemoryCandidateReviewOutcome,
    MemoryCandidateReviewReason,
    MemoryCandidateReviewRequest,
    memory_candidate_review_batch_identity,
    memory_candidate_review_entry_identity,
    memory_candidate_review_plan_identity,
    memory_candidate_review_request_identity,
)
from ayyo_memory_validation import MemoryValidationService
from ayyo_world_model import SemanticEvidenceKind

from consolidation_helpers import SYSTEM_TIME_NS, semantic_batch_chain, semantic_chain


class ControlledReviewModelInvariantTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.sqlite = SQLiteMemoryStore(
            Path(self.temporary_directory.name) / "memory.sqlite3"
        )
        self.memory = MemoryService(
            self.sqlite,
            clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
            id_factory=lambda: UUID(int=1),
        )
        self.pipeline = ControlledMemoryCandidateReviewPipeline(
            MemoryValidationService(self.memory)
        )

    def tearDown(self) -> None:
        self.sqlite.close()
        self.temporary_directory.cleanup()

    def plan_for(self, store, *, now_ns=SYSTEM_TIME_NS):
        return self.pipeline.prepare(store, now_ns=now_ns)

    def batch_for(self, store, plan, *, now_ns=SYSTEM_TIME_NS):
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        return request, self.pipeline.execute_review(
            request,
            store,
            now_ns=now_ns,
        )

    def test_request_snapshots_and_canonicalizes_caller_id_list(self) -> None:
        store, *_ = semantic_batch_chain(item_count=3)
        plan = self.plan_for(store)
        caller_ids = list(reversed(plan.proposal_ids))
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=caller_ids,
        )
        caller_ids.clear()
        self.assertEqual(plan.proposal_ids, request.selected_proposal_ids)

    def test_plan_identity_commits_to_prepare_time(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        first = self.plan_for(store, now_ns=SYSTEM_TIME_NS)
        second = self.plan_for(store, now_ns=SYSTEM_TIME_NS + 1_000)
        self.assertEqual(first.discovery_result, second.discovery_result)
        self.assertNotEqual(first.plan_id, second.plan_id)

    def test_public_identity_helpers_reconstruct_exact_ids(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        request, batch = self.batch_for(store, plan)
        entry = batch.entries[0]
        self.assertEqual(
            plan.plan_id,
            memory_candidate_review_plan_identity(
                pipeline_fingerprint=CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
                prepared_at_ns=plan.prepared_at_ns,
                discovery_result=plan.discovery_result,
            ),
        )
        self.assertEqual(
            request.request_id,
            memory_candidate_review_request_identity(
                plan_id=plan.plan_id,
                selected_proposal_ids=request.selected_proposal_ids,
            ),
        )
        self.assertEqual(
            entry.entry_id,
            memory_candidate_review_entry_identity(
                plan_id=entry.plan_id,
                discovery_result_id=entry.discovery_result_id,
                proposal_id=entry.proposal_id,
                staging_result=entry.staging_result,
                selection_item=entry.selection_item,
                validation_decision=entry.validation_decision,
                evaluated=entry.evaluated,
            ),
        )
        counts = (
            batch.staged_count,
            batch.staging_failed_count,
            batch.selected_count,
            batch.deferred_count,
            batch.rejected_count,
            batch.evaluated_count,
        )
        self.assertEqual(
            batch.batch_id,
            memory_candidate_review_batch_identity(
                pipeline_fingerprint=batch.pipeline_fingerprint,
                outcome=batch.outcome,
                reasons=batch.reasons,
                plan_id=batch.plan_id,
                discovery_result_id=batch.discovery_result_id,
                request_id=batch.request_id,
                entries=batch.entries,
                selection_decision=batch.selection_decision,
                discovery_count=batch.discovery_count,
                requested_count=batch.requested_count,
                counts=counts,
                validation_decision_counts=batch.validation_decision_counts,
            ),
        )

    def test_plan_rejects_malformed_identity_version_and_fingerprint(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        cases = (
            {"plan_id": "bad"},
            {"pipeline_version": 2},
            {
                "pipeline_fingerprint":
                    "controlled-memory-review-pipeline-sha256-" + "0" * 64
            },
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ControlledMemoryReviewError):
                    replace(plan, **changes)

    def test_entry_rejects_changed_evaluation_or_lineage(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        _, batch = self.batch_for(store, plan)
        entry = batch.entries[0]
        for changes in (
            {"evaluated": False},
            {"proposal_id": "memory-candidate-discovery-proposal-sha256-" + "0" * 64},
            {"discovery_result_id": "memory-candidate-discovery-sha256-" + "0" * 64},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ControlledMemoryReviewError):
                    replace(entry, **changes)

    def test_batch_rejects_inconsistent_counts_entries_and_reasons(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        _, batch = self.batch_for(store, plan)
        cases = (
            {"evaluated_count": 0},
            {"requested_count": 2},
            {"entries": ()},
            {"reasons": (MemoryCandidateReviewReason.NOTHING_REQUESTED,)},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ControlledMemoryReviewError):
                    replace(batch, **changes)

    def test_structural_failure_contains_no_partial_work(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=(
                "memory-candidate-discovery-proposal-sha256-" + "0" * 64,
            ),
        )
        batch = self.pipeline.execute_review(request, store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual((), batch.entries)
        self.assertIsNone(batch.selection_decision)
        self.assertEqual(0, batch.staged_count)
        self.assertEqual(0, batch.evaluated_count)

    def test_tampered_oversized_allowlist_returns_resource_outcome(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=(),
        )
        object.__setattr__(
            request,
            "selected_proposal_ids",
            tuple(
                "memory-candidate-discovery-proposal-sha256-" + f"{index:064x}"
                for index in range(33)
            ),
        )
        batch = self.pipeline.execute_review(request, store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(
            MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
            batch.outcome,
        )
        self.assertEqual(
            (MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,),
            batch.reasons,
        )
        self.assertEqual((), batch.entries)

    def test_review_models_are_frozen(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan = self.plan_for(store)
        request, batch = self.batch_for(store, plan)
        for record, attribute, replacement in (
            (plan, "plan_id", "changed"),
            (request, "request_id", "changed"),
            (batch.entries[0], "entry_id", "changed"),
            (batch, "batch_id", "changed"),
        ):
            with self.subTest(record=type(record).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, attribute, replacement)


if __name__ == "__main__":
    unittest.main()
