from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from ayyo_executive import ExecutiveDecision, Plan, PlanStep
from ayyo_manipulation_planning import ExecutionDisposition
from ayyo_manipulation_trajectory import (
    HandoffEligibilityReason,
    HandoffEligibilityStatus,
    ExecutionHandoffEligibilityDecision,
    PhysicalValidationStatus,
    RuntimeEndpointState,
    SafetyEligibilityReason,
    SafetyEligibilityStatus,
    TrajectoryConstructionRequest,
    TrajectoryFailureCode,
    TrajectoryTimingConfiguration,
    TrajectoryValidationError,
    TrajectorySafetyEligibilityResult,
    construct_deterministic_trajectory,
    create_trajectory_evidence,
    evaluate_execution_handoff_eligibility,
    evaluate_trajectory_safety_eligibility,
    trajectory_review_binding_fingerprint,
    trajectory_safety_review_parameters,
)
from ayyo_safety import CapabilitySafetyRule, HazardClass, SafetyKernel, SafetyPolicy
from ayyo_skill_manager import (
    BindingReason,
    SkillManagerService,
    SkillRegistry,
    SemanticVersion,
)

from conftest import _proposal


def _replace_proposal_step(proposal: ExecutiveDecision, step: PlanStep) -> ExecutiveDecision:
    return ExecutiveDecision(
        request_id=proposal.request_id,
        owner_subject=proposal.owner_subject,
        decision_type=proposal.decision_type,
        reason_codes=proposal.reason_codes,
        explanation=proposal.explanation,
        context_snapshot_version=proposal.context_snapshot_version,
        request_fingerprint=proposal.request_fingerprint,
        capability_contract_fingerprint=proposal.capability_contract_fingerprint,
        context_references=proposal.context_references,
        assumptions=proposal.assumptions,
        required_capabilities=proposal.required_capabilities,
        required_approvals=proposal.required_approvals,
        constraints=proposal.constraints,
        proposed_plan=Plan((step,)),
    )


def test_positive_safety_result_has_only_review_semantics(stage9b_bundle) -> None:
    result = stage9b_bundle["safety_result"]
    assert result.status is (
        SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
    )
    assert result.reasons == (SafetyEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,)
    assert result.execution_disposition is ExecutionDisposition.NOT_EXECUTED
    assert result.physical_validation is PhysicalValidationStatus.ABSENT


def test_positive_handoff_stops_before_runtime_authority(stage9b_bundle) -> None:
    decision = stage9b_bundle["handoff"]
    assert decision.status is (
        HandoffEligibilityStatus.ELIGIBLE_FOR_FUTURE_SIMULATION_HANDOFF_REVIEW
    )
    assert decision.reasons == (
        HandoffEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,
        HandoffEligibilityReason.SKILL_MANAGER_HANDOFF_ELIGIBLE,
        HandoffEligibilityReason.FUTURE_RUNTIME_REVIEW_REQUIRED,
    )
    assert decision.runtime_endpoint_state is RuntimeEndpointState.NOT_REGISTERED
    assert decision.execution_disposition is ExecutionDisposition.NOT_EXECUTED
    assert decision.physical_validation is PhysicalValidationStatus.ABSENT
    assert decision.skill_handoff_reference.trajectory_binding_fingerprint == (
        trajectory_review_binding_fingerprint(
            stage9b_bundle["trajectory_evidence"]
        )
    )


def test_safety_parameters_bind_complete_relevant_lineage(stage9b_bundle) -> None:
    evidence = stage9b_bundle["trajectory_evidence"]
    parameters = trajectory_safety_review_parameters(evidence)
    assert set(parameters) == {
        "candidate_path_fingerprint",
        "candidate_path_id",
        "collision_proof_fingerprint",
        "collision_proof_id",
        "execution_disposition",
        "physical_validation",
        "stage9a_decision_fingerprint",
        "stage9a_decision_id",
        "stage9a_evidence_fingerprint",
        "stage9a_evidence_id",
        "stage9a_request_fingerprint",
        "stage9a_request_id",
        "trajectory_evidence_fingerprint",
        "trajectory_evidence_id",
        "trajectory_fingerprint",
        "trajectory_id",
        "trajectory_request_fingerprint",
        "trajectory_request_id",
    }
    assert parameters["execution_disposition"] == "not_executed"
    assert parameters["physical_validation"] == "absent"


