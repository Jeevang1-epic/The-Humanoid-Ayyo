#!/usr/bin/env bash

set -euo pipefail

readonly workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../ros2_ws" && pwd)"

# shellcheck disable=SC1091
set +u
source /opt/ros/jazzy/setup.bash
set -u

cd "$workspace_root"
colcon build --symlink-install
