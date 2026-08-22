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

## Planned, but not implemented

- Ayyo robot model
- Perception
- Memory OS
- Personal Cognitive Twin (PCT)
- Cognition
- Safety runtime
- Robot skills
- Simulation integration
- Manipulation integration
- Navigation integration
- Teach Mode
- Learning pipeline
- Physical hardware

The repository contains engineering infrastructure only; it does not provide an
Ayyo application runtime or simulated robot behavior yet.
