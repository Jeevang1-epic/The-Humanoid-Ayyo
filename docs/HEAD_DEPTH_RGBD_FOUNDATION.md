# Head Depth / RGB-D Sensor Foundation v1

## Purpose and status

This milestone adds a transport-neutral, trustworthy head-depth evidence path.
Its scope is the independent depth sensor foundation, not RGB-D fusion or scene
perception. The subsequent
[Head RGB-D Fusion Foundation](HEAD_RGBD_FUSION_FOUNDATION.md) consumes this
unchanged compact depth contract. The live
end-to-end automated path validated here is a programmatic TEST source. A
default-off Gazebo simulation seam is implemented and contract-tested, but the
dedicated depth smoke does not claim a Gazebo sensor-performance validation.
No physical depth camera, vendor driver, or real-world depth calibration was
used or validated.

```text
reviewed depth source
  → sensor_msgs/Image + sensor_msgs/CameraInfo
  → exact source/frame/session/calibration and payload validation
  → compact sealed depth frame + acquisition health
  → Perception Trust Boundary
  → bounded Working Memory
  → immutable World Model
  → read-only GetRobotBodyState query
```

Raw depth bytes exist only while the ROS callback validates and summarizes one
message. They do not enter Perception state, Working Memory, World Model,
Memory OS, Personal Context, Executive, Safety, Skill Manager, or the query.

## Fixed ROS and sensor identity

The reviewed standard interfaces are:

| Topic | Type |
| --- | --- |
| `/ayyo/camera/head/depth/image_raw` | `sensor_msgs/msg/Image` |
| `/ayyo/camera/head/depth/camera_info` | `sensor_msgs/msg/CameraInfo` |

The typed sensor is `ayyo.camera.head.depth.v1`, its mount datum is
`head_depth_camera_frame`, and its optical frame is
`head_depth_camera_optical_frame`. The mount is a fixed zero transform under
the existing `head_camera_frame`. The depth optical joint is fixed under the
depth mount with RPY `-π/2 0 -π/2`, preserving ROS optical axes without
changing the existing RGB optical frame.

The description validator now requires 39 links, 38 joints, 18 movable joints,
and the unchanged 33-part mesh contract. It checks the fixed parentage,
transform, finite values, uniqueness, and distinct RGB/depth identities.

## Source identity and provenance

`DepthSourceManifest` binds robot, depth sensor, producer/version/implementation
digest, classification, provenance, mount and optical frames, fixed topics,
geometry, encoding and metric-range allowlists, calibration identities, and a
canonical manifest fingerprint. The registry admits at most 16 exact sources.

| Profile class | Source kind | Clock | Transport | Executable v1 status |
| --- | --- | --- | --- | --- |
| TEST fixture | `test_fixture` | `test_time` | `ros2` | validated |
| Gazebo | `simulation` | `ros_simulation_time` | `ros2` | default-off seam |
| recorded fixture | `recorded_data` | `recorded_time` | `recorded` | typed contract only |
| reviewed device | `physical_sensor` | `ros_system_time` | `ros2` | no device profile yet |

The validated TEST source is
`ros.camera.head.depth.test-fixture.v1`. The simulation source is
`ros.camera.head.depth.simulation.gazebo.v1`. Classification, source kind,
clock, transport, sensor, producer, calibration, and manifest must all agree;
shared ROS topics never confer physical trust. Simulation cannot masquerade as
physical, and recorded evidence cannot masquerade as live evidence.

## Calibration and exact pairing

`DepthCameraCalibration` wraps the existing finite, bounded standard
`CameraCalibration` and adds exact sensor, source, mount, optical frame,
version, calibration source, and optional import identity. Two canonical
identities are retained:

- `camera-calibration-sha256-*` fingerprints standard `CameraInfo` content.
- `depth-camera-calibration-sha256-*` additionally binds the depth source,
  frames, version, and import source.

Invalid dimensions, distortion models/coefficient counts, `D/K/R/P` shapes,
non-finite or all-zero matrices, binning/ROI, frames, source binding, or
fingerprints fail closed. Unknown calibration cannot activate acquisition.
The repository makes no claim that the fixture or Gazebo matrices describe a
real lens accurately.

Image and CameraInfo pair only at the same nonzero acquisition timestamp and
under the same robot, source, sensor, optical frame, provenance, active session,
and configured calibration. Arrival proximity is never used. Each side of the
pairing state has an eight-entry hard bound and a 200 ms default wait window.

## Depth encoding semantics

V1 admits only explicit source-allowlisted `16UC1` and `32FC1` images:

- `16UC1` values are unsigned millimetres and are converted to metres for the
  compact range summary. Zero means invalid/no return.
- `32FC1` values are metres. Zero and NaN are explicit invalid/no-return
  sentinels. Negative values and positive or negative infinity are rejected.
- Every nonzero valid value must be inside the source's reviewed metric range;
  the current TEST/simulation range is 0.1–30.0 m.
- Width, height, encoding, endian flag, row step, and total byte count must be
  internally consistent. Row padding is allowed only when the total payload is
  exactly `step × height`.
- Empty buffers and frames with no valid measurement are rejected.

Validation produces only width/height/encoding/step/byte count/endian,
valid/invalid counts, minimum/maximum metres, and a payload SHA-256. It retains
no pixel array.

## Lifecycle, admission, and recovery

