"""Fail-closed Safety and Skill eligibility integration for Stage 9B."""

from __future__ import annotations

from ayyo_executive import (
    DecisionReason,
    ExecutiveDecision,
    ExecutiveDecisionType,
    ExecutiveError,
    ExpectedResultCategory,
    FailurePolicy,
    Plan,
    PlanStep,
)
from ayyo_safety import (
    HazardClass,
    SafetyDecision,
    SafetyDisposition,
    SafetyKernel,
    SafetyKernelError,
    SafetyRevalidationStatus,
)
from ayyo_skill_manager import (
    BindingStatus,
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    InvocationStatus,
    SkillAvailability,
    SkillBindingResult,
    SkillInvocation,
    SkillLifecycle,
    SkillManagerService,
    SkillManagerError,
    SkillSelection,
)

from .errors import TrajectoryFailureCode, TrajectoryValidationError
from .models import (
    FUTURE_SKILL_BACKEND_ID,
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
    trajectory_review_binding_fingerprint,
    verify_handoff_decision,
    verify_safety_result,
    verify_trajectory_evidence,
)


def trajectory_safety_review_parameters(
    evidence: TrajectoryEvidence,
) -> dict[str, str]:
    """Return the closed parameter document binding Safety to one trajectory."""

    if not verify_trajectory_evidence(evidence):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "Safety parameters require verified trajectory evidence",
        )
    request = evidence.request
    trajectory = evidence.trajectory
    return {
        "candidate_path_fingerprint": request.candidate_path_fingerprint,
        "candidate_path_id": request.candidate_path_id,
        "collision_proof_fingerprint": request.collision_proof_fingerprint,
        "collision_proof_id": request.collision_proof_id,
        "execution_disposition": evidence.execution_disposition.value,
        "physical_validation": evidence.physical_validation.value,
        "stage9a_decision_fingerprint": request.stage9a_decision_fingerprint,
        "stage9a_decision_id": request.stage9a_decision_id,
        "stage9a_evidence_fingerprint": request.stage9a_evidence_fingerprint,
        "stage9a_evidence_id": request.stage9a_evidence_id,
        "stage9a_request_fingerprint": request.stage9a_request_fingerprint,
        "stage9a_request_id": request.stage9a_request_id,
        "trajectory_evidence_fingerprint": evidence.trajectory_evidence_fingerprint,
        "trajectory_evidence_id": evidence.trajectory_evidence_id,
        "trajectory_fingerprint": trajectory.trajectory_fingerprint,
        "trajectory_id": trajectory.trajectory_id,
        "trajectory_request_fingerprint": request.trajectory_request_fingerprint,
        "trajectory_request_id": request.trajectory_request_id,
    }


