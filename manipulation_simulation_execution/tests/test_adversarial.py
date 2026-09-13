from __future__ import annotations

import copy
from dataclasses import replace
from math import inf, nan

import pytest

from ayyo_manipulation_simulation_execution import (
    GoalAcceptance,
    SimulationExecutionObservation,
    SimulationExecutionOutcome,
    SimulationExecutionValidationError,
    create_simulation_execution_goal,
    create_simulation_execution_request,
    create_simulation_execution_result,
    evaluate_simulation_preflight,
    observed_final_errors,
    verify_execution_request,
)


def test_stale_nested_safety_policy_is_not_trusted(stage9c_bundle) -> None:
    handoff = copy.copy(stage9c_bundle["handoff"])
    safety_result = copy.copy(handoff.safety_result)
    decision = copy.copy(safety_result.source_safety_decision)
    object.__setattr__(decision, "policy_fingerprint", "policy-content-sha256-" + "0" * 64)
    object.__setattr__(safety_result, "source_safety_decision", decision)
    object.__setattr__(handoff, "safety_result", safety_result)
    with pytest.raises(SimulationExecutionValidationError):
        create_simulation_execution_request(handoff)


def test_mutated_nested_trajectory_is_not_trusted(stage9c_bundle) -> None:
    request = copy.copy(stage9c_bundle["execution_request"])
    handoff = copy.copy(request.stage9b_handoff)
    safety_result = copy.copy(handoff.safety_result)
    evidence = copy.copy(safety_result.trajectory_evidence)
    trajectory = copy.copy(evidence.trajectory)
    points = list(trajectory.points)
    point = copy.copy(points[-1])
    positions = list(point.positions)
    positions[0] = replace(positions[0], position=positions[0].position + 0.1)
    object.__setattr__(point, "positions", tuple(positions))
    points[-1] = point
    object.__setattr__(trajectory, "points", tuple(points))
    object.__setattr__(evidence, "trajectory", trajectory)
    object.__setattr__(safety_result, "trajectory_evidence", evidence)
    object.__setattr__(handoff, "safety_result", safety_result)
    object.__setattr__(request, "stage9b_handoff", handoff)
    assert not verify_execution_request(request)


@pytest.mark.parametrize("value", (nan, inf, -inf))
def test_nonfinite_observation_positions_fail_closed(stage9c_bundle, value: float) -> None:
    observation = stage9c_bundle["observation"]
    ending = list(observation.ending_positions)
    ending[0] = value
    with pytest.raises(SimulationExecutionValidationError):
        replace(observation, ending_positions=tuple(ending))


def test_success_cannot_claim_cancellation(stage9c_bundle) -> None:
    observation = stage9c_bundle["observation"]
    with pytest.raises(SimulationExecutionValidationError):
        replace(
            observation,
            acceptance=GoalAcceptance.ACCEPTED,
            outcome=SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED,
            cancellation_requested=True,
            cancellation_confirmed=True,
        )


def test_malformed_exact_type_contract_does_not_leak_assertion(stage9c_bundle) -> None:
    request = copy.copy(stage9c_bundle["execution_request"])
    object.__setattr__(request, "controller_contract", None)
    assert not verify_execution_request(request)
    handoff = copy.copy(request.stage9b_handoff)
    object.__setattr__(handoff, "safety_result", None)
    with pytest.raises(SimulationExecutionValidationError):
        create_simulation_execution_request(handoff)


@pytest.mark.parametrize("field", ("collision", "state", "controller", "timestamp"))
def test_malformed_public_preflight_input_is_typed(stage9c_bundle, field: str) -> None:
    arguments = {
        "collision_proof": stage9c_bundle["collision_proof"],
        "start_state": stage9c_bundle["state"],
        "controller_state": stage9c_bundle["controller_state"],
        "evaluated_at_ns": 1_000_000_000,
    }
    names = {
        "collision": "collision_proof",
        "state": "start_state",
        "controller": "controller_state",
        "timestamp": "evaluated_at_ns",
    }
    arguments[names[field]] = None
    with pytest.raises(SimulationExecutionValidationError):
        evaluate_simulation_preflight(**arguments)


def test_malformed_public_goal_and_result_inputs_are_typed(stage9c_bundle) -> None:
    with pytest.raises(SimulationExecutionValidationError):
        create_simulation_execution_goal(None)
    with pytest.raises(SimulationExecutionValidationError):
        create_simulation_execution_result(None, stage9c_bundle["observation"])
    with pytest.raises(SimulationExecutionValidationError):
        create_simulation_execution_result(stage9c_bundle["execution_goal"], None)


@pytest.mark.parametrize(
    "ending,target",
    (
        (None, (0.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, float("nan"), 0.0)),
    ),
)
def test_malformed_public_error_derivation_is_typed(ending, target) -> None:
    with pytest.raises(SimulationExecutionValidationError):
        observed_final_errors(ending, target)


