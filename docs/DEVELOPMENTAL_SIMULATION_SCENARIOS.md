# Ayyo Developmental Simulation Scenario Harness Foundation v1

## Status and scope

This Stage-6 foundation provides deterministic, bounded, development-only
stories across the existing Gazebo Harmonic, ROS 2 Jazzy, observation, policy,
and one-joint simulation-control seams. Its framework identity is
`ayyo.developmental-scenarios.v1`; framework version is `1.0.0`.

The harness answers one narrow question: given a known launch profile and one
reviewed scenario, what does Ayyo observe, what does the current cognition and
Safety chain permit or defer, what can the separate DEVELOPMENT-only control
path do, and did every owned process shut down?

These results prove software/ROS/Gazebo integration against the current
DEVELOPMENT PROXY robot model. They do not validate physical mass, inertia,
actuator torque, contacts, collision geometry, balance, human-safe movement,
final industrial design, or real sensors.

## Ownership and dependency direction

The owner is the dedicated `ayyo_scenarios` ROS package backed by the
transport-neutral `ayyo-developmental-scenarios` Python distribution. This is
test orchestration, not a production architecture layer.

```text
fixed Stage-6 scenario catalog
  → immutable bounded runner/report contracts
  → ayyo_scenarios fixed launch profiles
  → existing ayyo_simulation launch
  → existing description, controllers, bridges, and World Model

production-motion scenario only:
  → Executive public request/evaluation
  → Immutable Safety public evaluation
  → Skill Manager public binding
  → Runtime Bridge public eligibility/not-dispatched result

development-control scenarios only:
  → existing SetDevelopmentJointPosition service
  → existing neck_yaw_joint controller
```

The standalone scenario distribution depends on the public Memory, Personal
Context, Executive, Safety, Skill Manager, and Runtime Bridge packages only to
construct the real read-empty production-policy proof. The ROS wrapper depends
on `ayyo_description`, `ayyo_simulation`, `launch`, `launch_ros`, `rviz2`, and
Python. No Perception, World Model, Working Memory, Memory, Memory Validation,
Personal Context, Executive, Safety, Skill Manager, Runtime Bridge, or
simulation-control production package imports or depends on the scenario
package. No lower layer calls back into the harness.

## Closed scenario and operation model

The public immutable contracts are:

- `DevelopmentScenarioDefinition`
- `DevelopmentScenarioStep`
- `DevelopmentScenarioAssertion`
- `DevelopmentScenarioStepResult`
- `DevelopmentScenarioAssertionResult`
- `DevelopmentScenarioReport`
- `ScenarioCleanupResult`
- `DevelopmentScenarioRunner`
- `DevelopmentScenarioExecutor`

Definitions carry a scenario ID, semantic version, category, description,
fixed launch profile, ordered typed steps, explicit timeout per step, expected
safe outcome, development authority requirement, assertions, and a canonical
SHA-256 fingerprint. Reports carry framework/scenario/report identities, typed
outcome, assertion results, typed failures, canonical observed identities,
policy decisions, development-authority use, production dispatch count,
bounded source summaries, and cleanup state.

The operation vocabulary is a closed enum. It contains only reviewed waits,
queries, policy evaluations, exact development neck operations, and health or
side-effect assertions. Definitions cannot contain shell commands, executable
paths, `eval`, dynamic imports, caller-selected ROS service names, or arbitrary
topics. The ROS wrapper accepts only `observation`, `development_control`, and
`sensor_absence` profiles. Unknown scenarios, profiles, and operations fail.

## Determinism and resource bounds

For equal definitions, fixed inputs, profile, and observed semantic results,
scenario and report identities are equal. Identity excludes current wall time,
PID, hostname, username, machine path, random UUID, and unordered mappings.
Runtime timing exists only in bounded waits and does not enter semantic
identity.

Version 1 enforces:

