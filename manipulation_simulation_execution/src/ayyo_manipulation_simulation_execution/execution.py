"""Pure construction and evaluation operations for Stage 9C."""

from __future__ import annotations

from .models import (
    DEFAULT_EXECUTION_TIMEOUT_MARGIN_NS,
    DEFAULT_START_TOLERANCE,
    DEFAULT_STATE_FRESHNESS_NS,
    CollisionSamplingPolicy,
    PreflightReason,
    PreflightStatus,
    SimulationCollisionProof,
    SimulationControllerContract,
    SimulationControllerState,
    SimulationExecutionGoal,
    SimulationExecutionObservation,
    SimulationExecutionRequest,
    SimulationExecutionResult,
    SimulationExecutionResultStatus,
    SimulationExecutionOutcome,
    SimulationPreflightEvidence,
    SimulatedJointState,
    expected_goal_points,
    _motion_status,
    _preflight_reasons,
)


def create_simulation_execution_request(
    stage9b_handoff,
    *,
    controller_contract: SimulationControllerContract | None = None,
    sampling_policy: CollisionSamplingPolicy | None = None,
) -> SimulationExecutionRequest:
    """Bind one exact positive Stage 9B handoff to the fixed Stage 9C profile."""

    return SimulationExecutionRequest(
        stage9b_handoff=stage9b_handoff,
        controller_contract=(
            SimulationControllerContract()
            if controller_contract is None
            else controller_contract
        ),
        sampling_policy=(
            CollisionSamplingPolicy() if sampling_policy is None else sampling_policy
        ),
    )


def evaluate_simulation_preflight(
    collision_proof: SimulationCollisionProof,
    start_state: SimulatedJointState,
    controller_state: SimulationControllerState,
    *,
    evaluated_at_ns: int,
) -> SimulationPreflightEvidence:
    """Evaluate collision, lifecycle, freshness, and exact-start evidence."""

    provisional = _preflight_reasons(
        collision_proof,
        start_state,
        controller_state,
        evaluated_at_ns,
        start_tolerance=DEFAULT_START_TOLERANCE,
        state_freshness_ns=DEFAULT_STATE_FRESHNESS_NS,
    )
    positive = provisional == (
        PreflightReason.COLLISION_FREE_DENSE_PATH,
        PreflightReason.CONTROLLER_READY,
        PreflightReason.START_STATE_MATCHED,
    )
    return SimulationPreflightEvidence(
        collision_proof=collision_proof,
        start_state=start_state,
        controller_state=controller_state,
        evaluated_at_ns=evaluated_at_ns,
        status=(
            PreflightStatus.READY_FOR_SIMULATION_EXECUTION
            if positive
            else PreflightStatus.REJECTED
        ),
        reasons=provisional,
    )


def create_simulation_execution_goal(
    preflight_evidence: SimulationPreflightEvidence,
) -> SimulationExecutionGoal:
    """Create the exact position-only action goal after positive preflight."""

    request = preflight_evidence.execution_request
    points = expected_goal_points(request)
    timeout_ns = round(points[-1].time_from_start * 1_000_000_000) + (
        DEFAULT_EXECUTION_TIMEOUT_MARGIN_NS
    )
    return SimulationExecutionGoal(
        preflight_evidence=preflight_evidence,
        action_endpoint=request.controller_contract.action_endpoint,
        joint_names=request.controller_contract.joint_names,
        points=points,
        execution_timeout_ns=timeout_ns,
    )


def create_simulation_execution_result(
    execution_goal: SimulationExecutionGoal,
    observation: SimulationExecutionObservation,
) -> SimulationExecutionResult:
    """Bind one observed action outcome without escalating its authority."""

    completed = (
        observation.outcome
        is SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
    )
    return SimulationExecutionResult(
        execution_goal=execution_goal,
        observation=observation,
        status=(
            SimulationExecutionResultStatus.COMPLETED
            if completed
            else SimulationExecutionResultStatus.FAILED
        ),
        motion_status=_motion_status(observation),
    )


def observed_final_errors(
    ending_positions: tuple[float, ...],
    target_positions: tuple[float, ...],
) -> tuple[float, ...]:
    """Derive bounded final absolute error without fabricating feedback."""

    return tuple(
        abs(actual - target)
        for actual, target in zip(
            ending_positions,
            target_positions,
            strict=True,
        )
    )
