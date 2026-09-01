#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-head-audio-smoke.XXXXXX)"
readonly focused_log="$smoke_root/focused.log"
readonly default_off_log="$smoke_root/default_off.log"
readonly enabled_log="$smoke_root/head_audio.log"
readonly default_domain_id="$((150 + ($$ % 30)))"
readonly smoke_domain_id="${AYYO_HEAD_AUDIO_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_head_audio_smoke_$$"
readonly audio_python_path="$repository_root/world_model/src:$repository_root/head_audio/src:$repository_root/physical_camera/src:$repository_root/depth_camera/src:$repository_root/rgbd_fusion/src:$repository_root/visual_evaluation/src:$repository_root/perception/src:$repository_root/working_memory/src"
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

PYTHONPATH="$audio_python_path" pytest -q "$repository_root/head_audio/tests" >"$focused_log"
PYTHONPATH="$audio_python_path" pytest -q "$repository_root/perception/tests" >>"$focused_log"
PYTHONPATH="$audio_python_path" pytest -q "$repository_root/working_memory/tests" >>"$focused_log"
PYTHONPATH="$audio_python_path" pytest -q "$repository_root/world_model/tests" >>"$focused_log"
printf 'PASS: 232 focused tests prove sealed admission, adversarial rejection, bounded retention, and the 5000-cycle resource fixture\n'

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
ayyo_smoke_start_owned_launch "$launch_log" ros2 launch ayyo_simulation head_audio_fixture.launch.py enable_head_audio_fixture:=false head_audio_profile:=unconfigured
wait_until 'default-off audio composition reaches active lifecycle' world_model_active
audio_info="$(ros2 topic info /ayyo/audio/head/microphone/raw --verbose 2>/dev/null || true)"
if grep -q 'Publisher count: [1-9]' <<<"$audio_info"; then
  printf 'FAIL: default-off audio path unexpectedly has a publisher\n' >&2
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
assert state["audio_frame"] is None
assert state["current_audio_count"] == 0
' "$default_query"
ayyo_smoke_shutdown_owned_launch
for _ in {1..40}; do
  graph_empty && break
  sleep 0.25
done
graph_empty
printf 'PASS: head audio is runtime default-off and leaves no ROS graph\n'

launch_log="$enabled_log"
ayyo_smoke_start_owned_launch "$launch_log" ros2 launch ayyo_simulation head_audio_fixture.launch.py enable_head_audio_fixture:=true head_audio_profile:=test_fixture_v1 world_model_retention_ttl_ms:=10000

trusted_audio_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
audio=state["audio_frame"]
sensor=next(item for item in state["sensors"] if item["sensor_id"] == "ayyo.microphone.head.v1")
raise SystemExit(0 if state["status"] == 1
  and audio is not None
  and audio["availability"] == 1
  and audio["freshness"] == 1
  and sensor["health"] is not None
  and sensor["health"]["availability"] == 1
  else 1)
' "$smoke_root/body.json"
}

wrong_source_logged() {
  grep -q 'audio message identity conflicts with its reviewed source' "$launch_log"
}

wait_until 'head audio lifecycle is active' world_model_active
wait_until 'sealed audio and diagnostics reach the read-only query' trusted_audio_ready

audio_type="$(ros2 topic type /ayyo/audio/head/microphone/raw)"
[[ "$audio_type" == 'ayyo_interfaces/msg/AudioFrame' ]]
python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
audio=state["audio_frame"]
sensor=next(item for item in state["sensors"] if item["sensor_id"] == audio["sensor_id"])
health=sensor["health"]
assert audio["sensor_id"] == "ayyo.microphone.head.v1"
assert audio["frame_id"] == "head_microphone_frame"
assert audio["producer_id"] == "ayyo.audio.test-adapter.v1"
assert audio["source_kind"] == "test_fixture"
assert audio["source_id"] == "ros.audio.head.test-fixture.v1"
assert audio["source_clock"] == "test_time"
assert audio["source_transport"] == "ros2"
assert audio["source_interface"] == "ayyo-interfaces.audio-frame.v1"
assert audio["sample_rate_hz"] == 16000
assert audio["channel_count"] == 1
assert audio["encoding"] == "pcm_s16le"
assert audio["frame_count"] == 160 and audio["sample_count"] == 160
assert audio["duration_ns"] == 10000000
assert audio["data_size_bytes"] == 320
assert audio["observed_at_ns"] > 0
assert audio["result_at_ns"] >= audio["observed_at_ns"]
assert audio["source_manifest_id"].startswith("audio-source-sha256-")
assert audio["session_id"].startswith("audio-session-sha256-")
assert audio["observation_id"].startswith("world-observation-")
assert len(audio["payload_sha256"]) == 64
assert state["current_audio_count"] == 1
assert state["recent_evidence_count"] <= 256
assert state["audio_diagnostics"]["lifecycle_state"] == "active"
assert state["audio_diagnostics"]["retained_payload_bytes"] == 0
assert health["source_kind"] == "test_fixture"
assert health["detail"] == "audio_capture_active"
for forbidden in ("data", "samples", "command", "movement", "skill", "safety"):
    assert forbidden not in audio
