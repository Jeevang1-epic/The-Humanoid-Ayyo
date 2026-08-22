#!/usr/bin/env bash

set -euo pipefail

readonly workspace_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../ros2_ws" && pwd)"

# shellcheck disable=SC1091
set +u
source /opt/ros/jazzy/setup.bash
set -u

if [[ ! -f "$workspace_root/install/setup.bash" ]]; then
  printf 'Workspace is not built; run scripts/build_workspace.sh first.\n' >&2
  exit 1
fi

# shellcheck disable=SC1091
set +u
source "$workspace_root/install/setup.bash"
set -u

cd "$workspace_root"
colcon test
colcon test-result --verbose
