#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-head-rgbd-fusion-smoke.XXXXXX)"
readonly focused_log="$smoke_root/focused.log"
readonly default_off_log="$smoke_root/default_off.log"
readonly enabled_log="$smoke_root/enabled.log"
readonly default_domain_id="$((155 + ($$ % 30)))"
readonly smoke_domain_id="${AYYO_HEAD_RGBD_FUSION_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_head_rgbd_fusion_smoke_$$"
launch_pid=""
launch_log=""

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
if [[ ! "$smoke_domain_id" =~ ^[0-9]+$ ]] \
  || ((smoke_domain_id < 0 || smoke_domain_id > 232)); then
  printf 'FAIL: ROS_DOMAIN_ID must be an integer from 0 through 232\n' >&2
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
mkdir -p "$ROS_LOG_DIR"

if [[ -n "$(ros2 node list --no-daemon 2>/dev/null)" ]]; then
  printf 'FAIL: isolated ROS graph was not empty before launch\n' >&2
  exit 1
fi

{
  python3 -m pytest -q "$repository_root/rgbd_fusion/tests"
  python3 -m pytest -q \
    "$repository_root/perception/tests/test_rgbd_fusion_boundary.py"
  python3 -m pytest -q \
    "$repository_root/working_memory/tests/test_rgbd_fusion_resources.py"
  python3 -m pytest -q \
    "$repository_root/world_model/tests/test_rgbd_fusion.py"
} >"$focused_log" 2>&1
grep -q '18 passed' "$focused_log"
grep -q '2 passed' "$focused_log"
grep -q '3 passed' "$focused_log"
grep -q '4 passed' "$focused_log"
printf 'PASS: exact-time, adversarial, lifecycle, sealed-admission, and 5000-cycle resource proofs pass\n'

wait_until() {
  local description="$1"
  local check_function="$2"
  local attempts="${3:-200}"
  local attempt
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,500p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,500p' "$launch_log" >&2
  return 1
}

world_model_active() {
  ros2 lifecycle get /ayyo_world_model 2>/dev/null | grep -q '^active \[3\]$'
}

graph_empty() {
  [[ -z "$(ros2 node list --no-daemon 2>/dev/null)" ]]
}

launch_log="$default_off_log"
ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation head_rgbd_fusion_fixture.launch.py \
  enable_head_rgbd_fusion_fixture:=false \
  depth_camera_profile:=unconfigured \
  rgbd_fusion_profile:=unconfigured
wait_until 'default-off RGB-D composition reaches active lifecycle' world_model_active
set +e
default_query="$(ros2 run ayyo_world_model body_state_query.py 2>/dev/null)"
default_query_status=$?
set -e
[[ "$default_query_status" -eq 2 ]]
python3 -c '
import json,sys
state=json.loads(sys.argv[1].splitlines()[0])
assert state["status"] == 0
assert state["fused_rgbd"] is None
assert state["current_fused_rgbd_count"] == 0
assert not any(item["kind"] == "rgbd_fusion" for item in state["sensors"])
' "$default_query"
for topic in \
  /ayyo/camera/head/image_raw \
  /ayyo/camera/head/camera_info \
  /ayyo/camera/head/depth/image_raw \
  /ayyo/camera/head/depth/camera_info; do
  topic_info="$(ros2 topic info "$topic" --verbose 2>/dev/null || true)"
  if grep -q 'Publisher count: [1-9]' <<<"$topic_info"; then
    printf 'FAIL: default-off RGB-D path published %s\n' "$topic" >&2
    exit 1
  fi
done
ayyo_smoke_shutdown_owned_launch
for _ in {1..40}; do
  graph_empty && break
  sleep 0.25
done
graph_empty
printf 'PASS: default-off RGB-D composition publishes no camera evidence and leaves no graph\n'

launch_log="$enabled_log"
ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation head_rgbd_fusion_fixture.launch.py \
  enable_head_rgbd_fusion_fixture:=true \
  depth_camera_profile:=test_fixture_v1 \
  rgbd_fusion_profile:=exact_test_fixture_v1 \
  world_model_retention_ttl_ms:=10000

trusted_rgbd_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
fused=state["fused_rgbd"]
raise SystemExit(0 if state["status"] == 1
  and state["visual_frame"] is not None
  and state["depth_frame"] is not None
  and fused is not None
  and fused["availability"] == 1
  and fused["freshness"] == 1
  else 1)
' "$smoke_root/body.json"
}

wait_until 'head RGB-D lifecycle is active' world_model_active
wait_until 'sealed exact-time RGB-D reaches the read-only query' trusted_rgbd_ready

[[ "$(ros2 topic type /ayyo/camera/head/image_raw)" == 'sensor_msgs/msg/Image' ]]
[[ "$(ros2 topic type /ayyo/camera/head/camera_info)" == 'sensor_msgs/msg/CameraInfo' ]]
[[ "$(ros2 topic type /ayyo/camera/head/depth/image_raw)" == 'sensor_msgs/msg/Image' ]]
[[ "$(ros2 topic type /ayyo/camera/head/depth/camera_info)" == 'sensor_msgs/msg/CameraInfo' ]]
printf 'PASS: canonical RGB and depth channels retain standard Image/CameraInfo types\n'

