from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from ayyo_manipulation_simulation_execution import (
    GoalAcceptance,
    HardwareAuthority,
    PhysicalValidationClaim,
    PreflightReason,
    PreflightStatus,
    ProductionRuntimeAuthority,
    SimulationAuthority,
    SimulationControllerContract,
    SimulationExecutionFailureCode,
    SimulationExecutionObservation,
    SimulationExecutionOutcome,
    SimulationExecutionResultStatus,
    SimulationExecutionValidationError,
    SimulationMotionStatus,
    create_simulation_execution_goal,
    create_simulation_execution_request,
    expected_dense_samples,
    verify_collision_proof,
    verify_controller_contract,
    verify_execution_goal,
    verify_execution_request,
    verify_execution_result,
    verify_preflight_evidence,
)


def test_positive_chain_has_only_simulation_authority(stage9c_bundle) -> None:
    request = stage9c_bundle["execution_request"]
    preflight = stage9c_bundle["preflight"]
    result = stage9c_bundle["result"]
    assert verify_execution_request(request)
    assert verify_preflight_evidence(preflight)
    assert verify_execution_result(result)
    assert request.authority is SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    assert request.physical_validation is PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
    assert request.hardware_authority is HardwareAuthority.NO_HARDWARE_AUTHORITY
    assert request.production_runtime_authority is (
        ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
    )
    assert preflight.status is PreflightStatus.READY_FOR_SIMULATION_EXECUTION
    assert preflight.reasons == (
        PreflightReason.COLLISION_FREE_DENSE_PATH,
        PreflightReason.CONTROLLER_READY,
        PreflightReason.START_STATE_MATCHED,
    )
    assert result.status is SimulationExecutionResultStatus.COMPLETED
    assert result.motion_status is SimulationMotionStatus.SIMULATION_EXECUTED


def test_controller_contract_is_exact_and_partial_goals_are_forbidden() -> None:
    contract = SimulationControllerContract()
    assert verify_controller_contract(contract)
    with pytest.raises(SimulationExecutionValidationError) as caught:
        replace(contract, allow_partial_joints_goal=True)
    assert caught.value.code is SimulationExecutionFailureCode.CONTROLLER_MISMATCH


@pytest.mark.parametrize(
    "field,value",
    (
        ("controller_name", "another_controller"),
        ("action_endpoint", "/another/follow_joint_trajectory"),
        ("joint_names", ("left_shoulder_yaw_joint",) * 4),
        ("simulation_mode", False),
        ("manipulation_control_enabled", False),
        ("base_pose_topic", "/unreviewed/base_pose"),
    ),
)
def test_controller_substitution_fails_closed(field: str, value: object) -> None:
    with pytest.raises(SimulationExecutionValidationError):
        replace(SimulationControllerContract(), **{field: value})


def test_dense_sampling_is_bounded_and_includes_every_stage9b_endpoint(
    stage9c_bundle,
) -> None:
    request = stage9c_bundle["execution_request"]
    samples = expected_dense_samples(request)
    trajectory_positions = tuple(
        tuple(item.position for item in point.positions)
        for point in request.trajectory.points
    )
    assert len(samples) > len(trajectory_positions)
    assert len(samples) <= request.sampling_policy.maximum_total_samples
    for endpoint in trajectory_positions:
        assert endpoint in tuple(sample.positions for sample in samples)
    assert samples[0].positions == trajectory_positions[0]
    assert samples[-1].positions == trajectory_positions[-1]


def test_collision_mutation_invalidates_recursive_proof(stage9c_bundle) -> None:
    proof = copy.copy(stage9c_bundle["collision_proof"])
    samples = list(proof.samples)
    samples[1] = copy.copy(samples[1])
    object.__setattr__(samples[1], "positions", samples[0].positions)
    object.__setattr__(proof, "samples", tuple(samples))
    assert not verify_collision_proof(proof)


def test_rejected_preflight_cannot_create_goal(stage9c_bundle) -> None:
    preflight = copy.copy(stage9c_bundle["preflight"])
    object.__setattr__(preflight, "status", PreflightStatus.REJECTED)
    with pytest.raises(SimulationExecutionValidationError) as caught:
        create_simulation_execution_goal(preflight)
    assert caught.value.code is SimulationExecutionFailureCode.COLLISION_PREFLIGHT


def test_goal_maps_exact_stage9b_positions_and_times(stage9c_bundle) -> None:
    goal = stage9c_bundle["execution_goal"]
    trajectory = stage9c_bundle["trajectory"]
    assert verify_execution_goal(goal)
    assert goal.joint_names == trajectory.joint_names
    assert tuple(point.time_from_start for point in goal.points) == tuple(
        point.time_from_start for point in trajectory.points
    )
    assert tuple(point.positions for point in goal.points) == tuple(
        tuple(item.position for item in point.positions)
        for point in trajectory.points
    )


def test_forged_success_without_feedback_is_rejected(stage9c_bundle) -> None:
    goal = stage9c_bundle["execution_goal"]
    with pytest.raises(SimulationExecutionValidationError) as caught:
        SimulationExecutionObservation(
            execution_goal_id=goal.execution_goal_id,
            execution_goal_fingerprint=goal.execution_goal_fingerprint,
            acceptance=GoalAcceptance.ACCEPTED,
            outcome=SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED,
            controller_error_code=0,
            started_at_ns=1,
            completed_at_ns=2,
            starting_positions=goal.preflight_evidence.start_state.positions,
            ending_positions=None,
            final_target_positions=goal.points[-1].positions,
            final_joint_errors=None,
            feedback_samples_observed=0,
            cancellation_requested=False,
            cancellation_confirmed=False,
            timed_out=False,
            detail="Forged success.",
        )
    assert caught.value.code is SimulationExecutionFailureCode.FEEDBACK_INVALID


def test_timeout_requires_cancellation_request(stage9c_bundle) -> None:
    observation = stage9c_bundle["observation"]
    with pytest.raises(SimulationExecutionValidationError) as caught:
        replace(
            observation,
            outcome=SimulationExecutionOutcome.TIMED_OUT,
            timed_out=True,
            cancellation_requested=False,
            ending_positions=None,
            final_joint_errors=None,
            controller_error_code=0,
        )
    assert caught.value.code is SimulationExecutionFailureCode.EXECUTION_TIMEOUT


def test_nonpositive_stage9b_handoff_is_rejected(stage9c_bundle) -> None:
    handoff = copy.copy(stage9c_bundle["handoff"])
    object.__setattr__(handoff, "status", handoff.status.__class__.INELIGIBLE)
    with pytest.raises(SimulationExecutionValidationError) as caught:
        create_simulation_execution_request(handoff)
    assert caught.value.code is SimulationExecutionFailureCode.UPSTREAM_INTEGRITY
