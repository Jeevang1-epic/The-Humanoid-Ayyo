from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from ament_index_python.packages import get_package_prefix, get_package_share_directory


JOINT_NAMES = [
    "left_shoulder_yaw_joint",
    "left_shoulder_pitch_joint",
    "left_elbow_flex_joint",
    "left_wrist_yaw_joint",
]
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


def _content_fingerprint(prefix: str, value: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    return f"{prefix}-sha256-{sha256(without_comments.encode()).hexdigest()}"


def _fixture(tmp_path: Path) -> tuple[list[str], str, str]:
    description_share = Path(get_package_share_directory("ayyo_description"))
    planning_share = Path(get_package_share_directory("ayyo_manipulation_planning"))
    executable = (
        Path(get_package_prefix("ayyo_manipulation_simulation_execution"))
        / "lib/ayyo_manipulation_simulation_execution/stage9c_moveit_preflight"
    )
    urdf = subprocess.run(
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
    srdf_path = planning_share / "config/ayyo_left_arm.srdf"
    srdf = srdf_path.read_text(encoding="utf-8")
    input_document = {
        "collision_model_fingerprint": "collision-model-content-sha256-" + "1" * 64,
        "collision_model_id": "collision-model-sha256-" + "1" * 64,
        "collision_objects": [
            {
                "dimensions_xyz": [0.1, 0.1, 0.1],
                "frame_id": "base_link",
                "object_fingerprint": "collision-object-content-sha256-" + "1" * 64,
                "object_id": "review-box",
                "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "position_xyz": [1.0, 0.0, 0.5],
                "schema": {"id": "ayyo.manipulation-planning.collision-box.v1", "version": "1.0.0"},
            }
        ],
        "disabled_collision_pairs": DISABLED_COLLISION_PAIRS,
        "execution_request_fingerprint": "execution-request-content-sha256-" + "1" * 64,
        "execution_request_id": "execution-request-sha256-" + "1" * 64,
        "group_fingerprint": "group-content-sha256-" + "1" * 64,
        "group_id": "group-sha256-" + "1" * 64,
        "joint_catalog_fingerprint": "catalog-content-sha256-" + "1" * 64,
        "joint_catalog_id": "catalog-sha256-" + "1" * 64,
        "joint_names": JOINT_NAMES,
        "robot_description_content_fingerprint": _content_fingerprint(
            "ayyo-expanded-urdf-content", urdf
        ),
        "robot_model_fingerprint": "model-content-sha256-" + "1" * 64,
        "robot_model_id": "model-sha256-" + "1" * 64,
        "samples": [
            {
                "positions": [0.0, 0.0, 0.2, 0.0],
                "sample_index": 0,
                "segment_fraction": 0.0,
                "segment_index": 0,
                "segment_subdivisions": 1,
                "subdivision_index": 0,
            },
            {
                "positions": [0.01, 0.01, 0.21, 0.01],
                "sample_index": 1,
                "segment_fraction": 1.0,
                "segment_index": 0,
                "segment_subdivisions": 1,
                "subdivision_index": 1,
            },
        ],
        "sampling_policy_fingerprint": "sampling-policy-sha256-" + "1" * 64,
        "scene_fingerprint": "scene-content-sha256-" + "1" * 64,
        "scene_id": "scene-sha256-" + "1" * 64,
        "schema": {"id": "ayyo.stage9c.moveit-preflight-input.v1", "version": "1.0.0"},
        "srdf_content_fingerprint": _content_fingerprint(
            "ayyo-left-arm-srdf-content", srdf
        ),
        "trajectory_fingerprint": "trajectory-content-sha256-" + "1" * 64,
        "trajectory_id": "trajectory-sha256-" + "1" * 64,
    }
    payload = json.dumps(input_document, separators=(",", ":"), sort_keys=True)
    input_path = tmp_path / "preflight-input.json"
    input_path.write_text(payload, encoding="utf-8")
    return [str(executable), str(srdf_path), str(input_path)], urdf, payload


def test_preflight_is_headless_dense_and_deterministic(tmp_path: Path) -> None:
    command, urdf, input_payload = _fixture(tmp_path)
    runs = [
        subprocess.run(
            command,
            input=urdf,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        for _ in range(2)
    ]
    assert runs[0].stdout == runs[1].stdout
    report = json.loads(runs[0].stdout)
    assert report["input_fingerprint"] == (
        "stage9c-moveit-preflight-input-sha256-"
        + sha256(input_payload.encode()).hexdigest()
    )
    assert report["samples_checked"] == 2
    assert all(item["within_joint_limits"] for item in report["samples"])
    assert all(item["self_collision_free"] for item in report["samples"])
    assert all(item["environment_collision_free"] for item in report["samples"])
    assert report["continuous_collision_certification"] is False
    assert report["no_execution_api_used"] is True
    assert json.dumps(report, separators=(",", ":"), sort_keys=True) == runs[0].stdout


def test_preflight_rejects_substituted_description_and_noncanonical_input(
    tmp_path: Path,
) -> None:
    command, urdf, payload = _fixture(tmp_path)
    substituted = urdf.replace('xyz="0 0 -0.28"', 'xyz="0 0 -0.27"', 1)
    rejected = subprocess.run(
        command,
        input=substituted,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert rejected.returncode == 2
    assert "description fingerprint is not reviewed" in rejected.stderr

    Path(command[2]).write_text(payload + "\n", encoding="utf-8")
    rejected = subprocess.run(
        command,
        input=urdf,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert rejected.returncode == 2
    assert "not canonical JSON" in rejected.stderr
