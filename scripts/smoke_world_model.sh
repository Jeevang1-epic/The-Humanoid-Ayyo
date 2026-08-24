#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly smoke_root="$(mktemp -d -t ayyo-world-model-smoke.XXXXXX)"
readonly launch_log="$smoke_root/world_model.log"
readonly default_domain_id="$((120 + ($$ % 80)))"
readonly smoke_domain_id="${AYYO_WORLD_MODEL_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_world_model_smoke_$$"
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
  headless:=true enable_control:=true enable_development_control:=true \
  enable_world_model:=true >"$launch_log" 2>&1 &
launch_pid=$!

wait_until() {
  local description="$1"
  local check_function="$2"
  for _ in {1..180}; do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,300p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,300p' "$launch_log" >&2
  return 1
}

world_model_active() {
  local state service_type
  state="$(ros2 lifecycle get /ayyo_world_model 2>/dev/null || true)"
  service_type="$(
    ros2 service type /ayyo/world_model/get_robot_body_state 2>/dev/null || true
  )"
  grep -q 'active' <<<"$state" &&
    [[ "$service_type" == 'ayyo_interfaces/srv/GetRobotBodyState' ]]
}

body_state_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/current.json" 2>/dev/null
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
  printf 'FAIL: World Model launch survived bounded SIGINT and SIGTERM\n' >&2
  return 1
}

wait_until 'World Model lifecycle and fixed query service are active' world_model_active
wait_until 'standard joint-state evidence reaches Working Memory' body_state_ready
cp "$smoke_root/current.json" "$smoke_root/initial.json"

python3 -c '
import json
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["status"] == 1
assert state["robot_id"] == "ayyo.robot.v1"
assert state["availability"] == 2
assert state["known_joint_count"] == 18
assert len(state["joint_names"]) == 18
assert state["source_kind"] == "simulation"
assert state["source_clock"] == "ros_simulation_time"
assert state["source_transport"] == "ros2"
assert all(value == 1 for value in state["joint_freshness"])
assert max(state["joint_observed_at_ns"]) <= state["queried_at_ns"]
assert state["snapshot_id"].startswith("world-snapshot-")
assert state["snapshot_fingerprint"].startswith("world_snapshot:sha256:")
assert all(value.startswith("world-observation-") for value in state["joint_observation_ids"])
' "$smoke_root/initial.json"
printf 'PASS: World Model exposes a fresh provenance-bound complete body snapshot\n'

ros2 run ayyo_simulation_control development_command.py --position 0.1 \
  >"$smoke_root/control.json"

motion_observed() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/final.json" 2>/dev/null || return 1
  python3 -c '
import json
import sys

state = json.load(open(sys.argv[1], encoding="utf-8"))
index = state["joint_names"].index("neck_yaw_joint")
raise SystemExit(0 if abs(state["positions"][index] - 0.1) <= 0.01 else 1)
' "$smoke_root/final.json"
}
wait_until 'observed feedback updates the neck state after bounded motion' motion_observed

python3 -c '
import json
import sys

initial = json.load(open(sys.argv[1], encoding="utf-8"))
final = json.load(open(sys.argv[2], encoding="utf-8"))
initial_index = initial["joint_names"].index("neck_yaw_joint")
final_index = final["joint_names"].index("neck_yaw_joint")
assert abs(final["positions"][final_index] - 0.1) <= 0.01
assert abs(final["positions"][final_index] - initial["positions"][initial_index]) >= 0.001
assert final["joint_observed_at_ns"][final_index] >= initial["joint_observed_at_ns"][initial_index]
assert final["joint_observation_ids"][final_index] != initial["joint_observation_ids"][initial_index]
assert final["snapshot_id"] != initial["snapshot_id"]
' "$smoke_root/initial.json" "$smoke_root/final.json"
printf 'PASS: command intent stayed separate from observation-backed World Model change\n'

shutdown_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: World Model adapter reported an unclean lifecycle\n' >&2
  sed -n '1,340p' "$launch_log" >&2
  exit 1
fi
printf 'PASS: World Model lifecycle and simulation processes shut down cleanly\n'
printf 'PASS: embodied body-state integration smoke validation completed\n'
