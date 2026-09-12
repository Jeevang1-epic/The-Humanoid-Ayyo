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
MAX_DESCRIPTION_BYTES = 1024 * 1024


def _padded_robot_description(document: str, target_bytes: int) -> str:
    marker_bytes = len("<!---->".encode("utf-8"))
    padding_bytes = target_bytes - len(document.encode("utf-8")) - marker_bytes
    assert padding_bytes >= 0
    padded = document.replace(
        "</robot>",
        "<!--" + ("x" * padding_bytes) + "--></robot>",
        1,
    )
    assert len(padded.encode("utf-8")) == target_bytes
    return padded


def _proof_command() -> tuple[list[str], str]:
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
    return command, expanded


def test_moveit_planning_scene_proof_is_headless_deterministic_and_collision_checked():
    command, expanded = _proof_command()
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


def test_moveit_planning_scene_proof_enforces_description_bound_without_truncation():
    command, expanded = _proof_command()
    assert 0 < len(expanded.encode("utf-8")) < MAX_DESCRIPTION_BYTES

    below_limit = subprocess.run(
        command,
        input=expanded,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert json.loads(below_limit.stdout) == EXPECTED

    exactly_at_limit = subprocess.run(
        command,
        input=_padded_robot_description(expanded, MAX_DESCRIPTION_BYTES),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert json.loads(exactly_at_limit.stdout) == EXPECTED

    over_limit = subprocess.run(
        command,
        input=_padded_robot_description(expanded, MAX_DESCRIPTION_BYTES + 1),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert over_limit.returncode == 2
    assert over_limit.stdout == ""
    assert "input violates its planning-proof byte bound" in over_limit.stderr

    empty = subprocess.run(
        command,
        input="",
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert empty.returncode == 2
    assert empty.stdout == ""
    assert "input violates its planning-proof byte bound" in empty.stderr
