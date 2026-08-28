#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-visual-camera-smoke.XXXXXX)"
readonly launch_log="$smoke_root/visual_camera.log"
readonly default_domain_id="$((220 + ($$ % 10)))"
readonly smoke_domain_id="${AYYO_VISUAL_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_visual_camera_smoke_$$"
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
ros2 pkg prefix ros_gz_image >/dev/null
ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_control:=true enable_development_control:=true \
  enable_world_model:=true enable_camera:=true

wait_until() {
  local description="$1"
  local check_function="$2"
  local attempts="${3:-200}"
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,460p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,460p' "$launch_log" >&2
  return 1
}

world_model_active() {
  ros2 lifecycle get /ayyo_world_model 2>/dev/null \
    | grep -q '^active \[3\]$'
}

ayyo_spawned() {
  gz model --list 2>/dev/null | grep -q -- '- ayyo$'
}

trusted_visual_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
visual = state["visual_frame"]
raise SystemExit(
    0 if state["status"] == 1
    and visual is not None
    and visual["availability"] == 1
    and visual["freshness"] == 1
    else 1
)
' "$smoke_root/body.json"
}

wrong_frame_logged() {
  grep -Eq 'Image frame does not match|CameraInfo frame does not match' "$launch_log"
}

wait_until 'visual adapter lifecycle is active' world_model_active
wait_until 'canonical Ayyo entity is spawned' ayyo_spawned
wait_until 'trusted visual metadata reaches the read-only query' trusted_visual_ready

python3 "$repository_root/scripts/visual_test_fixture.py" \
  --scenario verify_stream >"$smoke_root/stream.json"
python3 -c '
import json
import sys
stream = json.load(open(sys.argv[1], encoding="utf-8"))
assert stream == {
    "data_size_bytes": 230400,
    "encoding": "rgb8",
    "frame_id": "head_camera_optical_frame",
    "height": 240,
    "source_timestamp_ns": stream["source_timestamp_ns"],
    "width": 320,
}
assert stream["source_timestamp_ns"] > 0
' "$smoke_root/stream.json"
printf 'PASS: actual nonempty RGB image and matching CameraInfo carry exact optical frame and source time\n'

image_info="$(ros2 topic info /ayyo/camera/head/image_raw --verbose)"
camera_info="$(ros2 topic info /ayyo/camera/head/camera_info --verbose)"
grep -q 'Type: sensor_msgs/msg/Image' <<<"$image_info"
grep -q 'Publisher count: 1' <<<"$image_info"
grep -q 'Type: sensor_msgs/msg/CameraInfo' <<<"$camera_info"
grep -q 'Publisher count: 1' <<<"$camera_info"

python3 -c '
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
visual = state["visual_frame"]
assert visual is not None
assert visual["sensor_id"] == "ayyo.camera.head.rgb.v1"
assert visual["frame_id"] == "head_camera_optical_frame"
assert visual["source_kind"] == "simulation"
assert visual["source_id"] == "ros.camera.head.simulation.gz-harmonic.v1"
assert visual["source_clock"] == "ros_simulation_time"
assert visual["source_transport"] == "ros2"
assert visual["source_interface"] == "sensor-msgs.image-camera-info.v1"
assert visual["width"] == 320 and visual["height"] == 240
assert visual["encoding"] == "rgb8" and visual["step"] == 960
assert visual["data_size_bytes"] == 230400
assert visual["observed_at_ns"] > 0
assert visual["observed_at_ns"] <= state["queried_at_ns"]
assert visual["calibration_id"].startswith("camera-calibration-sha256-")
assert visual["observation_id"].startswith("world-observation-")
assert visual["observation_fingerprint"].startswith("visual_frame:sha256:")
assert state["current_visual_count"] == 1
assert state["recent_evidence_count"] <= 256
camera = next(item for item in state["sensors"] if item["sensor_id"] == visual["sensor_id"])
assert camera["health"] is None
' "$smoke_root/body.json"
printf 'PASS: trusted simulation provenance, calibration identity, bounded state, and absent health are explicit\n'

python3 "$repository_root/scripts/visual_test_fixture.py" \
  --scenario adversarial_contracts >"$smoke_root/adversarial.json"
python3 -c '
import json
import sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["malformed_rejected"] is True
assert result["physical_substitution"] == "clock_domain_mismatch"
assert result["wrong_frame"] == "frame_mismatch"
' "$smoke_root/adversarial.json"
printf 'PASS: malformed evidence and simulation-to-physical provenance substitution fail closed\n'

python3 "$repository_root/scripts/visual_test_fixture.py" \
  --scenario wrong_frame >"$smoke_root/wrong_frame.json"
wait_until 'wrong-frame ROS camera source is rejected by the live adapter' wrong_frame_logged 40
wait_until 'valid source remains trusted after adversarial traffic' trusted_visual_ready 40
python3 -c '
import json
import sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
assert state["visual_frame"]["frame_id"] == "head_camera_optical_frame"
assert state["visual_frame"]["source_kind"] == "simulation"
assert state["current_visual_count"] == 1
' "$smoke_root/body.json"

before_position="$(python3 -c '
import json,sys
state=json.load(open(sys.argv[1]))
print(state["positions"][state["joint_names"].index("neck_yaw_joint")])
' "$smoke_root/body.json")"
ros2 run ayyo_simulation_control development_command.py --position 0.1 \
  >"$smoke_root/motion.json"
wait_until 'visual evidence remains available after bounded neck motion' trusted_visual_ready 40
python3 -c '
import json
import sys
state=json.load(open(sys.argv[1]))
position=state["positions"][state["joint_names"].index("neck_yaw_joint")]
assert abs(position - 0.1) <= 0.01
assert abs(position - float(sys.argv[2])) >= 0.001
assert state["visual_frame"] is not None
' "$smoke_root/body.json" "$before_position"
printf 'PASS: existing bounded neck motion remains independent of visual observation\n'

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
ros2 lifecycle set /ayyo_world_model activate >/dev/null
wait_until 'reactivated adapter admits new visual evidence' trusted_visual_ready 60
printf 'PASS: camera subscriptions obey lifecycle deactivate/reactivate boundaries\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: visual camera adapter reported an unclean lifecycle\n' >&2
  sed -n '1,500p' "$launch_log" >&2
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
printf 'PASS: visual-camera owned-process set is empty after bounded shutdown\n'
printf 'PASS: Head RGB Camera and Visual Observation Foundation v1 smoke completed\n'
