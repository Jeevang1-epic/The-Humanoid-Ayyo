# Ayyo Robot Description & Simulation Foundation v1

## Status and scope

Robot Description & Simulation Foundation v1 provides a deterministic,
mesh-ready ROS 2 Jazzy description and a non-actuating Gazebo Harmonic
development boundary. It establishes the frame, joint, asset, launch, TF,
simulation, and future control contracts into which the reviewed Ayyo
mechanical design will be imported.

No final Ayyo visual or collision mesh is present. The default boxes are
explicit development proxy geometry for URDF, TF, RViz, spawn, and packaging
validation. They are not the Ayyo industrial design, validated collision
geometry, or a physical model. Dimensions, mass properties, limits, controller
gains, contact properties, and actuator selections remain design-dependent.

The automated headless smoke test has exercised Xacro expansion, URDF
validation, installed packages, ROS node startup, TF, Gazebo server launch,
entity spawn, the clock bridge, and bounded shutdown. The milestone's RViz and
Gazebo graphical inspections have not been executed and are not claimed as
passed.

## Package ownership

- `ayyo_description` single-owns the authoritative Xacro, materials, proxy
  visual/collision primitives, mesh contract, dormant ros2_control interface
  macro, RViz configuration, RViz-only launch, and description validator.
- `ayyo_simulation` owns the Gazebo Harmonic world, static entity-spawn
  composition, and explicit ROS-Gazebo clock bridge configuration.
- `ayyo_bringup` remains the existing general graph-composition foundation; it
  does not duplicate the description or simulation launch in v1.
- `ayyo_interfaces` is unchanged. This milestone has no justified command,
  perception, service, action, or controller interface to add.

Robot description and simulation have no dependency on Memory OS, Memory
Validation, Personal Context Twin, Executive Cognition, Safety Kernel, Skill
Manager, or Runtime Bridge.

## Coordinate and naming contract

Frames follow REP-103 conventions:

- right-handed coordinates;
- `+x` forward;
- `+y` left;
- `+z` up;
- SI metres, kilograms, radians, seconds;
- lowercase snake-case link and joint names; and
- `_link`, `_frame`, and `_joint` suffixes communicate role.

`base_link` is the canonical root and represents the robot body datum. The
development spawn places it at `z=0.95`, which brings the proxy feet to the
ground plane. Final base datum and ground-contact height require mechanical
design verification.

## Canonical frame tree

```text
base_link
└── pelvis_link
    ├── torso_link
    │   └── chest_link
    │       ├── neck_link
    │       │   └── head_link
    │       │       └── head_camera_frame
    │       ├── left_shoulder_mount_link
    │       │   └── left_shoulder_yaw_link
    │       │       └── left_upper_arm_link
    │       │           └── left_elbow_link
    │       │               └── left_forearm_link
    │       │                   └── left_wrist_link
    │       │                       └── left_hand_link
    │       └── right_shoulder_mount_link
    │           └── right_shoulder_yaw_link
    │               └── right_upper_arm_link
    │                   └── right_elbow_link
    │                       └── right_forearm_link
    │                           └── right_wrist_link
    │                               └── right_hand_link
    ├── left_hip_mount_link
    │   └── left_hip_yaw_link
    │       └── left_thigh_link
    │           └── left_knee_link
    │               └── left_shin_link
    │                   └── left_ankle_link
    │                       └── left_foot_link
    └── right_hip_mount_link
        └── right_hip_yaw_link
            └── right_thigh_link
                └── right_knee_link
                    └── right_shin_link
                        └── right_ankle_link
                            └── right_foot_link
```

The camera frame is a mounting datum only. No camera, sensor plugin,
perception topic, or perception behavior exists.

## Joint contract

All origins are `xyz` metres at zero `rpy`. Axes are expressed in the parent
joint frame. Fixed joints have no actuator or limit. Each revolute joint is a
provisional one-actuator relationship for description and interface design;
the final transmission, actuator, encoder, reduction, continuous torque,
velocity, range, and safety limits require reviewed Ayyo hardware data.

