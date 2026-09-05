from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from ayyo_memory import MemoryService, MemoryType, ProvenanceType, SQLiteMemoryStore
from ayyo_memory_consolidation import WorkingMemoryCandidateBridge
from ayyo_memory_validation import (
    DecisionType,
    MemoryValidationService,
)

from consolidation_helpers import SYSTEM_TIME_NS, request, retain_robot


class IncrementingClock:
    def __init__(self) -> None:
        self._next = datetime(2026, 1, 2, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        result = self._next
        self._next += timedelta(microseconds=1)
        return result


class IncrementingIds:
    def __init__(self) -> None:
        self._value = 0

    def __call__(self) -> UUID:
        self._value += 1
        return UUID(int=self._value)


class MemoryValidationBridgeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "memory.sqlite3"
        self.store = SQLiteMemoryStore(database_path)
        self.memory_service = MemoryService(
            self.store,
            clock=IncrementingClock(),
            id_factory=IncrementingIds(),
        )
        self.validation = MemoryValidationService(self.memory_service)
        self.working_memory, self.observation = retain_robot()
        self.bridge = WorkingMemoryCandidateBridge(self.working_memory)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def stage(self, *, value=None):
        result = self.bridge.stage(
            request(
                self.observation,
                memory_type=MemoryType.EPISODIC,
                value={"position_rad": 0.25} if value is None else value,
            ),
            now_ns=SYSTEM_TIME_NS,
        )
        assert result.candidate is not None
        return result.candidate

    def test_evaluation_is_read_only_deterministic_and_preserves_provenance(self) -> None:
        candidate = self.stage()
        working_before = self.working_memory.stats(now_ns=SYSTEM_TIME_NS)
        first = self.validation.evaluate(candidate)
        second = self.validation.evaluate(candidate)
        self.assertEqual(first, second)
        self.assertEqual(DecisionType.ACCEPT_NEW, first.decision_type)
        self.assertEqual([], self.memory_service.query_memories(active_only=False))
        self.assertEqual(
            working_before,
            self.working_memory.stats(now_ns=SYSTEM_TIME_NS),
        )
        self.assertEqual(
            ProvenanceType.DIRECT_OBSERVATION,
            first.candidate.provenance.provenance_type,
        )
        self.assertEqual(
            self.observation.observation_id,
            first.candidate.provenance.details["source_observation_id"],
        )

    def test_accept_new_persists_only_after_caller_explicitly_applies(self) -> None:
        decision = self.validation.evaluate(self.stage())
        self.assertEqual([], self.memory_service.query_memories(active_only=False))
        applied = self.validation.apply(decision)
        self.assertTrue(applied.mutation_applied)
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))
        duplicate = self.validation.evaluate(self.stage())
        self.assertEqual(DecisionType.EXACT_DUPLICATE, duplicate.decision_type)
        self.assertFalse(duplicate.persistence_permitted)

    def test_conflict_review_uses_existing_policy_without_bridge_override(self) -> None:
        first = self.validation.evaluate(self.stage(value={"position_rad": 0.25}))
        self.validation.apply(first)
        conflict = self.validation.evaluate(
            self.stage(value={"position_rad": 0.5})
        )
        self.assertEqual(DecisionType.CONFLICT_REVIEW, conflict.decision_type)
        self.assertEqual(1, len(self.memory_service.query_memories(active_only=False)))
        self.assertTrue(conflict.persistence_permitted)
        self.assertIsNone(conflict.candidate.correction_target_id)

    def test_direct_observation_candidate_carries_no_correction_authority(self) -> None:
        candidate = self.stage()
        self.assertIsNone(candidate.correction_target_id)
        self.assertIsNone(candidate.correction_reason)
        self.assertEqual(
            ProvenanceType.DIRECT_OBSERVATION,
            candidate.provenance.provenance_type,
        )


if __name__ == "__main__":
    unittest.main()
