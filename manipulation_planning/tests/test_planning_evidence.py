from __future__ import annotations

from dataclasses import replace

import pytest

from ayyo_manipulation_planning import (
    CollisionBox,
    ExecutionDisposition,
    ManipulationPlanEvidence,
    ManipulationPlanningDecision,
    ManipulationPlanningRequest,
    PlanEvidenceStatus,
    PlanningDecisionReason,
    PlanningDisposition,
    PlanningSceneEvidence,
    PlanningValidationError,
    deterministic_joint_interpolation,
    evaluate_manipulation_plan,
    verify_manipulation_plan_evidence,
    verify_manipulation_planning_request,
)


def test_collision_free_evidence_is_only_available_for_review(planning_bundle):
    *_, request, evidence = planning_bundle
    decision = evaluate_manipulation_plan(request, evidence)

    assert decision.disposition is PlanningDisposition.PLAN_AVAILABLE_FOR_REVIEW
    assert decision.execution_disposition is ExecutionDisposition.NOT_EXECUTED
    assert PlanningDecisionReason.EXECUTION_OUT_OF_SCOPE in decision.reasons
    assert PlanningDecisionReason.PHYSICAL_VALIDATION_ABSENT in decision.reasons


def test_interpolation_is_deterministic_bounded_and_exact(planning_bundle):
    *_, request, _ = planning_bundle
    first = deterministic_joint_interpolation(request)
    second = deterministic_joint_interpolation(request)

    assert first == second
    assert 2 <= len(first) <= request.planner_configuration.max_waypoints
    assert first[0] == request.start_state
    assert first[-1].positions == request.goal.positions


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (PlanEvidenceStatus.START_STATE_COLLISION_REPORTED, PlanningDecisionReason.START_STATE_COLLISION),
        (PlanEvidenceStatus.GOAL_STATE_COLLISION_REPORTED, PlanningDecisionReason.GOAL_STATE_COLLISION),
        (PlanEvidenceStatus.PATH_COLLISION_REPORTED, PlanningDecisionReason.PATH_COLLISION),
        (PlanEvidenceStatus.NO_PLAN_REPORTED, PlanningDecisionReason.NO_PLAN_FOUND),
    ],
)
def test_negative_evidence_stays_rejected(planning_bundle, status, reason):
    *_, request, evidence = planning_bundle
    rejected = replace(evidence, status=status, waypoints=())
    decision = evaluate_manipulation_plan(request, rejected)
    assert decision.disposition is PlanningDisposition.REJECTED
    assert reason in decision.reasons
    assert decision.execution_disposition is ExecutionDisposition.NOT_EXECUTED


def test_evidence_request_substitution_is_rejected(planning_bundle):
    *_, request, evidence = planning_bundle
    alternate = replace(request, goal=replace(request.goal, positions=(
        replace(request.goal.positions[0], position=0.4),
        *request.goal.positions[1:],
    )))
    with pytest.raises(PlanningValidationError):
        evaluate_manipulation_plan(alternate, evidence)


def test_waypoint_group_identity_substitution_is_rejected(planning_bundle):
    *_, evidence = planning_bundle
    malicious = replace(evidence.waypoints[1], group_id="group-sha256-" + ("0" * 64))
    with pytest.raises(PlanningValidationError):
        replace(evidence, waypoints=(evidence.waypoints[0], malicious, *evidence.waypoints[2:]))


def test_scene_robot_identity_substitution_is_rejected(planning_bundle):
    *_, request, _ = planning_bundle
    scene = replace(request.scene, robot_model_id="model-sha256-" + ("0" * 64))
    with pytest.raises(PlanningValidationError):
        replace(request, scene=scene)


def test_collision_object_set_substitution_is_rejected(planning_bundle):
    *_, evidence = planning_bundle
    with pytest.raises(PlanningValidationError):
        replace(evidence, checked_collision_object_ids=())


def test_collision_free_status_cannot_carry_collisions(planning_bundle):
    *_, evidence = planning_bundle
    with pytest.raises(PlanningValidationError):
        replace(evidence, colliding_object_ids=("review-box",))


def test_rejection_cannot_carry_usable_waypoints(planning_bundle):
    *_, evidence = planning_bundle
    with pytest.raises(PlanningValidationError):
        replace(evidence, status=PlanEvidenceStatus.PATH_COLLISION_REPORTED)


def test_false_collision_check_flags_fail_closed(planning_bundle):
    *_, evidence = planning_bundle
    for field in ("self_collision_checked", "environment_collision_checked"):
        with pytest.raises(PlanningValidationError):
            replace(evidence, **{field: False})


def test_recomputed_verifiers_detect_post_construction_mutation(planning_bundle):
    *_, request, evidence = planning_bundle
    object.__setattr__(request, "request_id", "request-sha256-" + ("0" * 64))
    object.__setattr__(evidence, "request", request)
    assert not verify_manipulation_planning_request(request)
    assert not verify_manipulation_plan_evidence(evidence)


def test_decision_rejects_contradictory_reason(planning_bundle):
    *_, request, evidence = planning_bundle
    with pytest.raises(PlanningValidationError):
        ManipulationPlanningDecision(
            request=request,
            plan_evidence=evidence,
            disposition=PlanningDisposition.PLAN_AVAILABLE_FOR_REVIEW,
            reasons=(
                PlanningDecisionReason.NO_PLAN_FOUND,
                PlanningDecisionReason.EXECUTION_OUT_OF_SCOPE,
                PlanningDecisionReason.PHYSICAL_VALIDATION_ABSENT,
            ),
            execution_disposition=ExecutionDisposition.NOT_EXECUTED,
        )


@pytest.mark.parametrize(
    "field",
    ["robot_model", "joint_catalog", "group", "start_state", "goal", "scene"],
)
def test_request_cross_object_substitutions_fail_closed(planning_bundle, field):
    model, catalog, group, start, goal, scene, request, _ = planning_bundle
    replacements = {
        "robot_model": replace(model, description_fingerprint="description-sha256-" + ("0" * 64)),
        "joint_catalog": replace(catalog, robot_model=replace(model, description_fingerprint="description-sha256-" + ("1" * 64))),
        "group": replace(group, joint_catalog_id="catalog-sha256-" + ("2" * 64)),
        "start_state": replace(start, group_id="group-sha256-" + ("3" * 64)),
        "goal": replace(goal, group_fingerprint="group-content-sha256-" + ("4" * 64)),
        "scene": replace(scene, group_id="group-sha256-" + ("5" * 64)),
    }
    with pytest.raises(PlanningValidationError):
        replace(request, **{field: replacements[field]})


def test_collision_scene_is_fixed_bounded_box_only(planning_bundle):
    model, _, group, *_ = planning_bundle
    wrong_frame = CollisionBox("box", "odom", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.1, 0.1, 0.1))
    with pytest.raises(PlanningValidationError):
        PlanningSceneEvidence(model.robot_model_id, model.robot_model_fingerprint, group.group_id, group.group_fingerprint, "base_link", (wrong_frame,))
    with pytest.raises(PlanningValidationError):
        CollisionBox("box", "base_link", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.1, 0.1, 0.1))
    duplicate = CollisionBox("box", "base_link", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.1, 0.1, 0.1))
    with pytest.raises(PlanningValidationError):
        PlanningSceneEvidence(model.robot_model_id, model.robot_model_fingerprint, group.group_id, group.group_fingerprint, "base_link", (duplicate, duplicate))
