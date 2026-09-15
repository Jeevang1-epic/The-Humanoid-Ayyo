# Simulated End-Effector and Grasp Interaction Foundation

## Scope

Stage 9D adds one explicit, simulation-only interaction proof downstream of the
complete Stage 9C execution result. It gives the existing `left_hand_link` a
fixed end-effector identity, introduces one reviewed dynamic box in Gazebo, and
proves a bounded sequence:

```text
detached precondition
→ exact hand/object alignment
→ fresh Gazebo contact for the exact collision pair
→ contact-gated fixed constraint
→ attached-body MoveIt sample checks
→ the unchanged Stage 9C trajectory and controller execution
→ fresh relative-pose hold evidence
→ explicit constraint removal
→ fresh non-rigid post-release evidence
→ whole-body stability
```

This is not grasp planning, finger control, force control, tactile sensing,
general object manipulation, autonomous behavior, physical validation, or a
production Runtime/Skill implementation.

## Dependency and authority boundary

The transport-neutral distribution is
`ayyo-manipulation-grasp-interaction==0.1.0`. Its only direct project dependency
is the exact released Stage 9C distribution,
`ayyo-manipulation-simulation-execution==0.1.0`. Every positive Stage 9D request
and result recursively retains and verifies the complete Stage 9C request and
result rather than trusting identifiers alone.

The ROS package `ayyo_manipulation_grasp_interaction` imports the reviewed
Stage 9C adapter module. It reuses the existing request construction, dense
collision report, simulated-state observer, controller check, exact action-goal
mapping, one-goal execution, final-state correlation, and whole-body stability
evaluation. Stage 9D does not copy or replace the Stage 9C path, joint order,
timing, controller, endpoint, execution-success rules, or support fixture.

Every positive Stage 9D result states:

- `development_simulation_only`
- `not_physically_validated`
- `no_hardware_authority`
- `no_production_runtime_authority`

No lower cognition, Safety, Skill, Runtime, Stage 9A, Stage 9B, or transport
package depends back on Stage 9D.

## Fixed end-effector contract

The only allowed robot is `ayyo`. The only end-effector link and frame are
`left_hand_link`, and the exact semantic Gazebo entity is
`ayyo::left_hand_link`. Gazebo preserves that semantic frame by applying the
reviewed fixed `left_wrist_link` to `left_hand_link` transform to the physical
`left_wrist_link`; the exact contact collision is therefore the corresponding
fixed-joint-lumped collision,
`ayyo::left_wrist_link::left_wrist_link_fixed_joint_lump__left_hand_link_collision_1`.
The standard bridge spells the same semantic entity `ayyo/left_hand_link` on
the paired ROS pose topic; the adapter accepts only that fixed spelling and
maps it back to the canonical entity ID. The versioned interaction mode is
`contact_gated_fixed_constraint`, implemented by fixture
`ayyo.stage9d.contact-gated-fixed-constraint.v1` version `1.0.0`.

The fixture is a deliberately narrow simulation mechanism, not a hand model.
It accepts no SDF-selected robot, link, object, topic, or mode. It starts with
no hand/object constraint. An attach request is consumed once and succeeds only
when the exact robot link and object link resolve uniquely, a bounded contact
message for the exact collision pair was observed within 250 ms of simulation
time, and the relative pose is within 0.012 m and 0.10 rad of the reviewed
alignment. Because the reviewed target begins under the terminal hand surface,
the fixture applies one fixed open-loop 0.55 N world-up staging preload while
the grasp constraint is detached. This keeps the gravity-enabled dynamic body
in real contact without teleporting it. The preload is permanently removed on
the first accepted attachment, before collision preflight or Stage 9C motion.
It then creates one Gazebo `DetachableJoint` of type `fixed` between those exact
links. A detach request removes that joint, and the preload is not restored, so
fresh non-rigid release motion remains observable. The state publisher reports
only `attached` or `detached`.

