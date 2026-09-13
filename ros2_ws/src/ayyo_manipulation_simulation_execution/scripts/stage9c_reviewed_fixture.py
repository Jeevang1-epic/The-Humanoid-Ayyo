#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Build the one documented Stage 9C development proof lineage."""

from __future__ import annotations

from ayyo_executive import (
    DecisionReason,
    ExecutiveDecision,
    ExecutiveDecisionType,
    ExpectedResultCategory,
    FailurePolicy,
    Fingerprint,
    FingerprintKind,
    Plan,
    PlanStep,
)
from ayyo_manipulation_planning import (
    CollisionBox,
    ExecutionDisposition,
    ManipulationPlanEvidence,
    ManipulationPlanningRequest,
    MoveItCollisionProof,
    PlanEvidenceStatus,
    PlanningSceneEvidence,
    build_left_arm_planning_model,
    build_reviewed_collision_model,
    default_planner_configuration,
    deterministic_joint_interpolation,
    evaluate_manipulation_plan,
    make_joint_goal,
    make_joint_state,
)
from ayyo_manipulation_simulation_execution import create_simulation_execution_request
from ayyo_manipulation_trajectory import (
    FUTURE_SKILL_BACKEND_ID,
    SAFETY_REVIEW_CAPABILITY_ID,
    SAFETY_REVIEW_STEP_ID,
    TrajectoryConstructionRequest,
    TrajectoryTimingConfiguration,
    construct_deterministic_trajectory,
    create_trajectory_evidence,
    evaluate_execution_handoff_eligibility,
    evaluate_trajectory_safety_eligibility,
    trajectory_safety_review_parameters,
)
from ayyo_personal_context import ContextSnapshotVersion
from ayyo_safety import CapabilitySafetyRule, HazardClass, SafetyKernel, SafetyPolicy
from ayyo_skill_manager import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    SchemaProperty,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    SkillManagerService,
    SkillRegistry,
    ValueSchema,
    ValueType,
)


def reviewed_planning_request(
    expanded_urdf: str,
    reviewed_srdf: str,
) -> ManipulationPlanningRequest:
    """Construct the documented fixed Stage 9A demonstration request."""

    model, catalog, group = build_left_arm_planning_model(expanded_urdf)
    collision_model = build_reviewed_collision_model(
        expanded_urdf,
        reviewed_srdf,
        model,
        catalog,
        group,
    )
    box = CollisionBox(
        object_id="review-box",
        frame_id="base_link",
        position_xyz=(1.0, 0.0, 0.5),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        dimensions_xyz=(0.1, 0.1, 0.1),
    )
    return ManipulationPlanningRequest(
        robot_model=model,
        joint_catalog=catalog,
        group=group,
        collision_model=collision_model,
        start_state=make_joint_state(group, catalog, (0.0, 0.0, 0.2, 0.0)),
        goal=make_joint_goal(group, catalog, (0.3, 0.4, 0.8, 0.2)),
        scene=PlanningSceneEvidence(
            robot_model_id=model.robot_model_id,
            robot_model_fingerprint=model.robot_model_fingerprint,
            group_id=group.group_id,
            group_fingerprint=group.group_fingerprint,
            frame_id="base_link",
            collision_objects=(box,),
        ),
        planner_configuration=default_planner_configuration(),
    )


def _proposal(trajectory_evidence) -> ExecutiveDecision:
    step = PlanStep(
        step_id=SAFETY_REVIEW_STEP_ID,
        capability_id=SAFETY_REVIEW_CAPABILITY_ID,
        parameters=trajectory_safety_review_parameters(trajectory_evidence),
        dependencies=(),
        preconditions=(),
        required_context=(),
        required_approvals=(),
        constraints=(),
        expected_result=ExpectedResultCategory.INFORMATION,
        failure_policy=FailurePolicy.STOP_PLAN,
    )
    return ExecutiveDecision(
        request_id=trajectory_evidence.trajectory_evidence_id,
        owner_subject="ayyo-stage9c-simulation-proof",
        decision_type=ExecutiveDecisionType.PROPOSE,
        reason_codes=(DecisionReason.READY_FOR_SAFETY_REVIEW,),
        explanation=(
            "Review one exact Stage 9B trajectory for explicit Stage 9C simulation."
        ),
        context_snapshot_version=ContextSnapshotVersion("3" * 64),
        request_fingerprint=Fingerprint(FingerprintKind.REQUEST, "1" * 64),
        capability_contract_fingerprint=Fingerprint(
            FingerprintKind.CAPABILITY_CONTRACT,
            "2" * 64,
        ),
        context_references=(),
        assumptions=(),
        required_capabilities=(SAFETY_REVIEW_CAPABILITY_ID,),
        required_approvals=(),
        constraints=(),
        proposed_plan=Plan((step,)),
    )


