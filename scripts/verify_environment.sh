#!/usr/bin/env bash

set -euo pipefail

failures=0

pass() {
  printf 'PASS: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]]; then
    pass "Ubuntu 24.04"
  else
    fail "Ubuntu 24.04 required; found ${PRETTY_NAME:-unknown operating system}"
  fi
else
  fail "cannot read /etc/os-release"
fi

if [[ "${ROS_DISTRO:-}" == "jazzy" ]]; then
  pass "ROS_DISTRO is jazzy"
else
  fail "ROS_DISTRO must be jazzy; found ${ROS_DISTRO:-unset}"
fi

for command_name in ros2 colcon gz rviz2; do
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$command_name is available"
  else
    fail "$command_name is not available"
  fi
done

if command -v gz >/dev/null 2>&1; then
  if gz sim --version 2>&1 | grep -q 'version 8\.'; then
    pass "Gazebo Harmonic is available"
  else
    fail "Gazebo Harmonic could not be verified"
  fi
fi

for package_name in \
  ros_gz_bridge \
  moveit_ros_move_group \
  nav2_bringup \
  controller_manager; do
  if command -v ros2 >/dev/null 2>&1 && ros2 pkg prefix "$package_name" >/dev/null 2>&1; then
    pass "ROS package $package_name is available"
  else
    fail "ROS package $package_name is not available"
  fi
done

if ((failures > 0)); then
  printf 'FAIL: environment verification found %d problem(s)\n' "$failures" >&2
  exit 1
fi

pass "environment verification completed"
