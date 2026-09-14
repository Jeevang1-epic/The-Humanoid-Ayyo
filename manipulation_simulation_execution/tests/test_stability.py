from __future__ import annotations

import copy
from dataclasses import replace
from math import cos, sin

import pytest

from ayyo_manipulation_simulation_execution import (
    SimulationExecutionFailureCode,
    SimulationExecutionOutcome,
    SimulationExecutionResultStatus,
    SimulationExecutionValidationError,
    SimulationMotionStatus,
    StabilityReason,
    StabilityStatus,
    create_simulation_execution_result,
    evaluate_whole_body_stability,
)


def _evaluate(bundle, final_state=None, post_controller_state=None):
    return evaluate_whole_body_stability(
        bundle["initial_whole_body_state"],
        bundle["final_whole_body_state"] if final_state is None else final_state,
        (
            bundle["post_controller_state"]
            if post_controller_state is None
            else post_controller_state
        ),
        evaluated_at_ns=3_500_000_000,
    )


def _with_base(bundle, *, position=None, orientation=None):
    final = bundle["final_whole_body_state"]
    base = replace(
        final.base_pose,
        position_xyz=final.base_pose.position_xyz if position is None else position,
        orientation_xyzw=(
            final.base_pose.orientation_xyzw if orientation is None else orientation
        ),
    )
    return replace(final, base_pose=base)


def test_valid_reviewed_execution_has_fresh_stable_whole_body_evidence(
    stage9c_bundle,
) -> None:
    stability = stage9c_bundle["stability_observation"]
    result = stage9c_bundle["result"]
    assert stability.status is StabilityStatus.WHOLE_BODY_STABLE
    assert stability.reasons == (StabilityReason.WHOLE_BODY_STABLE,)
    assert result.status is SimulationExecutionResultStatus.COMPLETED
    assert result.motion_status is SimulationMotionStatus.SIMULATION_EXECUTED


def test_action_success_alone_cannot_produce_success(stage9c_bundle) -> None:
    with pytest.raises(SimulationExecutionValidationError) as caught:
        replace(stage9c_bundle["observation"], stability_observation=None)
    assert caught.value.code is SimulationExecutionFailureCode.FEEDBACK_INVALID


def test_whole_body_collapse_is_failure_even_after_action_success(
    stage9c_bundle,
) -> None:
    collapsed = _with_base(stage9c_bundle, position=(0.25, 0.0, 0.20))
    stability = _evaluate(stage9c_bundle, collapsed)
    assert stability.status is StabilityStatus.REJECTED
    assert StabilityReason.BASE_TRANSLATION_EXCEEDED in stability.reasons
    assert StabilityReason.BASE_HEIGHT_INVALID in stability.reasons
    observation = replace(
        stage9c_bundle["observation"],
        outcome=SimulationExecutionOutcome.WHOLE_BODY_STABILITY_VIOLATED,
        stability_observation=stability,
    )
    result = create_simulation_execution_result(
        stage9c_bundle["execution_goal"],
        observation,
    )
    assert result.status is SimulationExecutionResultStatus.FAILED
    assert result.motion_status is SimulationMotionStatus.ATTEMPTED


def test_unexpected_base_translation_is_rejected(stage9c_bundle) -> None:
    moved = _with_base(stage9c_bundle, position=(0.006, 0.0, 0.95))
    assert StabilityReason.BASE_TRANSLATION_EXCEEDED in _evaluate(
        stage9c_bundle, moved
    ).reasons


def test_unexpected_base_roll_pitch_is_rejected(stage9c_bundle) -> None:
    angle = 0.011
    tilted = _with_base(
        stage9c_bundle,
        orientation=(sin(angle / 2.0), 0.0, 0.0, cos(angle / 2.0)),
    )
    assert StabilityReason.BASE_ROLL_PITCH_EXCEEDED in _evaluate(
        stage9c_bundle, tilted
    ).reasons


def test_non_target_motion_is_rejected(stage9c_bundle) -> None:
    final = stage9c_bundle["final_whole_body_state"]
    positions = list(final.positions)
    positions[0] += 0.011
    moved = replace(final, positions=tuple(positions))
    assert StabilityReason.NON_TARGET_JOINT_MOTION in _evaluate(
        stage9c_bundle, moved
    ).reasons


def test_stale_post_result_joint_state_is_rejected(stage9c_bundle) -> None:
    stale = replace(
        stage9c_bundle["final_whole_body_state"],
        observed_at_ns=1_000_000_000,
        sequence=1,
    )
    assert StabilityReason.POST_STATE_STALE in _evaluate(
        stage9c_bundle, stale
    ).reasons


def test_controller_must_remain_active_after_result(stage9c_bundle) -> None:
    inactive = replace(
        stage9c_bundle["post_controller_state"],
        controller_active=False,
    )
    assert StabilityReason.CONTROLLER_NOT_READY in _evaluate(
        stage9c_bundle,
        post_controller_state=inactive,
    ).reasons


def test_malformed_physical_observation_fails_with_typed_error(
    stage9c_bundle,
) -> None:
    malformed = copy.copy(stage9c_bundle["final_whole_body_state"])
    malformed_base = copy.copy(malformed.base_pose)
    object.__setattr__(malformed_base, "orientation_xyzw", (0.0, 0.0, 1.0))
    object.__setattr__(malformed, "base_pose", malformed_base)
    with pytest.raises(SimulationExecutionValidationError) as caught:
        _evaluate(stage9c_bundle, malformed)
    assert caught.value.code is SimulationExecutionFailureCode.PHYSICAL_OBSERVATION
