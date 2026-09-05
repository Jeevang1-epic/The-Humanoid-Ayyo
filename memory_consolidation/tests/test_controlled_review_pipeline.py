from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from ayyo_memory import MemoryService, SQLiteMemoryStore
from ayyo_memory_consolidation import (
    CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
    CONTROLLED_MEMORY_REVIEW_PIPELINE_ID,
    CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION,
    MAX_CANDIDATE_DISCOVERY_PROPOSALS,
    MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS,
    MAX_MEMORY_REVIEW_ENTRIES,
    MAX_MEMORY_REVIEW_EVALUATIONS,
    MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS,
    BoundedMemoryCandidateDiscoveryPolicy,
    ControlledMemoryCandidateReviewPipeline,
    ControlledMemoryReviewError,
    MemoryCandidateReviewOutcome,
    MemoryCandidateReviewPlan,
    MemoryCandidateReviewReason,
    MemoryCandidateReviewRequest,
    ReviewedMemoryCandidateSelectionPolicy,
    WorkingMemoryCandidateBridge,
    ConsolidationRequest,
)
from ayyo_memory_validation import DecisionType, MemoryValidationService
from ayyo_world_model import SemanticEvidenceKind

from consolidation_helpers import (
    SYSTEM_TIME_NS,
    semantic_batch_chain,
    semantic_chain,
    working_memory,
)


class EvaluatorSpy:
    def __init__(self, validation: MemoryValidationService) -> None:
        self.validation = validation
        self.calls = []

    def evaluate(self, candidate):
        self.calls.append(candidate)
        return self.validation.evaluate(candidate)


class FailingEvaluator:
    def evaluate(self, candidate):
        raise AssertionError("prepare must not evaluate")


class ControlledReviewPipelineContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = SQLiteMemoryStore(
            Path(self.temporary_directory.name) / "memory.sqlite3"
        )
        self.memory = MemoryService(
            self.store,
            clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
            id_factory=lambda: UUID(int=1),
        )
        self.validation = MemoryValidationService(self.memory)
        self.evaluator = EvaluatorSpy(self.validation)
        self.pipeline = ControlledMemoryCandidateReviewPipeline(self.evaluator)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def person_plan(self, *, confidence: float = 0.75):
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=confidence,
        )
        return store, self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)

    def execute_all(self, store, plan):
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        return request, self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )

    def test_pipeline_identity_and_bounds_are_explicit(self) -> None:
        self.assertEqual(
            "ayyo.controlled-memory-review-pipeline.v1",
            CONTROLLED_MEMORY_REVIEW_PIPELINE_ID,
        )
        self.assertEqual(1, CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION)
        self.assertTrue(
            CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT.startswith(
                "controlled-memory-review-pipeline-sha256-"
            )
        )
        self.assertLessEqual(
            MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS,
            MAX_CANDIDATE_DISCOVERY_PROPOSALS,
        )
        self.assertEqual(32, MAX_MEMORY_REVIEW_ENTRIES)
        self.assertEqual(32, MAX_MEMORY_REVIEW_EVALUATIONS)

    def test_prepare_invokes_existing_discovery_exactly_once(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        original = BoundedMemoryCandidateDiscoveryPolicy.discover
        calls = []

        def tracked(policy, working_memory, *, now_ns):
            calls.append((working_memory, now_ns))
            return original(policy, working_memory, now_ns=now_ns)

        with patch.object(
            BoundedMemoryCandidateDiscoveryPolicy,
            "discover",
            new=tracked,
        ):
            plan = self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual([(store, SYSTEM_TIME_NS)], calls)
        self.assertEqual(1, plan.proposal_count)

    def test_prepare_does_not_stage_select_or_evaluate(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        pipeline = ControlledMemoryCandidateReviewPipeline(FailingEvaluator())
        with (
            patch.object(
                WorkingMemoryCandidateBridge,
                "stage",
                side_effect=AssertionError("prepare must not stage"),
            ) as stage,
            patch.object(
                ReviewedMemoryCandidateSelectionPolicy,
                "select",
                side_effect=AssertionError("prepare must not select"),
            ) as select,
        ):
            plan = pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(1, plan.proposal_count)
        stage.assert_not_called()
        select.assert_not_called()
        self.assertEqual([], self.memory.query_memories(active_only=False))

    def test_plan_is_immutable_complete_and_deterministic(self) -> None:
        store, first = self.person_plan()
        second = self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(first, second)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.discovery_result.discovery_id, first.discovery_result_id)
        self.assertEqual(
            first.discovery_result.policy_fingerprint,
            first.discovery_policy_fingerprint,
        )
        self.assertEqual(
            tuple(sorted(first.proposal_ids)),
            first.proposal_ids,
        )
        with self.assertRaises(FrozenInstanceError):
            first.prepared_at_ns = SYSTEM_TIME_NS + 1

    def test_plan_preserves_exact_discovery_policy_and_summary(self) -> None:
        store, plan = self.person_plan()
        discovery = BoundedMemoryCandidateDiscoveryPolicy().discover(
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(discovery, plan.discovery_result)
        self.assertEqual(discovery.policy_id, plan.discovery_policy_id)
        self.assertEqual(discovery.policy_version, plan.discovery_policy_version)
        self.assertEqual(discovery.policy_fingerprint, plan.discovery_policy_fingerprint)
        self.assertEqual(discovery.outcome, plan.discovery_result.outcome)
        self.assertEqual(discovery.reasons, plan.discovery_result.reasons)
        self.assertEqual(discovery.retained_evidence_count, plan.discovery_result.retained_evidence_count)
        self.assertEqual(discovery.inspected_evidence_count, plan.discovery_result.inspected_evidence_count)

    def test_plan_proposal_order_is_canonical_for_multiple_proposals(self) -> None:
        store, *_ = semantic_batch_chain(item_count=4)
        plan = self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(4, plan.proposal_count)
        self.assertEqual(tuple(sorted(plan.proposal_ids)), plan.proposal_ids)

    def test_plan_diagnostics_remain_within_discovery_bound(self) -> None:
        plan = self.pipeline.prepare(working_memory(), now_ns=SYSTEM_TIME_NS)
        self.assertLessEqual(plan.diagnostic_count, MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS)

    def test_prepare_does_not_call_validation_apply(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        self.validation.apply = Mock(wraps=self.validation.apply)
        self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        self.validation.apply.assert_not_called()
        self.assertEqual([], self.memory.query_memories(active_only=False))

    def test_zero_proposals_produces_a_valid_bounded_plan(self) -> None:
        store = working_memory()
        plan = self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, plan.proposal_count)
        self.assertEqual(1, plan.diagnostic_count)
        self.assertTrue(plan.plan_id.startswith("memory-candidate-review-plan-sha256-"))

    def test_mutating_discovery_source_after_prepare_cannot_change_plan(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        source = BoundedMemoryCandidateDiscoveryPolicy().discover(
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        with patch.object(
            BoundedMemoryCandidateDiscoveryPolicy,
            "discover",
            return_value=source,
        ):
            plan = self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        object.__setattr__(source.proposals[0].request, "predicate", "tampered")
        self.assertEqual("observed_anonymous_person", plan.discovery_result.requests[0].predicate)

    def test_one_exact_proposal_passes_the_caller_gate(self) -> None:
        store, plan = self.person_plan()
        request, batch = self.execute_all(store, plan)
        self.assertEqual(request.request_id, batch.request_id)
        self.assertEqual(MemoryCandidateReviewOutcome.REVIEW_COMPLETED, batch.outcome)
        self.assertEqual(1, batch.requested_count)
        self.assertEqual(1, batch.staged_count)
        self.assertEqual(1, batch.selected_count)
        self.assertEqual(1, batch.evaluated_count)
        self.assertEqual(DecisionType.ACCEPT_NEW, batch.entries[0].validation_decision.decision_type)
        self.assertEqual([], self.memory.query_memories(active_only=False))

    def test_empty_allowlist_stops_before_staging_selection_and_evaluation(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=(),
        )
        with (
            patch.object(
                WorkingMemoryCandidateBridge,
                "stage",
                side_effect=AssertionError("nothing requested must not stage"),
            ) as stage,
            patch.object(
                ReviewedMemoryCandidateSelectionPolicy,
                "select",
                side_effect=AssertionError("nothing requested must not select"),
            ) as select,
        ):
            batch = self.pipeline.execute_review(
                request,
                store,
                now_ns=SYSTEM_TIME_NS,
            )
        self.assertEqual(MemoryCandidateReviewOutcome.NOTHING_REQUESTED, batch.outcome)
        self.assertEqual((MemoryCandidateReviewReason.NOTHING_REQUESTED,), batch.reasons)
        self.assertEqual((), batch.entries)
        stage.assert_not_called()
        select.assert_not_called()
        self.assertEqual([], self.evaluator.calls)

    def test_unknown_proposal_identity_fails_whole_invocation_closed(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=(
                "memory-candidate-discovery-proposal-sha256-" + "0" * 64,
            ),
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual((MemoryCandidateReviewReason.UNKNOWN_PROPOSAL_ID,), batch.reasons)
        self.assertEqual((), batch.entries)
        self.assertIsNone(batch.selection_decision)
        self.assertEqual([], self.evaluator.calls)

    def test_duplicate_requested_identity_is_rejected_not_deduplicated(self) -> None:
        store, plan = self.person_plan()
        proposal_id = plan.proposal_ids[0]
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=(proposal_id, proposal_id),
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual(
            (MemoryCandidateReviewReason.DUPLICATE_PROPOSAL_ID,),
            batch.reasons,
        )
        self.assertEqual((), batch.entries)

    def test_caller_order_does_not_change_request_identity(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
        )
        plan = self.pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        first = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        second = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=tuple(reversed(plan.proposal_ids)),
        )
        self.assertEqual(first, second)
        self.assertEqual(first.request_id, second.request_id)

    def test_tampered_plan_pipeline_fingerprint_fails_closed(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        object.__setattr__(
            plan,
            "pipeline_fingerprint",
            "controlled-memory-review-pipeline-sha256-" + "0" * 64,
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual(
            (MemoryCandidateReviewReason.PLAN_INTEGRITY_FAILED,),
            batch.reasons,
        )

    def test_tampered_plan_request_snapshot_fails_closed(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        object.__setattr__(
            plan.discovery_result.proposals[0].request,
            "predicate",
            "observed_known_person",
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual((), batch.entries)

    def test_tampered_proposal_identity_fails_closed(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        object.__setattr__(
            plan.discovery_result.proposals[0],
            "proposal_id",
            "memory-candidate-discovery-proposal-sha256-" + "0" * 64,
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)

    def test_tampered_evidence_reference_fails_closed(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        reference = plan.discovery_result.requests[0].supporting_evidence[0]
        object.__setattr__(reference, "source_id", "untrusted.source.v1")
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual((), batch.entries)

    def test_tampered_plan_identity_and_discovery_identity_fail_closed(self) -> None:
        for field_name, replacement in (
            ("plan_id", "memory-candidate-review-plan-sha256-" + "0" * 64),
            (
                "discovery_id",
                "memory-candidate-discovery-sha256-" + "0" * 64,
            ),
        ):
            with self.subTest(field_name=field_name):
                store, plan = self.person_plan()
                request = MemoryCandidateReviewRequest(
                    plan=plan,
                    selected_proposal_ids=plan.proposal_ids,
                )
                target = plan if field_name == "plan_id" else plan.discovery_result
                object.__setattr__(target, field_name, replacement)
                batch = self.pipeline.execute_review(
                    request,
                    store,
                    now_ns=SYSTEM_TIME_NS,
                )
                self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
                self.assertEqual((), batch.entries)

    def test_tampered_request_identity_fails_closed(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        object.__setattr__(
            request,
            "request_id",
            "memory-candidate-review-request-sha256-" + "0" * 64,
        )
        batch = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(MemoryCandidateReviewOutcome.PLAN_INVALID, batch.outcome)
        self.assertEqual(
            (MemoryCandidateReviewReason.REQUEST_INTEGRITY_FAILED,),
            batch.reasons,
        )

    def test_request_count_and_identity_bounds_fail_at_construction(self) -> None:
        _, plan = self.person_plan()
        with self.assertRaises(ControlledMemoryReviewError):
            MemoryCandidateReviewRequest(
                plan=plan,
                selected_proposal_ids=tuple(
                    "memory-candidate-discovery-proposal-sha256-"
                    + f"{index:064x}"
                    for index in range(MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS + 1)
                ),
            )
        with self.assertRaises(ControlledMemoryReviewError):
            MemoryCandidateReviewRequest(
                plan=plan,
                selected_proposal_ids=("not-a-proposal",),
            )

    def test_public_request_and_plan_expose_no_candidate_mutation_authority(self) -> None:
        plan_fields = {item.name for item in fields(MemoryCandidateReviewPlan)}
        request_fields = {
            item.name for item in fields(MemoryCandidateReviewRequest)
        }
        forbidden = {
            "candidate",
            "confidence",
            "correction_reason",
            "correction_target_id",
            "memory_type",
            "provenance",
            "value",
        }
        self.assertFalse(plan_fields & forbidden)
        self.assertFalse(request_fields & forbidden)
        consolidation_fields = {
            item.name for item in fields(ConsolidationRequest)
        }
        self.assertFalse(
            consolidation_fields
            & {
                "confidence",
                "correction_reason",
                "correction_target_id",
                "observed_at",
                "provenance",
            }
        )
        self.assertFalse(hasattr(self.pipeline, "apply"))
        self.assertFalse(hasattr(self.pipeline, "persist"))

    def test_full_entry_lineage_is_exact_and_immutable(self) -> None:
        store, plan = self.person_plan()
        _, batch = self.execute_all(store, plan)
        entry = batch.entries[0]
        proposal = plan.discovery_result.proposals[0]
        self.assertEqual(plan.plan_id, entry.plan_id)
        self.assertEqual(plan.discovery_result_id, entry.discovery_result_id)
        self.assertEqual(proposal.proposal_id, entry.proposal_id)
        self.assertIs(proposal.request, entry.request)
        self.assertIs(
            entry.staging_result.candidate,
            entry.selection_item.candidate,
        )
        self.assertIs(
            entry.selection_item.candidate,
            entry.validation_decision.candidate,
        )
        self.assertTrue(entry.evaluated)
        with self.assertRaises(FrozenInstanceError):
            entry.evaluated = False

    def test_stable_reexecution_is_deterministic_and_read_only(self) -> None:
        store, plan = self.person_plan()
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        first = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        second = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual([], self.memory.query_memories(active_only=False))


if __name__ == "__main__":
    unittest.main()
