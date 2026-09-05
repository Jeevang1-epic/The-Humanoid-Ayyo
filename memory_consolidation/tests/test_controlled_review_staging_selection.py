from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from ayyo_memory import MemoryService, ProvenanceType, SQLiteMemoryStore
from ayyo_memory_consolidation import (
    CANDIDATE_SELECTION_POLICY_FINGERPRINT,
    CANDIDATE_SELECTION_POLICY_ID,
    CANDIDATE_SELECTION_POLICY_VERSION,
    CandidateSelectionDecision,
    CandidateSelectionItemDecision,
    CandidateSelectionOutcome,
    CandidateSelectionReason,
    CandidateStagingReason,
    CandidateStagingStatus,
    ControlledMemoryCandidateReviewPipeline,
    MemoryCandidateReviewOutcome,
    MemoryCandidateReviewRequest,
    ReviewedMemoryCandidateSelectionPolicy,
    WorkingMemoryCandidateBridge,
    candidate_identity,
)
from ayyo_memory_validation import MemoryValidationService
from ayyo_world_model import SemanticEvidenceKind, SemanticEvidenceObservation

from consolidation_helpers import (
    SYSTEM_TIME_NS,
    add_semantic_chain,
    semantic_batch_chain,
    semantic_chain,
)


class EvaluatorSpy:
    def __init__(self, validation) -> None:
        self.validation = validation
        self.calls = []

    def evaluate(self, candidate):
        self.calls.append(candidate)
        return self.validation.evaluate(candidate)


