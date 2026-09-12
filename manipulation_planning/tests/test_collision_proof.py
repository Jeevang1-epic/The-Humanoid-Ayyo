from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from ayyo_manipulation_planning import (
    ExecutionDisposition,
    ManipulationPlanEvidence,
    PlanEvidenceStatus,
    PlanningSerializationError,
    PlanningValidationError,
    build_reviewed_collision_model,
    deterministic_joint_interpolation,
    moveit_collision_proof_from_canonical_json,
)
from ayyo_manipulation_planning.canonical import canonical_json


def _raw_proof(request):
    waypoints = deterministic_joint_interpolation(request)
    return {
        "backend_id": "moveit.planning-scene.v1",
        "backend_version": "moveit-2.12.4",
        "collision_objects": [
            {
                "dimensions_xyz": list(item.dimensions_xyz),
                "frame_id": item.frame_id,
                "object_id": item.object_id,
                "orientation_xyzw": list(item.orientation_xyzw),
                "position_xyz": list(item.position_xyz),
            }
            for item in request.scene.collision_objects
        ],
        "deterministic_seed": 0,
        "disabled_collision_pairs": [
            list(pair) for pair in request.collision_model.disabled_collision_pairs
        ],
        "environment_collision_free": [True] * len(waypoints),
        "execution_disposition": "not_executed",
        "goal_obstacle_collision_reported": True,
        "group_name": "left_arm",
        "interpolation_step": 0.05,
        "joint_names": list(request.group.joint_names),
        "limits_match_reviewed": True,
        "max_waypoints": 129,
        "model_frame": "base_link",
        "no_execution_api_used": True,
        "physical_validation": "absent",
        "planner_id": "ayyo.bounded-linear-joint-space.v1",
        "result": "plan_available_for_review",
        "robot_description_content_fingerprint": (
            request.collision_model.robot_description_content_fingerprint
        ),
        "samples_checked": len(waypoints),
        "schema": {"id": "ayyo.moveit-planning-scene-proof.v1", "version": "1.0.0"},
        "self_collision_free": [True] * len(waypoints),
        "srdf_content_fingerprint": request.collision_model.srdf_content_fingerprint,
        "waypoints": [
            [position.position for position in waypoint.positions]
            for waypoint in waypoints
        ],
    }


def test_reviewed_collision_model_binds_exact_urdf_srdf_group_and_acm(
    expanded_urdf,
    reviewed_srdf,
    planning_bundle,
):
    model, catalog, group, *_, request, _ = planning_bundle
    rebuilt = build_reviewed_collision_model(
        expanded_urdf,
        reviewed_srdf,
        model,
        catalog,
        group,
    )
    assert rebuilt == request.collision_model
    assert len(rebuilt.disabled_collision_pairs) == 10


@pytest.mark.parametrize(
    "substituted_srdf",
    [
        lambda srdf: srdf.replace(
            'link1="left_forearm_link" link2="left_hand_link"',
            'link1="left_elbow_link" link2="left_hand_link"',
            1,
        ),
        lambda srdf: srdf.replace("reason=\"Adjacent\"", "reason=\"Never\"", 1),
        lambda srdf: srdf.replace("</robot>", '<passive_joint name="left_wrist_yaw_joint"/></robot>'),
        lambda srdf: srdf.replace("<group name=\"left_arm\">", "<group name=\"arm\">", 1),
    ],
)
def test_semantically_substituted_srdf_fails_closed(
    expanded_urdf,
    reviewed_srdf,
    planning_bundle,
    substituted_srdf,
):
    model, catalog, group, *_ = planning_bundle
    with pytest.raises(PlanningValidationError):
        build_reviewed_collision_model(
            expanded_urdf,
            substituted_srdf(reviewed_srdf),
            model,
            catalog,
            group,
        )


def test_nonsemantic_comments_do_not_substitute_collision_identity(
    expanded_urdf,
    reviewed_srdf,
    planning_bundle,
):
    model, catalog, group, *_, request, _ = planning_bundle
    urdf = expanded_urdf.replace("</robot>", "<!-- invocation-path-free --></robot>")
    srdf = reviewed_srdf.replace("</robot>", "<!-- review note --></robot>")
    assert build_reviewed_collision_model(urdf, srdf, model, catalog, group) == (
        request.collision_model
    )


