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
    create_simulation_execution_request,
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
