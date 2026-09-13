# Manipulation Trajectory & Execution Eligibility Foundation v1

## Scope

Stage 9B adds one transport-neutral pre-execution boundary above the reviewed
Stage 9A planning result:

```text
reviewed Stage 9A plan decision
→ exact trajectory construction request
→ deterministic bounded timing
→ immutable trajectory evidence
→ independent Safety eligibility evidence
→ explicit Skill handoff eligibility evidence
→ future simulation Runtime handoff review eligibility
→ stop
```

A positive Safety status is
`TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW`. The final positive handoff status
means that the same evidence may be considered by a future, separately reviewed
Stage 9C simulation boundary. Neither status grants permission to move. Every
positive artifact remains `NOT_EXECUTED`, physical validation remains `ABSENT`,
and the future Runtime endpoint is explicitly `NOT_REGISTERED`.

## Exact Stage 9A binding

`TrajectoryConstructionRequest` embeds the complete immutable
`ManipulationPlanningDecision`. Construction recursively rebuilds and verifies
that decision and requires its exact positive, collision-free-review state.
The request additionally exposes derived content bindings for the authoritative
robot model, joint catalog, group, collision model, Stage 9A request, candidate
path, MoveIt collision proof, plan evidence, and decision. Those duplicate
bindings are recomputed from the embedded decision and cannot be caller chosen.

Consequently an ID string is never sufficient. A rejected decision, stale
identity, different request/evidence/proof, waypoint mutation or reordering,
joint-order change, changed robot model or limit, collision-positive mutation,
or rehashed outer wrapper fails before a trajectory can be accepted.

## Deterministic timing contract

Version 1 uses no dynamics engine. For each adjacent waypoint and each reviewed
planning joint it computes:

```text
joint_time = absolute_position_delta / (reviewed_velocity_limit × velocity_scale)
segment_time = max(minimum_segment_duration, every joint_time)
```

The default velocity scale is `0.25` and is bounded to `[0.01, 0.25]`.
Minimum segment duration is bounded to `[0.001, 1.0]` seconds. Maximum total
duration is explicit and bounded to `300.0` seconds; the default is `30.0`.
Point count is explicit and cannot exceed 129. Each point retains the exact
joint order and positions from Stage 9A. Times begin at `0.0`, then increase
strictly; duplicate timestamps, stationary adjacent points, non-finite values,
negative time, out-of-limit positions, missing/implicit joints, and excessive
duration or point count fail closed.

The trajectory contains positions and `time_from_start` only. It does not
fabricate acceleration, torque, payload, force, contact, stability, thermal,
latency, or dynamics evidence.

## Safety and handoff boundary

The Safety proposal is closed to one step and one capability:
`manipulation.trajectory.simulation-review`. Its parameters bind the exact
Stage 9A request/evidence/decision, candidate path, collision proof, Stage 9B
request/trajectory/evidence, execution disposition, and physical-validation
state. The expected result is information, and the reviewed Safety
classification required for a positive result is `INTERNAL_NON_ACTUATING`.
This classifies inspection of immutable evidence; it does not classify the
future physical movement as safe.
An otherwise eligible Safety decision carrying any other hazard classification
is explicitly ineligible with `SAFETY_CLASSIFICATION_MISMATCH`; it is not
misreported as a Safety block or a physical-safety result.

The caller must explicitly obtain and supply both the Safety decision and Skill
Manager binding. Stage 9B re-evaluates Safety against the supplied policy,
first reconstructs every capability rule and the complete Safety policy/kernel,
and rejects any mismatch between current policy content, indexes, and derived
fingerprint. It retains that exact proposal/decision/kernel context. Stage 9B
also reconstructs every Skill definition in the current registry through the
public constructors, including nested value schemas, context/resource
requirements, backend and lifecycle semantics, then reconstructs the registry,
selection, binding, and complete invocation. Exact equality of every semantic
and derived identity field is required before recording an inert reference to
the future review backend. It
does not call `SkillManagerService.bind`, import Runtime Bridge, create a
Runtime request or decision, register an endpoint, or dispatch anything.
The Safety reference also carries a recomputable binding fingerprint over the
full trajectory and Stage 9A lineage. A positive result is accepted only when
its retained authoritative Safety context independently reproduces that exact
reference, so changing the binding and rehashing a wrapper cannot reuse Safety
evidence from trajectory A for trajectory B.

## Canonical evidence

All nine public artifacts are frozen, bounded, schema/version explicit, and
content-addressed. Serialization verifies the complete object before emitting
bytes. Parsing requires the one sorted compact UTF-8 JSON spelling and rejects
duplicate keys, extra or missing fields, unknown schemas/versions/enums,
non-finite numbers, negative zero, excessive nesting/nodes/bytes/collections,
malformed nested Stage 9A evidence, stale identities, and nested mutation even
when an attacker recomputes outer hashes. Accepted artifacts satisfy:

```text
parse(bytes) → object → serialize(object) == bytes
```

Safety-result reconstruction additionally requires the original Executive
proposal, Safety decision, and current Safety kernel. Final handoff-decision
reconstruction also requires the original Skill binding and current Skill
Manager. These validation contexts are deliberately not invented from identity
strings or wrapper hashes; callers must supply them, and reconstruction reruns
the same deterministic Safety and Skill checks before accepting the payload.
Expected malformed upstream immutable-contract state is converted to
`TrajectoryValidationError` at evaluation/verification boundaries and
`TrajectorySerializationError` at canonical publication/reconstruction
boundaries rather than leaking incidental upstream implementation exceptions.
This is repository-local provenance validation, not authentication.

## Authority exclusions

Production Stage 9B contains no ROS package, publisher, action or service
client; no MoveGroup or FollowJointTrajectory execution; no controller manager,
ros2_control command, Gazebo motion, hardware interface, subprocess, network,
database, background worker, dynamic model loader, policy activation, or
learning/promotion operation. Existing left-arm command interfaces remain
disabled and no arm controller is added.

Stage 9C is intentionally separate: a future simulation-only execution boundary
must independently define and review Runtime endpoint registration, controller
acceptance, simulation feedback, motion Safety treatment, cancellation, timeout,
and failure behavior. Physical manipulation remains later still, after separate
simulation and physical-safety gates.

## Validation

Run the focused suite while retaining any ROS Python path installed by the
sourced environment:

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:manipulation_planning/src:manipulation_trajectory/src${PYTHONPATH:+:$PYTHONPATH} \
  python3 -m pytest -q manipulation_trajectory/tests
```

The package is transport-neutral, so Stage 9B itself adds no ROS package to
build. Stage 9A's existing ROS/MoveIt proof remains the authoritative external
collision evidence feeding the reviewed planning decision.
