from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ayyo_manipulation_planning import (
    CollisionBox,
    ExecutionDisposition,
    ManipulationPlanEvidence,
    ManipulationPlanningRequest,
    PlanEvidenceStatus,
    PlanningSceneEvidence,
    build_left_arm_planning_model,
    default_planner_configuration,
    deterministic_joint_interpolation,
    make_joint_goal,
    make_joint_state,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
XACRO_PATH = REPOSITORY_ROOT / "ros2_ws/src/ayyo_description/urdf/ayyo.urdf.xacro"


@pytest.fixture(scope="session")
def expanded_urdf() -> str:
    return subprocess.run(
        ["xacro", str(XACRO_PATH), "use_meshes:=false", "simulation_mode:=false"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout


@pytest.fixture()
def planning_bundle(expanded_urdf):
    model, catalog, group = build_left_arm_planning_model(expanded_urdf)
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
        start_state=start,
        goal=goal,
        scene=scene,
        planner_configuration=default_planner_configuration(),
    )
    waypoints = deterministic_joint_interpolation(request)
    evidence = ManipulationPlanEvidence(
        request=request,
        status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
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