| Joint | Parent → child | Origin | Axis | Type | Lower / upper (rad) | Effort / velocity | Intended relationship |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `base_to_pelvis_joint` | `base_link` → `pelvis_link` | `0 0 0` | — | fixed | — | — | Body datum, no actuator |
| `pelvis_to_torso_joint` | `pelvis_link` → `torso_link` | `0 0 0.08` | — | fixed | — | — | V1 rigid spine datum |
| `torso_to_chest_joint` | `torso_link` → `chest_link` | `0 0 0.18` | — | fixed | — | — | V1 rigid chest datum |
| `neck_yaw_joint` | `chest_link` → `neck_link` | `0 0 0.20` | `0 0 1` | revolute | `-1.2 / 1.2` | `8 / 1.5` | Provisional neck-yaw actuator |
| `head_pitch_joint` | `neck_link` → `head_link` | `0 0 0.10` | `0 1 0` | revolute | `-0.6 / 0.6` | `8 / 1.2` | Provisional head-pitch actuator |
| `head_camera_mount_joint` | `head_link` → `head_camera_frame` | `0.105 0 0.13` | — | fixed | — | — | Reviewed future sensor mount |
| `left_shoulder_mount_joint` | `chest_link` → `left_shoulder_mount_link` | `0 0.14 0.13` | — | fixed | — | — | Left shoulder datum |
| `left_shoulder_yaw_joint` | `left_shoulder_mount_link` → `left_shoulder_yaw_link` | `0 0.05 0` | `0 0 1` | revolute | `-1.2 / 1.2` | `20 / 1.2` | Provisional shoulder-yaw actuator |
| `left_shoulder_pitch_joint` | `left_shoulder_yaw_link` → `left_upper_arm_link` | `0 0 0` | `0 1 0` | revolute | `-1.8 / 1.8` | `20 / 1.2` | Provisional shoulder-pitch actuator |
| `left_upper_arm_to_elbow_joint` | `left_upper_arm_link` → `left_elbow_link` | `0 0 -0.28` | — | fixed | — | — | Elbow datum |
| `left_elbow_flex_joint` | `left_elbow_link` → `left_forearm_link` | `0 0 0` | `0 1 0` | revolute | `0 / 2.2` | `15 / 1.5` | Provisional elbow-flex actuator |
| `left_wrist_yaw_joint` | `left_forearm_link` → `left_wrist_link` | `0 0 -0.24` | `0 0 1` | revolute | `-1.5 / 1.5` | `5 / 1.5` | Provisional wrist-yaw actuator |
| `left_wrist_to_hand_joint` | `left_wrist_link` → `left_hand_link` | `0 0 -0.08` | — | fixed | — | — | V1 rigid hand datum |
| `right_shoulder_mount_joint` | `chest_link` → `right_shoulder_mount_link` | `0 -0.14 0.13` | — | fixed | — | — | Right shoulder datum |
| `right_shoulder_yaw_joint` | `right_shoulder_mount_link` → `right_shoulder_yaw_link` | `0 -0.05 0` | `0 0 1` | revolute | `-1.2 / 1.2` | `20 / 1.2` | Provisional shoulder-yaw actuator |
| `right_shoulder_pitch_joint` | `right_shoulder_yaw_link` → `right_upper_arm_link` | `0 0 0` | `0 1 0` | revolute | `-1.8 / 1.8` | `20 / 1.2` | Provisional shoulder-pitch actuator |
| `right_upper_arm_to_elbow_joint` | `right_upper_arm_link` → `right_elbow_link` | `0 0 -0.28` | — | fixed | — | — | Elbow datum |
| `right_elbow_flex_joint` | `right_elbow_link` → `right_forearm_link` | `0 0 0` | `0 1 0` | revolute | `0 / 2.2` | `15 / 1.5` | Provisional elbow-flex actuator |
| `right_wrist_yaw_joint` | `right_forearm_link` → `right_wrist_link` | `0 0 -0.24` | `0 0 1` | revolute | `-1.5 / 1.5` | `5 / 1.5` | Provisional wrist-yaw actuator |
| `right_wrist_to_hand_joint` | `right_wrist_link` → `right_hand_link` | `0 0 -0.08` | — | fixed | — | — | V1 rigid hand datum |
| `left_hip_mount_joint` | `pelvis_link` → `left_hip_mount_link` | `0 0.085 -0.10` | — | fixed | — | — | Left hip datum |
| `left_hip_yaw_joint` | `left_hip_mount_link` → `left_hip_yaw_link` | `0 0 -0.04` | `0 0 1` | revolute | `-0.6 / 0.6` | `40 / 1.0` | Provisional hip-yaw actuator |
| `left_hip_pitch_joint` | `left_hip_yaw_link` → `left_thigh_link` | `0 0 0` | `0 1 0` | revolute | `-1.0 / 1.2` | `45 / 1.0` | Provisional hip-pitch actuator |
| `left_thigh_to_knee_joint` | `left_thigh_link` → `left_knee_link` | `0 0 -0.34` | — | fixed | — | — | Knee datum |
| `left_knee_flex_joint` | `left_knee_link` → `left_shin_link` | `0 0 0` | `0 1 0` | revolute | `0 / 2.0` | `45 / 1.0` | Provisional knee-flex actuator |
| `left_ankle_pitch_joint` | `left_shin_link` → `left_ankle_link` | `0 0 -0.34` | `0 1 0` | revolute | `-0.6 / 0.6` | `35 / 1.0` | Provisional ankle-pitch actuator |
| `left_ankle_to_foot_joint` | `left_ankle_link` → `left_foot_link` | `0 0 -0.04` | — | fixed | — | — | V1 rigid foot datum |
| `right_hip_mount_joint` | `pelvis_link` → `right_hip_mount_link` | `0 -0.085 -0.10` | — | fixed | — | — | Right hip datum |
| `right_hip_yaw_joint` | `right_hip_mount_link` → `right_hip_yaw_link` | `0 0 -0.04` | `0 0 1` | revolute | `-0.6 / 0.6` | `40 / 1.0` | Provisional hip-yaw actuator |
| `right_hip_pitch_joint` | `right_hip_yaw_link` → `right_thigh_link` | `0 0 0` | `0 1 0` | revolute | `-1.0 / 1.2` | `45 / 1.0` | Provisional hip-pitch actuator |
| `right_thigh_to_knee_joint` | `right_thigh_link` → `right_knee_link` | `0 0 -0.34` | — | fixed | — | — | Knee datum |
| `right_knee_flex_joint` | `right_knee_link` → `right_shin_link` | `0 0 0` | `0 1 0` | revolute | `0 / 2.0` | `45 / 1.0` | Provisional knee-flex actuator |
| `right_ankle_pitch_joint` | `right_shin_link` → `right_ankle_link` | `0 0 -0.34` | `0 1 0` | revolute | `-0.6 / 0.6` | `35 / 1.0` | Provisional ankle-pitch actuator |
| `right_ankle_to_foot_joint` | `right_ankle_link` → `right_foot_link` | `0 0 -0.04` | — | fixed | — | — | V1 rigid foot datum |

