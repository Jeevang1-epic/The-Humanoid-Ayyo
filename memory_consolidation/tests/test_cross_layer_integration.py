from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from ayyo_memory import MemoryService, MemoryType, ProvenanceType, SQLiteMemoryStore
from ayyo_memory_consolidation import (
    CandidateReviewItem,
    CandidateSelectionOutcome,
    ReviewedMemoryCandidateSelectionPolicy,
    WorkingMemoryCandidateBridge,
)
from ayyo_memory_validation import DecisionType, MemoryValidationService
from ayyo_perception import (
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_working_memory import IngestionStatus, WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import AYYO_ROBOT_ID, ObservationClock

from consolidation_helpers import (
    JOINT_SENSOR,
    SYSTEM_PROVENANCE,
    SYSTEM_TIME_NS,
    catalog,
    request,
    robot_observation,
)


class CrossLayerCandidateSeamTest(unittest.TestCase):
    def test_reviewed_observation_reaches_validation_without_automatic_memory(self) -> None:
        trust = PerceptionTrustBoundary(
            PerceptionTrustConfig(
                robot_id=AYYO_ROBOT_ID,
                source_clock=ObservationClock.ROS_SYSTEM_TIME,
                sources=(
                    PerceptionSourceContract(JOINT_SENSOR, SYSTEM_PROVENANCE),
                ),
                freshness_ns=1_000_000_000,
                retention_ttl_ns=2_000_000_000,
            )
        )
        observation = robot_observation()
        admitted = trust.admit(
            observation,
            now_ns=SYSTEM_TIME_NS,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(AdmissionStatus.ACCEPTED, admitted.status)

        working_memory = WorkingMemory(
            catalog(),
            WorkingMemoryConfig(
                robot_id=AYYO_ROBOT_ID,
                source_clock=ObservationClock.ROS_SYSTEM_TIME,
                allowed_provenance=(SYSTEM_PROVENANCE,),
                freshness_ns=1_000_000_000,
                retention_ttl_ns=2_000_000_000,
            ),
        )
        retained = working_memory.ingest(
            observation,
            now_ns=SYSTEM_TIME_NS,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(IngestionStatus.ACCEPTED, retained.status)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "memory.sqlite3")
            try:
                memory_service = MemoryService(
                    store,
                    clock=lambda: datetime(2026, 1, 2, tzinfo=timezone.utc),
                    id_factory=lambda: UUID(int=1),
                )
                validation = MemoryValidationService(memory_service)
                bridge = WorkingMemoryCandidateBridge(working_memory)
                self.assertEqual(
                    [],
                    memory_service.query_memories(active_only=False),
                )
                self.assertFalse(hasattr(bridge, "candidate"))

                staged = bridge.stage(
                    request(observation, memory_type=MemoryType.EPISODIC),
                    now_ns=SYSTEM_TIME_NS,
                )
                assert staged.candidate is not None
                candidate = staged.candidate
                self.assertEqual(
                    ProvenanceType.DIRECT_OBSERVATION,
                    candidate.provenance.provenance_type,
                )
                self.assertEqual(
                    observation.observation_id,
                    candidate.provenance.details["source_observation_id"],
                )
                self.assertNotIn("person_id", candidate.value)
                self.assertNotIn("object_id", candidate.value)
                self.assertEqual(
                    [],
                    memory_service.query_memories(active_only=False),
                )

                selector = ReviewedMemoryCandidateSelectionPolicy()
                selection = selector.select(
                    [CandidateReviewItem.from_staging(staged)]
                )
                self.assertEqual(
                    CandidateSelectionOutcome.SELECT_FOR_REVIEW,
                    selection.outcome,
                )
                self.assertEqual((candidate,), selection.selected_candidates)
                self.assertFalse(hasattr(selector, "apply"))
                self.assertEqual(
                    [],
                    memory_service.query_memories(active_only=False),
                )

                validation_decision = validation.evaluate(
                    selection.selected_candidates[0]
                )
                self.assertEqual(
                    DecisionType.ACCEPT_NEW,
                    validation_decision.decision_type,
                )
                self.assertEqual(
                    [],
                    memory_service.query_memories(active_only=False),
                )
                validation.apply(validation_decision)
                self.assertEqual(
                    1,
                    len(memory_service.query_memories(active_only=False)),
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