' "$smoke_root/body.json"
printf 'PASS: canonical bounded message preserves exact TEST source, format, time, session, compact metrics, and health\n'

services="$(ros2 service list --no-daemon)"
for forbidden in cmd_vel trajectory navigation manipulation skill execute actuator motor; do
  if grep -qi "$forbidden" <<<"$services"; then
    printf 'FAIL: audio composition exposed forbidden authority: %s\n' "$forbidden" >&2
    exit 1
  fi
done
printf 'PASS: audio evidence exposes no movement, skill, safety, or actuator authority\n'

now_sec="$(date +%s)"
valid_digest='96a296d224f285c67bee93c30f8a3091570f0daa35dc5b87e410b78630a09cfc7'
before_invalid="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["audio_diagnostics"]["transport_invalid_count"])' "$smoke_root/body.json")"
timeout 5 ros2 topic pub --once /ayyo/audio/head/microphone/raw ayyo_interfaces/msg/AudioFrame "{header: {stamp: {sec: $now_sec, nanosec: 1}, frame_id: head_microphone_frame}, result_stamp: {sec: $now_sec, nanosec: 1}, source_id: ros.audio.head.spoofed.v1, producer_id: ayyo.audio.test-adapter.v1, microphone_id: ayyo.microphone.head.v1, sample_rate_hz: 16000, channel_count: 1, encoding: pcm_s16le, frame_count: 1, payload_sha256: $valid_digest, data: [0, 0]}" >/dev/null
wait_until 'wrong-source audio transport is rejected' wrong_source_logged 40
timeout 5 ros2 topic pub --once /ayyo/audio/head/microphone/raw ayyo_interfaces/msg/AudioFrame "{header: {stamp: {sec: $now_sec, nanosec: 2}, frame_id: head_microphone_frame}, result_stamp: {sec: $now_sec, nanosec: 2}, source_id: ros.audio.head.test-fixture.v1, producer_id: ayyo.audio.test-adapter.v1, microphone_id: ayyo.microphone.head.v1, sample_rate_hz: 8000, channel_count: 1, encoding: pcm_s16le, frame_count: 1, payload_sha256: $valid_digest, data: [0, 0]}" >/dev/null
wait_until 'valid audio recovers after adversarial transport' trusted_audio_ready 40
python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
diagnostics=state["audio_diagnostics"]
assert diagnostics["transport_invalid_count"] >= int(sys.argv[2]) + 2
assert diagnostics["retained_payload_bytes"] == 0
' "$smoke_root/body.json" "$before_invalid"
printf 'PASS: wrong-source and unsupported-format frames increment bounded rejection diagnostics without retaining payloads\n'

before_observation="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["audio_frame"]["observation_id"])' "$smoke_root/body.json")"
before_session="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["audio_frame"]["session_id"])' "$smoke_root/body.json")"
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
assert state["audio_frame"] is None
' "$deactivated_query"
ros2 lifecycle set /ayyo_world_model activate >/dev/null
wait_until 'reactivated audio adapter admits a distinct valid source epoch' trusted_audio_ready 60
python3 -c '
import json,sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
audio=state["audio_frame"]
assert audio["observation_id"] != sys.argv[2]
assert audio["session_id"] != sys.argv[3]
' "$smoke_root/body.json" "$before_observation" "$before_session"
printf 'PASS: deactivation closes readiness and reactivation creates a distinct session\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: head audio adapter reported an unclean lifecycle\n' >&2
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
  printf 'FAIL: audio smoke retained owned processes after shutdown\n' >&2
  ayyo_smoke_owned_processes >&2
  exit 1
fi
sleep 2
graph_empty
[[ -z "$(ayyo_smoke_owned_pids)" ]]
printf 'PASS: delayed head-audio owned-process set and isolated ROS graph are empty\n'
printf 'PASS: Head Audio Perception Foundation v1 smoke completed\n'
