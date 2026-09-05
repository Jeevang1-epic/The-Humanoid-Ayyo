from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import inspect
import unittest
from uuid import UUID

from ayyo_memory import MemoryType, Provenance, ProvenanceType
from ayyo_memory_consolidation import (
    CANDIDATE_SELECTION_POLICY_FINGERPRINT,
    CANDIDATE_SELECTION_POLICY_ID,
    CANDIDATE_SELECTION_POLICY_VERSION,
    MAX_CANDIDATE_SELECTION_COUNT,
    MAX_CANDIDATE_SELECTION_REASONS,
    MIN_REVIEW_CONFIDENCE,
    CandidateReviewItem,
    CandidateSelectionError,
    CandidateSelectionOutcome,
    CandidateSelectionReason,
    ReviewedMemoryCandidateSelectionPolicy,
    WorkingMemoryCandidateBridge,
    candidate_identity,
)
from ayyo_memory_validation import CandidateEvidence
from ayyo_world_model import AYYO_ROBOT_ID, MAX_JSON_TEXT, SemanticEvidenceKind

from consolidation_helpers import (
    SYSTEM_TIME_NS,
    request,
    retain_robot,
    robot_observation,
    semantic_chain,
    semantic_request,
)


OBSERVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def review_candidate(
    *,
    memory_type: MemoryType = MemoryType.EPISODIC,
    subject: str = "owner",
    predicate: str = "stated_value",
    value="tea",
    provenance_type: ProvenanceType = ProvenanceType.EXPLICIT_OWNER_STATEMENT,
    source_id: str = "owner-statement-1",
    details=None,
    confidence: float = 0.9,
    observed_at: datetime = OBSERVED_AT,
    metadata=None,
    correction_target_id: UUID | None = None,
    correction_reason: str | None = None,
) -> CandidateEvidence:
    return CandidateEvidence(
        memory_type=memory_type,
        subject=subject,
        predicate=predicate,
        value=value,
        provenance=Provenance(
            provenance_type=provenance_type,
            source_id=source_id,
            details={} if details is None else details,
        ),
        confidence=confidence,
        observed_at=observed_at,
        metadata={} if metadata is None else metadata,
        correction_target_id=correction_target_id,
        correction_reason=correction_reason,
    )


def staged_review_item(
    *,
    confidence: float = 0.625,
    memory_type: MemoryType = MemoryType.EPISODIC,
    subject: str = AYYO_ROBOT_ID,
    predicate: str = "observed_neck_position",
    value=None,
) -> CandidateReviewItem:
    observation = robot_observation(confidence=confidence)
    store, _ = retain_robot(observation=observation)
    staged = WorkingMemoryCandidateBridge(store).stage(
        request(
            observation,
            memory_type=memory_type,
            subject=subject,
            predicate=predicate,
            value={"position_rad": 0.25} if value is None else value,
        ),
        now_ns=SYSTEM_TIME_NS,
    )
    return CandidateReviewItem.from_staging(staged)


class ReviewedCandidateSelectionPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ReviewedMemoryCandidateSelectionPolicy()

    def test_one_valid_staged_candidate_is_selected_only_for_review(self) -> None:
        item = staged_review_item()

        decision = self.policy.select([item])

        self.assertEqual(
            CandidateSelectionOutcome.SELECT_FOR_REVIEW,
            decision.outcome,
        )
        self.assertEqual(
            (CandidateSelectionReason.ELIGIBLE_FOR_REVIEW,),
            decision.reasons,
        )
        self.assertEqual((item.candidate,), decision.selected_candidates)
        self.assertEqual((candidate_identity(item.candidate),), decision.selected_candidate_ids)

    def test_selection_api_has_no_apply_persist_or_evaluate_operation(self) -> None:
        public_methods = {
            name
            for name, value in inspect.getmembers(
                ReviewedMemoryCandidateSelectionPolicy,
                predicate=inspect.isfunction,
            )
            if not name.startswith("_")
        }
        self.assertEqual({"select"}, public_methods)
        self.assertEqual((), ReviewedMemoryCandidateSelectionPolicy.__slots__)

    def test_identical_inputs_produce_identical_decisions(self) -> None:
        item = staged_review_item()

        first = self.policy.select((item,))
        second = ReviewedMemoryCandidateSelectionPolicy().select([item])

        self.assertEqual(first, second)
        self.assertEqual(first.selection_id, second.selection_id)

    def test_exact_duplicate_candidates_are_collapsed_and_deferred(self) -> None:
        item = staged_review_item()

        decision = self.policy.select([item, item])

        self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
        self.assertEqual(0, decision.selected_count)
        self.assertEqual(1, decision.unique_candidate_count)
        self.assertEqual(2, decision.items[0].occurrence_count)
        self.assertEqual(
            (CandidateSelectionReason.DUPLICATE_CANDIDATE,),
            decision.items[0].reasons,
        )

    def test_duplicate_propositions_from_distinct_evidence_are_all_deferred(self) -> None:
        first = CandidateReviewItem(
            review_candidate(source_id="owner-statement-1")
        )
        second = CandidateReviewItem(
            review_candidate(
                source_id="owner-statement-2",
                observed_at=OBSERVED_AT + timedelta(seconds=1),
            )
        )

        decision = self.policy.select([first, second])

        self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
        self.assertEqual(0, decision.selected_count)
        self.assertEqual(2, decision.deferred_count)
        self.assertTrue(
            all(
                CandidateSelectionReason.DUPLICATE_PROPOSITION in item.reasons
                for item in decision.items
            )
        )

    def test_conflicting_candidates_are_surfaced_without_a_winner(self) -> None:
        tea = CandidateReviewItem(
            review_candidate(
                memory_type=MemoryType.PREFERENCE,
                predicate="preferred_drink",
                value="tea",
                source_id="owner-statement-tea",
            )
        )
        coffee = CandidateReviewItem(
            review_candidate(
                memory_type=MemoryType.PREFERENCE,
                predicate="preferred_drink",
                value="coffee",
                source_id="owner-statement-coffee",
            )
        )

        decision = self.policy.select([tea, coffee])

        self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
        self.assertEqual((), decision.selected_candidates)
        self.assertEqual(2, decision.deferred_count)
        self.assertTrue(
            all(
                CandidateSelectionReason.CONFLICTING_CANDIDATE in item.reasons
                for item in decision.items
            )
        )

    def test_unsupported_procedural_memory_fails_closed(self) -> None:
        item = CandidateReviewItem(
            review_candidate(
                memory_type=MemoryType.PROCEDURAL,
                provenance_type=ProvenanceType.TRUSTED_MANUAL_IMPORT,
            )
        )

        decision = self.policy.select([item])

        self.assertEqual(
            CandidateSelectionOutcome.REJECT_SELECTION,
            decision.outcome,
        )
        self.assertEqual(
            (CandidateSelectionReason.UNSUPPORTED_MEMORY_TYPE,),
            decision.items[0].reasons,
        )

    def test_missing_confidence_is_rejected_and_never_invented(self) -> None:
        candidate = review_candidate()
        object.__setattr__(candidate, "confidence", None)

        decision = self.policy.select([CandidateReviewItem(candidate)])

        self.assertEqual(
            CandidateSelectionOutcome.REJECT_SELECTION,
            decision.outcome,
        )
        self.assertIn(
            CandidateSelectionReason.MISSING_REQUIRED_CONFIDENCE,
            decision.reasons,
        )
        self.assertIsNone(decision.items[0].candidate.confidence)

    def test_zero_confidence_remains_zero_and_is_deferred(self) -> None:
        item = staged_review_item(confidence=0.0)

        decision = self.policy.select([item])

        self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
        self.assertEqual(
            (CandidateSelectionReason.LOW_CONFIDENCE_FOR_POLICY,),
            decision.items[0].reasons,
        )
        self.assertEqual(0.0, decision.items[0].candidate.confidence)

    def test_anonymous_person_remains_anonymous_after_selection(self) -> None:
        store, _, _, semantic, semantic_item = semantic_chain(
            kind=SemanticEvidenceKind.PERSON,
            confidence=0.75,
        )
        staged = WorkingMemoryCandidateBridge(store).stage(
            semantic_request(semantic, semantic_item),
            now_ns=SYSTEM_TIME_NS,
        )

        decision = self.policy.select([CandidateReviewItem.from_staging(staged)])

        self.assertEqual(CandidateSelectionOutcome.SELECT_FOR_REVIEW, decision.outcome)
        value = decision.selected_candidates[0].value
        self.assertEqual({"anonymous", "kind", "region"}, set(value))
        self.assertNotIn("person_id", value)
        self.assertNotIn("owner_id", value)

    def test_anonymous_object_category_never_becomes_object_identity(self) -> None:
        store, _, _, semantic, semantic_item = semantic_chain(
            kind=SemanticEvidenceKind.OBJECT,
            confidence=0.75,
            category="cup",
        )
        staged = WorkingMemoryCandidateBridge(store).stage(
            semantic_request(semantic, semantic_item),
            now_ns=SYSTEM_TIME_NS,
        )

        decision = self.policy.select([CandidateReviewItem.from_staging(staged)])

        value = decision.selected_candidates[0].value
        self.assertEqual("cup", value["category"])
        self.assertTrue(value["anonymous"])
        self.assertNotIn("object_id", value)
        self.assertNotIn("owner", value)

    def test_selection_never_adds_owner_identity_to_direct_evidence(self) -> None:
        item = staged_review_item()

        decision = self.policy.select([item])

        self.assertIs(item.candidate, decision.selected_candidates[0])
        self.assertNotIn("owner", decision.selected_candidates[0].value)
        self.assertEqual(AYYO_ROBOT_ID, decision.selected_candidates[0].subject)

    def test_selection_never_introduces_a_preference_proposition(self) -> None:
        item = staged_review_item()

        decision = self.policy.select([item])

        self.assertEqual((item.candidate,), decision.selected_candidates)
        self.assertTrue(
            all(
                candidate.memory_type is not MemoryType.PREFERENCE
                for candidate in decision.selected_candidates
            )
        )

    def test_selection_never_introduces_a_social_proposition(self) -> None:
        item = staged_review_item()

        decision = self.policy.select([item])

        self.assertEqual(1, decision.input_candidate_count)
        self.assertEqual(1, decision.unique_candidate_count)
        self.assertTrue(
            all(
                candidate.memory_type is not MemoryType.SOCIAL
                for candidate in decision.selected_candidates
            )
        )

    def test_direct_observation_cannot_gain_owner_statement_authority(self) -> None:
        item = staged_review_item()

        decision = self.policy.select([item])

        self.assertEqual(
            ProvenanceType.DIRECT_OBSERVATION,
            decision.selected_candidates[0].provenance.provenance_type,
        )
        self.assertIs(item.candidate, decision.selected_candidates[0])

    def test_policy_identity_version_and_fingerprint_are_deterministic(self) -> None:
        first = ReviewedMemoryCandidateSelectionPolicy()
        second = ReviewedMemoryCandidateSelectionPolicy()

        self.assertEqual(CANDIDATE_SELECTION_POLICY_ID, first.policy_id)
        self.assertEqual(CANDIDATE_SELECTION_POLICY_VERSION, first.policy_version)
        self.assertEqual(
            CANDIDATE_SELECTION_POLICY_FINGERPRINT,
            first.policy_fingerprint,
        )
        self.assertEqual(first.policy_fingerprint, second.policy_fingerprint)
        self.assertTrue(
            first.policy_fingerprint.startswith(
                "candidate-selection-policy-sha256-"
            )
        )

    def test_candidate_order_does_not_change_the_semantic_result(self) -> None:
        first = CandidateReviewItem(
            review_candidate(value="tea", source_id="statement-tea")
        )
        second = CandidateReviewItem(
            review_candidate(value="coffee", source_id="statement-coffee")
        )

        forward = self.policy.select([first, second])
        reversed_order = self.policy.select([second, first])

        self.assertEqual(forward, reversed_order)
        self.assertEqual(forward.selection_id, reversed_order.selection_id)

    def test_observation_time_contributes_to_candidate_identity(self) -> None:
        first = review_candidate(observed_at=OBSERVED_AT)
        second = review_candidate(observed_at=OBSERVED_AT + timedelta(microseconds=1))

        self.assertNotEqual(candidate_identity(first), candidate_identity(second))
        decision = self.policy.select(
            [CandidateReviewItem(first), CandidateReviewItem(second)]
        )
        self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
        self.assertEqual(2, decision.unique_candidate_count)

    def test_duplicate_eligibility_variants_are_order_independent_and_fail_closed(self) -> None:
        staged = staged_review_item()
        without_eligibility = CandidateReviewItem(staged.candidate)

        forward = self.policy.select([staged, without_eligibility])
        reversed_order = self.policy.select([without_eligibility, staged])

        self.assertEqual(forward, reversed_order)
        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, forward.outcome)
        self.assertEqual(
            (
                CandidateSelectionReason.DUPLICATE_CANDIDATE,
                CandidateSelectionReason.SOURCE_ELIGIBILITY_REQUIRED,
            ),
            forward.items[0].reasons,
        )

    def test_candidate_count_overflow_fails_closed_without_materializing_items(self) -> None:
        item = staged_review_item()

        decision = self.policy.select(
            [item] * (MAX_CANDIDATE_SELECTION_COUNT + 1)
        )

        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, decision.outcome)
        self.assertEqual(
            (CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,),
            decision.reasons,
        )
        self.assertEqual(MAX_CANDIDATE_SELECTION_COUNT + 1, decision.input_candidate_count)
        self.assertEqual((), decision.items)

    def test_candidate_content_and_metadata_overflow_fail_closed(self) -> None:
        cases = (
            review_candidate(value="x" * (MAX_JSON_TEXT + 1)),
            review_candidate(metadata={f"field-{index}": index for index in range(17)}),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                decision = self.policy.select([CandidateReviewItem(candidate)])
                self.assertEqual(
                    CandidateSelectionOutcome.REJECT_SELECTION,
                    decision.outcome,
                )
                self.assertIn(
                    CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,
                    decision.reasons,
                )

    def test_aggregate_content_overflow_fails_closed(self) -> None:
        items = [
            CandidateReviewItem(
                review_candidate(
                    value="x" * MAX_JSON_TEXT,
                    source_id=f"owner-statement-{index}",
                )
            )
            for index in range(9)
        ]

        decision = self.policy.select(items)

        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, decision.outcome)
        self.assertEqual(
            (CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,),
            decision.reasons,
        )
        self.assertEqual((), decision.items)

    def test_input_mutation_after_construction_does_not_change_decision(self) -> None:
        value = {"choices": ["tea"]}
        metadata = {"review": ["human"]}
        details = {"channel": ["speech"]}
        candidate = review_candidate(
            value=value,
            metadata=metadata,
            details=details,
        )
        item = CandidateReviewItem(candidate)
        inputs = [item]
        before = self.policy.select(inputs)

        value["choices"].append("coffee")
        metadata["review"].append("changed")
        details["channel"].append("changed")
        inputs.clear()
        after = self.policy.select([item])

        self.assertEqual(before, after)
        self.assertEqual({"choices": ["tea"]}, after.selected_candidates[0].value)
        self.assertEqual({"review": ["human"]}, after.selected_candidates[0].metadata)
        self.assertEqual(
            {"channel": ["speech"]},
            after.selected_candidates[0].provenance.details,
        )

    def test_memory_validation_remains_a_separate_caller_operation(self) -> None:
        decision = self.policy.select([staged_review_item()])

        self.assertFalse(hasattr(decision, "validation_decision"))
        self.assertFalse(hasattr(self.policy, "evaluate"))
        self.assertFalse(hasattr(self.policy, "apply"))
        self.assertIsInstance(decision.selected_candidates[0], CandidateEvidence)

    def test_direct_observation_requires_exact_staging_eligibility(self) -> None:
        staged = staged_review_item()

        decision = self.policy.select([CandidateReviewItem(staged.candidate)])

        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, decision.outcome)
        self.assertEqual(
            (CandidateSelectionReason.SOURCE_ELIGIBILITY_REQUIRED,),
            decision.items[0].reasons,
        )

    def test_staging_result_must_belong_to_the_exact_candidate(self) -> None:
        staged = staged_review_item()
        different = review_candidate()

        with self.assertRaises(CandidateSelectionError):
            CandidateReviewItem(
                candidate=different,
                staging_result=staged.staging_result,
            )

    def test_broader_direct_observation_claim_is_deferred_for_confirmation(self) -> None:
        item = staged_review_item(memory_type=MemoryType.SPATIAL)

        decision = self.policy.select([item])

        self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
        self.assertEqual(
            (
                CandidateSelectionReason.DIRECT_OBSERVATION_REQUIRES_CONFIRMATION,
            ),
            decision.items[0].reasons,
        )

    def test_explicit_owner_preference_can_be_presented_for_review(self) -> None:
        candidate = review_candidate(
            memory_type=MemoryType.PREFERENCE,
            predicate="preferred_drink",
            value="tea",
        )

        decision = self.policy.select([CandidateReviewItem(candidate)])

        self.assertEqual(CandidateSelectionOutcome.SELECT_FOR_REVIEW, decision.outcome)
        self.assertIs(candidate, decision.selected_candidates[0])
        self.assertEqual(
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            decision.selected_candidates[0].provenance.provenance_type,
        )

    def test_derived_preference_and_social_claims_require_owner_confirmation(self) -> None:
        for memory_type in (MemoryType.PREFERENCE, MemoryType.SOCIAL):
            with self.subTest(memory_type=memory_type):
                candidate = review_candidate(
                    memory_type=memory_type,
                    provenance_type=ProvenanceType.DERIVED_INFERENCE,
                )
                decision = self.policy.select([CandidateReviewItem(candidate)])
                self.assertEqual(CandidateSelectionOutcome.DEFER, decision.outcome)
                self.assertEqual(
                    (CandidateSelectionReason.OWNER_CONFIRMATION_REQUIRED,),
                    decision.items[0].reasons,
                )
                self.assertIs(candidate, decision.items[0].candidate)

    def test_review_threshold_is_exact_and_documented_as_a_constant(self) -> None:
        at_threshold = review_candidate(confidence=MIN_REVIEW_CONFIDENCE)
        below_threshold = review_candidate(
            confidence=MIN_REVIEW_CONFIDENCE - 0.001,
            source_id="owner-statement-below-threshold",
        )

        self.assertEqual(
            CandidateSelectionOutcome.SELECT_FOR_REVIEW,
            self.policy.select([CandidateReviewItem(at_threshold)]).outcome,
        )
        below = self.policy.select([CandidateReviewItem(below_threshold)])
        self.assertEqual(CandidateSelectionOutcome.DEFER, below.outcome)
        self.assertEqual(
            (CandidateSelectionReason.LOW_CONFIDENCE_FOR_POLICY,),
            below.reasons,
        )

    def test_correction_candidate_is_rejected_without_apply(self) -> None:
        candidate = review_candidate(
            correction_target_id=UUID(int=1),
            correction_reason="owner requested correction",
        )

        decision = self.policy.select([CandidateReviewItem(candidate)])

        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, decision.outcome)
        self.assertEqual(
            (CandidateSelectionReason.CORRECTION_NOT_ALLOWED,),
            decision.reasons,
        )

    def test_empty_input_is_a_typed_bounded_rejection(self) -> None:
        decision = self.policy.select([])

        self.assertEqual(CandidateSelectionOutcome.REJECT_SELECTION, decision.outcome)
        self.assertEqual(
            (CandidateSelectionReason.INSUFFICIENT_EVIDENCE,),
            decision.reasons,
        )
        self.assertEqual(0, decision.input_candidate_count)

    def test_decisions_are_immutable_and_reasons_are_bounded(self) -> None:
        decision = self.policy.select([staged_review_item()])

        with self.assertRaises(FrozenInstanceError):
            decision.outcome = CandidateSelectionOutcome.DEFER
        self.assertLessEqual(len(decision.reasons), MAX_CANDIDATE_SELECTION_REASONS)
        self.assertLessEqual(
            len(decision.items[0].reasons),
            MAX_CANDIDATE_SELECTION_REASONS,
        )


if __name__ == "__main__":
    unittest.main()
