#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-visual-evaluation-smoke.XXXXXX)"
readonly fixture_log="$smoke_root/evaluation_fixture.log"
readonly launch_log="$smoke_root/visual_evaluation_ros.log"
readonly default_domain_id="$((160 + ($$ % 20)))"
readonly smoke_domain_id="${AYYO_VISUAL_EVALUATION_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_visual_evaluation_smoke_$$"
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
export GZ_HOMEDIR="$smoke_root/gz_home"
mkdir -p "$ROS_LOG_DIR" "$GZ_HOMEDIR"

preexisting_nodes="$(ros2 node list --no-daemon 2>/dev/null)"
if [[ -n "$preexisting_nodes" ]]; then
  printf 'FAIL: isolated ROS graph was not empty before launch\n%s\n' \
    "$preexisting_nodes" >&2
  exit 1
fi

ayyo_smoke_start_owned_launch "$fixture_log" \
  python3 "$repository_root/scripts/visual_producer_evaluation_test_fixture.py"
if ! ayyo_smoke_wait_owned_exit 1200 0.05; then
  printf 'FAIL: transport-neutral evaluation fixture did not exit cleanly\n' >&2
  sed -n '1,400p' "$fixture_log" >&2
  exit 1
fi
python3 -c '
import json
import sys
lines=open(sys.argv[1], encoding="utf-8").read().splitlines()
prefix="VISUAL_EVALUATION_FIXTURE_RESULT="
matches=[line[len(prefix):] for line in lines if line.startswith(prefix)]
assert len(matches) == 1
result=json.loads(matches[0])
assert result["cycle_count"] == 5000
assert result["accepted_count"] == 10000
assert result["rejected_count"] == 0
assert result["current_interpretation_count"] == 1
assert result["current_evaluation_reference_count"] == 1
assert result["recent_bounded_state_size"] == 16
assert result["retained_unique_state_count"] <= 18
assert result["semantic_reference_count"] == 1
assert result["duplicate_bounded"] is True
assert result["corrupt_sample_rejected"] is True
assert result["recovered_after_corruption"] is True
assert result["physical_source_substitution_rejected"] is True
assert result["reproducible"] is True
assert result["owned_evaluation_processes"] == []
assert result["traced_python_current_bytes"] > 0
assert 0 < result["traced_python_peak_bytes"] < 64 * 1024 * 1024
for key in ("malformed_output_decision", "timeout_decision", "wrong_model_decision", "wrong_source_decision"):
    assert result[key] == "does_not_meet_mechanical_policy"
' "$fixture_log"
printf 'PASS: owned offline fixture proves adversarial rejection, recovery, reproducibility, and 5000-cycle bounds\n'

ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_control:=false enable_world_model:=true \
  enable_camera:=true enable_visual_reference_interpreter:=false \
  enable_visual_producer_evaluation_fixture:=true \
  world_model_retention_ttl_ms:=10000

wait_until() {
  local description="$1"
  local check_function="$2"
  local attempts="${3:-240}"
  local attempt
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,520p' "$launch_log" >&2
      return 1
    fi
    if "$check_function"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,520p' "$launch_log" >&2
  return 1
}

evaluated_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json
import sys
s=json.load(open(sys.argv[1], encoding="utf-8"))
i=s["visual_interpretation"]
raise SystemExit(0 if s["status"] == 1 and i and i["evaluation"] and i["model"] else 1)
' "$smoke_root/body.json"
}

