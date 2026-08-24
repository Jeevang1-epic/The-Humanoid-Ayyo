# Ayyo

Ayyo is a developmental personal humanoid companion project created by
P. Jeevan Kumar and Amrutha Sai Reddy. The project follows a software-first,
simulation-first approach so that cognition, safety, learning, and embodiment
can mature behind stable boundaries before physical hardware is introduced.

## Current status

Ayyo has reached the Embodied World Model and Working Memory Foundation v1
review stage.

Implemented:

- Repository structure, engineering conventions, and architecture documentation
- A ROS 2 workspace with interface/bringup foundations, installable Runtime
  Bridge and simulation-control packages, an authoritative robot-description
  package, and a dedicated Gazebo Harmonic simulation package
- Local environment verification, build, and test scripts
- A verified local ROS 2, Gazebo, and RViz development setup
- A standalone, provenance-aware Memory OS core with SQLite persistence
- A standalone deterministic validation and consolidation policy for candidate
  memory evidence
- A standalone, read-only Personal Context Twin that projects deterministic,
  owner-isolated, evidence-backed snapshots from Memory OS
- A standalone Executive Cognition layer that consumes PCT snapshots and emits
  deterministic declarative proposals, explicit blockers, and stale-decision
  evidence without execution or safety authority
- A standalone Immutable Safety Kernel that independently validates Executive
  proposal graphs, applies explicit fail-closed hazard policy, retains approval
  and safety prerequisites, and binds immutable decisions to proposal and
  policy fingerprints without executing actions
- A standalone Skill Manager that explicitly registers immutable skill and
  backend declarations, validates bounded parameter contracts, and binds
  unchanged Safety-reviewed proposal steps to inert, fingerprinted invocation
  contracts without executing skills or calling ROS
- A standalone ROS Runtime Bridge that reconstructs Skill Manager binding data,
  validates an exact service-only endpoint allowlist, emits deterministic
  dispatch-eligibility decisions, and models an unavailable-by-default
  transport boundary without a concrete ROS client or robot execution
- A modular 35-link, 34-joint canonical Ayyo humanoid frame tree with 18
  provisional movable joints, deterministic Xacro/URDF validation, isolated
  proxy geometry, and a machine-readable 33-part final-mesh contract
- Separate RViz-only and Gazebo Harmonic launch paths using the same
  authoritative Xacro, plus a static non-actuating simulation spawn and one
  explicit Gazebo-to-ROS clock bridge
- An opt-in Jazzy/Harmonic `gz_ros2_control` path with `AyyoSystem`, an
  authoritative `joint_state_broadcaster`, and one position command interface
  for the URDF-bounded `neck_yaw_joint`; non-control simulation remains static
- A standalone deterministic simulation-control core with canonical command,
  failure, result, Runtime Bridge evidence, URDF-limit, lifecycle, stale-time,
  and feedback contracts
- A separately flagged typed development ROS service that proves bounded motion
  from controller-derived state without arbitrary endpoint dispatch, plus
  non-control and controlled headless lifecycle smoke tests
- A standalone transport-neutral World Model with immutable provenance-bound
  robot/environment observations, authoritative URDF joint validation,
  deterministic freshness, and canonical current-state snapshots
- A standalone deterministic Working Memory with explicit TTL, bounded current
  entities, bounded recent evidence, duplicate suppression, out-of-order and
  future-time rejection, deterministic eviction, and no durable persistence
- A lifecycle-managed fixed `/joint_states` ROS observation adapter and typed
  read-only body-state query that distinguish simulation from future physical
  provenance and learn movement only from observed controller feedback

Planned, but not implemented:

- Final Ayyo CAD-derived visual/collision meshes and reviewed physical data
- Graphical Ayyo mesh/frame/collision validation
- Additional commandable joints, trajectory/whole-body control, and validated
  dynamics/contact behavior
- Physical/environment perception beyond standard joint-state feedback
- Natural-language/model integration and authenticated identity/approval
- Runtime skill implementations, manipulation, and navigation
- Production-authorized typed ROS services, runtime scheduling, and resource
  enforcement; Safety v1 still defers all physical movement
- Teach Mode and learning pipeline
- Physical hardware

## Architecture

