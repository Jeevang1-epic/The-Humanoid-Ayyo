# Ayyo

Ayyo is a developmental personal humanoid companion project created by
P. Jeevan Kumar and Amrutha Sai Reddy. The project follows a software-first,
simulation-first approach so that cognition, safety, learning, and embodiment
can mature behind stable boundaries before physical hardware is introduced.

## Current status

Ayyo is at the deterministic Memory Validation Policy stage.

Implemented:

- Repository structure, engineering conventions, and architecture documentation
- A ROS 2 workspace with three minimal package foundations
- Local environment verification, build, and test scripts
- A verified local ROS 2, Gazebo, and RViz development setup
- A standalone, provenance-aware Memory OS core with SQLite persistence
- A standalone deterministic validation and consolidation policy for candidate
  memory evidence

Planned, but not implemented:

- Ayyo robot model and simulation integration
- Perception
- Personal Cognitive Twin
- Cognition and safety runtime
- Robot skills, manipulation, and navigation
- Teach Mode and learning pipeline
- Physical hardware

## Architecture

The planned system separates perception, world and memory state, owner modeling,
executive cognition, model access, planning, immutable safety enforcement, skill
management, and replaceable ROS 2 embodiment. Safety-critical controls remain
independent of cognition and learned policies. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/MEMORY_VALIDATION.md](docs/MEMORY_VALIDATION.md), and
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

Run Memory OS tests:

```bash
PYTHONPATH=memory/src python3 -m unittest discover -s memory/tests -v
```

Run Memory Validation tests:

```bash
PYTHONPATH=memory/src:memory_validation/src \
python3 -m unittest discover -s memory_validation/tests -v
```

## Repository layout

```text
docs/          Architecture, roadmap, safety, and status
memory/        Standalone Memory OS core and its tests
memory_validation/  Deterministic evidence policy layer and its tests
ros2_ws/src/   ROS 2 interfaces, description, and bringup packages
scripts/       Local environment, build, and test commands
tests/         Repository-level tests when justified
```

The roadmap defines the intended progression. Memory persistence and deterministic
candidate validation are implemented; the Personal Cognitive Twin and all
cognition and robot runtime systems remain planned.
