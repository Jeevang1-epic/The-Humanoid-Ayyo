#!/usr/bin/env bash

set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly workspace_root="$repository_root/ros2_ws"
readonly process_helper="$repository_root/scripts/smoke_processes.sh"
readonly smoke_root="$(mktemp -d -t ayyo-scenarios-smoke.XXXXXX)"
readonly default_domain_id="$((180 + ($$ % 20)))"
readonly smoke_domain_id="${AYYO_SCENARIO_SMOKE_DOMAIN_ID:-$default_domain_id}"
readonly smoke_partition="ayyo_scenarios_smoke_$$"
readonly wait_deadline_seconds=75
readonly scenario_python_path="$repository_root/memory/src:$repository_root/personal_context/src:$repository_root/executive/src:$repository_root/safety_kernel/src:$repository_root/skill_manager/src:$repository_root/runtime_bridge/src:$repository_root/developmental_scenarios/src"
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

ros2 pkg prefix ayyo_scenarios >/dev/null
ros2 pkg prefix ayyo_simulation >/dev/null
ros2 pkg prefix ayyo_world_model >/dev/null

wait_until() {
  local description="$1"
  local check_function="$2"
  local deadline="$((SECONDS + wait_deadline_seconds))"
  shift 2
  while ((SECONDS < deadline)); do
    if ! kill -0 "$launch_pid" 2>/dev/null; then
      printf 'FAIL: scenario launch exited while waiting for %s\n' "$description" >&2
      sed -n '1,520p' "$current_launch_log" >&2
      return 1
    fi
    if "$check_function" "$@"; then
      printf 'PASS: %s\n' "$description"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: timed out waiting for %s\n' "$description" >&2
  sed -n '1,520p' "$current_launch_log" >&2
  return 1
}

start_profile() {
  local profile="$1"
  current_launch_log="$smoke_root/${profile}.log"
  ayyo_smoke_start_owned_launch "$current_launch_log" \
    ros2 launch ayyo_scenarios developmental_scenarios.launch.py \
    profile:="$profile" headless:=true start_rviz:=false
}

isolated_graph_empty() {
  local nodes
  nodes="$(timeout 3 ros2 node list --no-daemon 2>/dev/null || true)"
  [[ -z "$nodes" ]]
}

stop_profile() {
  local profile="$1"
  if ! ayyo_smoke_shutdown_owned_launch; then
    printf 'FAIL: %s profile did not complete bounded owned-process cleanup\n' \
      "$profile" >&2
    return 1
  fi
  local deadline="$((SECONDS + 12))"
  while ((SECONDS < deadline)); do
    if isolated_graph_empty; then
      printf 'PASS: %s owned process set and isolated ROS graph are empty\n' \
        "$profile"
      return 0
    fi
    sleep 0.25
  done
  printf 'FAIL: isolated ROS graph retained nodes after %s shutdown\n' \
    "$profile" >&2
  timeout 3 ros2 node list --no-daemon >&2 || true
  return 1
}

world_model_active() {
  timeout 3 ros2 lifecycle get /ayyo_world_model 2>/dev/null \
    | grep -q '^active \[3\]$'
}

clock_ready() {
  timeout 3 ros2 topic echo --once /clock rosgraph_msgs/msg/Clock \
    >/dev/null 2>&1
}

model_spawned_once() {
  local count
  count="$(
    gz model --list 2>/dev/null \
      | grep -Ec -- '^[[:space:]]*- ayyo$' || true
  )"
  [[ "$count" -eq 1 ]]
}

body_query_to() {
  timeout 5 ros2 run ayyo_world_model body_state_query.py >"$1" 2>/dev/null
}

semantic_query_to() {
  timeout 5 ros2 run ayyo_world_model semantic_state_query.py >"$1" 2>/dev/null
}

topic_has_one_publisher() {
  local information
  information="$(timeout 3 ros2 topic info "$1" --no-daemon 2>/dev/null || true)"
  grep -qx 'Publisher count: 1' <<<"$information"
}

topic_has_no_publisher() {
  local information
  information="$(timeout 3 ros2 topic info "$1" --no-daemon 2>/dev/null || true)"
  [[ -z "$information" ]] || grep -qx 'Publisher count: 0' <<<"$information"
}

development_service_absent() {
  local services
  services="$(timeout 3 ros2 service list --no-daemon 2>/dev/null || true)"
  ! grep -qx '/ayyo/development/set_joint_position' <<<"$services"
}

