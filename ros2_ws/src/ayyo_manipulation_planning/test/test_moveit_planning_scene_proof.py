from __future__ import annotations

import json
from pathlib import Path
import subprocess

from ament_index_python.packages import get_package_prefix, get_package_share_directory


JOINT_NAMES = [
    "left_shoulder_yaw_joint",
    "left_shoulder_pitch_joint",
    "left_elbow_flex_joint",
    "left_wrist_yaw_joint",
]
START = (0.0, 0.0, 0.2, 0.0)
GOAL = (0.3, 0.0, 0.8, 0.2)
PATH_SEGMENTS = 13
DISABLED_COLLISION_PAIRS = [
    ["chest_link", "left_shoulder_mount_link"],
    ["left_elbow_link", "left_forearm_link"],
    ["left_elbow_link", "left_upper_arm_link"],
    ["left_forearm_link", "left_hand_link"],
    ["left_forearm_link", "left_upper_arm_link"],
    ["left_forearm_link", "left_wrist_link"],
    ["left_hand_link", "left_wrist_link"],
    ["left_shoulder_mount_link", "left_shoulder_yaw_link"],
    ["left_shoulder_mount_link", "left_upper_arm_link"],
    ["left_shoulder_yaw_link", "left_upper_arm_link"],
]
EXPECTED = {
    "backend_id": "moveit.planning-scene.v1",
    "backend_version": "moveit-2.12.4",
    "collision_objects": [{
        "dimensions_xyz": [0.1, 0.1, 0.1],
        "frame_id": "base_link",
        "object_id": "review-box",
        "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "position_xyz": [1.0, 0.0, 0.5],
    }],
    "deterministic_seed": 0,
    "disabled_collision_pairs": DISABLED_COLLISION_PAIRS,
    "environment_collision_free": [True] * (PATH_SEGMENTS + 1),
    "execution_disposition": "not_executed",
    "goal_obstacle_collision_reported": True,
    "group_name": "left_arm",
    "interpolation_step": 0.05,
    "joint_names": JOINT_NAMES,
    "limits_match_reviewed": True,
    "max_waypoints": 129,
    "model_frame": "base_link",
    "no_execution_api_used": True,
    "physical_validation": "absent",
    "planner_id": "ayyo.bounded-linear-joint-space.v1",
    "result": "plan_available_for_review",
    "robot_description_content_fingerprint": (
        "ayyo-expanded-urdf-content-sha256-"
        "cc736dfa37535399b739d4e51550f5f76fe63102e037e29aabbb1c2e303ce93f"
    ),
    "samples_checked": PATH_SEGMENTS + 1,
    "schema": {"id": "ayyo.moveit-planning-scene-proof.v1", "version": "1.0.0"},
    "self_collision_free": [True] * (PATH_SEGMENTS + 1),
    "srdf_content_fingerprint": (
        "ayyo-left-arm-srdf-content-sha256-"
        "43b8163ee53c3694ee79890340611c822b79ddd1cee209a35d5d887163e0e385"
    ),
    "waypoints": [
        [
            start + ((goal - start) * (index / PATH_SEGMENTS))
            for start, goal in zip(START, GOAL, strict=True)
        ]
        for index in range(PATH_SEGMENTS + 1)
    ],
}
MAX_DESCRIPTION_BYTES = 1024 * 1024
MAX_SEMANTIC_BYTES = 64 * 1024


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


def _assert_exact_proof(payload: str) -> None:
    result = json.loads(payload)
    assert result == EXPECTED
    assert json.dumps(
        result,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) == payload


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
    _assert_exact_proof(runs[0].stdout)


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
    _assert_exact_proof(below_limit.stdout)

    exactly_at_limit = subprocess.run(
        command,
        input=_padded_robot_description(expanded, MAX_DESCRIPTION_BYTES),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    _assert_exact_proof(exactly_at_limit.stdout)

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


def test_moveit_planning_scene_proof_rejects_substituted_urdf_content():
    command, expanded = _proof_command()
    substituted = expanded.replace('xyz="0 0 -0.28"', 'xyz="0 0 -0.27"', 1)
    assert substituted != expanded
    result = subprocess.run(
        command,
        input=substituted,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "description fingerprint is not reviewed" in result.stderr


def test_moveit_planning_scene_proof_rejects_substituted_acm(tmp_path):
    command, expanded = _proof_command()
    srdf_path = Path(command[1])
    reviewed = srdf_path.read_text(encoding="utf-8")
    variants = (
        reviewed.replace(
            'link1="left_forearm_link" link2="left_hand_link"',
            'link1="left_elbow_link" link2="left_hand_link"',
            1,
        ),
        reviewed.replace("</robot>", (
            '<disable_collisions link1="chest_link" link2="left_hand_link" '
            'reason="Adjacent"/></robot>'
        )),
    )
    for index, variant in enumerate(variants):
        candidate = tmp_path / f"substituted-{index}.srdf"
        candidate.write_text(variant, encoding="utf-8")
        result = subprocess.run(
            [command[0], str(candidate)],
            input=expanded,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 2
        assert result.stdout == ""
        assert "description fingerprint is not reviewed" in result.stderr


def test_moveit_planning_scene_proof_enforces_srdf_bound(tmp_path):
    command, expanded = _proof_command()
    oversized = tmp_path / "oversized.srdf"
    oversized.write_text("x" * (MAX_SEMANTIC_BYTES + 1), encoding="utf-8")
    result = subprocess.run(
        [command[0], str(oversized)],
        input=expanded,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "input violates its planning-proof byte bound" in result.stderr
