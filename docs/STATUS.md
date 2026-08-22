# Project Status

## Verified development environment

- Ubuntu 24.04 under WSL2
- ROS 2 Jazzy installed
- Gazebo Harmonic installed
- RViz2 installed
- MoveIt 2 installed
- Nav2 installed
- ros2_control installed
- ros_gz installed
- ROS publisher/subscriber smoke test passed
- Gazebo GUI smoke test passed
- RViz GUI smoke test passed

## Implemented

- Architecture, roadmap, and safety contracts
- ROS 2 workspace with minimal `ament_cmake` foundations for `ayyo_interfaces`,
  `ayyo_description`, and `ayyo_bringup`
- Local environment verification, build, and test scripts
- Standalone Memory OS core with typed records and mandatory provenance
- SQLite persistence with schema versioning, foreign keys, WAL journaling,
  transactional corrections, retractions, and conflict records
- Deterministic memory queries and revision/conflict inspection

## Planned, but not implemented

- Ayyo robot model
- Perception
- Personal Cognitive Twin (PCT)
- Memory validation and consolidation policy
- ROS 2 memory bridge
- Cognition
- Safety runtime
- Robot skills
- Simulation integration
- Manipulation integration
- Navigation integration
- Teach Mode
- Learning pipeline
- Physical hardware

The repository contains the engineering foundation and Memory OS core. It does
not provide owner modeling, cognition, perception, or simulated robot behavior.