def _validate_exact_proposal(
    evidence: TrajectoryEvidence,
    proposal: ExecutiveDecision,
) -> None:
    if type(proposal) is not ExecutiveDecision:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety review requires an immutable Executive decision",
        )
    plan = proposal.proposed_plan
    if type(plan) is not Plan:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety review proposal must contain one exact trajectory-review step",
        )
    try:
        if len(plan.steps) != 1:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "Safety review proposal must contain one exact trajectory-review step",
            )
        step = plan.steps[0]
    except (AttributeError, TypeError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety review proposal plan failed its immutable public contract",
        ) from error
    if type(step) is not PlanStep:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal is not the closed non-actuating trajectory-review contract",
        )
    try:
        invalid = (
            proposal.request_id != evidence.trajectory_evidence_id
            or proposal.decision_type is not ExecutiveDecisionType.PROPOSE
            or proposal.reason_codes != (DecisionReason.READY_FOR_SAFETY_REVIEW,)
            or proposal.context_references
            or proposal.assumptions
            or proposal.required_capabilities != (SAFETY_REVIEW_CAPABILITY_ID,)
            or proposal.required_approvals
            or proposal.constraints
            or step.step_id != SAFETY_REVIEW_STEP_ID
            or step.capability_id != SAFETY_REVIEW_CAPABILITY_ID
            or step.parameters != trajectory_safety_review_parameters(evidence)
            or step.dependencies
            or step.preconditions
            or step.required_context
            or step.required_approvals
            or step.constraints
            or step.expected_result is not ExpectedResultCategory.INFORMATION
            or step.failure_policy is not FailurePolicy.STOP_PLAN
        )
    except (AttributeError, ExecutiveError, TypeError, ValueError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal failed closed during trajectory-review reconstruction",
        ) from error
    if invalid:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal is not the closed non-actuating trajectory-review contract",
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

    if not verify_trajectory_evidence(evidence):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "Safety eligibility requires verified trajectory evidence",
        )
    if type(kernel) is not SafetyKernel or type(safety_decision) is not SafetyDecision:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety eligibility requires exact public Safety contracts",
        )
    _validate_exact_proposal(evidence, proposal)
    try:
        revalidation = kernel.revalidate(safety_decision, proposal)
        rebuilt = kernel.evaluate(proposal)
    except (AttributeError, SafetyKernelError, TypeError, ValueError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety evidence could not be independently revalidated",
        ) from error
    if (
        revalidation.status is not SafetyRevalidationStatus.CURRENT
        or rebuilt != safety_decision
        or safety_decision.source_decision_id != proposal.decision_id
        or safety_decision.source_request_id != evidence.trajectory_evidence_id
        or len(safety_decision.step_decisions) != 1
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety evidence is stale, substituted, or not reproducible",
        )
    step = safety_decision.step_decisions[0]
    if (
        step.step_id != SAFETY_REVIEW_STEP_ID
        or step.capability_id != SAFETY_REVIEW_CAPABILITY_ID
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety step does not bind the trajectory-review capability",
        )
    disposition = ReviewedSafetyDisposition(safety_decision.disposition.value)
    hazard = (
        ReviewedHazardClass.INTERNAL_NON_ACTUATING
        if step.hazard_class is HazardClass.INTERNAL_NON_ACTUATING
        else ReviewedHazardClass.OTHER
    )
    reference = SafetyEligibilityReference(
        source_executive_decision_id=proposal.decision_id,
        source_executive_decision_fingerprint=str(proposal.decision_fingerprint),
        source_safety_decision_id=safety_decision.decision_id,
        source_safety_decision_fingerprint=str(safety_decision.decision_fingerprint),
        source_proposal_fingerprint=str(safety_decision.proposal_fingerprint),
        source_policy_version=safety_decision.policy_version,
        source_policy_fingerprint=str(safety_decision.policy_fingerprint),
        source_step_id=step.step_id,
        capability_id=step.capability_id,
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
    if type(manager) is not SkillManagerService or type(binding_result) is not (
        SkillBindingResult
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "handoff eligibility requires exact public Skill Manager contracts",
        )
    rebuilt_safety_result = evaluate_trajectory_safety_eligibility(
        safety_result.trajectory_evidence,
        proposal,
        safety_decision,
        manager.safety_kernel,
    )
    if rebuilt_safety_result != safety_result:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety result does not match the supplied trajectory and policy",
        )
    selection = binding_result.selection
    if type(selection) is not SkillSelection:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding selection failed its immutable public contract",
        )
    try:
        skill = manager.registry.resolve(selection.skill_id)
        current_selection = manager.registry.selection(
            skill_id=selection.skill_id,
            capability_id=selection.capability_id,
            source_step_id=selection.source_step_id,
        )
    except (AttributeError, SkillManagerError, TypeError, ValueError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding registry evidence could not be revalidated",
        ) from error
    if (
        current_selection != selection
        or skill is None
        or binding_result.source_safety_decision_id != safety_decision.decision_id
        or selection.capability_id != SAFETY_REVIEW_CAPABILITY_ID
        or selection.source_step_id != SAFETY_REVIEW_STEP_ID
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding is stale, substituted, or cross-composed",
        )

    if safety_result.status is not (
        SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
    ):
        return ExecutionHandoffEligibilityDecision(
            safety_result=safety_result,
            status=HandoffEligibilityStatus.INELIGIBLE,
            reasons=(HandoffEligibilityReason.SAFETY_INELIGIBLE,),
            skill_handoff_reference=None,
        )

    invocation = binding_result.invocation
    expected_parameters = trajectory_safety_review_parameters(
        safety_result.trajectory_evidence
    )
    if (
        binding_result.status is not BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
        or binding_result.reasons
        or type(invocation) is not SkillInvocation
        or invocation.status is not InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
        or invocation.skill_definition != skill
        or invocation.selection != selection
        or skill.availability is not SkillAvailability.AVAILABLE
        or skill.lifecycle is not SkillLifecycle.VALIDATED
        or skill.required_context
        or skill.required_resources
        or skill.required_approval_classes
        or skill.concurrency_policy is not ConcurrencyPolicy.PARALLEL
        or skill.idempotency is not IdempotencyClass.IDEMPOTENT
        or skill.failure_semantics is not FailureSemantics.NON_RETRYABLE
        or invocation.parameters != expected_parameters
        or invocation.context_references
        or invocation.required_resources
        or invocation.required_approvals
        or invocation.backend_id != FUTURE_SKILL_BACKEND_ID
        or invocation.expected_result is not ExpectedResultCategory.INFORMATION
        or invocation.safety_classification is not HazardClass.INTERNAL_NON_ACTUATING
        or invocation.source_request_id != safety_result.trajectory_evidence.trajectory_evidence_id
        or invocation.source_executive_decision_id != proposal.decision_id
        or invocation.source_safety_decision_id != safety_decision.decision_id
        or str(invocation.source_executive_fingerprint)
        != safety_result.safety_reference.source_executive_decision_fingerprint
        or str(invocation.source_safety_fingerprint)
        != safety_result.safety_reference.source_safety_decision_fingerprint
        or str(invocation.source_proposal_fingerprint)
        != safety_result.safety_reference.source_proposal_fingerprint
        or str(invocation.source_policy_fingerprint)
        != safety_result.safety_reference.source_policy_fingerprint
        or invocation.source_policy_version
        != safety_result.safety_reference.source_policy_version
    ):
        return ExecutionHandoffEligibilityDecision(
            safety_result=safety_result,
            status=HandoffEligibilityStatus.INELIGIBLE,
            reasons=(HandoffEligibilityReason.SKILL_MANAGER_INELIGIBLE,),
            skill_handoff_reference=None,
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
        selection_fingerprint=str(binding_result.selection.fingerprint),
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
    )
    if not verify_handoff_decision(decision):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.EVIDENCE_MISMATCH,
            "constructed handoff decision failed recursive verification",
        )
    return decision
