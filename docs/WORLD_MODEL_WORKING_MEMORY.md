# Embodied World Model and Working Memory Foundation v1

## Status and purpose

Ayyo now has a transport-neutral v1 representation of current embodied and
environment state plus deterministic bounded retention for temporary evidence.
This fills the architectural space between the future Perception Trust Boundary
and durable Memory Validation.

The implementation answers a deliberately narrow question: from reviewed,
bounded evidence, what does Ayyo currently believe about its body and observed
environment, how fresh is that belief, and which recent evidence is still
available for immediate reasoning?

It does not implement perception. Environment state starts empty and remains
empty unless a caller supplies an actual typed observation. The live ROS adapter
currently normalizes only standard `/joint_states`; no camera, microphone, IMU,
TF perception, person tracking, or object detector is fabricated.

Gazebo is a replaceable development body backend. It is not the final project
goal. The final objective is the physical Ayyo humanoid, and the observation
contract is designed so encoder-backed physical `ros2_control` joint state can
replace simulated `gz_ros2_control` joint state without changing World Model
semantics.

## Architecture position

```text
future physical sensors / current simulation feedback
        ↓
fixed typed ROS observation adapter
        ↓ normalized evidence
World Model immutable contracts and projection
        ↓
bounded Working Memory current state + recent evidence
        ↓ explicit future consolidation decision
Memory Validation CandidateEvidence
        ↓ evaluate / explicitly apply
Memory OS durable evidence
        ↓
Personal Context Twin + Executive Cognition
```

The standalone `ayyo-world-model` package has no runtime dependency. The
standalone `ayyo-working-memory` package depends only on the public World Model
API. Neither package imports ROS, Gazebo, Memory OS, Personal Context Twin,
Executive Cognition, networking, persistence, subprocess, or model providers.
ROS ownership is isolated in `ros2_ws/src/ayyo_world_model`.

## Trust boundary

Perception and telemetry are evidence, not authority. Receiving a ROS message
does not prove truth, safety, authorization, or physical success. Before an
observation can become current state, Working Memory requires:

- the canonical `ayyo.robot.v1` identity;
- an exact reviewed provenance profile;
- a compatible explicit source clock;
- a deterministic content-derived identity;
- bounded finite values and collections;
- source time within freshness/retention policy;
- newer temporal ordering for each affected state key; and
- known non-fixed joints within authoritative URDF position, velocity, and
  effort bounds.

The first ROS adapter does not inspect controller commands. It learns movement
only from `/joint_states` feedback. A successful request and observed reality
are intentionally different evidence:

```text
command request ≠ observed body state
```

## Typed observation model

`RobotStateObservation` carries one bounded, immutable body evidence batch:

- canonical robot identity;
- one to 128 unique, canonically sorted `JointObservation` values and/or an
  optional `Pose3D`;
- finite joint position and optional velocity/effort values;
- source observation timestamp in nanoseconds;
- exact `ObservationProvenance`;
- finite confidence from zero through one; and
- a content-derived observation ID and typed SHA-256 fingerprint.

`EnvironmentEntityObservation` carries the observing robot identity, one typed
and bounded entity identity, an optional bounded spatial pose, bounded
JSON-compatible properties, confidence, source time, provenance, and a
content-derived evidence identity. It must contain a pose and/or non-empty
properties, so creating an entity requires actual evidence.

`Pose3D` names a parent and child frame, requires distinct canonical frames,
finite XYZ values, and a normalized XYZW quaternion. The live joint-state
adapter supplies no base pose because `/joint_states` does not provide one.
Future TF or localization ingestion must use a separate reviewed adapter and the
same typed core boundary.

## Provenance

Every meaningful observation retains source kind, canonical source identity,
clock domain, transport kind, and typed source-interface identity. Source kind
and clock domain have fixed valid pairs. Simulation evidence uses
`ROS_SIMULATION_TIME`; physical sensor evidence uses `ROS_SYSTEM_TIME`; recorded
and test evidence use their own explicit clocks. Recorded evidence must also use
the recorded transport.