| Resource | Bound |
| --- | ---: |
| scenarios per invocation | 8 |
| steps per scenario | 32 |
| assertions per scenario | 64 |
| typed report reasons | 16 |
| report text per field | 512 characters |
| source summaries | 16 |
| observed identities | 32 |
| policy decisions | 16 |
| retained ROS samples | 64 |
| diagnostic records | 32 |
| one step deadline | 100 ms to 120 s |

The runner stores final bounded evidence only, not full topic histories, image
buffers, audio, giant messages, or unbounded logs. Outcomes are exactly
`PASS`, `FAIL`, and `NOT_APPLICABLE`; every mandatory v1 catalog scenario is
applicable. One failed required assertion or incomplete cleanup makes the
scenario fail.

## Fixed launch profiles

`developmental_scenarios.launch.py` reuses `simulation.launch.py` and its
authoritative Xacro. It does not duplicate the robot description.

| Profile | Control | Development service | World Model | Localization | RGB / semantic TEST fixture |
| --- | --- | --- | --- | --- | --- |
| `observation` | on | off | on | on | on |
| `development_control` | on | on | on | off | off |
| `sensor_absence` | on | off | on | on | off |

All automated validation passes `headless:=true` and `start_rviz:=false`.
Gazebo GUI and RViz are never correctness dependencies.

ROS 2 Jazzy `launch_testing` and `launch_testing_ros` are installed. The
milestone retains the repository's session-tagged shell adapter for the full
Gazebo proof because it already owns the actual `gz sim` child, supports three
sequential isolated profiles, validates graph state while the simulator is
live, and proves teardown. The ROS package still has focused ament contract
tests. Replacing this end-to-end ownership path with `launch_testing` would not
improve the current process guarantee.

## Implemented scenarios

### 1. Embodied observation baseline

The `observation` profile proves one `ayyo` model, active World Model, `/clock`,
one controller-derived `/joint_states` publisher, simulated IMU, simulated
`odom` to `base_link` evidence, current body state, `ayyo.robot.v1`, simulation
clock/provenance, zero durable Memory OS writes, no production motion endpoint,
and clean shutdown.

### 2. Visual and anonymous semantic observation

The same profile proves the actual Gazebo RGB bridge and retained compact frame
metadata, then the reviewed default-off TEST semantic fixture through
Perception, Working Memory, World Model, and the anonymous read-only query.
Source observation identities, fingerprints, source timestamps, optical frame,
producer/interface provenance, regions, absent PERSON confidence, genuine
OBJECT confidence `0.0`, and category semantics remain explicit. PERSON and
OBJECT remain anonymous; empty or partial evidence does not establish complete
scene absence; no persistent entity or memory write is created. This is a TEST
fixture, not a production detector.

### 3. Production physical request remains deferred

The harness constructs a real public `ExecutiveRequest` for
`robot.neck.set-position`. Executive produces a declarative proposal. The
unchanged Safety policy classifies it as physical movement and returns
`DEFERRED` with `physical_movement_information_unavailable`. Skill Manager
returns `INELIGIBLE` with `safety_deferred`; Runtime Bridge returns `DEFERRED`
with no request; `RuntimeDispatcher.not_dispatched` returns `NOT_ELIGIBLE`.
Production dispatch, development-service calls, controller commands, and
durable writes remain exactly zero. A later controller-derived state sample
must show the requested neck joint unchanged. This is the expected PASS.

### 4. Explicit development-only neck actuation

Only the `development_control` profile exposes the existing
`SetDevelopmentJointPosition` service. The smoke captures initial
`neck_yaw_joint`, commands `0.1` rad, requires feedback within `0.01` rad,
observes the result through World Model, and returns to the reviewed neutral
`0.0` rad state. The authoritative URDF range remains `[-1.2, 1.2]` rad.
Development injection is recorded; production dispatch remains zero.

### 5. Invalid development command fails closed

