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
- Standalone deterministic candidate validation with conservative identity and
  JSON normalization
- Typed duplicate, contradiction, correction, rejection, and review decisions
- Explicit evaluation/application separation using only the public Memory OS API
- Standalone Personal Context Twin v1 using only public, read-only Memory OS
  operations
- Exact owner isolation with deterministic resolved, conflicted, and unknown
  context states
- Immutable evidence-backed snapshots and canonical SHA-256 change versions
- Standalone Executive Cognition v1 with immutable structured requests,
  capability contracts, explicit proposal outcomes, and declarative plans
- Deterministic request, relevant-capability, relevant-context, and decision
  fingerprints with explicit stale-decision revalidation
- Fail-closed handling of unknown/unavailable capabilities and
  unknown/conflicted required owner context

## Planned, but not implemented

- Ayyo robot model
- Perception
- Provenance aggregation and advanced consolidation policy
- ROS 2 memory bridge
- Natural-language/model cognition integration
- Capability implementation discovery and Skill Manager integration
- Safety runtime
- Robot skills
- Simulation integration
- Manipulation integration
- Navigation integration
- Teach Mode
- Learning pipeline
- Physical hardware

The repository contains the engineering foundation, Memory OS core,
deterministic memory validation policy, a bounded owner-context read model, and
a deterministic proposal-only Executive layer. It does not provide inferred
personality, natural-language understanding, model reasoning, perception,
authorization, physical safety, execution, or simulated robot behavior.