The ROS boundary exposes two reviewed profiles:

| Profile | Source kind | Clock | Source identity |
| --- | --- | --- | --- |
| `simulation_ros2_control_v1` | simulation | ROS simulation time | `ros.joint-states.simulation.ros2-control.v1` |
| `physical_ros2_control_v1` | physical sensor | ROS system time | `ros.joint-states.physical.ros2-control.v1` |

The adapter rejects a simulation profile with wall/system ROS time and a
physical profile with simulation time. Profile selection never changes the
fixed `/joint_states` subscription. A simulation observation cannot be rebuilt
as physical evidence without changing its fingerprint, and Working Memory
rejects provenance outside its configured exact allowlist.

## Authoritative body bounds

`RobotJointCatalog` parses the authoritative expanded URDF without depending on
ROS or Gazebo. The immutable catalog retains fixed/movable joint type and finite
position, velocity, and effort limits, plus a canonical fingerprint. Unknown
and fixed joint observations are rejected.

A reviewed `1e-8` numerical tolerance permits encoder/simulation floating-point
noise at an exact limit. This was needed because Gazebo produced knee feedback
about `2.4e-15` radians below an authoritative zero lower limit. A value `1e-6`
past the same limit remains rejected. The tolerance is evidence-normalization
policy, not a command or physical-safety limit change; Safety Kernel and
ros2_control limits remain unchanged.

## World Model projection

`WorldModelProjector` is a pure transformation over the current evidence chosen
by Working Memory. It creates an immutable `WorldSnapshot` containing:

- `RobotBodyState` with canonical identity, all known movable joint names,
  observed joint states, optional base pose, and explicit unavailable/partial/
  available coverage;
- zero or more canonically ordered `WorldEntity` records; and
- a typed canonical snapshot version and derived snapshot ID.

Each observed joint retains its source observation identity, fingerprint,
confidence, timestamp, provenance, optional velocity/effort, and fresh/stale
state. Missing joints remain missing; no zero values are invented. An empty
snapshot knows the canonical robot and reviewed joint catalog but reports body
state as unavailable.

Snapshot identity covers relevant projected state, evidence identities,
provenance, and discrete freshness. It excludes exact query/capture time, so two
queries during the same freshness state produce the same semantic identity.
New evidence or a fresh-to-stale transition changes the identity. Dictionary
insertion order, process ID, machine path, user name, randomness, temporary
paths, and wall-clock noise do not enter fingerprints.

Maximum valid ingress values use a separate smaller bound from internal
aggregate fingerprint documents. This allows all configured bounded entities
to be represented without relaxing public observation limits.

## Working Memory

`WorkingMemory` owns temporary current state and a compact recent-evidence
window. It has no database, filesystem writes, timer, worker thread, polling
loop, or autonomous refresh. Time is supplied explicitly to every ingest/query
operation so deterministic tests and ROS adapters control the correct clock.

Current robot state is keyed per joint and optional body pose. Partial newer
messages update only the joints they contain and do not clear other unexpired
state. A same-key message with an older timestamp is rejected. Different
evidence for the same key and exact timestamp is rejected as a temporal
conflict. Exact duplicates are no-ops and do not extend TTL or recent history.

Environment state is keyed by canonical identity. Newer observations replace
older current state. Capacity overflow deterministically evicts by:

```text
oldest source timestamp
→ canonical observation identity
→ canonical entity identity
```

Recent evidence is sorted by source timestamp and canonical observation ID and
retains only the newest configured capacity. Its envelope keeps monotonic
receipt time separately from source time. Receipt time never enters semantic
observation identity.

## Time and freshness

The time model separates source timestamp, the configured ROS source clock,
monotonic receipt time, and monotonic timeout time. The default ROS policy is:

- fresh through 500 ms of source-clock age;
- retained for 2 seconds of source-clock age;
- up to 50 ms permitted future skew; and
- future timestamps beyond that skew rejected.