class ControlledReviewStagingAndSelectionTest(unittest.TestCase):
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
        self.evaluator = EvaluatorSpy(MemoryValidationService(self.memory))
        self.pipeline = ControlledMemoryCandidateReviewPipeline(self.evaluator)

    def tearDown(self) -> None:
        self.sqlite.close()
        self.temporary_directory.cleanup()

    def prepare_and_request(self, store, *, now_ns=SYSTEM_TIME_NS):
        plan = self.pipeline.prepare(store, now_ns=now_ns)
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        return plan, request

    def test_expired_after_prepare_is_one_typed_staging_failure(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            freshness_ns=100,
            ttl_ns=1_000,
        )
        _, request = self.prepare_and_request(store)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS + 1_001,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_STALE, batch.outcome)
        self.assertEqual(1, batch.staging_failed_count)
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_NOT_FOUND,
            batch.entries[0].staging_result.reason,
        )
        self.assertFalse(batch.entries[0].evaluated)
        self.assertEqual(0, batch.selection_decision.input_candidate_count)

    def test_stale_retained_evidence_is_not_repaired_or_rediscovered(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            freshness_ns=100,
            ttl_ns=1_000,
        )
        _, request = self.prepare_and_request(store)
        with patch(
            "ayyo_memory_consolidation.pipeline."
            "BoundedMemoryCandidateDiscoveryPolicy.discover",
            side_effect=AssertionError("execute must not rediscover"),
        ) as discover:
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS + 101,
            )
        discover.assert_not_called()
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_STALE,
            batch.entries[0].staging_result.reason,
        )
        self.assertIsNone(batch.entries[0].selection_item)

    def test_reset_epoch_evidence_is_ineligible(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, request = self.prepare_and_request(store)
        store.reset()
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_NOT_FOUND,
            batch.entries[0].staging_result.reason,
        )

    def test_evicted_evidence_is_ineligible(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, request = self.prepare_and_request(store)
        store._recent.clear()
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_NOT_FOUND,
            batch.entries[0].staging_result.reason,
        )

    def test_different_robot_working_memory_fails_staging(self) -> None:
        source, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, request = self.prepare_and_request(source)
        other, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            robot_id="other.robot.v1",
        )
        batch = self.pipeline.execute_review(
            request,
            other,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(
            CandidateStagingReason.ROBOT_MISMATCH,
            batch.entries[0].staging_result.reason,
        )

    def test_corrupted_retained_source_identity_fails_staging(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, request = self.prepare_and_request(store)
        semantic = next(
            envelope.observation
            for envelope in store._recent
            if type(envelope.observation) is SemanticEvidenceObservation
        )
        interpretation = store._recent[-2].observation
        object.__setattr__(
            semantic,
            "source_visual_fingerprint",
            interpretation.fingerprint,
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(CandidateStagingStatus.INELIGIBLE, batch.entries[0].staging_result.status)
        self.assertEqual(CandidateStagingReason.SOURCE_MISMATCH, batch.entries[0].staging_result.reason)

    def test_each_exact_request_is_staged_once_with_the_same_now(self) -> None:
        store, *_ = semantic_batch_chain(item_count=3)
        plan, request = self.prepare_and_request(store)
        original = WorkingMemoryCandidateBridge.stage
        calls = []

        def tracked(bridge, staging_request, *, now_ns):
            calls.append((staging_request, now_ns))
            return original(bridge, staging_request, now_ns=now_ns)

        with patch.object(WorkingMemoryCandidateBridge, "stage", new=tracked):
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS,
            )
        self.assertEqual(3, len(calls))
        self.assertEqual(
            list(plan.discovery_result.requests),
            [item[0] for item in calls],
        )
        self.assertEqual({SYSTEM_TIME_NS}, {item[1] for item in calls})
        self.assertEqual(3, len(batch.entries))

    def test_partial_staging_failure_does_not_block_valid_proposal(self) -> None:
        first = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            observed_at_ns=SYSTEM_TIME_NS,
            freshness_ns=100_000,
            ttl_ns=1_000_000,
        )
        second = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
            observed_at_ns=SYSTEM_TIME_NS + 100_000,
            freshness_ns=100_000,
            ttl_ns=1_000_000,
        )
        store = first[0]
        add_semantic_chain(store, second, now_ns=SYSTEM_TIME_NS + 100_000)
        plan, request = self.prepare_and_request(
            store,
            now_ns=SYSTEM_TIME_NS + 100_000,
        )
        self.assertEqual(2, plan.proposal_count)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS + 150_000,
        )
        self.assertEqual(
            MemoryCandidateReviewOutcome.REVIEW_COMPLETED_WITH_INELIGIBLE_ENTRIES,
            batch.outcome,
        )
        self.assertEqual(1, batch.staged_count)
        self.assertEqual(1, batch.staging_failed_count)
        self.assertEqual(1, batch.evaluated_count)
        self.assertEqual(1, len(self.evaluator.calls))
        self.assertEqual(2, len(batch.entries))

    def test_all_staged_candidates_reach_one_complete_selection_call(self) -> None:
        store, *_ = semantic_batch_chain(item_count=3)
        _, request = self.prepare_and_request(store)
        original = ReviewedMemoryCandidateSelectionPolicy.select
        inputs = []

        def tracked(policy, candidates):
            inputs.append(tuple(candidates))
            return original(policy, candidates)

        with patch.object(
            ReviewedMemoryCandidateSelectionPolicy,
            "select",
            new=tracked,
        ):
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS,
            )
        self.assertEqual(1, len(inputs))
        self.assertEqual(3, len(inputs[0]))
        self.assertEqual(3, batch.selection_decision.input_candidate_count)

    def test_conflicting_candidates_are_all_deferred_without_evaluation(self) -> None:
        store, *_ = semantic_batch_chain(item_count=2)
        _, request = self.prepare_and_request(store)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(0, batch.selected_count)
        self.assertEqual(2, batch.deferred_count)
        self.assertEqual([], self.evaluator.calls)
        for entry in batch.entries:
            self.assertEqual(CandidateSelectionOutcome.DEFER, entry.selection_outcome)
            self.assertIn(
                CandidateSelectionReason.CONFLICTING_CANDIDATE,
                entry.selection_reasons,
            )
            self.assertFalse(entry.evaluated)

    def test_low_confidence_candidate_is_deferred_without_evaluation(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.0,
        )
        _, request = self.prepare_and_request(store)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        entry = batch.entries[0]
        self.assertEqual(0.0, entry.staging_result.candidate.confidence)
        self.assertEqual(CandidateSelectionOutcome.DEFER, entry.selection_outcome)
        self.assertIn(
            CandidateSelectionReason.LOW_CONFIDENCE_FOR_POLICY,
            entry.selection_reasons,
        )
        self.assertFalse(entry.evaluated)
        self.assertEqual([], self.evaluator.calls)

    def test_missing_confidence_never_reaches_staging_or_evaluation(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=None,
        )
        plan, request = self.prepare_and_request(store)
        self.assertEqual(0, plan.proposal_count)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.NOTHING_REQUESTED, batch.outcome)
        self.assertEqual([], self.evaluator.calls)

    def test_staging_owns_original_utc_observation_time(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, request = self.prepare_and_request(store)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        candidate = batch.entries[0].staging_result.candidate
        self.assertEqual(datetime(2026, 1, 1, tzinfo=timezone.utc), candidate.observed_at)

    def test_stable_working_memory_content_and_ttl_are_not_refreshed(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        retained_before = store.recent_evidence(now_ns=SYSTEM_TIME_NS)
        stats_before = store.stats(now_ns=SYSTEM_TIME_NS)
        _, request = self.prepare_and_request(store)
        self.pipeline.execute_review(request, store, now_ns=SYSTEM_TIME_NS)
        retained_after = store.recent_evidence(now_ns=SYSTEM_TIME_NS)
        stats_after = store.stats(now_ns=SYSTEM_TIME_NS)
        self.assertEqual(retained_before, retained_after)
        self.assertEqual(stats_before, stats_after)

    def test_exact_duplicate_candidates_use_existing_collapse_behavior(self) -> None:
        store, *_ = semantic_batch_chain(item_count=2)
        plan, request = self.prepare_and_request(store)
        first_staging = WorkingMemoryCandidateBridge(store).stage(
            plan.discovery_result.requests[0],
            now_ns=SYSTEM_TIME_NS,
        )
        with patch.object(
            WorkingMemoryCandidateBridge,
            "stage",
            return_value=first_staging,
        ):
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS,
            )
        self.assertEqual(1, batch.selection_decision.unique_candidate_count)
        item = batch.selection_decision.items[0]
        self.assertEqual(2, item.occurrence_count)
        self.assertEqual(CandidateSelectionOutcome.DEFER, item.outcome)
        self.assertIn(CandidateSelectionReason.DUPLICATE_CANDIDATE, item.reasons)
        self.assertEqual([], self.evaluator.calls)

    def test_rejected_selection_entry_is_never_evaluated(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan, request = self.prepare_and_request(store)
        staged = WorkingMemoryCandidateBridge(store).stage(
            plan.discovery_result.requests[0],
            now_ns=SYSTEM_TIME_NS,
        )
        candidate = staged.candidate
        assert candidate is not None
        item = CandidateSelectionItemDecision(
            candidate_id=candidate_identity(candidate),
            candidate=candidate,
            outcome=CandidateSelectionOutcome.REJECT_SELECTION,
            reasons=(CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,),
            occurrence_count=1,
        )
        forced = CandidateSelectionDecision(
            policy_id=CANDIDATE_SELECTION_POLICY_ID,
            policy_version=CANDIDATE_SELECTION_POLICY_VERSION,
            policy_fingerprint=CANDIDATE_SELECTION_POLICY_FINGERPRINT,
            selection_id="candidate-selection-sha256-" + "0" * 64,
            outcome=CandidateSelectionOutcome.REJECT_SELECTION,
            reasons=(CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,),
            items=(item,),
            input_candidate_count=1,
        )
        with patch.object(
            ReviewedMemoryCandidateSelectionPolicy,
            "select",
            return_value=forced,
        ):
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS,
            )
        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, batch.entries[0].selection_outcome)
        self.assertEqual(1, batch.rejected_count)
        self.assertEqual([], self.evaluator.calls)

    def test_selection_resource_failure_aborts_whole_invocation(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, request = self.prepare_and_request(store)
        forced = CandidateSelectionDecision(
            policy_id=CANDIDATE_SELECTION_POLICY_ID,
            policy_version=CANDIDATE_SELECTION_POLICY_VERSION,
            policy_fingerprint=CANDIDATE_SELECTION_POLICY_FINGERPRINT,
            selection_id="candidate-selection-sha256-" + "0" * 64,
            outcome=CandidateSelectionOutcome.REJECT_SELECTION,
            reasons=(CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,),
            items=(),
            input_candidate_count=1,
        )
        with patch.object(
            ReviewedMemoryCandidateSelectionPolicy,
            "select",
            return_value=forced,
        ):
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS,
            )
        self.assertEqual(
            MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
            batch.outcome,
        )
        self.assertEqual((), batch.entries)
        self.assertIsNone(batch.selection_decision)
        self.assertEqual([], self.evaluator.calls)

    def test_staged_candidate_preserves_anonymous_semantics_and_provenance(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
            category="water-bottle",
        )
        _, request = self.prepare_and_request(store)
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        candidate = batch.entries[0].staging_result.candidate
        self.assertEqual(ProvenanceType.DIRECT_OBSERVATION, candidate.provenance.provenance_type)
        self.assertEqual(semantic.observation_id, candidate.provenance.details["source_observation_id"])
        self.assertEqual(item.source_semantic_observation_id, candidate.provenance.source_id)
        self.assertEqual("observed_anonymous_object", candidate.predicate)
        self.assertTrue(candidate.value["anonymous"])
        self.assertNotIn("person_id", candidate.value)
        self.assertNotIn("object_id", candidate.value)
        self.assertIsNone(candidate.correction_target_id)
        self.assertIsNone(candidate.correction_reason)


if __name__ == "__main__":
    unittest.main()