The adapter states are `unconfigured`, `inactive`, `active`, and `finalized`.
Configuration resolves one registered source and exact calibration. Every
activation creates a distinct deterministic session ID. Inactive callbacks,
old sessions, and incomplete pairs are rejected. Deactivation clears pairing,
Perception authorization, and Working Memory state; cleanup returns to
unconfigured, and shutdown is terminal.

Only the adapter can seal `DepthCameraAdmission`. Its frame and separate health
observation must match one exact `DepthTrustRequirement`. Perception consumes
the frame and health authorization once. Bare frames, replays, changed
requirements, unknown producers/sources, wrong robot/sensor/frame, physical or
recorded spoofing, stale/future/out-of-order time, and conflicting identities
fail closed. Rejected traffic does not poison later valid evidence.

Depth observations are evidence only. The adapter, query, fixture, and Gazebo
bridge expose no command, movement, navigation, manipulation, skill, Safety,
Executive, or durable-memory authority.

## Working Memory, World Model, and query

Working Memory keeps at most one current compact depth observation per sensor
plus its configured bounded recent evidence. Duplicate evidence does not grow
state; stale evidence disappears; rejected evidence cannot resurrect it; reset
clears the time/session epoch. The standard fixture uses a 16-entry recent
capacity in its 5,000-cycle resource proof.

World Model exposes immutable `DepthFrameObservation` state with calibration,
manifest, session, source time/provenance, compact validity/range statistics,
and observation/payload fingerprints. Missing evidence remains missing. Query
evaluation does not mutate state, and no depth byte array exists in the
snapshot or `GetRobotBodyState` response.

The read-only query adds `current_depth_count` and one optional compact
`depth_frame`. It contains no RGB-depth association or geometric claim.

## Simulation and physical migration

Gazebo depth is independently default-off through `enable_depth_camera=false`.
When explicitly enabled with the World Model, the description creates one
320×240, 10 Hz `R_FLOAT32` sensor on the depth optical frame with 0.1–30.0 m
clipping. Fixed one-way bridges carry Image and CameraInfo into the reviewed
topics, and the World Model selects only `simulation_depth_v1`. Normal core
imports and the hardware-free TEST smoke do not require Gazebo.

A future real RGB-D device should publish the same standard topics while adding
a dedicated `PROJECT_REVIEWED_DEVICE` manifest/profile, verified driver and
implementation identity, controlled calibration import, device identity where
truthfully available, ROS system-time behavior, and hardware diagnostics. It
must not rename or reuse the TEST/simulation profile. RGB and depth remain
independently admitted evidence; the separate reviewed temporal fusion layer
does not turn this TEST depth profile into physical trust.

## Resource and adversarial proof

The deterministic fixture sends 5,000 exact pairs through adapter → Perception
→ Working Memory → World Model. Expected final state is 5,000 accepted pairs,
10,000 admitted frame/health observations, one current depth state, one health
state, 16 recent unique observations, 18 total retained references, zero
pending pairs, and zero unused depth authorizations. `tracemalloc` must remain
below 32 MiB peak; this is a regression ceiling, not an edge-hardware benchmark.

The unit/fixture/smoke coverage rejects malformed calibration, empty/malformed
payloads, unsupported encoding, bad step/byte counts, invalid/NaN/infinite/range
semantics, wrong robot/camera/sensor/frame/source/producer, simulation/physical
and recorded/live substitution, stale/future/regressed/out-of-order/duplicate
evidence, conflicting identities/fingerprints, inactive/old-session evidence,
and bare Perception bypass. It proves valid recovery and scoped clean teardown.
The fixture also verifies that the Gazebo manifest remains explicitly
`simulation`/`ros_simulation_time`/`ros2` and cannot enter the TEST trust policy.

## Explicit limitations and non-goals

Not implemented: physical depth hardware, vendor driver, device discovery,
calibration file loader, hardware timing/rate/latency/drop validation,
physical RGB-depth synchronization, spatial registration, PointCloud2, 3D
geometry, obstacle extraction,
objects/faces/people, tracking, segmentation, OCR, scene understanding, SLAM,
visual localization, navigation, manipulation, motion planning, autonomous
movement, production ML, cloud/network services, or authority of any kind.

## Exact manual validation

From the repository root:

```bash
source /opt/ros/jazzy/setup.bash
export PYTHONPATH="world_model/src:depth_camera/src:physical_camera/src:visual_evaluation/src:perception/src:working_memory/src:ros2_ws/src/ayyo_world_model/scripts:$PYTHONPATH"
python3 -m pytest -q \
  depth_camera/tests \
  perception/tests/test_depth_boundary.py \
  working_memory/tests/test_depth_resources.py \
  world_model/tests/test_depth_camera.py \
  ros2_ws/src/ayyo_world_model/test/test_ros_adapter.py \
  ros2_ws/src/ayyo_description/test/test_description.py \
  ros2_ws/src/ayyo_simulation/test/test_simulation.py

rm -rf ros2_ws/build ros2_ws/install ros2_ws/log
./scripts/build_workspace.sh
source ros2_ws/install/setup.bash
./scripts/test_workspace.sh
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py

./scripts/smoke_head_depth_rgbd.sh
./scripts/smoke_head_depth_rgbd.sh
git diff --check
```

For manual Gazebo inspection, use an isolated domain/partition and explicitly
enable both World Model and depth:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=151
export GZ_PARTITION=ayyo_head_depth_manual_151
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_world_model:=true enable_depth_camera:=true
```
