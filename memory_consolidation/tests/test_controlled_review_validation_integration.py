from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from uuid import UUID

from ayyo_memory import MemoryService, ProvenanceType, SQLiteMemoryStore
from ayyo_memory_consolidation import (
    CandidateSelectionOutcome,
    ControlledMemoryCandidateReviewPipeline,
    ControlledMemoryReviewError,
    MemoryCandidateReviewOutcome,
    MemoryCandidateReviewRequest,
    candidate_identity,
)
from ayyo_memory_validation import (
    POLICY_VERSION,
    DecisionReason,
    DecisionType,
    MemoryValidationService,
    ValidationDecision,
)
from ayyo_world_model import SemanticEvidenceKind

from consolidation_helpers import SYSTEM_TIME_NS, add_semantic_chain, semantic_chain


class EvaluatorSpy:
    def __init__(self, validation: MemoryValidationService) -> None:
        self.validation = validation
        self.calls = []

    def evaluate(self, candidate):
        self.calls.append(candidate)
        return self.validation.evaluate(candidate)


class ControlledReviewValidationIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.sqlite = SQLiteMemoryStore(
            Path(self.temporary_directory.name) / "memory.sqlite3"
        )
        self.next_id = 0

        def make_id():
            self.next_id += 1
            return UUID(int=self.next_id)

        self.memory = MemoryService(
            self.sqlite,
            clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
            id_factory=make_id,
        )
        self.validation = MemoryValidationService(self.memory)
        self.evaluator = EvaluatorSpy(self.validation)
        self.pipeline = ControlledMemoryCandidateReviewPipeline(self.evaluator)

    def tearDown(self) -> None:
        self.sqlite.close()
        self.temporary_directory.cleanup()

    def review_all(self, store, *, now_ns=SYSTEM_TIME_NS):
        plan = self.pipeline.prepare(store, now_ns=now_ns)
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        batch = self.pipeline.execute_review(request, store, now_ns=now_ns)
        return plan, request, batch

    def test_accept_new_is_reported_but_never_applied(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, _, batch = self.review_all(store)
        self.assertEqual(DecisionType.ACCEPT_NEW, batch.entries[0].validation_decision.decision_type)
        self.assertTrue(batch.entries[0].validation_decision.persistence_permitted)
        self.assertEqual(((DecisionType.ACCEPT_NEW, 1),), batch.validation_decision_counts)
        self.assertEqual([], self.memory.query_memories(active_only=False))
        self.assertEqual([], self.memory.list_conflicts(include_resolved=True))

    def test_selected_candidate_is_evaluated_exactly_once(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, _, batch = self.review_all(store)
        self.assertEqual(1, len(self.evaluator.calls))
        self.assertIs(
            batch.entries[0].staging_result.candidate,
            self.evaluator.calls[0],
        )
        self.assertEqual(1, batch.evaluated_count)

    def test_exact_duplicate_is_reported_without_a_second_record(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        plan, request, first = self.review_all(store)
        applied = self.validation.apply(first.entries[0].validation_decision)
        self.assertTrue(applied.mutation_applied)
        count_before = len(self.memory.query_memories(active_only=False))
        second = self.pipeline.execute_review(
            request,
            store,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(plan.plan_id, second.plan_id)
        self.assertEqual(
            DecisionType.EXACT_DUPLICATE,
            second.entries[0].validation_decision.decision_type,
        )
        self.assertEqual(
            count_before,
            len(self.memory.query_memories(active_only=False)),
        )

    def test_conflict_review_is_reported_without_creating_conflict(self) -> None:
        first_store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
            category="cup",
        )
        _, _, first = self.review_all(first_store)
        self.validation.apply(first.entries[0].validation_decision)
        second_store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
            category="water-bottle",
            observed_at_ns=SYSTEM_TIME_NS + 1_000,
        )
        before_records = len(self.memory.query_memories(active_only=False))
        before_conflicts = len(self.memory.list_conflicts(include_resolved=True))
        _, _, second = self.review_all(
            second_store,
            now_ns=SYSTEM_TIME_NS + 1_000,
        )
        decision = second.entries[0].validation_decision
        self.assertEqual(DecisionType.CONFLICT_REVIEW, decision.decision_type)
        self.assertEqual(
            before_records,
            len(self.memory.query_memories(active_only=False)),
        )
        self.assertEqual(
            before_conflicts,
            len(self.memory.list_conflicts(include_resolved=True)),
        )

    def test_pipeline_never_calls_apply_create_correct_or_store_writes(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        self.validation.apply = Mock(wraps=self.validation.apply)
        self.memory.create_memory = Mock(wraps=self.memory.create_memory)
        self.memory.correct_memory = Mock(wraps=self.memory.correct_memory)
        self.sqlite.add_memory = Mock(wraps=self.sqlite.add_memory)
        self.sqlite.correct_memory = Mock(wraps=self.sqlite.correct_memory)
        self.review_all(store)
        self.validation.apply.assert_not_called()
        self.memory.create_memory.assert_not_called()
        self.memory.correct_memory.assert_not_called()
        self.sqlite.add_memory.assert_not_called()
        self.sqlite.correct_memory.assert_not_called()
        self.assertEqual([], self.memory.query_memories(active_only=False))

    def test_pipeline_cannot_perform_a_correction(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        _, _, batch = self.review_all(store)
        candidate = batch.entries[0].validation_decision.candidate
        self.assertIsNone(candidate.correction_target_id)
        self.assertIsNone(candidate.correction_reason)
        self.assertNotEqual(
            DecisionType.APPLY_CORRECTION,
            batch.entries[0].validation_decision.decision_type,
        )

    def test_evaluator_decision_for_different_candidate_fails_closed(self) -> None:
        first_store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        second_store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
        )
        _, _, second = self.review_all(second_store)
        wrong_decision = second.entries[0].validation_decision

        class WrongEvaluator:
            def evaluate(self, candidate):
                return wrong_decision

        pipeline = ControlledMemoryCandidateReviewPipeline(WrongEvaluator())
        plan = pipeline.prepare(first_store, now_ns=SYSTEM_TIME_NS)
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        with self.assertRaises(ControlledMemoryReviewError):
            pipeline.execute_review(request, first_store, now_ns=SYSTEM_TIME_NS)

    def test_oversized_validation_lineage_fails_whole_invocation_closed(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )

        class OversizedEvaluator:
            def evaluate(inner_self, candidate):
                normalized = self.validation.normalize(candidate)
                memory_ids = tuple(UUID(int=index) for index in range(1, 5_001))
                return ValidationDecision(
                    decision_type=DecisionType.EXACT_DUPLICATE,
                    reason_code=DecisionReason.EXACT_VALUE_ALREADY_ACTIVE,
                    normalized_identity=normalized.identity,
                    candidate=candidate,
                    relevant_memory_ids=memory_ids,
                    conflict_ids=(),
                    persistence_permitted=False,
                    explanatory_metadata=(
                        ("active_memory_count", 5_000),
                        ("correction_requested", False),
                        ("exact_duplicate_count", 5_000),
                        ("identity_was_normalized", False),
                        ("policy_version", POLICY_VERSION),
                        ("storage_identity_variant_count", 0),
                    ),
                )

        pipeline = ControlledMemoryCandidateReviewPipeline(OversizedEvaluator())
        plan = pipeline.prepare(store, now_ns=SYSTEM_TIME_NS)
        request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=plan.proposal_ids,
        )
        batch = pipeline.execute_review(request, store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(
            MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
            batch.outcome,
        )
        self.assertEqual((), batch.entries)
        self.assertEqual([], self.memory.query_memories(active_only=False))

    def test_multi_candidate_evaluation_is_canonical_sequential_and_read_only(self) -> None:
        person = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            observed_at_ns=SYSTEM_TIME_NS,
        )
        object_chain = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.875,
            category="cup",
            observed_at_ns=SYSTEM_TIME_NS + 1_000,
        )
        store = person[0]
        add_semantic_chain(
            store,
            object_chain,
            now_ns=SYSTEM_TIME_NS + 1_000,
        )
        plan, request, batch = self.review_all(
            store,
            now_ns=SYSTEM_TIME_NS + 1_000,
        )
        self.assertEqual(2, plan.proposal_count)
        self.assertEqual(MemoryCandidateReviewOutcome.REVIEW_COMPLETED, batch.outcome)
        self.assertEqual(2, batch.staged_count)
        self.assertEqual(2, batch.selected_count)
        self.assertEqual(2, batch.evaluated_count)
        self.assertEqual(
            sorted(candidate_identity(item) for item in self.evaluator.calls[-2:]),
            [candidate_identity(item) for item in self.evaluator.calls[-2:]],
        )
        self.assertEqual(
            {"observed_anonymous_person", "observed_anonymous_object"},
            {item.request.predicate for item in batch.entries},
        )
        self.assertEqual(
            {person[3].observation_id, object_chain[3].observation_id},
            {
                item.staging_result.candidate.provenance.details[
                    "source_observation_id"
                ]
                for item in batch.entries
            },
        )
        self.assertEqual([], self.memory.query_memories(active_only=False))

        reverse_request = MemoryCandidateReviewRequest(
            plan=plan,
            selected_proposal_ids=tuple(reversed(plan.proposal_ids)),
        )
        reverse = self.pipeline.execute_review(
            reverse_request,
            store,
            now_ns=SYSTEM_TIME_NS + 1_000,
        )
        self.assertEqual(request, reverse_request)
        self.assertEqual(batch, reverse)

    def test_end_to_end_requires_explicit_apply_outside_pipeline(self) -> None:
        store, _, _, semantic, item = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        self.assertEqual([], self.memory.query_memories(active_only=False))
        plan, _, batch = self.review_all(store)
        entry = batch.entries[0]
        self.assertEqual(plan.discovery_result_id, entry.discovery_result_id)
        self.assertEqual(
            item.source_semantic_observation_id,
            entry.request.supporting_evidence[0].semantic_item_id,
        )
        self.assertEqual(
            semantic.observation_id,
            entry.staging_result.candidate.provenance.details[
                "source_observation_id"
            ],
        )
        self.assertEqual(CandidateSelectionOutcome.SELECT_FOR_REVIEW, entry.selection_outcome)
        self.assertEqual(DecisionType.ACCEPT_NEW, entry.validation_decision.decision_type)
        self.assertEqual(ProvenanceType.DIRECT_OBSERVATION, entry.validation_decision.provenance.provenance_type)
        self.assertEqual([], self.memory.query_memories(active_only=False))

        applied = self.validation.apply(entry.validation_decision)
        self.assertTrue(applied.mutation_applied)
        self.assertEqual(1, len(self.memory.query_memories(active_only=False)))


if __name__ == "__main__":
    unittest.main()
