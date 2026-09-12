# Manipulation Planning & Collision Safety Foundation v1

## Purpose and status

This milestone begins Stage 9 with a bounded planning-only foundation for
Ayyo's left arm. It makes robot-model identity, joint limits, planning inputs,
collision-scene evidence, candidate waypoints, and collision-check outcomes
explicit and independently reviewable before any execution boundary exists.

A positive decision is `PLAN_AVAILABLE_FOR_REVIEW`. It is never permission to
move and is always paired with `NOT_EXECUTED` and
`PHYSICAL_VALIDATION_ABSENT` evidence.

## Architecture boundary

```text
expanded authoritative Ayyo URDF supplied by caller
→ immutable robot-model fingerprint
→ exact immutable left-arm joint catalog and group
→ exact start state + bounded joint-space goal
→ bounded fixed-box planning scene in base_link
→ deterministic candidate interpolation
→ external MoveIt PlanningScene collision check
→ exact immutable plan evidence
→ pure review decision
→ stop
```

The transport-neutral `ayyo_manipulation_planning` core depends only on the
Python standard library. It performs no file, process, network, ROS, learned-
model loading, background, persistence, control, or execution operation. The
caller supplies already-expanded URDF text. The ROS package
`ayyo_manipulation_planning` owns a
headless C++ PlanningScene proof; it creates no ROS node, topic, service,
action, MoveGroup client, Runtime endpoint, controller, or hardware interface.

No existing perception, memory, cognition, Safety, Skill Manager, Runtime
Bridge, simulation-control, learning, approval, showcase, or ROS package
depends back on this milestone. Independent Safety remains authoritative and
continues to defer physical movement.

## Authoritative manipulator group

Version 1 accepts exactly one group:

| Property | Exact value |
| --- | --- |
| Group | `left_arm` |
| Planning frame | `base_link` |
| Chain base | `left_shoulder_mount_link` |
| Chain tip | `left_hand_link` |

The ordered chain is derived from the expanded authoritative Xacro/URDF:

| Joint | Kind | Lower | Upper |
| --- | --- | ---: | ---: |
| `left_shoulder_yaw_joint` | revolute | -1.2 | 1.2 |
| `left_shoulder_pitch_joint` | revolute | -1.8 | 1.8 |
| `left_upper_arm_to_elbow_joint` | fixed | — | — |
| `left_elbow_flex_joint` | revolute | 0.0 | 2.2 |
| `left_wrist_yaw_joint` | revolute | -1.5 | 1.5 |
| `left_wrist_to_hand_joint` | fixed | — | — |

Fixed joints can never appear in planning positions. Right-arm, unknown,
duplicate, missing, reordered, integer-coerced, non-finite, and out-of-limit
positions fail closed with typed errors. The catalog also rejects a changed
ordered chain or changed reviewed limits.

## Immutable identity and evidence chain

Every public artifact is frozen, slot-backed, resource-bounded, canonically
serializable, and content-addressed. The chain binds:

```text
expanded-description fingerprint
→ robot-model ID/fingerprint
→ joint-catalog ID/fingerprint
→ group ID/fingerprint
→ start + goal identities
→ scene ID/fingerprint
→ planner configuration identity
→ request ID/fingerprint
→ waypoint state identities + collision evidence
→ plan-evidence ID/fingerprint
→ decision ID/fingerprint
```

Construction and canonical reconstruction revalidate every nested object and
every ID/fingerprint pair. ID-only, fingerprint-only, valid-but-unrelated,
nested, endpoint, waypoint, scene, planner-seed, and recomputed-outer identity
substitutions fail closed. Canonical parsing rejects duplicate keys,
noncanonical JSON, non-finite constants, unknown/missing fields, unknown
schemas/versions/enums, resource excess, and malformed nesting.

## Collision-scene boundary

Version 1 supports at most 16 collision objects. Each is a fixed box with:

- a bounded identifier;
- the exact `base_link` frame;
- finite position within the reviewed 10 m coordinate bound;
- identity orientation only; and
- three positive dimensions no greater than 5 m.

