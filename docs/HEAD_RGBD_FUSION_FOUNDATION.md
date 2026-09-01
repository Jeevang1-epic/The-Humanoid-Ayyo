# Head RGB-D Synchronization and Fused Observation Foundation v1

## Purpose and scope

This milestone establishes a trustworthy temporal relationship between one
already-admitted head RGB observation and one already-admitted head-depth
observation. It proves that both compact observations belong to the same exact
source acquisition time under one reviewed TEST composition, then carries one
sealed immutable fused record through Perception, bounded Working Memory, and
the read-only World Model.

It does not perform computer vision, point-cloud generation, spatial
registration, 3D reconstruction, SLAM, navigation, manipulation, learning, or
actuation. Fused evidence has no motion, skill, Safety, Executive, Simulation
Control, or arbitrary-tool authority.

## Trust flow

```text
canonical RGB Image + CameraInfo
  -> compact admitted VisualFrameObservation
canonical depth Image + CameraInfo
  -> sealed admitted DepthFrameObservation
both exact source times equal
  -> bounded lifecycle RGB-D synchronizer
  -> sealed FusedRgbdObservation
  -> Perception Trust Boundary
  -> bounded Working Memory
  -> immutable World Model projection
  -> additive read-only GetRobotBodyState fields
```

Raw ROS messages never mutate Working Memory or the World Model. The
synchronizer accepts only compact domain observations. A constructed fused
Python value is not trusted: Perception requires the private admission issued
by the lifecycle synchronizer and verifies that its exact RGB and depth
components were separately admitted.

## Exact source identity and time

The v1 policy is `ayyo.rgbd.exact-source-time.v1`, version `1.0.0`. Pairing
uses the `observed_at_ns` values derived from the two ROS message headers. It
does not use callback arrival, wall-clock receipt, queue insertion order,
latest-frame state, nearest-neighbour selection, or an implicit tolerance.

The deterministic pair identity binds both observation identities, both
producer identities, reviewed source fingerprints, RGB/depth/synchronization
session identities, the exact shared acquisition timestamp, and pairing policy
identity/version. The fused identity additionally binds component
fingerprints, provenance, frames, calibration identities, result time, sensor,
and the explicit lack of validated spatial registration. Equal reviewed
evidence produces equal pair and observation identities.

## Frames and calibration

The component semantics remain independent and unchanged:

- RGB mount: `head_camera_frame`
- RGB optical frame: `head_camera_optical_frame`
- depth mount: `head_depth_camera_frame`
- depth optical frame: `head_depth_camera_optical_frame`

Each component retains its own immutable calibration identity. v1 validates
temporal synchronization only. `spatial_registration_validated` is always
`false`; the repository has no reviewed RGB-to-depth extrinsic or registration
record, so the contract makes no pixel-alignment or geometric claim.

## Provenance and lifecycle isolation

The executable proof is explicitly TEST-only:

- RGB: `ros.camera.head.rgb.depth.test-fixture.v1`, ROS 2 transport;
- depth: `ros.camera.head.depth.test-fixture.v1`, ROS 2 transport; and
- fusion: `ayyo.rgbd.head.test-synchronizer.v1`, direct domain transport.

All use the explicit `test_time` clock classification. The TEST fusion source
cannot be substituted for physical, simulation, or recorded evidence.

Activation requires the active depth lifecycle session and creates distinct
RGB-side and synchronization sessions. Deactivation clears both pending
queues. Reactivation creates new depth, RGB, and synchronization epochs. Old
depth sessions, inactive callbacks, and pending evidence from a previous epoch
fail closed and cannot repopulate fused state.

## Bounded state

The transport-neutral synchronizer has hard capacities of eight pending RGB
and eight pending depth observations. It stores compact observations only,
suppresses duplicates, removes stale entries, and deterministically evicts the
oldest acquisition time. Pending state is cleared on lifecycle transitions.

Working Memory stores one current fused state for the reviewed fusion sensor
plus references in its existing bounded recent-evidence capacity. It requires
the exact RGB and depth components to be current or recently retained.
Duplicates do not grow state, rejected evidence does not replace trusted
state, TTL expiry removes readiness, reset clears the epoch, and repeated
queries do not mutate memory.

The World Model exposes one immutable `ObservedFusedRgbdState` and sensor
availability/freshness. Its document and ROS query contain compact identities,
frames, calibration/source fingerprints, sessions, times, policy, and
provenance. Neither surface contains RGB or depth buffers.

## ROS 2 composition and query

The existing topics remain unchanged:

- `/ayyo/camera/head/image_raw`
- `/ayyo/camera/head/camera_info`
- `/ayyo/camera/head/depth/image_raw`
- `/ayyo/camera/head/depth/camera_info`

`head_rgbd_fusion_fixture.launch.py` is default off. Enabling it requires:

```text
enable_head_rgbd_fusion_fixture:=true
depth_camera_profile:=test_fixture_v1
rgbd_fusion_profile:=exact_test_fixture_v1
```

One owned fixture publishes tiny standard RGB and depth pairs with one shared
header timestamp. Disabled composition publishes no camera evidence and does
not configure the fusion sensor. The existing `GetRobotBodyState` service is
extended additively with compact `rgbd_*` fields; existing topics and request
semantics are unchanged.

## Fail-closed behavior and validation

Focused tests cover malformed/forged requirements, wrong robot/source/sensor,
cross-camera and optical-frame substitution, calibration and source-manifest
conflicts, degraded evidence, timestamp mismatch, missing counterparts,
duplicates, future/stale/regressed times, deterministic eviction, pair/fused
identity conflicts, private-seal enforcement, exact component admission,
inactive callbacks, old-session replay, reset/expiry, rejection recovery,
query stability, and lack of raw data or authority dependencies.

The resource proof processes 5,000 exact acquisition cycles. Pending RGB and
depth counts end at zero, accepted pairs equal 5,000, and traced Python memory
must remain below the test's fixed current/peak limits.

```bash
PYTHONPATH=world_model/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q rgbd_fusion/tests

./scripts/smoke_head_rgbd_fusion.sh
./scripts/smoke_head_rgbd_fusion.sh
```

The smoke owns every launched process, checks default-off behavior, verifies
the four canonical standard ROS topics, proves exact fused metadata through
the real read-only service, cycles lifecycle sessions, and requires an empty
owned process set and isolated ROS graph after shutdown.

## Physical-hardware migration

A physical implementation must add reviewed RGB and depth source manifests,
producer implementation fingerprints, a common or explicitly modeled clock,
validated lifecycle/session binding, and measured synchronization behavior.
Any nonzero timing tolerance must be a separate typed bounded policy and must
not alter the exact TEST policy. Pixel registration requires independently
reviewed intrinsics, RGB-to-depth extrinsics, registration behavior, and
hardware evidence before `spatial_registration_validated` can become true.

This milestone did not validate a physical RGB-D device, vendor driver,
hardware clock synchronization, transport jitter, RGB-to-depth extrinsics,
pixel registration, image/depth quality, point clouds, geometry, or physical
performance.
