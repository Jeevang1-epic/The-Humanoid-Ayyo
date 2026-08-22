from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from ayyo_memory import (
    AlreadyRetractedError,
    CURRENT_SCHEMA_VERSION,
    InvalidConfidenceError,
    InvalidCorrectionTargetError,
    InvalidMemoryDataError,
    InvalidProvenanceError,
    MemoryRecord,
    MemoryNotFoundError,
    MemoryPersistenceError,
    MemoryService,
    MemoryStatus,
    MemoryType,
    PersistenceConflictError,
    Provenance,
    ProvenanceType,
    SchemaVersionError,
    SQLiteMemoryStore,
    StoreClosedError,
)


OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class IncrementingClock:
    def __init__(self) -> None:
        self._next = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(microseconds=1)
        return current


def owner_statement(source_id: str = "owner.voice") -> Provenance:
    return Provenance(
        ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        source_id,
        {"interaction_id": "interaction-001"},
    )


def inference(source_id: str = "preference.classifier") -> Provenance:
    return Provenance(
        ProvenanceType.DERIVED_INFERENCE,
        source_id,
        {"method": "behavioral-observation"},
    )


class MemoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.store = SQLiteMemoryStore(self.database_path)
        self.clock = IncrementingClock()
        self.service = MemoryService(self.store, clock=self.clock)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def create_memory(
        self,
        *,
        memory_type: MemoryType = MemoryType.PREFERENCE,
        subject: str = "owner",
        predicate: str = "preferred_drink",
        value: object = "tea",
        provenance: Provenance | None = None,
        confidence: float = 0.95,
    ):
        return self.service.create_memory(
            memory_type=memory_type,
            subject=subject,
            predicate=predicate,
            value=value,
            provenance=provenance or owner_statement(),
            confidence=confidence,
            observed_at=OBSERVED_AT,
            metadata={"context": "kitchen"},
        )

    def correct_memory(self, memory_id: UUID, value: object = "coffee"):
        return self.service.correct_memory(
            memory_id,
            value=value,
            provenance=owner_statement("owner.correction"),
            confidence=1.0,
            observed_at=OBSERVED_AT + timedelta(days=1),
            reason="Owner explicitly corrected the preference",
        )

    def test_fresh_database_contains_no_owner_memories(self) -> None:
        self.assertEqual([], self.service.query_memories(active_only=False))

    def test_memory_creation_persists_domain_fields(self) -> None:
        created = self.create_memory()
        persisted = self.service.get_memory(created.memory_id)

        self.assertEqual(MemoryType.PREFERENCE, persisted.memory_type)
        self.assertEqual("owner", persisted.subject)
        self.assertEqual("preferred_drink", persisted.predicate)
        self.assertEqual("tea", persisted.value)
        self.assertEqual(0.95, persisted.confidence)
        self.assertEqual(MemoryStatus.ACTIVE, persisted.status)
        self.assertEqual({"context": "kitchen"}, persisted.metadata)

    def test_database_survives_close_and_reopen(self) -> None:
        created = self.create_memory()
        self.store.close()

        self.store = SQLiteMemoryStore(self.database_path)
        self.service = MemoryService(self.store, clock=self.clock)

        self.assertEqual(created, self.service.get_memory(created.memory_id))

    def test_provenance_survives_persistence(self) -> None:
        provenance = Provenance(
            ProvenanceType.DIRECT_OBSERVATION,
            "camera.front",
            {"frame_id": "frame-42", "quality": 0.8},
        )
        created = self.create_memory(provenance=provenance)

        self.assertEqual(provenance, self.service.get_memory(created.memory_id).provenance)

    def test_confidence_validation_rejects_invalid_values(self) -> None:
        invalid_values = (-0.01, 1.01, float("nan"), float("inf"), "high", True)
        for invalid_value in invalid_values:
            with self.subTest(confidence=invalid_value):
                with self.assertRaises(InvalidConfidenceError):
                    self.create_memory(confidence=invalid_value)

    def test_missing_or_malformed_provenance_is_rejected(self) -> None:
        with self.assertRaises(InvalidProvenanceError):
            self.service.create_memory(
                memory_type=MemoryType.SEMANTIC,
                subject="owner",
                predicate="favorite_color",
                value="blue",
                provenance=None,
                confidence=0.7,
                observed_at=OBSERVED_AT,
            )
        with self.assertRaises(InvalidProvenanceError):
            Provenance(ProvenanceType.SYSTEM_EVENT, "", {})

    def test_retrieval_by_id_and_not_found_error(self) -> None:
        created = self.create_memory()
        self.assertEqual(created, self.service.get_memory(created.memory_id))

        with self.assertRaises(MemoryNotFoundError):
            self.service.get_memory(UUID(int=999))

    def test_retrieval_by_type(self) -> None:
        preference = self.create_memory()
        self.create_memory(
            memory_type=MemoryType.EPISODIC,
            predicate="visited",
            value="workshop",
        )

        self.assertEqual(
            [preference],
            self.service.query_memories(memory_type=MemoryType.PREFERENCE),
        )

    def test_retrieval_by_subject_and_predicate(self) -> None:
        preferred_drink = self.create_memory()
        self.create_memory(subject="workshop", predicate="contains", value="tools")

        self.assertEqual(
            [preferred_drink],
            self.service.query_memories(
                subject="owner",
                predicate="preferred_drink",
            ),
        )

    def test_active_retrieval_excludes_superseded_memory(self) -> None:
        original = self.create_memory()
        replacement = self.correct_memory(original.memory_id)

        self.assertEqual(
            [replacement],
            self.service.query_memories(
                subject="owner",
                predicate="preferred_drink",
            ),
        )
        self.assertEqual(
            [original.memory_id, replacement.memory_id],
            [
                record.memory_id
                for record in self.service.query_memories(
                    subject="owner",
                    predicate="preferred_drink",
                    active_only=False,
                )
            ],
        )

    def test_correction_creates_linked_revision_and_preserves_history(self) -> None:
        original = self.create_memory()
        replacement = self.correct_memory(original.memory_id)
        persisted_original = self.service.get_memory(original.memory_id)

        self.assertNotEqual(original.memory_id, replacement.memory_id)
        self.assertEqual(original.memory_id, replacement.supersedes)
        self.assertEqual(MemoryStatus.SUPERSEDED, persisted_original.status)
        self.assertEqual(
            [original.memory_id, replacement.memory_id],
            [
                record.memory_id
                for record in self.service.get_revision_history(replacement.memory_id)
            ],
        )
        self.assertEqual(
            "Owner explicitly corrected the preference",
            replacement.revision_reason,
        )

    def test_correction_rolls_back_if_replacement_insert_fails(self) -> None:
        target_id = UUID(int=10)
        duplicate_id = UUID(int=20)
        ids = iter((target_id, duplicate_id, duplicate_id))
        service = MemoryService(
            self.store,
            clock=self.clock,
            id_factory=lambda: next(ids),
        )
        target = service.create_memory(
            memory_type=MemoryType.PREFERENCE,
            subject="owner",
            predicate="preferred_drink",
            value="tea",
            provenance=owner_statement(),
            confidence=0.9,
            observed_at=OBSERVED_AT,
        )
        service.create_memory(
            memory_type=MemoryType.SPATIAL,
            subject="workshop",
            predicate="tool_location",
            value="north_wall",
            provenance=owner_statement(),
            confidence=0.9,
            observed_at=OBSERVED_AT,
        )

        with self.assertRaises(PersistenceConflictError):
            service.correct_memory(
                target.memory_id,
                value="coffee",
                provenance=owner_statement("owner.correction"),
                confidence=1.0,
                observed_at=OBSERVED_AT + timedelta(days=1),
                reason="Owner corrected the preference",
            )

        self.assertEqual(MemoryStatus.ACTIVE, service.get_memory(target.memory_id).status)
        self.assertEqual([target], service.get_revision_history(target.memory_id))

    def test_correction_rolls_back_after_late_conflict_failure(self) -> None:
        target = self.create_memory(value="tea")
        competing = self.create_memory(value="coffee", provenance=inference())
        existing_conflict = self.service.list_conflicts()[0]

        with patch(
            "ayyo_memory.sqlite_store.uuid4",
            return_value=existing_conflict.conflict_id,
        ):
            with self.assertRaises(PersistenceConflictError):
                self.correct_memory(target.memory_id, value="water")

        self.assertEqual(MemoryStatus.ACTIVE, self.service.get_memory(target.memory_id).status)
        self.assertEqual([target], self.service.get_revision_history(target.memory_id))
        self.assertEqual(
            {target.memory_id, competing.memory_id},
            {
                record.memory_id
                for record in self.service.query_memories(
                    subject="owner",
                    predicate="preferred_drink",
                )
            },
        )
        persisted_conflict = self.service.list_conflicts()[0]
        self.assertEqual(existing_conflict.conflict_id, persisted_conflict.conflict_id)
        self.assertIsNone(persisted_conflict.resolved_at)

    def test_creation_rolls_back_if_conflict_creation_fails(self) -> None:
        first = self.create_memory(value="tea")
        second = self.create_memory(value="coffee", provenance=inference())
        existing_conflict = self.service.list_conflicts()[0]

        with patch(
            "ayyo_memory.sqlite_store.uuid4",
            return_value=existing_conflict.conflict_id,
        ):
            with self.assertRaises(PersistenceConflictError):
                self.create_memory(value="water")

        self.assertEqual(
            {first.memory_id, second.memory_id},
            {
                record.memory_id
                for record in self.service.query_memories(
                    subject="owner",
                    predicate="preferred_drink",
                )
            },
        )
        self.assertEqual([existing_conflict], self.service.list_conflicts())

    def test_correction_rejects_superseded_and_retracted_targets(self) -> None:
        superseded = self.create_memory(predicate="drink", value="tea")
        self.correct_memory(superseded.memory_id, value="coffee")
        with self.assertRaises(InvalidCorrectionTargetError):
            self.correct_memory(superseded.memory_id, value="water")

        retracted = self.create_memory(predicate="snack", value="fruit")
        self.service.retract_memory(retracted.memory_id, reason="Owner withdrew it")
        with self.assertRaises(AlreadyRetractedError):
            self.correct_memory(retracted.memory_id, value="nuts")

    def test_store_rejects_correction_to_a_different_logical_memory(self) -> None:
        target = self.create_memory()
        created_at = self.clock()
        replacement = MemoryRecord(
            memory_id=UUID(int=101),
            memory_type=target.memory_type,
            subject=target.subject,
            predicate="different_predicate",
            value="coffee",
            provenance=owner_statement("owner.correction"),
            confidence=1.0,
            observed_at=OBSERVED_AT + timedelta(days=1),
            created_at=created_at,
            status=MemoryStatus.ACTIVE,
            status_changed_at=created_at,
            supersedes=target.memory_id,
            revision_reason="Invalid cross-key correction",
        )

        with self.assertRaises(InvalidCorrectionTargetError):
            self.store.correct_memory(target.memory_id, replacement)

        self.assertEqual(MemoryStatus.ACTIVE, self.service.get_memory(target.memory_id).status)
        self.assertEqual([target], self.service.get_revision_history(target.memory_id))

    def test_multi_revision_history_is_root_to_tip_and_single_active(self) -> None:
        original = self.create_memory(value="tea")
        second = self.correct_memory(original.memory_id, value="coffee")
        third = self.correct_memory(second.memory_id, value="water")

        expected = [original.memory_id, second.memory_id, third.memory_id]
        self.assertEqual(
            expected,
            [
                record.memory_id
                for record in self.service.get_revision_history(second.memory_id)
            ],
        )
        self.assertEqual(
            expected,
            [record.memory_id for record in self.service.get_revision_history(third.memory_id)],
        )
        self.assertEqual(
            [third.memory_id],
            [
                record.memory_id
                for record in self.service.query_memories(
                    subject="owner",
                    predicate="preferred_drink",
                )
            ],
        )

    def test_retraction_retains_history_and_removes_active_record(self) -> None:
        created = self.create_memory()
        retracted = self.service.retract_memory(
            created.memory_id,
            reason="Owner withdrew the statement",
        )

        self.assertEqual(MemoryStatus.RETRACTED, retracted.status)
        self.assertEqual("Owner withdrew the statement", retracted.status_reason)
        self.assertEqual([], self.service.query_memories())
        self.assertEqual(
            [created.memory_id],
            [record.memory_id for record in self.service.query_memories(active_only=False)],
        )
        with self.assertRaises(AlreadyRetractedError):
            self.service.retract_memory(created.memory_id, reason="Repeated request")

    def test_unresolved_contradictory_evidence_coexists(self) -> None:
        explicit = self.create_memory(value="tea", provenance=owner_statement())
        inferred = self.create_memory(value="coffee", provenance=inference())

        active_ids = {
            record.memory_id
            for record in self.service.query_memories(
                subject="owner",
                predicate="preferred_drink",
            )
        }
        self.assertEqual({explicit.memory_id, inferred.memory_id}, active_ids)

    def test_conflict_inspection_exposes_both_sides(self) -> None:
        explicit = self.create_memory(value="tea", provenance=owner_statement())
        inferred = self.create_memory(value="coffee", provenance=inference())

        conflicts = self.service.list_conflicts(
            subject="owner",
            predicate="preferred_drink",
        )

        self.assertEqual(1, len(conflicts))
        self.assertEqual(
            {explicit.memory_id, inferred.memory_id},
            {
                conflicts[0].left_memory.memory_id,
                conflicts[0].right_memory.memory_id,
            },
        )
        self.assertIsNone(conflicts[0].resolved_at)

    def test_lower_authority_evidence_cannot_be_used_as_correction(self) -> None:
        explicit = self.create_memory(value="tea", provenance=owner_statement())

        with self.assertRaises(InvalidProvenanceError):
            self.service.correct_memory(
                explicit.memory_id,
                value="coffee",
                provenance=inference(),
                confidence=0.6,
                observed_at=OBSERVED_AT + timedelta(days=1),
                reason="Inferred from observed behavior",
            )

        self.assertEqual(MemoryStatus.ACTIVE, self.service.get_memory(explicit.memory_id).status)

    def test_explicit_correction_resolves_historical_contradiction(self) -> None:
        original = self.create_memory(value="tea")
        replacement = self.correct_memory(original.memory_id, value="coffee")

        self.assertEqual([], self.service.list_conflicts())
        resolved = self.service.list_conflicts(include_resolved=True)
        self.assertEqual(1, len(resolved))
        self.assertEqual(replacement.memory_id, resolved[0].resolution_memory_id)
        self.assertIsNotNone(resolved[0].resolved_at)

    def test_retraction_resolves_related_conflict(self) -> None:
        first = self.create_memory(value="tea")
        self.create_memory(value="coffee", provenance=inference())
        self.service.retract_memory(first.memory_id, reason="Owner withdrew the statement")

        self.assertEqual([], self.service.list_conflicts())
        self.assertEqual(1, len(self.service.list_conflicts(include_resolved=True)))

    def test_retraction_rolls_back_if_conflict_resolution_fails(self) -> None:
        target = self.create_memory(value="tea")
        self.create_memory(value="coffee", provenance=inference())

        with patch.object(
            self.store,
            "_resolve_conflicts",
            side_effect=RuntimeError("forced conflict resolution failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.retract_memory(target.memory_id, reason="Owner withdrew it")

        self.assertEqual(MemoryStatus.ACTIVE, self.service.get_memory(target.memory_id).status)
        self.assertEqual(1, len(self.service.list_conflicts()))

    def test_nested_store_transaction_is_rejected_and_outer_rolls_back(self) -> None:
        with self.assertRaises(MemoryPersistenceError):
            with self.store._transaction():
                with self.store._transaction():
                    self.fail("nested transaction unexpectedly started")

        self.assertFalse(self.store._require_connection().in_transaction)
        self.assertEqual([], self.service.query_memories(active_only=False))

    def test_retraction_resolves_only_conflicts_involving_its_target(self) -> None:
        drink = self.create_memory(predicate="drink", value="tea")
        self.create_memory(predicate="drink", value="coffee", provenance=inference())
        self.create_memory(predicate="color", value="blue")
        self.create_memory(predicate="color", value="red", provenance=inference())

        self.service.retract_memory(drink.memory_id, reason="Owner withdrew it")

        unresolved = self.service.list_conflicts()
        self.assertEqual(1, len(unresolved))
        self.assertEqual("color", unresolved[0].left_memory.predicate)
        self.assertEqual(
            1,
            len(
                self.service.list_conflicts(
                    predicate="drink",
                    include_resolved=True,
                )
            ),
        )

    def test_correction_resolves_only_applicable_conflicts(self) -> None:
        drink = self.create_memory(predicate="drink", value="tea")
        self.create_memory(predicate="drink", value="coffee", provenance=inference())
        self.create_memory(predicate="color", value="blue")
        self.create_memory(predicate="color", value="red", provenance=inference())

        self.correct_memory(drink.memory_id, value="coffee")

        unresolved = self.service.list_conflicts()
        self.assertEqual(1, len(unresolved))
        self.assertEqual("color", unresolved[0].left_memory.predicate)
        resolved_drink_conflicts = self.service.list_conflicts(
            predicate="drink",
            include_resolved=True,
        )
        self.assertEqual(2, len(resolved_drink_conflicts))
        self.assertTrue(all(conflict.resolved_at for conflict in resolved_drink_conflicts))

    def test_conflict_pairs_are_canonical_and_unique(self) -> None:
        ids = iter((UUID(int=20), UUID(int=10)))
        service = MemoryService(
            self.store,
            clock=self.clock,
            id_factory=lambda: next(ids),
        )
        service.create_memory(
            memory_type=MemoryType.PREFERENCE,
            subject="owner",
            predicate="drink",
            value="tea",
            provenance=owner_statement(),
            confidence=0.9,
            observed_at=OBSERVED_AT,
        )
        service.create_memory(
            memory_type=MemoryType.PREFERENCE,
            subject="owner",
            predicate="drink",
            value="coffee",
            provenance=inference(),
            confidence=0.8,
            observed_at=OBSERVED_AT,
        )
        conflict = service.list_conflicts()[0]

        self.assertEqual(UUID(int=10), conflict.left_memory.memory_id)
        self.assertEqual(UUID(int=20), conflict.right_memory.memory_id)

        connection = self.store._require_connection()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO memory_conflicts("
                "conflict_id, left_memory_id, right_memory_id, created_at, reason"
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    str(UUID(int=30)),
                    str(conflict.left_memory.memory_id),
                    str(conflict.right_memory.memory_id),
                    "2026-01-03T00:00:00.000000Z",
                    "duplicate pair",
                ),
            )

    def test_self_conflicts_and_missing_conflict_references_are_rejected(self) -> None:
        memory = self.create_memory()
        with self.assertRaises(InvalidMemoryDataError):
            self.store._insert_conflict(
                memory.memory_id,
                memory.memory_id,
                created_at=self.clock(),
            )

        connection = self.store._require_connection()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO memory_conflicts("
                "conflict_id, left_memory_id, right_memory_id, created_at, reason"
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    str(UUID(int=40)),
                    str(UUID(int=41)),
                    str(UUID(int=42)),
                    "2026-01-03T00:00:00.000000Z",
                    "invalid references",
                ),
            )

    def test_query_order_is_deterministic_for_equal_timestamps(self) -> None:
        fixed_time = datetime(2026, 2, 1, tzinfo=timezone.utc)
        ids = iter((UUID(int=2), UUID(int=1)))
        service = MemoryService(
            self.store,
            clock=lambda: fixed_time,
            id_factory=lambda: next(ids),
        )
        service.create_memory(
            memory_type=MemoryType.SEMANTIC,
            subject="workshop",
            predicate="first_fact",
            value="alpha",
            provenance=owner_statement(),
            confidence=0.8,
            observed_at=OBSERVED_AT,
        )
        service.create_memory(
            memory_type=MemoryType.SEMANTIC,
            subject="workshop",
            predicate="second_fact",
            value="beta",
            provenance=owner_statement(),
            confidence=0.8,
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(
            [UUID(int=1), UUID(int=2)],
            [record.memory_id for record in service.query_memories()],
        )

    def test_schema_version_and_foreign_keys_are_initialized(self) -> None:
        self.assertEqual(CURRENT_SCHEMA_VERSION, self.store.schema_version)
        self.assertTrue(self.store.foreign_keys_enabled)

    def test_required_sqlite_configuration_is_verified_after_reopen(self) -> None:
        def configuration() -> tuple[object, ...]:
            connection = self.store._require_connection()
            return (
                connection.autocommit,
                connection.isolation_level,
                int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower(),
                int(connection.execute("PRAGMA synchronous").fetchone()[0]),
                int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
            )

        expected = (sqlite3.LEGACY_TRANSACTION_CONTROL, None, 1, "wal", 2, 5000)
        self.assertEqual(expected, configuration())
        self.store.close()
        self.store = SQLiteMemoryStore(self.database_path)
        self.service = MemoryService(self.store, clock=self.clock)
        self.assertEqual(expected, configuration())

    def test_wal_journal_mode_is_persistent(self) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual("wal", journal_mode)

    def test_newer_schema_version_is_rejected(self) -> None:
        self.store.close()
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "INSERT INTO schema_versions(version, applied_at) VALUES (?, ?)",
                (CURRENT_SCHEMA_VERSION + 1, "2026-01-01T00:00:00.000000Z"),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(SchemaVersionError):
            SQLiteMemoryStore(self.database_path)

    def test_unversioned_nonempty_database_is_rejected(self) -> None:
        unversioned_path = Path(self.temporary_directory.name) / "unversioned.sqlite3"
        connection = sqlite3.connect(unversioned_path)
        try:
            connection.execute("CREATE TABLE unknown_data(value TEXT NOT NULL)")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(SchemaVersionError):
            SQLiteMemoryStore(unversioned_path)

    def test_partial_current_schema_is_rejected(self) -> None:
        partial_path = Path(self.temporary_directory.name) / "partial.sqlite3"
        connection = sqlite3.connect(partial_path)
        try:
            connection.execute(
                "CREATE TABLE schema_versions ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO schema_versions(version, applied_at) VALUES (?, ?)",
                (CURRENT_SCHEMA_VERSION, "2026-01-01T00:00:00.000000Z"),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(SchemaVersionError):
            SQLiteMemoryStore(partial_path)

    def test_all_required_memory_categories_are_supported(self) -> None:
        for memory_type in MemoryType:
            with self.subTest(memory_type=memory_type):
                self.create_memory(
                    memory_type=memory_type,
                    predicate=f"fact_{memory_type.value}",
                    value=memory_type.value,
                )
        self.assertEqual(len(MemoryType), len(self.service.query_memories()))

    def test_naive_timestamps_and_non_json_values_are_rejected(self) -> None:
        with self.assertRaises(InvalidMemoryDataError):
            self.service.create_memory(
                memory_type=MemoryType.SEMANTIC,
                subject="owner",
                predicate="timezone_test",
                value="invalid",
                provenance=owner_statement(),
                confidence=0.8,
                observed_at=datetime(2026, 1, 1),
            )
        with self.assertRaises(InvalidMemoryDataError):
            self.create_memory(value={"invalid": object()})
        with self.assertRaises(InvalidMemoryDataError):
            self.service.create_memory(
                memory_type=MemoryType.SEMANTIC,
                subject="owner",
                predicate="invalid_metadata",
                value="test",
                provenance=owner_statement(),
                confidence=0.8,
                observed_at=OBSERVED_AT,
                metadata={"invalid": object()},
            )

        cyclic_value: list[object] = []
        cyclic_value.append(cyclic_value)
        with self.assertRaises(InvalidMemoryDataError):
            self.create_memory(value=cyclic_value)

    def test_domain_enums_and_identity_text_are_validated(self) -> None:
        with self.assertRaises(InvalidMemoryDataError):
            self.create_memory(memory_type="preference")
        with self.assertRaises(InvalidProvenanceError):
            Provenance("system_event", "memory.import", {})
        with self.assertRaises(InvalidMemoryDataError):
            self.create_memory(subject=" ")
        with self.assertRaises(InvalidMemoryDataError):
            self.create_memory(predicate=" preferred_drink")
        with self.assertRaises(InvalidMemoryDataError):
            self.service.get_memory("not-a-uuid")

    def test_mutating_caller_inputs_does_not_change_created_memory(self) -> None:
        value = {"choices": ["tea"]}
        metadata = {"context": {"room": "kitchen"}}
        provenance = Provenance(
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            "owner.voice",
            {"evidence": {"ids": ["interaction-001"]}},
        )
        created = self.service.create_memory(
            memory_type=MemoryType.PREFERENCE,
            subject="owner",
            predicate="preferred_drink",
            value=value,
            provenance=provenance,
            confidence=0.95,
            observed_at=OBSERVED_AT,
            metadata=metadata,
        )

        value["choices"].append("coffee")
        metadata["context"]["room"] = "workshop"
        provenance.details["evidence"]["ids"].append("interaction-002")

        expected_value = {"choices": ["tea"]}
        expected_metadata = {"context": {"room": "kitchen"}}
        expected_details = {"evidence": {"ids": ["interaction-001"]}}
        self.assertEqual(expected_value, created.value)
        self.assertEqual(expected_metadata, created.metadata)
        self.assertEqual(expected_details, created.provenance.details)
        persisted = self.service.get_memory(created.memory_id)
        self.assertEqual(expected_value, persisted.value)
        self.assertEqual(expected_metadata, persisted.metadata)
        self.assertEqual(expected_details, persisted.provenance.details)

    def test_closed_store_rejects_operations(self) -> None:
        self.store.close()
        with self.assertRaises(StoreClosedError):
            self.service.query_memories()


if __name__ == "__main__":
    unittest.main()
