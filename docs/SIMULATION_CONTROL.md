# Ayyo Simulation Control & Actuation Foundation v1

## Status and mission

Simulation Control & Actuation Foundation v1 implements one deliberately small,
opt-in actuation path for the Gazebo Harmonic development model. It proves that
one reviewed joint can receive a finite, URDF-bounded position target through a
typed Ayyo boundary, a standard ros2_control controller, and
`gz_ros2_control`, and that controller-derived state can prove the resulting
simulated motion.

This milestone is not walking, manipulation, whole-body control, autonomous
movement, MoveIt, Nav2, a physical driver, or physical-safety certification.
The only commandable joint is `neck_yaw_joint`. The default RViz and Gazebo
launches remain non-actuating.

The automated controlled smoke has exercised controller lifecycle, hardware
interfaces, single-publisher joint state, typed valid and invalid commands,
feedback-backed motion, and bounded shutdown. Graphical controlled Gazebo
review remains a human validation step and is not claimed as executed.

## Architecture and dependency direction

The intended production direction remains:

```text
Executive proposal
→ Immutable Safety decision
→ Skill Manager binding
→ Runtime Bridge eligibility
→ typed simulation-control adapter
→ ros2_control Controller Manager
→ gz_ros2_control GazeboSimSystem
→ Gazebo Harmonic
→ joint_state_broadcaster feedback
```

Each layer consumes only reviewed public contracts from the layer above it.
Simulation control is downstream infrastructure. It does not plan, approve,
reinterpret Safety, select skills, dynamically discover endpoints, or grant
runtime eligibility.

The standalone `ayyo-simulation-control` Python distribution depends only on
`ayyo-runtime-bridge==0.1.0`. Its core policy and controller-port modules do not
import ROS. The `runtime_boundary` module is intentionally separate because it
needs the full standalone Executive → Safety → Skill → Runtime dependency
chain. The ROS package installs the common control core plus the explicit
development adapter; importing the common top-level package does not import or
weaken the Runtime Bridge.

The lower description and simulation packages do not import Executive, Safety,
Skill Manager, or Runtime Bridge. Their dependencies point only toward the
description, typed control adapter, controller packages, and Gazebo.

## Production authorization is intentionally closed

`RuntimeSimulationControlBoundary` recognizes exactly this future runtime
identity:

| Field | Reviewed value |
| --- | --- |
| Capability | `simulation.joint.position.set` |
| Backend | `simulation.control.position.v1` |
| ROS package | `ayyo_interfaces` |
| Interface | `ApplyRuntimeJointPosition` |
| Service | `/ayyo/simulation_control/apply_runtime_joint_position` |

It accepts only an exact current `RuntimeDecision` with complete request,
decision, invocation, endpoint-binding, and registry fingerprints. It
revalidates that decision against the current binding and rejects changed,
ineligible, blocked, deferred, malformed, or endpoint-substituted evidence.

Safety Kernel v1 classifies physical movement as `DEFERRED`. Consequently, a
real physical-movement binding cannot become Runtime Bridge `ELIGIBLE`, and the
production translator cannot currently create a dispatchable motion command.
An eligible informational skill also cannot be relabeled as movement. There is
no production ROS service implementation for
`ApplyRuntimeJointPosition` in this milestone. This is deliberate no-bypass
behavior, not an incomplete success claim.

## Explicit development injection boundary

Development motion uses a separate service and authority kind:

```text
enable_control:=true
+ enable_development_control:=true
→ /ayyo/development/set_joint_position
→ SetDevelopmentJointPosition
→ development.simulation.control.v1 authority
```

Both flags default to `false`. `enable_development_control` is effective only
with control enabled. The development service starts after the entity,
`joint_state_broadcaster`, and position controller spawners have completed.
Its name, message type, controller topic, controller identity, hardware
identity, and command interface are constants in reviewed source. A request
cannot supply a ROS topic, service, action, plugin, shell command, executable,
or graph endpoint.

The convenience command is also explicit development tooling:

```bash
ros2 run ayyo_simulation_control development_command.py --position 0.1
```

It always targets the fixed typed service. `--joint` permits negative testing
of the policy; it does not choose a controller or ROS endpoint. Exit status is
`0` only for feedback-backed completion, `2` for a typed rejection, and `1`
for client/clock/service failure.

## ros2_control and Gazebo architecture

