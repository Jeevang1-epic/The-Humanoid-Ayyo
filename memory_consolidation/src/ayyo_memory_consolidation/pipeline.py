"""Explicit two-phase orchestration through read-only memory review."""

from __future__ import annotations

from ayyo_memory_validation import (
    NormalizedIdentity,
    ValidationDecision,
    canonicalize_json,
)
from ayyo_working_memory import WorkingMemory

from .discovery_models import (
    CandidateDiscoveryDiagnostic,
    CandidateDiscoveryProposal,
    CandidateDiscoveryResult,
    discovery_request_document,
)
from .discovery_policy import BoundedMemoryCandidateDiscoveryPolicy
from .errors import ControlledMemoryReviewError, MemoryConsolidationError
from .models import (
    CandidateStagingStatus,
    ConsolidationRequest,
    EvidenceReference,
)
from .pipeline_models import (
    CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
    CONTROLLED_MEMORY_REVIEW_PIPELINE_ID,
    CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION,
    MAX_MEMORY_REVIEW_AGGREGATE_CHARACTERS,
    MAX_MEMORY_REVIEW_EVALUATIONS,
    MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS,
    MemoryCandidateEvaluator,
    MemoryCandidateReviewBatch,
    MemoryCandidateReviewEntry,
    MemoryCandidateReviewOutcome,
    MemoryCandidateReviewPlan,
    MemoryCandidateReviewReason,
    MemoryCandidateReviewRequest,
    _review_batch_counts,
    _validation_decision_document,
    _validation_counts,
    memory_candidate_review_batch_identity,
    memory_candidate_review_entry_identity,
    memory_candidate_review_plan_identity,
    ordered_memory_review_reasons,
)
from .selection_models import CandidateReviewItem, CandidateSelectionOutcome
from .selection_policy import (
    ReviewedMemoryCandidateSelectionPolicy,
    candidate_identity,
)
from .service import WorkingMemoryCandidateBridge


