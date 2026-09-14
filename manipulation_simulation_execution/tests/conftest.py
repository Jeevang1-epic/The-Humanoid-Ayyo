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
from ayyo_manipulation_simulation_execution import (
    GoalAcceptance,
    SimulationCollisionProof,
    SimulationControllerState,
    SimulationExecutionObservation,
    SimulationExecutionOutcome,
    SimulatedBasePose,
    SimulatedJointState,
    SimulatedWholeBodyState,
    STAGE9C_WHOLE_BODY_JOINT_NAMES,
    create_simulation_execution_goal,
    create_simulation_execution_request,
    create_simulation_execution_result,
    evaluate_simulation_preflight,
    evaluate_whole_body_stability,
    expected_dense_samples,
    observed_final_errors,
    preflight_input_fingerprint,
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
XACRO_PATH = REPOSITORY_ROOT / "ros2_ws/src/ayyo_description/urdf/ayyo.urdf.xacro"
SRDF_PATH = REPOSITORY_ROOT / "ros2_ws/src/ayyo_manipulation_planning/config/ayyo_left_arm.srdf"


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
    return SkillManagerService(
        registry=SkillRegistry(version=SemanticVersion("1.0.0"), skills=(skill,)),
        safety_kernel=kernel,
    )


@pytest.fixture(scope="session")
def _stage9c_base(expanded_urdf: str, reviewed_srdf: str) -> dict[str, object]:
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
    planning_request = ManipulationPlanningRequest(
        robot_model=model,
        joint_catalog=catalog,
        group=group,
        collision_model=collision_model,
        start_state=start,
        goal=goal,
        scene=scene,
        planner_configuration=default_planner_configuration(),
    )
    waypoints = deterministic_joint_interpolation(planning_request)
    stage9a_proof = MoveItCollisionProof(
        request_id=planning_request.request_id,
        request_fingerprint=planning_request.request_fingerprint,
        collision_model_id=collision_model.collision_model_id,
        collision_model_fingerprint=collision_model.collision_model_fingerprint,
        planner_configuration_id=planning_request.planner_configuration.configuration_id,
        planner_configuration_fingerprint=planning_request.planner_configuration.configuration_fingerprint,
        robot_description_content_fingerprint=collision_model.robot_description_content_fingerprint,
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
    stage9a_evidence = ManipulationPlanEvidence(
        request=planning_request,
        status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
        collision_proof=stage9a_proof,
        backend_version="moveit-2.12.4",
        planner_seed=0,
        waypoints=waypoints,
        checked_collision_object_ids=(box.object_id,),
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
    trajectory_evidence = create_trajectory_evidence(trajectory_request, trajectory)
    proposal = _proposal(trajectory_evidence)
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
    manager = _manager(kernel, trajectory_safety_review_parameters(trajectory_evidence))
    selection = manager.registry.selection(
        skill_id="manipulation.trajectory.simulation-review",
        capability_id=SAFETY_REVIEW_CAPABILITY_ID,
        source_step_id=SAFETY_REVIEW_STEP_ID,
    )
    binding = manager.bind(proposal, safety_decision, selection)
    safety_result = evaluate_trajectory_safety_eligibility(
        trajectory_evidence,
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
    execution_request = create_simulation_execution_request(handoff)
    samples = expected_dense_samples(execution_request)
    collision_proof = SimulationCollisionProof(
        execution_request=execution_request,
        input_fingerprint=preflight_input_fingerprint(execution_request),
        backend_id="moveit.planning-scene.stage9c-preflight.v1",
        backend_version="moveit-2.12.4",
        samples=samples,
    )
    start_positions = tuple(item.position for item in trajectory.points[0].positions)
    state = SimulatedJointState(
        joint_names=trajectory.joint_names,
        positions=start_positions,
        observed_at_ns=1_000_000_000,
        sequence=1,
    )
    contract = execution_request.controller_contract
    controller_state = SimulationControllerState(
        controller_contract_id=contract.controller_contract_id,
        controller_contract_fingerprint=contract.controller_contract_fingerprint,
        controller_active=True,
        hardware_active=True,
        state_broadcaster_active=True,
        action_server_available=True,
        support_fixture_active=True,
        base_pose_observable=True,
        claimed_command_interfaces=tuple(
            f"{name}/position" for name in trajectory.joint_names
        ),
        observed_at_ns=1_000_000_000,
    )
    preflight = evaluate_simulation_preflight(
        collision_proof,
        state,
        controller_state,
        evaluated_at_ns=1_000_000_000,
    )
    execution_goal = create_simulation_execution_goal(preflight)
    target = execution_goal.points[-1].positions
    initial_positions_by_name = {
        name: 0.0 for name in STAGE9C_WHOLE_BODY_JOINT_NAMES
    }
    initial_positions_by_name.update(dict(zip(trajectory.joint_names, start_positions)))
    initial_whole_body_state = SimulatedWholeBodyState(
        joint_names=STAGE9C_WHOLE_BODY_JOINT_NAMES,
        positions=tuple(
            initial_positions_by_name[name] for name in STAGE9C_WHOLE_BODY_JOINT_NAMES
        ),
        observed_at_ns=1_000_000_000,
        sequence=1,
        base_pose=SimulatedBasePose(
            position_xyz=(0.0, 0.0, 0.95),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            observed_at_ns=1_000_000_000,
            sequence=1,
        ),
    )
    final_positions_by_name = dict(initial_positions_by_name)
    final_positions_by_name.update(dict(zip(trajectory.joint_names, target)))
    final_whole_body_state = SimulatedWholeBodyState(
        joint_names=STAGE9C_WHOLE_BODY_JOINT_NAMES,
        positions=tuple(
            final_positions_by_name[name] for name in STAGE9C_WHOLE_BODY_JOINT_NAMES
        ),
        observed_at_ns=3_400_000_000,
        sequence=2,
        base_pose=SimulatedBasePose(
            position_xyz=(0.0, 0.0, 0.95),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            observed_at_ns=3_400_000_000,
            sequence=2,
        ),
    )
    post_controller_state = SimulationControllerState(
        controller_contract_id=contract.controller_contract_id,
        controller_contract_fingerprint=contract.controller_contract_fingerprint,
        controller_active=True,
        hardware_active=True,
        state_broadcaster_active=True,
        action_server_available=True,
        support_fixture_active=True,
        base_pose_observable=True,
        claimed_command_interfaces=tuple(
            f"{name}/position" for name in trajectory.joint_names
        ),
        observed_at_ns=3_400_000_000,
    )
    stability_observation = evaluate_whole_body_stability(
        initial_whole_body_state,
        final_whole_body_state,
        post_controller_state,
        evaluated_at_ns=3_500_000_000,
    )
    observation = SimulationExecutionObservation(
        execution_goal_id=execution_goal.execution_goal_id,
        execution_goal_fingerprint=execution_goal.execution_goal_fingerprint,
        acceptance=GoalAcceptance.ACCEPTED,
        outcome=SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED,
        controller_error_code=0,
        started_at_ns=1_100_000_000,
        completed_at_ns=3_500_000_000,
        starting_positions=start_positions,
        ending_positions=target,
        final_target_positions=target,
        final_joint_errors=observed_final_errors(target, target),
        feedback_samples_observed=10,
        cancellation_requested=False,
        cancellation_confirmed=False,
        timed_out=False,
        detail="Simulation action completed with bounded final feedback.",
        stability_observation=stability_observation,
    )
    result = create_simulation_execution_result(execution_goal, observation)
    return {
        "expanded_urdf": expanded_urdf,
        "reviewed_srdf": reviewed_srdf,
        "planning_request": planning_request,
        "stage9a_decision": stage9a_decision,
        "trajectory": trajectory,
        "proposal": proposal,
        "kernel": kernel,
        "safety_decision": safety_decision,
        "manager": manager,
        "binding": binding,
        "handoff": handoff,
        "execution_request": execution_request,
        "collision_proof": collision_proof,
        "state": state,
        "controller_state": controller_state,
        "initial_whole_body_state": initial_whole_body_state,
        "final_whole_body_state": final_whole_body_state,
        "post_controller_state": post_controller_state,
        "stability_observation": stability_observation,
        "preflight": preflight,
        "execution_goal": execution_goal,
        "observation": observation,
        "result": result,
    }


@pytest.fixture()
def stage9c_bundle(_stage9c_base: dict[str, object]) -> dict[str, object]:
    return dict(_stage9c_base)
