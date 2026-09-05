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

The separate
[Perception Trust Boundary](PERCEPTION_TRUST_PROPRIOCEPTION.md) now admits
standard joint-state and body-IMU evidence before Working Memory. Environment
state still starts empty and remains empty unless a caller supplies actual typed
evidence. The reviewed localization and diagnostics adapters now supply exact
pose and explicit health evidence through the same path; see
[BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md](BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md).
The [Visual Camera Foundation](VISUAL_CAMERA_FOUNDATION.md) now admits compact
calibrated RGB-frame metadata from paired standard `Image`/`CameraInfo`
messages. Pixels, microphone data, people, objects, scene meaning, and missing
pose/health are not fabricated or retained in semantic state.

Gazebo is a replaceable development body backend. It is not the final project
goal. The final objective is the physical Ayyo humanoid, and the observation
contract is designed so encoder-backed physical `ros2_control` joint state can
replace simulated `gz_ros2_control` joint state without changing World Model
semantics.

## Architecture position

```text
future physical sensors / current simulation feedback
        ↓
fixed standard ROS decoding adapter; raw image payload ends here
        ↓ normalized immutable evidence
Perception Trust Boundary
        ↓ admitted evidence
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
standalone `ayyo-perception` package depends only on its public contracts, and
the standalone `ayyo-working-memory` package depends only on the public World
Model API. None imports ROS, Gazebo, Memory OS, Personal Context Twin,
Executive Cognition, networking, persistence, subprocess, or model providers.
ROS ownership is isolated in `ros2_ws/src/ayyo_world_model`.

## Trust boundary

Perception and telemetry are evidence, not authority. Receiving a ROS message
does not prove truth, safety, authorization, or physical success. The dedicated
trust boundary first validates exact source/sensor/frame/provenance, immutable
identity, numeric/covariance structure, and time ordering. Before an admitted
observation can become current state, Working Memory additionally requires:

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
The separate reviewed localization adapter supplies only exact timestamped
`odom` to `base_link` evidence through the same typed core boundary.

`ImuObservation` independently preserves supplied orientation, angular
velocity, linear acceleration, optional 3x3 covariance, optional quality,
exact `imu_link` sensor identity, provenance, availability, time, and canonical
identity. Missing estimates and unknown covariance remain `None`.

`BodyPoseObservation` adds an exact source/target-frame pose, optional 6x6
covariance, optional quality, provenance, and availability.
`SensorHealthObservation` provides bounded available/degraded/error/stale/
unavailable evidence; diagnostic text is data only and grants no authority.
Both now have narrow live adapters without changing these transport-neutral
contracts.

`CameraCalibration` validates exact image dimensions, bounded finite `D/K/R/P`
parameters, distortion model, binning, and ROI before deriving a deterministic
identity. `VisualFrameObservation` retains only robot/sensor identity, optical
frame, dimensions, `rgb8` encoding, step, byte count, calibration identity,
source timestamp, availability, provenance, and canonical identity. It has no
pixel field and cannot represent detected entities or scene knowledge.

`VisualInterpretationObservation` now represents a bounded semantic result from
one exact admitted `VisualFrameObservation`. It retains the source frame ID and
fingerprint, unchanged acquisition time, a separate result time, exact RGB
camera/optical frame, source provenance, exact producer/model/adapter identity,
and at most 32 typed normalized 2D detections with optional finite confidence.
The focused contract is documented in
[VISUAL_PERCEPTION_PROCESSING.md](VISUAL_PERCEPTION_PROCESSING.md).
Evaluated interpretations may additionally retain one compact immutable model/
dataset/policy/report reference. The evaluator report, manifests, model bytes,
dataset bytes, and pixels remain outside Working Memory and snapshots; see
[VISUAL_PRODUCER_EVALUATION.md](VISUAL_PRODUCER_EVALUATION.md).

`SemanticEvidenceObservation` is the transport-neutral projection of one
non-empty anonymous subset from one exact admitted visual interpretation. Each
item preserves its Perception semantic observation ID, source detection ID,
person/object kind, normalized region, object category where applicable, and
optional confidence. The enclosing observation preserves exact source frame
and interpretation identities/fingerprints, RGB camera/optical frame,
producer, compact evaluated-reference digest, source/result time, provenance,
and availability. Its deterministic identity rechecks the source
Person/Object observation content. It contains no pixels, entity ID, tracking
ID, command, or authority field and does not assert that omitted detections are
absent.

## Provenance

Every meaningful observation retains source kind, canonical source identity,
clock domain, transport kind, and typed source-interface identity. Source kind
and clock domain have fixed valid pairs. Simulation evidence uses
`ROS_SIMULATION_TIME`; physical sensor evidence uses `ROS_SYSTEM_TIME`; recorded
and test evidence use their own explicit clocks. Recorded evidence must also use
the recorded transport.

The ROS boundary exposes two reviewed embodiment profiles. Each pins distinct
joint, IMU, body-pose, and head-camera provenance:

| Profile | Source kind | Clock | Source identity |
| --- | --- | --- | --- |
| `simulation_ros2_control_v1` | simulation | ROS simulation time | `ros.joint-states.simulation.ros2-control.v1` |
| `physical_ros2_control_v1` | physical sensor | ROS system time | `ros.joint-states.physical.ros2-control.v1` |

The corresponding IMU sources are
`ros.imu.simulation.gz-harmonic.v1` and
`ros.imu.physical.standard-driver.v1`. Only the simulation profile has been
exercised; the physical profile is a reviewed seam, not a hardware claim.
The corresponding RGB camera sources are
`ros.camera.head.simulation.gz-harmonic.v1` and
the unexercised seam `ros.camera.head.physical.standard-driver.v1`, both using
the transport-neutral `sensor-msgs.image-camera-info.v1` interface identity.
The seam is not sufficient to admit a physical frame. The separate
[Physical Head Camera, Calibration, and Diagnostics Foundation](PHYSICAL_HEAD_CAMERA_CALIBRATION_DIAGNOSTICS.md)
requires an explicit manifest, calibration, active session, and sealed
Perception authorization. Its only executable source is TEST-only.

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
  observed joint states, zero or more current IMU and compact visual states,
  optional base pose, per-sensor availability, and explicit
  unavailable/partial/available joint coverage;
- zero or more canonically ordered `WorldEntity` records;
- zero or more canonically ordered anonymous `ObservedSemanticEvidenceState`
  values, separate from persistent environment entities; and
- a typed canonical snapshot version and derived snapshot ID.

Each observed joint retains its source observation identity, fingerprint,
confidence, timestamp, provenance, optional velocity/effort, and fresh/stale
state. Missing joints remain missing; no zero values are invented. An empty
snapshot knows the canonical robot and reviewed joint catalog but reports body
state as unavailable.

Snapshot identity covers relevant projected state, evidence identities,
provenance, and discrete freshness. It excludes exact query/capture time, so two
queries during the same freshness state produce the same semantic identity.
New evidence, health change, fresh-to-stale transition, or TTL disappearance
changes the identity. Dictionary
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

Current robot state is keyed per joint, IMU sensor, visual sensor,
visual-camera/interpretation-producer pair, body-pose source, and sensor health
source. Partial newer
messages update only the joints they contain and do not clear other unexpired
state. A same-key message with an older timestamp is rejected. Different
evidence for the same key and exact timestamp is rejected as a temporal
conflict. Exact duplicates are no-ops and do not extend TTL or recent history.

Anonymous semantic state uses a conservative recent-evidence model because the
upstream Person/Object contract does not promise complete negative detection.
One immutable batch contains one or more admitted items from one exact
interpretation. Working Memory rechecks the retained source frame,
interpretation, producer/evaluation digest, detection category/label/region,
confidence, robot, camera, frame, time, and provenance. Newer batches do not
erase older unexpired batches merely because an item is omitted. Older arrivals
and same-result-time conflicts are rejected; exact duplicates do not refresh
TTL. Batches disappear at source-time TTL, reset, deterministic capacity
eviction, or earlier if their required retained frame/interpretation reference
is evicted. This represents “recent anonymous evidence,” never “the scene is
empty” or “the same person/object persists.”

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
marks retained evidence stale after freshness, and reports its known sensor as
unavailable after TTL. Adapter restart begins empty. Deactivate destroys both
fixed proprioceptive subscriptions as part of destroying all six observation
subscriptions; cleanup removes/reset temporary state and unmatched camera
message references.

## Resource bounds

Defaults and hard maxima are explicit:

| Resource | Default | Hard maximum |
| --- | ---: | ---: |
| Recent evidence | 256 observations | 4,096 |
| Current environment entities | 128 | 256 |
| Current anonymous semantic evidence batches | 64 | 64 |
| Retention TTL | 2 seconds | 300 seconds |
| One observation joint count | 128 | 128 |
| JSON depth | 16 | 16 |
| JSON nodes per public value | 2,048 | 2,048 |
| Items per public collection | 256 | 256 |
| One string | 4,096 characters | 4,096 |
| Aggregate public text | 65,536 characters | 65,536 |
| Integer width | 1,024 bits | 1,024 bits |

Current robot-joint entries are additionally bounded by the immutable joint
catalog (18 movable joints presently). IMU, visual, pose, and health current
entries are bounded by the immutable sensor catalog (four identities presently).
One semantic batch is capped at 32 unique detections, semantic current state at
64 batches, and source-order watermarks at the fixed 32-sensor by 16-producer
catalog product. The 2,000-update semantic regression retains at most the
configured current batches and recent references.
The camera adapter keeps at most one pending `Image` and one pending
`CameraInfo`, clearing both after an exact pair; pixels never enter trust,
Working Memory, World Model, fingerprints, or Memory OS. Counters use constant
storage. No
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

The proprioception review additionally admitted 5,000 full IMU samples at a
simulated 100 Hz through trust and Working Memory. It retained one trust key,
one current IMU, 201 recent/unique observations, and 202 references;
`tracemalloc` reported 545,739 current and 557,087 peak bytes. This has the same
development-machine-only qualification.

The localization/diagnostics regression runs 3,000 alternating pose and health
cycles with one current pose, one current health item, 32 recent observations,
at most 34 unique observations/references, current traced memory below 2 MB,
and peak below 8 MB.

The visual regression admitted 5,000 compact frames at a simulated 10 Hz. It
retained one trust key, one current visual observation, 21 recent/unique
observations, and 22 total references; `tracemalloc` reported 110,275 current
and 113,999 peak bytes. This excludes raw ROS/Gazebo buffers, middleware, the
interpreter, and is not an edge-hardware claim.

## Read-only query surfaces

The core exposes immutable typed `current_snapshot`, `get_robot_state`,
`get_entity`, `query_freshness`, `recent_evidence`, and bounded `stats`
operations. There is no expression engine, arbitrary filter, raw database
query, ROS topic selection, `eval`, `exec`, or mutable world-state result.

The ROS package adds two fixed read-only services:

```text
/ayyo/world_model/get_robot_body_state
ayyo_interfaces/srv/GetRobotBodyState

