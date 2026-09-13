# Manipulation Simulation Execution & Observed Outcome Foundation

Stage 9C is Ayyo's first manipulation milestone permitted to move the left arm.
That authority exists only inside the reviewed Gazebo Harmonic development
simulation, behind an explicit default-off controller profile and a separate
caller invocation. It does not authorize physical hardware or production
Runtime execution.

## Boundary and flow

The implementation extends the existing Stage 9A and Stage 9B evidence chain;
it does not plan another path or reinterpret Stage 9B eligibility:

```text
exact positive Stage 9B future-simulation-handoff review decision
→ recursively verified Stage 9A/9B/Safety/Skill lineage
→ immutable simulation execution request and fixed controller contract
→ bounded dense samples of the exact position-only trajectory
→ MoveIt PlanningScene preflight using the reviewed URDF/SRDF/ACM/scene
→ fresh exact simulated start state and active controller/action evidence
→ one explicit FollowJointTrajectory goal
→ bounded controller outcome and fresh final joint-state observation
→ immutable canonical Stage 9C result
→ stop
```

The transport-neutral `ayyo-manipulation-simulation-execution` core owns the
contracts and pure validation/evaluation functions. The ROS package
`ayyo_manipulation_simulation_execution` owns the MoveIt preflight executable,
the fixed action adapter, and the dedicated launch wrapper. Stage 9A, Stage 9B,
Executive, Safety Kernel, Skill Manager, Runtime Bridge, and Simulation Control
do not depend on Stage 9C.

## Exact Stage 9B trust boundary

`SimulationExecutionRequest` accepts only a recursively valid positive
`ExecutionHandoffEligibilityDecision` whose Runtime endpoint remains
`NOT_REGISTERED`, execution remains `NOT_EXECUTED`, and physical validation
remains `ABSENT`. The retained graph includes the exact Stage 9A robot model,
joint catalog/order and limits, group, scene, candidate path, collision proof,
request/evidence/decision, the exact Stage 9B timing configuration and every
trajectory point/time, and the authoritative Stage 9B Safety and Skill
contexts.

Stage 9C calls the Stage 9B recursive verifier; it does not trust wrapper IDs.
Canonical reconstruction delegates the nested handoff to the Stage 9B public
reconstruction seam and requires the source Executive proposal, Safety
decision/kernel, Skill binding, and Skill Manager again. Substitution, stale
derived identity, cross-trajectory evidence, malformed nested data, reordering,
or rehashing fails before goal construction.

## Default-off simulation controller

The authoritative description adds
`simulation_manipulation_control`, default `false`. It has effect only inside
the already simulation-gated `ros2_control` block. The ordinary description
has no `ros2_control` system, normal simulation defaults to no controller, and
the existing development-control profile retains only the neck position
command interface.

The dedicated Stage 9C launch explicitly selects simulation control and
manipulation control. That profile replaces the neck command interface with
exactly these four position command interfaces, in Stage 9A order:

- `left_shoulder_yaw_joint/position`
- `left_shoulder_pitch_joint/position`
- `left_elbow_flex_joint/position`
- `left_wrist_yaw_joint/position`

No fixed-chain, right-arm, leg, or neck command interface is exposed by that
profile. Its controller is
`ayyo_left_arm_trajectory_controller`, type
`joint_trajectory_controller/JointTrajectoryController`, with position command
and position/velocity state interfaces, `allow_partial_joints_goal: false`,
simulation time, and the fixed action endpoint:

```text
/ayyo_left_arm_trajectory_controller/follow_joint_trajectory
```

Launching the profile loads controller infrastructure but sends no goal and
causes no planned motion. The explicit client is required.

## Exact trajectory and collision preflight

The action adapter copies Stage 9B joint names, joint order, positions, point
count, and `time_from_start` values exactly. Points carry positions only; it
does not fabricate velocities or accelerations. For position-only points, the
reviewed controller configuration follows the corresponding joint-space line
segments. Stage 9C samples those same segments at a maximum joint delta of
`0.01` rad, with at most 64 subdivisions per segment, 4096 total samples, and
every exact endpoint included.

The C++ preflight loads the authoritative expanded URDF and reviewed SRDF,
checks their exact content fingerprints, the left-arm group/order, and the
allowed-collision matrix, then constructs the existing MoveIt PlanningScene
and exact request collision objects. Every dense sample is checked for joint
limits, self collision, and environment collision. Any collision, mismatch,
malformed input, changed model/scene/path/trajectory, or resource-bound breach
prevents goal construction.

This is deterministic bounded simulation preflight evidence. It is not
continuous swept-volume collision certification, contact/force safety,
physical collision certification, or proof of real-world safety between
samples.

