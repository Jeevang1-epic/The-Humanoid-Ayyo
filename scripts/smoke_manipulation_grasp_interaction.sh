#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-stage9d-smoke.XXXXXX)"
readonly launch_log="$smoke_root/stage9d_simulation.log"
readonly result_json="$smoke_root/stage9d_result.json"
readonly default_setup="$workspace_root/install/setup.bash"
readonly install_setup="${AYYO_STAGE9D_INSTALL_SETUP:-$default_setup}"
readonly default_domain_id="$((100 + ($$ % 100)))"
readonly smoke_domain_id="${AYYO_STAGE9D_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_stage9d_smoke_$$"
readonly wait_deadline_seconds=60
launch_pid=""

# shellcheck source=scripts/smoke_processes.sh
source "$process_helper"

cleanup() {
  local exit_status="$?"
  trap - EXIT INT TERM
  if ! ayyo_smoke_shutdown_owned_launch; then
    exit_status=1
  fi
  rm -rf "$smoke_root"
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -f "$install_setup" ]]; then
  printf 'Stage 9D workspace is not built: %s\n' "$install_setup" >&2
  exit 1
fi

# shellcheck disable=SC1090
set +u
source /opt/ros/jazzy/setup.bash
source "$install_setup"
set -u

export ROS_DOMAIN_ID="$smoke_domain_id"
export GZ_PARTITION="$smoke_partition"
export ROS_LOG_DIR="$smoke_root/ros_logs"
export GZ_HOMEDIR="$smoke_root/gz_home"
mkdir -p "$ROS_LOG_DIR" "$GZ_HOMEDIR"

ros2 pkg prefix ayyo_manipulation_grasp_interaction >/dev/null
ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_manipulation_grasp_interaction \
  stage9d_simulation.launch.py headless:=true

wait_until() {
  local description="$1"
  local check_function="$2"
  local deadline="$((SECONDS + wait_deadline_seconds))"
  while ((SECONDS < deadline)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,360p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,360p' "$launch_log" >&2
  return 1
}

controllers_ready() {
  local controllers
  controllers="$(
    timeout 3 ros2 control list_controllers \
      --controller-manager /controller_manager 2>/dev/null || true
  )"
  grep -Eq \
    '^joint_state_broadcaster[[:space:]]+joint_state_broadcaster/JointStateBroadcaster[[:space:]]+active$' \
    <<<"$controllers" &&
    grep -Eq \
      '^ayyo_left_arm_trajectory_controller[[:space:]]+joint_trajectory_controller/JointTrajectoryController[[:space:]]+active$' \
      <<<"$controllers" &&
    ! grep -q 'ayyo_neck_position_controller' <<<"$controllers"
}

action_ready() {
  local actions
  actions="$(timeout 3 ros2 action list -t 2>/dev/null || true)"
  grep -Fxq \
    '/ayyo_left_arm_trajectory_controller/follow_joint_trajectory [control_msgs/action/FollowJointTrajectory]' \
    <<<"$actions"
}

stage9d_topics_ready() {
  local topics
  topics="$(timeout 3 ros2 topic list -t 2>/dev/null || true)"
  grep -Fxq \
    '/ayyo/stage9d/grasp_object/contacts [ros_gz_interfaces/msg/Contacts]' \
    <<<"$topics" &&
    grep -Fxq \
      '/ayyo/stage9d/grasp_object/odometry [nav_msgs/msg/Odometry]' \
      <<<"$topics" &&
    grep -Fxq \
      '/ayyo/stage9d/grasp_fixture/state [std_msgs/msg/String]' \
      <<<"$topics"
}

object_ready() {
  local sample
  sample="$(
    timeout 3 ros2 topic echo --once /ayyo/stage9d/grasp_object/odometry \
      nav_msgs/msg/Odometry 2>/dev/null || true
  )"
  grep -q 'position:' <<<"$sample" && grep -q 'orientation:' <<<"$sample"
}