production_motion_services_absent() {
  local services
  services="$(timeout 3 ros2 service list --no-daemon 2>/dev/null || true)"
  ! grep -Eq '^/ayyo/runtime/.+(motion|joint|trajectory|move)' <<<"$services"
}

controllers_ready() {
  local controllers
  controllers="$(
    timeout 3 ros2 control list_controllers \
      --controller-manager /controller_manager 2>/dev/null || true
  )"
  grep -Eq \
    '^joint_state_broadcaster[[:space:]]+joint_state_broadcaster/JointStateBroadcaster[[:space:]]+active$' \
    <<<"$controllers" &&
    grep -Eq \
      '^ayyo_neck_position_controller[[:space:]]+forward_command_controller/ForwardCommandController[[:space:]]+active$' \
      <<<"$controllers"
}

development_service_ready() {
  local service_type
  service_type="$(
    timeout 3 ros2 service type /ayyo/development/set_joint_position \
      2>/dev/null || true
  )"
  [[ "$service_type" == 'ayyo_interfaces/srv/SetDevelopmentJointPosition' ]]
}

emit_report() {
  local scenario_id="$1"
  local report_path="$smoke_root/report_${scenario_id}.json"
  PYTHONPATH="$scenario_python_path" \
    python3 "$repository_root/ros2_ws/src/ayyo_scenarios/scripts/scenario_report.py" \
      --scenario "$scenario_id" >"$report_path"
  python3 -c '
import json
import sys
report=json.load(open(sys.argv[1], encoding="utf-8"))
assert report["outcome"] == "pass"
assert report["cleanup"] == {
    "detail":"Repository-owned process session is empty after bounded shutdown.",
    "outcome":"clean",
    "owned_processes_remaining":0,
}
assert report["production_dispatch_count"] == 0
assert report["report_id"].startswith("scenario-report-sha256-")
assert "/home/" not in repr(report) and "pid=" not in repr(report).lower()
print("REPORT:", json.dumps(report, sort_keys=True, separators=(",", ":")))
' "$report_path"
}

# Scenario 6 first: prove default-off visual behavior independently.
start_profile sensor_absence
wait_until 'sensor-absence World Model lifecycle is active' world_model_active
wait_until 'sensor-absence simulation clock is available' clock_ready
wait_until 'optional camera source has no publisher' \
  topic_has_no_publisher /ayyo/camera/head/image_raw
wait_until 'body query remains available without optional visual input' \
  body_query_to "$smoke_root/absence_body.json"
semantic_query_to "$smoke_root/absence_semantic_first.json"
semantic_query_to "$smoke_root/absence_semantic_second.json"
python3 -c '
import json
import sys
body=json.load(open(sys.argv[1], encoding="utf-8"))
first=json.load(open(sys.argv[2], encoding="utf-8"))
second=json.load(open(sys.argv[3], encoding="utf-8"))
assert body["status"] == 1 and body["robot_id"] == "ayyo.robot.v1"
assert body["visual_frame"] is None
assert body["visual_interpretation"] is None
assert body["current_visual_count"] == 0
assert body["current_visual_interpretation_count"] == 0
for semantic in (first, second):
    assert semantic["status"] == 1
    assert semantic["semantic_state_count"] == 0
    assert semantic["semantic_states"] == []
    assert "physical-scene occupancy remains unknown" in semantic["detail"]
' "$smoke_root/absence_body.json" \
  "$smoke_root/absence_semantic_first.json" \
  "$smoke_root/absence_semantic_second.json"
printf 'PASS: absent visual source creates no evidence, refresh, or complete-scene claim\n'
stop_profile sensor_absence
emit_report optional-visual-source-absent

# Scenarios 1-3 share the fixed non-development observation profile.
start_profile observation
wait_until 'observation World Model lifecycle is active' world_model_active
wait_until 'Gazebo exposes exactly one canonical Ayyo model' model_spawned_once
wait_until 'observation simulation clock is available' clock_ready
wait_until 'joint-state broadcaster is the sole authoritative publisher' \
  topic_has_one_publisher /joint_states
wait_until 'simulation IMU has one publisher' \
  topic_has_one_publisher /ayyo/imu/data
wait_until 'simulation odometry has one publisher' \
  topic_has_one_publisher /ayyo/localization/odometry
wait_until 'simulation RGB source has one publisher' \
  topic_has_one_publisher /ayyo/camera/head/image_raw
wait_until 'development command service is absent from observation profile' \
  development_service_absent
