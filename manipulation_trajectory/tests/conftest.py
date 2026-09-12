from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

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
from ayyo_safety import (
    CapabilitySafetyRule,
    HazardClass,
    SafetyKernel,
    SafetyPolicy,
)
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
XACRO_PATH = REPOSITORY_ROOT / "ros2_ws/src/ayyo_description/urdf/ayyo.urdf.xacro"
SRDF_PATH = (
    REPOSITORY_ROOT
    / "ros2_ws/src/ayyo_manipulation_planning/config/ayyo_left_arm.srdf"
)


@pytest.fixture(scope="session")
def expanded_urdf() -> str:
    return subprocess.run(
        ["xacro", str(XACRO_PATH), "use_meshes:=false", "simulation_mode:=false"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout


@pytest.fixture(scope="session")
def reviewed_srdf() -> str:
    return SRDF_PATH.read_text(encoding="utf-8")


@pytest.fixture()
def stage9a_bundle(expanded_urdf: str, reviewed_srdf: str) -> dict[str, object]:
    model, catalog, group = build_left_arm_planning_model(expanded_urdf)
    collision_model = build_reviewed_collision_model(
        expanded_urdf,
        reviewed_srdf,
        model,
        catalog,
        group,
    )
    start = make_joint_state(group, catalog, (0.0, 0.0, 0.2, 0.0))
    goal = make_joint_goal(group, catalog, (0.3, 0.4, 0.8, 0.2))
    box = CollisionBox(
        object_id="review-box",
        frame_id="base_link",
        position_xyz=(1.0, 0.0, 0.5),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        dimensions_xyz=(0.1, 0.1, 0.1),
    )
    scene = PlanningSceneEvidence(
        robot_model_id=model.robot_model_id,
        robot_model_fingerprint=model.robot_model_fingerprint,
        group_id=group.group_id,
        group_fingerprint=group.group_fingerprint,
        frame_id="base_link",
        collision_objects=(box,),
    )
    request = ManipulationPlanningRequest(
        robot_model=model,
        joint_catalog=catalog,
        group=group,
        collision_model=collision_model,
        start_state=start,
        goal=goal,
        scene=scene,
        planner_configuration=default_planner_configuration(),
    )
    waypoints = deterministic_joint_interpolation(request)
    proof = MoveItCollisionProof(
        request_id=request.request_id,
        request_fingerprint=request.request_fingerprint,
        collision_model_id=collision_model.collision_model_id,
        collision_model_fingerprint=collision_model.collision_model_fingerprint,
        planner_configuration_id=request.planner_configuration.configuration_id,
        planner_configuration_fingerprint=(
            request.planner_configuration.configuration_fingerprint
        ),
        robot_description_content_fingerprint=(
            collision_model.robot_description_content_fingerprint
        ),
        srdf_content_fingerprint=collision_model.srdf_content_fingerprint,
        disabled_collision_pairs=collision_model.disabled_collision_pairs,
        backend_version="moveit-2.12.4",
        joint_names=group.joint_names,
        waypoints=waypoints,
        collision_objects=scene.collision_objects,
        self_collision_free=(True,) * len(waypoints),
        environment_collision_free=(True,) * len(waypoints),
        limits_match_reviewed=True,
        goal_obstacle_collision_reported=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    evidence = ManipulationPlanEvidence(
        request=request,
        status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
        collision_proof=proof,
        backend_version="moveit-2.12.4",
        planner_seed=0,
        waypoints=waypoints,
        checked_collision_object_ids=(box.object_id,),
        colliding_object_ids=(),
        self_collision_checked=True,
        environment_collision_checked=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    decision = evaluate_manipulation_plan(request, evidence)
    return {
        "model": model,
        "catalog": catalog,
        "group": group,
        "collision_model": collision_model,
        "request": request,
        "waypoints": waypoints,
        "proof": proof,
        "evidence": evidence,
        "decision": decision,
    }


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
        owner_subject="ayyo-stage9b-review",
        decision_type=ExecutiveDecisionType.PROPOSE,
        reason_codes=(DecisionReason.READY_FOR_SAFETY_REVIEW,),
        explanation="Review one exact inert trajectory artifact for a future simulation boundary.",
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


def _manager(kernel: SafetyKernel, parameters: dict[str, str]) -> SkillManagerService:
    properties = tuple(
        SchemaProperty(
            name=name,
            schema=ValueSchema(
                ValueType.STRING,
                min_length=1,
                max_length=256,
                allowed_values=(value,) if name in {
                    "execution_disposition",
                    "physical_validation",
                } else (),
            ),
        )
        for name, value in parameters.items()
    )
    skill = SkillDefinition(
        skill_id="manipulation.trajectory.simulation-review",
        version=SemanticVersion("1.0.0"),
        name="Future manipulation simulation review",
        description="Inert declarative handoff contract; no runtime endpoint exists.",
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
    registry = SkillRegistry(
        version=SemanticVersion("1.0.0"),
        skills=(skill,),
    )
    return SkillManagerService(registry=registry, safety_kernel=kernel)


@pytest.fixture()
def stage9b_bundle(stage9a_bundle: dict[str, object]) -> dict[str, object]:
    timing = TrajectoryTimingConfiguration()
    request = TrajectoryConstructionRequest(
        stage9a_decision=stage9a_bundle["decision"],
        timing_configuration=timing,
    )
    trajectory = construct_deterministic_trajectory(request)
    evidence = create_trajectory_evidence(request, trajectory)
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
    manager = _manager(kernel, trajectory_safety_review_parameters(evidence))
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
    return {
        **stage9a_bundle,
        "timing": timing,
        "trajectory_request": request,
        "trajectory": trajectory,
        "trajectory_evidence": evidence,
        "proposal": proposal,
        "kernel": kernel,
        "safety_decision": safety_decision,
        "manager": manager,
        "selection": selection,
        "binding": binding,
        "safety_result": safety_result,
        "handoff": handoff,
    }
