from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
import inspect
import unittest

from ayyo_memory import MemoryType, ProvenanceType
from ayyo_memory_consolidation import (
    MAX_CONSOLIDATION_METADATA_FIELDS,
    CandidateStagingReason,
    CandidateStagingStatus,
    ConsolidationRequest,
    ConsolidationRequestError,
    EvidenceReference,
    WorkingMemoryCandidateBridge,
)
from ayyo_memory_validation import CandidateEvidence
from ayyo_world_model import AYYO_ROBOT_ID, ObservationClock

from consolidation_helpers import (
    OTHER_SYSTEM_PROVENANCE,
    SIMULATION_PROVENANCE,
    SYSTEM_PROVENANCE,
    SYSTEM_TIME_NS,
    TEST_PROVENANCE,
    reference,
    request,
    retain_robot,
    robot_observation,
    working_memory,
)


class CandidateBridgeContractTest(unittest.TestCase):
    def test_valid_fresh_evidence_stages_exact_immutable_candidate(self) -> None:
        store, observation = retain_robot()
        value = {"position_rad": 0.25, "samples": [1, 2]}
        metadata = {"review_note": ["bounded", "manual"]}
        references = [reference(observation)]
        staging_request = request(
            observation,
            memory_type=MemoryType.SPATIAL,
            subject=AYYO_ROBOT_ID,
            predicate="observed_neck_position",
            value=value,
            supporting_evidence=references,
            metadata=metadata,
        )
        value["position_rad"] = 0.9
        metadata["review_note"].append("changed")
        references.clear()

        result = WorkingMemoryCandidateBridge(store).stage(
            staging_request,
            now_ns=SYSTEM_TIME_NS,
        )

        self.assertEqual(CandidateStagingStatus.ELIGIBLE, result.status)
        self.assertEqual(CandidateStagingReason.ELIGIBLE, result.reason)
        self.assertIsInstance(result.candidate, CandidateEvidence)
        candidate = result.candidate
        assert candidate is not None
        self.assertEqual(MemoryType.SPATIAL, candidate.memory_type)
        self.assertEqual(AYYO_ROBOT_ID, candidate.subject)
        self.assertEqual("observed_neck_position", candidate.predicate)
        self.assertEqual(
            {"position_rad": 0.25, "samples": [1, 2]},
            candidate.value,
        )
        self.assertEqual(
            {"review_note": ["bounded", "manual"]},
            candidate.metadata,
        )
        candidate.value["samples"].append(3)
        candidate.metadata["review_note"].append("mutated")
        self.assertEqual([1, 2], candidate.value["samples"])
        self.assertEqual(
            ["bounded", "manual"],
            candidate.metadata["review_note"],
        )
        with self.assertRaises(FrozenInstanceError):
            result.status = CandidateStagingStatus.INELIGIBLE

    def test_provenance_confidence_and_original_utc_time_are_derived_exactly(self) -> None:
        store, observation = retain_robot()
        candidate = WorkingMemoryCandidateBridge(store).stage(
            request(observation),
            now_ns=SYSTEM_TIME_NS,
        ).candidate
        assert candidate is not None
        self.assertEqual(0.625, candidate.confidence)
        self.assertEqual(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            candidate.observed_at,
        )
        self.assertEqual(
            ProvenanceType.DIRECT_OBSERVATION,
            candidate.provenance.provenance_type,
        )
        self.assertEqual(observation.observation_id, candidate.provenance.source_id)
        details = candidate.provenance.details
        self.assertEqual(observation.observation_id, details["source_observation_id"])
        self.assertEqual(
            str(observation.fingerprint),
            details["source_observation_fingerprint"],
        )
        self.assertEqual(SYSTEM_PROVENANCE.document(), details["source_provenance"])

    def test_zero_confidence_remains_a_genuine_zero(self) -> None:
        observation = robot_observation(confidence=0.0)
        store, _ = retain_robot(observation=observation)
        candidate = WorkingMemoryCandidateBridge(store).stage(
            request(observation),
            now_ns=SYSTEM_TIME_NS,
        ).candidate
        assert candidate is not None
        self.assertEqual(0.0, candidate.confidence)

    def test_unknown_expired_and_reset_epoch_evidence_all_fail_closed(self) -> None:
        store, observation = retain_robot()
        bridge = WorkingMemoryCandidateBridge(store)
        unknown = EvidenceReference(
            observation_id="world-observation-" + "0" * 64,
            observation_fingerprint=str(observation.fingerprint),
            source_id=SYSTEM_PROVENANCE.source_id,
        )
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_NOT_FOUND,
            bridge.stage(
                request(observation, supporting_evidence=[unknown]),
                now_ns=SYSTEM_TIME_NS,
            ).reason,
        )
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_NOT_FOUND,
            bridge.stage(
                request(observation),
                now_ns=SYSTEM_TIME_NS + 2_000_000_001,
            ).reason,
        )
        reset_store, reset_observation = retain_robot()
        reset_store.reset()
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_NOT_FOUND,
            WorkingMemoryCandidateBridge(reset_store).stage(
                request(reset_observation),
                now_ns=0,
            ).reason,
        )

    def test_stale_retained_evidence_is_ineligible_under_fresh_only_policy(self) -> None:
        store, observation = retain_robot(
            store=working_memory(freshness_ns=10, ttl_ns=100),
        )
        result = WorkingMemoryCandidateBridge(store).stage(
            request(observation),
            now_ns=SYSTEM_TIME_NS + 11,
        )
        self.assertEqual(CandidateStagingReason.EVIDENCE_STALE, result.reason)
        self.assertIsNone(result.candidate)

    def test_wrong_robot_fingerprint_and_provenance_source_fail(self) -> None:
        store, observation = retain_robot()
        bridge = WorkingMemoryCandidateBridge(store)
        wrong_robot = ConsolidationRequest(
            robot_id="other.robot.v1",
            memory_type=MemoryType.EPISODIC,
            subject=AYYO_ROBOT_ID,
            predicate="observed_neck_position",
            value={"position_rad": 0.25},
            supporting_evidence=[reference(observation)],
        )
        tampered_fingerprint = EvidenceReference(
            observation_id=observation.observation_id,
            observation_fingerprint="robot_state:sha256:" + "0" * 64,
            source_id=SYSTEM_PROVENANCE.source_id,
        )
        wrong_source = reference(
            observation,
            source_id=OTHER_SYSTEM_PROVENANCE.source_id,
        )
        self.assertEqual(
            CandidateStagingReason.ROBOT_MISMATCH,
            bridge.stage(wrong_robot, now_ns=SYSTEM_TIME_NS).reason,
        )
        self.assertEqual(
            CandidateStagingReason.SOURCE_MISMATCH,
            bridge.stage(
                request(observation, supporting_evidence=[tampered_fingerprint]),
                now_ns=SYSTEM_TIME_NS,
            ).reason,
        )
        self.assertEqual(
            CandidateStagingReason.SOURCE_MISMATCH,
            bridge.stage(
                request(observation, supporting_evidence=[wrong_source]),
                now_ns=SYSTEM_TIME_NS,
            ).reason,
        )

    def test_tampered_retained_content_fails_identity_validation(self) -> None:
        store, observation = retain_robot()
        object.__setattr__(store._recent[0].observation, "confidence", 0.9)
        result = WorkingMemoryCandidateBridge(store).stage(
            request(observation),
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(CandidateStagingReason.SOURCE_MISMATCH, result.reason)
        self.assertIsNone(result.candidate)

    def test_simulation_test_and_other_non_epoch_clocks_are_never_relabeled_utc(self) -> None:
        cases = (
            (SIMULATION_PROVENANCE, ObservationClock.ROS_SIMULATION_TIME),
            (TEST_PROVENANCE, ObservationClock.TEST_TIME),
        )
        for provenance, clock in cases:
            with self.subTest(clock=clock):
                observation = robot_observation(
                    observed_at_ns=100_000,
                    provenance=provenance,
                )
                store = working_memory(provenance=provenance, clock=clock)
                retain_robot(observation=observation, store=store, now_ns=100_000)
                result = WorkingMemoryCandidateBridge(store).stage(
                    request(observation),
                    now_ns=100_000,
                )
                self.assertEqual(CandidateStagingReason.UNSUPPORTED_CLOCK, result.reason)
                self.assertIsNone(result.candidate)

    def test_inexact_nanoseconds_and_future_time_fail_closed(self) -> None:
        inexact = robot_observation(observed_at_ns=SYSTEM_TIME_NS + 1)
        inexact_store, _ = retain_robot(
            observation=inexact,
            now_ns=SYSTEM_TIME_NS + 1,
        )
        future = robot_observation(observed_at_ns=SYSTEM_TIME_NS + 1_000)
        future_store, _ = retain_robot(
            observation=future,
            now_ns=SYSTEM_TIME_NS,
        )
        self.assertEqual(
            CandidateStagingReason.TIMESTAMP_NOT_UTC_CONVERTIBLE,
            WorkingMemoryCandidateBridge(inexact_store).stage(
                request(inexact),
                now_ns=SYSTEM_TIME_NS + 1,
            ).reason,
        )
        self.assertEqual(
            CandidateStagingReason.EVIDENCE_TIME_IN_FUTURE,
            WorkingMemoryCandidateBridge(future_store).stage(
                request(future),
                now_ns=SYSTEM_TIME_NS,
            ).reason,
        )

    def test_observations_cannot_stage_preference_social_or_procedural_memory(self) -> None:
        store, observation = retain_robot()
        bridge = WorkingMemoryCandidateBridge(store)
        for memory_type in (
            MemoryType.PREFERENCE,
            MemoryType.SOCIAL,
            MemoryType.PROCEDURAL,
        ):
            with self.subTest(memory_type=memory_type):
                result = bridge.stage(
                    request(observation, memory_type=memory_type),
                    now_ns=SYSTEM_TIME_NS,
                )
                self.assertEqual(
                    CandidateStagingReason.MEMORY_TYPE_NOT_ALLOWED,
                    result.reason,
                )

    def test_correction_and_persistence_are_impossible_through_public_bridge_api(self) -> None:
        request_parameters = inspect.signature(ConsolidationRequest).parameters
        bridge_methods = {
            name for name, _ in inspect.getmembers(WorkingMemoryCandidateBridge)
        }
        self.assertNotIn("correction_target_id", request_parameters)
        self.assertNotIn("correction_reason", request_parameters)
        self.assertNotIn("apply", bridge_methods)
        self.assertNotIn("persist", bridge_methods)
        self.assertNotIn("evaluate", bridge_methods)
        store, observation = retain_robot()
        candidate = WorkingMemoryCandidateBridge(store).stage(
            request(observation),
            now_ns=SYSTEM_TIME_NS,
        ).candidate
        assert candidate is not None
        self.assertIsNone(candidate.correction_target_id)
        self.assertIsNone(candidate.correction_reason)

    def test_request_resource_bounds_and_result_shape_are_enforced(self) -> None:
        _, observation = retain_robot()
        with self.assertRaises(ConsolidationRequestError):
            request(
                observation,
                metadata={
                    f"field-{index}": index
                    for index in range(MAX_CONSOLIDATION_METADATA_FIELDS + 1)
                },
            )
        with self.assertRaises(ConsolidationRequestError):
            request(
                observation,
                supporting_evidence=[reference(observation), reference(observation)],
            )
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(ConsolidationRequestError):
            request(observation, value=cycle)

    def test_public_request_has_no_authority_or_time_inputs(self) -> None:
        names = {field.name for field in fields(ConsolidationRequest)}
        self.assertFalse(
            names
            & {
                "confidence",
                "observed_at",
                "provenance",
                "provenance_type",
                "correction_target_id",
                "correction_reason",
            }
        )


if __name__ == "__main__":
    unittest.main()