Control mode expands the authoritative Xacro with:

- `gz_ros2_control/GazeboSimSystem` as hardware `AyyoSystem`;
- the Gazebo Harmonic `gz_ros2_control-system` plugin;
- the installed `controllers.yaml` path;
- position, velocity, and effort state interfaces for all 18 movable joints;
- one position command interface, `neck_yaw_joint/position`; and
- initial position `0.0` for the development interfaces.

No Gazebo Classic `gazebo_ros2_control` dependency or plugin is present.
Control mode forces the simulated model to non-static. Non-control mode retains
the original static model and contains no control plugin or ros2_control block.

Controller Manager runs at 100 Hz in simulation time and enforces URDF command
limits. The launch activates controllers in this order:

```text
spawn Ayyo entity
→ joint_state_broadcaster
→ ayyo_neck_position_controller
→ optional development adapter
```

`ayyo_neck_position_controller` is a standard
`forward_command_controller/ForwardCommandController` with the position
interface and exactly one joint. This small controller is enough for the
one-joint foundation and introduces no custom controller framework.

## First controlled joint

`neck_yaw_joint` was selected because it is an existing visible upper-body
joint, is not part of locomotion or ground contact, starts at zero, and already
has symmetric authoritative development limits:

```text
lower:    -1.2 rad
upper:     1.2 rad
effort:    8.0
velocity:  1.5 rad/s
```

No limit was invented or copied into the adapter. `UrdfJointLimitCatalog`
parses the expanded `robot_description`, verifies unique supported joint
contracts, and owns a deterministic fingerprint of the complete parsed catalog
and exact allowlist. Adding another joint later requires an explicit source
allowlist change, an additional reviewed ros2_control command interface,
controller configuration, and tests.

## Typed command contract

The core `SimulationControlCommand` is immutable and contains:

- schema-pinned command type `set_joint_positions`;
- one or more immutable joint/position targets, with v1 policy accepting
  exactly one allowlisted target;
- `issued_at_ns` and `expires_at_ns` in ROS simulation time;
- either explicit development-test authority or the complete Runtime Bridge
  authority evidence chain; and
- canonical SHA-256 command identity and fingerprint.

Targets are finite real numbers. Booleans, strings, NaN, positive infinity,
negative infinity, duplicate target names, empty target lists, excessive target
counts, unsupported types, invalid time windows, and malformed authority
identities fail during model reconstruction. Command target order is canonical,
so semantically identical target sets have identical identities.

`SetDevelopmentJointPosition.srv` exposes only the reviewed set-position enum,
joint and position arrays, issue time, bounded validity duration, and injection
identity. The response carries typed status/failure, command and result
identities/fingerprints, an explicit feedback flag, before/after positions, and
observation time.

## Validation and dispatch semantics

The adapter evaluates a command in this order:

1. Reconstruct the immutable command and verify its fingerprint.
2. Validate exactly one target against the current URDF catalog and allowlist.
3. Reject issue time ahead of the current simulation clock or an expired
   validity window.
4. Revalidate the development session or Runtime authority.
5. Obtain fresh controller-manager and hardware-component evidence with a
   bounded wall-time lifecycle query.
6. Read a fresh authoritative `neck_yaw_joint` state sample.
7. Read simulation time again and recheck the command validity window.
8. Require hardware, position controller, and state broadcaster to be active;
   require the exact controller identity and at least one command subscriber.
9. Revalidate authority again immediately before dispatch.
10. Publish only to the fixed reviewed controller command topic.
11. Wait a bounded monotonic-wall-time interval for a later state sequence.
12. Require feedback simulation time to be at or after dispatch and not in the
    future, observable state change of at least `0.001` rad, and target error no
    greater than `0.01` rad.

Command expiry is an authorization-to-dispatch window, not a promise that the
physical result completes by the expiry instant. Feedback waiting uses a
bounded monotonic clock so a paused or faulty simulation clock cannot create an
unbounded service callback. Command and observation timestamps remain
simulation-time values and are never silently compared to wall-clock epoch
time.

## Controller and joint-state ownership

With `enable_control:=false`, the existing development
`joint_state_publisher` owns zero joint states for TF visualization. With
`enable_control:=true`, that node is disabled and
`joint_state_broadcaster` is the sole `/joint_states` publisher. The
broadcaster publishes position, velocity, and effort state for all 18 movable
joints. The controlled smoke asserts publisher count `1` and the absence of
`/ayyo_sim_joint_state_publisher`.