python3 -c '
import json,re,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
rgb=state["visual_frame"]
depth=state["depth_frame"]
fused=state["fused_rgbd"]
assert state["current_visual_count"] == 1
assert state["current_depth_count"] == 1
assert state["current_fused_rgbd_count"] == 1
assert fused["observed_at_ns"] == rgb["observed_at_ns"] == depth["observed_at_ns"]
assert fused["result_at_ns"] >= fused["observed_at_ns"]
assert fused["pair_id"].startswith("rgbd-pair-sha256-")
assert fused["pairing_policy_id"] == "ayyo.rgbd.exact-source-time.v1"
assert fused["pairing_policy_version"] == "1.0.0"
assert fused["synchronization_session_id"].startswith("rgbd-synchronization-session-sha256-")
assert fused["spatial_registration_validated"] is False
assert fused["source_kind"] == "test_fixture"
assert fused["source_id"] == "ayyo.rgbd.head.test-synchronizer.v1"
assert fused["source_clock"] == "test_time"
assert fused["source_transport"] == "direct"
assert fused["rgb"]["observation_id"] == rgb["observation_id"]
assert fused["rgb"]["sensor_id"] == "ayyo.camera.head.rgb.v1"
assert fused["rgb"]["camera_frame_id"] == "head_camera_frame"
assert fused["rgb"]["optical_frame_id"] == "head_camera_optical_frame"
assert fused["rgb"]["calibration_id"] == rgb["calibration_id"]
assert fused["rgb"]["source_id"] == "ros.camera.head.rgb.depth.test-fixture.v1"
assert fused["rgb"]["source_transport"] == "ros2"
assert fused["depth"]["observation_id"] == depth["observation_id"]
assert fused["depth"]["sensor_id"] == "ayyo.camera.head.depth.v1"
assert fused["depth"]["camera_frame_id"] == "head_depth_camera_frame"
assert fused["depth"]["optical_frame_id"] == "head_depth_camera_optical_frame"
assert fused["depth"]["calibration_id"] == depth["calibration_id"]
assert fused["depth"]["source_id"] == "ros.camera.head.depth.test-fixture.v1"
assert fused["depth"]["source_transport"] == "ros2"
assert fused["depth"]["source_fingerprint_sha256"] == depth["source_manifest_id"].split("-")[-1]
assert re.fullmatch(r"[0-9a-f]{64}", fused["rgb"]["source_fingerprint_sha256"])
assert "data" not in fused["rgb"] and "data" not in fused["depth"]
assert state["recent_evidence_count"] <= 256
' "$smoke_root/body.json"
printf 'PASS: exact source time, deterministic identity, component provenance, frames, calibration, sessions, and compactness are preserved\n'

services="$(ros2 service list --no-daemon)"
for forbidden in cmd_vel trajectory navigation manipulation skill execute actuator motor; do
  if grep -qi "$forbidden" <<<"$services"; then
    printf 'FAIL: RGB-D composition exposed forbidden authority: %s\n' \
      "$forbidden" >&2
    exit 1
  fi
done
printf 'PASS: fused RGB-D evidence exposes no motion, skill, or actuator authority\n'

before_pair="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fused_rgbd"]["pair_id"])' "$smoke_root/body.json")"
before_rgb_session="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fused_rgbd"]["rgb"]["session_id"])' "$smoke_root/body.json")"
before_depth_session="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fused_rgbd"]["depth"]["session_id"])' "$smoke_root/body.json")"
before_sync_session="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["fused_rgbd"]["synchronization_session_id"])' "$smoke_root/body.json")"

ros2 lifecycle set /ayyo_world_model deactivate >/dev/null
sleep 0.5
set +e
deactivated_query="$(ros2 run ayyo_world_model body_state_query.py 2>/dev/null)"
deactivated_status=$?
set -e
[[ "$deactivated_status" -eq 2 ]]
python3 -c '
import json,sys
state=json.loads(sys.argv[1].splitlines()[0])
assert state["status"] == 0
assert state["fused_rgbd"] is None
' "$deactivated_query"
ros2 lifecycle set /ayyo_world_model activate >/dev/null
wait_until 'reactivation admits a distinct RGB-D source epoch' trusted_rgbd_ready 80
python3 -c '
import json,sys
fused=json.load(open(sys.argv[1], encoding="utf-8"))["fused_rgbd"]
assert fused["pair_id"] != sys.argv[2]
assert fused["rgb"]["session_id"] != sys.argv[3]
assert fused["depth"]["session_id"] != sys.argv[4]
assert fused["synchronization_session_id"] != sys.argv[5]
' "$smoke_root/body.json" "$before_pair" "$before_rgb_session" \
  "$before_depth_session" "$before_sync_session"
printf 'PASS: deactivate clears fused readiness and reactivation isolates a new RGB/depth/synchronization session\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' \
  "$launch_log"; then
  printf 'FAIL: RGB-D composition reported an unclean lifecycle\n' >&2
  sed -n '1,520p' "$launch_log" >&2
  exit 1
fi
remaining_nodes=""
for _ in {1..40}; do
  remaining_nodes="$(ros2 node list --no-daemon 2>/dev/null)"
  [[ -z "$remaining_nodes" ]] && break
  sleep 0.25
done
if [[ -n "$remaining_nodes" ]]; then
  printf 'FAIL: isolated ROS graph was not empty after shutdown\n%s\n' \
    "$remaining_nodes" >&2
  exit 1
fi
if [[ -n "$(ayyo_smoke_owned_pids)" ]]; then
  printf 'FAIL: RGB-D smoke retained owned processes after shutdown\n' >&2
  ayyo_smoke_owned_processes >&2
  exit 1
fi
printf 'PASS: owned-process set and isolated ROS graph are empty after shutdown\n'
printf 'PASS: Head RGB-D Synchronization and Fused Observation Foundation v1 smoke completed\n'
