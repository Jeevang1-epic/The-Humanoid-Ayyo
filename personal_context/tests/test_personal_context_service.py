from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from ayyo_memory import (
    MemoryConflict,
    MemoryRecord,
    MemoryService,
    MemoryStatus,
    MemoryType,
    Provenance,
    ProvenanceType,
    SQLiteMemoryStore,
    StoreClosedError,
)
from ayyo_personal_context import (
    ContextDomain,
    ContextState,
    InconsistentSourceStateError,
    InvalidOwnerError,
    PersonalContextProjector,
    PersonalContextService,
    PersonalContextValidationError,
)


OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class IncrementingClock:
    def __init__(self) -> None:
        self._next = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(microseconds=1)
        return current


def provenance(source_id: str = "owner.voice") -> Provenance:
    return Provenance(
        ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        source_id,
        {"evidence": {"frames": [f"{source_id}-frame"]}},
    )


class PersonalContextServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.store = SQLiteMemoryStore(self.database_path)
        self.memory_service = MemoryService(self.store, clock=IncrementingClock())
        self.service = PersonalContextService(
            self.memory_service,
            owner_subject="owner",
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def create(self, **overrides) -> MemoryRecord:
        arguments = {
            "memory_type": MemoryType.PREFERENCE,
            "subject": "owner",
            "predicate": "preferred_drink",
            "value": "tea",
            "provenance": provenance(),
            "confidence": 0.9,
            "observed_at": OBSERVED_AT,
            "metadata": {"test": "context"},
        }
        arguments.update(overrides)
        return self.memory_service.create_memory(**arguments)

    def test_empty_store_is_stable_and_queries_unknown(self) -> None:
        self.assertEqual("owner", self.service.owner_subject)
        first = self.service.build_snapshot()
        second = self.service.build_snapshot()

        self.assertEqual((), first.entries)
        self.assertEqual(first, second)
        self.assertEqual(first.version, self.service.snapshot_version())
        result = self.service.get_context(
            ContextDomain.PREFERENCE,
            "preferred_drink",
        )
        self.assertEqual(ContextState.UNKNOWN, result.state)
        self.assertIsNone(result.entry)

    def test_each_supported_memory_type_maps_to_one_context_domain(self) -> None:
        supported = (
            (MemoryType.SEMANTIC, ContextDomain.SEMANTIC),
            (MemoryType.PREFERENCE, ContextDomain.PREFERENCE),
            (MemoryType.SOCIAL, ContextDomain.SOCIAL),
            (MemoryType.SPATIAL, ContextDomain.SPATIAL),
            (MemoryType.PROCEDURAL, ContextDomain.PROCEDURAL),
        )
        for index, (memory_type, _) in enumerate(supported):
            self.create(
                memory_type=memory_type,
                predicate=f"predicate_{index}",
                value=f"value_{index}",
            )

        snapshot = self.service.build_snapshot()

        self.assertEqual(
            {domain for _, domain in supported},
            {entry.identity.domain for entry in snapshot.entries},
        )
        self.assertTrue(
            all(entry.state is ContextState.RESOLVED for entry in snapshot.entries)
        )

    def test_episodic_and_failure_memories_are_excluded(self) -> None:
        initial_version = self.service.snapshot_version()
        for memory_type in (MemoryType.EPISODIC, MemoryType.FAILURE):
            self.create(
                memory_type=memory_type,
                predicate=f"excluded_{memory_type.value}",
                value={"event": memory_type.value},
            )

        snapshot = self.service.build_snapshot()

        self.assertEqual((), snapshot.entries)
        self.assertEqual(initial_version, snapshot.version)

    def test_one_active_value_is_resolved_with_traceable_evidence(self) -> None:
        memory = self.create(
            value={"drink": "tea", "temperature": "warm"},
            confidence=0.75,
            provenance=provenance("owner.import"),
        )

        result = self.service.get_context(
            ContextDomain.PREFERENCE,
            "preferred_drink",
        )

        self.assertEqual(ContextState.RESOLVED, result.state)
        self.assertEqual(1, len(result.entry.values))
        self.assertEqual(
            {"drink": "tea", "temperature": "warm"},
            result.entry.values[0].value,
        )
        reference = result.entry.values[0].evidence[0]
        self.assertEqual(memory.memory_id, reference.memory_id)
        self.assertEqual("owner.import", reference.provenance_source_id)
        self.assertEqual(0.75, reference.confidence)
        self.assertEqual(
            {"evidence": {"frames": ["owner.import-frame"]}},
            reference.provenance_details,
        )
        self.assertEqual({"test": "context"}, reference.metadata)

    def test_social_relationship_remains_owner_centric_and_explicit(self) -> None:
        self.create(
            memory_type=MemoryType.SOCIAL,
            predicate="relationship",
            value={"person_id": "person-42", "kind": "friend"},
            metadata={"related_person_id": "person-42"},
        )

        result = self.service.get_context(ContextDomain.SOCIAL, "relationship")

        self.assertEqual("owner", result.identity.subject)
        self.assertEqual(
            {"person_id": "person-42", "kind": "friend"},
            result.entry.values[0].value,
        )
        self.assertEqual(
            {"related_person_id": "person-42"},
            result.entry.values[0].evidence[0].metadata,
        )

    def test_equivalent_active_values_collapse_with_all_evidence(self) -> None:
        first = self.create(value={"b": 2, "a": [1]})
        second = self.create(
            value={"a": [1], "b": 2},
            provenance=provenance("owner.second-statement"),
        )

        result = self.service.get_context(
            ContextDomain.PREFERENCE,
            "preferred_drink",
        )

        self.assertEqual(ContextState.RESOLVED, result.state)
        self.assertEqual(1, len(result.entry.values))
        self.assertEqual(
            tuple(sorted((first.memory_id, second.memory_id), key=str)),
            tuple(
                reference.memory_id for reference in result.entry.values[0].evidence
            ),
        )
        self.assertEqual((), result.entry.conflict_ids)

    def test_different_active_values_remain_explicitly_conflicted(self) -> None:
        first = self.create(value="tea", confidence=0.1)
        second = self.create(value="coffee", confidence=1.0)

        result = self.service.get_context(
            ContextDomain.PREFERENCE,
            "preferred_drink",
        )

        self.assertEqual(ContextState.CONFLICTED, result.state)
        self.assertEqual({"tea", "coffee"}, {value.value for value in result.entry.values})
        self.assertEqual(1, len(result.entry.conflict_ids))
        self.assertEqual(
            {first.memory_id, second.memory_id},
            {
                reference.memory_id
                for value in result.entry.values
                for reference in value.evidence
            },
        )

    def test_boolean_and_integer_values_remain_distinct(self) -> None:
        self.create(value=False)
        self.create(value=0)

        result = self.service.get_context(
            ContextDomain.PREFERENCE,
            "preferred_drink",
        )

        self.assertEqual(ContextState.CONFLICTED, result.state)
        self.assertEqual(
            {"false", "0"},
            {value.canonical_value for value in result.entry.values},
        )

    def test_unicode_structured_value_is_preserved_exactly(self) -> None:
        expected = {"drink": "ಕಾಫಿ ☕", "note": "Café"}
        self.create(
            memory_type=MemoryType.SEMANTIC,
            predicate="unicode_profile",
            value=expected,
        )

        result = self.service.get_context(
            ContextDomain.SEMANTIC,
            "unicode_profile",
        )

        self.assertEqual(expected, result.entry.values[0].value)

    def test_confidence_recency_and_uuid_do_not_select_a_conflict_winner(self) -> None:
        ids = iter((UUID(int=100), UUID(int=1), UUID(int=50)))
        alternate_store = SQLiteMemoryStore(
            Path(self.temporary_directory.name) / "alternate.sqlite3"
        )
        try:
            memory = MemoryService(
                alternate_store,
                clock=IncrementingClock(),
                id_factory=lambda: next(ids),
            )
            service = PersonalContextService(memory, owner_subject="owner")
            memory.create_memory(
                memory_type=MemoryType.PREFERENCE,
                subject="owner",
                predicate="preferred_drink",
                value="older-low-confidence",
                provenance=provenance("older"),
                confidence=0.01,
                observed_at=OBSERVED_AT,
            )
            memory.create_memory(
                memory_type=MemoryType.PREFERENCE,
                subject="owner",
                predicate="preferred_drink",
                value="newer-high-confidence",
                provenance=provenance("newer"),
                confidence=1.0,
                observed_at=OBSERVED_AT + timedelta(days=1),
            )

            result = service.get_context(
                ContextDomain.PREFERENCE,
                "preferred_drink",
            )

            self.assertEqual(ContextState.CONFLICTED, result.state)
            self.assertEqual(2, len(result.entry.values))
        finally:
            alternate_store.close()

    def test_correction_changes_value_and_preserves_lineage_reference(self) -> None:
        original = self.create(value="tea")
        before = self.service.build_snapshot()
        corrected = self.memory_service.correct_memory(
            original.memory_id,
            value="coffee",
            provenance=provenance("owner.correction"),
            confidence=0.95,
            observed_at=OBSERVED_AT + timedelta(days=1),
            reason="Owner corrected their preference",
        )

        after = self.service.build_snapshot()
        reference = after.entries[0].values[0].evidence[0]

        self.assertNotEqual(before.version, after.version)
        self.assertEqual("coffee", after.entries[0].values[0].value)
        self.assertEqual(corrected.memory_id, reference.memory_id)
        self.assertEqual(original.memory_id, reference.supersedes)
        self.assertEqual("Owner corrected their preference", reference.revision_reason)

    def test_retraction_removes_context_and_changes_version(self) -> None:
        memory = self.create(value="tea")
        before = self.service.build_snapshot()

        self.memory_service.retract_memory(memory.memory_id, reason="Owner withdrew it")
        after = self.service.build_snapshot()

        self.assertNotEqual(before.version, after.version)
        self.assertEqual((), after.entries)
        self.assertEqual(
            ContextState.UNKNOWN,
            after.get_context(ContextDomain.PREFERENCE, "preferred_drink").state,
        )

    def test_retraction_resolves_conflict_without_hiding_remaining_value(self) -> None:
        remaining = self.create(value="tea")
        removed = self.create(value="coffee")
        conflicted = self.service.build_snapshot()

        self.memory_service.retract_memory(removed.memory_id, reason="Bad evidence")
        resolved = self.service.build_snapshot()

        self.assertEqual(ContextState.CONFLICTED, conflicted.entries[0].state)
        self.assertEqual(ContextState.RESOLVED, resolved.entries[0].state)
        self.assertEqual("tea", resolved.entries[0].values[0].value)
        self.assertEqual(remaining.memory_id, resolved.entries[0].values[0].evidence[0].memory_id)
        self.assertEqual((), resolved.entries[0].conflict_ids)

    def test_correction_can_resolve_conflict_to_equivalent_active_values(self) -> None:
        target = self.create(value="tea")
        existing = self.create(value="coffee")

        corrected = self.memory_service.correct_memory(
            target.memory_id,
            value="coffee",
            provenance=provenance("owner.correction"),
            confidence=1.0,
            observed_at=OBSERVED_AT + timedelta(days=1),
            reason="Owner selected coffee",
        )
        snapshot = self.service.build_snapshot()

        self.assertEqual(ContextState.RESOLVED, snapshot.entries[0].state)
        self.assertEqual(1, len(snapshot.entries[0].values))
        self.assertEqual(
            tuple(sorted((existing.memory_id, corrected.memory_id), key=str)),
            tuple(
                reference.memory_id
                for reference in snapshot.entries[0].values[0].evidence
            ),
        )

    def test_snapshot_is_deterministic_under_source_iteration_order(self) -> None:
        self.create(
            memory_type=MemoryType.SEMANTIC,
            predicate="birth_city",
            value="Hyderabad",
        )
        self.create(predicate="preferred_drink", value="tea")
        self.create(predicate="preferred_drink", value="coffee")
        memories = self.memory_service.query_memories(subject="owner")
        conflicts = self.memory_service.list_conflicts(subject="owner")
        projector = PersonalContextProjector()

        forward = projector.project(
            "owner",
            active_memories=memories,
            unresolved_conflicts=conflicts,
        )
        reverse = projector.project(
            "owner",
            active_memories=tuple(reversed(memories)),
            unresolved_conflicts=tuple(reversed(conflicts)),
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(forward.version, reverse.version)

    def test_repeated_builds_and_reads_do_not_mutate_memory_os(self) -> None:
        self.create(value="tea")
        before = self.memory_service.query_memories(active_only=False)
        conflicts_before = self.memory_service.list_conflicts(include_resolved=True)

        snapshots = [self.service.build_snapshot() for _ in range(5)]
        for _ in range(5):
            self.service.get_context(ContextDomain.PREFERENCE, "preferred_drink")

        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))
        self.assertEqual(before, self.memory_service.query_memories(active_only=False))
        self.assertEqual(
            conflicts_before,
            self.memory_service.list_conflicts(include_resolved=True),
        )

    def test_snapshot_uses_exactly_two_filtered_public_reads(self) -> None:
        self.create(value="tea")
        with (
            patch.object(
                self.memory_service,
                "query_memories",
                wraps=self.memory_service.query_memories,
            ) as query,
            patch.object(
                self.memory_service,
                "list_conflicts",
                wraps=self.memory_service.list_conflicts,
            ) as conflicts,
        ):
            self.service.build_snapshot()

        query.assert_called_once_with(subject="owner", active_only=True)
        conflicts.assert_called_once_with(subject="owner", include_resolved=False)

    def test_owner_isolation_and_other_owner_changes_do_not_change_version(self) -> None:
        self.create(value="tea")
        before = self.service.build_snapshot()
        other = self.create(
            subject="other-owner",
            predicate="private_note",
            value="first private value",
        )
        self.create(
            subject="other-owner",
            predicate="private_note",
            value="conflicting private value",
        )
        after_insert = self.service.build_snapshot()
        self.memory_service.retract_memory(other.memory_id, reason="Other owner withdrew")
        after_retraction = self.service.build_snapshot()

        self.assertEqual(before, after_insert)
        self.assertEqual(before, after_retraction)
        self.assertTrue(
            all(entry.identity.subject == "owner" for entry in after_insert.entries)
        )

    def test_duplicate_memory_ids_fail_even_when_one_domain_is_excluded(self) -> None:
        supported = self.create(value="tea")
        excluded = MemoryRecord(
            memory_id=supported.memory_id,
            memory_type=MemoryType.EPISODIC,
            subject=supported.subject,
            predicate="event",
            value="walked",
            provenance=supported.provenance,
            confidence=supported.confidence,
            observed_at=supported.observed_at,
            created_at=supported.created_at,
            status=MemoryStatus.ACTIVE,
            status_changed_at=supported.status_changed_at,
        )

        with self.assertRaises(InconsistentSourceStateError):
            PersonalContextProjector().project(
                "owner",
                active_memories=(excluded, supported),
                unresolved_conflicts=(),
            )

    def test_case_and_internal_whitespace_identity_boundaries_are_exact(self) -> None:
        self.create(subject="Owner", predicate="preferred_drink", value="coffee")
        self.create(subject="owner profile", predicate="preferred_drink", value="water")
        self.create(subject="owner", predicate="preferred  drink", value="juice")
        self.create(subject="owner", predicate="preferred_drink", value="tea")

        snapshot = self.service.build_snapshot()

        self.assertEqual(2, len(snapshot.entries))
        self.assertEqual(
            ContextState.RESOLVED,
            snapshot.get_context(ContextDomain.PREFERENCE, "preferred_drink").state,
        )
        self.assertEqual(
            ContextState.RESOLVED,
            snapshot.get_context(ContextDomain.PREFERENCE, "preferred  drink").state,
        )
        self.assertEqual(
            ContextState.UNKNOWN,
            snapshot.get_context(ContextDomain.PREFERENCE, "Preferred_Drink").state,
        )

    def test_snapshot_outputs_cannot_mutate_snapshot_or_memory_os(self) -> None:
        memory = self.create(value={"choices": ["tea"]})
        snapshot = self.service.build_snapshot()
        returned = snapshot.entries[0].values[0].value
        returned["choices"].append("coffee")
        details = snapshot.entries[0].values[0].evidence[0].provenance_details
        details["evidence"]["frames"].append("forged")
        metadata = snapshot.entries[0].values[0].evidence[0].metadata
        metadata["test"] = "forged"

        self.assertEqual(
            {"choices": ["tea"]},
            snapshot.entries[0].values[0].value,
        )
        self.assertEqual(
            {"choices": ["tea"]},
            self.memory_service.get_memory(memory.memory_id).value,
        )
        self.assertEqual(
            ["owner.voice-frame"],
            snapshot.entries[0].values[0].evidence[0].provenance_details[
                "evidence"
            ]["frames"],
        )
        self.assertEqual(
            {"test": "context"},
            snapshot.entries[0].values[0].evidence[0].metadata,
        )

    def test_relevant_owner_change_changes_version(self) -> None:
        empty = self.service.build_snapshot()
        first = self.create(value="tea")
        added = self.service.build_snapshot()
        second = self.create(value="tea", provenance=provenance("owner.repeat"))
        reinforced = self.service.build_snapshot()
        self.memory_service.retract_memory(second.memory_id, reason="Duplicate withdrawn")
        withdrawn = self.service.build_snapshot()

        self.assertNotEqual(empty.version, added.version)
        self.assertNotEqual(added.version, reinforced.version)
        self.assertEqual(added.version, withdrawn.version)
        self.assertEqual(first.memory_id, withdrawn.entries[0].values[0].evidence[0].memory_id)

    def test_invalid_owner_and_dependency_construction_fail_typed(self) -> None:
        for owner in ("", " owner", "owner ", None):
            with self.subTest(owner=owner):
                with self.assertRaises(InvalidOwnerError):
                    PersonalContextService(self.memory_service, owner_subject=owner)
        with self.assertRaises(PersonalContextValidationError):
            PersonalContextService(object(), owner_subject="owner")

    def test_closed_memory_store_failure_is_not_hidden(self) -> None:
        self.store.close()
        with self.assertRaises(StoreClosedError):
            self.service.build_snapshot()

    def test_unexpected_memory_service_failure_is_not_hidden(self) -> None:
        failure = RuntimeError("unexpected dependency failure")
        with patch.object(
            self.memory_service,
            "query_memories",
            side_effect=failure,
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected dependency failure"):
                self.service.build_snapshot()

    def test_incomplete_or_stale_conflict_reads_fail_closed(self) -> None:
        first = self.create(value="tea")
        second = self.create(value="coffee")
        records = self.memory_service.query_memories(subject="owner")
        conflict = self.memory_service.list_conflicts(subject="owner")[0]
        projector = PersonalContextProjector()

        with self.assertRaises(InconsistentSourceStateError):
            projector.project(
                "owner",
                active_memories=records,
                unresolved_conflicts=(),
            )
        with self.assertRaises(InconsistentSourceStateError):
            projector.project(
                "owner",
                active_memories=(first,),
                unresolved_conflicts=(conflict,),
            )

        self.assertEqual({first.memory_id, second.memory_id}, {r.memory_id for r in records})

    def test_projector_rejects_wrong_owner_in_filtered_source_state(self) -> None:
        other = self.create(subject="other-owner")
        with self.assertRaises(InconsistentSourceStateError):
            PersonalContextProjector().project(
                "owner",
                active_memories=(other,),
                unresolved_conflicts=(),
            )

    def test_projector_rejects_conflict_snapshot_mismatch(self) -> None:
        self.create(value="tea")
        self.create(value="coffee")
        records = self.memory_service.query_memories(subject="owner")
        conflict = self.memory_service.list_conflicts(subject="owner")[0]
        altered_left = MemoryRecord(
            **{
                field: getattr(conflict.left_memory, field)
                for field in conflict.left_memory.__dataclass_fields__
                if field not in {"value"}
            },
            value="altered",
        )
        altered_conflict = MemoryConflict(
            conflict_id=conflict.conflict_id,
            left_memory=altered_left,
            right_memory=conflict.right_memory,
            created_at=conflict.created_at,
            reason=conflict.reason,
        )

        with self.assertRaises(InconsistentSourceStateError):
            PersonalContextProjector().project(
                "owner",
                active_memories=records,
                unresolved_conflicts=(altered_conflict,),
            )


if __name__ == "__main__":
    unittest.main()