def _isolated_handoff_lineage(stage9c_bundle):
    """Copy only the immutable lineage path targeted by mutation probes."""
    source = stage9c_bundle["handoff"]
    handoff = copy.copy(source)
    safety = copy.copy(source.safety_result)
    evidence = copy.copy(safety.trajectory_evidence)
    trajectory = copy.copy(evidence.trajectory)
    trajectory_request = copy.copy(trajectory.request)
    decision = copy.copy(trajectory_request.stage9a_decision)
    planning = copy.copy(decision.request)
    plan_evidence = copy.copy(decision.plan_evidence)

    object.__setattr__(planning, "robot_model", copy.copy(planning.robot_model))
    object.__setattr__(planning, "group", copy.copy(planning.group))
    object.__setattr__(planning, "scene", copy.copy(planning.scene))
    object.__setattr__(plan_evidence, "request", planning)
    object.__setattr__(
        plan_evidence,
        "collision_proof",
        copy.copy(plan_evidence.collision_proof),
    )
    object.__setattr__(decision, "request", planning)
    object.__setattr__(decision, "plan_evidence", plan_evidence)
    object.__setattr__(trajectory_request, "stage9a_decision", decision)
    points = tuple(copy.copy(point) for point in trajectory.points)
    for point in points:
        object.__setattr__(
            point,
            "positions",
            tuple(copy.copy(position) for position in point.positions),
        )
    object.__setattr__(trajectory, "request", trajectory_request)
    object.__setattr__(trajectory, "points", points)
    object.__setattr__(evidence, "request", trajectory_request)
    object.__setattr__(evidence, "trajectory", trajectory)
    object.__setattr__(safety, "trajectory_evidence", evidence)
    object.__setattr__(safety, "safety_reference", copy.copy(safety.safety_reference))
    object.__setattr__(handoff, "safety_result", safety)
    object.__setattr__(
        handoff,
        "skill_handoff_reference",
        copy.copy(handoff.skill_handoff_reference),
    )
    return handoff


@pytest.mark.parametrize(
    "mutation",
    (
        "handoff_semantics",
        "trajectory_joints_reordered",
        "trajectory_joint_missing",
        "trajectory_fixed_joint",
        "trajectory_right_arm_joint",
        "trajectory_timestamp",
        "trajectory_position",
        "trajectory_point_count",
        "robot_model",
        "manipulator_group",
        "planning_scene",
        "stage9a_collision_proof",
        "safety_reference",
        "skill_reference",
    ),
)
def test_substituted_stage9b_lineage_fails_before_stage9c_request(
    stage9c_bundle,
    mutation: str,
) -> None:
    handoff = _isolated_handoff_lineage(stage9c_bundle)
    trajectory = handoff.safety_result.trajectory_evidence.trajectory
    planning = trajectory.request.stage9a_decision.request
    if mutation == "handoff_semantics":
        object.__setattr__(handoff, "execution_disposition", None)
    elif mutation == "trajectory_joints_reordered":
        object.__setattr__(trajectory, "joint_names", tuple(reversed(trajectory.joint_names)))
    elif mutation == "trajectory_joint_missing":
        object.__setattr__(trajectory, "joint_names", trajectory.joint_names[:-1])
    elif mutation == "trajectory_fixed_joint":
        object.__setattr__(
            trajectory,
            "joint_names",
            (*trajectory.joint_names[:-1], "left_hand_fixed_joint"),
        )
    elif mutation == "trajectory_right_arm_joint":
        object.__setattr__(
            trajectory,
            "joint_names",
            (*trajectory.joint_names[:-1], "right_wrist_yaw_joint"),
        )
    elif mutation == "trajectory_timestamp":
        object.__setattr__(
            trajectory.points[-1],
            "time_from_start",
            trajectory.points[-2].time_from_start,
        )
    elif mutation == "trajectory_position":
        object.__setattr__(trajectory.points[-1].positions[0], "position", 100.0)
    elif mutation == "trajectory_point_count":
        object.__setattr__(trajectory, "points", trajectory.points[:-1])
    elif mutation == "robot_model":
        object.__setattr__(planning.robot_model, "robot_name", "substituted")
    elif mutation == "manipulator_group":
        object.__setattr__(
            planning.group,
            "joint_names",
            tuple(reversed(planning.group.joint_names)),
        )
    elif mutation == "planning_scene":
        object.__setattr__(planning.scene, "frame_id", "substituted_link")
    elif mutation == "stage9a_collision_proof":
        object.__setattr__(
            trajectory.request.stage9a_decision.plan_evidence.collision_proof,
            "limits_match_reviewed",
            False,
        )
    elif mutation == "safety_reference":
        object.__setattr__(
            handoff.safety_result.safety_reference,
            "source_policy_fingerprint",
            "policy:sha256:" + "0" * 64,
        )
    elif mutation == "skill_reference":
        object.__setattr__(
            handoff.skill_handoff_reference,
            "skill_fingerprint",
            "skill:sha256:" + "0" * 64,
        )
    with pytest.raises(SimulationExecutionValidationError):
        create_simulation_execution_request(handoff)