The planned system separates perception, world and memory state, owner modeling,
executive cognition, model access, planning, immutable safety enforcement, skill
management, and replaceable ROS 2 embodiment. Safety-critical controls remain
independent of cognition and learned policies. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/MEMORY_VALIDATION.md](docs/MEMORY_VALIDATION.md),
[docs/PERSONAL_CONTEXT_TWIN.md](docs/PERSONAL_CONTEXT_TWIN.md),
[docs/EXECUTIVE_COGNITION.md](docs/EXECUTIVE_COGNITION.md),
[docs/SAFETY_KERNEL.md](docs/SAFETY_KERNEL.md),
[docs/SKILL_MANAGER.md](docs/SKILL_MANAGER.md),
[docs/ROS_RUNTIME_BRIDGE.md](docs/ROS_RUNTIME_BRIDGE.md),
[docs/ROBOT_DESCRIPTION_SIMULATION.md](docs/ROBOT_DESCRIPTION_SIMULATION.md),
[docs/SIMULATION_CONTROL.md](docs/SIMULATION_CONTROL.md),
[docs/WORLD_MODEL_WORKING_MEMORY.md](docs/WORLD_MODEL_WORKING_MEMORY.md),
[docs/AYYO_MESH_IMPORT.md](docs/AYYO_MESH_IMPORT.md), and
[docs/SAFETY.md](docs/SAFETY.md).

## Supported environment

- Ubuntu 24.04 under WSL2
- ROS 2 Jazzy
- Gazebo Harmonic
- RViz2
- MoveIt 2, Nav2, ros2_control, and ros_gz
- Python 3.12, CMake, and colcon

Verify the environment from a shell with ROS 2 sourced:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/verify_environment.sh
```

Build the workspace:

```bash
./scripts/build_workspace.sh
```

Run package tests:

```bash
./scripts/test_workspace.sh
```

Validate the authoritative robot description:

```bash
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
```

Run the opt-in headless simulation lifecycle after building:

```bash
./scripts/smoke_simulation.sh
```

Run the explicitly controlled one-joint headless lifecycle:

```bash
./scripts/smoke_simulation_control.sh
```

Run Memory OS tests:

```bash
PYTHONPATH=memory/src python3 -m unittest discover -s memory/tests -v
```

Run Memory Validation tests:

```bash
PYTHONPATH=memory/src:memory_validation/src \
python3 -m unittest discover -s memory_validation/tests -v
```

Run Personal Context Twin tests:

```bash
PYTHONPATH=memory/src:personal_context/src \
python3 -m unittest discover -s personal_context/tests -v
```

Run Executive Cognition tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src \
python3 -m unittest discover -s executive/tests -v
```

Run Immutable Safety Kernel tests:

```bash
PYTHONPATH=memory/src:memory_validation/src:personal_context/src:executive/src:safety_kernel/src \
python3 -m unittest discover -s safety_kernel/tests -v
```

Run Skill Manager tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src \
python3 -m unittest discover -s skill_manager/tests -v
```

Run ROS Runtime Bridge tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src \
python3 -m unittest discover -s runtime_bridge/tests -v
```

Run Simulation Control tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:simulation_control/src \
python3 -m unittest discover -s simulation_control/tests -v
```

Run World Model and Working Memory tests:

```bash
PYTHONPATH=world_model/src \
python3 -m unittest discover -s world_model/tests -v

PYTHONPATH=world_model/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v
```

Run the embodied feedback integration smoke after building:

```bash
./scripts/smoke_world_model.sh
```

## Repository layout

```text
docs/          Architecture, roadmap, safety, and status
memory/        Standalone Memory OS core and its tests
memory_validation/  Deterministic evidence policy layer and its tests
personal_context/  Deterministic owner-context projection and its tests
executive/     Deterministic Executive proposal planning and its tests
safety_kernel/  Immutable deterministic proposal safety review and its tests
skill_manager/  Immutable declarative skill contracts and Safety binding
runtime_bridge/  Deterministic Skill-to-ROS compatibility and transport boundary
simulation_control/  Bounded deterministic simulation-control policy and feedback
world_model/  Transport-neutral embodied/environment observations and snapshots
working_memory/  Bounded temporary current-state and recent-evidence retention
ros2_ws/src/   ROS 2 interfaces, description, simulation, Runtime Bridge, and bringup
scripts/       Local environment, build, and test commands
tests/         Repository-level tests when justified
```

The roadmap defines the intended progression. Memory persistence, deterministic
candidate validation, Personal Context Twin v1, Executive Cognition v1,
Immutable Safety Kernel v1, Skill Manager v1, controlled ROS Runtime Bridge v1,
Robot Description & Simulation Foundation v1, and the one-joint Simulation
Control & Actuation Foundation v1, and Embodied World Model and Working Memory
Foundation v1 are implemented. Production motion remains
closed because Safety v1 defers physical movement; only explicit development
injection can exercise the simulated neck joint. Final Ayyo assets,
authenticated identity/approval, production runtime services, additional
controllers, physical-safety subsystems, and physical robot execution remain
planned.