The adapter subscribes to `/joint_states`, but it never publishes that topic.
Controller lifecycle is not inferred from topic names: the adapter queries
`/controller_manager/list_controllers` and
`/controller_manager/list_hardware_components`, verifies exact types and names,
and requires `AyyoSystem` to expose `neck_yaw_joint/position` as available and
claimed.

## Result and feedback semantics

`SimulationControlResult` has two statuses: `REJECTED` and `COMPLETED`. Its
evidence flags form a strict causal chain:

```text
boundary accepted
→ controller dispatched
→ feedback observed
→ state changed
→ target reached
```

No flag may skip an earlier boundary. Feedback evidence requires a final value
and observation time; boundary acceptance requires the initial value. A result
cannot report `COMPLETED` unless every flag is true, the command is intact, no
failure is present, before/after feedback exists, state changed, and the target
was reached within tolerance. ROS accepting a publication is therefore not
success. The observed state change is the downstream proof that the controller
and simulated hardware acted on the request.

Failures and results use canonical SHA-256 fingerprints and derived IDs. A
failure associated with a command must match that command. Impossible evidence
order, stale identity, non-finite feedback, or observation time predating the
command is rejected during reconstruction.

## Public APIs

The top-level `ayyo_simulation_control` package exports the typed authority,
command, target, controller snapshot/lifecycle, joint sample, limit catalog,
failure, result, adapter, gateway/revalidator protocols, development gate,
constants, and validation errors. It exports no ROS node and does not import the
optional upstream chain. Production translation is explicitly imported from
`ayyo_simulation_control.runtime_boundary` as
`RuntimeSimulationControlBoundary` with its exact endpoint constants.

The ROS surface consists only of:

- service type `ayyo_interfaces/srv/SetDevelopmentJointPosition`;
- service name `/ayyo/development/set_joint_position`;
- node executable `simulation_control_node.py`; and
- explicit test client `development_command.py`.

The raw `/ayyo_neck_position_controller/commands` topic is an internal fixed
gateway port, not a public Ayyo command API.

## Failure taxonomy

The public failure codes are intentionally explicit:

| Area | Codes |
| --- | --- |
| Command shape | `malformed_command`, `unsupported_command_type`, `duplicate_target` |
| Joint policy | `unknown_joint`, `fixed_joint`, `joint_not_allowlisted`, `below_minimum`, `above_maximum` |
| Time | `stale_command`, `command_from_future` |
| Upstream authority | `malformed_upstream_identity`, `upstream_not_eligible`, `stale_runtime_binding`, `runtime_endpoint_mismatch` |
| Development authority | `development_injection_disabled`, `development_session_changed` |
| Lifecycle | `control_system_inactive`, `controller_unavailable`, `controller_inactive`, `state_broadcaster_inactive` |
| Controller port | `command_receiver_unavailable`, `controller_rejected` |
| Feedback | `state_unavailable`, `state_stale`, `feedback_timeout`, `target_not_reached` |

Unknown/fixed/nonallowlisted joints are distinguished. Boundary values `-1.2`
and `1.2` are inclusive; values beyond them are rejected before controller
access. Expected failures become deterministic typed results. Programming
defects are not hidden behind broad exception handlers.

## No-bypass guarantees

Production control source contains no arbitrary ROS endpoint field, wildcard
bridge, topic/action transport selection, dynamic import, plugin discovery,
filesystem execution, subprocess, shell, `eval`, or `exec`. The ROS adapter has
fixed endpoint constants and catches only typed validation failures. The core
contains no ROS, network, process, or filesystem command surface.

The implementation does not:

- reinterpret Safety `DEFERRED`, `BLOCKED`, or approval-required decisions;
- create a direct Executive-to-controller path;
- treat an informational eligible skill as movement authority;
- dynamically register a controller or command joint;
- expose the raw controller command topic through its API;
- claim success from message acceptance alone; or
- add physical hardware behavior.

## Automated validation

Build and run all ROS tests:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/build_workspace.sh
./scripts/test_workspace.sh
```

Run standalone simulation-control tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:simulation_control/src \
python3 -m unittest discover -s simulation_control/tests -v
```

Run the non-control and controlled headless smokes:

```bash
./scripts/smoke_simulation.sh
./scripts/smoke_simulation_control.sh
./scripts/smoke_developmental_scenarios.sh
```

