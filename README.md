# Ayyo

Ayyo is a developmental personal humanoid companion project created by
P. Jeevan Kumar and Amrutha Sai Reddy. The project follows a software-first,
simulation-first approach so that cognition, safety, learning, and embodiment
can mature behind stable boundaries before physical hardware is introduced.

## Current status

Ayyo has reached the deterministic Executive Cognition v1 proposal stage.

Implemented:

- Repository structure, engineering conventions, and architecture documentation
- A ROS 2 workspace with three minimal package foundations
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

Planned, but not implemented:

- Ayyo robot model and simulation integration
- Perception
- Natural-language/model integration and an immutable safety runtime
- Robot skills, manipulation, and navigation
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
[docs/EXECUTIVE_COGNITION.md](docs/EXECUTIVE_COGNITION.md), and
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

## Repository layout

```text
docs/          Architecture, roadmap, safety, and status
memory/        Standalone Memory OS core and its tests
memory_validation/  Deterministic evidence policy layer and its tests
personal_context/  Deterministic owner-context projection and its tests
executive/     Deterministic Executive proposal planning and its tests
ros2_ws/src/   ROS 2 interfaces, description, and bringup packages
scripts/       Local environment, build, and test commands
tests/         Repository-level tests when justified
```

The roadmap defines the intended progression. Memory persistence, deterministic
candidate validation, Personal Context Twin v1, and Executive Cognition v1 are
implemented; authorization, safety, and robot runtime systems remain planned.