contact_ready() {
  local sample
  sample="$(
    timeout 3 ros2 topic echo --once /ayyo/stage9d/grasp_object/contacts \
      ros_gz_interfaces/msg/Contacts 2>/dev/null || true
  )"
  grep -q 'stage9d_grasp_object_collision' <<<"$sample" &&
    grep -q 'left_hand_link' <<<"$sample"
}

fixture_detached() {
  local sample
  sample="$(
    timeout 3 ros2 topic echo --once /ayyo/stage9d/grasp_fixture/state \
      std_msgs/msg/String 2>/dev/null || true
  )"
  grep -Fxq 'data: detached' <<<"$sample"
}

wait_until 'Stage 9C reviewed controllers are active' controllers_ready
wait_until 'the fixed Stage 9C action is the only arm execution seam' action_ready
wait_until 'the five fixed Stage 9D bridge topics are typed' stage9d_topics_ready
wait_until 'the exact reviewed primitive has fresh odometry' object_ready
wait_until 'the exact hand/object contact is observable' contact_ready
wait_until 'the Stage 9D constraint begins detached' fixture_detached

set +e
timeout --signal=INT --kill-after=5 120 \
  ros2 run ayyo_manipulation_grasp_interaction stage9d_interaction.py \
  >"$result_json"
execution_status=$?
set -e
if [[ "$execution_status" -ne 0 ]]; then
  printf 'FAIL: Stage 9D interaction exited %s\n' "$execution_status" >&2
  tail -240 "$result_json" >&2 || true
  tail -360 "$launch_log" >&2
  exit 1
fi

python3 - "$result_json" <<'PY'
import json
from pathlib import Path
import sys

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["status"] == "simulation_grasp_interaction_completed"
assert result["completed_phases"] == [
    "pregrasp_validated",
    "contact_observed",
    "grasp_established",
    "hold_validated",
    "release_requested",
    "release_observed",
]
assert result["failure_reasons"] == []
assert result["authority"] == "development_simulation_only"
assert result["physical_validation"] == "not_physically_validated"
assert result["hardware_authority"] == "no_hardware_authority"
assert result["production_runtime_authority"] == "no_production_runtime_authority"
release = result["release"]
hold = release["hold"]
grasp = hold["grasp"]
assert grasp["contact"]["collision_pairs"] == [[
    "ayyo::left_hand_link::collision",
    "stage9d_grasp_object::stage9d_grasp_object_link::stage9d_grasp_object_collision",
]]
assert grasp["pregrasp"]["detached_fixture"]["state"] == "detached"
assert grasp["attached_fixture"]["state"] == "attached"
assert hold["attached_fixture"]["state"] == "attached"
assert hold["relative_translation_change"] <= 0.005
assert hold["relative_rotation_change"] <= 0.05
assert hold["stage9c_result"]["status"] == "completed"
assert hold["stage9c_result"]["motion_status"] == "simulation_executed"
assert hold["stage9c_result"]["observation"]["stability_observation"]["status"] == (
    "whole_body_stable"
)
proof = hold["collision_proof"]
assert proof["allowed_touch_links"] == ["left_hand_link"]
assert proof["target_object_specific"] is True
assert proof["grasp_interval_only"] is True
assert proof["global_acm_modified"] is False
assert proof["continuous_collision_certification"] is False
assert proof["physical_collision_certification"] is False
assert all(sample["attached_object_checked"] for sample in proof["samples"])
assert release["detached_fixture"]["state"] == "detached"
assert release["relative_pose_change"] >= 0.005
assert release["post_release_stability"]["status"] == "whole_body_stable"
PY
printf 'PASS: exact Stage 9D contact established one bounded simulated hold\n'
printf 'PASS: reviewed Stage 9C motion carried the object within hold bounds\n'
printf 'PASS: explicit release produced fresh non-rigid object evidence\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|Segmentation fault' "$launch_log"; then
  printf 'FAIL: Stage 9D adapter reported an unclean shutdown\n' >&2
  sed -n '1,420p' "$launch_log" >&2
  exit 1
fi
printf 'PASS: Stage 9D owned process set is empty after bounded shutdown\n'
printf 'PASS: headless Stage 9D simulation grasp interaction completed\n'
