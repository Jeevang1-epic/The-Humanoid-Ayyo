from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from ayyo_memory import (
    AlreadyRetractedError,
    MemoryStatus,
    MemoryType,
    PersistenceConflictError,
    Provenance,
    ProvenanceType,
    SQLiteMemoryStore,
    StoreClosedError,
)
from ayyo_memory import MemoryService
from ayyo_memory_validation import (
    ApplicationResult,
    CandidateEvidence,
    DecisionNotApplicableError,
    DecisionReason,
    DecisionType,
    DeterministicValidationPolicy,
    MemoryValidationService,
    NormalizedIdentity,
    PolicyInvariantError,
    StaleDecisionError,
)


OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class IncrementingClock:
    def __init__(self) -> None:
        self._next = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(microseconds=1)
        return current


def provenance(provenance_type: ProvenanceType, source_id: str) -> Provenance:
    return Provenance(
        provenance_type,
        source_id,
        {"evidence_id": f"{source_id}-001"},
    )


def owner_statement(source_id: str = "owner.voice") -> Provenance:
    return provenance(ProvenanceType.EXPLICIT_OWNER_STATEMENT, source_id)


def derived_inference(source_id: str = "preference.classifier") -> Provenance:
    return provenance(ProvenanceType.DERIVED_INFERENCE, source_id)


class MemoryValidationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.store = SQLiteMemoryStore(self.database_path)
        self.clock = IncrementingClock()
        self.memory_service = MemoryService(self.store, clock=self.clock)
        self.validation_service = MemoryValidationService(self.memory_service)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def candidate(self, **overrides) -> CandidateEvidence:
        arguments = {
            "memory_type": MemoryType.PREFERENCE,
            "subject": "owner",
            "predicate": "preferred_drink",
            "value": "tea",
            "provenance": owner_statement(),
            "confidence": 0.9,
            "observed_at": OBSERVED_AT,
            "metadata": {"context": "kitchen"},
        }
        arguments.update(overrides)
        return CandidateEvidence(**arguments)

    def create_existing(self, **overrides):
        arguments = {
            "memory_type": MemoryType.PREFERENCE,
            "subject": "owner",
            "predicate": "preferred_drink",
            "value": "tea",
            "provenance": owner_statement(),
            "confidence": 0.9,
            "observed_at": OBSERVED_AT,
            "metadata": {"origin": "test evidence"},
        }
        arguments.update(overrides)
        return self.memory_service.create_memory(**arguments)

    def test_empty_state_evaluates_accept_new_without_mutation(self) -> None:
        candidate = self.candidate()
        first = self.validation_service.evaluate(candidate)
        second = self.validation_service.evaluate(candidate)

        self.assertEqual(first, second)
        self.assertEqual(DecisionType.ACCEPT_NEW, first.decision_type)
        self.assertEqual(DecisionReason.NO_ACTIVE_MEMORY, first.reason_code)
        self.assertTrue(first.persistence_permitted)
        self.assertEqual([], self.memory_service.query_memories(active_only=False))

    def test_normalized_identity_is_persisted_only_on_explicit_apply(self) -> None:
        candidate = self.candidate(
            subject="  Cafe\u0301   Owner ",
            predicate=" preferred\t drink ",
        )
        decision = self.validation_service.evaluate(candidate)
        self.assertEqual("Café Owner", decision.normalized_identity.subject)
        self.assertEqual("preferred drink", decision.normalized_identity.predicate)
        self.assertEqual([], self.memory_service.query_memories(active_only=False))

        result = self.validation_service.apply(decision)

        self.assertTrue(result.mutation_applied)
        self.assertEqual("Café Owner", result.memory.subject)
        self.assertEqual("preferred drink", result.memory.predicate)
        trace = result.memory.metadata["ayyo_memory_validation"]
        self.assertEqual("  Cafe\u0301   Owner ", trace["original_subject"])
        self.assertEqual(" preferred\t drink ", trace["original_predicate"])
        self.assertEqual("Café Owner", trace["normalized_subject"])
        self.assertEqual("accept_new", trace["decision"])

    def test_case_distinct_identity_is_not_merged(self) -> None:
        self.create_existing(subject="Owner")
        decision = self.validation_service.evaluate(self.candidate(subject="owner"))
        self.assertEqual(DecisionType.ACCEPT_NEW, decision.decision_type)
        self.assertEqual((), decision.relevant_memory_ids)

    def test_exact_duplicate_is_a_deterministic_no_op(self) -> None:
        existing = self.create_existing(value={"b": 2, "a": [1, {"z": True}]})
        candidate = self.candidate(value={"a": [1, {"z": True}], "b": 2})

        first = self.validation_service.evaluate(candidate)
        second = self.validation_service.evaluate(candidate)
        applied_once = self.validation_service.apply(first)
        applied_twice = self.validation_service.apply(first)

        self.assertEqual(first, second)
        self.assertEqual(DecisionType.EXACT_DUPLICATE, first.decision_type)
        self.assertEqual(
            DecisionReason.EXACT_VALUE_ALREADY_ACTIVE,
            first.reason_code,
        )
        self.assertFalse(first.persistence_permitted)
        self.assertFalse(applied_once.mutation_applied)
        self.assertFalse(applied_twice.mutation_applied)
        self.assertEqual(existing.memory_id, applied_once.memory_id)
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))

    def test_reapplying_accept_decision_is_idempotent(self) -> None:
        decision = self.validation_service.evaluate(self.candidate())
        first = self.validation_service.apply(decision)
        second = self.validation_service.apply(decision)

        self.assertTrue(first.mutation_applied)
        self.assertFalse(second.mutation_applied)
        self.assertEqual(first.memory_id, second.memory_id)
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))

    def test_stale_accept_after_equivalent_insert_becomes_safe_no_op(self) -> None:
        candidate = self.candidate(value={"drink": "tea", "size": "small"})
        decision = self.validation_service.evaluate(candidate)
        equivalent = self.create_existing(value={"size": "small", "drink": "tea"})

        result = self.validation_service.apply(decision)

        self.assertFalse(result.mutation_applied)
        self.assertEqual(DecisionType.EXACT_DUPLICATE, result.decision.decision_type)
        self.assertEqual(equivalent.memory_id, result.memory_id)
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))

    def test_duplicate_decision_preserves_new_provenance_without_overwriting(self) -> None:
        existing = self.create_existing(provenance=owner_statement())
        candidate = self.candidate(provenance=derived_inference(), confidence=0.7)
        decision = self.validation_service.evaluate(candidate)

        self.assertEqual(DecisionType.EXACT_DUPLICATE, decision.decision_type)
        self.assertEqual(
            ProvenanceType.DERIVED_INFERENCE,
            decision.provenance.provenance_type,
        )
        self.validation_service.apply(decision)
        persisted = self.memory_service.get_memory(existing.memory_id)
        self.assertEqual(
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            persisted.provenance.provenance_type,
        )

    def test_conflicting_value_requires_review_before_persistence(self) -> None:
        existing = self.create_existing(value="tea")
        candidate = self.candidate(
            value="coffee",
            provenance=derived_inference(),
            confidence=1.0,
        )
        decision = self.validation_service.evaluate(candidate)

        self.assertEqual(DecisionType.CONFLICT_REVIEW, decision.decision_type)
        self.assertEqual(DecisionReason.DIFFERENT_ACTIVE_VALUE, decision.reason_code)
        self.assertTrue(decision.persistence_permitted)
        self.assertEqual((existing.memory_id,), decision.relevant_memory_ids)
        self.assertEqual((), decision.conflict_ids)
        self.assertEqual(
            MemoryStatus.ACTIVE,
            self.memory_service.get_memory(existing.memory_id).status,
        )
        self.assertEqual(1, len(self.memory_service.query_memories()))

    def test_explicit_apply_persists_conflict_without_selecting_winner(self) -> None:
        first = self.create_existing(value="tea", confidence=0.2)
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                provenance=derived_inference(),
                confidence=1.0,
            )
        )
        result = self.validation_service.apply(decision)

        self.assertTrue(result.mutation_applied)
        self.assertEqual(
            MemoryStatus.ACTIVE,
            self.memory_service.get_memory(first.memory_id).status,
        )
        self.assertEqual(MemoryStatus.ACTIVE, result.memory.status)
        self.assertEqual(2, len(self.memory_service.query_memories()))
        conflicts = self.memory_service.list_conflicts()
        self.assertEqual(1, len(conflicts))
        self.assertIsNone(conflicts[0].resolved_at)

        repeated = self.validation_service.evaluate(decision.candidate)
        self.assertEqual(DecisionType.EXACT_DUPLICATE, repeated.decision_type)
        self.assertEqual(
            DecisionReason.EXACT_VALUE_ACTIVE_WITH_CONFLICTS,
            repeated.reason_code,
        )
        self.assertEqual((conflicts[0].conflict_id,), repeated.conflict_ids)

    def test_reapplying_conflict_decision_does_not_duplicate_evidence(self) -> None:
        self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(value="coffee", provenance=derived_inference())
        )
        first = self.validation_service.apply(decision)
        second = self.validation_service.apply(decision)

        self.assertTrue(first.mutation_applied)
        self.assertFalse(second.mutation_applied)
        self.assertEqual(first.memory_id, second.memory_id)
        self.assertEqual(2, len(self.memory_service.query_memories()))

    def test_changed_conflict_state_makes_review_decision_stale(self) -> None:
        self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(value="coffee", provenance=derived_inference())
        )
        self.create_existing(value="water", provenance=derived_inference())

        with self.assertRaises(StaleDecisionError):
            self.validation_service.apply(decision)

        self.assertEqual(
            {"tea", "water"},
            {record.value for record in self.memory_service.query_memories()},
        )

    def test_resolved_conflict_state_makes_review_decision_stale(self) -> None:
        self.create_existing(value="tea")
        removed = self.create_existing(value="coffee", provenance=derived_inference())
        decision = self.validation_service.evaluate(
            self.candidate(value="water", provenance=derived_inference())
        )
        self.memory_service.retract_memory(
            removed.memory_id,
            reason="Evidence withdrawn before apply",
        )

        with self.assertRaises(StaleDecisionError):
            self.validation_service.apply(decision)

        self.assertEqual(
            ["tea"],
            [record.value for record in self.memory_service.query_memories()],
        )

    def test_unrelated_conflicts_do_not_contaminate_decision(self) -> None:
        self.create_existing(value="tea")
        self.create_existing(value="coffee", provenance=derived_inference())
        self.create_existing(predicate="favorite_color", value="blue")
        self.create_existing(
            predicate="favorite_color",
            value="green",
            provenance=derived_inference(),
        )
        drink_conflict_ids = tuple(
            sorted(
                (
                    conflict.conflict_id
                    for conflict in self.memory_service.list_conflicts()
                    if conflict.left_memory.predicate == "preferred_drink"
                ),
                key=str,
            )
        )

        decision = self.validation_service.evaluate(
            self.candidate(value="water", provenance=derived_inference())
        )

        self.assertEqual(drink_conflict_ids, decision.conflict_ids)
        self.assertEqual(2, len(decision.relevant_memory_ids))
        self.assertEqual(1, len(decision.conflict_ids))

    def test_decision_identifiers_are_sorted_and_repeatable(self) -> None:
        for value in ("tea", "coffee", "water"):
            self.create_existing(value=value, provenance=derived_inference())
        candidate = self.candidate(value="juice", provenance=derived_inference())

        first = self.validation_service.evaluate(candidate)
        second = self.validation_service.evaluate(candidate)

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(sorted(first.relevant_memory_ids, key=str)),
            first.relevant_memory_ids,
        )
        self.assertEqual(tuple(sorted(first.conflict_ids, key=str)), first.conflict_ids)
        self.assertEqual(3, len(first.relevant_memory_ids))
        self.assertEqual(3, len(first.conflict_ids))

    def test_canonical_storage_variant_is_review_only(self) -> None:
        existing = self.create_existing(subject="owner  profile", value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(subject="owner profile", value="coffee")
        )

        self.assertEqual(DecisionType.CONFLICT_REVIEW, decision.decision_type)
        self.assertEqual(
            DecisionReason.CANONICAL_IDENTITY_VARIANT_REQUIRES_REVIEW,
            decision.reason_code,
        )
        self.assertFalse(decision.persistence_permitted)
        with self.assertRaises(DecisionNotApplicableError):
            self.validation_service.apply(decision)
        self.assertEqual([existing], self.memory_service.query_memories())

    def test_exact_value_with_unlinked_storage_variant_remains_duplicate(self) -> None:
        variant = self.create_existing(subject="owner  profile", value="tea")
        exact = self.create_existing(subject="owner profile", value="coffee")

        decision = self.validation_service.evaluate(
            self.candidate(subject="owner profile", value="coffee")
        )

        self.assertEqual(DecisionType.EXACT_DUPLICATE, decision.decision_type)
        self.assertEqual(
            DecisionReason.EXACT_VALUE_ALREADY_ACTIVE,
            decision.reason_code,
        )
        self.assertEqual((), decision.conflict_ids)
        self.assertEqual(
            tuple(sorted((variant.memory_id, exact.memory_id), key=str)),
            decision.relevant_memory_ids,
        )
        self.assertEqual(1, decision.metadata["storage_identity_variant_count"])

    def test_owner_correction_uses_memory_os_revision_history(self) -> None:
        original = self.create_existing(value="tea")
        candidate = self.candidate(
            value="coffee",
            provenance=owner_statement("owner.correction"),
            observed_at=OBSERVED_AT + timedelta(days=1),
            correction_target_id=original.memory_id,
            correction_reason="Owner corrected the preference",
        )
        decision = self.validation_service.evaluate(candidate)
        result = self.validation_service.apply(decision)

        self.assertEqual(DecisionType.APPLY_CORRECTION, decision.decision_type)
        self.assertEqual(
            DecisionReason.EXPLICIT_CORRECTION_ALLOWED,
            decision.reason_code,
        )
        self.assertTrue(result.mutation_applied)
        self.assertEqual(original.memory_id, result.memory.supersedes)
        self.assertEqual(
            MemoryStatus.SUPERSEDED,
            self.memory_service.get_memory(original.memory_id).status,
        )
        history = self.memory_service.get_revision_history(result.memory.memory_id)
        self.assertEqual(
            [original.memory_id, result.memory.memory_id],
            [record.memory_id for record in history],
        )
        self.assertEqual(candidate.provenance, result.memory.provenance)

    def test_trusted_manual_import_can_correct(self) -> None:
        original = self.create_existing(predicate="favorite_color", value="blue")
        candidate = self.candidate(
            predicate="favorite_color",
            value="green",
            provenance=provenance(
                ProvenanceType.TRUSTED_MANUAL_IMPORT,
                "owner.reviewed_import",
            ),
            correction_target_id=original.memory_id,
            correction_reason="Owner-approved imported correction",
        )
        decision = self.validation_service.evaluate(candidate)
        result = self.validation_service.apply(decision)

        self.assertEqual(DecisionType.APPLY_CORRECTION, decision.decision_type)
        self.assertTrue(result.mutation_applied)
        self.assertEqual(
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
            result.memory.provenance.provenance_type,
        )

    def test_non_authoritative_sources_cannot_destructively_correct(self) -> None:
        target = self.create_existing(value="tea")
        forbidden_types = (
            ProvenanceType.DIRECT_OBSERVATION,
            ProvenanceType.DERIVED_INFERENCE,
            ProvenanceType.SYSTEM_EVENT,
        )
        for provenance_type in forbidden_types:
            with self.subTest(provenance_type=provenance_type):
                candidate = self.candidate(
                    value="coffee",
                    provenance=provenance(provenance_type, f"source.{provenance_type.value}"),
                    confidence=1.0,
                    correction_target_id=target.memory_id,
                    correction_reason="Unsupported destructive correction",
                )
                decision = self.validation_service.evaluate(candidate)
                self.assertEqual(DecisionType.REJECT, decision.decision_type)
                self.assertEqual(
                    DecisionReason.CORRECTION_AUTHORITY_FORBIDDEN,
                    decision.reason_code,
                )
                self.assertFalse(decision.persistence_permitted)
                with self.assertRaises(DecisionNotApplicableError):
                    self.validation_service.apply(decision)
                self.assertEqual(
                    MemoryStatus.ACTIVE,
                    self.memory_service.get_memory(target.memory_id).status,
                )

    def test_invalid_correction_targets_are_rejected_deterministically(self) -> None:
        missing = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=UUID(int=999),
                correction_reason="Target is missing",
            )
        )
        self.assertEqual(DecisionType.REJECT, missing.decision_type)
        self.assertEqual(DecisionReason.CORRECTION_TARGET_NOT_FOUND, missing.reason_code)

        target = self.create_existing(predicate="preferred_drink")
        mismatch = self.validation_service.evaluate(
            self.candidate(
                predicate="favorite_color",
                value="blue",
                correction_target_id=target.memory_id,
                correction_reason="Wrong logical identity",
            )
        )
        self.assertEqual(DecisionType.REJECT, mismatch.decision_type)
        self.assertEqual(DecisionReason.CORRECTION_IDENTITY_MISMATCH, mismatch.reason_code)

        retracted = self.create_existing(predicate="snack", value="fruit")
        self.memory_service.retract_memory(retracted.memory_id, reason="Owner withdrew it")
        inactive = self.validation_service.evaluate(
            self.candidate(
                predicate="snack",
                value="nuts",
                correction_target_id=retracted.memory_id,
                correction_reason="Cannot revise retracted evidence",
            )
        )
        self.assertEqual(DecisionType.REJECT, inactive.decision_type)
        self.assertEqual(DecisionReason.CORRECTION_TARGET_NOT_ACTIVE, inactive.reason_code)

    def test_reapplying_correction_decision_is_idempotent(self) -> None:
        original = self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=original.memory_id,
                correction_reason="Owner correction",
            )
        )
        first = self.validation_service.apply(decision)
        second = self.validation_service.apply(decision)

        self.assertTrue(first.mutation_applied)
        self.assertFalse(second.mutation_applied)
        self.assertEqual(first.memory_id, second.memory_id)
        self.assertEqual(
            DecisionReason.CORRECTION_ALREADY_APPLIED,
            second.decision.reason_code,
        )
        self.assertEqual(2, len(self.memory_service.get_revision_history(original.memory_id)))

    def test_stale_correction_is_rejected_after_target_is_superseded(self) -> None:
        target = self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=target.memory_id,
                correction_reason="Owner correction",
            )
        )
        external = self.memory_service.correct_memory(
            target.memory_id,
            value="water",
            provenance=owner_statement("owner.external-correction"),
            confidence=0.95,
            observed_at=OBSERVED_AT + timedelta(days=1),
            reason="Concurrent owner correction",
        )

        with self.assertRaises(StaleDecisionError):
            self.validation_service.apply(decision)

        history = self.memory_service.get_revision_history(target.memory_id)
        self.assertEqual([target.memory_id, external.memory_id], [r.memory_id for r in history])
        self.assertEqual("water", history[-1].value)

    def test_stale_correction_is_rejected_after_target_is_retracted(self) -> None:
        target = self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=target.memory_id,
                correction_reason="Owner correction",
            )
        )
        self.memory_service.retract_memory(
            target.memory_id,
            reason="Owner withdrew the target",
        )

        with self.assertRaises(StaleDecisionError):
            self.validation_service.apply(decision)

        self.assertEqual(
            MemoryStatus.RETRACTED,
            self.memory_service.get_memory(target.memory_id).status,
        )
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))

    def test_final_correction_race_is_rejected_atomically_by_memory_os(self) -> None:
        target = self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=target.memory_id,
                correction_reason="Owner correction",
            )
        )
        correct_memory = self.memory_service.correct_memory

        def retract_then_correct(memory_id, **kwargs):
            self.memory_service.retract_memory(
                memory_id,
                reason="Concurrent owner retraction",
            )
            return correct_memory(memory_id, **kwargs)

        with patch.object(
            self.memory_service,
            "correct_memory",
            side_effect=retract_then_correct,
        ):
            with self.assertRaises(AlreadyRetractedError):
                self.validation_service.apply(decision)

        self.assertEqual(
            MemoryStatus.RETRACTED,
            self.memory_service.get_memory(target.memory_id).status,
        )
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))

    def test_final_create_race_is_atomic_but_not_compare_and_write(self) -> None:
        candidate = self.candidate(value="tea")
        decision = self.validation_service.evaluate(candidate)
        create_memory = self.memory_service.create_memory
        injected = False

        def create_after_equivalent_insert(**kwargs):
            nonlocal injected
            if not injected:
                injected = True
                concurrent_arguments = dict(kwargs)
                concurrent_arguments["provenance"] = derived_inference(
                    "concurrent.writer"
                )
                create_memory(**concurrent_arguments)
            return create_memory(**kwargs)

        with patch.object(
            self.memory_service,
            "create_memory",
            side_effect=create_after_equivalent_insert,
        ):
            result = self.validation_service.apply(decision)

        self.assertTrue(result.mutation_applied)
        memories = self.memory_service.query_memories(active_only=False)
        self.assertEqual(2, len(memories))
        self.assertEqual({"tea"}, {memory.value for memory in memories})
        self.assertEqual([], self.memory_service.list_conflicts())

    def test_correction_resolves_only_applicable_conflicts(self) -> None:
        drink = self.create_existing(value="tea")
        self.create_existing(value="coffee", provenance=derived_inference())
        self.create_existing(predicate="favorite_color", value="blue")
        self.create_existing(
            predicate="favorite_color",
            value="green",
            provenance=derived_inference(),
        )
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=drink.memory_id,
                correction_reason="Owner selected the correct drink",
            )
        )

        result = self.validation_service.apply(decision)

        self.assertTrue(result.mutation_applied)
        unresolved = self.memory_service.list_conflicts()
        self.assertEqual(1, len(unresolved))
        self.assertEqual("favorite_color", unresolved[0].left_memory.predicate)
        drink_history = self.memory_service.list_conflicts(
            predicate="preferred_drink",
            include_resolved=True,
        )
        self.assertEqual(2, len(drink_history))
        self.assertTrue(all(conflict.resolved_at is not None for conflict in drink_history))

    def test_failed_correction_remains_atomic_in_memory_os(self) -> None:
        ids = iter((UUID(int=10), UUID(int=20), UUID(int=20)))
        self.memory_service = MemoryService(
            self.store,
            clock=self.clock,
            id_factory=lambda: next(ids),
        )
        self.validation_service = MemoryValidationService(self.memory_service)
        target = self.create_existing(value="tea")
        self.create_existing(
            memory_type=MemoryType.SPATIAL,
            subject="workshop",
            predicate="tool_location",
            value="north_wall",
        )
        decision = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=target.memory_id,
                correction_reason="Owner correction",
            )
        )

        with self.assertRaises(PersistenceConflictError):
            self.validation_service.apply(decision)

        self.assertEqual(
            MemoryStatus.ACTIVE,
            self.memory_service.get_memory(target.memory_id).status,
        )
        self.assertEqual([target], self.memory_service.get_revision_history(target.memory_id))

    def test_failed_conflict_creation_leaves_no_partial_memory_or_conflict(self) -> None:
        ids = iter((UUID(int=10), UUID(int=20), UUID(int=20)))
        self.memory_service = MemoryService(
            self.store,
            clock=self.clock,
            id_factory=lambda: next(ids),
        )
        self.validation_service = MemoryValidationService(self.memory_service)
        existing = self.create_existing(value="tea")
        unrelated = self.create_existing(
            memory_type=MemoryType.SPATIAL,
            subject="workshop",
            predicate="tool_location",
            value="north_wall",
        )
        decision = self.validation_service.evaluate(
            self.candidate(value="coffee", provenance=derived_inference())
        )

        with self.assertRaises(PersistenceConflictError):
            self.validation_service.apply(decision)

        self.assertEqual(
            {existing.memory_id, unrelated.memory_id},
            {
                record.memory_id
                for record in self.memory_service.query_memories(active_only=False)
            },
        )
        self.assertEqual([], self.memory_service.list_conflicts(include_resolved=True))

    def test_failed_new_memory_creation_leaves_no_partial_memory(self) -> None:
        ids = iter((UUID(int=10), UUID(int=20), UUID(int=20)))
        self.memory_service = MemoryService(
            self.store,
            clock=self.clock,
            id_factory=lambda: next(ids),
        )
        self.validation_service = MemoryValidationService(self.memory_service)
        first = self.create_existing(
            memory_type=MemoryType.SPATIAL,
            subject="workshop",
            predicate="tool_location",
            value="north_wall",
        )
        second = self.create_existing(
            memory_type=MemoryType.SOCIAL,
            subject="visitor",
            predicate="display_name",
            value="Sam",
        )
        decision = self.validation_service.evaluate(
            self.candidate(predicate="favorite_color", value="blue")
        )

        with self.assertRaises(PersistenceConflictError):
            self.validation_service.apply(decision)

        self.assertEqual(
            {first.memory_id, second.memory_id},
            {
                record.memory_id
                for record in self.memory_service.query_memories(active_only=False)
            },
        )

    def test_public_decision_constructor_rejects_impossible_states(self) -> None:
        accepted = self.validation_service.evaluate(self.candidate())
        with self.assertRaises(PolicyInvariantError):
            replace(
                accepted,
                reason_code=DecisionReason.EXPLICIT_CORRECTION_ALLOWED,
            )
        with self.assertRaises(PolicyInvariantError):
            replace(
                accepted,
                normalized_identity=NormalizedIdentity(
                    memory_type=MemoryType.PREFERENCE,
                    subject="owner",
                    predicate="favorite_color",
                ),
            )
        with self.assertRaises(PolicyInvariantError):
            replace(accepted, explanatory_metadata=((1, None),))
        with self.assertRaises(PolicyInvariantError):
            ApplicationResult(
                decision=accepted,
                mutation_applied=False,
                memory=None,
            )

        existing = self.create_existing(value="tea")
        duplicate = self.validation_service.evaluate(self.candidate(value="tea"))
        with self.assertRaises(PolicyInvariantError):
            replace(duplicate, relevant_memory_ids=())
        review = self.validation_service.evaluate(
            self.candidate(value="coffee", provenance=derived_inference())
        )
        with self.assertRaises(PolicyInvariantError):
            replace(review, persistence_permitted=False)

        correction = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=existing.memory_id,
                correction_reason="Owner correction",
            )
        )
        unauthorized_candidate = self.candidate(
            value="coffee",
            provenance=derived_inference(),
            correction_target_id=existing.memory_id,
            correction_reason="Inference cannot correct",
        )
        with self.assertRaises(PolicyInvariantError):
            replace(correction, candidate=unauthorized_candidate)

        rejected = self.validation_service.evaluate(
            self.candidate(
                value="coffee",
                correction_target_id=UUID(int=999),
                correction_reason="Missing correction target",
            )
        )
        with self.assertRaises(PolicyInvariantError):
            replace(rejected, persistence_permitted=True)

    def test_apply_rejects_forged_unrelated_relevant_memory_ids(self) -> None:
        self.create_existing(value="tea")
        decision = self.validation_service.evaluate(
            self.candidate(value="coffee", provenance=derived_inference())
        )
        forged = replace(decision, relevant_memory_ids=(UUID(int=999),))

        with self.assertRaises(StaleDecisionError):
            self.validation_service.apply(forged)

        self.assertEqual(1, len(self.memory_service.query_memories()))

    def test_policy_rejects_conflicts_absent_from_active_snapshot(self) -> None:
        first = self.create_existing(value="tea")
        self.create_existing(value="coffee", provenance=derived_inference())
        conflict = self.memory_service.list_conflicts()[0]
        normalized = self.validation_service.normalize(
            self.candidate(value="water", provenance=derived_inference())
        )

        with self.assertRaises(PolicyInvariantError):
            DeterministicValidationPolicy().evaluate(
                normalized,
                active_memories=(first,),
                conflicts=(conflict,),
            )

    def test_policy_rejects_truncated_correction_revision_snapshot(self) -> None:
        target = self.create_existing(value="tea")
        self.memory_service.correct_memory(
            target.memory_id,
            value="coffee",
            provenance=owner_statement("owner.concurrent-correction"),
            confidence=0.95,
            observed_at=OBSERVED_AT + timedelta(days=1),
            reason="Concurrent owner correction",
        )
        candidate = self.candidate(
            value="coffee",
            correction_target_id=target.memory_id,
            correction_reason="Owner correction",
        )
        normalized = self.validation_service.normalize(candidate)
        target_snapshot = self.memory_service.get_memory(target.memory_id)

        with self.assertRaises(PolicyInvariantError):
            DeterministicValidationPolicy().evaluate(
                normalized,
                active_memories=tuple(self.memory_service.query_memories()),
                conflicts=tuple(self.memory_service.list_conflicts()),
                correction_target=target_snapshot,
                revision_history=(target_snapshot,),
            )

    def test_stale_mutating_decision_is_rejected(self) -> None:
        candidate = self.candidate(value="tea")
        decision = self.validation_service.evaluate(candidate)
        self.create_existing(value="coffee")

        with self.assertRaises(StaleDecisionError):
            self.validation_service.apply(decision)
        self.assertEqual(1, len(self.memory_service.query_memories()))

    def test_closed_memory_store_error_is_not_hidden(self) -> None:
        self.store.close()
        with self.assertRaises(StoreClosedError):
            self.validation_service.evaluate(self.candidate())

    def test_closed_memory_store_error_during_apply_is_not_hidden(self) -> None:
        decision = self.validation_service.evaluate(self.candidate())
        self.store.close()

        with self.assertRaises(StoreClosedError):
            self.validation_service.apply(decision)


if __name__ == "__main__":
    unittest.main()
