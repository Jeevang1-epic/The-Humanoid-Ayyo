#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly smoke_root="$(mktemp -d -t ayyo-control-smoke.XXXXXX)"
readonly launch_log="$smoke_root/simulation_control.log"
readonly invalid_error="$smoke_root/invalid_command.err"
readonly default_domain_id="$((100 + ($$ % 100)))"
readonly smoke_domain_id="${AYYO_CONTROL_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_control_smoke_$$"
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

ros2 pkg prefix ayyo_simulation_control >/dev/null
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_control:=true enable_development_control:=true \
  >"$launch_log" 2>&1 &
launch_pid=$!

wait_until() {
  local description="$1"
  local check_function="$2"
  for _ in {1..160}; do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,260p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,260p' "$launch_log" >&2
  return 1
}

controlled_nodes_ready() {
  local nodes
  nodes="$(ros2 node list --no-daemon 2>/dev/null || true)"
  grep -qx '/ayyo_clock_bridge' <<<"$nodes" &&
    grep -qx '/ayyo_sim_robot_state_publisher' <<<"$nodes" &&
    grep -qx '/ayyo_simulation_control' <<<"$nodes" &&
    ! grep -qx '/ayyo_sim_joint_state_publisher' <<<"$nodes"
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
      '^ayyo_neck_position_controller[[:space:]]+forward_command_controller/ForwardCommandController[[:space:]]+active$' \
      <<<"$controllers"
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
  [[ "$command_count" -eq 1 ]] &&
    grep -Eq \
      '^[[:space:]]+neck_yaw_joint/position[[:space:]]+\[available\][[:space:]]+\[claimed\]$' \
      <<<"$interfaces"
}

joint_states_ready() {
  local information sample
  information="$(ros2 topic info /joint_states --no-daemon 2>/dev/null || true)"
  grep -qx 'Publisher count: 1' <<<"$information" || return 1
  sample="$(
    timeout 3 ros2 topic echo --once /joint_states sensor_msgs/msg/JointState \
      2>/dev/null || true
  )"
  grep -q 'neck_yaw_joint' <<<"$sample"
}

development_service_ready() {
  local service_type
  service_type="$(
    ros2 service type /ayyo/development/set_joint_position 2>/dev/null || true
  )"
  [[ "$service_type" == 'ayyo_interfaces/srv/SetDevelopmentJointPosition' ]]
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
  printf 'FAIL: controlled launch survived bounded SIGINT and SIGTERM\n' >&2
  return 1
}

wait_until 'controlled ROS nodes are running without the development state publisher' \
  controlled_nodes_ready
wait_until 'joint-state and position controllers are active' controllers_ready
wait_until 'exactly one reviewed command interface is claimed' hardware_ready
wait_until 'joint_state_broadcaster is the sole authoritative state publisher' \
  joint_states_ready
wait_until 'typed development control service is available' development_service_ready

set +e
valid_output="$(
  ros2 run ayyo_simulation_control development_command.py --position 0.1
)"
valid_status=$?
set -e
if [[ "$valid_status" -ne 0 ]]; then
  printf 'FAIL: valid typed command exited %s\n%s\n' \
    "$valid_status" "$valid_output" >&2
  tail -160 "$launch_log" >&2
  exit 1
fi
python3 -c '
import json
import sys

result = json.loads(sys.argv[1])
assert result["status"] == 1
assert result["failure_code"] == ""
assert result["has_state_feedback"] is True
assert abs(result["final_position"] - 0.1) <= 0.01
assert abs(result["final_position"] - result["initial_position"]) >= 0.001
assert result["command_id"].startswith("control-command-")
assert result["result_id"].startswith("control-result-")
' "$valid_output"
printf 'PASS: typed bounded motion completed with correlated state feedback\n'

set +e
invalid_output="$(
  ros2 run ayyo_simulation_control development_command.py --position 1.3 \
    2>"$invalid_error"
)"
invalid_status=$?
set -e
[[ "$invalid_status" -eq 2 ]]
python3 -c '
import json
import sys

result = json.loads(sys.argv[1].splitlines()[0])
assert result["status"] == 0
assert result["failure_code"] == "above_maximum"
assert result["has_state_feedback"] is False
assert result["command_id"].startswith("control-command-")
assert result["result_id"].startswith("control-result-")
' "$invalid_output"
printf 'PASS: out-of-range typed command was rejected before dispatch\n'

shutdown_launch
if grep -Eq 'Traceback|exception was never retrieved' "$launch_log"; then
  printf 'FAIL: typed adapter reported an unclean shutdown\n' >&2
  sed -n '1,300p' "$launch_log" >&2
  exit 1
fi
printf 'PASS: controlled simulation processes shut down cleanly\n'
printf 'PASS: headless simulation control smoke validation completed\n'