Objects are canonicalized by identifier and duplicates are rejected. There are
no meshes, octomaps, attached bodies, dynamic obstacles, transforms, latest
frame lookup, inferred geometry, scene persistence, or background updates.

Plan evidence must state that both self-collision and environment-collision
checks occurred, bind the exact complete requested object-ID set, retain the
deterministic planner seed, and use exact request-bound waypoints. Collision-
free evidence needs exact start/end points and cannot name a collision. A
rejection cannot carry a usable trajectory.

## Deterministic planner boundary

The pure helper uses planner identity
`ayyo.bounded-linear-joint-space.v1`, a maximum per-joint interpolation step of
0.05 rad, a maximum of 129 waypoints, and deterministic seed 0. It produces
candidate samples only. Samples acquire no plan status until an external
collision checker returns separately supplied evidence bound to the exact
request.

This simple interpolation is deliberately not a general motion planner,
optimal planner, Cartesian planner, IK solver, grasp planner, or dynamics
validator.

## MoveIt 2 headless proof

The C++ proof constructs a MoveIt RobotModel and PlanningScene directly from
the expanded Ayyo URDF and reviewed SRDF. The SRDF defines only `left_arm` and
excludes a bounded set of mechanically adjacent link pairs. It verifies:

- MoveIt's group exposes exactly the four reviewed movable joints in order;
- MoveIt's position bounds exactly match the authoritative URDF;
- the reviewed start and goal are in bounds and self/environment collision-free;
- all 21 deterministic path samples are in bounds and collision-free; and
- a fixed 0.12 m box centered at the goal hand is accepted into the scene and
  produces a collision report.

The proof links MoveIt core only. It does not depend on
`moveit_ros_planning_interface`, `moveit_ros_move_group`, controller manager,
trajectory messages, `rclcpp`, or any hardware/control package.

## Controller and Safety invariants

The milestone does not modify the authoritative robot Xacro, ros2_control
description, controller configuration, Safety Kernel, Skill Manager, Runtime
Bridge, or simulation-control implementation. All left-arm
`command_position` declarations remain `false`. The single forward position
controller remains scoped to `neck_yaw_joint`.

Planning evidence does not pass through or around Safety. There is simply no
path from this package to execution.

## Software Showcase v1 consistency

The Stage-8 showcase is an explicitly closed, content-addressed v1 snapshot of
15 capabilities and 19 evidence references. This milestone does not silently
rewrite those reviewed identities or create a reverse dependency. A future
showcase catalog version may add Stage-9 evidence after separate review; the
existing v1 truthfully remains its fixed historical catalog.

## Explicit non-goals

This milestone does not provide:

- arm actuation, trajectory execution, deployment, or Runtime dispatch;
- a ROS service/action/topic endpoint or MoveGroup client;
- an arm controller or commandable arm ros2_control interface;
- grasp selection, inverse kinematics, Cartesian planning, time
  parameterization, dynamics, torque, contact, or balance behavior;
- live/dynamic collision objects, perception-to-scene projection, persistence,
  or background workers;
- learned/candidate model loading, inference, training, policy activation,
  automatic learning, promotion, or rollback;
- production authority, physical validation, hardware control, emergency stop,
  or physical-safety certification; or
- any bypass or replacement of the independent Safety Kernel.

## Validation

The focused transport-neutral suite covers exact URDF derivation, all joint
limits, malformed model input, canonical identities/round trips, cross-object
substitution, collision-scene bounds, decision semantics, resource attacks,
dependency direction, controller invariants, and absence of execution APIs.

The isolated ROS build compiles `ayyo_description` and
`ayyo_manipulation_planning` against ROS 2 Jazzy and MoveIt 2 2.12.4. Its
headless test runs the PlanningScene proof twice and requires byte-identical
stdout plus all expected collision/bounds evidence. Gazebo and hardware are not
started because the milestone has no related runtime or command path.
