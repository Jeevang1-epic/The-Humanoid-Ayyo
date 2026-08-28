#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-localization-diagnostics-smoke.XXXXXX)"
readonly launch_log="$smoke_root/localization_diagnostics.log"
readonly default_domain_id="$((200 + ($$ % 20)))"
readonly smoke_domain_id="${AYYO_LOCALIZATION_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_localization_diagnostics_smoke_$$"
launch_pid=""

# shellcheck source=scripts/smoke_processes.sh
source "$process_helper"

cleanup() {
  local exit_status="$?"
  trap - EXIT INT TERM
  if ! ayyo_smoke_shutdown_owned_launch; then
    exit_status=1
  fi
  if [[ "$exit_status" -ne 0 && "${AYYO_KEEP_FAILED_SMOKE:-0}" == "1" ]]; then
    printf 'DEBUG: retained failed smoke artifacts at %s\n' "$smoke_root" >&2
  else
    rm -rf "$smoke_root"
  fi
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -f "$workspace_root/install/setup.bash" ]]; then
  printf 'Workspace is not built; run scripts/build_workspace.sh first.\n' >&2
  exit 1
fi

# shellcheck disable=SC1091
set +u
source /opt/ros/jazzy/setup.bash
source "$workspace_root/install/setup.bash"
set -u

export ROS_DOMAIN_ID="$smoke_domain_id"
export GZ_PARTITION="$smoke_partition"
export ROS_LOG_DIR="$smoke_root/ros_logs"
export GZ_HOMEDIR="$smoke_root/gz_home"
mkdir -p "$ROS_LOG_DIR" "$GZ_HOMEDIR"

ros2 pkg prefix ayyo_world_model >/dev/null
ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_control:=true enable_development_control:=true \
  enable_world_model:=true enable_localization:=true

wait_until() {
  local description="$1"
  local check_function="$2"
  local attempts="$3"
  shift 3
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,420p' "$launch_log" >&2
      return 1
    fi
    if "$check_function" "$@"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,420p' "$launch_log" >&2
  return 1
}

world_model_active() {
  ros2 lifecycle get /ayyo_world_model 2>/dev/null \
    | grep -q '^active \[3\]$'
}

trusted_body_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
pose = state["base_pose"]
raise SystemExit(
    0 if state["status"] == 1
    and len(state["joint_names"]) == 18
    and state["imu"] is not None
    and pose is not None
    and pose["source_frame_id"] == "odom"
    and pose["target_frame_id"] == "base_link"
    else 1
)
' "$smoke_root/body.json"
}

query_body() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py >"$1"
}

health_absent() {
  local output="$1"
  query_body "$output" 2>/dev/null || return 1
  python3 -c '
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
reviewed = {"ayyo.joint-state.body.v1", "ayyo.imu.body.v1"}
raise SystemExit(0 if all(
    item["health"] is None for item in state["sensors"]
    if item["sensor_id"] in reviewed
) else 1)
' "$output"
}

wait_until 'localization/diagnostics lifecycle is active' world_model_active 200
wait_until 'actual Gazebo localization reaches the trusted body query' trusted_body_ready 200

odom_info="$(ros2 topic info /ayyo/localization/odometry --verbose)"
grep -q 'Type: nav_msgs/msg/Odometry' <<<"$odom_info"
grep -q 'Publisher count: 1' <<<"$odom_info"

python3 -c '
import json
import math
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
pose = state["base_pose"]
assert pose is not None
assert pose["source_kind"] == "simulation"
assert pose["source_id"] == "ros.body-pose.simulation.localization.v1"
assert pose["source_clock"] == "ros_simulation_time"
assert pose["source_transport"] == "ros2"
assert pose["source_interface"] == "nav-msgs.odometry-tf2.v1"
assert pose["covariance"] is None
assert pose["quality"] is None
assert pose["observation_id"].startswith("world-observation-")
assert pose["observation_fingerprint"].startswith("body_pose:sha256:")
assert pose["observed_at_ns"] <= state["queried_at_ns"]
assert all(math.isfinite(value) for value in pose["translation_xyz"])
assert all(math.isfinite(value) for value in pose["orientation_xyzw"])
assert any(abs(value) > 0.0 for value in pose["translation_xyz"])
for sensor_id in ("ayyo.joint-state.body.v1", "ayyo.imu.body.v1"):
    sensor = next(item for item in state["sensors"] if item["sensor_id"] == sensor_id)
    assert sensor["health"] is None
' "$smoke_root/body.json"
printf 'PASS: pose retains exact frames, simulation provenance, and unknown uncertainty\n'
printf 'PASS: absent diagnostics did not become healthy evidence\n'

python3 "$repository_root/scripts/perception_test_fixture.py" \
  --scenario unknown_diagnostic
python3 "$repository_root/scripts/perception_test_fixture.py" \
  --scenario wrong_localization_frame
sleep 0.25
query_body "$smoke_root/rejected.json"
python3 -c '
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["base_pose"]["source_frame_id"] == "odom"
assert state["base_pose"]["target_frame_id"] == "base_link"
assert all(item["health"] is None for item in state["sensors"] if item["sensor_id"] in {
    "ayyo.joint-state.body.v1", "ayyo.imu.body.v1"
})
' "$smoke_root/rejected.json"
printf 'PASS: unknown diagnostics and wrong-frame localization fail closed\n'

for diagnostic_case in 'joint ok' 'imu warn' 'imu error' 'imu stale'; do
  read -r component level <<<"$diagnostic_case"
  python3 "$repository_root/scripts/perception_test_fixture.py" \
    --scenario diagnostic --component "$component" --level "$level" \
    --verify-query >"$smoke_root/diagnostic_${component}_${level}.json"
done
printf 'PASS: ROS OK, WARN, ERROR, and STALE traverse the live diagnostics trust path\n'

sleep 2.15
wait_until 'expired diagnostics disappear instead of becoming healthy' \
  health_absent 40 "$smoke_root/health_expired.json"

before_position="$(python3 -c '
import json,sys
state=json.load(open(sys.argv[1]))
print(state["positions"][state["joint_names"].index("neck_yaw_joint")])
' "$smoke_root/health_expired.json")"
ros2 run ayyo_simulation_control development_command.py --position 0.1 \
  >"$smoke_root/motion.json"
query_body "$smoke_root/after_motion.json"
python3 -c '
import json
import sys
state=json.load(open(sys.argv[1]))
position=state["positions"][state["joint_names"].index("neck_yaw_joint")]
assert abs(position - 0.1) <= 0.01
assert abs(position - float(sys.argv[2])) >= 0.001
assert state["base_pose"] is not None
' "$smoke_root/after_motion.json" "$before_position"
printf 'PASS: bounded development motion remains independent from observation authority\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: localization/diagnostics adapter reported an unclean lifecycle\n' >&2
  sed -n '1,460p' "$launch_log" >&2
  exit 1
fi
remaining_nodes=""
for _ in {1..40}; do
  remaining_nodes="$(ros2 node list --no-daemon 2>/dev/null)"
  if [[ -z "$remaining_nodes" ]]; then
    break
  fi
  sleep 0.25
done
if [[ -n "$remaining_nodes" ]]; then
  printf 'FAIL: isolated ROS graph was not empty after shutdown\n' >&2
  printf '%s\n' "$remaining_nodes" >&2
  exit 1
fi
printf 'PASS: localization/diagnostics owned-process set is empty after bounded shutdown\n'
printf 'PASS: Body Localization and Sensor Diagnostics Foundation v1 smoke completed\n'