## Simulated start, execution, and observation

Before dispatch, the adapter observes the exact four joints from
`/joint_states`, requires finite position values and a sample no more than
`0.5` seconds old, and compares them with the first Stage 9B waypoint using a
maximum `0.01` rad development-only tolerance. It also verifies the exact
controller type, lifecycle state, claimed interfaces, simulated hardware
state, state broadcaster, and action availability. A mismatch is rejected; the
adapter does not teleport, prepend, or replan a path to the start.

The dedicated profile sets gz_ros2_control's position tracking gain to `1.0`
so the simulated arm can converge under its simulated load. This parameter is
content-addressed with the controller configuration, remains absent from the
ordinary neck-only profile, and has no physical-controller or hardware meaning.
JointTrajectoryController enforces a `0.02` rad goal tolerance per reviewed
joint, a `0.05` rad/s stopped-velocity tolerance, and at most four seconds of
simulated goal-settling time. These development-only simulation values fit
inside the execution contract's five-second margin and have no physical-safety
meaning.

One accepted goal receives a timeout equal to its reviewed duration plus a
fixed five-second development margin. There is no automatic retry or
replacement goal. On timeout the adapter requests cancellation and records
whether cancellation was confirmed. Unavailable server, inactive controller,
goal rejection, path/goal tolerance violation, cancellation, abort, simulator
shutdown, malformed feedback, and missing final feedback remain explicit
failure outcomes.

Successful classification requires an accepted action, controller success,
at least one valid correlated feedback sample, and a fresh post-result simulated
joint-state observation that settles within the original execution deadline,
with no timeout/cancellation and final absolute error no greater than `0.02`
rad on every reviewed joint. This observation period never resends or replaces
the action. The bounded
observation records start/completion times, start/end/target positions, final
errors, feedback count, controller code, and cancellation/timeout truth. It
does not retain an unbounded telemetry stream.

## Evidence and authority semantics

Deterministic requests, controller configuration, sampling policy, preflight
inputs, and exact goals are content-addressed. Live observations and results
also have strict canonical representations and integrity checks, but their
identities legitimately include run-specific timestamps and observed state.

A positive result means exactly:

- `SIMULATION_EXECUTION_COMPLETED`
- `DEVELOPMENT_SIMULATION_ONLY`
- `NOT_PHYSICALLY_VALIDATED`
- `NO_HARDWARE_AUTHORITY`
- `NO_PRODUCTION_RUNTIME_AUTHORITY`

It does not mean physically safe, hardware validated, production authorized,
or eligible for physical execution. Stage 9C adds no Runtime Bridge endpoint,
production Skill implementation, automatic Skill invocation, physical driver,
CAN/serial/USB path, arbitrary publisher/action endpoint, network service,
persistence, daemon, background worker, autonomous retry, or planning loop.

## Validation

Run the core suite while retaining the ROS Python environment used by `xacro`:

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:manipulation_planning/src:manipulation_trajectory/src:manipulation_simulation_execution/src${PYTHONPATH:+:$PYTHONPATH} \
  python3 -m pytest -q manipulation_simulation_execution/tests
```

Build and test the relevant ROS packages in disposable locations when desired:

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
colcon build \
  --packages-up-to ayyo_manipulation_simulation_execution \
  --build-base /tmp/ayyo-stage9c-build \
  --install-base /tmp/ayyo-stage9c-install
source /tmp/ayyo-stage9c-install/setup.bash
colcon test \
  --packages-select ayyo_manipulation_simulation_execution \
  --build-base /tmp/ayyo-stage9c-build \
  --install-base /tmp/ayyo-stage9c-install
colcon test-result --test-result-base /tmp/ayyo-stage9c-build --verbose
```

Run the one owned headless Gazebo movement proof only as an explicit
development action:

```bash
AYYO_STAGE9C_INSTALL_SETUP=/tmp/ayyo-stage9c-install/setup.bash \
  scripts/smoke_manipulation_simulation_execution.sh
```

The proof's reviewed development fixture moves from
`(0.0, 0.0, 0.2, 0.0)` to `(0.3, 0.0, 0.8, 0.2)` in canonical left-arm joint
order. Stage 9A owns and collision-checks that candidate path, Stage 9B owns
its exact timing, and Stage 9C forwards the resulting trajectory without
altering its geometry.

## Remaining Stage 9 work

Stage 9C does not implement grasp/end-effector semantics, trajectory dynamics,
force/contact reasoning, independent physical-movement Safety policy,
production Runtime/Skill execution, emergency-stop integration, physical
calibration, or hardware control. Those remain separately reviewed future
milestones; Stage 9D and physical integration have not begun.
