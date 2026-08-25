# Perception Trust Boundary and Proprioception Foundation v1

## Status and mission

Ayyo now has a deterministic, transport-neutral boundary that decides whether
normalized proprioceptive evidence is admissible before it can affect Working
Memory or the World Model. Admission means that evidence is structurally valid,
fresh enough, correctly identified, and from one reviewed source profile. It
does not mean the measurement is objectively true, safe, authorized, or an
instruction.

The supported live evidence is deliberately narrow:

- existing standard `/joint_states` feedback;
- one standard `sensor_msgs/Imu` body-IMU stream on `/ayyo/imu/data`;
- one exact-frame standard `nav_msgs/Odometry` localization stream on
  `/ayyo/localization/odometry`; and
- two reviewed standard `DiagnosticArray` component identities on
  `/diagnostics`; and
- one paired standard `sensor_msgs/Image` and `sensor_msgs/CameraInfo` RGB
  stream on fixed head-camera topics.

Body pose, sensor health, and covariance remain transport-neutral standalone
contracts. The live localization and diagnostics seams are documented in
[BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md](BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md).
Camera detection/recognition/tracking, depth, audio, fusion, navigation, motion
authority, and durable sensor logging are not implemented. The RGB transport
and compact pixel-free visual-state boundary are documented in
[Visual Camera Foundation](VISUAL_CAMERA_FOUNDATION.md).
The bounded post-admission semantic seam and synthetic-only proof are documented
in [Visual Perception Processing](VISUAL_PERCEPTION_PROCESSING.md).

## Architecture