def test_canonical_moveit_result_binds_the_exact_request_path_and_scene(planning_bundle):
    *_, request, _ = planning_bundle
    proof = moveit_collision_proof_from_canonical_json(
        request,
        canonical_json(_raw_proof(request)),
    )
    assert proof.waypoints == deterministic_joint_interpolation(request)
    assert proof.collision_objects == request.scene.collision_objects
    assert proof.execution_disposition is ExecutionDisposition.NOT_EXECUTED


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.update(result="rejected"),
        lambda item: item.update(limits_match_reviewed=False),
        lambda item: item.update(goal_obstacle_collision_reported=False),
        lambda item: item["disabled_collision_pairs"].pop(),
        lambda item: item["disabled_collision_pairs"].reverse(),
        lambda item: item["collision_objects"][0]["position_xyz"].__setitem__(0, 0.9),
        lambda item: item["waypoints"].pop(1),
        lambda item: item["waypoints"].insert(1, list(item["waypoints"][1])),
        lambda item: item["waypoints"].__setitem__(
            1, [item["waypoints"][1][0] + 0.001, *item["waypoints"][1][1:]]
        ),
        lambda item: item["waypoints"].reverse(),
        lambda item: item["self_collision_free"].__setitem__(1, False),
        lambda item: item["environment_collision_free"].__setitem__(1, False),
        lambda item: item.update(interpolation_step=0.1),
        lambda item: item.update(deterministic_seed=1),
        lambda item: item.update(execution_disposition="executed"),
        lambda item: item.update(physical_validation="present"),
    ],
)
def test_moveit_result_substitution_and_collision_positive_claims_fail_closed(
    planning_bundle,
    mutate,
):
    *_, request, _ = planning_bundle
    document = _raw_proof(request)
    mutate(document)
    with pytest.raises(PlanningSerializationError):
        moveit_collision_proof_from_canonical_json(request, canonical_json(document))


def test_moveit_result_from_request_a_cannot_be_composed_with_request_b(planning_bundle):
    *_, request, _ = planning_bundle
    alternate_goal = replace(
        request.goal,
        positions=(
            replace(request.goal.positions[0], position=0.4),
            *request.goal.positions[1:],
        ),
    )
    alternate_request = replace(request, goal=alternate_goal)
    with pytest.raises(PlanningSerializationError):
        moveit_collision_proof_from_canonical_json(
            alternate_request,
            canonical_json(_raw_proof(request)),
        )


def test_proof_from_request_a_cannot_be_composed_with_evidence_for_request_b(
    planning_bundle,
):
    *_, request, evidence = planning_bundle
    alternate_goal = replace(
        request.goal,
        positions=(
            replace(request.goal.positions[0], position=0.4),
            *request.goal.positions[1:],
        ),
    )
    alternate_request = replace(request, goal=alternate_goal)
    alternate_waypoints = deterministic_joint_interpolation(alternate_request)
    with pytest.raises(PlanningValidationError):
        ManipulationPlanEvidence(
            request=alternate_request,
            status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
            collision_proof=evidence.collision_proof,
            backend_version=evidence.backend_version,
            planner_seed=evidence.planner_seed,
            waypoints=alternate_waypoints,
            checked_collision_object_ids=evidence.checked_collision_object_ids,
            colliding_object_ids=(),
            self_collision_checked=True,
            environment_collision_checked=True,
            execution_disposition=ExecutionDisposition.NOT_EXECUTED,
        )


def test_proof_waypoint_identity_binding_cannot_be_substituted(planning_bundle):
    *_, evidence = planning_bundle
    proof = evidence.collision_proof
    substituted = replace(
        proof.waypoints[1],
        group_id="manipulator-group-sha256-" + ("0" * 64),
    )
    foreign_proof = replace(
        proof,
        waypoints=(proof.waypoints[0], substituted, *proof.waypoints[2:]),
    )
    with pytest.raises(PlanningValidationError):
        replace(evidence, collision_proof=foreign_proof)


def test_collision_free_proof_cannot_be_relabelled_as_collision_positive(planning_bundle):
    *_, evidence = planning_bundle
    with pytest.raises(PlanningValidationError):
        replace(
            evidence,
            status=PlanEvidenceStatus.PATH_COLLISION_REPORTED,
            waypoints=(),
        )


def test_moveit_result_rejects_noncanonical_json(planning_bundle):
    *_, request, _ = planning_bundle
    document = _raw_proof(request)
    canonical = canonical_json(document)
    variants = (
        canonical + "\n",
        canonical.replace("{", "{ ", 1),
        canonical.replace('"backend_id"', '"backend_id":"shadow","backend_id"', 1),
    )
    for payload in variants:
        with pytest.raises(PlanningSerializationError):
            moveit_collision_proof_from_canonical_json(request, payload)


def test_moveit_proof_nested_post_construction_mutation_is_not_publishable(
    planning_bundle,
):
    *_, evidence = planning_bundle
    proof = evidence.collision_proof
    object.__setattr__(proof.waypoints[1].positions[0], "position", 0.0)
    with pytest.raises(PlanningValidationError):
        replace(evidence, collision_proof=proof)
