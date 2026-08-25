# Body Localization and Sensor Diagnostics Foundation v1

## Implemented now

Ayyo now has one narrow, evidence-only body-localization path and one
allowlisted standard ROS diagnostics path. Both terminate in the existing
Perception Trust Boundary, bounded Working Memory, immutable World Model, and
fixed read-only body-state query. Neither path authorizes motion, changes
Safety policy, writes Memory OS, or turns diagnostic text into behavior.

The verified simulation flow is:

```text
Gazebo Harmonic OdometryPublisher
→ fixed one-way ros_gz bridge (`nav_msgs/Odometry`)
→ exact `odom` to `base_link` TF2 lookup at the source timestamp
→ BodyPoseObservation with simulation provenance
→ Perception Trust Boundary
→ bounded Working Memory
→ immutable World Model snapshot
→ `/ayyo/world_model/get_robot_body_state`
```

The physical migration seam is deliberately the same above a future driver:

```text
physical localization estimator exposing standard `nav_msgs/Odometry`
→ the same exact-frame adapter under the physical source profile
→ the same trust, retention, projection, and read-only query contracts
```

Only the lower source and exact provenance profile change. The standalone
World Model, Working Memory, and Perception packages contain no ROS, Gazebo,
vendor SDK, network, persistence, command, or subprocess dependency.

## Fixed localization contract

The ROS boundary accepts only:

| Field | Reviewed value |
| --- | --- |
| ROS topic | `/ayyo/localization/odometry` |
| ROS type | `nav_msgs/msg/Odometry` |
| Reference/source frame | `odom` |
| Body/target frame | `base_link` |
| Sensor identity | `ayyo.body-pose.localization.v1` |
| Interface identity | `nav-msgs.odometry-tf2.v1` |
| Default exact lookup timeout | 20 ms |
| Maximum configurable lookup timeout | 100 ms |

Frame names are constants, not request parameters. `map`, aliases, empty
frames, reverse pairs, and a different body frame fail closed. This milestone
does not introduce a `map` frame or claim a global map.

Each odometry sample is converted into one transform in a TF2 `Buffer` whose
cache duration is the existing Working Memory retention TTL. The adapter asks
TF2 for exactly `odom → base_link` at the nonzero source timestamp. Timestamp
zero is rejected because TF2 reserves it for “latest.” There is no latest-time
retry, identity/zero-pose fallback, alternate-frame search, unbounded wait, or
public duplicate `/tf` publisher.

After lookup, the returned frame pair and timestamp are checked again. The
pose retains finite XYZ translation, canonical XYZW orientation, the original
source time, sensor identity, provenance, content-derived observation ID, and
typed fingerprint. A 36-value covariance is validated when supplied. An
all-zero ROS covariance means unknown and remains `null`; it is never treated
as perfect certainty. Quality remains `null` because the current source does
not supply it.

## Typed lookup and pose failure behavior

Failures become explicit bounded health evidence for the localization sensor;
they never overwrite the last valid pose with fabricated coordinates.

| Failure | Ayyo health |
| --- | --- |
| lookup unavailable | unavailable |
| lookup timeout | unavailable |
| connectivity failure | error |
| extrapolation / exact time unavailable | error |
| invalid frame request or lookup result | error |
| stale transform at admission | stale |
| rejected provenance | error |
| non-finite pose | error |
| invalid quaternion | error |
| invalid covariance | error |

The existing 500 ms freshness, 2 second retention TTL, and 50 ms permitted
future skew remain source-time policy. A retained pose becomes stale at the
freshness boundary and disappears after TTL. Duplicates and receipt time do
not refresh source-time state.

## Simulation localization source

Localization is opt-in. `simulation.launch.py` defaults
`enable_localization:=false`. When true, the authoritative Xacro enables
Harmonic's `gz::sim::systems::OdometryPublisher` with a fixed 50 Hz ground-
truth odometry output:

```text
/ayyo/localization/ground_truth/odometry  gz.msgs.Odometry
```

The simulation package's fixed bridge maps it one way to:

```text
/ayyo/localization/odometry  nav_msgs/msg/Odometry
```

It is labeled `ros.body-pose.simulation.localization.v1`, source kind
`simulation`, and clock `ros_simulation_time`. It is development ground truth,
not SLAM, fused localization, a physical estimate, or a safety-certified pose.
The plugin metadata is conditionally attached to the authoritative simulated
model; `ayyo_simulation` continues to own launch, bridge, profile selection,
and the development source boundary. Removing Gazebo leaves the hardware-
neutral observation contract intact.

## Reviewed diagnostics contract

The lifecycle adapter has one fixed `/diagnostics`
`diagnostic_msgs/msg/DiagnosticArray` subscription. Only these exact pairs can
affect Ayyo health:

| Diagnostic name | Required hardware ID | Sensor |
| --- | --- | --- |
| `ayyo/proprioception/joint_state_source` | `ayyo.joint-state.body.v1` | joint-state / encoder source |
| `ayyo/proprioception/body_imu_source` | `ayyo.imu.body.v1` | body IMU source |

