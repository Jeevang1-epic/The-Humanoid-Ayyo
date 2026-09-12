from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ayyo_manipulation_planning import (
    CollisionBox,
    ExecutionDisposition,
    ManipulationPlanEvidence,
    ManipulationPlanningRequest,
    MoveItCollisionProof,
    PlanEvidenceStatus,
    PlanningSceneEvidence,
    build_left_arm_planning_model,
    build_reviewed_collision_model,
    default_planner_configuration,
    deterministic_joint_interpolation,
    make_joint_goal,
    make_joint_state,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
XACRO_PATH = REPOSITORY_ROOT / "ros2_ws/src/ayyo_description/urdf/ayyo.urdf.xacro"
SRDF_PATH = (
    REPOSITORY_ROOT
    / "ros2_ws/src/ayyo_manipulation_planning/config/ayyo_left_arm.srdf"
)


@pytest.fixture(scope="session")
def expanded_urdf() -> str:
    return subprocess.run(
        ["xacro", str(XACRO_PATH), "use_meshes:=false", "simulation_mode:=false"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout


@pytest.fixture(scope="session")
def reviewed_srdf() -> str:
    return SRDF_PATH.read_text(encoding="utf-8")


@pytest.fixture()
def planning_bundle(expanded_urdf, reviewed_srdf):
    model, catalog, group = build_left_arm_planning_model(expanded_urdf)
    collision_model = build_reviewed_collision_model(
        expanded_urdf,
        reviewed_srdf,
        model,
        catalog,
        group,
    )
    start = make_joint_state(group, catalog, (0.0, 0.0, 0.2, 0.0))
    goal = make_joint_goal(group, catalog, (0.3, 0.4, 0.8, 0.2))
    box = CollisionBox(
        object_id="review-box",
        frame_id="base_link",
        position_xyz=(1.0, 0.0, 0.5),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        dimensions_xyz=(0.1, 0.1, 0.1),
    )
    scene = PlanningSceneEvidence(
        robot_model_id=model.robot_model_id,
        robot_model_fingerprint=model.robot_model_fingerprint,
        group_id=group.group_id,
        group_fingerprint=group.group_fingerprint,
        frame_id="base_link",
        collision_objects=(box,),
    )
    request = ManipulationPlanningRequest(
        robot_model=model,
        joint_catalog=catalog,
        group=group,
        collision_model=collision_model,
        start_state=start,
        goal=goal,
        scene=scene,
        planner_configuration=default_planner_configuration(),
    )
    waypoints = deterministic_joint_interpolation(request)
    collision_proof = MoveItCollisionProof(
        request_id=request.request_id,
        request_fingerprint=request.request_fingerprint,
        collision_model_id=collision_model.collision_model_id,
        collision_model_fingerprint=collision_model.collision_model_fingerprint,
        planner_configuration_id=request.planner_configuration.configuration_id,
        planner_configuration_fingerprint=(
            request.planner_configuration.configuration_fingerprint
        ),
        robot_description_content_fingerprint=(
            collision_model.robot_description_content_fingerprint
        ),
        srdf_content_fingerprint=collision_model.srdf_content_fingerprint,
        disabled_collision_pairs=collision_model.disabled_collision_pairs,
        backend_version="moveit-2.12.4",
        joint_names=group.joint_names,
        waypoints=waypoints,
        collision_objects=scene.collision_objects,
        self_collision_free=(True,) * len(waypoints),
        environment_collision_free=(True,) * len(waypoints),
        limits_match_reviewed=True,
        goal_obstacle_collision_reported=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    evidence = ManipulationPlanEvidence(
        request=request,
        status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
        collision_proof=collision_proof,
        backend_version="moveit-2.12.4",
        planner_seed=0,
        waypoints=waypoints,
        checked_collision_object_ids=(box.object_id,),
        colliding_object_ids=(),
        self_collision_checked=True,
        environment_collision_checked=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    return model, catalog, group, start, goal, scene, request, evidence
