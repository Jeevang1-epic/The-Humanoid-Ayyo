#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly smoke_root="$(mktemp -d -t ayyo-perception-smoke.XXXXXX)"
readonly launch_log="$smoke_root/perception.log"
readonly default_domain_id="$((140 + ($$ % 60)))"
readonly smoke_domain_id="${AYYO_PERCEPTION_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_perception_smoke_$$"
launch_pid=""

cleanup() {
  if [[ -n "$launch_pid" ]] && kill -0 "$launch_pid" 2>/dev/null; then
    kill -INT "$launch_pid" 2>/dev/null || true
    for _ in {1..50}; do
      if ! kill -0 "$launch_pid" 2>/dev/null; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "$launch_pid" 2>/dev/null; then
      kill -TERM "$launch_pid" 2>/dev/null || true
    fi
    wait "$launch_pid" 2>/dev/null || true
  fi
  rm -rf "$smoke_root"
}
trap cleanup EXIT INT TERM

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
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_world_model:=true >"$launch_log" 2>&1 &
launch_pid=$!

wait_until() {
  local description="$1"
  local check_function="$2"
  for _ in {1..180}; do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,340p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,340p' "$launch_log" >&2
  return 1
}

world_model_active() {
  ros2 lifecycle get /ayyo_world_model 2>/dev/null | grep -q 'active'
}

trusted_imu_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
imu = state["imu"]
raise SystemExit(
    0
    if state["status"] == 1
    and imu is not None
    and imu["availability"] == 1
    and imu["freshness"] == 1
    else 1
)
' "$smoke_root/body.json"
}

wait_for_launch_exit() {
  for _ in {1..100}; do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      wait "$launch_pid" 2>/dev/null || true
      launch_pid=""
      return 0
    fi
    sleep 0.1
  done
  return 1
}

shutdown_launch() {
  kill -INT "$launch_pid"
  if wait_for_launch_exit; then
    return 0
  fi
  kill -TERM "$launch_pid"
  if wait_for_launch_exit; then
    return 0
  fi
  printf 'FAIL: perception launch survived bounded SIGINT and SIGTERM\n' >&2
  return 1
}

wait_until 'perception lifecycle is active' world_model_active
wait_until 'Gazebo IMU evidence reaches the trusted World Model path' trusted_imu_ready

topic_info="$(ros2 topic info /ayyo/imu/data --verbose)"
grep -q 'Type: sensor_msgs/msg/Imu' <<<"$topic_info"
grep -q 'Publisher count: 1' <<<"$topic_info"

python3 -c '
import json
import math
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
imu = state["imu"]
assert imu is not None
assert imu["sensor_id"] == "ayyo.imu.body.v1"
assert imu["frame_id"] == "imu_link"
assert imu["source_kind"] == "simulation"
assert imu["source_clock"] == "ros_simulation_time"
assert imu["source_transport"] == "ros2"
assert imu["observation_id"].startswith("world-observation-")
assert imu["observation_fingerprint"].startswith("imu:sha256:")
assert imu["observed_at_ns"] <= state["queried_at_ns"]
vectors = (
    imu["orientation_xyzw"],
    imu["angular_velocity_xyz"],
    imu["linear_acceleration_xyz"],
)
assert any(vector is not None for vector in vectors)
assert all(math.isfinite(value) for vector in vectors if vector for value in vector)
assert state["base_pose"] is None
assert state["base_pose_availability"] == 0
assert len(state["sensors"]) == 4
assert state["snapshot_id"].startswith("world-snapshot-")
assert state["perception_accepted_count"] >= 2
' "$smoke_root/body.json"
printf 'PASS: canonical IMU evidence retains frame, clock, provenance, and missing-data semantics\n'
printf 'PASS: body pose remains explicitly unavailable without localization evidence\n'

ros2 lifecycle set /ayyo_world_model deactivate >/dev/null
set +e
deactivated_output="$(ros2 run ayyo_world_model body_state_query.py 2>/dev/null)"
deactivated_status=$?
set -e
[[ "$deactivated_status" -eq 2 ]]
python3 -c '
import json
import sys

state = json.loads(sys.argv[1].splitlines()[0])
assert state["status"] == 0
assert state["availability"] == 0
' "$deactivated_output"
printf 'PASS: deactivation removes sensor subscriptions and closes the query readiness boundary\n'

ros2 lifecycle set /ayyo_world_model activate >/dev/null
wait_until 'reactivated adapter admits new IMU evidence' trusted_imu_ready

shutdown_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: perception adapter reported an unclean lifecycle\n' >&2
  sed -n '1,380p' "$launch_log" >&2
  exit 1
fi
printf 'PASS: perception lifecycle and simulation processes shut down cleanly\n'
printf 'PASS: Gazebo to ROS to trust boundary to Working Memory to World Model proof completed\n'