The controlled smoke uses a process-isolated Gazebo partition and a fresh ROS
domain unless `AYYO_CONTROL_SMOKE_DOMAIN_ID` is explicitly set. It never
publishes directly to the raw controller topic.
The Stage-6 harness additionally proves the policy contrast in one repeatable
suite: a real Executive physical request remains Safety `DEFERRED` with no
Runtime request and no joint movement, while the separately flagged
DEVELOPMENT service moves only `neck_yaw_joint`, restores neutral, and rejects
`1.3` rad without clamping.

## Exact manual graphical and control validation

From the repository root, build once:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/build_workspace.sh
source ros2_ws/install/setup.bash
```

In terminal 1, select an isolated graph and start controlled graphical Gazebo:

```bash
export ROS_DOMAIN_ID=121
export GZ_PARTITION=ayyo_control_manual_121
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false use_meshes:=false spawn_z:=0.95 \
  enable_control:=true enable_development_control:=true
```

Confirm Gazebo renders the proxy robot on the ground plane. This is a graphical
development check, not validation of final geometry, inertias, collision,
stability, or hardware.

In terminal 2, start from the same repository root, source the same workspace,
and use the same graph:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=121
export GZ_PARTITION=ayyo_control_manual_121
```

Inspect controller status:

```bash
ros2 control list_controllers --controller-manager /controller_manager
```

Expected: `joint_state_broadcaster` and
`ayyo_neck_position_controller` are both `active`.

Inspect hardware and interfaces:

```bash
ros2 control list_hardware_components --controller-manager /controller_manager
ros2 control list_hardware_interfaces --controller-manager /controller_manager
```

Expected: `AyyoSystem` is active; exactly one command interface is listed,
`neck_yaw_joint/position [available] [claimed]`; the 18 joints expose
position/velocity/effort state.

Inspect authoritative state and its sole publisher:

```bash
ros2 topic info /joint_states --verbose
ros2 topic echo --once /joint_states sensor_msgs/msg/JointState
```

Expected: publisher count is `1`, the publisher is
`joint_state_broadcaster`, and `neck_yaw_joint` is present.

Run one minimal bounded motion proof while watching the head turn in Gazebo:

```bash
ros2 run ayyo_simulation_control development_command.py --position 0.1
```

Expected: exit `0`; JSON status `1`; `has_state_feedback:true`; different
initial/final positions; final position within `0.01` rad of `0.1`; command and
result IDs/fingerprints are populated.

Run the out-of-range rejection proof:

```bash
ros2 run ayyo_simulation_control development_command.py --position 1.3
printf 'exit=%s\n' "$?"
```

Expected: exit `2`; JSON status `0`; failure `above_maximum`;
`has_state_feedback:false`; no additional motion.

Return to terminal 1 and press `Ctrl-C`. Then, in terminal 2, verify the isolated
ROS graph is empty and no Gazebo process for this partition remains:

```bash
ros2 node list --no-daemon
pgrep -af 'gz sim.*ayyo_foundation.sdf|simulation.launch.py' || true
```

## Known limitations and future expansion

- Safety v1 defers physical movement, so no production-authorized actuation is
  currently possible.
- The runtime production service and concrete runtime transport do not exist.
- The development service is local test injection, not identity or approval.
- Only `neck_yaw_joint` has a command interface.
- The forward position controller is a foundation proof, not a motion planner
  or smooth trajectory generator. ros2_control may visibly rate-limit a step
  target using the URDF velocity bound before the target is reached.
- Proxy geometry, provisional inertias, contacts, dynamics, and joint limits
  are not final mechanical or physical-safety data.
- There is no collision, force, workspace, balance, self-collision,
  emergency-stop, watchdog, authenticated operator, or hardware safety layer.
- There is no persistence of command audit records beyond normal ROS logs and
  returned deterministic identities.

Future joint expansion must remain explicit: review mechanics and safety,
extend the exact allowlist, add only the needed ros2_control command interface,
bind a reviewed controller, add typed service/schema support, retain
dispatch-time authority and simulation-time revalidation, and prove feedback.
Production movement additionally requires dedicated motion/contact/workspace
safety, authenticated authorization, emergency-stop integration, runtime
scheduling, and a current Runtime Bridge path. Simulation convenience must
never be promoted into physical authority.
