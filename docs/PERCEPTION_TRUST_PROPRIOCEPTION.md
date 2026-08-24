# Perception Trust Boundary and Proprioception Foundation v1

## Status and mission

Ayyo now has a deterministic, transport-neutral boundary that decides whether
normalized proprioceptive evidence is admissible before it can affect Working
Memory or the World Model. Admission means that evidence is structurally valid,
fresh enough, correctly identified, and from one reviewed source profile. It
does not mean the measurement is objectively true, safe, authorized, or an
instruction.

The supported live evidence is deliberately narrow:

- existing standard `/joint_states` feedback; and
- one standard `sensor_msgs/Imu` body-IMU stream on `/ayyo/imu/data`.

Body/base pose, sensor-health, and covariance contracts exist in the standalone
core. Body pose has no live source and is reported `UNAVAILABLE`; diagnostics
have no live adapter. Camera, depth, audio, detection, fusion, localization,
motion, and durable sensor logging are not implemented.

## Architecture

```text
Gazebo Harmonic body IMU / simulated ros2_control today
        ↓
fixed standard ROS sensor topics
        ↓
lifecycle ROS decoding adapter
        ↓
ayyo-perception deterministic trust boundary
        ↓ accepted immutable transport-neutral observation
bounded Working Memory
        ↓
World Model projection
        ↓
fixed read-only body-state query
```

The intended physical path is the same above the driver:

```text
physical IMU / encoders / future localization
        ↓
vendor driver exposing standard ROS sensor messages
        ↓
the same lifecycle decoding adapter using a physical source profile
        ↓
the same trust boundary, Working Memory, and World Model contracts
```

Only the exact provenance profile and lower driver are allowed to change. The
standalone core contains no `rclpy`, ROS message, Gazebo, `ros_gz`, vendor SDK,
network, persistence, or subprocess import.

## Package ownership

- `world_model/` owns immutable canonical observations, covariance, sensor
  identity, availability, projected body state, and snapshot identity.
- `perception/` owns exact source registration and deterministic admission.
  It depends only on the public `ayyo-world-model` package.
- `working_memory/` owns bounded current/recent evidence, source-time TTL,
  duplicate/order policy, and deterministic disappearance.
- `ros2_ws/src/ayyo_world_model` composes those three cores and owns ROS
  decoding, lifecycle, fixed subscriptions, and the read-only query.
- `ayyo_description` single-owns `imu_link` and its fixed pelvis mount.
- `ayyo_simulation` owns only the Harmonic IMU system and explicit ROS bridge
  used for development proof.

No perception package imports Memory OS, cognition, Safety, Skill Manager,
Runtime Bridge, Simulation Control, or a controller command interface.

## Trust boundary

`PerceptionTrustBoundary` reconstructs every input using the immutable World
Model constructor before admission. It then checks:

- canonical robot identity;
- one exact registered sensor kind, identity, and frame;
- one exact source identity, source kind, interface, transport, and clock;
- source-profile/clock compatibility;
- finite values, vector dimensions, quaternion and covariance invariants;
- reviewed body-pose source and target frames;
- source time against future-skew and retention bounds;
- monotonic receipt ordering;
- duplicate, out-of-order, and same-time conflicting evidence; and
- content-derived observation identity and fingerprint integrity.

The boundary retains only one `(timestamp, observation ID)` pair per configured
measurement or health key. Source registrations are capped at 32 and tracked
keys at twice that count. There is no history queue, worker, timer, polling
loop, dynamic source discovery, or arbitrary topic selection.

Malformed evidence produces typed validation or admission failure. Programming
errors are not hidden by broad catch-and-ignore handling.

## Supported sensor contracts

The live simulation profile registers these immutable semantic identities:

| Kind | Sensor identity | Frame | ROS interface |
| --- | --- | --- | --- |
| Joint state | `ayyo.joint-state.body.v1` | `base_link` | `/joint_states` `sensor_msgs/JointState` |
| IMU | `ayyo.imu.body.v1` | `imu_link` | `/ayyo/imu/data` `sensor_msgs/Imu` |
| Body pose | `ayyo.body-pose.localization.v1` | target `base_link` | contract only; no live topic |

