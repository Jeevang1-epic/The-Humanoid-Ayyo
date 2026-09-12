from __future__ import annotations

from dataclasses import replace
import math

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
    verify_manipulator_joint_state,
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


def test_collision_free_evidence_rejects_non_planner_waypoint(planning_bundle):
    *_, evidence = planning_bundle
    middle_index = len(evidence.waypoints) // 2
    middle = evidence.waypoints[middle_index]
    changed = replace(
        middle,
        positions=(
            replace(middle.positions[0], position=middle.positions[0].position + 0.001),
            *middle.positions[1:],
        ),
    )
    waypoints = list(evidence.waypoints)
    waypoints[middle_index] = changed
    with pytest.raises(PlanningValidationError):
        replace(evidence, waypoints=tuple(waypoints))


def test_group_fixed_joint_substitution_fails_closed(planning_bundle):
    _, _, group, *_ = planning_bundle
    with pytest.raises(PlanningValidationError):
        replace(group, fixed_joint_names=("left_wrist_to_hand_joint",))


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


def test_joint_limit_substitution_after_request_creation_is_rejected(planning_bundle):
    _, catalog, _, _, _, _, request, _ = planning_bundle
    changed_joint = replace(catalog.chain_joints[0], lower=-1.1)
    with pytest.raises(PlanningValidationError):
        replace(
            catalog,
            chain_joints=(changed_joint, *catalog.chain_joints[1:]),
        )


def test_start_state_substitution_after_evidence_creation_is_rejected(planning_bundle):
    *_, request, evidence = planning_bundle
    changed_start = replace(
        request.start_state,
        positions=(
            replace(request.start_state.positions[0], position=0.1),
            *request.start_state.positions[1:],
        ),
    )
    alternate = replace(request, start_state=changed_start)
    with pytest.raises(PlanningValidationError):
        evaluate_manipulation_plan(alternate, evidence)


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


@pytest.mark.parametrize("artifact_name", ["start", "goal", "waypoint"])
def test_mutated_joint_position_leaf_fails_recursive_verification(
    planning_bundle,
    artifact_name,
):
    *_, request, evidence = planning_bundle
    artifact = {
        "start": request.start_state,
        "goal": request.goal,
        "waypoint": evidence.waypoints[1],
    }[artifact_name]
    object.__setattr__(artifact.positions[0], "position", 0)

    if artifact_name == "goal":
        with pytest.raises(PlanningValidationError):
            replace(request, goal=artifact)
    elif artifact_name == "waypoint":
        assert not verify_manipulator_joint_state(artifact)
        with pytest.raises(PlanningValidationError):
            replace(
                evidence,
                waypoints=(evidence.waypoints[0], artifact, *evidence.waypoints[2:]),
            )
    else:
        assert not verify_manipulator_joint_state(artifact)
        with pytest.raises(PlanningValidationError):
            replace(request, start_state=artifact)


def test_outer_reconstruction_cannot_legitimize_mutated_joint_position(planning_bundle):
    _, catalog, group, start, *_ = planning_bundle
    object.__setattr__(start.positions[0], "position", 0)
    with pytest.raises(PlanningValidationError):
        type(start)(
            group_id=group.group_id,
            group_fingerprint=group.group_fingerprint,
            joint_catalog_id=catalog.joint_catalog_id,
            joint_catalog_fingerprint=catalog.joint_catalog_fingerprint,
            positions=start.positions,
        )


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
    substitutions = {
        "robot_model": lambda: replace(
            request,
            robot_model=replace(
                model,
                description_fingerprint="description-sha256-" + ("0" * 64),
            ),
        ),
        "joint_catalog": lambda: replace(
            request,
            joint_catalog=replace(
                catalog,
                robot_model=replace(
                    model,
                    description_fingerprint="description-sha256-" + ("1" * 64),
                ),
            ),
        ),
        "group": lambda: replace(
            request,
            group=replace(
                group,
                joint_catalog_id="catalog-sha256-" + ("2" * 64),
            ),
        ),
        "start_state": lambda: replace(
            request,
            start_state=replace(
                start,
                group_id="group-sha256-" + ("3" * 64),
            ),
        ),
        "goal": lambda: replace(
            request,
            goal=replace(
                goal,
                group_fingerprint="group-content-sha256-" + ("4" * 64),
            ),
        ),
        "scene": lambda: replace(
            request,
            scene=replace(
                scene,
                group_id="group-sha256-" + ("5" * 64),
            ),
        ),
    }
    with pytest.raises(PlanningValidationError):
        substitutions[field]()


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


@pytest.mark.parametrize(
    ("position", "dimensions"),
    [
        ((0.0, 0.0, 0.0), (0.0, 0.1, 0.1)),
        ((0.0, 0.0, 0.0), (-0.1, 0.1, 0.1)),
        ((0.0, 0.0, 0.0), (5.000001, 0.1, 0.1)),
        ((math.nan, 0.0, 0.0), (0.1, 0.1, 0.1)),
        ((math.inf, 0.0, 0.0), (0.1, 0.1, 0.1)),
        ((0.0, 0.0, 0.0), (math.nan, 0.1, 0.1)),
        ((0.0, 0.0, 0.0), (math.inf, 0.1, 0.1)),
    ],
)
def test_malformed_collision_dimensions_and_positions_fail_closed(position, dimensions):
    with pytest.raises(PlanningValidationError):
        CollisionBox("box", "base_link", position, (0.0, 0.0, 0.0, 1.0), dimensions)


def test_collision_scene_resource_and_identifier_bounds(planning_bundle):
    model, _, group, *_ = planning_bundle
    boxes = tuple(
        CollisionBox(f"box-{index:02d}", "base_link", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.1, 0.1, 0.1))
        for index in range(17)
    )
    with pytest.raises(PlanningValidationError):
        PlanningSceneEvidence(model.robot_model_id, model.robot_model_fingerprint, group.group_id, group.group_fingerprint, "base_link", boxes)
    with pytest.raises(PlanningValidationError):
        CollisionBox("x" * 257, "base_link", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.1, 0.1, 0.1))


def test_collision_scene_construction_canonicalizes_object_order(planning_bundle):
    model, _, group, *_ = planning_bundle
    first = CollisionBox("a", "base_link", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.1, 0.1, 0.1))
    second = CollisionBox("b", "base_link", (1.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (0.1, 0.1, 0.1))
    forward = PlanningSceneEvidence(model.robot_model_id, model.robot_model_fingerprint, group.group_id, group.group_fingerprint, "base_link", (first, second))
    reverse = PlanningSceneEvidence(model.robot_model_id, model.robot_model_fingerprint, group.group_id, group.group_fingerprint, "base_link", (second, first))
    assert forward == reverse


def test_obstacle_mutation_after_plan_generation_is_rejected(planning_bundle):
    *_, request, evidence = planning_bundle
    changed_box = replace(request.scene.collision_objects[0], position_xyz=(0.9, 0.0, 0.5))
    changed_scene = replace(request.scene, collision_objects=(changed_box,))
    changed_request = replace(request, scene=changed_scene)
    with pytest.raises(PlanningValidationError):
        evaluate_manipulation_plan(changed_request, evidence)