/ayyo/world_model/get_anonymous_semantic_state
ayyo_interfaces/srv/GetAnonymousSemanticState
```

It reports ready/not-ready, canonical robot/snapshot identities, source profile,
expected and observed joints, IMU values with explicit presence flags,
covariance/quality presence, exact pose frames/values/provenance, independent
explicit health presence/detail/provenance, compact visual dimensions/encoding/
step/byte-count/calibration identity/provenance, sensor summaries, timestamps,
freshness, evidence IDs/fingerprints, and bounded retention counts. No image
bytes are serialized by this service. A query for
another robot identity fails closed.

The dedicated semantic service serializes `WorldSnapshot.semantic_states` from
one snapshot operation into at most 64 `AnonymousSemanticState` messages with
at most 32 `AnonymousSemanticItem` values each. It preserves semantic evidence,
source frame/interpretation/detection, producer/evaluation, provenance, region,
object category, freshness, and availability. `has_confidence=false` carries
`None`; `has_confidence=true` with `confidence=0.0` remains a real zero. Person
items have no object category, and all transported IDs remain evidence
provenance rather than entity identities. Its fixed client has bounded waits
and prints canonical JSON. An empty result means no currently retained evidence,
not that the physical scene is empty. Querying never invokes Perception,
refreshes TTL, mutates Working Memory, creates entities, or writes durable state.

## ROS lifecycle and restart behavior

`AyyoWorldModelNode` is a managed `LifecycleNode` and self-drives deterministic
configure/activate transitions through the reviewed executable.

- Configure selects one reviewed profile, verifies ROS clock compatibility,
  parses `robot_description`, creates Working Memory, and creates both queries.
- Activate creates fixed `/joint_states`, `/ayyo/imu/data`,
  `/ayyo/localization/odometry`, `/diagnostics`,
  `/ayyo/camera/head/image_raw`, and `/ayyo/camera/head/camera_info`
  subscriptions plus one retention-bounded TF2 buffer.
- Deactivate destroys all subscriptions and the TF2 buffer and makes queries
  not ready.
- Cleanup/shutdown destroy interfaces and discard temporary state.
- Error routes through cleanup.

There are no background threads or timers. Startup, query-client waits, and
process shutdown are bounded. Invalid high-rate messages use constant-space
counters and rate-reduced warnings.

## Simulation-to-hardware migration

The verified development path is:

```text
World Model ← Working Memory ← Perception Trust Boundary
← fixed standard joint/IMU/camera adapter (simulation profile)
← ros2_control feedback + ros_gz sensor/image bridges ← Gazebo Harmonic
```

The intended physical path is:

```text
World Model ← Working Memory ← Perception Trust Boundary
← fixed standard joint/IMU/camera adapter (physical profile)
← joint_state_broadcaster + future standard IMU and camera drivers
← future Ayyo hardware interfaces, encoders, and sensors
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

PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v

PYTHONPATH=world_model/src:perception/src \
python3 -m unittest discover -s perception/tests -v

./scripts/build_workspace.sh
./scripts/test_workspace.sh
./scripts/smoke_world_model.sh
./scripts/smoke_perception.sh
./scripts/smoke_localization_diagnostics.sh
./scripts/smoke_visual_camera.sh
```

The smoke starts controlled headless simulation, requires the lifecycle/query
surface active, verifies an 18-joint fresh simulation snapshot, requests the
existing bounded `0.1` rad neck motion, and proves a new snapshot from later
`/joint_states` feedback. The World Model adapter has no control-request import.
Shutdown must be clean.

## Current limitations

- ROS joint-state, simulated body-IMU, exact-frame localization, and reviewed
  joint/IMU diagnostic ingestion are live; opt-in simulated RGB frame metadata
  and default-off TEST microphone metadata are live without retaining pixels or
  raw audio samples.
- Compact TEST/simulation depth metadata now has a live adapter, bounded state,
  and read-only query path. Environment entities, force/torque, touch, physical
  depth/audio hardware, navigation, manipulation, human tracking, RGB-D
  geometry and speech/audio interpretation have typed or architectural space
  but no live production adapter. Anonymous semantic visual evidence now has a
  transport-neutral bounded state path, but no production detector, tracking,
  complete-scene claim, or persistent identity/entity projection. Its live ROS
  transport is read-only and TEST-smoke-validated, not a production detector.
- Covariance and optional quality are preserved when supplied; v1 has no sensor
  fusion, calibration/bias estimation, trust scoring, probabilistic estimation,
  or cross-sensor conflict resolution.
- Expected proprioceptive sensors have explicit query-time disappearance;
  environment entities still expire by TTL without a tombstone observation.
- Working Memory is in-process/non-durable; node restart loses temporary state.
- The body query exposes joint, IMU, pose, sensor-summary, explicit health, and
  compact pixel-free RGB, interpretation, depth, RGB-D fusion, and sample-free
  audio state. The separate semantic query exposes only bounded current/recent
  anonymous semantic evidence already present in `WorldSnapshot`.
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
  enable_world_model:=true enable_camera:=true
```

In another identically configured terminal:

```bash
ros2 lifecycle get /ayyo_world_model
ros2 run ayyo_world_model body_state_query.py
ros2 run rqt_image_view rqt_image_view /ayyo/camera/head/image_raw
ros2 run ayyo_simulation_control development_command.py --position 0.1
ros2 run ayyo_world_model body_state_query.py
```

Confirm lifecycle is active, the first query reports 18 fresh joints with
simulation provenance, the head visibly turns, and the later query reports
`neck_yaw_joint` within `0.01` rad of `0.1` with later evidence and changed
snapshot IDs. The query also reports compact visual state while `rqt_image_view`
shows the raw transport; the query must contain no pixels. This graphical check
was not executed in this milestone. Press `Ctrl-C` and verify the isolated
graph/processes terminate.
