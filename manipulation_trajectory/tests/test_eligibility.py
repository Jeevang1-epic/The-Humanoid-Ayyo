from __future__ import annotations

import copy
from dataclasses import replace
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
    verify_safety_result,
)
from ayyo_safety import CapabilitySafetyRule, HazardClass, SafetyKernel, SafetyPolicy
from ayyo_skill_manager import (
    BindingReason,
    SkillInvocation,
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


def test_post_construction_proposal_shape_mutation_fails_with_typed_error(
    stage9b_bundle,
) -> None:
    proposal = copy.deepcopy(stage9b_bundle["proposal"])
    object.__setattr__(proposal, "proposed_plan", "malformed")
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_trajectory_safety_eligibility(
            stage9b_bundle["trajectory_evidence"],
            proposal,
            stage9b_bundle["safety_decision"],
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
            source_proposal=stage9b_bundle["proposal"],
            source_safety_decision=stage9b_bundle["safety_decision"],
            source_safety_kernel=stage9b_bundle["kernel"],
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


def test_rehashed_safety_reference_from_a_cannot_attest_trajectory_b(
    stage9a_bundle,
    stage9b_bundle,
) -> None:
    request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    evidence_b = create_trajectory_evidence(
        request,
        construct_deterministic_trajectory(request),
    )
    rebound = replace(
        stage9b_bundle["safety_result"].safety_reference,
        trajectory_binding_fingerprint=trajectory_review_binding_fingerprint(evidence_b),
    )
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectorySafetyEligibilityResult(
            trajectory_evidence=evidence_b,
            safety_reference=rebound,
            status=stage9b_bundle["safety_result"].status,
            reasons=stage9b_bundle["safety_result"].reasons,
            source_proposal=stage9b_bundle["proposal"],
            source_safety_decision=stage9b_bundle["safety_decision"],
            source_safety_kernel=stage9b_bundle["kernel"],
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


def test_positive_safety_result_cannot_be_created_from_reference_only(
    stage9b_bundle,
) -> None:
    source = stage9b_bundle["safety_result"]
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectorySafetyEligibilityResult(
            trajectory_evidence=source.trajectory_evidence,
            safety_reference=source.safety_reference,
            status=source.status,
            reasons=source.reasons,
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


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


def test_nested_safety_rule_mutation_with_stale_identity_is_rejected(
    stage9b_bundle,
) -> None:
    kernel = SafetyKernel(
        SafetyPolicy(
            capability_rules=(
                CapabilitySafetyRule(
                    capability_id="manipulation.trajectory.simulation-review",
                    hazard_class=HazardClass.PHYSICAL_MOVEMENT,
                ),
            )
        )
    )
    policy_fingerprint = kernel.policy.fingerprint
    object.__setattr__(
        kernel.policy.capability_rules[0],
        "hazard_class",
        HazardClass.INTERNAL_NON_ACTUATING,
    )
    safety = kernel.evaluate(stage9b_bundle["proposal"])
    assert safety.disposition.value == "eligible_for_downstream"
    assert kernel.policy.fingerprint == policy_fingerprint

    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_trajectory_safety_eligibility(
            stage9b_bundle["trajectory_evidence"],
            stage9b_bundle["proposal"],
            safety,
            kernel,
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


def test_positive_safety_result_construction_rejects_mutated_authority(
    stage9b_bundle,
) -> None:
    kernel = SafetyKernel(
        SafetyPolicy(
            capability_rules=(
                CapabilitySafetyRule(
                    capability_id="manipulation.trajectory.simulation-review",
                    hazard_class=HazardClass.INTERNAL_NON_ACTUATING,
                ),
            )
        )
    )
    safety = kernel.evaluate(stage9b_bundle["proposal"])
    source = stage9b_bundle["safety_result"]
    object.__setattr__(
        kernel.policy.capability_rules[0],
        "hazard_class",
        HazardClass.PHYSICAL_MOVEMENT,
    )

    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectorySafetyEligibilityResult(
            trajectory_evidence=source.trajectory_evidence,
            safety_reference=source.safety_reference,
            status=source.status,
            reasons=source.reasons,
            source_proposal=stage9b_bundle["proposal"],
            source_safety_decision=safety,
            source_safety_kernel=kernel,
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


def test_post_construction_skill_selection_mutation_fails_with_typed_error(
    stage9b_bundle,
) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    object.__setattr__(tampered, "selection", None)
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
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            tampered,
            stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


@pytest.mark.parametrize("field", ("invocation_id", "fingerprint"))
def test_mutated_skill_invocation_identity_fails_closed(
    stage9b_bundle,
    field: str,
) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    invocation = tampered.invocation
    assert invocation is not None
    replacement = (
        "forged-invocation"
        if field == "invocation_id"
        else type(invocation.fingerprint)(invocation.fingerprint.kind, "0" * 64)
    )
    object.__setattr__(invocation, field, replacement)
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            tampered,
            stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_mutated_skill_invocation_parameters_fail_closed(stage9b_bundle) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    invocation = tampered.invocation
    assert invocation is not None
    changed = invocation.parameters
    changed["trajectory_id"] = stage9b_bundle["trajectory_request"].candidate_path_id
    object.__setattr__(invocation, "_parameters", changed)
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            tampered,
            stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


@pytest.mark.parametrize(
    "mutation",
    ("selection_fingerprint", "skill_fingerprint", "source_request_id"),
)
def test_skill_identity_and_source_substitution_fails_closed(
    stage9b_bundle,
    mutation: str,
) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    invocation = tampered.invocation
    assert invocation is not None
    if mutation == "selection_fingerprint":
        value = tampered.selection.fingerprint
        object.__setattr__(
            tampered.selection,
            "fingerprint",
            type(value)(value.kind, "0" * 64),
        )
    elif mutation == "skill_fingerprint":
        value = invocation.skill_definition.fingerprint
        object.__setattr__(
            invocation.skill_definition,
            "fingerprint",
            type(value)(value.kind, "0" * 64),
        )
    else:
        object.__setattr__(invocation, "source_request_id", "forged-request")
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            tampered,
            stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_rehashed_outer_handoff_cannot_hide_mutated_invocation(stage9b_bundle) -> None:
    tampered = copy.deepcopy(stage9b_bundle["binding"])
    assert tampered.invocation is not None
    object.__setattr__(tampered.invocation, "invocation_id", "forged-invocation")
    with pytest.raises(TrajectoryValidationError) as caught:
        ExecutionHandoffEligibilityDecision(
            safety_result=stage9b_bundle["safety_result"],
            status=stage9b_bundle["handoff"].status,
            reasons=stage9b_bundle["handoff"].reasons,
            skill_handoff_reference=stage9b_bundle["handoff"].skill_handoff_reference,
            source_skill_binding=tampered,
            source_skill_manager=stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


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


def test_nested_skill_schema_mutation_with_stale_identity_is_rejected(
    stage9b_bundle,
) -> None:
    manager = stage9b_bundle["manager"]
    skill = manager.registry.skills[0]
    skill_fingerprint = skill.fingerprint
    registry_fingerprint = manager.registry.fingerprint
    object.__setattr__(skill.input_schema, "allow_additional_properties", True)
    assert skill.fingerprint == skill_fingerprint
    assert manager.registry.fingerprint == registry_fingerprint

    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            stage9b_bundle["binding"],
            manager,
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_handoff_construction_rejects_mutated_skill_declaration(
    stage9b_bundle,
) -> None:
    handoff = stage9b_bundle["handoff"]
    manager = stage9b_bundle["manager"]
    object.__setattr__(
        manager.registry.skills[0].input_schema,
        "allow_additional_properties",
        True,
    )

    with pytest.raises(TrajectoryValidationError) as caught:
        ExecutionHandoffEligibilityDecision(
            safety_result=handoff.safety_result,
            status=handoff.status,
            reasons=handoff.reasons,
            skill_handoff_reference=handoff.skill_handoff_reference,
            source_skill_binding=stage9b_bundle["binding"],
            source_skill_manager=manager,
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
            source_skill_binding=stage9b_bundle["binding"],
            source_skill_manager=stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_uninitialized_exact_public_contracts_fail_with_typed_errors(
    stage9b_bundle,
) -> None:
    with pytest.raises(TrajectoryValidationError) as proposal_error:
        evaluate_trajectory_safety_eligibility(
            stage9b_bundle["trajectory_evidence"],
            object.__new__(ExecutiveDecision),
            stage9b_bundle["safety_decision"],
            stage9b_bundle["kernel"],
        )
    assert proposal_error.value.code is TrajectoryFailureCode.SAFETY_MISMATCH

    with pytest.raises(TrajectoryValidationError) as binding_error:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            object.__new__(type(stage9b_bundle["binding"])),
            stage9b_bundle["manager"],
        )
    assert binding_error.value.code is TrajectoryFailureCode.SKILL_MISMATCH

    malformed = copy.deepcopy(stage9b_bundle["binding"])
    object.__setattr__(malformed, "invocation", object.__new__(SkillInvocation))
    with pytest.raises(TrajectoryValidationError) as invocation_error:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            malformed,
            stage9b_bundle["manager"],
        )
    assert invocation_error.value.code is TrajectoryFailureCode.SKILL_MISMATCH


def test_malformed_executive_parameter_storage_uses_typed_errors(
    stage9b_bundle,
) -> None:
    result = stage9b_bundle["safety_result"]
    proposal = result.source_proposal
    object.__setattr__(proposal.proposed_plan.steps[0], "_parameters", [])

    assert not verify_safety_result(result)
    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_trajectory_safety_eligibility(
            result.trajectory_evidence,
            proposal,
            result.source_safety_decision,
            result.source_safety_kernel,
        )
    assert caught.value.code is TrajectoryFailureCode.SAFETY_MISMATCH


def test_malformed_skill_parameter_storage_uses_typed_error(
    stage9b_bundle,
) -> None:
    binding = stage9b_bundle["binding"]
    assert binding.invocation is not None
    object.__setattr__(binding.invocation, "_parameters", [])

    with pytest.raises(TrajectoryValidationError) as caught:
        evaluate_execution_handoff_eligibility(
            stage9b_bundle["safety_result"],
            stage9b_bundle["proposal"],
            stage9b_bundle["safety_decision"],
            binding,
            stage9b_bundle["manager"],
        )
    assert caught.value.code is TrajectoryFailureCode.SKILL_MISMATCH
