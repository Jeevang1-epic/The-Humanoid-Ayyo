"""Fail-closed Safety and Skill eligibility integration for Stage 9B."""

from __future__ import annotations

from ayyo_executive import (
    ExecutiveDecision,
)
from ayyo_safety import (
    SafetyDecision,
    SafetyKernel,
)
from ayyo_skill_manager import (
    SkillBindingResult,
    SkillManagerService,
)

from .errors import TrajectoryFailureCode, TrajectoryValidationError
from .models import (
    HandoffEligibilityReason,
    HandoffEligibilityStatus,
    ReviewedHazardClass,
    ReviewedSafetyDisposition,
    SAFETY_REVIEW_CAPABILITY_ID,
    SAFETY_REVIEW_STEP_ID,
    SafetyEligibilityReason,
    SafetyEligibilityReference,
    SafetyEligibilityStatus,
    SkillRuntimeHandoffReference,
    TrajectoryEvidence,
    TrajectorySafetyEligibilityResult,
    ExecutionHandoffEligibilityDecision,
    _validated_safety_context,
    _validated_skill_binding_context,
    trajectory_review_binding_fingerprint,
    verify_handoff_decision,
    verify_safety_result,
)


def evaluate_trajectory_safety_eligibility(
    evidence: TrajectoryEvidence,
    proposal: ExecutiveDecision,
    safety_decision: SafetyDecision,
    kernel: SafetyKernel,
) -> TrajectorySafetyEligibilityResult:
    """Verify external Safety evidence and express review-only eligibility.

    Eligibility applies to an information-only review handoff.  It is not a
    physical-movement Safety decision and confers no execution authority.
    """

    disposition, hazard = _validated_safety_context(
        evidence,
        proposal,
        safety_decision,
        kernel,
    )
    reference = SafetyEligibilityReference(
        source_executive_decision_id=proposal.decision_id,
        source_executive_decision_fingerprint=str(proposal.decision_fingerprint),
        source_safety_decision_id=safety_decision.decision_id,
        source_safety_decision_fingerprint=str(safety_decision.decision_fingerprint),
        source_proposal_fingerprint=str(safety_decision.proposal_fingerprint),
        source_policy_version=safety_decision.policy_version,
        source_policy_fingerprint=str(safety_decision.policy_fingerprint),
        source_step_id=SAFETY_REVIEW_STEP_ID,
        capability_id=SAFETY_REVIEW_CAPABILITY_ID,
        safety_disposition=disposition,
        hazard_class=hazard,
        trajectory_binding_fingerprint=trajectory_review_binding_fingerprint(evidence),
    )
    if (
        disposition is ReviewedSafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM
        and hazard is ReviewedHazardClass.INTERNAL_NON_ACTUATING
    ):
        status = SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
        reasons = (SafetyEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,)
    else:
        status = SafetyEligibilityStatus.INELIGIBLE
        reason_by_disposition = {
            ReviewedSafetyDisposition.EXTERNAL_APPROVAL_REQUIRED: (
                SafetyEligibilityReason.SAFETY_APPROVAL_REQUIRED
            ),
            ReviewedSafetyDisposition.DEFERRED: SafetyEligibilityReason.SAFETY_DEFERRED,
            ReviewedSafetyDisposition.BLOCKED: SafetyEligibilityReason.SAFETY_BLOCKED,
            ReviewedSafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM: (
                SafetyEligibilityReason.SAFETY_CLASSIFICATION_MISMATCH
            ),
        }
        reasons = (reason_by_disposition[disposition],)
    return TrajectorySafetyEligibilityResult(
        trajectory_evidence=evidence,
        safety_reference=reference,
        status=status,
        reasons=reasons,
        source_proposal=proposal,
        source_safety_decision=safety_decision,
        source_safety_kernel=kernel,
    )


def evaluate_execution_handoff_eligibility(
    safety_result: TrajectorySafetyEligibilityResult,
    proposal: ExecutiveDecision,
    safety_decision: SafetyDecision,
    binding_result: SkillBindingResult,
    manager: SkillManagerService,
) -> ExecutionHandoffEligibilityDecision:
    """Verify an inert Skill binding and stop before any Runtime request exists."""

    if not verify_safety_result(safety_result):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "handoff eligibility requires a verified Stage 9B Safety result",
        )
    try:
        source_kernel = safety_result.source_safety_kernel
        if (
            proposal != safety_result.source_proposal
            or safety_decision != safety_result.source_safety_decision
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "handoff inputs differ from the authoritative Safety provenance",
            )
    except AttributeError as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety result provenance is malformed",
        ) from error
    rebuilt_safety_result = evaluate_trajectory_safety_eligibility(
        safety_result.trajectory_evidence,
        proposal,
        safety_decision,
        source_kernel,
    )
    if rebuilt_safety_result != safety_result:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety result does not match the supplied trajectory and policy",
        )
    rebuilt_binding, invocation, skill_eligible = _validated_skill_binding_context(
        safety_result,
        binding_result,
        manager,
    )

    if safety_result.status is not (
        SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
    ):
        return ExecutionHandoffEligibilityDecision(
            safety_result=safety_result,
            status=HandoffEligibilityStatus.INELIGIBLE,
            reasons=(HandoffEligibilityReason.SAFETY_INELIGIBLE,),
            skill_handoff_reference=None,
            source_skill_binding=rebuilt_binding,
            source_skill_manager=manager,
        )

    if not skill_eligible or invocation is None:
        return ExecutionHandoffEligibilityDecision(
            safety_result=safety_result,
            status=HandoffEligibilityStatus.INELIGIBLE,
            reasons=(HandoffEligibilityReason.SKILL_MANAGER_INELIGIBLE,),
            skill_handoff_reference=None,
            source_skill_binding=rebuilt_binding,
            source_skill_manager=manager,
        )
    reference = SkillRuntimeHandoffReference(
        source_safety_result_id=safety_result.safety_result_id,
        source_safety_result_fingerprint=safety_result.safety_result_fingerprint,
        source_safety_decision_id=safety_decision.decision_id,
        source_safety_decision_fingerprint=str(safety_decision.decision_fingerprint),
        source_step_id=SAFETY_REVIEW_STEP_ID,
        capability_id=SAFETY_REVIEW_CAPABILITY_ID,
        skill_id=invocation.skill_definition.skill_id,
        skill_version=str(invocation.skill_definition.version),
        skill_fingerprint=str(invocation.skill_definition.fingerprint),
        selection_fingerprint=str(rebuilt_binding.selection.fingerprint),
        invocation_id=invocation.invocation_id,
        invocation_fingerprint=str(invocation.fingerprint),
        backend_id=invocation.backend_id,
        trajectory_binding_fingerprint=trajectory_review_binding_fingerprint(
            safety_result.trajectory_evidence
        ),
    )
    decision = ExecutionHandoffEligibilityDecision(
        safety_result=safety_result,
        status=(
            HandoffEligibilityStatus.ELIGIBLE_FOR_FUTURE_SIMULATION_HANDOFF_REVIEW
        ),
        reasons=(
            HandoffEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,
            HandoffEligibilityReason.SKILL_MANAGER_HANDOFF_ELIGIBLE,
            HandoffEligibilityReason.FUTURE_RUNTIME_REVIEW_REQUIRED,
        ),
        skill_handoff_reference=reference,
        source_skill_binding=rebuilt_binding,
        source_skill_manager=manager,
    )
    if not verify_handoff_decision(decision):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.EVIDENCE_MISMATCH,
            "constructed handoff decision failed recursive verification",
        )
    return decision
