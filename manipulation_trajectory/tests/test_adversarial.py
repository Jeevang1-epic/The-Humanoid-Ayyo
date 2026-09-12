from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from ayyo_manipulation_planning import (
    PlanEvidenceStatus,
    evaluate_manipulation_plan,
)
from ayyo_manipulation_trajectory import (
    TrajectoryConstructionRequest,
    TrajectoryFailureCode,
    TrajectoryTimingConfiguration,
    TrajectoryValidationError,
)


def _mutate_stage9a(decision, mutation: str) -> None:
    evidence = decision.plan_evidence
    proof = evidence.collision_proof
    assert proof is not None
    if mutation == "request_substitution":
        object.__setattr__(decision.request, "request_id", "request-sha256-" + "0" * 64)
    elif mutation == "evidence_substitution":
        object.__setattr__(evidence, "plan_evidence_id", "plan-evidence-sha256-" + "0" * 64)
    elif mutation == "proof_substitution":
        object.__setattr__(proof, "proof_id", "moveit-collision-proof-sha256-" + "0" * 64)
    elif mutation == "candidate_path_substitution":
        object.__setattr__(proof, "candidate_path_id", "candidate-path-sha256-" + "0" * 64)
    elif mutation == "waypoint_mutation":
        object.__setattr__(evidence.waypoints[1].positions[0], "position", 0.123)
    elif mutation == "waypoint_reorder":
        object.__setattr__(evidence, "waypoints", tuple(reversed(evidence.waypoints)))
    elif mutation == "waypoint_deletion":
        object.__setattr__(evidence, "waypoints", evidence.waypoints[:-1])
    elif mutation == "waypoint_duplication":
        object.__setattr__(evidence, "waypoints", (evidence.waypoints[0], *evidence.waypoints))
    elif mutation == "joint_order":
        object.__setattr__(decision.request.group, "joint_names", tuple(reversed(
            decision.request.group.joint_names
        )))
    elif mutation == "robot_model":
        object.__setattr__(
            decision.request.robot_model,
            "robot_model_id",
            "robot-model-sha256-" + "0" * 64,
        )
    elif mutation == "joint_limit":
        object.__setattr__(
            decision.request.joint_catalog.chain_joints[0],
            "lower",
            -1.234,
        )
    elif mutation == "stale_decision":
        object.__setattr__(decision, "decision_id", "planning-decision-sha256-" + "0" * 64)
    elif mutation == "collision_positive_as_free":
        object.__setattr__(
            proof,
            "environment_collision_free",
            (False, *proof.environment_collision_free[1:]),
        )
    else:  # pragma: no cover - closed test table
        raise AssertionError(mutation)


@pytest.mark.parametrize(
    "mutation",
    (
        "request_substitution",
        "evidence_substitution",
        "proof_substitution",
        "candidate_path_substitution",
        "waypoint_mutation",
        "waypoint_reorder",
        "waypoint_deletion",
        "waypoint_duplication",
        "joint_order",
        "robot_model",
        "joint_limit",
        "stale_decision",
        "collision_positive_as_free",
    ),
)
def test_any_stage9a_lineage_mutation_fails_before_trajectory(
    stage9a_bundle,
    mutation: str,
) -> None:
    decision = copy.deepcopy(stage9a_bundle["decision"])
    _mutate_stage9a(decision, mutation)
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectoryConstructionRequest(decision, TrajectoryTimingConfiguration())
    assert caught.value.code is TrajectoryFailureCode.UPSTREAM_INTEGRITY


@pytest.mark.parametrize(
    "status",
    (
        PlanEvidenceStatus.START_STATE_COLLISION_REPORTED,
        PlanEvidenceStatus.GOAL_STATE_COLLISION_REPORTED,
        PlanEvidenceStatus.PATH_COLLISION_REPORTED,
        PlanEvidenceStatus.NO_PLAN_REPORTED,
    ),
)
def test_valid_stage9a_rejections_never_create_trajectory_requests(
    stage9a_bundle,
    status,
) -> None:
    rejected_evidence = replace(
        stage9a_bundle["evidence"],
        status=status,
        collision_proof=None,
        waypoints=(),
    )
    rejection = evaluate_manipulation_plan(
        stage9a_bundle["request"],
        rejected_evidence,
    )
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectoryConstructionRequest(rejection, TrajectoryTimingConfiguration())
    assert caught.value.code is TrajectoryFailureCode.UPSTREAM_REJECTED