At exactly the freshness bound, state is fresh. It becomes stale after that
bound and disappears after TTL. A duplicate cannot refresh either interval.
Source-clock regression raises a typed error. The ROS adapter responds by
discarding all temporary state and starting a new evidence epoch; it never
compares simulation time to wall time or retains future state across a reset.
Monotonic receipt time is also required not to regress within one Working Memory
epoch; impossible ordering is rejected rather than hidden.

Publisher disappearance requires no timer: the next read evaluates source time,
expires old evidence, and reports not ready. Adapter restart begins empty.
Deactivate and cleanup stop observation and remove/reset temporary state.

## Resource bounds

Defaults and hard maxima are explicit:

| Resource | Default | Hard maximum |
| --- | ---: | ---: |
| Recent evidence | 256 observations | 4,096 |
| Current environment entities | 128 | 256 |
| Retention TTL | 2 seconds | 300 seconds |
| One observation joint count | 128 | 128 |
| JSON depth | 16 | 16 |
| JSON nodes per public value | 2,048 | 2,048 |
| Items per public collection | 256 | 256 |
| One string | 4,096 characters | 4,096 |
| Aggregate public text | 65,536 characters | 65,536 |
| Integer width | 1,024 bits | 1,024 bits |

Current robot-joint entries are additionally bounded by the immutable joint
catalog (18 movable joints presently). Counters use constant storage. No
all-time observation-ID set is retained. At query time, shared multi-joint batch
evidence is reconstructed once and referenced by each current joint, avoiding
repeated whole-batch hashing/copies.

Tests run 5,000 rapid updates and assert current entities, recent evidence,
unique observations, and reference slots stay within configured caps. A
`tracemalloc` test measures 2,000 compact updates and enforces current traced
memory below 2 MB and peak below 8 MB. These are development-machine bounds,
not a compatibility claim for a specific Raspberry Pi or Jetson model.

An explicit review run using the current authoritative 18-joint catalog and
5,000 full joint batches at a simulated 100 Hz retained 201 unique batches
(the 2-second TTL boundary), 18 current-joint references, 219 total observation
references, 745,212 current traced bytes, and a 756,679-byte traced peak. This
measurement excludes the Python interpreter, ROS middleware, and Gazebo.

## Read-only query surfaces

The core exposes immutable typed `current_snapshot`, `get_robot_state`,
`get_entity`, `query_freshness`, `recent_evidence`, and bounded `stats`
operations. There is no expression engine, arbitrary filter, raw database
query, ROS topic selection, `eval`, `exec`, or mutable world-state result.

The ROS package adds one fixed read-only service:

```text
/ayyo/world_model/get_robot_body_state
ayyo_interfaces/srv/GetRobotBodyState
```

It reports ready/not-ready, canonical robot/snapshot identities, source profile,
expected and observed joints, position and optional velocity/effort, per-joint
timestamps, confidence, freshness, evidence IDs, and bounded retention counts.
A query for another robot identity fails closed.

## ROS lifecycle and restart behavior

`AyyoWorldModelNode` is a managed `LifecycleNode` and self-drives deterministic
configure/activate transitions through the reviewed executable.

- Configure selects one reviewed profile, verifies ROS clock compatibility,
  parses `robot_description`, creates Working Memory, and creates the query.
- Activate creates the sole `/joint_states` subscription.
- Deactivate destroys the subscription and makes queries not ready.
- Cleanup/shutdown destroy interfaces and discard temporary state.
- Error routes through cleanup.

There are no background threads or timers. Startup, query-client waits, and
process shutdown are bounded. Invalid high-rate messages use constant-space
counters and rate-reduced warnings.

## Simulation-to-hardware migration

The verified development path is:

```text
World Model ← Working Memory ← fixed /joint_states adapter (simulation profile)
← joint_state_broadcaster ← ros2_control ← gz_ros2_control ← Gazebo Harmonic
```

The intended physical path is:

```text
World Model ← Working Memory ← fixed /joint_states adapter (physical profile)
← joint_state_broadcaster ← ros2_control ← future Ayyo hardware interface
← physical drivers/communications ← encoders and sensors
```

