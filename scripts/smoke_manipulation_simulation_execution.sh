#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-stage9c-smoke.XXXXXX)"
readonly launch_log="$smoke_root/stage9c_simulation.log"
readonly result_json="$smoke_root/stage9c_result.json"
readonly default_setup="$workspace_root/install/setup.bash"
readonly install_setup="${AYYO_STAGE9C_INSTALL_SETUP:-$default_setup}"
readonly default_domain_id="$((100 + ($$ % 100)))"
readonly smoke_domain_id="${AYYO_STAGE9C_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_stage9c_smoke_$$"
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
  printf 'Stage 9C workspace is not built: %s\n' "$install_setup" >&2
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

ros2 pkg prefix ayyo_manipulation_simulation_execution >/dev/null
ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_manipulation_simulation_execution \
  stage9c_simulation.launch.py headless:=true

wait_until() {
  local description="$1"
  local check_function="$2"
  local deadline="$((SECONDS + wait_deadline_seconds))"
  while ((SECONDS < deadline)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,320p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,320p' "$launch_log" >&2
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

hardware_ready() {
  local interfaces command_count
  interfaces="$(
    timeout 3 ros2 control list_hardware_interfaces \
      --controller-manager /controller_manager 2>/dev/null || true
  )"
  command_count="$(
    awk '
      /^command interfaces$/ { in_commands=1; next }
      /^state interfaces$/ { in_commands=0 }
      in_commands && NF { count++ }
      END { print count+0 }
    ' <<<"$interfaces"
  )"
  [[ "$command_count" -eq 4 ]] || return 1
  local joint
  for joint in \
    left_shoulder_yaw_joint \
    left_shoulder_pitch_joint \
    left_elbow_flex_joint \
    left_wrist_yaw_joint
  do
    grep -Eq \
      "^[[:space:]]+$joint/position[[:space:]]+\[available\][[:space:]]+\[claimed\]$" \
      <<<"$interfaces" || return 1
  done
}

action_ready() {
  local actions
  actions="$(timeout 3 ros2 action list -t 2>/dev/null || true)"
  grep -Fxq \
    '/ayyo_left_arm_trajectory_controller/follow_joint_trajectory [control_msgs/action/FollowJointTrajectory]' \
    <<<"$actions"
}

joint_states_ready() {
  local sample
  sample="$(
    timeout 3 ros2 topic echo --once /joint_states sensor_msgs/msg/JointState \
      2>/dev/null || true
  )"
  grep -q 'left_shoulder_yaw_joint' <<<"$sample" &&
    grep -q 'left_elbow_flex_joint' <<<"$sample"
}

wait_until 'Stage 9C controllers are active without the neck controller' controllers_ready
wait_until 'exactly four reviewed arm command interfaces are claimed' hardware_ready
wait_until 'the fixed FollowJointTrajectory action is available' action_ready
wait_until 'fresh simulated left-arm state is observable' joint_states_ready

set +e
timeout --signal=INT --kill-after=5 90 \
  ros2 run ayyo_manipulation_simulation_execution stage9c_execution.py \
  >"$result_json"
execution_status=$?
set -e
if [[ "$execution_status" -ne 0 ]]; then
  printf 'FAIL: Stage 9C execution exited %s\n' "$execution_status" >&2
  python3 - "$result_json" <<'PY' >&2 || true
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.is_file() or not path.stat().st_size:
    raise SystemExit("FAIL: Stage 9C emitted no result artifact")
result = json.loads(path.read_text(encoding="utf-8"))
observation = result.get("observation")
if observation is None:
    print(
        "FAIL: preflight status/reasons:",
        result.get("status"),
        result.get("reasons"),
    )
else:
    print(
        "FAIL: execution outcome/final errors:",
        observation.get("outcome"),
        observation.get("final_joint_errors"),
    )
PY
  tail -240 "$launch_log" >&2
  exit 1
fi

python3 - "$result_json" <<'PY'
import json
from pathlib import Path
import sys

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["status"] == "completed"
assert result["motion_status"] == "simulation_executed"
assert result["authority"] == "development_simulation_only"
assert result["physical_validation"] == "not_physically_validated"
assert result["hardware_authority"] == "no_hardware_authority"
assert result["production_runtime_authority"] == "no_production_runtime_authority"
observation = result["observation"]
assert observation["acceptance"] == "accepted"
assert observation["outcome"] == "simulation_execution_completed"
assert observation["controller_error_code"] == 0
assert observation["feedback_samples_observed"] >= 1
assert max(observation["final_joint_errors"]) <= 0.02
assert max(
    abs(end - start)
    for start, end in zip(
        observation["starting_positions"], observation["ending_positions"], strict=True
    )
) >= 0.1
goal = result["execution_goal"]
assert goal["action_endpoint"] == (
    "/ayyo_left_arm_trajectory_controller/follow_joint_trajectory"
)
assert goal["joint_names"] == [
    "left_shoulder_yaw_joint",
    "left_shoulder_pitch_joint",
    "left_elbow_flex_joint",
    "left_wrist_yaw_joint",
]
preflight = goal["preflight_evidence"]
assert preflight["status"] == "ready_for_simulation_execution"
assert preflight["reasons"] == [
    "collision_free_dense_path",
    "controller_ready",
    "start_state_matched",
]
assert preflight["physical_validation"] == "not_physically_validated"
proof = preflight["collision_proof"]
assert proof["continuous_collision_certification"] is False
assert len(proof["samples"]) > len(
    proof["execution_request"]["stage9b_handoff"]["safety_result"]
    ["trajectory_evidence"]["trajectory"]["points"]
)
PY
printf 'PASS: reviewed Stage 9B trajectory moved only the simulated left arm\n'
printf 'PASS: final state feedback is correlated and within 0.02 rad\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|Segmentation fault' "$launch_log"; then
  printf 'FAIL: Stage 9C adapter reported an unclean shutdown\n' >&2
  sed -n '1,360p' "$launch_log" >&2
  exit 1
fi
printf 'PASS: Stage 9C owned process set is empty after bounded shutdown\n'
printf 'PASS: headless Stage 9C simulation execution proof completed\n'