```text
Gazebo Harmonic body IMU / localization / RGB camera / simulated ros2_control
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
physical IMU / encoders / future localization and standard RGB camera
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
- `ayyo_description` single-owns `imu_link`, the head camera mount, and the
  fixed ROS optical frame.
- `ayyo_simulation` owns the Harmonic observation sources, fixed one-way ROS
  bridges, opt-in localization/camera flags, and development proof composition.

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
- exact paired image/calibration timestamp, optical frame, dimensions,
  encoding, step/byte count, and calibration invariants;
- reviewed body-pose source and target frames;
- source time against future-skew and retention bounds;
- monotonic receipt ordering;
- duplicate, out-of-order, and same-time conflicting evidence; and
- content-derived observation identity and fingerprint integrity.

The boundary retains only one ordering pair per configured measurement, health,
or visual camera/producer key. Source registrations are capped at 32,
interpretation producers at 16, and recently admitted visual source references
at 64 with deterministic eviction. There is no unbounded history queue, worker,
timer, polling loop, dynamic source discovery, or arbitrary topic selection.

Malformed evidence produces typed validation or admission failure. Programming
errors are not hidden by broad catch-and-ignore handling.

## Supported sensor contracts

The live simulation profile registers these immutable semantic identities:

| Kind | Sensor identity | Frame | ROS interface |
| --- | --- | --- | --- |
| Joint state | `ayyo.joint-state.body.v1` | `base_link` | `/joint_states` `sensor_msgs/JointState` |
| IMU | `ayyo.imu.body.v1` | `imu_link` | `/ayyo/imu/data` `sensor_msgs/Imu` |
| Body pose | `ayyo.body-pose.localization.v1` | `odom` → `base_link` | `/ayyo/localization/odometry` `nav_msgs/Odometry` |
| RGB camera | `ayyo.camera.head.rgb.v1` | `head_camera_optical_frame` | `/ayyo/camera/head/image_raw` `sensor_msgs/Image` + `/ayyo/camera/head/camera_info` `sensor_msgs/CameraInfo` |

The body-pose contract permits only source frame `odom` and body frame
`base_link`. The adapter performs one bounded exact-source-timestamp TF2 lookup;
it never requests latest TF, aliases frames, publishes a competing public TF,
or fabricates a pose.

The visual adapter accepts only a nonzero exact-timestamp pair with identical
optical frame and dimensions. It currently accepts `rgb8`, positive bounded
dimensions, exact `step >= width*3`, and exactly `step*height` non-empty bytes.
It validates finite bounded calibration arrays and derives their identity
deterministically. Only compact metadata crosses into the transport-neutral
observation; pixel bytes are never hashed into or stored by trust, Working
Memory, World Model, the body-state query, or Memory OS.

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

The live adapter accepts only `odom` to `base_link` standard odometry, inserts
that one sample into a TTL-bounded TF2 buffer, and looks it up at the exact
nonzero source timestamp with a 20 ms default and 100 ms hard maximum wait.
Returned frames/time are rechecked before normalization. Lookup, connectivity,
extrapolation, timeout, stale, numeric, quaternion, and covariance failures
become typed health evidence without replacing the last valid pose. Unknown
all-zero covariance and absent quality remain `None`.

## Health and availability

The transport-neutral states are:

- `AVAILABLE` — measurement or health evidence says the source is available;
- `DEGRADED` — evidence remains usable with a supplied degraded condition;
- `ERROR` — explicit source/adapter failure evidence;
- `STALE` — query time crossed the freshness boundary; and
- `UNAVAILABLE` — no retained source evidence or an explicit unavailable report.

`SensorHealthObservation` retains bounded diagnostic text only as evidence.
The live adapter accepts exact name/hardware pairs only for the joint-state and
body-IMU sources and maps ROS OK/WARN/ERROR/STALE to available/degraded/error/
stale. Unknown names are explicitly ignored; wrong identity, malformed level,
conflicting duplicate, duplicate key, or oversized input is rejected. Text and
key/value fields cannot become an endpoint, expression, identity, permission,
approval, policy, or executable content.

Measurement availability and explicit health are projected independently.
Message arrival does not imply healthy. A measurement may remain visible while
explicit health is degraded/error, and missing diagnostics remain `null`.

## Provenance and clocks

Simulation and physical profiles use different immutable provenance:

| Evidence | Simulation source | Physical source | Clock |
| --- | --- | --- | --- |
| Joint state | `ros.joint-states.simulation.ros2-control.v1` | `ros.joint-states.physical.ros2-control.v1` | simulation / system |
| IMU | `ros.imu.simulation.gz-harmonic.v1` | `ros.imu.physical.standard-driver.v1` | simulation / system |
| Body pose | `ros.body-pose.simulation.localization.v1` | `ros.body-pose.physical.localization.v1` | simulation / system |
| Diagnostics | `ros.diagnostics.simulation.test-fixture.v1` | `ros.diagnostics.physical.standard.v1` | simulation / system |
| RGB camera | `ros.camera.head.simulation.gz-harmonic.v1` | `ros.camera.head.physical.standard-driver.v1` | simulation / system |

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

At the freshness crossing, retained IMU, visual, pose, or explicit health
evidence becomes `STALE`; the snapshot identity changes once. After TTL it is removed
and the known measurement sensor becomes `UNAVAILABLE`, while absent explicit
health returns `null`; the snapshot identity changes again. Query times within
one discrete freshness state do not change semantic identity. Duplicates
cannot refresh either boundary.

There are no background timers. Query/ingestion time deterministically advances
freshness and expiry. Source-clock regression resets both trust-boundary and
Working-Memory state before a new epoch. Adapter restart and lifecycle cleanup
start empty. Deactivation destroys all six subscriptions, clears the two
single-message camera pending slots, drops the TF2 buffer, and makes the
read-only query not ready.

## Working Memory and World Model

Working Memory retains at most one current IMU observation, one current visual
observation, one current body-pose observation per reviewed v1 source, one
health observation per sensor, the catalog-bounded current joints, and the
configured recent-evidence window.
High-frequency samples replace current state and are pruned by TTL/capacity.

World Model `RobotBodyState` now contains:

- unchanged catalog-bounded joint state;
- zero or more immutable current IMU states;
- zero or more immutable compact visual states without pixels;
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
and no timer. On activation it creates exactly six fixed subscriptions:

```text
/joint_states       sensor_msgs/JointState
/ayyo/imu/data      sensor_msgs/Imu
/ayyo/localization/odometry  nav_msgs/Odometry
/diagnostics        diagnostic_msgs/DiagnosticArray
/ayyo/camera/head/image_raw  sensor_msgs/Image
/ayyo/camera/head/camera_info  sensor_msgs/CameraInfo
```

It exposes only the existing fixed read-only service:

```text
/ayyo/world_model/get_robot_body_state
ayyo_interfaces/srv/GetRobotBodyState
```

The additive response reports sensor summaries, IMU estimates and explicit
presence flags, covariance/quality presence, pose availability, provenance,
freshness, fingerprints, compact visual metadata/calibration identity, and
bounded counters while preserving all existing joint fields. Requests cannot
select topics, frames, graph endpoints, filters,
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
| `/ayyo/localization/ground_truth/odometry` `gz.msgs.Odometry` | `/ayyo/localization/odometry` `nav_msgs/Odometry` | Gazebo → ROS |
| `/ayyo/camera/head/image_raw` camera image | same topic `sensor_msgs/Image` | Gazebo → ROS via `ros_gz_image` when enabled |
| `/ayyo/camera/head/camera_info` `gz.msgs.CameraInfo` | same topic `sensor_msgs/CameraInfo` | Gazebo → ROS when enabled |

`scripts/smoke_perception.sh` proved actual fresh IMU evidence—not merely topic
existence—through Gazebo → ROS → trust boundary → Working Memory → World Model
→ read-only query, verified simulation provenance and missing pose, exercised
deactivate/reactivate, and observed clean shutdown.

With `enable_localization:=true`, Harmonic's fixed 50 Hz odometry publisher
provides development ground truth labeled only as simulation. The non-installed
test fixture supplies reviewed diagnostics because there is no production
health producer. `scripts/smoke_localization_diagnostics.sh` proves actual pose,
all four ROS health mappings, unknown/wrong-frame fail-closed behavior, expiry,
motion independence, and clean shutdown.

With `enable_camera:=true`, the fixed optical-frame Harmonic camera supplies
10 Hz 320x240 `rgb8` images and matching calibration. The default remains off.
`scripts/smoke_visual_camera.sh` proves the real non-empty image path through
admission and the pixel-free query, simulation provenance, wrong-frame and
malformed rejection, valid recovery, expiry/health disappearance, lifecycle,
existing neck motion independence, and clean shutdown.

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

A separate 3,000-cycle pose/health regression retains one current pose, one
current health observation, 32 recent observations, and at most 34 unique
observations/references while enforcing current traced memory below 2 MB and
peak below 8 MB.

A 5,000-frame visual regression at a simulated 10 Hz retains one trust key,
one current visual item, 21 recent/unique observations, and 22 references.
`tracemalloc` reported 110,275 current bytes and a 113,999-byte peak. This
excludes image transport buffers, ROS middleware, Gazebo, and the interpreter;
it is not a Raspberry Pi or Jetson compatibility claim.

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
./scripts/smoke_localization_diagnostics.sh
./scripts/smoke_visual_camera.sh
```

