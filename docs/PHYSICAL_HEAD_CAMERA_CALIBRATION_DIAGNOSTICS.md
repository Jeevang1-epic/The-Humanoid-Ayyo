# Physical Head Camera, Calibration, and Diagnostics Foundation v1

## Purpose and status

This foundation defines the narrow path through which a future reviewed
physical head camera may provide visual evidence to Ayyo. It is driver-neutral,
default-off, and transport-neutral at its core. No physical camera was available
or used. The only executable source in this milestone is an explicitly named,
programmatic TEST fixture.

The foundation does not select or claim support for UVC, RealSense, OAK-D, CSI,
or any other device. It adds no vendor SDK, network dependency, camera-control
channel, movement authority, or skill-execution authority.

## Architecture

```text
future reviewed device and ROS driver
        ↓ standard sensor_msgs/Image + sensor_msgs/CameraInfo
explicit physical source manifest and active source session
        ↓
ROS metadata normalizer; raw Image bytes end in callback scope
        ↓
transport-neutral calibration, time, geometry, and pairing adapter
        ↓ sealed frame + separate acquisition-health evidence
existing Perception Trust Boundary
        ↓
bounded Working Memory
        ↓
immutable World Model
        ↓
existing read-only GetRobotBodyState query
```

Perception remains the sole evidence-admission boundary. The physical adapter
can create a sealed admission candidate, but only Perception can authorize and
admit its frame and health observations. Neither observation is an instruction.

## Source identities and provenance

`PhysicalCameraSourceManifest` is an immutable allowlist record binding the
canonical robot and camera, source and adapter implementation, source
classification, optional real device identity, distinct mount/optical frames,
fixed standard topics, `rgb8` and geometry bounds, ROS system-time provenance,
calibration identities, and a deterministic manifest fingerprint.

Absent serials or fingerprints remain `None`. Registration is idempotent only
when the whole manifest is identical; conflicting content fails closed. The
registry has a hard limit of 16 sources.

The automated source is deliberately identified as:

```text
classification: test_fixture
source:         ros.camera.head.physical.test-fixture.v1
sensor:         ayyo.camera.head.rgb.v1
optical frame:  head_camera_optical_frame
camera frame:   head_camera_frame
clock:          ros_system_time
transport:      ros2
interface:      sensor-msgs.image-camera-info.v1
device serial:  unknown
fingerprint:    unknown
```

Simulation remains `ros.camera.head.simulation.gz-harmonic.v1` with simulation
provenance and simulation time. Recorded evaluation retains recorded
provenance and time. A shared topic cannot convert either source into physical
evidence: manifest, sealed session, provenance, and trust policy must agree.

## Calibration semantics

`PhysicalCameraCalibration` wraps the existing bounded `CameraCalibration` and
adds exact camera, source, camera-frame, optical-frame, version, source class,
and optional import identity. The record retains bounded `D`, `K`, `R`, `P`,
binning, and ROI values outside Working Memory.

Validation rejects non-finite values, malformed or all-zero matrices,
impossible geometry, unsupported distortion models or coefficient counts,
wrong camera/source/frame binding, invalid ROI/binning, oversized metadata,
and fingerprints that do not match canonical content. Input is not repaired.
`None` means calibration is unknown; malformed supplied calibration is invalid.
Unknown calibration may be diagnosed but cannot activate acquisition.

Two compact identities are derived:

- `camera-calibration-sha256-*` covers standard calibration content.
- `physical-camera-calibration-sha256-*` also covers source, frame, version,
  calibration source, and import identity.

Only the compact standard calibration identity travels with a visual frame.
Full matrices never enter Working Memory, World Model, Memory OS, or the query.

ROS Jazzy on the validated environment does not currently have an installed
`camera_info_manager` package. This milestone therefore implements no file or
URL loader. A future reviewed loader should sit upstream of the core validator,
use only an explicit project-owned location, and reject traversal, symlink
escape, runtime-supplied paths, and remote URLs.

## Lifecycle and source sessions

The adapter uses `unconfigured`, `inactive`, `active`, and `finalized` states.
Configuration resolves one registered source and exact calibration. Activation
is allowed only from inactive and creates a new deterministic source session.
Evidence is rejected while inactive or under an old session.

Deactivation stops ROS subscriptions, clears both pairing collections, clears
the adapter session, and resets the physical composition's Perception and
Working Memory epochs. Reactivation creates a different session, so late
callbacks and pre-deactivation evidence cannot become current again. Cleanup
returns to unconfigured; shutdown finalizes the adapter.

## Timestamp and pairing rules

The Image header timestamp remains acquisition time. Receipt time, wall-clock
substitution, simulation time, and evaluation-result time never replace it.
The physical profile requires ROS system time. Stale, future, repeated,
regressed, out-of-order, cross-session, and wrong-clock evidence is rejected.

Image and CameraInfo metadata pair only when source, session, robot, camera,
optical frame, provenance, and exact timestamp match. Image geometry must match
the configured calibration; nearby arrival alone is insufficient. Each side
retains at most eight metadata references, uses a 200 ms default wait window,
and evicts the oldest timestamp deterministically. Raw bytes are not stored by
the core and leave scope after the existing ROS callback pipeline finishes.