class ControlledMemoryCandidateReviewPipeline:
    """Coordinate explicit review without acquiring persistence authority."""

    __slots__ = ("_evaluate",)

    def __init__(self, evaluator: MemoryCandidateEvaluator) -> None:
        evaluation = getattr(evaluator, "evaluate", None)
        if not callable(evaluation):
            raise ControlledMemoryReviewError(
                "review pipeline requires a read-only candidate evaluator"
            )
        self._evaluate = evaluation

    @property
    def pipeline_id(self) -> str:
        return CONTROLLED_MEMORY_REVIEW_PIPELINE_ID

    @property
    def pipeline_version(self) -> int:
        return CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION

    @property
    def pipeline_fingerprint(self) -> str:
        return CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT

    def prepare(
        self,
        working_memory: WorkingMemory,
        *,
        now_ns: int,
    ) -> MemoryCandidateReviewPlan:
        """Discover exactly once and return an immutable, non-invoking plan."""

        discovery_result = BoundedMemoryCandidateDiscoveryPolicy().discover(
            working_memory,
            now_ns=now_ns,
        )
        try:
            snapshot = _snapshot_discovery_result(discovery_result)
            _require_bounded_discovery_snapshot(snapshot)
            plan_id = memory_candidate_review_plan_identity(
                pipeline_fingerprint=self.pipeline_fingerprint,
                prepared_at_ns=now_ns,
                discovery_result=snapshot,
            )
            return MemoryCandidateReviewPlan(
                pipeline_id=self.pipeline_id,
                pipeline_version=self.pipeline_version,
                pipeline_fingerprint=self.pipeline_fingerprint,
                plan_id=plan_id,
                prepared_at_ns=now_ns,
                discovery_result=snapshot,
            )
        except (MemoryConsolidationError, TypeError, ValueError) as error:
            raise ControlledMemoryReviewError(
                "discovery returned an invalid review-plan snapshot"
            ) from error

    def execute_review(
        self,
        request: MemoryCandidateReviewRequest,
        working_memory: WorkingMemory,
        *,
        now_ns: int,
    ) -> MemoryCandidateReviewBatch:
        """Restage, select once, and evaluate only explicitly selected proposals."""

        if type(request) is not MemoryCandidateReviewRequest:
            raise ControlledMemoryReviewError(
                "execute_review requires an exact MemoryCandidateReviewRequest"
            )

        try:
            plan = _verify_review_plan(request.plan)
        except (MemoryConsolidationError, TypeError, ValueError):
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.PLAN_INVALID,
                reason=MemoryCandidateReviewReason.PLAN_INTEGRITY_FAILED,
            )

        selected_ids = request.selected_proposal_ids
        if (
            isinstance(selected_ids, (list, tuple))
            and len(selected_ids) > MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS
        ):
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
                reason=MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,
                plan=plan,
            )

        try:
            verified_request = _verify_review_request(request, plan=plan)
        except (MemoryConsolidationError, TypeError, ValueError):
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.PLAN_INVALID,
                reason=MemoryCandidateReviewReason.REQUEST_INTEGRITY_FAILED,
                plan=plan,
            )

        proposal_ids = verified_request.selected_proposal_ids
        if len(proposal_ids) > MAX_MEMORY_REVIEW_REQUESTED_PROPOSALS:
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
                reason=MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,
                plan=plan,
            )
        if len(set(proposal_ids)) != len(proposal_ids):
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.PLAN_INVALID,
                reason=MemoryCandidateReviewReason.DUPLICATE_PROPOSAL_ID,
                plan=plan,
                request=verified_request,
            )

        proposals_by_id = {
            item.proposal_id: item for item in plan.discovery_result.proposals
        }
        if any(proposal_id not in proposals_by_id for proposal_id in proposal_ids):
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.PLAN_INVALID,
                reason=MemoryCandidateReviewReason.UNKNOWN_PROPOSAL_ID,
                plan=plan,
                request=verified_request,
            )
        if not proposal_ids:
            return _review_batch(
                outcome=MemoryCandidateReviewOutcome.NOTHING_REQUESTED,
                reasons=(MemoryCandidateReviewReason.NOTHING_REQUESTED,),
                plan=plan,
                request=verified_request,
                entries=(),
                selection_decision=None,
            )
        if type(working_memory) is not WorkingMemory:
            raise ControlledMemoryReviewError(
                "execute_review requires an exact WorkingMemory instance"
            )

        bridge = WorkingMemoryCandidateBridge(working_memory)
        staged = []
        review_items = []
        for proposal_id in proposal_ids:
            proposal = proposals_by_id[proposal_id]
            staging_result = bridge.stage(proposal.request, now_ns=now_ns)
            staged.append((proposal, staging_result))
            if staging_result.status is CandidateStagingStatus.ELIGIBLE:
                review_items.append(CandidateReviewItem.from_staging(staging_result))

        selection_decision = ReviewedMemoryCandidateSelectionPolicy().select(
            tuple(review_items)
        )
        if review_items and not selection_decision.items:
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
                reason=MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,
                plan=plan,
                request=verified_request,
            )

        selected_items = tuple(
            item
            for item in selection_decision.items
            if item.outcome is CandidateSelectionOutcome.SELECT_FOR_REVIEW
        )
        if len(selected_items) > MAX_MEMORY_REVIEW_EVALUATIONS:
            return _structural_batch(
                outcome=MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
                reason=MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,
                plan=plan,
                request=verified_request,
            )
        validation_by_candidate_id = {}
        validation_characters = 0
        for item in selected_items:
            decision = self._evaluate(item.candidate)
            verified_decision = _verify_validation_decision(
                decision,
                candidate=item.candidate,
            )
            validation_characters += len(
                canonicalize_json(_validation_decision_document(verified_decision))
            )
            if validation_characters > MAX_MEMORY_REVIEW_AGGREGATE_CHARACTERS:
                return _structural_batch(
                    outcome=MemoryCandidateReviewOutcome.RESOURCE_LIMIT_REACHED,
                    reason=MemoryCandidateReviewReason.RESOURCE_LIMIT_REACHED,
                    plan=plan,
                    request=verified_request,
                )
            validation_by_candidate_id[item.candidate_id] = verified_decision

        selection_by_candidate_id = {
            item.candidate_id: item for item in selection_decision.items
        }
        entries = []
        for proposal, staging_result in staged:
            candidate = staging_result.candidate
            selection_item = (
                None
                if candidate is None
                else selection_by_candidate_id[candidate_identity(candidate)]
            )
            validation_decision = (
                None
                if selection_item is None
                else validation_by_candidate_id.get(selection_item.candidate_id)
            )
            evaluated = validation_decision is not None
            entry_id = memory_candidate_review_entry_identity(
                plan_id=plan.plan_id,
                discovery_result_id=plan.discovery_result_id,
                proposal_id=proposal.proposal_id,
                staging_result=staging_result,
                selection_item=selection_item,
                validation_decision=validation_decision,
                evaluated=evaluated,
            )
            entries.append(
                MemoryCandidateReviewEntry(
                    entry_id=entry_id,
                    plan_id=plan.plan_id,
                    discovery_result_id=plan.discovery_result_id,
                    proposal_id=proposal.proposal_id,
                    request=proposal.request,
                    staging_result=staging_result,
                    selection_item=selection_item,
                    validation_decision=validation_decision,
                    evaluated=evaluated,
                )
            )

        canonical_entries = tuple(sorted(entries, key=lambda item: item.proposal_id))
        staged_count = sum(
            entry.staging_result.status is CandidateStagingStatus.ELIGIBLE
            for entry in canonical_entries
        )
        if staged_count == len(canonical_entries):
            outcome = MemoryCandidateReviewOutcome.REVIEW_COMPLETED
            reasons = (MemoryCandidateReviewReason.REVIEW_COMPLETED,)
        elif not staged_count:
            outcome = MemoryCandidateReviewOutcome.PLAN_STALE
            reasons = ordered_memory_review_reasons(
                (
                    MemoryCandidateReviewReason.STAGING_INELIGIBLE,
                    MemoryCandidateReviewReason.PLAN_STALE,
                )
            )
        else:
            outcome = (
                MemoryCandidateReviewOutcome.REVIEW_COMPLETED_WITH_INELIGIBLE_ENTRIES
            )
            reasons = ordered_memory_review_reasons(
                (
                    MemoryCandidateReviewReason.REVIEW_COMPLETED,
                    MemoryCandidateReviewReason.STAGING_INELIGIBLE,
                )
            )
        return _review_batch(
            outcome=outcome,
            reasons=reasons,
            plan=plan,
            request=verified_request,
            entries=canonical_entries,
            selection_decision=selection_decision,
        )


