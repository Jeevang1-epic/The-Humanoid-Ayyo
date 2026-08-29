#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-physical-camera-smoke.XXXXXX)"
readonly fixture_log="$smoke_root/offline_fixture.log"
readonly default_off_log="$smoke_root/default_off.log"
readonly enabled_log="$smoke_root/physical_camera.log"
readonly default_domain_id="$((90 + ($$ % 30)))"
readonly smoke_domain_id="${AYYO_PHYSICAL_CAMERA_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_physical_camera_smoke_$$"
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

ayyo_smoke_start_owned_launch "$fixture_log" python3 "$repository_root/scripts/physical_camera_foundation_test_fixture.py"
if ! ayyo_smoke_wait_owned_exit 1200 0.05; then
  printf 'FAIL: transport-neutral physical-camera fixture did not exit cleanly\n' >&2
  sed -n '1,400p' "$fixture_log" >&2
  exit 1
fi
python3 -c '
import json
import sys
lines=open(sys.argv[1], encoding="utf-8").read().splitlines()
prefix="PHYSICAL_CAMERA_FOUNDATION_FIXTURE_RESULT="
matches=[line[len(prefix):] for line in lines if line.startswith(prefix)]
assert len(matches) == 1
result=json.loads(matches[0])
assert result["cycle_count"] == 5000
assert result["accepted_count"] == 10000
assert result["adapter_accepted_pair_count"] == 5000
assert result["adapter_rejected_count"] == 0
assert result["current_visual_count"] == 1
assert result["current_health_count"] == 1
assert result["recent_bounded_state_size"] == 16
assert result["retained_unique_state_count"] == 16
assert result["pending_image_count"] == 0
assert result["pending_camera_info_count"] == 0
assert result["physical_authorization_count"] == 0
assert result["source_reference_count"] == 64
assert result["fixture_classification"] == "test_fixture"
for key in (
    "malformed_calibration_rejected",
    "simulation_spoof_rejected",
    "wrong_frame_rejected",
    "inactive_evidence_rejected",
    "old_session_rejected",
    "session_changed_on_reactivation",
    "bare_perception_bypass_rejected",
    "query_immutable",
):
    assert result[key] is True
assert 0 < result["traced_python_peak_bytes"] < 64 * 1024 * 1024
' "$fixture_log"
printf 'PASS: offline fixture proves 5000-cycle bounds, calibration, lifecycle, spoof rejection, and sealed trust\n'

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
ayyo_smoke_start_owned_launch "$launch_log" ros2 launch ayyo_simulation physical_camera_fixture.launch.py enable_physical_camera_fixture:=false physical_camera_profile:=unconfigured
wait_until 'default-off physical composition reaches active lifecycle' world_model_active
image_info="$(ros2 topic info /ayyo/camera/head/image_raw --verbose 2>/dev/null || true)"
if grep -q 'Publisher count: [1-9]' <<<"$image_info"; then
  printf 'FAIL: default-off physical camera unexpectedly has a publisher\n' >&2
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
assert state["visual_frame"] is None
' "$default_query"
ayyo_smoke_shutdown_owned_launch
for _ in {1..40}; do
  graph_empty && break
  sleep 0.25
done
graph_empty
printf 'PASS: physical camera path is runtime default-off and leaves no graph\n'

launch_log="$enabled_log"
ayyo_smoke_start_owned_launch "$launch_log" ros2 launch ayyo_simulation physical_camera_fixture.launch.py enable_physical_camera_fixture:=true physical_camera_profile:=test_fixture_v1 world_model_retention_ttl_ms:=10000

trusted_physical_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
visual=state["visual_frame"]
camera=next(item for item in state["sensors"] if item["sensor_id"] == "ayyo.camera.head.rgb.v1")
raise SystemExit(0 if state["status"] == 1
  and visual is not None
  and visual["availability"] == 1
  and visual["freshness"] == 1
  and camera["health"] is not None
  and camera["health"]["availability"] == 1
  else 1)
' "$smoke_root/body.json"
}

