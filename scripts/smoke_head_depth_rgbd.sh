#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-head-depth-rgbd-smoke.XXXXXX)"
readonly fixture_log="$smoke_root/offline_fixture.log"
readonly default_off_log="$smoke_root/default_off.log"
readonly enabled_log="$smoke_root/head_depth.log"
readonly default_domain_id="$((120 + ($$ % 30)))"
readonly smoke_domain_id="${AYYO_HEAD_DEPTH_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_head_depth_smoke_$$"
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
if [[ ! "$smoke_domain_id" =~ ^[0-9]+$ ]] || ((smoke_domain_id < 0 || smoke_domain_id > 232)); then
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

preexisting_nodes="$(ros2 node list --no-daemon 2>/dev/null)"
if [[ -n "$preexisting_nodes" ]]; then
  printf 'FAIL: isolated ROS graph was not empty before launch\n%s\n' "$preexisting_nodes" >&2
  exit 1
fi

ayyo_smoke_start_owned_launch "$fixture_log" python3 "$repository_root/scripts/head_depth_rgbd_test_fixture.py"
if ! ayyo_smoke_wait_owned_exit 1200 0.05; then
  printf 'FAIL: transport-neutral depth fixture did not exit cleanly\n' >&2
  sed -n '1,400p' "$fixture_log" >&2
  exit 1
fi
python3 -c '
import json
import sys
lines=open(sys.argv[1], encoding="utf-8").read().splitlines()
prefix="HEAD_DEPTH_RGBD_FIXTURE_RESULT="
matches=[line[len(prefix):] for line in lines if line.startswith(prefix)]
assert len(matches) == 1
result=json.loads(matches[0])
assert result["cycle_count"] == 5000
assert result["accepted_count"] == 10000
assert result["adapter_accepted_pair_count"] == 5000
assert result["adapter_rejected_count"] == 0
assert result["current_depth_count"] == 1
assert result["current_health_count"] == 1
assert result["recent_bounded_state_size"] == 16
assert result["retained_unique_state_count"] == 16
assert result["retained_reference_count"] == 18
assert result["pending_image_count"] == 0
assert result["pending_camera_info_count"] == 0
assert result["depth_authorization_count"] == 0
assert result["fixture_classification"] == "test_fixture"
for key in (
    "all_invalid_rejected",
    "bare_perception_bypass_rejected",
    "byte_mismatch_rejected",
    "calibration_mismatch_rejected",
    "classification_substitution_rejected",
    "conflicting_fingerprint_rejected",
    "conflicting_identity_rejected",
    "duplicate_rejected",
    "empty_payload_rejected",
    "future_rejected",
    "impossible_step_rejected",
    "inactive_evidence_rejected",
    "infinite_depth_rejected",
    "invalid_range_rejected",
    "malformed_calibration_rejected",
    "nan_sentinel_counted_invalid",
    "negative_depth_rejected",
    "no_raw_depth_retained",
    "old_session_rejected",
    "out_of_order_rejected",
    "query_immutable",
    "recorded_evidence_rejected",
    "recorded_live_substitution_rejected",
    "reset_clears_authorization",
    "session_changed_on_reactivation",
    "simulation_spoof_rejected",
    "spoofed_physical_rejected",
    "stale_rejected",
    "unknown_producer_rejected",
    "unknown_source_rejected",
    "unsupported_encoding_rejected",
    "valid_recovery_after_adversarial",
    "wrong_camera_identity_rejected",
    "wrong_frame_rejected",
    "wrong_robot_rejected",
    "wrong_sensor_rejected",
):
    assert result[key] is True, key
assert 0 < result["traced_python_current_bytes"] < 16 * 1024 * 1024
assert 0 < result["traced_python_peak_bytes"] < 32 * 1024 * 1024
' "$fixture_log"
printf 'PASS: offline fixture proves 5000-cycle bounds, depth semantics, lifecycle, and adversarial rejection\n'

wait_until() {
  local description="$1"
  local check_function="$2"
  local attempts="${3:-200}"
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
ayyo_smoke_start_owned_launch "$launch_log" ros2 launch ayyo_simulation head_depth_fixture.launch.py enable_head_depth_fixture:=false depth_camera_profile:=unconfigured
wait_until 'default-off depth composition reaches active lifecycle' world_model_active
depth_info="$(ros2 topic info /ayyo/camera/head/depth/image_raw --verbose 2>/dev/null || true)"
if grep -q 'Publisher count: [1-9]' <<<"$depth_info"; then
  printf 'FAIL: default-off depth path unexpectedly has a publisher\n' >&2
  exit 1
fi
set +e
default_query="$(ros2 run ayyo_world_model body_state_query.py 2>/dev/null)"
default_query_status=$?
set -e
[[ "$default_query_status" -eq 2 ]]
python3 -c '
import json,sys
state=json.loads(sys.argv[1].splitlines()[0])
assert state["status"] == 0
assert state["depth_frame"] is None
assert state["current_depth_count"] == 0
' "$default_query"
ayyo_smoke_shutdown_owned_launch
for _ in {1..40}; do
  graph_empty && break
  sleep 0.25
done
graph_empty
printf 'PASS: head-depth path is runtime default-off and leaves no graph\n'

launch_log="$enabled_log"
ayyo_smoke_start_owned_launch "$launch_log" ros2 launch ayyo_simulation head_depth_fixture.launch.py enable_head_depth_fixture:=true depth_camera_profile:=test_fixture_v1 world_model_retention_ttl_ms:=10000

trusted_depth_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
depth=state["depth_frame"]
sensor=next(item for item in state["sensors"] if item["sensor_id"] == "ayyo.camera.head.depth.v1")
raise SystemExit(0 if state["status"] == 1
  and depth is not None
  and depth["availability"] == 1
  and depth["freshness"] == 1
  and depth["valid_count"] > 0
  and depth["data_size_bytes"] > 0
  and sensor["health"] is not None
  and sensor["health"]["availability"] == 1
  else 1)
' "$smoke_root/body.json"
}