def _snapshot_discovery_result(
    result: CandidateDiscoveryResult,
) -> CandidateDiscoveryResult:
    if type(result) is not CandidateDiscoveryResult:
        raise ControlledMemoryReviewError(
            "review preparation requires an exact CandidateDiscoveryResult"
        )
    proposals = tuple(
        CandidateDiscoveryProposal(
            policy_id=proposal.policy_id,
            policy_version=proposal.policy_version,
            policy_fingerprint=proposal.policy_fingerprint,
            proposal_id=proposal.proposal_id,
            request=_snapshot_consolidation_request(proposal.request),
        )
        for proposal in result.proposals
    )
    diagnostics = tuple(
        CandidateDiscoveryDiagnostic(
            reason=diagnostic.reason,
            evidence_id=diagnostic.evidence_id,
            semantic_item_id=diagnostic.semantic_item_id,
        )
        for diagnostic in result.diagnostics
    )
    return CandidateDiscoveryResult(
        policy_id=result.policy_id,
        policy_version=result.policy_version,
        policy_fingerprint=result.policy_fingerprint,
        discovery_id=result.discovery_id,
        outcome=result.outcome,
        reasons=tuple(result.reasons),
        proposals=proposals,
        diagnostics=diagnostics,
        retained_evidence_count=result.retained_evidence_count,
        inspected_evidence_count=result.inspected_evidence_count,
    )