This is a simulation interaction fixture. The fixed preload is neither measured
force evidence nor feedback force control. The mechanism is not a gripper
controller, force-closure model, friction-margin claim, or physical grasp
mechanism.

## Reviewed object contract

Exactly one allowed grasp target exists:

| Field | Fixed value |
| --- | --- |
| Object identity | `ayyo.stage9d.reviewed-grasp-object.v1` |
| Gazebo model/link | `stage9d_grasp_object` / `stage9d_grasp_object_link` |
| Collision | `stage9d_grasp_object_collision` |
| Primitive | box, `0.03 × 0.03 × 0.02` m |
| Mass | `0.05` kg |
| Inertia diagonal | `5.416666666666667e-6`, `5.416666666666667e-6`, `7.5e-6` kg·m² |
| Initial world pose | position `(-0.07774664053275518, 0.19, 0.5757939902418903)`, pitch `0.2` rad |
| Reviewed hand-relative pose | position `(0.02, 0, -0.17)`, identity rotation |
| Dynamics | dynamic, collision enabled, gravity enabled |
| Evidence | 100 Hz contact plus a bounded 20 Hz exact Gazebo world-pose pair |

The object is spawned with renaming disabled. Its model, link, collision,
geometry, pose, mass, inertia, dynamics flags, provenance, and allowed target
identity are all part of the immutable content-addressed contract. Missing,
duplicated, substituted, renamed, or malformed targets fail closed.

## Contact, attachment, and hold evidence

Contact comes from Gazebo's contact sensor and is bridged as
`ros_gz_interfaces/msg/Contacts`; it is not inferred from proximity or a
scripted timestamp. The proof retains the normalized exact collision pair,
contact count, optional bounded maximum depth, observation time, and monotonic
sequence. Empty, oversized, stale, replayed, malformed, or wrong-participant
contact is rejected.

Before attachment, fresh world-frame hand and object poses plus fixture state
must prove the exact object is present once, aligned, and detached. The adapter
publishes one attach command only after that precondition and fresh contact.
The resulting grasp evidence binds the pregrasp, contact, attached fixture
state, request identity, and run session.

Holding is proved after the unchanged Stage 9C motion. The exact object must
remain present and the fixture must remain attached. Fresh final hand/object
poses must show no more than 0.005 m relative translation change or 0.05 rad
relative rotation change, and world displacement is bounded to reject a
teleport. The embedded Stage 9C result must itself be a recursively valid
completed result with a stable whole-body observation and an active
post-result controller.

## Collision policy during the grasp interval

The Stage 9D MoveIt preflight attaches only the reviewed box to
`left_hand_link`. Its only touch link is `left_hand_link`; the global allowed-
collision matrix is unchanged. The proof checks joint bounds, self collision,
environment collision, and attached-body collision at every one of the exact
66 dense Stage 9C samples. It is bound to the exact Stage 9D request and grasp
evidence fingerprints.

The object-specific touch allowance exists only while the object is attached
for this grasp interval. No robot-wide object allowance, global ACM relaxation,
or wrong-object reuse is accepted. The artifact explicitly states that bounded
samples are neither continuous collision certification nor physical collision
certification.

## Release and post-release evidence

Release is a separate explicit command after a successfully established hold.
The fixture must produce a newer detached observation, and both hand and exact
object must produce newer fresh poses. Relative hand/object translation must
change by at least 0.005 m, demonstrating that the object is no longer rigidly
carried. A fresh post-release 18-joint and base observation is evaluated by the
unchanged Stage 9C stability policy with a fresh active controller state.

Release before hold, continued attachment, stale evidence, disappearance,
substitution, insufficient relative change, or whole-body instability rejects
the result.

## Evidence and integrity model

Contracts and evidence are frozen, slotted dataclasses with closed enums,
bounded text, bounded collections, finite normalized numeric data, schema IDs,
semantic SHA-256 fingerprints, and content-derived IDs. Canonical JSON uses
sorted keys and compact separators, rejects duplicate keys and non-finite or
negative-zero values, limits decoded structures to 500,000 nodes, and limits a
canonical artifact to 16 MiB.