wrong_frame_logged() {
  grep -Eq 'physical (Image|CameraInfo) frame does not match' "$launch_log"
}

malformed_calibration_logged() {
  grep -Eq 'finite real number|configured calibration' "$launch_log"
}

wait_until 'physical-camera lifecycle is active' world_model_active
wait_until 'sealed physical camera and diagnostics reach the read-only query' trusted_physical_ready

python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
visual=state["visual_frame"]
camera=next(item for item in state["sensors"] if item["sensor_id"] == visual["sensor_id"])
health=camera["health"]
assert visual["sensor_id"] == "ayyo.camera.head.rgb.v1"
assert visual["frame_id"] == "head_camera_optical_frame"
assert visual["source_kind"] == "physical_sensor"
assert visual["source_id"] == "ros.camera.head.physical.test-fixture.v1"
assert visual["source_clock"] == "ros_system_time"
assert visual["source_transport"] == "ros2"
assert visual["source_interface"] == "sensor-msgs.image-camera-info.v1"
assert visual["width"] == 4 and visual["height"] == 2
assert visual["encoding"] == "rgb8" and visual["step"] == 12
assert visual["data_size_bytes"] == 24
assert visual["calibration_id"].startswith("camera-calibration-sha256-")
assert visual["observation_id"].startswith("world-observation-")
assert state["current_visual_count"] == 1
assert state["recent_evidence_count"] <= 256
assert health["source_id"] == "ros.camera.head.physical.test-fixture.v1"
assert "physical_camera:frame_accepted" in health["detail"]
assert "calibration=valid" in health["detail"]
assert "lifecycle=active" in health["detail"]
assert state["visual_interpretation"] is None
' "$smoke_root/body.json"
printf 'PASS: exact physical TEST provenance, optical frame, calibration identity, and health are compact\n'

services="$(ros2 service list --no-daemon)"
for forbidden in cmd_vel trajectory navigation manipulation skill execute actuator motor; do
  if grep -qi "$forbidden" <<<"$services"; then
    printf 'FAIL: physical camera composition exposed forbidden authority: %s\n' "$forbidden" >&2
    exit 1
  fi
done
printf 'PASS: physical camera and diagnostics expose no movement or skill authority\n'

python3 "$repository_root/scripts/physical_camera_foundation_test_fixture.py" --scenario wrong_frame >"$smoke_root/wrong_frame.json"
wait_until 'wrong-frame physical evidence is rejected' wrong_frame_logged 40
python3 "$repository_root/scripts/physical_camera_foundation_test_fixture.py" --scenario malformed_calibration >"$smoke_root/malformed_calibration.json"
wait_until 'malformed physical calibration is rejected' malformed_calibration_logged 40
wait_until 'valid physical source recovers after adversarial traffic' trusted_physical_ready 40
before_observation="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["visual_frame"]["observation_id"])' "$smoke_root/body.json")"
before_session="$(python3 -c 'import json,sys; state=json.load(open(sys.argv[1])); camera=next(x for x in state["sensors"] if x["sensor_id"]=="ayyo.camera.head.rgb.v1"); print(camera["health"]["detail"].split("session=")[1].split(":")[0])' "$smoke_root/body.json")"

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
' "$deactivated_query"
ros2 lifecycle set /ayyo_world_model activate >/dev/null
wait_until 'reactivated physical adapter admits a new valid source epoch' trusted_physical_ready 60
python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
visual=state["visual_frame"]
camera=next(item for item in state["sensors"] if item["sensor_id"] == visual["sensor_id"])
session=camera["health"]["detail"].split("session=")[1].split(":")[0]
assert visual["observation_id"] != sys.argv[2]
assert session != sys.argv[3]
' "$smoke_root/body.json" "$before_observation" "$before_session"
printf 'PASS: deactivate blocks evidence and reactivation establishes a distinct source session\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: physical camera adapter reported an unclean lifecycle\n' >&2
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
printf 'PASS: physical-camera owned-process set and isolated ROS graph are empty\n'
printf 'PASS: Physical Head Camera Adapter, Calibration, and Diagnostics Foundation v1 smoke completed\n'