def test_parameter_substitution_is_rejected_even_with_fresh_safety(stage9b_bundle) -> None:
    proposal = stage9b_bundle["proposal"]
    original_step = proposal.proposed_plan.steps[0]
    changed = original_step.parameters
    changed["trajectory_id"] = stage9b_bundle["trajectory_request"].candidate_path_id
    step = PlanStep(
        step_id=original_step.step_id,
        capability_id=original_step.capability_id,
        parameters=changed,
        dependencies=original_step.dependencies,
        preconditions=original_step.preconditions,
        required_context=original_step.required_context,
        required_approvals=original_step.required_approvals,
        constraints=original_step.constraints,
        expected_result=original_step.expected_result,
        failure_policy=original_step.failure_policy,
    )
    substituted = _replace_proposal_step(proposal, step)
    safety = stage9b_bundle["kernel"].evaluate(substituted)
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_trajectory_safety_eligibility(
            stage9b_bundle["trajectory_evidence"],
            substituted,
            safety,
            stage9b_bundle["kernel"],
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


def test_safety_decision_from_other_trajectory_is_rejected(stage9a_bundle, stage9b_bundle) -> None:
    request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    other_evidence = create_trajectory_evidence(
        request,
        construct_deterministic_trajectory(request),
    )
    other_proposal = _proposal(other_evidence)
    other_safety = stage9b_bundle["kernel"].evaluate(other_proposal)
    with pytest.raises(TrajectoryValidationError):
        evaluate_trajectory_safety_eligibility(
            stage9b_bundle["trajectory_evidence"],
            other_proposal,
            other_safety,
            stage9b_bundle["kernel"],
        )


def test_safety_reference_from_trajectory_a_cannot_construct_result_for_b(
    stage9a_bundle,
    stage9b_bundle,
) -> None:
    request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    other_evidence = create_trajectory_evidence(
        request,
        construct_deterministic_trajectory(request),
    )
    source = stage9b_bundle["safety_result"]
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectorySafetyEligibilityResult(
            trajectory_evidence=other_evidence,
            safety_reference=source.safety_reference,
            status=source.status,
            reasons=source.reasons,
        )
    assert caught.value.code is TrajectoryFailureCode.EVIDENCE_MISMATCH


def test_stale_safety_policy_is_rejected(stage9b_bundle) -> None:
    changed_kernel = SafetyKernel(SafetyPolicy(capability_rules=()))
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_trajectory_safety_eligibility(
            stage9b_bundle["trajectory_evidence"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            changed_kernel,
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


def test_other_hazard_never_becomes_positive_simulation_review(stage9b_bundle) -> None:
    kernel = SafetyKernel(
        SafetyPolicy(
            capability_rules=(
                CapabilitySafetyRule(
                    capability_id="manipulation.trajectory.simulation-review",
                    hazard_class=HazardClass.INFORMATIONAL_READ_ONLY,
                ),
            )
        )
    )
    safety = kernel.evaluate(stage9b_bundle["proposal"])
    result = evaluate_trajectory_safety_eligibility(
        stage9b_bundle["trajectory_evidence"],
        stage9b_bundle["proposal"],
        safety,
        kernel,
    )
    assert result.status is SafetyEligibilityStatus.INELIGIBLE
    assert result.reasons == (
        SafetyEligibilityReason.SAFETY_CLASSIFICATION_MISMATCH,
    )


def test_skill_binding_from_other_safety_decision_is_rejected(stage9b_bundle) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    object.__setattr__(tampered, "source_safety_decision_id", "safety-decision-substitute")
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            tampered,
            stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_contradictory_skill_binding_reasons_cannot_become_positive(stage9b_bundle) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    object.__setattr__(tampered, "reasons", (BindingReason.SKILL_UNAVAILABLE,))
    result = evaluate_execution_handoff_eligibility(
        stage9b_bundle["safety_result"],
        stage9b_bundle["proposal"],
        stage9b_bundle["safety_decision"],
        tampered,
        stage9b_bundle["manager"],
    )
    assert result.status is HandoffEligibilityStatus.INELIGIBLE
    assert result.reasons == (HandoffEligibilityReason.SKILL_MANAGER_INELIGIBLE,)


def test_stale_skill_selection_is_rejected(stage9b_bundle) -> None:
    empty_manager = SkillManagerService(
        registry=SkillRegistry(version=SemanticVersion("2.0.0"), skills=()),
        safety_kernel=stage9b_bundle["kernel"],
    )
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            stage9b_bundle["binding"],
            empty_manager,
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_skill_manager_is_not_automatically_invoked(stage9b_bundle) -> None:
    with patch.object(
        SkillManagerService,
        "bind",
        side_effect=AssertionError("Stage 9B must consume explicit binding evidence"),
    ):
        decision = evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            stage9b_bundle["binding"],
            stage9b_bundle["manager"],
        )
    assert decision == stage9b_bundle["handoff"]


def test_handoff_from_trajectory_a_cannot_be_reused_with_b(stage9a_bundle, stage9b_bundle) -> None:
    request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    evidence = create_trajectory_evidence(request, construct_deterministic_trajectory(request))
    proposal = _proposal(evidence)
    safety = stage9b_bundle["kernel"].evaluate(proposal)
    with pytest.raises(TrajectoryValidationError):
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            proposal,
            safety,
            stage9b_bundle["binding"],
            stage9b_bundle["manager"],
        )


def test_skill_reference_from_a_cannot_construct_positive_handoff_for_b(
    stage9a_bundle,
    stage9b_bundle,
) -> None:
    request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    evidence = create_trajectory_evidence(
        request,
        construct_deterministic_trajectory(request),
    )
    proposal = _proposal(evidence)
    safety = stage9b_bundle["kernel"].evaluate(proposal)
    safety_result = evaluate_trajectory_safety_eligibility(
        evidence,
        proposal,
        safety,
        stage9b_bundle["kernel"],
    )
    with pytest.raises(TrajectoryValidationError) as caught:
        ExecutionHandoffEligibilityDecision(
            safety_result=safety_result,
            status=(
                HandoffEligibilityStatus.ELIGIBLE_FOR_FUTURE_SIMULATION_HANDOFF_REVIEW
            ),
            reasons=(
                HandoffEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,
                HandoffEligibilityReason.SKILL_MANAGER_HANDOFF_ELIGIBLE,
                HandoffEligibilityReason.FUTURE_RUNTIME_REVIEW_REQUIRED,
            ),
            skill_handoff_reference=(
                stage9b_bundle["handoff"].skill_handoff_reference
            ),
        )
    assert caught.value.code is TrajectoryFailureCode.EVIDENCE_MISMATCH