The same explicit profile requests `1.3` rad. The current public service must
return `REJECTED`, typed reason `above_maximum`, and no state-feedback success.
The neck cannot reach that target, World Model cannot fabricate it, controllers
remain active, and a later body query succeeds. The policy is not changed and
the target is not silently clamped into an accepted result.

### 6. Optional visual source absent

The `sensor_absence` profile leaves camera and semantic production off. World
Model and the simulation clock remain available; the camera has no publisher;
visual and interpretation counts remain zero; two read-only semantic queries
remain empty and explicitly state that physical-scene occupancy is unknown.
No stale evidence is refreshed and the system shuts down cleanly.

The optional memory-review scenario is deliberately not implemented. There is
no ROS memory service, and introducing one or crossing process-private state
would be artificial. The already-published transport-neutral pipeline remains
covered by its own tests.

## Process ownership and time policy

`scripts/smoke_developmental_scenarios.sh` sources
`scripts/smoke_processes.sh`. Each profile receives a private run marker,
Gazebo partition, bounded valid ROS domain, ROS log directory, and tracked
process session. Readiness uses explicit deadline polling for lifecycle state,
topics, services, model count, queries, controllers, and joint feedback. Fixed
sleeps are not accepted as correctness proof.

Shutdown signals only the owned launch/session. The helper waits for all tagged
children, may escalate only within that owned set, and fails if cleanup was not
bounded. The smoke then requires its isolated ROS graph to be empty. It never
uses `pkill`, `killall`, a broad process match, or another user's ROS process.

Run the automated Stage-6 proof after building:

```bash
./scripts/build_workspace.sh
./scripts/smoke_developmental_scenarios.sh
```

The smoke emits six bounded deterministic JSON reports and removes runtime
artifacts after success.

## Read-only catalog inspection

The `ayyo-developmental-scenarios` package installs the `ayyo-scenarios`
console command. It exposes four fixed local inspection operations:

```bash
ayyo-scenarios list
ayyo-scenarios describe embodied-observation-baseline
ayyo-scenarios manifest
ayyo-scenarios verify
```

`list` renders the six reviewed definitions in their canonical declared order.
`describe` resolves one exact ID through the existing catalog lookup and shows
its typed steps, assertions, and timeouts. `manifest` emits byte-deterministic
canonical JSON under schema `ayyo.developmental-scenario-manifest.v1`, version
`1.0.0`. `verify` recomputes scenario and manifest fingerprints and checks
identity uniqueness, order, enum membership, authority declarations, semantic
versions, and resource bounds.

These commands only read immutable in-process catalog definitions. They do not
start ROS, Gazebo, launch files, controllers, simulation, development motion,
Executive cognition, Safety evaluation, Runtime Bridge dispatch, or memory
persistence. They accept no shell command, executable, ROS name, Python module,
or filesystem path.

## Optional manual graphical inspection

This route reuses the authoritative description, Gazebo world, controller,
camera, and RViz configuration:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=121
export GZ_PARTITION=ayyo_scenario_manual_121
ros2 launch ayyo_scenarios developmental_scenarios.launch.py \
  profile:=observation headless:=false start_rviz:=true
```

A human may inspect the proxy robot, TF tree, joint state, camera frame, body
state, and—using the separate `development_control` profile—bounded neck
movement. Merely launching GUI tools is not automated PASS evidence. No human
graphical inspection was performed for this milestone.

## Implemented and not implemented

Implemented: the deterministic Stage-6 framework; immutable bounded reports;
headless profiles; embodied, anonymous visual semantic, production-safe defer,
development neck actuation/reset, invalid-command, and sensor-absence
scenarios; isolated process ownership and cleanup; and an optional manual
Gazebo/RViz route.

Not implemented: production motion authorization, a production Runtime motion
endpoint, MoveIt integration, Nav2 integration, trajectories, arms or legs,
biped walking, balance, manipulation, physical safety certification, final
mechanical geometry, real sensor validation, automatic learning, or autonomous
durable memory promotion.