The body-pose contract currently permits only reviewed source frame `map` in
the composed v1 profile. Because no localization or TF adapter exists, that
registration creates an expected unavailable sensor state; it does not create a
pose.

## IMU semantics

`ImuObservation` can independently carry:

- orientation quaternion;
- angular velocity in radians per second;
- linear acceleration in metres per second squared;
- optional 3x3 covariance for each supplied estimate;
- optional scalar quality in `[0, 1]` when a source actually supplies one;
- sensor/frame identity, source timestamp, provenance, and availability; and
- canonical observation ID and typed SHA-256 fingerprint.

ROS `sensor_msgs/Imu` rules are preserved at decoding:

- covariance element zero equal to `-1` means that associated estimate is not
  supplied, so both estimate and covariance remain absent;
- an all-zero covariance array means covariance is unknown, so it becomes
  `None`, not perfect covariance;
- zero-valued measurement components remain real supplied values only when the
  associated estimate is available; and
- the adapter supplies no quality value because Gazebo does not provide one.

At least one estimate must be present. NaN, either infinity, booleans as
numbers, wrong dimensions, zero quaternions, and grossly unnormalized
quaternions are rejected.

Quaternions within `1e-6` norm error are normalized, and the equivalent `q` / 
`-q` representations are sign-canonicalized before identity derivation. This
bounded numerical rule does not normalize grossly invalid data. Negative zero
is canonicalized to positive zero so equivalent rotations have equal
fingerprints.

## Covariance and quality

`CovarianceMatrix` supports only 3x3 sensor covariance and 6x6 pose covariance.
It requires the exact square value count, finite real numbers, symmetry within
a bounded numerical tolerance, non-negative variance, and a positive-
semidefinite matrix checked by bounded dependency-free LDL-transpose
decomposition. Covariance without its estimate is invalid.

Unknown covariance and unavailable quality remain `None`. The ROS query uses
explicit `has_*` flags; the JSON client renders absent estimates, covariance,
quality, and pose as `null`. Placeholder transport zeros are never presented as
known state.

Covariance and quality preserve uncertainty. They are not converted to binary
truth, permission, approval, safety clearance, or execution eligibility.

## Body/base pose semantics

`BodyPoseObservation` carries one actual `Pose3D`, exact source and body target
frames, optional 6x6 covariance, optional quality, provenance, availability,
and canonical identity. Translation is metres and orientation is a canonical
XYZW quaternion.

No TF/localization adapter is implemented. The World Model therefore reports:

```text
base_pose = unavailable
```

It never substitutes `0 0 0`, an identity quaternion, a latest transform, or a
different frame. The trust boundary has typed failure evidence for lookup
unavailable and extrapolation cases so a future bounded adapter can report
failure without manufacturing a transform. Future TF lookup must use the exact
registered frames and requested timestamp with a bounded lookup duration.

## Health and availability

The transport-neutral states are:

- `AVAILABLE` — measurement or health evidence says the source is available;
- `DEGRADED` — evidence remains usable with a supplied degraded condition;
- `ERROR` — explicit source/adapter failure evidence;
- `STALE` — query time crossed the freshness boundary; and
- `UNAVAILABLE` — no retained source evidence or an explicit unavailable report.

`SensorHealthObservation` retains bounded diagnostic text only as evidence.
No code interprets that text as an endpoint, expression, identity, permission,
approval, policy, or executable content. There is no live
`diagnostic_msgs` adapter in v1.

When measurement and health evidence both exist, the newest source-timestamped
evidence determines the availability summary; equal-time health is
conservative. The immutable measurement may remain visible with `ERROR` or
`DEGRADED` status so uncertainty is not erased.

## Provenance and clocks

Simulation and physical profiles use different immutable provenance:

| Evidence | Simulation source | Physical source | Clock |
| --- | --- | --- | --- |
| Joint state | `ros.joint-states.simulation.ros2-control.v1` | `ros.joint-states.physical.ros2-control.v1` | simulation / system |
| IMU | `ros.imu.simulation.gz-harmonic.v1` | `ros.imu.physical.standard-driver.v1` | simulation / system |
| Body pose contract | `ros.body-pose.simulation.localization.v1` | `ros.body-pose.physical.localization.v1` | simulation / system |

Simulation requires `ROS_SIMULATION_TIME` and `use_sim_time=true`. Physical
sensors require `ROS_SYSTEM_TIME` and `use_sim_time=false`. Recorded and test
sources retain their own clock kinds in the public model. Unrelated clocks are
never compared.

Source timestamp, ROS current source time, and monotonic receipt time remain
separate. Receipt time is admission evidence and never enters semantic
fingerprints. Relabeling simulation evidence as physical changes provenance,
identity, and requires admission under a different exact profile.

## Freshness and disappearance

Default source-time policy remains:

- fresh through 500 ms age;
- retained through a 2 second TTL;
- future skew allowed through 50 ms; and
- older/future evidence outside those bounds rejected.

At the freshness crossing, an IMU remains bounded evidence but becomes
`STALE`; the snapshot identity changes once. After TTL it is removed and the
known sensor becomes `UNAVAILABLE`; the snapshot identity changes again. Query
times within one discrete freshness state do not change semantic identity.
Duplicates cannot refresh either boundary.

There are no background timers. Query/ingestion time deterministically advances
freshness and expiry. Source-clock regression resets both trust-boundary and
Working-Memory state before a new epoch. Adapter restart and lifecycle cleanup
start empty. Deactivation destroys both subscriptions and makes the read-only
query not ready.

## Working Memory and World Model

Working Memory retains at most one current IMU observation, one current body-
pose observation per reviewed v1 source, one health observation per sensor, the
catalog-bounded current joints, and the configured recent-evidence window.
High-frequency samples replace current state and are pruned by TTL/capacity.

World Model `RobotBodyState` now contains:

- unchanged catalog-bounded joint state;
- zero or more immutable current IMU states;
- optional evidence-backed base pose; and
- a canonical availability summary for every expected sensor.

Snapshot identity includes values, covariance/quality, provenance, evidence
identity, effective availability, and discrete freshness. Complete observation
payloads are not duplicated for each IMU field; projected IMU state references
one immutable observation.

## Memory OS non-relationship

No sensor telemetry is written to Memory OS. Perception and Working Memory do
not import Memory OS or Memory Validation and perform no persistence. A future
meaningful consolidation policy must explicitly select bounded candidate
evidence and follow:

```text
Working Memory → Candidate Evidence → Memory Validation → Memory OS
```

Raw high-rate IMU telemetry must not bypass that path.

## ROS adapter and read-only API

`AyyoWorldModelNode` remains a `LifecycleNode` using a single-threaded executor
and no timer. On activation it creates exactly two fixed sensor-data QoS
subscriptions:

```text
/joint_states       sensor_msgs/JointState
/ayyo/imu/data      sensor_msgs/Imu
```

It exposes only the existing fixed read-only service:

```text
/ayyo/world_model/get_robot_body_state
ayyo_interfaces/srv/GetRobotBodyState
```

The additive response reports sensor summaries, IMU estimates and explicit
presence flags, covariance/quality presence, pose availability, provenance,
freshness, fingerprints, and bounded counters while preserving all existing
joint fields. Requests cannot select topics, frames, graph endpoints, filters,
expressions, services, actions, or robot identities other than canonical Ayyo.

## Gazebo Harmonic proof

The authoritative Xacro contains one fixed `imu_link` mounted 0.04 m above the
pelvis datum. Non-simulation expansion contains the frame but no sensor.
Simulation expansion adds one `body_imu` at that frame, publishing at 100 Hz.
The world adds only Harmonic's IMU system. The explicit bridge allowlist is now:

| Gazebo | ROS | Direction |
| --- | --- | --- |
| `/clock` `gz.msgs.Clock` | `/clock` `rosgraph_msgs/Clock` | Gazebo → ROS |
| `/ayyo/imu/data` `gz.msgs.IMU` | `/ayyo/imu/data` `sensor_msgs/Imu` | Gazebo → ROS |

`scripts/smoke_perception.sh` proved actual fresh IMU evidence—not merely topic
existence—through Gazebo → ROS → trust boundary → Working Memory → World Model
→ read-only query, verified simulation provenance and missing pose, exercised
deactivate/reactivate, and observed clean shutdown.

## Resource bounds and measurement

The trust boundary holds no observation history and tracks at most 32 sources /
64 measurement-health ordering keys. Working Memory retains at most 256 recent
observations by default and 4,096 at its hard maximum; its 2 second default TTL
also removes old high-rate evidence.

An explicit development-machine run admitted 5,000 full IMU samples at a
simulated 100 Hz through both trust and Working Memory. It retained one trust
key, one current IMU, 201 recent/unique observations at the inclusive 2-second
TTL boundary, and 202 total observation references. `tracemalloc` reported
545,739 current bytes and a 557,087-byte peak. This excludes the Python
interpreter, ROS middleware, and Gazebo and is not a Raspberry Pi or Jetson
compatibility claim.

## Automated validation

```bash
PYTHONPATH=world_model/src python3 -m unittest discover -s world_model/tests -v
PYTHONPATH=world_model/src:perception/src \
python3 -m unittest discover -s perception/tests -v
PYTHONPATH=world_model/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v

./scripts/build_workspace.sh
./scripts/test_workspace.sh
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
./scripts/smoke_simulation.sh
./scripts/smoke_simulation_control.sh
./scripts/smoke_world_model.sh
./scripts/smoke_perception.sh
```

Tests cover malformed values and shapes, ROS unavailable/unknown semantics,
quaternion tolerance, covariance structure and positive-semidefiniteness,
wrong sensor/robot/frame/provenance/clock, time ordering, duplicates, health,
disappearance, reset, immutable identities, lifecycle, high-rate bounds, and
all prior contracts.

## Exact human validation

After building, launch the reviewed graphical simulation path:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=123
export GZ_PARTITION=ayyo_perception_manual_123
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false enable_world_model:=true
```

In a second identically configured terminal:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=123
export GZ_PARTITION=ayyo_perception_manual_123
ros2 lifecycle get /ayyo_world_model
ros2 topic info /ayyo/imu/data --verbose
ros2 topic echo --once /ayyo/imu/data sensor_msgs/msg/Imu
ros2 run ayyo_world_model body_state_query.py
```

Confirm the lifecycle is active, the IMU has one publisher and exact
`imu_link`, the query reports a fresh `ayyo.imu.body.v1` observation with
simulation provenance, and `base_pose` is `null`. This validates development
plumbing and visualization only, not physical calibration, dynamics, final
geometry, hardware, or safety. Press `Ctrl-C` and verify the isolated graph and
Gazebo processes terminate.

## Known limitations

- No physical IMU or physical source profile has been exercised.
- Gazebo covariance is unknown and quality is absent; neither is fabricated.
- No live TF/localization, diagnostics, sensor calibration, clock-sync,
  cross-sensor consistency, or fusion adapter exists.
- There is no pose estimate, bias estimate, gravity compensation, EKF, SLAM,
  contact state, force/torque, tactile, camera, depth, audio, or detection.
- Sensor health text is a typed core contract only; no ROS diagnostics input is
  live.
- Working Memory remains in-process and non-durable.
- Perception supplies evidence only and cannot authorize movement or modify
  Safety policy.

## Recommended next milestone

Implement **Body Localization and Sensor Diagnostics Foundation v1**: one
strict timestamped pose adapter with bounded exact-frame lookup, explicit
lookup/connectivity/extrapolation failure health, and a narrow allowlisted
diagnostics mapping for existing joint/IMU sources. Keep sensor fusion, SLAM,
camera/audio perception, durable telemetry, and execution authority out of
scope until those seams are reviewed.