wait_until 'no production motion Runtime endpoint exists' \
  production_motion_services_absent
wait_until 'complete embodied observation reaches World Model' \
  body_query_to "$smoke_root/observation_body.json"
wait_until 'anonymous semantic TEST evidence reaches read-only query' \
  semantic_query_to "$smoke_root/observation_semantic.json"
python3 -c '
import json
import sys
body=json.load(open(sys.argv[1], encoding="utf-8"))
semantic=json.load(open(sys.argv[2], encoding="utf-8"))
assert body["status"] == 1 and body["robot_id"] == "ayyo.robot.v1"
assert body["known_joint_count"] == 18 and len(body["joint_names"]) == 18
assert body["source_kind"] == "simulation"
assert body["source_clock"] == "ros_simulation_time"
assert body["source_transport"] == "ros2"
assert body["imu"] is not None and body["imu"]["source_kind"] == "simulation"
assert body["imu"]["source_clock"] == "ros_simulation_time"
assert body["base_pose"] is not None
assert body["base_pose"]["source_kind"] == "simulation"
assert body["base_pose"]["source_frame_id"] == "odom"
assert body["base_pose"]["target_frame_id"] == "base_link"
visual=body["visual_frame"]
assert visual is not None
assert visual["sensor_id"] == "ayyo.camera.head.rgb.v1"
assert visual["frame_id"] == "head_camera_optical_frame"
assert visual["source_id"] == "ros.camera.head.simulation.gz-harmonic.v1"
assert visual["source_kind"] == "simulation"
assert semantic["status"] == 1 and semantic["robot_id"] == "ayyo.robot.v1"
assert 1 <= semantic["semantic_state_count"] <= 64
for state in semantic["semantic_states"]:
    assert state["sensor_id"] == visual["sensor_id"]
    assert state["reference_frame_id"] == visual["frame_id"]
    assert state["source_visual_observation_id"].startswith("world-observation-")
    assert state["source_visual_fingerprint"].startswith("visual_frame:sha256:")
    assert 0 < state["source_observed_at_ns"] <= state["result_at_ns"]
    assert state["producer"]["kind"] == "test_fixture"
    assert state["source_provenance"]["kind"] == "simulation"
    by_kind={item["kind"]:item for item in state["items"]}
    assert set(by_kind) == {"person", "object"}
    assert by_kind["person"]["category"] is None
    assert by_kind["person"]["confidence"] is None
    assert by_kind["object"]["category"] == "synthetic.demo-object.v1"
    assert by_kind["object"]["confidence"] == 0.0
text=repr(semantic).lower()
for forbidden in ("person_id", "object_id", "owner_id", "entity_id", "track_id"):
    assert forbidden not in text
' "$smoke_root/observation_body.json" "$smoke_root/observation_semantic.json"
printf 'PASS: embodied and anonymous semantic observations preserve exact simulation/TEST lineage\n'

PYTHONPATH="$scenario_python_path" \
  python3 "$repository_root/ros2_ws/src/ayyo_scenarios/scripts/production_motion_probe.py" \
  >"$smoke_root/production_boundary.json"
python3 -c '
import json
import sys
result=json.load(open(sys.argv[1], encoding="utf-8"))
assert result == {
    "development_service_call_count":0,
    "dispatch_status":"not_eligible",
    "durable_memory_write_count":0,
    "executive_decision":"propose",
    "production_dispatch_count":0,
    "runtime_eligibility":"deferred",
    "runtime_reason":"upstream_deferred",
    "safety_disposition":"deferred",
    "safety_reason":"physical_movement_information_unavailable",
    "skill_binding_reason":"safety_deferred",
    "skill_binding_status":"ineligible",
}
' "$smoke_root/production_boundary.json"
cp "$smoke_root/observation_body.json" "$smoke_root/production_before.json"
production_joint_still() {
  body_query_to "$smoke_root/production_after.json" || return 1
  python3 -c '
import json
import sys
before=json.load(open(sys.argv[1], encoding="utf-8"))
after=json.load(open(sys.argv[2], encoding="utf-8"))
name="neck_yaw_joint"
before_index=before["joint_names"].index(name)
after_index=after["joint_names"].index(name)
advanced=after["joint_observed_at_ns"][after_index] > before["joint_observed_at_ns"][before_index]
unchanged=abs(after["positions"][after_index]-before["positions"][before_index]) <= 0.001
raise SystemExit(0 if advanced and unchanged else 1)
' "$smoke_root/production_before.json" "$smoke_root/production_after.json"
}
wait_until 'fresh joint feedback proves production request caused zero movement' \
  production_joint_still
