from __future__ import annotations

from dataclasses import replace

import pytest

from ayyo_manipulation_simulation_execution import (
    PreflightReason,
    PreflightStatus,
    SimulationCollisionProof,
    SimulationControllerState,
    SimulationExecutionFailureCode,
    SimulationExecutionValidationError,
    SimulatedJointState,
    evaluate_simulation_preflight,
)


def test_collision_positive_dense_sample_rejects_preflight(stage9c_bundle) -> None:
    proof = stage9c_bundle["collision_proof"]
    samples = list(proof.samples)
    samples[3] = replace(samples[3], environment_collision_free=False)
    collision = SimulationCollisionProof(
        execution_request=proof.execution_request,
        input_fingerprint=proof.input_fingerprint,
        backend_id=proof.backend_id,
        backend_version=proof.backend_version,
        samples=tuple(samples),
    )
    result = evaluate_simulation_preflight(
        collision,
        stage9c_bundle["state"],
        stage9c_bundle["controller_state"],
        evaluated_at_ns=1_000_000_000,
    )
    assert result.status is PreflightStatus.REJECTED
    assert result.reasons == (PreflightReason.COLLISION_REPORTED,)


def test_simulated_start_state_mismatch_rejects_without_replanning(
    stage9c_bundle,
) -> None:
    state = replace(
        stage9c_bundle["state"],
        positions=(0.02, 0.0, 0.2, 0.0),
    )
    result = evaluate_simulation_preflight(
        stage9c_bundle["collision_proof"],
        state,
        stage9c_bundle["controller_state"],
        evaluated_at_ns=1_000_000_000,
    )
    assert result.status is PreflightStatus.REJECTED
    assert result.reasons == (PreflightReason.START_STATE_MISMATCH,)


def test_stale_start_or_controller_state_rejects(stage9c_bundle) -> None:
    state = replace(stage9c_bundle["state"], observed_at_ns=1)
    result = evaluate_simulation_preflight(
        stage9c_bundle["collision_proof"],
        state,
        stage9c_bundle["controller_state"],
        evaluated_at_ns=1_000_000_000,
    )
    assert result.status is PreflightStatus.REJECTED
    assert result.reasons == (PreflightReason.STATE_STALE,)


@pytest.mark.parametrize(
    "field",
    (
        "controller_active",
        "hardware_active",
        "state_broadcaster_active",
        "action_server_available",
    ),
)
def test_inactive_controller_boundary_rejects(stage9c_bundle, field: str) -> None:
    state = replace(stage9c_bundle["controller_state"], **{field: False})
    result = evaluate_simulation_preflight(
        stage9c_bundle["collision_proof"],
        stage9c_bundle["state"],
        state,
        evaluated_at_ns=1_000_000_000,
    )
    assert result.status is PreflightStatus.REJECTED
    assert result.reasons == (PreflightReason.CONTROLLER_UNAVAILABLE,)


def test_partial_claimed_command_interface_is_malformed(stage9c_bundle) -> None:
    contract = stage9c_bundle["execution_request"].controller_contract
    with pytest.raises(SimulationExecutionValidationError) as caught:
        SimulationControllerState(
            controller_contract_id=contract.controller_contract_id,
            controller_contract_fingerprint=contract.controller_contract_fingerprint,
            controller_active=True,
            hardware_active=True,
            state_broadcaster_active=True,
            action_server_available=True,
            claimed_command_interfaces=("left_shoulder_yaw_joint/position",),
            observed_at_ns=1,
        )
    assert caught.value.code is SimulationExecutionFailureCode.CONTROLLER_MISMATCH


@pytest.mark.parametrize(
    "positions",
    (
        (float("nan"), 0.0, 0.2, 0.0),
        (float("inf"), 0.0, 0.2, 0.0),
        (0.0, 0.0, 0.2),
    ),
)
def test_malformed_simulated_state_is_typed(positions) -> None:
    with pytest.raises(SimulationExecutionValidationError):
        SimulatedJointState(
            joint_names=(
                "left_shoulder_yaw_joint",
                "left_shoulder_pitch_joint",
                "left_elbow_flex_joint",
                "left_wrist_yaw_joint",
            ),
            positions=positions,
            observed_at_ns=1,
            sequence=1,
        )
