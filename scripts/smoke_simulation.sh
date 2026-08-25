#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-simulation-smoke.XXXXXX)"
readonly launch_log="$smoke_root/simulation.log"
readonly smoke_domain_id="${AYYO_SMOKE_DOMAIN_ID:-97}"
readonly smoke_partition="ayyo_simulation_smoke_$$"
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

ros2 pkg prefix ayyo_description >/dev/null
ros2 pkg prefix ayyo_simulation >/dev/null
ros2 run ayyo_description validate_description.py

ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation simulation.launch.py headless:=true

wait_until() {
  local description="$1"
  local check_function="$2"
  for _ in {1..120}; do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,240p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,240p' "$launch_log" >&2
  return 1
}

simulation_nodes_ready() {
  local nodes
  nodes="$(ros2 node list 2>/dev/null || true)"
  grep -qx '/ayyo_clock_bridge' <<<"$nodes" &&
    grep -qx '/ayyo_sim_joint_state_publisher' <<<"$nodes" &&
    grep -qx '/ayyo_sim_robot_state_publisher' <<<"$nodes"
}

tf_ready() {
  timeout 2 ros2 topic echo --once /tf tf2_msgs/msg/TFMessage \
    >/dev/null 2>&1
}

clock_ready() {
  timeout 2 ros2 topic echo --once /clock rosgraph_msgs/msg/Clock \
    >/dev/null 2>&1
}

model_ready() {
  local models
  models="$(gz model --list 2>/dev/null || true)"
  grep -qw 'ayyo' <<<"$models" && grep -qw 'ground_plane' <<<"$models"
}

wait_until 'ROS simulation nodes are running' simulation_nodes_ready
wait_until 'TF is available' tf_ready
wait_until 'ROS-Gazebo clock bridge is healthy' clock_ready
wait_until 'Ayyo entity is spawned in Gazebo' model_ready
ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|unable to convert call argument|Unable to convert call argument' \
  "$launch_log"; then
  printf 'FAIL: simulation reported an unclean joint-state or launch shutdown\n' >&2
  sed -n '1,300p' "$launch_log" >&2
  exit 1
fi
printf 'PASS: simulation owned-process set is empty after bounded shutdown\n'

printf 'PASS: headless simulation smoke validation completed\n'
