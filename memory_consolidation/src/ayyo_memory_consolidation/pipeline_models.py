"""Immutable contracts for controlled memory-candidate review orchestration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from ayyo_memory_validation import (
    CandidateEvidence,
    DecisionType,
    ValidationDecision,
    canonicalize_json,
)
from ayyo_world_model import MAX_JSON_CHARACTERS, MAX_OBSERVATION_TIME_NS

from .discovery_models import (
    MAX_CANDIDATE_DISCOVERY_PROPOSALS,
    CandidateDiscoveryResult,
    candidate_discovery_proposal_identity,
)
from .discovery_policy import CANDIDATE_DISCOVERY_POLICY_FINGERPRINT
from .errors import ControlledMemoryReviewError
from .models import (
    CandidateStagingStatus,
    CandidateStagingResult,
    ConsolidationRequest,
)
from .selection_models import (
    MAX_CANDIDATE_SELECTION_COUNT,
    MAX_CANDIDATE_SELECTION_REASONS,
    CandidateSelectionDecision,
    CandidateSelectionItemDecision,
    CandidateSelectionOutcome,
    CandidateSelectionReason,
)
from .selection_policy import (
    CANDIDATE_SELECTION_POLICY_FINGERPRINT,
    candidate_identity,
)


CONTROLLED_MEMORY_REVIEW_PIPELINE_ID = (
    "ayyo.controlled-memory-review-pipeline.v1"
)
CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION = 1
MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS = min(
    MAX_CANDIDATE_DISCOVERY_PROPOSALS,
    MAX_CANDIDATE_SELECTION_COUNT,
)
MAX_MEMORY_REVIEW_ENTRIES = MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS
MAX_MEMORY_REVIEW_EVALUATIONS = MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS
MAX_MEMORY_REVIEW_REASONS = MAX_CANDIDATE_SELECTION_REASONS
MAX_MEMORY_REVIEW_AGGREGATE_CHARACTERS = MAX_JSON_CHARACTERS

_PIPELINE_POLICY_DOCUMENT = {
    "authority": "read_only_validation_evaluation",
    "bounds": {
        "aggregate_characters": MAX_MEMORY_REVIEW_AGGREGATE_CHARACTERS,
        "entry_count": MAX_MEMORY_REVIEW_ENTRIES,
        "evaluation_count": MAX_MEMORY_REVIEW_EVALUATIONS,
        "reason_count": MAX_MEMORY_REVIEW_REASONS,
        "requested_proposal_count": MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS,
    },
    "caller_gate": "exact_prepared_plan_and_explicit_proposal_id_allowlist",
    "discovery_policy_fingerprint": CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
    "duplicate_requested_proposal_behavior": "reject_entire_invocation",
    "evaluation_behavior": "selected_candidates_only_sequential_read_only",
    "partial_failure_behavior": "per_entry_staging_ineligibility",
    "pipeline_id": CONTROLLED_MEMORY_REVIEW_PIPELINE_ID,
    "pipeline_version": CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION,
    "selection_behavior": "one_complete_successfully_staged_batch",
    "selection_policy_fingerprint": CANDIDATE_SELECTION_POLICY_FINGERPRINT,
    "stale_plan_behavior": "authoritative_restaging_without_retry_or_rediscovery",
}
CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT = (
    "controlled-memory-review-pipeline-sha256-"
    + sha256(canonicalize_json(_PIPELINE_POLICY_DOCUMENT).encode("utf-8")).hexdigest()
)


class MemoryCandidateEvaluator(Protocol):
    """Narrow read-only authority used by the review pipeline."""

    def evaluate(self, candidate: CandidateEvidence) -> ValidationDecision: ...


class MemoryCandidateReviewOutcome(StrEnum):
    """Overall disposition of one explicit execute-review invocation."""

    REVIEW_COMPLETED = "review_completed"
    REVIEW_COMPLETED_WITH_INELIGIBLE_ENTRIES = (
        "review_completed_with_ineligible_entries"
    )
    NOTHING_REQUESTED = "nothing_requested"
    PLAN_INVALID = "plan_invalid"
    PLAN_STALE = "plan_stale"
    RESOURCE_LIMIT_REACHED = "resource_limit_reached"


class MemoryCandidateReviewReason(StrEnum):
    """Stable bounded reasons for a controlled review result."""

    REVIEW_COMPLETED = "review_completed"
    STAGING_INELIGIBLE = "staging_ineligible"
    NOTHING_REQUESTED = "nothing_requested"
    PLAN_INTEGRITY_FAILED = "plan_integrity_failed"
    REQUEST_INTEGRITY_FAILED = "request_integrity_failed"
    UNKNOWN_PROPOSAL_ID = "unknown_proposal_id"
    DUPLICATE_PROPOSAL_ID = "duplicate_proposal_id"
    PLAN_STALE = "plan_stale"
    RESOURCE_LIMIT_REACHED = "resource_limit_reached"


_REASON_ORDER = {
    reason: index for index, reason in enumerate(MemoryCandidateReviewReason)
}


def ordered_memory_review_reasons(
    reasons,
) -> tuple[MemoryCandidateReviewReason, ...]:
    """Return unique review reasons in stable policy-defined order."""

    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


@dataclass(frozen=True, slots=True)
class MemoryCandidateReviewPlan:
    """One immutable, verifiable snapshot of an exact discovery result."""

    pipeline_id: str
    pipeline_version: int
    pipeline_fingerprint: str
    plan_id: str
    prepared_at_ns: int
    discovery_result: CandidateDiscoveryResult

    def __post_init__(self) -> None:
        _validate_pipeline_identity(
            self.pipeline_id,
            self.pipeline_version,
            self.pipeline_fingerprint,
        )
        _validate_digest_identity(
            self.plan_id,
            "memory-candidate-review-plan-sha256-",
            "review plan identity",
        )
        if (
            type(self.prepared_at_ns) is not int
            or not 0 <= self.prepared_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            raise ControlledMemoryReviewError(
                "review plan time must be non-negative source-clock nanoseconds"
            )
        if type(self.discovery_result) is not CandidateDiscoveryResult:
            raise ControlledMemoryReviewError(
                "review plan requires an exact CandidateDiscoveryResult"
            )
        expected_id = memory_candidate_review_plan_identity(
            pipeline_fingerprint=self.pipeline_fingerprint,
            prepared_at_ns=self.prepared_at_ns,
            discovery_result=self.discovery_result,
        )
        if self.plan_id != expected_id:
            raise ControlledMemoryReviewError(
                "review plan identity does not match its discovery snapshot"
            )

    @property
    def discovery_result_id(self) -> str:
        return self.discovery_result.discovery_id

    @property
    def discovery_policy_id(self) -> str:
        return self.discovery_result.policy_id

    @property
    def discovery_policy_version(self) -> int:
        return self.discovery_result.policy_version

    @property
    def discovery_policy_fingerprint(self) -> str:
        return self.discovery_result.policy_fingerprint

    @property
    def proposal_ids(self) -> tuple[str, ...]:
        return tuple(item.proposal_id for item in self.discovery_result.proposals)

    @property
    def proposal_count(self) -> int:
        return self.discovery_result.proposal_count

    @property
    def diagnostic_count(self) -> int:
        return len(self.discovery_result.diagnostics)


@dataclass(frozen=True, slots=True, init=False)
class MemoryCandidateReviewRequest:
    """An explicit caller allowlist bound to one exact prepared plan."""

    plan: MemoryCandidateReviewPlan
    selected_proposal_ids: tuple[str, ...]
    request_id: str

    def __init__(
        self,
        *,
        plan: MemoryCandidateReviewPlan,
        selected_proposal_ids: Sequence[str],
    ) -> None:
        if type(plan) is not MemoryCandidateReviewPlan:
            raise ControlledMemoryReviewError(
                "review request requires an exact MemoryCandidateReviewPlan"
            )
        if not isinstance(selected_proposal_ids, (list, tuple)):
            raise ControlledMemoryReviewError(
                "selected proposal identities must be a bounded list or tuple"
            )
        if len(selected_proposal_ids) > MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS:
            raise ControlledMemoryReviewError(
                "selected proposal identity count exceeds its bound"
            )
        proposal_ids = tuple(selected_proposal_ids)
        for proposal_id in proposal_ids:
            _validate_digest_identity(
                proposal_id,
                "memory-candidate-discovery-proposal-sha256-",
                "selected proposal identity",
            )
        canonical_ids = tuple(sorted(proposal_ids))
        request_id = memory_candidate_review_request_identity(
            plan_id=plan.plan_id,
            selected_proposal_ids=canonical_ids,
        )
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "selected_proposal_ids", canonical_ids)
        object.__setattr__(self, "request_id", request_id)


@dataclass(frozen=True, slots=True)
class MemoryCandidateReviewEntry:
    """Full immutable lineage for one explicitly requested proposal."""

    entry_id: str
    plan_id: str
    discovery_result_id: str
    proposal_id: str
    request: ConsolidationRequest
    staging_result: CandidateStagingResult
    selection_item: CandidateSelectionItemDecision | None
    validation_decision: ValidationDecision | None
    evaluated: bool

    def __post_init__(self) -> None:
        _validate_digest_identity(
            self.entry_id,
            "memory-candidate-review-entry-sha256-",
            "review entry identity",
        )
        _validate_digest_identity(
            self.plan_id,
            "memory-candidate-review-plan-sha256-",
            "review plan identity",
        )
        _validate_digest_identity(
            self.discovery_result_id,
            "memory-candidate-discovery-sha256-",
            "discovery result identity",
        )
        _validate_digest_identity(
            self.proposal_id,
            "memory-candidate-discovery-proposal-sha256-",
            "proposal identity",
        )
        if type(self.request) is not ConsolidationRequest:
            raise ControlledMemoryReviewError(
                "review entry requires its exact ConsolidationRequest"
            )
        if self.proposal_id != candidate_discovery_proposal_identity(
            self.request,
            policy_fingerprint=CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
        ):
            raise ControlledMemoryReviewError(
                "review entry proposal identity does not match its request"
            )
        if type(self.staging_result) is not CandidateStagingResult:
            raise ControlledMemoryReviewError(
                "review entry requires an exact CandidateStagingResult"
            )
        if type(self.evaluated) is not bool:
            raise ControlledMemoryReviewError("evaluated status must be boolean")

        if self.staging_result.status is CandidateStagingStatus.ELIGIBLE:
            if type(self.selection_item) is not CandidateSelectionItemDecision:
                raise ControlledMemoryReviewError(
                    "staged entry requires its exact selection item"
                )
            candidate = self.staging_result.candidate
            assert candidate is not None
            if (
                self.selection_item.candidate != candidate
                or self.selection_item.candidate_id != candidate_identity(candidate)
            ):
                raise ControlledMemoryReviewError(
                    "selection item does not match the staged candidate"
                )
            selected = (
                self.selection_item.outcome
                is CandidateSelectionOutcome.SELECT_FOR_REVIEW
            )
            if self.evaluated is not selected:
                raise ControlledMemoryReviewError(
                    "evaluated status must exactly follow review selection"
                )
            if selected:
                if (
                    type(self.validation_decision) is not ValidationDecision
                    or self.validation_decision.candidate != candidate
                ):
                    raise ControlledMemoryReviewError(
                        "evaluated entry requires a decision for its exact candidate"
                    )
            elif self.validation_decision is not None:
                raise ControlledMemoryReviewError(
                    "deferred or rejected entry cannot contain validation"
                )
        elif (
            self.selection_item is not None
            or self.validation_decision is not None
            or self.evaluated
        ):
            raise ControlledMemoryReviewError(
                "ineligible staging entry cannot claim selection or evaluation"
            )

        expected_id = memory_candidate_review_entry_identity(
            plan_id=self.plan_id,
            discovery_result_id=self.discovery_result_id,
            proposal_id=self.proposal_id,
            staging_result=self.staging_result,
            selection_item=self.selection_item,
            validation_decision=self.validation_decision,
            evaluated=self.evaluated,
        )
        if self.entry_id != expected_id:
            raise ControlledMemoryReviewError(
                "review entry identity does not match its exact lineage"
            )

    @property
    def candidate_id(self) -> str | None:
        if self.selection_item is None:
            return None
        return self.selection_item.candidate_id

    @property
    def selection_outcome(self) -> CandidateSelectionOutcome | None:
        if self.selection_item is None:
            return None
        return self.selection_item.outcome

    @property
    def selection_reasons(self) -> tuple[CandidateSelectionReason, ...]:
        if self.selection_item is None:
            return ()
        return self.selection_item.reasons


@dataclass(frozen=True, slots=True)
class MemoryCandidateReviewBatch:
    """Canonical bounded result of one explicit controlled review invocation."""

    pipeline_id: str
    pipeline_version: int
    pipeline_fingerprint: str
    batch_id: str
    outcome: MemoryCandidateReviewOutcome
    reasons: tuple[MemoryCandidateReviewReason, ...]
    plan_id: str | None
    discovery_result_id: str | None
    request_id: str | None
    entries: tuple[MemoryCandidateReviewEntry, ...]
    selection_decision: CandidateSelectionDecision | None
    discovery_count: int
    requested_count: int
    staged_count: int
    staging_failed_count: int
    selected_count: int
    deferred_count: int
    rejected_count: int
    evaluated_count: int
    validation_decision_counts: tuple[tuple[DecisionType, int], ...] = field(
        default=()
    )

    def __post_init__(self) -> None:
        _validate_pipeline_identity(
            self.pipeline_id,
            self.pipeline_version,
            self.pipeline_fingerprint,
        )
        _validate_digest_identity(
            self.batch_id,
            "memory-candidate-review-batch-sha256-",
            "review batch identity",
        )
        if not isinstance(self.outcome, MemoryCandidateReviewOutcome):
            raise ControlledMemoryReviewError("review batch outcome must be typed")
        if (
            type(self.reasons) is not tuple
            or not self.reasons
            or len(self.reasons) > MAX_MEMORY_REVIEW_REASONS
            or any(
                not isinstance(reason, MemoryCandidateReviewReason)
                for reason in self.reasons
            )
            or self.reasons != ordered_memory_review_reasons(self.reasons)
        ):
            raise ControlledMemoryReviewError(
                "review batch reasons must be bounded, unique, and ordered"
            )
        _validate_optional_digest_identity(
            self.plan_id,
            "memory-candidate-review-plan-sha256-",
            "review plan identity",
        )
        _validate_optional_digest_identity(
            self.discovery_result_id,
            "memory-candidate-discovery-sha256-",
            "discovery result identity",
        )
        _validate_optional_digest_identity(
            self.request_id,
            "memory-candidate-review-request-sha256-",
            "review request identity",
        )
        if (
            type(self.entries) is not tuple
            or len(self.entries) > MAX_MEMORY_REVIEW_ENTRIES
            or any(
                type(item) is not MemoryCandidateReviewEntry for item in self.entries
            )
            or self.entries
            != tuple(sorted(self.entries, key=lambda item: item.proposal_id))
            or len({item.proposal_id for item in self.entries}) != len(self.entries)
        ):
            raise ControlledMemoryReviewError(
                "review entries must be bounded, unique, and canonically ordered"
            )
        if any(
            entry.plan_id != self.plan_id
            or entry.discovery_result_id != self.discovery_result_id
            for entry in self.entries
        ):
            raise ControlledMemoryReviewError(
                "review entries do not retain the batch source lineage"
            )
        if self.selection_decision is not None and type(
            self.selection_decision
        ) is not CandidateSelectionDecision:
            raise ControlledMemoryReviewError(
                "selection decision must retain the exact typed result"
            )
        if self.selection_decision is not None:
            selection_by_id = {
                item.candidate_id: item for item in self.selection_decision.items
            }
            for entry in self.entries:
                if entry.selection_item is not None and (
                    selection_by_id.get(entry.selection_item.candidate_id)
                    != entry.selection_item
                ):
                    raise ControlledMemoryReviewError(
                        "review entry selection is absent from the batch decision"
                    )

        expected_counts = _review_batch_counts(
            entries=self.entries,
            selection_decision=self.selection_decision,
        )
        supplied_counts = (
            self.staged_count,
            self.staging_failed_count,
            self.selected_count,
            self.deferred_count,
            self.rejected_count,
            self.evaluated_count,
        )
        if supplied_counts != expected_counts:
            raise ControlledMemoryReviewError(
                "review batch counts do not match its exact entries"
            )
        if (
            self.selection_decision is not None
            and self.selection_decision.input_candidate_count != self.staged_count
        ):
            raise ControlledMemoryReviewError(
                "batch selection input count must match successful staging"
            )
        if (
            type(self.discovery_count) is not int
            or not 0 <= self.discovery_count <= MAX_CANDIDATE_DISCOVERY_PROPOSALS
            or type(self.requested_count) is not int
            or not 0 <= self.requested_count <= MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS
        ):
            raise ControlledMemoryReviewError("review batch source counts are invalid")
        if self.entries and len(self.entries) != self.requested_count:
            raise ControlledMemoryReviewError(
                "review entries must cover every structurally valid request"
            )
        expected_validation_counts = _validation_counts(self.entries)
        if self.validation_decision_counts != expected_validation_counts:
            raise ControlledMemoryReviewError(
                "validation decision counts do not match evaluated entries"
            )
        self._validate_outcome_shape()
        expected_id = memory_candidate_review_batch_identity(
            pipeline_fingerprint=self.pipeline_fingerprint,
            outcome=self.outcome,
            reasons=self.reasons,
            plan_id=self.plan_id,
            discovery_result_id=self.discovery_result_id,
            request_id=self.request_id,
            entries=self.entries,
            selection_decision=self.selection_decision,
            discovery_count=self.discovery_count,
            requested_count=self.requested_count,
            counts=supplied_counts,
            validation_decision_counts=self.validation_decision_counts,
        )
        if self.batch_id != expected_id:
            raise ControlledMemoryReviewError(
                "review batch identity does not match its canonical result"
            )

    def _validate_outcome_shape(self) -> None:
        if self.outcome is MemoryCandidateReviewOutcome.NOTHING_REQUESTED:
            if (
                self.reasons != (MemoryCandidateReviewReason.NOTHING_REQUESTED,)
                or self.requested_count != 0
                or self.entries
                or self.selection_decision is not None
            ):
                raise ControlledMemoryReviewError(
                    "nothing-requested outcome has inconsistent content"
                )
            return
        if self.outcome in {
            MemoryCandidateReviewOutcome.PLAN_INVALID,
            MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
        }:
            if self.entries or self.selection_decision is not None:
                raise ControlledMemoryReviewError(
                    "structural failure cannot contain partial review work"
                )
            if (
                self.outcome is MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED
                and self.reasons
                != (MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,)
            ):
                raise ControlledMemoryReviewError(
                    "resource outcome must retain its exact typed reason"
                )
            if (
                self.outcome is MemoryCandidateReviewOutcome.PLAN_INVALID
                and not set(self.reasons)
                <= {
                    MemoryCandidateReviewReason.PLAN_INTEGRITY_FAILED,
                    MemoryCandidateReviewReason.REQUEST_INTEGRITY_FAILED,
                    MemoryCandidateReviewReason.UNKNOWN_PROPOSAL_ID,
                    MemoryCandidateReviewReason.DUPLICATE_PROPOSAL_ID,
                }
            ):
                raise ControlledMemoryReviewError(
                    "invalid-plan outcome has an incompatible reason"
                )
            return
        if self.requested_count == 0 or len(self.entries) != self.requested_count:
            raise ControlledMemoryReviewError(
                "completed review requires every requested entry"
            )
        if self.selection_decision is None:
            raise ControlledMemoryReviewError(
                "completed review requires its one batch selection decision"
            )
        if self.outcome is MemoryCandidateReviewOutcome.REVIEW_COMPLETED:
            if (
                self.staging_failed_count
                or self.reasons != (MemoryCandidateReviewReason.REVIEW_COMPLETED,)
            ):
                raise ControlledMemoryReviewError(
                    "completed review cannot contain staging failures"
                )
        elif self.outcome is MemoryCandidateReviewOutcome.PLAN_STALE:
            if (
                self.staged_count
                or self.reasons
                != (
                    MemoryCandidateReviewReason.STAGING_INELIGIBLE,
                    MemoryCandidateReviewReason.PLAN_STALE,
                )
            ):
                raise ControlledMemoryReviewError(
                    "stale plan must contain only ineligible entries"
                )
        elif self.outcome is (
            MemoryCandidateReviewOutcome.REVIEW_COMPLETED_WITH_INELIGIBLE_ENTRIES
        ):
            if (
                not self.staging_failed_count
                or not self.staged_count
                or self.reasons
                != (
                    MemoryCandidateReviewReason.REVIEW_COMPLETED,
                    MemoryCandidateReviewReason.STAGING_INELIGIBLE,
                )
            ):
                raise ControlledMemoryReviewError(
                    "partial review outcome does not match its entries"
                )

    @property
    def execution_id(self) -> str:
        """Return the deterministic execution identity carried by this batch."""

        return self.batch_id


def memory_candidate_review_plan_identity(
    *,
    pipeline_fingerprint: str,
    prepared_at_ns: int,
    discovery_result: CandidateDiscoveryResult,
) -> str:
    """Return the deterministic identity of an exact prepared review plan."""

    document = {
        "discovery": {
            "diagnostic_count": len(discovery_result.diagnostics),
            "discovery_id": discovery_result.discovery_id,
            "inspected_evidence_count": discovery_result.inspected_evidence_count,
            "outcome": discovery_result.outcome.value,
            "policy_fingerprint": discovery_result.policy_fingerprint,
            "policy_id": discovery_result.policy_id,
            "policy_version": discovery_result.policy_version,
            "proposal_ids": [
                item.proposal_id for item in discovery_result.proposals
            ],
            "retained_evidence_count": discovery_result.retained_evidence_count,
        },
        "pipeline_fingerprint": pipeline_fingerprint,
        "prepared_at_ns": prepared_at_ns,
        "schema": "ayyo.memory-candidate-review-plan.v1",
    }
    return "memory-candidate-review-plan-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def memory_candidate_review_request_identity(
    *,
    plan_id: str,
    selected_proposal_ids: tuple[str, ...],
) -> str:
    """Return the deterministic identity of an exact caller allowlist."""

    document = {
        "plan_id": plan_id,
        "schema": "ayyo.memory-candidate-review-request.v1",
        "selected_proposal_ids": list(selected_proposal_ids),
    }
    return "memory-candidate-review-request-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def memory_candidate_review_entry_identity(
    *,
    plan_id: str,
    discovery_result_id: str,
    proposal_id: str,
    staging_result: CandidateStagingResult,
    selection_item: CandidateSelectionItemDecision | None,
    validation_decision: ValidationDecision | None,
    evaluated: bool,
) -> str:
    """Return the deterministic identity of one complete review lineage."""

    candidate = staging_result.candidate
    document = {
        "discovery_result_id": discovery_result_id,
        "evaluated": evaluated,
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "schema": "ayyo.memory-candidate-review-entry.v1",
        "selection": (
            None
            if selection_item is None
            else {
                "candidate_id": selection_item.candidate_id,
                "occurrence_count": selection_item.occurrence_count,
                "outcome": selection_item.outcome.value,
                "reasons": [reason.value for reason in selection_item.reasons],
            }
        ),
        "staging": {
            "candidate_id": (
                None if candidate is None else candidate_identity(candidate)
            ),
            "detail": staging_result.detail,
            "reason": staging_result.reason.value,
            "status": staging_result.status.value,
        },
        "validation": _validation_decision_document(validation_decision),
    }
    return "memory-candidate-review-entry-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def memory_candidate_review_batch_identity(
    *,
    pipeline_fingerprint: str,
    outcome: MemoryCandidateReviewOutcome,
    reasons: tuple[MemoryCandidateReviewReason, ...],
    plan_id: str | None,
    discovery_result_id: str | None,
    request_id: str | None,
    entries: tuple[MemoryCandidateReviewEntry, ...],
    selection_decision: CandidateSelectionDecision | None,
    discovery_count: int,
    requested_count: int,
    counts: tuple[int, int, int, int, int, int],
    validation_decision_counts: tuple[tuple[DecisionType, int], ...],
) -> str:
    """Return the deterministic identity of one canonical review batch."""

    (
        staged_count,
        staging_failed_count,
        selected_count,
        deferred_count,
        rejected_count,
        evaluated_count,
    ) = counts
    document = {
        "counts": {
            "deferred": deferred_count,
            "discovered": discovery_count,
            "evaluated": evaluated_count,
            "rejected": rejected_count,
            "requested": requested_count,
            "selected": selected_count,
            "staged": staged_count,
            "staging_failed": staging_failed_count,
            "validation": {
                decision_type.value: count
                for decision_type, count in validation_decision_counts
            },
        },
        "discovery_result_id": discovery_result_id,
        "entry_ids": [item.entry_id for item in entries],
        "outcome": outcome.value,
        "pipeline_fingerprint": pipeline_fingerprint,
        "plan_id": plan_id,
        "reasons": [reason.value for reason in reasons],
        "request_id": request_id,
        "schema": "ayyo.memory-candidate-review-batch.v1",
        "selection_id": (
            None if selection_decision is None else selection_decision.selection_id
        ),
    }
    return "memory-candidate-review-batch-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def _review_batch_counts(
    *,
    entries: tuple[MemoryCandidateReviewEntry, ...],
    selection_decision: CandidateSelectionDecision | None,
) -> tuple[int, int, int, int, int, int]:
    staged_count = sum(
        item.staging_result.status is CandidateStagingStatus.ELIGIBLE
        for item in entries
    )
    staging_failed_count = len(entries) - staged_count
    selected_count = (
        0 if selection_decision is None else selection_decision.selected_count
    )
    deferred_count = (
        0 if selection_decision is None else selection_decision.deferred_count
    )
    rejected_count = (
        0 if selection_decision is None else selection_decision.rejected_count
    )
    evaluated_candidate_ids = {
        item.candidate_id for item in entries if item.evaluated
    }
    return (
        staged_count,
        staging_failed_count,
        selected_count,
        deferred_count,
        rejected_count,
        len(evaluated_candidate_ids),
    )


def _validation_counts(
    entries: tuple[MemoryCandidateReviewEntry, ...],
) -> tuple[tuple[DecisionType, int], ...]:
    decisions_by_candidate = {
        item.candidate_id: item.validation_decision
        for item in entries
        if item.evaluated
    }
    counts = Counter(
        decision.decision_type
        for decision in decisions_by_candidate.values()
        if decision is not None
    )
    return tuple(
        (decision_type, counts[decision_type])
        for decision_type in DecisionType
        if counts[decision_type]
    )


def _validation_decision_document(
    decision: ValidationDecision | None,
) -> dict[str, object] | None:
    if decision is None:
        return None
    return {
        "candidate_id": candidate_identity(decision.candidate),
        "conflict_ids": [str(item) for item in decision.conflict_ids],
        "decision_type": decision.decision_type.value,
        "explanatory_metadata": [list(item) for item in decision.explanatory_metadata],
        "normalized_identity": {
            "memory_type": decision.normalized_identity.memory_type.value,
            "predicate": decision.normalized_identity.predicate,
            "subject": decision.normalized_identity.subject,
        },
        "persistence_permitted": decision.persistence_permitted,
        "reason_code": decision.reason_code.value,
        "relevant_memory_ids": [str(item) for item in decision.relevant_memory_ids],
    }


def _validate_pipeline_identity(
    pipeline_id: object,
    pipeline_version: object,
    pipeline_fingerprint: object,
) -> None:
    if pipeline_id != CONTROLLED_MEMORY_REVIEW_PIPELINE_ID:
        raise ControlledMemoryReviewError("review pipeline identity is invalid")
    if pipeline_version != CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION:
        raise ControlledMemoryReviewError("review pipeline version is invalid")
    _validate_digest_identity(
        pipeline_fingerprint,
        "controlled-memory-review-pipeline-sha256-",
        "review pipeline fingerprint",
    )
    if pipeline_fingerprint != CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT:
        raise ControlledMemoryReviewError("review pipeline fingerprint is invalid")


def _validate_digest_identity(value: object, prefix: str, field_name: str) -> None:
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or len(value) != len(prefix) + 64
        or any(character not in "0123456789abcdef" for character in value[-64:])
    ):
        raise ControlledMemoryReviewError(f"{field_name} is malformed")


def _validate_optional_digest_identity(
    value: object,
    prefix: str,
    field_name: str,
) -> None:
    if value is not None:
        _validate_digest_identity(value, prefix, field_name)