wrong_frame_logged() {
  grep -Eq 'depth (Image|CameraInfo) frame does not match' "$launch_log"
}

malformed_payload_logged() {
  grep -Eq 'depth image step or byte count is inconsistent' "$launch_log"
}

wait_until 'head-depth lifecycle is active' world_model_active
wait_until 'sealed nonempty depth and diagnostics reach the read-only query' trusted_depth_ready

image_type="$(ros2 topic type /ayyo/camera/head/depth/image_raw)"
camera_info_type="$(ros2 topic type /ayyo/camera/head/depth/camera_info)"
[[ "$image_type" == 'sensor_msgs/msg/Image' ]]
[[ "$camera_info_type" == 'sensor_msgs/msg/CameraInfo' ]]
printf 'PASS: canonical depth topics expose standard Image and CameraInfo types\n'

python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
depth=state["depth_frame"]
sensor=next(item for item in state["sensors"] if item["sensor_id"] == depth["sensor_id"])
health=sensor["health"]
assert depth["sensor_id"] == "ayyo.camera.head.depth.v1"
assert depth["frame_id"] == "head_depth_camera_optical_frame"
assert depth["source_kind"] == "test_fixture"
assert depth["source_id"] == "ros.camera.head.depth.test-fixture.v1"
assert depth["source_clock"] == "test_time"
assert depth["source_transport"] == "ros2"
assert depth["source_interface"] == "sensor-msgs.image-camera-info.depth.v1"
assert depth["observed_at_ns"] > 0
assert depth["width"] == 4 and depth["height"] == 2
assert depth["encoding"] == "16UC1" and depth["step"] == 8
assert depth["data_size_bytes"] == 16
assert depth["valid_count"] == 8 and depth["invalid_count"] == 0
assert depth["minimum_m"] == 1.0 and depth["maximum_m"] == 1.7
assert depth["calibration_id"].startswith("camera-calibration-sha256-")
assert depth["calibration_record_id"].startswith("depth-camera-calibration-sha256-")
assert depth["source_manifest_id"].startswith("depth-camera-source-sha256-")
assert depth["session_id"].startswith("depth-camera-session-sha256-")
assert len(depth["payload_sha256"]) == 64
assert depth["observation_id"].startswith("world-observation-")
assert state["current_depth_count"] == 1
assert state["recent_evidence_count"] <= 256
assert health["source_id"] == "ros.camera.head.depth.test-fixture.v1"
assert "depth_camera:frame_accepted" in health["detail"]
assert "calibration=valid" in health["detail"]
assert "lifecycle=active" in health["detail"]
assert "data" not in depth
' "$smoke_root/body.json"
printf 'PASS: exact TEST provenance, acquisition time, optical frame, calibration, compact statistics, and health are exposed\n'

services="$(ros2 service list --no-daemon)"
for forbidden in cmd_vel trajectory navigation manipulation skill execute actuator motor; do
  if grep -qi "$forbidden" <<<"$services"; then
    printf 'FAIL: depth composition exposed forbidden authority: %s\n' "$forbidden" >&2
    exit 1
  fi
done
printf 'PASS: depth acquisition and diagnostics expose no movement or skill authority\n'

python3 "$repository_root/scripts/head_depth_rgbd_test_fixture.py" --scenario wrong_frame >"$smoke_root/wrong_frame.json"
wait_until 'wrong-frame depth evidence is rejected' wrong_frame_logged 40
python3 "$repository_root/scripts/head_depth_rgbd_test_fixture.py" --scenario malformed_payload >"$smoke_root/malformed_payload.json"
wait_until 'malformed depth payload is rejected' malformed_payload_logged 40
wait_until 'valid depth source recovers after adversarial traffic' trusted_depth_ready 40
before_observation="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["depth_frame"]["observation_id"])' "$smoke_root/body.json")"
before_session="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["depth_frame"]["session_id"])' "$smoke_root/body.json")"

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
assert state["availability"] == 0
assert state["depth_frame"] is None
' "$deactivated_query"
ros2 lifecycle set /ayyo_world_model activate >/dev/null
wait_until 'reactivated depth adapter admits a new valid source epoch' trusted_depth_ready 60
python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
depth=state["depth_frame"]
assert depth["observation_id"] != sys.argv[2]
assert depth["session_id"] != sys.argv[3]
' "$smoke_root/body.json" "$before_observation" "$before_session"
printf 'PASS: deactivate clears evidence and reactivation establishes a distinct source session\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: head-depth adapter reported an unclean lifecycle\n' >&2
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
  printf 'FAIL: isolated ROS graph was not empty after shutdown\n%s\n' "$remaining_nodes" >&2
  exit 1
fi
if [[ -n "$(ayyo_smoke_owned_pids)" ]]; then
  printf 'FAIL: depth smoke retained owned processes after shutdown\n' >&2
  ayyo_smoke_owned_processes >&2
  exit 1
fi
printf 'PASS: head-depth owned-process set and isolated ROS graph are empty\n'
printf 'PASS: Head Depth / RGB-D Sensor Foundation v1 smoke completed\n'