The conservative mapping is:

| ROS level | Ayyo availability |
| --- | --- |
| `OK` | available |
| `WARN` | degraded |
| `ERROR` | error |
| `STALE` | stale |

Unknown component names are explicitly ignored and counted. A known hardware
identity cannot substitute a different name. Wrong identity, malformed level,
conflicting duplicate status, duplicate keys, oversized input, and malformed
time are rejected. Each array is limited to 16 statuses; each status to 16
key/value pairs; each name, ID, message, key, and value to 256 characters; and
the retained canonical detail to 1,024 characters.

Diagnostic message and key/value text is retained only as bounded canonical
JSON evidence. It cannot select an identity, permission, topic, service,
action, frame, command, expression, plugin, or executable. No diagnostic
history is durable or unbounded.

Missing diagnostics remain missing: message arrival from a measurement source
does not manufacture healthy evidence. Explicit health is projected separately
from measurement availability. It becomes stale by source time and disappears
after TTL; absence then returns `health: null`, never healthy.

The production adapter does not manufacture simulated health. The repository's
`scripts/perception_test_fixture.py` is executable test infrastructure only,
is not installed by a ROS package, and publishes fixed scenarios solely for the
headless smoke.

## Working Memory and read-only API

Working Memory retains at most one current body pose per reviewed v1 source,
one current health observation per sensor, and the configured bounded recent-
evidence window. Measurement and explicit health use independent ordering
keys, so a diagnostic cannot replace a measurement or vice versa. Snapshot
identity changes only for semantically relevant accepted evidence, a discrete
freshness transition, or disappearance.

`GetRobotBodyState.srv` additively exposes the base pose's exact frames,
translation, orientation, optional covariance/quality, timestamp, identity,
fingerprint, and full provenance. Parallel bounded sensor arrays expose
explicit health presence, availability, freshness, time, identity,
fingerprint, provenance, and evidence detail. `body_state_query.py` renders
missing pose, covariance, quality, or health as JSON `null`.

A 3,000-cycle regression alternates pose and health observations and enforces
one current pose, one current health item, 32 recent observations, no more than
34 unique observations/references, current traced memory below 2 MB, and peak
below 8 MB. The TF2 cache uses the same bounded retention duration. These are
development-machine regression ceilings, not edge-hardware certification.

## Lifecycle, authority, and durable-memory boundaries

This subsystem owns four of the adapter's six fixed observation subscriptions:
joint state, IMU, localization odometry, and diagnostics. The other two are the
paired head-camera `Image`/`CameraInfo` boundary documented in
[Visual Camera Foundation](VISUAL_CAMERA_FOUNDATION.md). Deactivation destroys
all six subscriptions and drops the TF2 buffer. Cleanup, shutdown, error, or
source-clock regression
discard temporary evidence. All waits and shutdown escalation are bounded;
there are no workers, abandoned futures, dynamic plugins, or arbitrary ROS
names in the production adapter.

Localization and health are evidence only. They cannot call the development
controller, Runtime Bridge, Skill Manager, Safety Kernel, Executive, or any
command endpoint. The existing 0.1 rad development motion proof remains a
separate explicitly enabled control path. No raw or summarized localization or
diagnostic telemetry is persisted to Memory OS.

## Automated and manual validation

```bash
PYTHONPATH=world_model/src python3 -m unittest discover -s world_model/tests -v
PYTHONPATH=world_model/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v
PYTHONPATH=world_model/src:perception/src \
python3 -m unittest discover -s perception/tests -v

./scripts/build_workspace.sh
./scripts/test_workspace.sh
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
./scripts/smoke_localization_diagnostics.sh
```

For a manual development inspection after a clean build:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=124
export GZ_PARTITION=ayyo_localization_manual_124
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false enable_control:=true enable_development_control:=true \
  enable_world_model:=true enable_localization:=true
```

In another terminal with the same setup and isolation variables:

```bash
ros2 lifecycle get /ayyo_world_model
ros2 topic info /ayyo/localization/odometry --verbose
ros2 topic echo --once /ayyo/localization/odometry nav_msgs/msg/Odometry
ros2 run ayyo_world_model body_state_query.py
```

Confirm exact `odom` and `base_link` frames, simulation provenance, a real
timestamped pose, 18 joint observations, IMU evidence, and absent health until
an explicit reviewed diagnostic is supplied. Stop with `Ctrl-C`; if necessary,
send `SIGINT` and then bounded `SIGTERM` to the launch PID. Verify with
`ros2 node list --no-daemon` and `ps -ef | grep '[g]z sim'` that the isolated
graph and Gazebo processes are gone.

## Future work — not implemented

This milestone does not implement SLAM, EKF or other sensor fusion,
calibration, bias estimation, visual localization, navigation, walking,
balance, manipulation, physical sensor validation, a production diagnostic
producer, production movement authorization, physical-safety certification,
or durable telemetry. The Gazebo source is not evidence that the physical Ayyo
has been localized. Physical drivers, estimator selection, clocks,
calibration, uncertainty, failure recovery, and hardware safety require later
review.