Positive reconstruction recursively verifies:

- the full Stage 9A → 9B → 9C request and result lineage;
- robot, end-effector, object, fixture, contact, pose, and run identities;
- strictly increasing observation sequences and timestamps;
- the request-bound Stage 9D MoveIt input and all dense samples;
- attached hold continuity and exact object identity;
- explicit detached release and post-release stability; and
- every derived ID and fingerprint.

Cross-run composition, recomputed outer identities around invalid inner
evidence, payload substitution, wrong-object proof reuse, non-finite values,
oversized artifacts, and malformed canonical input fail closed with typed
`GraspInteractionFailureCode` or `GraspInteractionSerializationError` errors.

## ROS and Gazebo activation

Ordinary simulation remains unchanged and Stage 9D contact support defaults to
false. The dedicated launch enables the already reviewed Stage 9C control,
base-support, and localization flags; selects the contact-system world; spawns
the fixed object at its explicit reviewed pose; and creates exactly five
directional bridges:

- Gazebo → ROS: object contact, one exact two-entity world-pose message, fixture state
- ROS → Gazebo: attach, detach

Launching the profile sends no arm goal and does not attach the object. The only
documented interaction invocation is the owned-process smoke:

```bash
scripts/smoke_manipulation_grasp_interaction.sh
```

The smoke checks the exact active controllers and action, typed Stage 9D topics,
object evidence, real contact, initial detached state, the complete canonical
result, attached-body collision policy, Stage 9C motion and stability, hold and
release evidence, and bounded teardown. It must pass twice consecutively.

Run the transport-neutral suite with the complete upstream source path:

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:manipulation_planning/src:manipulation_trajectory/src:manipulation_simulation_execution/src:manipulation_grasp_interaction/src${PYTHONPATH:+:$PYTHONPATH} \
  python3 -m pytest -q manipulation_grasp_interaction/tests
```

The ROS package tests include source-surface isolation, fixed launch/bridge/SDF
contracts, an actual C++ MoveIt proof run, deterministic repeated output, and a
wrong-object rejection probe.

## Actual validation results

Final validation on 2026-09-15 used ROS 2 Jazzy and Gazebo Harmonic:

- changed Python modules compiled, the owned smoke passed `bash -n`, and all
  affected ROS linters passed;
- Stage 9D transport-neutral tests: 57 passed in 180.58 s — 23 model, 25
  serialization/adversarial, 5 proof, and 4 package-boundary tests;
- downstream boundary regressions: Stage 9A 11 passed, Stage 9B 10 passed, and
  Stage 9C 5 passed;
- the isolated affected Stage 9C ROS package built successfully and its 10
  CTest targets reported 21 test cases, 0 errors, 0 failures, and 1 declared
  skip;
- final fresh disposable ROS build: all 8 packages through
  `ayyo_manipulation_grasp_interaction` built successfully;
- final focused colcon run over `ayyo_simulation`,
  `ayyo_manipulation_simulation_execution`, and
  `ayyo_manipulation_grasp_interaction`: 107 test cases, 0 errors, 0 failures,
  and 3 declared skips. This includes 28 simulation contract tests, 8 Stage 9D
  adapter tests, and 2 Stage 9D MoveIt tests;
- the owned Stage 9D headless smoke passed twice consecutively from the final
  fresh install, and each run proved an empty owned-process set after bounded
  shutdown; and
- `git diff --check` passed.

## Remaining limits

Stage 9 remains incomplete. This milestone does not add multi-object scenes,
object discovery, perception-derived object identity, grasp pose generation,
approach planning, fingers, grasp quality, force/torque limits, force closure,
tactile feedback, compliant control, continuous collision checking, dynamics
validation, general pick-and-place, production Runtime/Skill authority,
independent physical motion/contact Safety policy, hardware drivers, emergency
stop integration, or physical manipulator validation.