Only the reviewed provenance profile and lower hardware implementation change.
World observations, retention, projection, query contracts, and higher layers do
not import or branch on Gazebo. No fake Raspberry Pi, Jetson, Arduino, STM32,
CAN, EtherCAT, motor driver, or hardware interface is introduced.

## Temporary versus durable memory

Working Memory is not Memory OS. It never imports Memory OS or Memory
Validation, writes a database, or automatically promotes an observation.
`recent_evidence()` is the explicit read boundary for a future consolidation
component. That component must make a meaningful policy decision, map selected
evidence into existing Memory Validation `CandidateEvidence`, and call:

```text
MemoryValidationService.evaluate(candidate)
→ explicit review/application decision
→ MemoryValidationService.apply(decision)
→ Memory OS
```

This milestone does not invent that mapping because no reviewed policy decides
which joint/environment changes are autobiographically meaningful. Direct ROS
telemetry cannot mutate durable memory, and future consolidation cannot bypass
Memory Validation.

## PCT, Executive, and learning relationships

Personal Context Twin remains durable owner context: “What does Ayyo know about
its owner?” World Model remains current embodied/environment state: “What has
Ayyo recently observed about itself and its surroundings?” They are not merged,
and PCT/Executive code is unchanged. A future reasoning integration may consume
both public snapshots while preserving owner isolation, conflicts, freshness,
provenance, and Safety review.

Working Memory prepares the future loop:

```text
observe → reason → act → observe outcome → select candidate
→ evaluate → promote or reject → consolidate
```

It does not implement unrestricted self-modification or automatic promotion.
Learned behavior can never mutate the Immutable Safety Kernel, physical joint
limits, emergency-stop behavior, hardware safety limits, or authority policy.
Learned skills/policies must be versioned, evaluated, explicitly promoted, and
rollback-capable.

## Automated validation

```bash
PYTHONPATH=world_model/src \
python3 -m unittest discover -s world_model/tests -v

PYTHONPATH=world_model/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v

./scripts/build_workspace.sh
./scripts/test_workspace.sh
./scripts/smoke_world_model.sh
```

The smoke starts controlled headless simulation, requires the lifecycle/query
surface active, verifies an 18-joint fresh simulation snapshot, requests the
existing bounded `0.1` rad neck motion, and proves a new snapshot from later
`/joint_states` feedback. The World Model adapter has no control-request import.
Shutdown must be clean.

## Current limitations

- Only ROS joint-state ingestion is live.
- Base pose, TF, environment entities, health/diagnostics, IMU, force/torque,
  touch, camera, depth, audio, navigation, manipulation, and human tracking have
  typed or architectural space but no live adapter.
- Confidence is supplied evidence; v1 has no sensor fusion, trust scoring,
  covariance, probabilistic estimation, or conflict resolution.
- Environment entities expire by TTL; there is no explicit disappearance or
  tombstone observation yet.
- Working Memory is in-process/non-durable; node restart loses temporary state.
- The ROS query exposes body state only.
- No automatic Memory Validation candidate selection or learning consolidation
  exists.
- No edge-hardware benchmark or Raspberry Pi/Jetson compatibility claim exists.
- Physical sensors, drivers, authorization, and physical safety remain future.

## Exact manual validation

After a clean build, launch the reviewed graphical controlled path:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=122
export GZ_PARTITION=ayyo_world_model_manual_122
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false enable_control:=true enable_development_control:=true \
  enable_world_model:=true
```

In another identically configured terminal:

```bash
ros2 lifecycle get /ayyo_world_model
ros2 run ayyo_world_model body_state_query.py
ros2 run ayyo_simulation_control development_command.py --position 0.1
ros2 run ayyo_world_model body_state_query.py
```

Confirm lifecycle is active, the first query reports 18 fresh joints with
simulation provenance, the head visibly turns, and the later query reports
`neck_yaw_joint` within `0.01` rad of `0.1` with later evidence and changed
snapshot IDs. Press `Ctrl-C` and verify the isolated graph/processes terminate.