def _snapshot_consolidation_request(
    request: ConsolidationRequest,
) -> ConsolidationRequest:
    if type(request) is not ConsolidationRequest:
        raise ControlledMemoryReviewError(
            "review proposal requires an exact ConsolidationRequest"
        )
    references = tuple(
        EvidenceReference(
            observation_id=reference.observation_id,
            observation_fingerprint=reference.observation_fingerprint,
            source_id=reference.source_id,
            semantic_item_id=reference.semantic_item_id,
        )
        for reference in request.supporting_evidence
    )
    return ConsolidationRequest(
        robot_id=request.robot_id,
        memory_type=request.memory_type,
        subject=request.subject,
        predicate=request.predicate,
        value=request.value,
        supporting_evidence=references,
        metadata=request.metadata,
    )


def _verify_review_plan(plan: MemoryCandidateReviewPlan) -> MemoryCandidateReviewPlan:
    if type(plan) is not MemoryCandidateReviewPlan:
        raise ControlledMemoryReviewError(
            "review invocation requires an exact prepared plan"
        )
    snapshot = _snapshot_discovery_result(plan.discovery_result)
    _require_bounded_discovery_snapshot(snapshot)
    rebuilt = MemoryCandidateReviewPlan(
        pipeline_id=plan.pipeline_id,
        pipeline_version=plan.pipeline_version,
        pipeline_fingerprint=plan.pipeline_fingerprint,
        plan_id=plan.plan_id,
        prepared_at_ns=plan.prepared_at_ns,
        discovery_result=snapshot,
    )
    if rebuilt != plan:
        raise ControlledMemoryReviewError("review plan snapshot was altered")
    return plan


def _verify_review_request(
    request: MemoryCandidateReviewRequest,
    *,
    plan: MemoryCandidateReviewPlan,
) -> MemoryCandidateReviewRequest:
    rebuilt = MemoryCandidateReviewRequest(
        plan=plan,
        selected_proposal_ids=request.selected_proposal_ids,
    )
    if rebuilt != request:
        raise ControlledMemoryReviewError("review request snapshot was altered")
    return request


def _verify_validation_decision(
    decision: ValidationDecision,
    *,
    candidate,
) -> ValidationDecision:
    if type(decision) is not ValidationDecision or decision.candidate != candidate:
        raise ControlledMemoryReviewError(
            "candidate evaluator returned a decision for different evidence"
        )
    rebuilt_identity = NormalizedIdentity(
        memory_type=decision.normalized_identity.memory_type,
        subject=decision.normalized_identity.subject,
        predicate=decision.normalized_identity.predicate,
    )
    rebuilt = ValidationDecision(
        decision_type=decision.decision_type,
        reason_code=decision.reason_code,
        normalized_identity=rebuilt_identity,
        candidate=candidate,
        relevant_memory_ids=tuple(decision.relevant_memory_ids),
        conflict_ids=tuple(decision.conflict_ids),
        persistence_permitted=decision.persistence_permitted,
        explanatory_metadata=tuple(decision.explanatory_metadata),
    )
    if rebuilt != decision:
        raise ControlledMemoryReviewError(
            "candidate evaluator returned an altered validation decision"
        )
    return decision


def _require_bounded_discovery_snapshot(result: CandidateDiscoveryResult) -> None:
    document = {
        "diagnostics": [
            {
                "evidence_id": item.evidence_id,
                "reason": item.reason.value,
                "semantic_item_id": item.semantic_item_id,
            }
            for item in result.diagnostics
        ],
        "policy_fingerprint": result.policy_fingerprint,
        "policy_id": result.policy_id,
        "proposals": [
            {
                "proposal_id": item.proposal_id,
                "request": discovery_request_document(item.request),
            }
            for item in result.proposals
        ],
        "schema": "ayyo.memory-candidate-discovery-resource.v1",
    }
    if len(canonicalize_json(document)) > MAX_MEMORY_REVIEW_AGGREGATE_CHARACTERS:
        raise ControlledMemoryReviewError(
            "review plan discovery snapshot exceeds its aggregate bound"
        )


