from __future__ import annotations

import unittest

from ayyo_memory import MemoryType
from ayyo_memory_consolidation import (
    CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
    CANDIDATE_DISCOVERY_POLICY_ID,
    CANDIDATE_DISCOVERY_POLICY_VERSION,
    MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS,
    MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS,
    MAX_CANDIDATE_DISCOVERY_EVIDENCE,
    MAX_CANDIDATE_DISCOVERY_PROPOSALS,
    BoundedMemoryCandidateDiscoveryPolicy,
    CandidateDiscoveryOutcome,
    CandidateDiscoveryReason,
    ConsolidationRequest,
    WorkingMemoryCandidateBridge,
)
from ayyo_memory_validation import CandidateEvidence, canonicalize_json
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    MAX_JSON_CHARACTERS,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SemanticEvidenceKind,
    SemanticEvidenceObservation,
)

from consolidation_helpers import (
    SYSTEM_PROVENANCE,
    SYSTEM_TIME_NS,
    VISUAL_PROVENANCE,
    robot_observation,
    semantic_batch_chain,
    semantic_chain,
    working_memory,
)


TEST_VISUAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.visual.memory-candidate.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-frame.v1",
)
OTHER_VISUAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    "ayyo.camera.head.rgb.other.v1",
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    "sensor_msgs.msg.image",
)


class CandidateDiscoveryPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = BoundedMemoryCandidateDiscoveryPolicy()

    def discover_semantic(
        self,
        *,
        kind: SemanticEvidenceKind = SemanticEvidenceKind.PERSON,
        confidence: float | None = 0.75,
        category: str = "cup",
    ):
        chain = semantic_chain(
            kind=kind,
            confidence=confidence,
            category=category,
        )
        return chain, self.policy.discover(chain[0], now_ns=SYSTEM_TIME_NS)

    def test_fresh_anonymous_person_produces_one_exact_request(self) -> None:
        (_, _, _, _, item), result = self.discover_semantic()
        self.assertEqual(CandidateDiscoveryOutcome.PROPOSALS_DISCOVERED, result.outcome)
        self.assertEqual(1, result.proposal_count)
        request = result.proposals[0].request
        self.assertEqual(MemoryType.EPISODIC, request.memory_type)
        self.assertEqual(AYYO_ROBOT_ID, request.subject)
        self.assertEqual("observed_anonymous_person", request.predicate)
        self.assertEqual(
            {
                "anonymous": True,
                "kind": "person",
                "region": item.region.document(),
            },
            request.value,
        )

    def test_fresh_anonymous_object_produces_one_exact_request(self) -> None:
        (_, _, _, _, item), result = self.discover_semantic(
            kind=SemanticEvidenceKind.OBJECT,
            category="water-bottle",
        )
        self.assertEqual(1, result.proposal_count)
        self.assertEqual("observed_anonymous_object", result.requests[0].predicate)
        self.assertEqual(item.category, result.requests[0].value["category"])

    def test_object_category_is_present_only_for_object_evidence(self) -> None:
        _, person = self.discover_semantic(kind=SemanticEvidenceKind.PERSON)
        _, object_result = self.discover_semantic(kind=SemanticEvidenceKind.OBJECT)
        self.assertNotIn("category", person.requests[0].value)
        self.assertEqual("cup", object_result.requests[0].value["category"])

    def test_normalized_region_is_preserved_exactly(self) -> None:
        (_, _, _, _, item), result = self.discover_semantic()
        self.assertEqual(
            item.region.document(),
            result.requests[0].value["region"],
        )

    def test_evidence_reference_and_fingerprint_are_exact(self) -> None:
        (_, _, _, semantic, item), result = self.discover_semantic()
        reference = result.requests[0].supporting_evidence[0]
        self.assertEqual(semantic.observation_id, reference.observation_id)
        self.assertEqual(str(semantic.fingerprint), reference.observation_fingerprint)
        self.assertEqual(semantic.provenance.source_id, reference.source_id)
        self.assertEqual(item.source_semantic_observation_id, reference.semantic_item_id)

    def test_proposal_identity_is_deterministic(self) -> None:
        chain, first = self.discover_semantic()
        second = self.policy.discover(chain[0], now_ns=SYSTEM_TIME_NS)
        self.assertEqual(first.proposals[0].proposal_id, second.proposals[0].proposal_id)

    def test_proposal_identity_changes_with_material_meaning(self) -> None:
        _, person = self.discover_semantic(kind=SemanticEvidenceKind.PERSON)
        _, object_result = self.discover_semantic(kind=SemanticEvidenceKind.OBJECT)
        self.assertNotEqual(
            person.proposals[0].proposal_id,
            object_result.proposals[0].proposal_id,
        )

    def test_output_order_is_canonical_not_storage_order(self) -> None:
        first_store, *_ = semantic_batch_chain(item_count=4)
        first = self.policy.discover(first_store, now_ns=SYSTEM_TIME_NS)
        first_store._recent.reverse()
        second = self.policy.discover(first_store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(sorted(item.proposal_id for item in first.proposals)),
            tuple(item.proposal_id for item in first.proposals),
        )

    def test_repeated_discovery_on_unchanged_state_is_identical(self) -> None:
        chain, first = self.discover_semantic()
        second = self.policy.discover(chain[0], now_ns=SYSTEM_TIME_NS)
        self.assertEqual(first, second)
        self.assertEqual(first.discovery_id, second.discovery_id)

    def test_mutating_returned_json_cannot_change_proposal_meaning(self) -> None:
        _, result = self.discover_semantic()
        request = result.requests[0]
        original = request.value
        caller_copy = request.value
        caller_copy["anonymous"] = False
        caller_copy["region"]["x_min"] = 0.4
        metadata_copy = request.metadata
        metadata_copy["owner"] = "invented"
        self.assertEqual(original, request.value)
        self.assertEqual({}, request.metadata)

    def test_missing_confidence_is_never_synthesized(self) -> None:
        _, result = self.discover_semantic(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=None,
        )
        self.assertEqual(0, result.proposal_count)
        self.assertIn(
            CandidateDiscoveryReason.MISSING_REQUIRED_CONFIDENCE,
            result.reasons,
        )

    def test_real_zero_confidence_remains_stageable_zero(self) -> None:
        (store, *_), result = self.discover_semantic(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.0,
        )
        staged = WorkingMemoryCandidateBridge(store).stage(
            result.requests[0],
            now_ns=SYSTEM_TIME_NS,
        )
        assert staged.candidate is not None
        self.assertEqual(0.0, staged.candidate.confidence)

    def test_unsupported_clock_produces_no_false_utc_proposal(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            provenance=TEST_VISUAL_PROVENANCE,
            clock=ObservationClock.TEST_TIME,
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE, result.outcome)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.UNSUPPORTED_CLOCK, result.reasons)

    def test_stale_evidence_matches_staging_ineligibility(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            freshness_ns=100,
            ttl_ns=1_000,
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 101)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.EVIDENCE_STALE, result.reasons)

    def test_expired_evidence_is_absent(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            freshness_ns=100,
            ttl_ns=1_000,
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 1_001)
        self.assertEqual(0, result.retained_evidence_count)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.NO_RETAINED_EVIDENCE, result.reasons)

    def test_reset_evidence_is_not_rediscovered(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        store.reset()
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.NO_RETAINED_EVIDENCE, result.reasons)

    def test_wrong_robot_evidence_cannot_become_a_proposal(self) -> None:
        other, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            robot_id="other.robot.v1",
        )
        store = working_memory(provenance=VISUAL_PROVENANCE, visual=True)
        store._recent = list(other.recent_evidence(now_ns=SYSTEM_TIME_NS))
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.WRONG_ROBOT, result.reasons)

    def test_corrupt_source_fingerprint_fails_closed(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
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
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE, result.outcome)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(
            CandidateDiscoveryReason.INVALID_RETAINED_EVIDENCE,
            result.reasons,
        )

    def test_duplicate_retained_identity_fails_closed_without_duplication(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        store._recent.append(store._recent[-1])
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(
            CandidateDiscoveryReason.INVALID_RETAINED_EVIDENCE,
            result.reasons,
        )

    def test_evidence_scan_bound_fails_closed_deterministically(self) -> None:
        store = working_memory(recent_evidence_capacity=65)
        for index in range(65):
            observed_at_ns = SYSTEM_TIME_NS + index * 1_000
            accepted = store.ingest(
                robot_observation(observed_at_ns=observed_at_ns),
                now_ns=observed_at_ns,
                received_at_monotonic_ns=index + 1,
            )
            self.assertEqual("accepted", accepted.status.value)
        first = self.policy.discover(
            store,
            now_ns=SYSTEM_TIME_NS + 64_000,
        )
        second = self.policy.discover(
            store,
            now_ns=SYSTEM_TIME_NS + 64_000,
        )
        self.assertEqual(first, second)
        self.assertEqual(65, first.retained_evidence_count)
        self.assertEqual(0, first.inspected_evidence_count)
        self.assertEqual(CandidateDiscoveryOutcome.RESOURCE_LIMIT_REACHED, first.outcome)

    def test_proposal_count_bound_is_enforced_deterministically(self) -> None:
        first, *_ = semantic_batch_chain(item_count=17)
        second, *_ = semantic_batch_chain(
            item_count=17,
            observed_at_ns=SYSTEM_TIME_NS + 1_000,
        )
        store = working_memory(
            provenance=VISUAL_PROVENANCE,
            visual=True,
            recent_evidence_capacity=64,
        )
        store._recent = list(first.recent_evidence(now_ns=SYSTEM_TIME_NS)) + list(
            second.recent_evidence(now_ns=SYSTEM_TIME_NS + 1_000)
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 1_000)
        self.assertEqual(MAX_CANDIDATE_DISCOVERY_PROPOSALS, result.proposal_count)
        self.assertEqual(CandidateDiscoveryOutcome.RESOURCE_LIMIT_REACHED, result.outcome)
        self.assertEqual(
            tuple(sorted(item.proposal_id for item in result.proposals)),
            tuple(item.proposal_id for item in result.proposals),
        )

    def test_diagnostic_count_bound_is_enforced(self) -> None:
        first, *_ = semantic_batch_chain(item_count=32, confidence=None)
        second, *_ = semantic_batch_chain(
            item_count=32,
            confidence=None,
            observed_at_ns=SYSTEM_TIME_NS + 1_000,
        )
        store = working_memory(
            provenance=VISUAL_PROVENANCE,
            visual=True,
            recent_evidence_capacity=64,
        )
        store._recent = list(first.recent_evidence(now_ns=SYSTEM_TIME_NS)) + list(
            second.recent_evidence(now_ns=SYSTEM_TIME_NS + 1_000)
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 1_000)
        self.assertLessEqual(
            len(result.diagnostics),
            MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS,
        )
        self.assertIn(CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED, result.reasons)

    def test_unsupported_observation_family_is_explicit(self) -> None:
        store = working_memory()
        observation = robot_observation()
        store.ingest(observation, now_ns=SYSTEM_TIME_NS, received_at_monotonic_ns=1)
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(
            CandidateDiscoveryReason.UNSUPPORTED_EVIDENCE_KIND,
            result.reasons,
        )

    def test_discovery_does_not_mutate_working_memory_content_or_counters(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        evidence_before = store.recent_evidence(now_ns=SYSTEM_TIME_NS)
        stats_before = store.stats(now_ns=SYSTEM_TIME_NS)
        self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(evidence_before, store.recent_evidence(now_ns=SYSTEM_TIME_NS))
        self.assertEqual(stats_before, store.stats(now_ns=SYSTEM_TIME_NS))

    def test_discovery_does_not_refresh_retention_ttl(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            freshness_ns=100,
            ttl_ns=1_000,
        )
        first = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 50)
        self.assertEqual(1, first.proposal_count)
        expired = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 1_001)
        self.assertEqual(0, expired.proposal_count)
        self.assertEqual(0, expired.retained_evidence_count)

    def test_discovery_does_not_construct_candidate_evidence(self) -> None:
        _, result = self.discover_semantic()
        self.assertIsInstance(result.requests[0], ConsolidationRequest)
        self.assertNotIsInstance(result.requests[0], CandidateEvidence)
        self.assertFalse(hasattr(result.proposals[0], "candidate"))

    def test_unavailable_source_chain_is_skipped_explicitly(self) -> None:
        store, frame, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        store._recent = [
            envelope
            for envelope in store._recent
            if envelope.observation.observation_id != frame.observation_id
        ]
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.INVALID_SOURCE_CHAIN, result.reasons)

    def test_non_allowlisted_provenance_is_skipped(self) -> None:
        other, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            provenance=OTHER_VISUAL_PROVENANCE,
        )
        store = working_memory(provenance=VISUAL_PROVENANCE, visual=True)
        store._recent = list(other.recent_evidence(now_ns=SYSTEM_TIME_NS))
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.PROVENANCE_NOT_ALLOWED, result.reasons)

    def test_future_dated_evidence_is_skipped(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            observed_at_ns=SYSTEM_TIME_NS + 1_000,
            ingest_now_ns=SYSTEM_TIME_NS,
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(CandidateDiscoveryReason.EVIDENCE_TIME_IN_FUTURE, result.reasons)

    def test_non_microsecond_timestamp_is_not_proposed(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
            observed_at_ns=SYSTEM_TIME_NS + 1,
        )
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 1)
        self.assertEqual(0, result.proposal_count)
        self.assertIn(
            CandidateDiscoveryReason.TIMESTAMP_NOT_UTC_CONVERTIBLE,
            result.reasons,
        )

    def test_invalid_discovery_time_has_typed_ineligible_result(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        result = self.policy.discover(store, now_ns=-1)
        self.assertEqual(CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE, result.outcome)
        self.assertIn(CandidateDiscoveryReason.INVALID_DISCOVERY_TIME, result.reasons)

    def test_source_clock_regression_has_typed_ineligible_result(self) -> None:
        store, *_ = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        self.policy.discover(store, now_ns=SYSTEM_TIME_NS + 1)
        result = self.policy.discover(store, now_ns=SYSTEM_TIME_NS)
        self.assertEqual(CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE, result.outcome)
        self.assertIn(CandidateDiscoveryReason.SOURCE_CLOCK_REGRESSION, result.reasons)

    def test_policy_identity_and_public_bounds_are_explicit(self) -> None:
        self.assertEqual("ayyo.memory-candidate-discovery.v1", self.policy.policy_id)
        self.assertEqual(CANDIDATE_DISCOVERY_POLICY_ID, self.policy.policy_id)
        self.assertEqual(CANDIDATE_DISCOVERY_POLICY_VERSION, self.policy.policy_version)
        self.assertEqual(CANDIDATE_DISCOVERY_POLICY_FINGERPRINT, self.policy.policy_fingerprint)
        self.assertEqual(64, MAX_CANDIDATE_DISCOVERY_EVIDENCE)
        self.assertEqual(32, MAX_CANDIDATE_DISCOVERY_PROPOSALS)
        self.assertEqual(
            MAX_JSON_CHARACTERS,
            MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS,
        )
        self.assertLess(
            len(canonicalize_json(result_document(self.discover_semantic()[1]))),
            MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS,
        )
        self.assertFalse(hasattr(self.policy, "__dict__"))


def result_document(result) -> dict[str, object]:
    return {
        "diagnostics": [
            {
                "evidence_id": item.evidence_id,
                "reason": item.reason.value,
                "semantic_item_id": item.semantic_item_id,
            }
            for item in result.diagnostics
        ],
        "policy_fingerprint": result.policy_fingerprint,
        "proposals": [
            {
                "proposal_id": item.proposal_id,
                "request_value": item.request.value,
            }
            for item in result.proposals
        ],
    }


if __name__ == "__main__":
    unittest.main()