Effort and velocity values are development metadata, not a physical-safety
contract. Positive bilateral rotations share the same parent-frame axis; the
manual RViz inspection must verify whether the final mechanism requires a
mirrored actuator sign convention.

## Geometry and mesh modes

Default `use_meshes:=false` expands 33 visual boxes and 33 separately declared
collision boxes. Proxy visual and collision elements use the same dimensions
only for early deterministic tests; this does not establish a production rule.

`use_meshes:=true` binds exactly the 33 names in
`meshes/mesh_contract.json` to:

```text
package://ayyo_description/meshes/visual/<part>.dae
package://ayyo_description/meshes/collision/<part>.stl
```

That mode is reserved for reviewed final assets. It currently points to absent
files by design and must not be used for a passing graphical validation. The
manifest truthfully records `final_assets_not_present`; normalized runtime
scale is `1 1 1`. Proxy mode uses named Xacro colors; mesh mode deliberately
omits that override so reviewed embedded DAE materials remain authoritative.
See [AYYO_MESH_IMPORT.md](AYYO_MESH_IMPORT.md) for the import gate.

## Public launch interfaces

### RViz-only description display

```bash
ros2 launch ayyo_description view_robot.launch.py \
  use_meshes:=false \
  use_joint_state_publisher_gui:=false \
  start_rviz:=true \
  use_sim_time:=false
```

The launch starts `robot_state_publisher`, one of the CLI or GUI development
joint-state publishers, and optional RViz. It does not start Gazebo or claim
physical simulation.

### Gazebo Harmonic simulation

```bash
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true \
  use_meshes:=false \
  spawn_x:=0.0 spawn_y:=0.0 spawn_z:=0.95 spawn_yaw:=0.0
```

The launch starts Gazebo Harmonic server-only by default, publishes the same
Xacro description, publishes zero development joint states, bridges the clock,
and spawns a static non-actuating entity named `ayyo`. `headless:=false` adds
the Gazebo graphical client. RViz is intentionally not composed into this
launch.

## Gazebo and ros_gz boundary