def _skill_manager(kernel, parameters) -> SkillManagerService:
    properties = tuple(
        SchemaProperty(
            name=name,
            schema=ValueSchema(
                ValueType.STRING,
                min_length=1,
                max_length=256,
                allowed_values=(value,)
                if name in {"execution_disposition", "physical_validation"}
                else (),
            ),
        )
        for name, value in parameters.items()
    )
    skill = SkillDefinition(
        skill_id="manipulation.trajectory.simulation-review",
        version=SemanticVersion("1.0.0"),
        name="Future manipulation simulation review",
        description="Inert declarative Stage 9B handoff; Stage 9C remains explicit.",
        capability_ids=(SAFETY_REVIEW_CAPABILITY_ID,),
        backend_id=FUTURE_SKILL_BACKEND_ID,
        input_schema=ValueSchema(ValueType.OBJECT, properties=properties),
        output_schema=ValueSchema(ValueType.OBJECT),
        safety_classification=HazardClass.INTERNAL_NON_ACTUATING,
        expected_result=ExpectedResultCategory.INFORMATION,
        timeout_ms=1_000,
        concurrency_policy=ConcurrencyPolicy.PARALLEL,
        idempotency=IdempotencyClass.IDEMPOTENT,
        failure_semantics=FailureSemantics.NON_RETRYABLE,
        availability=SkillAvailability.AVAILABLE,
        lifecycle=SkillLifecycle.VALIDATED,
        metadata={"authority": "none", "stage": "9b"},
    )
    return SkillManagerService(
        registry=SkillRegistry(version=SemanticVersion("1.0.0"), skills=(skill,)),
        safety_kernel=kernel,
    )


def reviewed_execution_request(
    planning_request: ManipulationPlanningRequest,
    collision_proof: MoveItCollisionProof,
):
    """Derive Stage 9C only after binding the observed Stage 9A proof."""

    waypoints = deterministic_joint_interpolation(planning_request)
    stage9a_evidence = ManipulationPlanEvidence(
        request=planning_request,
        status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
        collision_proof=collision_proof,
        backend_version=collision_proof.backend_version,
        planner_seed=planning_request.planner_configuration.deterministic_seed,
        waypoints=waypoints,
        checked_collision_object_ids=tuple(
            item.object_id for item in planning_request.scene.collision_objects
        ),
        colliding_object_ids=(),
        self_collision_checked=True,
        environment_collision_checked=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    stage9a_decision = evaluate_manipulation_plan(planning_request, stage9a_evidence)
    trajectory_request = TrajectoryConstructionRequest(
        stage9a_decision=stage9a_decision,
        timing_configuration=TrajectoryTimingConfiguration(),
    )
    trajectory = construct_deterministic_trajectory(trajectory_request)
    evidence = create_trajectory_evidence(trajectory_request, trajectory)
    proposal = _proposal(evidence)
    kernel = SafetyKernel(
        SafetyPolicy(
            capability_rules=(
                CapabilitySafetyRule(
                    capability_id=SAFETY_REVIEW_CAPABILITY_ID,
                    hazard_class=HazardClass.INTERNAL_NON_ACTUATING,
                ),
            )
        )
    )
    safety_decision = kernel.evaluate(proposal)
    manager = _skill_manager(
        kernel,
        trajectory_safety_review_parameters(evidence),
    )
    selection = manager.registry.selection(
        skill_id="manipulation.trajectory.simulation-review",
        capability_id=SAFETY_REVIEW_CAPABILITY_ID,
        source_step_id=SAFETY_REVIEW_STEP_ID,
    )
    binding = manager.bind(proposal, safety_decision, selection)
    safety_result = evaluate_trajectory_safety_eligibility(
        evidence,
        proposal,
        safety_decision,
        kernel,
    )
    handoff = evaluate_execution_handoff_eligibility(
        safety_result,
        proposal,
        safety_decision,
        binding,
        manager,
    )
    return create_simulation_execution_request(handoff)
