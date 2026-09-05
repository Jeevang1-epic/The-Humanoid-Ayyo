"""Immutable contracts for deterministic candidate selection for review."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_memory_validation import CandidateEvidence
from ayyo_world_model import MAX_JSON_CHARACTERS

from .errors import CandidateSelectionError
from .models import (
    CandidateStagingReason,
    CandidateStagingResult,
    CandidateStagingStatus,
)


CANDIDATE_SELECTION_POLICY_ID = "ayyo.reviewed-memory-candidate-selection.v1"
CANDIDATE_SELECTION_POLICY_VERSION = 1
MIN_REVIEW_CONFIDENCE = 0.5
MAX_CANDIDATE_SELECTION_COUNT = 32
MAX_CANDIDATE_SELECTION_REASONS = 16
MAX_CANDIDATE_SELECTION_AGGREGATE_CHARACTERS = MAX_JSON_CHARACTERS


class CandidateSelectionOutcome(StrEnum):
    SELECT_FOR_REVIEW = "select_for_review"
    DEFER = "defer"
    REJECT_SELECTION = "reject_selection"


class CandidateSelectionReason(StrEnum):
    ELIGIBLE_FOR_REVIEW = "eligible_for_review"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    DUPLICATE_PROPOSITION = "duplicate_proposition"
    CONFLICTING_CANDIDATE = "conflicting_candidate"
    UNSUPPORTED_MEMORY_TYPE = "unsupported_memory_type"
    SOURCE_ELIGIBILITY_REQUIRED = "source_eligibility_required"
    LOW_CONFIDENCE_FOR_POLICY = "low_confidence_for_policy"
    DIRECT_OBSERVATION_REQUIRES_CONFIRMATION = (
        "direct_observation_requires_confirmation"
    )
    OWNER_CONFIRMATION_REQUIRED = "owner_confirmation_required"
    PROVENANCE_REQUIRES_CONFIRMATION = "provenance_requires_confirmation"
    PROVENANCE_NOT_ALLOWED_FOR_MEMORY_TYPE = (
        "provenance_not_allowed_for_memory_type"
    )
    UNSUPPORTED_PROVENANCE = "unsupported_provenance"
    MISSING_REQUIRED_CONFIDENCE = "missing_required_confidence"
    SEMANTIC_CLAIM_EXCEEDS_EVIDENCE = "semantic_claim_exceeds_evidence"
    CORRECTION_NOT_ALLOWED = "correction_not_allowed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"


_REASON_ORDER = {
    reason: index for index, reason in enumerate(CandidateSelectionReason)
}

_DEFER_REASONS = frozenset(
    {
        CandidateSelectionReason.DUPLICATE_CANDIDATE,
        CandidateSelectionReason.DUPLICATE_PROPOSITION,
        CandidateSelectionReason.CONFLICTING_CANDIDATE,
        CandidateSelectionReason.LOW_CONFIDENCE_FOR_POLICY,
        CandidateSelectionReason.DIRECT_OBSERVATION_REQUIRES_CONFIRMATION,
        CandidateSelectionReason.OWNER_CONFIRMATION_REQUIRED,
        CandidateSelectionReason.PROVENANCE_REQUIRES_CONFIRMATION,
    }
)
_REJECT_REASONS = frozenset(
    {
        CandidateSelectionReason.UNSUPPORTED_MEMORY_TYPE,
        CandidateSelectionReason.SOURCE_ELIGIBILITY_REQUIRED,
        CandidateSelectionReason.PROVENANCE_NOT_ALLOWED_FOR_MEMORY_TYPE,
        CandidateSelectionReason.UNSUPPORTED_PROVENANCE,
        CandidateSelectionReason.MISSING_REQUIRED_CONFIDENCE,
        CandidateSelectionReason.SEMANTIC_CLAIM_EXCEEDS_EVIDENCE,
        CandidateSelectionReason.CORRECTION_NOT_ALLOWED,
        CandidateSelectionReason.INSUFFICIENT_EVIDENCE,
        CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,
    }
)


def ordered_selection_reasons(
    reasons,
) -> tuple[CandidateSelectionReason, ...]:
    """Return unique reasons in stable policy-defined order."""
    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


@dataclass(frozen=True, slots=True)
class CandidateReviewItem:
    """One immutable candidate and its optional exact staging eligibility."""

    candidate: CandidateEvidence
    staging_result: CandidateStagingResult | None = None

    def __post_init__(self) -> None:
        if type(self.candidate) is not CandidateEvidence:
            raise CandidateSelectionError(
                "review item requires an immutable CandidateEvidence"
            )
        if self.staging_result is not None:
            if type(self.staging_result) is not CandidateStagingResult:
                raise CandidateSelectionError("staging_result must be typed")
            if (
                self.staging_result.status is not CandidateStagingStatus.ELIGIBLE
                or self.staging_result.reason is not CandidateStagingReason.ELIGIBLE
                or self.staging_result.candidate != self.candidate
            ):
                raise CandidateSelectionError(
                    "review item staging result must be eligible for the exact candidate"
                )

    @classmethod
    def from_staging(
        cls,
        staging_result: CandidateStagingResult,
    ) -> CandidateReviewItem:
        if (
            type(staging_result) is not CandidateStagingResult
            or staging_result.candidate is None
        ):
            raise CandidateSelectionError(
                "eligible staging result with a candidate is required"
            )
        return cls(
            candidate=staging_result.candidate,
            staging_result=staging_result,
        )


@dataclass(frozen=True, slots=True)
class CandidateSelectionItemDecision:
    """Review-selection outcome for one unique candidate identity."""

    candidate_id: str
    candidate: CandidateEvidence
    outcome: CandidateSelectionOutcome
    reasons: tuple[CandidateSelectionReason, ...]
    occurrence_count: int

    def __post_init__(self) -> None:
        if (
            type(self.candidate_id) is not str
            or not self.candidate_id.startswith("memory-candidate-sha256-")
            or len(self.candidate_id) != len("memory-candidate-sha256-") + 64
            or any(
                character not in "0123456789abcdef"
                for character in self.candidate_id[-64:]
            )
        ):
            raise CandidateSelectionError("candidate identity is malformed")
        if type(self.candidate) is not CandidateEvidence:
            raise CandidateSelectionError("item decision lost its candidate")
        if not isinstance(self.outcome, CandidateSelectionOutcome):
            raise CandidateSelectionError("item outcome must be typed")
        if (
            type(self.reasons) is not tuple
            or not self.reasons
            or len(self.reasons) > MAX_CANDIDATE_SELECTION_REASONS
            or any(
                not isinstance(reason, CandidateSelectionReason)
                for reason in self.reasons
            )
            or self.reasons != ordered_selection_reasons(self.reasons)
        ):
            raise CandidateSelectionError(
                "item reasons must be non-empty, bounded, unique, and ordered"
            )
        if (
            type(self.occurrence_count) is not int
            or not 1
            <= self.occurrence_count
            <= MAX_CANDIDATE_SELECTION_COUNT
        ):
            raise CandidateSelectionError("candidate occurrence count is invalid")
        if self.outcome is CandidateSelectionOutcome.SELECT_FOR_REVIEW:
            if self.reasons != (CandidateSelectionReason.ELIGIBLE_FOR_REVIEW,):
                raise CandidateSelectionError(
                    "selected candidate must have only the eligible reason"
                )
        elif CandidateSelectionReason.ELIGIBLE_FOR_REVIEW in self.reasons:
            raise CandidateSelectionError(
                "non-selected candidate cannot claim review eligibility"
            )
        elif (
            self.outcome is CandidateSelectionOutcome.DEFER
            and not set(self.reasons) <= _DEFER_REASONS
        ):
            raise CandidateSelectionError("deferred candidate has an invalid reason")
        elif (
            self.outcome is CandidateSelectionOutcome.REJECT_SELECTION
            and not set(self.reasons) & _REJECT_REASONS
        ):
            raise CandidateSelectionError(
                "rejected candidate requires a rejection reason"
            )


@dataclass(frozen=True, slots=True)
class CandidateSelectionDecision:
    """Canonical bounded result of one explicit review-selection invocation."""

    policy_id: str
    policy_version: int
    policy_fingerprint: str
    selection_id: str
    outcome: CandidateSelectionOutcome
    reasons: tuple[CandidateSelectionReason, ...]
    items: tuple[CandidateSelectionItemDecision, ...]
    input_candidate_count: int

    def __post_init__(self) -> None:
        if self.policy_id != CANDIDATE_SELECTION_POLICY_ID:
            raise CandidateSelectionError("selection policy identity is invalid")
        if self.policy_version != CANDIDATE_SELECTION_POLICY_VERSION:
            raise CandidateSelectionError("selection policy version is invalid")
        for value, prefix, field_name in (
            (
                self.policy_fingerprint,
                "candidate-selection-policy-sha256-",
                "policy fingerprint",
            ),
            (self.selection_id, "candidate-selection-sha256-", "selection identity"),
        ):
            if (
                type(value) is not str
                or not value.startswith(prefix)
                or len(value) != len(prefix) + 64
                or any(
                    character not in "0123456789abcdef"
                    for character in value[-64:]
                )
            ):
                raise CandidateSelectionError(f"{field_name} is malformed")
        if not isinstance(self.outcome, CandidateSelectionOutcome):
            raise CandidateSelectionError("selection outcome must be typed")
        if (
            type(self.reasons) is not tuple
            or not self.reasons
            or len(self.reasons) > MAX_CANDIDATE_SELECTION_REASONS
            or any(
                not isinstance(reason, CandidateSelectionReason)
                for reason in self.reasons
            )
            or self.reasons != ordered_selection_reasons(self.reasons)
        ):
            raise CandidateSelectionError(
                "selection reasons must be non-empty, bounded, unique, and ordered"
            )
        if (
            type(self.items) is not tuple
            or len(self.items) > MAX_CANDIDATE_SELECTION_COUNT
            or any(type(item) is not CandidateSelectionItemDecision for item in self.items)
            or self.items
            != tuple(sorted(self.items, key=lambda item: item.candidate_id))
            or len({item.candidate_id for item in self.items}) != len(self.items)
        ):
            raise CandidateSelectionError(
                "selection items must be bounded, unique, and canonically ordered"
            )
        if type(self.input_candidate_count) is not int or self.input_candidate_count < 0:
            raise CandidateSelectionError("input candidate count is invalid")
        if self.items:
            if self.input_candidate_count != sum(
                item.occurrence_count for item in self.items
            ):
                raise CandidateSelectionError(
                    "input count does not match candidate occurrences"
                )
        else:
            if self.outcome is not CandidateSelectionOutcome.REJECT_SELECTION:
                raise CandidateSelectionError("empty selection must fail closed")
            if self.input_candidate_count == 0:
                expected_empty_reasons = (
                    CandidateSelectionReason.INSUFFICIENT_EVIDENCE,
                )
            else:
                expected_empty_reasons = (
                    CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,
                )
            if self.reasons != expected_empty_reasons:
                raise CandidateSelectionError("empty selection lost its reason")

        if self.items:
            expected_outcome = max(
                (item.outcome for item in self.items),
                key=lambda value: {
                    CandidateSelectionOutcome.SELECT_FOR_REVIEW: 0,
                    CandidateSelectionOutcome.DEFER: 1,
                    CandidateSelectionOutcome.REJECT_SELECTION: 2,
                }[value],
            )
            if self.outcome is not expected_outcome:
                raise CandidateSelectionError(
                    "selection outcome does not summarize its items"
                )
            expected_reasons = ordered_selection_reasons(
                reason
                for item in self.items
                for reason in item.reasons
                if (
                    self.outcome is CandidateSelectionOutcome.SELECT_FOR_REVIEW
                    or reason is not CandidateSelectionReason.ELIGIBLE_FOR_REVIEW
                )
            )
            if self.reasons != expected_reasons:
                raise CandidateSelectionError(
                    "selection reasons do not summarize its items"
                )

    @property
    def selected_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            item.candidate_id
            for item in self.items
            if item.outcome is CandidateSelectionOutcome.SELECT_FOR_REVIEW
        )

    @property
    def selected_candidates(self) -> tuple[CandidateEvidence, ...]:
        return tuple(
            item.candidate
            for item in self.items
            if item.outcome is CandidateSelectionOutcome.SELECT_FOR_REVIEW
        )

    @property
    def selected_count(self) -> int:
        return len(self.selected_candidate_ids)

    @property
    def unique_candidate_count(self) -> int:
        return len(self.items)

    @property
    def deferred_count(self) -> int:
        return sum(
            item.outcome is CandidateSelectionOutcome.DEFER
            for item in self.items
        )

    @property
    def rejected_count(self) -> int:
        return sum(
            item.outcome is CandidateSelectionOutcome.REJECT_SELECTION
            for item in self.items
        )