Tests cover malformed values and shapes, ROS unavailable/unknown semantics,
quaternion tolerance, covariance structure and positive-semidefiniteness,
wrong sensor/robot/frame/provenance/clock, time ordering, duplicates, health,
disappearance, reset, immutable identities, lifecycle, high-rate bounds, and
all prior contracts. Visual cases include empty/malformed/oversized payload
metadata, wrong optical frame, mismatched calibration/time/dimensions,
non-finite intrinsics, source substitution, duplicate/out-of-order/future/stale
input, fixed pending slots, and pixel-free state/query surfaces.

## Exact human validation

After building, launch the reviewed graphical simulation path:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=123
export GZ_PARTITION=ayyo_perception_manual_123
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false enable_world_model:=true enable_localization:=true \
  enable_camera:=true
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
ros2 topic echo --once /ayyo/localization/odometry nav_msgs/msg/Odometry
ros2 topic echo --once /ayyo/camera/head/camera_info sensor_msgs/msg/CameraInfo
ros2 run ayyo_world_model body_state_query.py
ros2 run rqt_image_view rqt_image_view /ayyo/camera/head/image_raw
```

Confirm the lifecycle is active, the IMU has one publisher and exact
`imu_link`, the query reports a fresh `ayyo.imu.body.v1` observation with
simulation provenance, and the base pose reports exact `odom` to `base_link`
frames with simulation localization provenance. Diagnostics remain absent
until an explicit reviewed producer supplies them. This validates development
plumbing only. Confirm the camera optical frame, non-empty RGB image, matching
calibration, and compact visual query state containing no pixels. This
graphical camera check was not executed in this milestone. It does not validate
physical calibration, dynamics, final geometry, hardware, or safety. Press
`Ctrl-C` and verify the isolated graph and Gazebo processes terminate.

## Known limitations

- No physical IMU/camera, localization estimator, diagnostics producer, or
  physical source profile has been exercised.
- Gazebo covariance is unknown and quality is absent; neither is fabricated.
- No SLAM, sensor calibration, clock-sync, cross-sensor consistency, or fusion
  adapter exists.
- There is no physical pose estimate, bias estimate, gravity compensation, EKF,
  SLAM, contact state, force/torque, tactile, depth, audio, detection,
  recognition, tracking, scene understanding, or visual localization.
- Sensor health text is inert evidence; no production ROS diagnostics source is
  implemented.
- Working Memory remains in-process and non-durable.
- Perception supplies evidence only and cannot authorize movement or modify
  Safety policy.

## Future work

Physical estimator/driver/camera validation, production diagnostic producers,
calibration refinement, bias estimation, SLAM/fusion, visual localization,
semantic camera/audio perception, navigation, durable telemetry policy, and
production execution authority remain separate reviewed milestones.