`ayyo_foundation.sdf` owns only a controlled ground plane, directional light,
physics configuration, and the Harmonic Physics, UserCommands, and
SceneBroadcaster systems. It contains no duplicate Ayyo model.

`ros_gz_bridge.yaml` has one allowlisted interface:

| Gazebo | ROS 2 | Direction | Reason |
| --- | --- | --- | --- |
| `/clock` `gz.msgs.Clock` | `/clock` `rosgraph_msgs/msg/Clock` | Gazebo → ROS | Drive `use_sim_time` for description nodes |

There is no wildcard bridge, command bridge, joint command, sensor stream,
service, or action. No Gazebo Classic package, API, or plugin is used.

## ros2_control readiness

`ayyo_ros2_control.xacro` contains a dormant `ayyo_ros2_control_system` macro
with position command and position/velocity/effort state interfaces for the 18
movable joints. It is included for a stable future interface location but is
never invoked by Foundation v1. It supplies no hardware plugin, transmission,
controller manager, controller configuration, controller, gain, or command.
Joint limits remain single-owned by the URDF joint contract.

The future flow is:

```text
authoritative robot_description
→ explicitly reviewed ros2_control system invocation
→ controller_manager
→ joint_state_broadcaster
→ reviewed simulation hardware plugin or physical hardware interface
→ explicitly reviewed controllers
```

Future controller configuration belongs under `ayyo_simulation/config/` for
simulation and in a separately reviewed hardware integration package for the
physical robot. It must not silently share a mock hardware identity.

## Runtime and safety boundary

The simulation launch is developer tooling. It may publish zero joint states
for TF and may spawn a static entity, but it exposes no movement command path.
It is not production runtime authorization and does not consume Runtime Bridge
requests.

Any future actuation path remains:

```text
Executive Cognition
→ Immutable Safety Kernel
→ Skill Manager
→ ROS Runtime Bridge
→ one statically reviewed typed ROS adapter
→ dedicated motion/contact/workspace safety and controller boundary
→ simulation or hardware
```

Robot description and simulation cannot import higher layers. Future adapters
must be pinned to exact Runtime Bridge service endpoint contracts; arbitrary
topic publication, service calls, action goals, graph discovery, and raw
controller dispatch remain forbidden.

## Automated validation

Run deterministic description validation from source:

```bash
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
```

After building, run the complete headless lifecycle smoke:

```bash
./scripts/build_workspace.sh
./scripts/smoke_simulation.sh
```

The smoke command verifies installed package lookup, installed description
validation, node startup, TF, clock bridge health, Gazebo entity discovery, and
bounded SIGINT/SIGTERM shutdown. It does not start a graphical desktop.

## Manual graphical validation

Build and source the workspace first:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/build_workspace.sh
source ros2_ws/install/setup.bash
```

RViz2 visual smoke test:

```bash
ros2 launch ayyo_description view_robot.launch.py \
  use_meshes:=false use_joint_state_publisher_gui:=true
```

Inspect orientation, overall scale, base/pelvis and limb frame placement, link
continuity, left/right symmetry, clipping/intersections, TF names, and each
joint's positive rotation direction. Proxy collision alignment can be enabled
in the RobotModel display, but matching proxies do not validate production
collision assets.

Gazebo Harmonic graphical smoke test:

```bash
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false use_meshes:=false spawn_z:=0.95
```

Inspect world orientation, ground contact, robot scale, link continuity,
left/right symmetry, clipping, proxy collision alignment, and entity pose. The
entity is intentionally static; this test cannot validate dynamics, controller
behavior, joint actuation, walking, or physical stability.

For final meshes, additionally inspect mesh origin/pivot placement, visual
materials, collision simplification, collision-to-visual alignment, and every
joint through its intended range. Record results explicitly; do not infer a
pass from successful launch.

## Deliberate limitations and blockers

- Final Ayyo CAD-derived visual and collision meshes are absent.
- Dimensions, inertias, centre of mass, joint topology, axes, and limits require
  mechanical review against the final design.
- No graphical Ayyo model inspection was executed in this milestone run.
- No `gz_ros2_control` or other hardware plugin is selected or loaded.
- No controller manager, joint-state broadcaster, command controller,
  transmission, actuator model, or controller gains exist.
- The spawned model is static and non-actuating; dynamics are not validated.
- No perception, MoveIt, navigation, autonomous walking, hardware driver,
  physical communication, runtime adapter, or physical-safety system exists.
