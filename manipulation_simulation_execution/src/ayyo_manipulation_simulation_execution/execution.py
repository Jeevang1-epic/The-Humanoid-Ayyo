"""Pure construction and evaluation operations for Stage 9C."""

from __future__ import annotations

from .errors import (
    SimulationExecutionFailureCode,
    SimulationExecutionValidationError,
)
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
    SimulationStabilityObservation,
    StabilityReason,
    StabilityStatus,
    SimulatedJointState,
    SimulatedWholeBodyState,
    expected_goal_points,
    verify_collision_proof,
    verify_controller_state,
    verify_execution_goal,
    verify_execution_observation,
    verify_joint_state,
    verify_preflight_evidence,
    _position_tuple,
    _motion_status,
    _preflight_reasons,
    _stability_reasons,
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

    if not verify_collision_proof(collision_proof):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
            "preflight evaluation requires a verified dense collision proof",
        )
    if not verify_joint_state(start_state):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.START_STATE_MISMATCH,
            "preflight evaluation requires a verified simulated joint state",
        )
    if not verify_controller_state(controller_state):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
            "preflight evaluation requires verified controller evidence",
        )
    try:
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
    except SimulationExecutionValidationError:
        raise
    except (
        AssertionError,
        AttributeError,
        ArithmeticError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
            "preflight evaluation received malformed evidence",
        ) from error


def create_simulation_execution_goal(
    preflight_evidence: SimulationPreflightEvidence,
) -> SimulationExecutionGoal:
    """Create the exact position-only action goal after positive preflight."""

    if not verify_preflight_evidence(preflight_evidence):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
            "execution goal requires recursively verified preflight evidence",
        )
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


def evaluate_whole_body_stability(
    initial_state: SimulatedWholeBodyState,
    final_state: SimulatedWholeBodyState,
    post_controller_state: SimulationControllerState,
    *,
    evaluated_at_ns: int,
) -> SimulationStabilityObservation:
    """Evaluate fresh post-result whole-body and controller observations."""

    from .models import (
        DEFAULT_MAXIMUM_BASE_ROLL_PITCH,
        DEFAULT_MAXIMUM_BASE_TRANSLATION,
        DEFAULT_MAXIMUM_BASE_YAW_CHANGE,
        DEFAULT_MAXIMUM_NON_TARGET_JOINT_DISPLACEMENT,
        DEFAULT_MINIMUM_BASE_HEIGHT,
        verify_whole_body_state,
    )

    if not verify_whole_body_state(initial_state) or not verify_whole_body_state(
        final_state
    ):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.PHYSICAL_OBSERVATION,
            "stability evaluation requires verified whole-body observations",
        )
    if not verify_controller_state(post_controller_state):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
            "stability evaluation requires verified post-result controller evidence",
        )
    try:
        reasons = _stability_reasons(
            initial_state,
            final_state,
            post_controller_state,
            evaluated_at_ns,
            state_freshness_ns=DEFAULT_STATE_FRESHNESS_NS,
            maximum_base_translation=DEFAULT_MAXIMUM_BASE_TRANSLATION,
            maximum_base_roll_pitch=DEFAULT_MAXIMUM_BASE_ROLL_PITCH,
            maximum_base_yaw_change=DEFAULT_MAXIMUM_BASE_YAW_CHANGE,
            maximum_non_target_joint_displacement=(
                DEFAULT_MAXIMUM_NON_TARGET_JOINT_DISPLACEMENT
            ),
            minimum_base_height=DEFAULT_MINIMUM_BASE_HEIGHT,
        )
        return SimulationStabilityObservation(
            initial_state=initial_state,
            final_state=final_state,
            post_controller_state=post_controller_state,
            evaluated_at_ns=evaluated_at_ns,
            status=(
                StabilityStatus.WHOLE_BODY_STABLE
                if reasons == (StabilityReason.WHOLE_BODY_STABLE,)
                else StabilityStatus.REJECTED
            ),
            reasons=reasons,
        )
    except SimulationExecutionValidationError:
        raise
    except (
        AssertionError,
        AttributeError,
        ArithmeticError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.PHYSICAL_OBSERVATION,
            "stability evaluation received malformed physical observations",
        ) from error


def create_simulation_execution_result(
    execution_goal: SimulationExecutionGoal,
    observation: SimulationExecutionObservation,
) -> SimulationExecutionResult:
    """Bind one observed action outcome without escalating its authority."""

    if not verify_execution_goal(execution_goal):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
            "execution result requires a recursively verified goal",
        )
    if not verify_execution_observation(observation):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.FEEDBACK_INVALID,
            "execution result requires a verified observation",
        )
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

    ending = _position_tuple(ending_positions, "ending_positions")
    target = _position_tuple(target_positions, "target_positions")
    return tuple(
        abs(actual - target)
        for actual, target in zip(
            ending,
            target,
            strict=True,
        )
    )
