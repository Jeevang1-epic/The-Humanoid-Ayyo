# Head RGB Camera and Visual Observation Foundation v1

## Implemented

Ayyo now has one narrow RGB visual-source path. It proves sensor transport,
calibration metadata, exact source identity, trust admission, temporary
retention, and read-only observability without claiming scene understanding.

The verified simulation path is:

```text
Gazebo Harmonic head RGB camera
→ ros_gz_image Image bridge + fixed CameraInfo bridge
→ sensor_msgs/Image + sensor_msgs/CameraInfo
→ exact-time fixed visual decoder
→ compact VisualFrameObservation (no pixels)
→ Perception Trust Boundary
→ bounded Working Memory
→ immutable World Model visual-source state
→ /ayyo/world_model/get_robot_body_state
```

This is evidence only. Camera input cannot call Executive, Safety, Skill
Manager, Runtime Bridge, Simulation Control, a controller, service, action, or
command. It writes nothing to Memory OS and grants no identity, permission,
approval, safety, health, or motion authority.

## Camera and frame contract

The authoritative description now owns:

```text
head_link
└── head_camera_frame
    └── head_camera_optical_frame
```

`head_camera_frame` remains the future physical mounting datum. The fixed
`head_camera_optical_joint` applies roll `-π/2`, pitch `0`, yaw `-π/2`, giving
the ROS optical convention: `+z` forward, `+x` right, and `+y` down. Image and
CameraInfo evidence must use exactly `head_camera_optical_frame`.

The frame contract exists in every description expansion. The sensor exists
only when simulation is expanded with `simulation_camera:=true`, which the
public launch controls through default-off `enable_camera:=false`.

## Fixed ROS interfaces

The reviewed input boundary contains no topic or frame parameters:

| ROS topic | Standard type | Direction | Transport owner |
| --- | --- | --- | --- |
| `/ayyo/camera/head/image_raw` | `sensor_msgs/msg/Image` | observation only | `ros_gz_image` / future standard driver |
| `/ayyo/camera/head/camera_info` | `sensor_msgs/msg/CameraInfo` | observation only | fixed one-way `ros_gz_bridge` entry / future standard driver |

`ros_gz_image` publishes the image through `image_transport`; the Ayyo adapter
does not create a second custom image message or bridge. CameraInfo uses a
separate fixed one-way allowlist entry with queue depth two. There is no wildcard,
ROS-to-Gazebo camera control, arbitrary ROS name, service, or action.

The lifecycle adapter retains at most one pending Image and one pending
CameraInfo reference while matching exact acquisition timestamps. Mismatched
older entries are dropped. After an exact pair is validated, pixel bytes are
not copied into an Ayyo observation and the pending references are cleared.
There is no timer, worker, retry loop, or history queue.

## Compact visual evidence

`VisualFrameObservation` is an immutable transport-neutral record containing
only:

- canonical robot and camera identities;
- exact optical frame;
- acquisition timestamp and source clock;
- source kind, source identity, transport, and interface;
- width, height, `rgb8` encoding, row step, byte-count metadata, and endian
  flag;
- deterministic calibration identity;
- measurement availability; and
- deterministic observation ID and typed SHA-256 fingerprint.

It has no pixel-data field. Pixel bytes are absent from World Model snapshots,
canonical snapshot fingerprints, Working Memory semantic state, recent
evidence payloads, and all durable memory. The byte count describes the
validated transport buffer; it does not retain that buffer.

World Model truthfully represents frame receipt and source availability only.
It does not create an object, person, owner identity, pose, depth, detection,
gesture, OCR result, relationship, or scene interpretation from raw RGB.

## CameraInfo and calibration identity

The adapter requires Image and CameraInfo to have the same nonzero source
timestamp, exact optical frame, and matching nonzero dimensions. The bounded
transport-neutral calibration contract validates:

- dimensions up to 4,096 per axis and 16,777,216 total pixels;
- a bounded nonempty distortion-model identity;
- at most 16 finite distortion values;
- exact finite 3×3 intrinsic and rectification arrays;
- an exact finite 3×4 projection array;
- nonzero positive focal lengths and homogeneous scales;
- bounded binning and in-image ROI metadata; and
- rejection of all-zero intrinsic, rectification, or projection claims.

Canonical calibration metadata derives
`camera-calibration-sha256-<digest>`. Only that compact identity is retained in
each visual frame observation. A changed matrix, model, dimension, binning, or
ROI changes the identity. The identity says which supplied metadata was used;
it is not a physical calibration certificate or quality score.

## Trust, time, freshness, and health

The simulation visual profile is immutable:

```text
sensor:     ayyo.camera.head.rgb.v1
frame:      head_camera_optical_frame
source:     ros.camera.head.simulation.gz-harmonic.v1
kind:       simulation
clock:      ros_simulation_time
transport:  ros2
interface:  sensor-msgs.image-camera-info.v1
```

The original `ros.camera.head.physical.standard-driver.v1` seam remains
unexercised and is not enabled as a trusted camera source by itself. The
separate
[Physical Head Camera, Calibration, and Diagnostics Foundation](PHYSICAL_HEAD_CAMERA_CALIBRATION_DIAGNOSTICS.md)
now requires an explicit source manifest, reviewed calibration, active session,
and sealed admission. Its executable source is TEST-only. Simulation evidence
cannot be relabeled as physical: exact provenance, clock, manifest, session,
and calibration checks reject substitution.

Visual evidence uses the existing default 500 ms freshness, 2 second TTL, and
50 ms permitted future skew. Duplicate, stale, future, out-of-order,
same-time-conflicting, wrong-robot, wrong-sensor, wrong-frame, wrong-source,
malformed-calibration, malformed-image, and source-clock-regression input fails
closed. Receipt time never replaces acquisition time.

A valid simulation frame establishes only that a source produced a valid frame
pair. The simulation path has no camera diagnostic producer, so explicit camera
health remains absent. The physical TEST foundation produces separate bounded
acquisition health; it is not scene understanding or real-device validation.
After freshness a retained measurement becomes stale; after TTL it disappears
and the known source becomes unavailable. This is evaluated on ingest/query
without a background timer.

## Simulation only

`enable_camera:=true` adds the Harmonic sensor and both reviewed bridges. The
development parameters are:

| Parameter | Simulation value |
| --- | ---: |
| Rate | 10 Hz |
| Resolution | 320 × 240 |
| Encoding | `rgb8` |
| Horizontal field of view | 1.0471975511965976 rad (60°) |
| Near / far clip | 0.1 m / 30.0 m |
| Rendering engine | Ogre2 |

These values are economical development parameters, not final physical
intrinsics, dimensions, placement accuracy, field of view, calibration, image
quality, or hardware selection. The headless smoke validates simulation
plumbing only. It does not validate a physical camera.

## Bounded-resource verification

Working Memory retains at most one current visual observation per reviewed
camera and the existing bounded recent-evidence window. No all-time visual ID
set exists. A 5,000-frame compact simulation at 10 Hz with the default 2 second
TTL retained:

- 5,000 accepted frames;
- one trust ordering key;
- one current visual state;
- 21 recent / unique observations at the inclusive TTL boundary; and
- 22 total observation references.

`tracemalloc` reported 110,275 current bytes and a 113,999-byte peak for the
Ayyo-owned compact trust and Working Memory structures. This excludes the
Python interpreter, Gazebo, ROS middleware, `image_transport`, bridge buffers,
and the unavoidable transient raw Image message. It is a development-machine
regression measurement, not a Raspberry Pi or Jetson performance claim.

## Verified

Automated validation covers deterministic optical topology, default-off sensor
expansion, explicit bridge configuration, standard-message normalization,
CameraInfo structure, malformed arrays and numbers, frame/time/dimension/
encoding/stride mismatches, exact source profiles, duplicates, ordering,
future/stale input, fingerprint tampering, lifecycle cleanup, and thousands of
high-rate compact observations.

The headless smoke verified:

- the canonical `ayyo` Gazebo entity;
- an actual nonempty 320×240 `rgb8` Image;
- matching CameraInfo and exact nonzero acquisition timestamp;
- exact `head_camera_optical_frame`;
- simulation provenance and deterministic calibration identity;
- trust admission and a single current visual state;
- malformed, wrong-frame, and physical-provenance substitution rejection;
- bounded recent evidence;
- independent existing 0.1-rad neck motion;
- lifecycle deactivate/reactivate behavior; and
- bounded clean ROS and Gazebo shutdown.

Run:

```bash
PYTHONPATH=world_model/src python3 -m unittest discover -s world_model/tests -v
PYTHONPATH=world_model/src:perception/src \
python3 -m unittest discover -s perception/tests -v
PYTHONPATH=world_model/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v
./scripts/build_workspace.sh
./scripts/test_workspace.sh
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
./scripts/smoke_visual_camera.sh
```

## Future physical migration path

The intended physical path is:

```text
physical RGB or RGB-D camera
→ vendor or standard ROS camera driver
→ fixed sensor_msgs/Image + sensor_msgs/CameraInfo topics
→ immutable physical source profile
→ same visual decoder and trust boundary
→ same bounded temporary visual-source state
→ later replaceable perception processors
→ compact trusted semantic observations
→ World Model
```

Real hardware review must establish the physical mount transform, calibration,
clock synchronization, supported encoding, bandwidth, failure behavior, and
diagnostics. It must not reuse simulation provenance. Memory OS, Personal
Context Twin, Executive, Safety, Skill Manager, Runtime Bridge, Working Memory
semantics, World Model semantics, and visual trust policy do not require a
Gazebo branch.

The processing seam deliberately does not select OpenCV, YOLO, MediaPipe, a
neural model, GPU vendor, cloud API, or proprietary vision stack. Later
processors may subscribe to the standard image transport and emit separately
reviewed compact evidence; they must not place pixel buffers into World Model
or durable memory.

The typed bounded seam and its explicitly synthetic reference proof are now
implemented by the
[Visual Perception Processing Foundation](VISUAL_PERCEPTION_PROCESSING.md).
It does not change the camera transport, calibration, frame, or pixel-retention
contracts described here and is not production machine perception.
The subsequent
[Recorded Visual Producer Evaluation and Perception Quality Gate](VISUAL_PRODUCER_EVALUATION.md)
binds future producer/model/dataset/policy identities to this same exact camera
source contract; it does not make the simulation camera physical evidence.

## Not implemented

- Real physical camera/driver integration, real calibration or synchronization,
  production diagnostics, and hardware validation; only the driver-neutral
  boundary and a programmatic TEST source are implemented
- RGB-D or depth transport
- Preprocessing, detection, tracking, face or owner recognition
- Object, person, identity, pose, gesture, OCR, or scene understanding
- Visual localization, SLAM, VSLAM, navigation, fusion, or trust scoring
- Camera-derived commands, motion authority, safety decisions, or durable
  telemetry
- Edge-device performance validation

## Exact manual graphical verification

After a clean build, launch the opt-in graphical development path:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=125
export GZ_PARTITION=ayyo_visual_camera_manual_125
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false enable_world_model:=true enable_camera:=true
```

In a second terminal with the same setup and isolation variables:

```bash
ros2 lifecycle get /ayyo_world_model
ros2 topic info /ayyo/camera/head/image_raw --verbose
ros2 topic echo --once /ayyo/camera/head/camera_info sensor_msgs/msg/CameraInfo
ros2 run ayyo_world_model body_state_query.py
ros2 run rqt_image_view rqt_image_view /ayyo/camera/head/image_raw
```

Confirm that the image view is nonempty and moves with the head frame, the
messages use `head_camera_optical_frame`, the query reports simulation-only
provenance, and camera health is absent. This manual step was not executed in
the milestone and is not claimed as verified. Stop both processes with
`Ctrl-C` and confirm the isolated graph and Gazebo processes terminate.