wait_until 'sealed evaluated interpretation reaches the fixed read-only query' evaluated_ready
cp "$smoke_root/body.json" "$smoke_root/body_first.json"
python3 -c '
import json
import sys
s=json.load(open(sys.argv[1], encoding="utf-8")); i=s["visual_interpretation"]; e=i["evaluation"]; m=i["model"]
assert s["current_visual_count"] == 1
assert s["current_visual_interpretation_count"] == 1
assert s["recent_evidence_count"] <= 256
assert i["sensor_id"] == "ayyo.camera.head.rgb.v1"
assert i["reference_frame_id"] == "head_camera_optical_frame"
assert i["source_kind"] == "simulation"
assert i["source_id"] == "ros.camera.head.simulation.gz-harmonic.v1"
assert i["source_clock"] == "ros_simulation_time"
assert i["source_transport"] == "ros2"
assert i["source_interface"] == "sensor-msgs.image-camera-info.v1"
assert i["producer_id"] == "ayyo.visual.evaluation.fixture.v1"
assert i["producer_kind"] == "test_fixture"
assert i["model_id"] == "ayyo.visual.evaluation.fixture-model.v1"
assert m["format"] == "deterministic_fixture"
assert m["source_classification"] == "test_fixture"
assert len(m["artifact_sha256"]) == 64
assert len(m["configuration_sha256"]) == 64
assert len(m["provenance_sha256"]) == 64
assert e["decision"] == "meets_mechanical_policy"
assert e["dataset_id"] == "ayyo.visual.fixture-live-profile-dataset.v1"
assert e["policy_id"] == "ayyo.visual.fixture-policy.v1"
for field in ("dataset_manifest_sha256", "policy_sha256", "producer_implementation_sha256", "producer_manifest_sha256", "report_semantic_sha256"):
    assert len(e[field]) == 64
assert len(i["detections"]) == 1
assert i["detections"][0]["label"] == "synthetic.evaluation-marker.v1"
assert "pixels" not in repr(s).lower() and "image_data" not in repr(s).lower()
' "$smoke_root/body_first.json"
printf 'PASS: compact model, producer, dataset, policy, report, source, and detection provenance are exact\n'

evaluated_ready
cp "$smoke_root/body.json" "$smoke_root/body_second.json"
python3 -c '
import json
import sys
a=json.load(open(sys.argv[1], encoding="utf-8"))["visual_interpretation"]
b=json.load(open(sys.argv[2], encoding="utf-8"))["visual_interpretation"]
for field in ("observation_id", "observation_fingerprint", "source_visual_observation_id", "source_visual_fingerprint", "evaluation", "model", "detections"):
    assert a[field] == b[field]
' "$smoke_root/body_first.json" "$smoke_root/body_second.json"
printf 'PASS: repeated read-only query leaves evaluated World Model identity unchanged\n'

if ros2 service list --no-daemon | grep -Eq 'cmd_vel|trajectory|simulation_control|execute'; then
  printf 'FAIL: evaluated fixture exposed a command or actuation service\n' >&2
  exit 1
fi
printf 'PASS: evaluated fixture exposes no movement, navigation, skill, or actuation authority\n'

lifecycle_inactive() {
  ros2 lifecycle get /ayyo_world_model 2>/dev/null \
    | grep -q '^inactive \[2\]$' && return 0
  ros2 lifecycle set /ayyo_world_model deactivate >/dev/null 2>&1
}

lifecycle_active() {
  ros2 lifecycle get /ayyo_world_model 2>/dev/null \
    | grep -q '^active \[3\]$' && return 0
  ros2 lifecycle set /ayyo_world_model activate >/dev/null 2>&1
}

first_interpretation_id="$(python3 -c '
import json,sys
print(json.load(open(sys.argv[1]))["visual_interpretation"]["observation_id"])
' "$smoke_root/body_first.json")"
wait_until 'evaluated adapter lifecycle deactivation completes' lifecycle_inactive 40
set +e
deactivated="$(ros2 run ayyo_world_model body_state_query.py 2>/dev/null)"
deactivated_status=$?
set -e
[[ "$deactivated_status" -eq 2 ]]
python3 -c 'import json,sys; assert json.loads(sys.argv[1].splitlines()[0])["status"] == 0' "$deactivated"
wait_until 'evaluated adapter lifecycle reactivation completes' lifecycle_active 40
wait_until 'reactivation issues one new sealed evaluated result' evaluated_ready 120
python3 -c '
import json
import sys
s=json.load(open(sys.argv[1], encoding="utf-8")); i=s["visual_interpretation"]
assert i["observation_id"] != sys.argv[2]
assert s["current_visual_interpretation_count"] == 1
assert s["recent_evidence_count"] <= 256
' "$smoke_root/body.json" "$first_interpretation_id"
printf 'PASS: default-off evaluated subscriptions obey deactivate/reactivate without duplication\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: evaluated visual lifecycle reported an unclean error\n' >&2
  sed -n '1,560p' "$launch_log" >&2
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
printf 'PASS: evaluation smoke leftover owned process set=[] and isolated graph is empty\n'
printf 'PASS: Recorded Visual Producer Evaluation and Perception Quality Gate v1 smoke completed\n'
