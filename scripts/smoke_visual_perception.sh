#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-visual-perception-smoke.XXXXXX)"
readonly launch_log="$smoke_root/visual_perception.log"
readonly default_domain_id="$((200 + ($$ % 20)))"
readonly smoke_domain_id="${AYYO_VISUAL_PERCEPTION_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_visual_perception_smoke_$$"
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

python3 "$repository_root/scripts/visual_interpretation_test_fixture.py" \
  >"$smoke_root/adversarial.json"
python3 -c '
import json,sys
r=json.load(open(sys.argv[1], encoding="utf-8"))
assert r == {
  "duplicate_bounded": True,
  "malformed_rejected": True,
  "missing_source": "source_frame_not_admitted",
  "no_confidence": True,
  "physical_substitution": "clock_domain_mismatch",
  "pixel_free_state": True,
  "recent_evidence_count": 16,
  "tracked_visual_source_count": 64,
  "valid_after_adversarial": True,
  "wrong_camera": "unknown_sensor",
  "wrong_robot": "wrong_robot_identity",
}
' "$smoke_root/adversarial.json"
printf 'PASS: adversarial provenance, source identity, duplicate, and 1000-frame resource proof\n'

ayyo_smoke_start_owned_launch "$launch_log" \
  ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_control:=false enable_world_model:=true \
  enable_camera:=true enable_visual_reference_interpreter:=true \
  enable_anonymous_semantic_test_fixture:=true