## Diagnostics

`PhysicalCameraDiagnostics` is acquisition health, not scene understanding. It
contains typed lifecycle/calibration state, source/acquisition flags, bounded
counters and pending counts, an observed-frequency estimate when supported,
and one event such as frame accepted, missing calibration, wrong source/frame/
dimensions, invalid calibration, pair mismatch, stale/future/regressed time,
repeated timestamp, pending eviction, inactive lifecycle, or device error.

Dropped-frame count remains `None` because the fixture supplies no trustworthy
device sequence evidence. Absence of diagnostics does not imply health. A
successfully paired frame creates a separate compact `SensorHealthObservation`;
it grants no authority.

## Trust, memory, World Model, and query

Every physical RGB source requires one exact
`PhysicalCameraTrustRequirement`. It binds the manifest, adapter
implementation, classification, camera, provenance, calibration, and manifest
identity. The lifecycle adapter seals the frame and health pair. Perception
consumes each authorization once; bare, replayed, changed, simulation,
recorded, or unknown-adapter evidence fails closed. Unconsumed physical
authorizations share the existing hard bound of 64.

Working Memory and World Model reuse the existing compact visual-frame and
sensor-health contracts. One current visual state is retained per camera with
bounded recent evidence. No query API expansion was needed: the existing
read-only service exposes source provenance, optical frame, geometry, byte
count, calibration and observation identity, availability, and bounded health.
Repeated queries do not mutate state.

## ROS integration and default-off behavior

The fixed standard contracts remain:

```text
/ayyo/camera/head/image_raw    sensor_msgs/msg/Image
/ayyo/camera/head/camera_info  sensor_msgs/msg/CameraInfo
```

The physical path defaults to `enable_physical_camera_adapter=false` and
`physical_camera_profile=unconfigured`. V1 accepts only the explicit
`test_fixture_v1` profile and cannot run with the synthetic interpreter or
recorded-evaluation fixture. Simulation retains its separate source path.

The hardware-free launch contains no Gazebo, controller, command, action,
navigation, manipulation, or skill endpoint. Its robot-state and joint-state
publishers exist only to make the established body-state query ready for the
TEST proof.

## Resource proof and fixture

The standalone fixture exercises 5,000 accepted pairs through the adapter,
Perception, Working Memory, and World Model. It retains one visual state, one
health state, 16 recent evidence references, no pending pairs, at most 64 trust
references, and no raw pixels. `tracemalloc` is checked against a conservative
64 MiB ceiling. This is a desktop regression bound, not an edge-device claim.

The smoke proves opt-in behavior, exact TEST provenance, calibration identity,
wrong-frame and malformed-calibration rejection, recovery, deactivation, a new
reactivation session, no authority, owned-process shutdown, and an empty ROS
graph. It requires no hardware.

## Physical migration and manual validation

Before admitting a real camera, Jeevan should:

1. Select the device/driver and record exact package, version, and build
   identity; determine whether a stable serial or fingerprint truly exists.
2. Add a `PROJECT_REVIEWED_DEVICE` manifest and dedicated default-off profile;
   never rename or reuse the TEST profile.
3. Import real calibration from a controlled project-owned location and verify
   dimensions, optical frame, `D/K/R/P`, model, fingerprint, lens, and mount.
4. Confirm only the reviewed topics, optical frame, encoding, geometry,
   acquisition timestamps, matching CameraInfo, and clock domain are used.
5. Measure real rate, continuity, latency, bandwidth, drops, disconnect/
   reconnect behavior, clock regression, and lifecycle stop/start.
6. Prove wrong device, serial, calibration, frame, simulated time, stale queues,
   and late callbacks fail closed and that valid evidence then recovers.
7. Inspect orientation, mount alignment, focus, exposure, distortion, motion
   blur, and calibration accuracy with real scenes and calibration targets.
8. Repeat clean build, all tests and smokes, two consecutive physical smokes,
   and isolated graph/orphan checks before human review.

The repository cannot perform this procedure merely by setting a flag; a
reviewed real-source profile and loader must be implemented first.

## NOT VALIDATED

This milestone does **not** validate a real physical camera, hardware or driver
compatibility, USB/CSI bandwidth, actual frame rate or latency, physical clock
synchronization, real lens calibration or accuracy, thermal behavior,
edge-compute performance, graphical image quality, or production driver
stability. It also does not implement RGB-D/depth, camera controls, production
visual interpretation, SLAM, visual localization, fusion, recognition,
navigation, manipulation, or physical safety.

## Known limitations and recommended next step

Only the TEST physical profile is executable. There is no real-device manifest,
calibration loader, device discovery, vendor adapter, sequence-based drop
counter, camera-control API, or hardware diagnostic producer. The recommended
next milestone is a reviewed real-device profile and bounded calibration loader
with the selected hardware present, followed by hardware-in-the-loop camera
qualification.