def _review_batch(
    *,
    outcome: MemoryCandidateReviewOutcome,
    reasons: tuple[MemoryCandidateReviewReason, ...],
    plan: MemoryCandidateReviewPlan,
    request: MemoryCandidateReviewRequest,
    entries: tuple[MemoryCandidateReviewEntry, ...],
    selection_decision,
) -> MemoryCandidateReviewBatch:
    counts = _review_batch_counts(
        entries=entries,
        selection_decision=selection_decision,
    )
    validation_counts = _validation_counts(entries)
    batch_id = memory_candidate_review_batch_identity(
        pipeline_fingerprint=CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
        outcome=outcome,
        reasons=reasons,
        plan_id=plan.plan_id,
        discovery_result_id=plan.discovery_result_id,
        request_id=request.request_id,
        entries=entries,
        selection_decision=selection_decision,
        discovery_count=plan.proposal_count,
        requested_count=len(request.selected_proposal_ids),
        counts=counts,
        validation_decision_counts=validation_counts,
    )
    return MemoryCandidateReviewBatch(
        pipeline_id=CONTROLLED_MEMORY_REVIEW_PIPELINE_ID,
        pipeline_version=CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION,
        pipeline_fingerprint=CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
        batch_id=batch_id,
        outcome=outcome,
        reasons=reasons,
        plan_id=plan.plan_id,
        discovery_result_id=plan.discovery_result_id,
        request_id=request.request_id,
        entries=entries,
        selection_decision=selection_decision,
        discovery_count=plan.proposal_count,
        requested_count=len(request.selected_proposal_ids),
        staged_count=counts[0],
        staging_failed_count=counts[1],
        selected_count=counts[2],
        deferred_count=counts[3],
        rejected_count=counts[4],
        evaluated_count=counts[5],
        validation_decision_counts=validation_counts,
    )


def _structural_batch(
    *,
    outcome: MemoryCandidateReviewOutcome,
    reason: MemoryCandidateReviewReason,
    plan: MemoryCandidateReviewPlan | None = None,
    request: MemoryCandidateReviewRequest | None = None,
) -> MemoryCandidateReviewBatch:
    reasons = (reason,)
    plan_id = None if plan is None else plan.plan_id
    discovery_result_id = None if plan is None else plan.discovery_result_id
    request_id = None if request is None else request.request_id
    discovery_count = 0 if plan is None else plan.proposal_count
    requested_count = 0 if request is None else len(request.selected_proposal_ids)
    counts = (0, 0, 0, 0, 0, 0)
    batch_id = memory_candidate_review_batch_identity(
        pipeline_fingerprint=CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
        outcome=outcome,
        reasons=reasons,
        plan_id=plan_id,
        discovery_result_id=discovery_result_id,
        request_id=request_id,
        entries=(),
        selection_decision=None,
        discovery_count=discovery_count,
        requested_count=requested_count,
        counts=counts,
        validation_decision_counts=(),
    )
    return MemoryCandidateReviewBatch(
        pipeline_id=CONTROLLED_MEMORY_REVIEW_PIPELINE_ID,
        pipeline_version=CONTROLLED_MEMORY_REVIEW_PIPELINE_VERSION,
        pipeline_fingerprint=CONTROLLED_MEMORY_REVIEW_PIPELINE_FINGERPRINT,
        batch_id=batch_id,
        outcome=outcome,
        reasons=reasons,
        plan_id=plan_id,
        discovery_result_id=discovery_result_id,
        request_id=request_id,
        entries=(),
        selection_decision=None,
        discovery_count=discovery_count,
        requested_count=requested_count,
        staged_count=0,
        staging_failed_count=0,
        selected_count=0,
        deferred_count=0,
        rejected_count=0,
        evaluated_count=0,
        validation_decision_counts=(),
    )