wait_until() {
  local description="$1"
  local check_function="$2"
  local attempts="${3:-240}"
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

interpreted_ready() {
  timeout 4 ros2 run ayyo_world_model body_state_query.py \
    >"$smoke_root/body.json" 2>/dev/null || return 1
  python3 -c '
import json,sys
s=json.load(open(sys.argv[1], encoding="utf-8")); v=s["visual_frame"]; i=s["visual_interpretation"]
raise SystemExit(0 if s["status"] == 1 and v and i and i["source_visual_observation_id"] == v["observation_id"] else 1)
' "$smoke_root/body.json"
}

wait_until 'trusted frame reaches deterministic interpreted read-only state' interpreted_ready
semantic_ready() {
  timeout 4 ros2 run ayyo_world_model semantic_state_query.py \
    >"$smoke_root/semantic.json" 2>/dev/null || return 1
  python3 -c '
import json,sys
s=json.load(open(sys.argv[1], encoding="utf-8"))
kinds={item["kind"] for state in s["semantic_states"] for item in state["items"]}
raise SystemExit(0 if s["status"] == 1 and kinds == {"person", "object"} else 1)
' "$smoke_root/semantic.json"
}
wait_until 'anonymous person/object state reaches the fixed semantic query' semantic_ready
python3 -c '
import json,sys
s=json.load(open(sys.argv[1], encoding="utf-8")); v=s["visual_frame"]; i=s["visual_interpretation"]
assert s["current_visual_count"] == 1
assert s["current_visual_interpretation_count"] == 2
assert i["sensor_id"] == "ayyo.camera.head.rgb.v1"
assert i["reference_frame_id"] == "head_camera_optical_frame"
assert i["source_observed_at_ns"] == v["observed_at_ns"]
assert i["source_visual_observation_id"] == v["observation_id"]
assert i["source_visual_fingerprint"] == v["observation_fingerprint"]
assert i["result_at_ns"] >= i["source_observed_at_ns"]
assert i["producer_id"] == "ayyo.visual.reference.synthetic.v1"
assert i["producer_kind"] == "test_fixture"
assert i["model_id"] == "none"
assert i["source_kind"] == "simulation"
assert i["source_id"] == "ros.camera.head.simulation.gz-harmonic.v1"
assert len(i["detections"]) == 1
d=i["detections"][0]
assert d["category"] == "test_pattern"
assert d["label"] == "synthetic.test-pattern.v1"
assert d["coordinate_space"] == "normalized_image"
assert d["region"] == {"x_min":0.25,"y_min":0.25,"x_max":0.75,"y_max":0.75}
assert d["confidence"] is None
assert "pixels" not in repr(s).lower() and "image_data" not in repr(s).lower()
' "$smoke_root/body.json"
printf 'PASS: source acquisition identity, synthetic provenance, normalized region, and absent confidence are exact\n'

python3 -c '
import json,sys
s=json.load(open(sys.argv[1], encoding="utf-8"))
assert s["status"] == 1
assert s["semantic_state_count"] == len(s["semantic_states"])
assert 1 <= s["semantic_state_count"] <= 64
assert s["snapshot_id"].startswith("world-snapshot-")
assert s["snapshot_fingerprint"].startswith("world_snapshot:sha256:")
for state in s["semantic_states"]:
    assert state["observation_id"].startswith("world-observation-")
    assert state["observation_fingerprint"].startswith("semantic_evidence:sha256:")
    assert state["sensor_id"] == "ayyo.camera.head.rgb.v1"
    assert state["reference_frame_id"] == "head_camera_optical_frame"
    assert state["source_visual_observation_id"].startswith("world-observation-")
    assert state["source_visual_fingerprint"].startswith("visual_frame:sha256:")
    assert state["source_interpretation_observation_id"].startswith("world-observation-")
    assert state["source_interpretation_fingerprint"].startswith("visual_interpretation:sha256:")
    assert state["producer"] == {
        "adapter_id":"ayyo.visual.semantic-query.fixture-adapter.v1",
        "id":"ayyo.visual.semantic-query.fixture.v1",
        "interface":"ayyo.visual-interpretation.v1",
        "kind":"test_fixture",
        "model_id":"none",
    }
    assert state["source_provenance"] == {
        "clock":"ros_simulation_time",
        "id":"ros.camera.head.simulation.gz-harmonic.v1",
        "interface":"sensor-msgs.image-camera-info.v1",
        "kind":"simulation",
        "transport":"ros2",
    }
    by_kind={item["kind"]:item for item in state["items"]}
    assert set(by_kind) == {"person", "object"}
    assert by_kind["person"]["category"] is None
    assert by_kind["person"]["confidence"] is None
    assert by_kind["person"]["region"] == {"x_min":0.1,"y_min":0.1,"x_max":0.4,"y_max":0.8}
    assert by_kind["object"]["category"] == "synthetic.demo-object.v1"
    assert by_kind["object"]["confidence"] == 0.0
    assert by_kind["object"]["region"] == {"x_min":0.55,"y_min":0.25,"x_max":0.9,"y_max":0.75}
    assert by_kind["person"]["source_semantic_observation_id"].startswith("person-observation-sha256-")
    assert by_kind["object"]["source_semantic_observation_id"].startswith("object-observation-sha256-")
text=repr(s).lower()
for forbidden in ("person_id", "object_id", "track_id", "entity_id", "pixels", "command", "authority"):
    assert forbidden not in text
' "$smoke_root/semantic.json"
printf 'PASS: typed semantic query preserves anonymous source evidence, provenance, regions, and optional confidence\n'

initial_position="$(python3 -c '
import json,sys
s=json.load(open(sys.argv[1])); print(s["positions"][s["joint_names"].index("neck_yaw_joint")])
' "$smoke_root/body.json")"
sleep 1
interpreted_ready
semantic_ready
python3 -c '
import json,sys
s=json.load(open(sys.argv[1])); p=s["positions"][s["joint_names"].index("neck_yaw_joint")]
assert abs(p-float(sys.argv[2])) <= 0.001
' "$smoke_root/body.json" "$initial_position"
printf 'PASS: interpreted visual evidence creates no movement authority\n'

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

wait_until 'lifecycle deactivation completes' lifecycle_inactive 40
set +e
deactivated="$(ros2 run ayyo_world_model body_state_query.py 2>/dev/null)"
deactivated_status=$?
semantic_deactivated="$(ros2 run ayyo_world_model semantic_state_query.py 2>/dev/null)"
semantic_deactivated_status=$?
set -e
[[ "$deactivated_status" -eq 2 ]]
[[ "$semantic_deactivated_status" -eq 2 ]]
python3 -c 'import json,sys; assert json.loads(sys.argv[1].splitlines()[0])["status"] == 0' "$deactivated"
python3 -c 'import json,sys; assert json.loads(sys.argv[1].splitlines()[0])["status"] == 0' "$semantic_deactivated"
wait_until 'lifecycle reactivation completes' lifecycle_active 40
wait_until 'reactivated adapter admits a new interpreted frame' interpreted_ready 80
wait_until 'reactivated semantic state reaches the query' semantic_ready 80
printf 'PASS: visual interpretation and semantic query obey lifecycle deactivate/reactivate boundaries\n'

ayyo_smoke_shutdown_owned_launch
if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' "$launch_log"; then
  printf 'FAIL: visual interpretation path reported an unclean lifecycle\n' >&2
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
printf 'PASS: interpreted-visual owned-process set is empty after bounded shutdown\n'
printf 'PASS: Visual Perception Processing Foundation v1 smoke completed\n'