printf 'PASS: Executive-to-Runtime physical request remained DEFERRED with zero dispatch\n'
stop_profile observation
emit_report embodied-observation-baseline
emit_report visual-anonymous-semantic-observation
emit_report production-physical-request-deferred

# Scenarios 4-5 use only the explicit development control profile.
start_profile development_control
wait_until 'development controller and hardware are active' controllers_ready
wait_until 'typed development control service is available' development_service_ready
wait_until 'development World Model lifecycle is active' world_model_active
wait_until 'development body query is ready' \
  body_query_to "$smoke_root/development_initial.json"

timeout --signal=INT --kill-after=5 30 \
  ros2 run ayyo_simulation_control development_command.py --position 0.1 \
  >"$smoke_root/development_valid.json"
python3 -c '
import json
import sys
result=json.load(open(sys.argv[1], encoding="utf-8"))
assert result["status"] == 1
assert result["failure_code"] == ""
assert result["has_state_feedback"] is True
assert abs(result["final_position"]-0.1) <= 0.01
' "$smoke_root/development_valid.json"
neck_at_target() {
  body_query_to "$smoke_root/development_target.json" || return 1
  python3 -c '
import json
import sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
index=state["joint_names"].index("neck_yaw_joint")
raise SystemExit(0 if abs(state["positions"][index]-0.1) <= 0.01 else 1)
' "$smoke_root/development_target.json"
}
wait_until 'World Model observes bounded DEVELOPMENT neck target' neck_at_target

timeout --signal=INT --kill-after=5 30 \
  ros2 run ayyo_simulation_control development_command.py --position 0.0 \
  >"$smoke_root/development_reset.json"
neck_at_neutral() {
  body_query_to "$smoke_root/development_neutral.json" || return 1
  python3 -c '
import json
import sys
state=json.load(open(sys.argv[1], encoding="utf-8"))
index=state["joint_names"].index("neck_yaw_joint")
raise SystemExit(0 if abs(state["positions"][index]) <= 0.01 else 1)
' "$smoke_root/development_neutral.json"
}
wait_until 'reviewed development reset restores neutral neck state' neck_at_neutral
printf 'PASS: explicit DEVELOPMENT-only neck command moved within URDF limits and reset\n'

cp "$smoke_root/development_neutral.json" "$smoke_root/invalid_before.json"
set +e
timeout --signal=INT --kill-after=5 30 \
  ros2 run ayyo_simulation_control development_command.py --position 1.3 \
  >"$smoke_root/invalid_result.json" 2>"$smoke_root/invalid_result.err"
invalid_status=$?
set -e
[[ "$invalid_status" -eq 2 ]]
python3 -c '
import json
import sys
result=json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[0])
assert result["status"] == 0
assert result["failure_code"] == "above_maximum"
assert result["has_state_feedback"] is False
' "$smoke_root/invalid_result.json"
body_query_to "$smoke_root/invalid_after.json"
python3 -c '
import json
import sys
before=json.load(open(sys.argv[1], encoding="utf-8"))
after=json.load(open(sys.argv[2], encoding="utf-8"))
name="neck_yaw_joint"
before_position=before["positions"][before["joint_names"].index(name)]
after_position=after["positions"][after["joint_names"].index(name)]
assert abs(before_position-after_position) <= 0.01
assert abs(after_position-1.3) > 1.0
assert after["status"] == 1 and after["robot_id"] == "ayyo.robot.v1"
' "$smoke_root/invalid_before.json" "$smoke_root/invalid_after.json"
controllers_ready
printf 'PASS: invalid DEVELOPMENT command failed closed without clamping or fabricated state\n'
stop_profile development_control
emit_report development-only-neck-actuation
emit_report invalid-development-command-rejected

for log_path in "$smoke_root"/*.log; do
  if grep -Eq 'Traceback|exception was never retrieved|World Model configure failed' \
    "$log_path"; then
    printf 'FAIL: scenario profile reported an unclean lifecycle in %s\n' \
      "$(basename "$log_path")" >&2
    sed -n '1,520p' "$log_path" >&2
    exit 1
  fi
done

printf 'PASS: all six Stage-6 developmental scenarios completed headlessly\n'
printf 'PASS: all scenario-owned Gazebo, ROS, bridge, controller, and fixture processes exited\n'
