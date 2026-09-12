from __future__ import annotations

import json
from pathlib import Path
import subprocess

from ament_index_python.packages import get_package_prefix, get_package_share_directory


EXPECTED = {
    "backend": "moveit-planning-scene",
    "goal_collision_free_without_object": True,
    "goal_obstacle_collision_reported": True,
    "group": "left_arm",
    "joint_count": 4,
    "limits_exact": True,
    "model_frame": "base_link",
    "no_execution_api_used": True,
    "passed": True,
    "path_collision_free": True,
    "samples_checked": 21,
    "start_collision_free": True,
}


def test_moveit_planning_scene_proof_is_headless_deterministic_and_collision_checked():
    description_share = Path(get_package_share_directory("ayyo_description"))
    planning_share = Path(get_package_share_directory("ayyo_manipulation_planning"))
    executable = (
        Path(get_package_prefix("ayyo_manipulation_planning"))
        / "lib/ayyo_manipulation_planning/moveit_planning_scene_proof"
    )
    expanded = subprocess.run(
        [
            "xacro",
            str(description_share / "urdf/ayyo.urdf.xacro"),
            "use_meshes:=false",
            "simulation_mode:=false",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    command = [str(executable), str(planning_share / "config/ayyo_left_arm.srdf")]
    runs = [
        subprocess.run(
            command,
            input=expanded,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        for _ in range(2)
    ]

    assert runs[0].stdout == runs[1].stdout
    assert json.loads(runs[0].stdout) == EXPECTED
